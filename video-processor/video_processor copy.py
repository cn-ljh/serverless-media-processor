import tempfile
import os
import hashlib
import logging
from typing import Dict, Tuple, List
from s3_operations import (
    S3Config, 
    get_s3_client, 
    download_object_from_s3, 
    get_full_s3_key,
    generate_presigned_url
)
from video_snapshots import VideoSnapshots

# Configure logging for AWS Lambda
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Prevent duplicate log messages
for handler in logger.handlers:
    logger.removeHandler(handler)

# Add StreamHandler for CloudWatch
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '[%(levelname)s] %(asctime)s.%(msecs)dZ %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
))
logger.addHandler(handler)

class VideoProcessor:
    # Supported video codecs
    SUPPORTED_CODECS = ['h264', 'h265']
    # Supported output formats
    SUPPORTED_FORMATS = ['jpg', 'png']
    # Supported rotation modes
    ROTATION_MODES = ['auto', 'h', 'w']

    @staticmethod
    def parse_snapshot_params(operations: str) -> Dict:
        """Parse and validate snapshot operation parameters"""
        if not operations:
            raise ValueError("No operations specified")

        # Initialize default values
        params = {
            't': 0,  # Default to first frame
            'w': 0,  # Default to auto-calculate
            'h': 0,  # Default to auto-calculate
            'm': 'default',  # Default mode
            'f': 'jpg',  # Default format
            'ar': 'auto'  # Default auto rotation
        }

        # Split operations string and parse parameters
        try:
            ops = operations.split(',')
            if ops[0] != 'snapshot':
                raise ValueError("First operation must be 'snapshot'")

            for op in ops[1:]:
                key, value = op.split('_')
                if key not in params:
                    raise ValueError(f"Invalid parameter: {key}")
                params[key] = value

            # Validate parameters
            VideoProcessor._validate_params(params)

            return params
        except ValueError as e:
            raise ValueError(f"Invalid operation format: {str(e)}")

    @staticmethod
    def _validate_params(params: Dict) -> None:
        """Validate snapshot parameters"""
        # Validate time
        try:
            params['t'] = int(params['t'])
            if params['t'] < 0:
                raise ValueError("Time must be non-negative")
        except ValueError:
            raise ValueError("Invalid time value")

        # Validate dimensions
        try:
            params['w'] = int(params['w'])
            params['h'] = int(params['h'])
            if params['w'] < 0 or params['h'] < 0:
                raise ValueError("Dimensions must be non-negative")
        except ValueError:
            raise ValueError("Invalid dimension values")

        # Validate mode
        if params['m'] not in ['default', 'fast']:
            raise ValueError("Invalid mode. Must be 'default' or 'fast'")

        # Validate format
        if params['f'] not in VideoProcessor.SUPPORTED_FORMATS:
            raise ValueError(f"Unsupported format. Must be one of {VideoProcessor.SUPPORTED_FORMATS}")

        # Validate rotation
        if params['ar'] not in VideoProcessor.ROTATION_MODES:
            raise ValueError(f"Invalid rotation mode. Must be one of {VideoProcessor.ROTATION_MODES}")

    @staticmethod
    def validate_video(video_info: Dict) -> None:
        """Validate video codec and color space"""
        # Check codec support
        codec = video_info.get('codec_name', '').lower()
        if codec not in VideoProcessor.SUPPORTED_CODECS:
            raise ValueError(f"Unsupported codec. Must be one of {VideoProcessor.SUPPORTED_CODECS}")

        # Check color space
        if video_info.get('color_space') == 'bt2020':
            raise ValueError("BT.2020 color space is not supported")

    @staticmethod
    def process_video(video_key: str, operations: str = None) -> Tuple[bytes, Dict]:
        """
        Process video with specified operations
        
        Args:
            video_key: Video file key/path
            operations: Operation string (e.g., 'snapshot,t_7000,f_jpg,w_800,h_600,m_fast')
            
        Returns:
            Tuple of (processed frame data, response headers)
            
        Raises:
            Exception: If operation fails
        """
        logger.info(f"Starting video processing for key: {video_key}")
        logger.info(f"Operation parameters: {operations}")
        
        try:
            # Get S3 configuration and client
            s3_config = S3Config()
            s3_client = get_s3_client()
            s3_key = get_full_s3_key(video_key)
            
            # Generate presigned URL with longer expiration for large videos
            video_url = generate_presigned_url(
                s3_client,
                s3_config.bucket_name,
                s3_key,
                expiration=7200  # 2 hours
            )
            
            # Parse and validate parameters
            params = VideoProcessor.parse_snapshot_params(operations)
            logger.info(f"Parsed parameters: {params}")
            
            # Convert target time from milliseconds to seconds
            target_time = params['t']/1000
            logger.info(f"Target frame time: {target_time}s")

            # Get video info with smart keyframe analysis around target time
            logger.info("Fetching video metadata with targeted keyframe analysis...")
            video_info = VideoSnapshots.get_video_info(
                video_url, 
                analyze_keyframes=True,
                target_time=target_time
            )
            VideoProcessor.validate_video(video_info)
            
            # Log video properties
            logger.info(
                f"Video metadata: codec={video_info.get('codec_name')}, "
                f"duration={video_info.get('duration')}s, "
                f"fps={video_info.get('fps', 'unknown')}, "
                f"bitrate={video_info.get('bit_rate', 'unknown')}"
            )
            
            # Determine if we should use segmented extraction
            duration = float(video_info.get('duration', 0)) or float(video_info.get('format_duration', 0))
            time_to_end = duration - target_time
            
            # Use segmented extraction if:
            # 1. Video is from HTTP source (presigned URL)
            # 2. Not too close to the end
            # 3. Not in fast mode (which only uses keyframes)
            use_segments = (
                video_url.startswith('http') and
                time_to_end > min(duration * 0.1, 5) and
                params['m'] != 'fast'
            )
            
            logger.info(f"Using {'segmented' if use_segments else 'direct'} frame extraction")
            
            # Extract frame with optimized approach
            frame_data = VideoSnapshots.extract_frame(
                video_url,
                params,
                video_info,
                use_segments=use_segments
            )
            
            # Set appropriate headers
            content_type = f"image/{params['f'].lower()}"
            etag = hashlib.md5(frame_data).hexdigest()
            cache_control = "public, max-age=3600"
            
            headers = {
                'Content-Type': content_type,
                'Cache-Control': cache_control,
                'ETag': etag,
                'Content-Disposition': f'inline; filename="frame_{params["t"]}ms.{params["f"]}"'
            }
            
            # Clean up old cached segments
            # Keep only the 5 most recently used segments
            cache = VideoSnapshots._segment_cache
            if len(cache) > 5:
                oldest_keys = sorted(cache.keys())[:-5]
                for key in oldest_keys:
                    if key in cache:
                        try:
                            os.unlink(cache[key])
                        except (OSError, FileNotFoundError):
                            pass
                        del cache[key]
            
            return frame_data, headers
            
        except Exception as e:
            logger.error(f"Error processing video: {str(e)}")
            raise
