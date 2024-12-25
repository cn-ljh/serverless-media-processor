import tempfile
import os
import hashlib
import logging
from typing import Dict, Tuple
from s3_operations import S3Config, get_s3_client, download_object_from_s3, get_full_s3_key
from video_snapshots import VideoSnapshots

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

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
        temp_file = None
        logger.info(f"Processing video. Key: {video_key}")
        
        try:
            # Get S3 configuration and client
            s3_config = S3Config()
            s3_client = get_s3_client()
            s3_key = get_full_s3_key(video_key)
            video_data = download_object_from_s3(s3_client, s3_config.bucket_name, s3_key)
            
            # Save to temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(video_key)[1])
            temp_file.write(video_data)
            temp_file.close()
            
            # Parse and validate parameters
            params = VideoProcessor.parse_snapshot_params(operations)
            
            # Get video info and validate
            video_info = VideoSnapshots.get_video_info(temp_file.name)
            VideoProcessor.validate_video(video_info)
            
            # Extract frame
            frame_data = VideoSnapshots.extract_frame(temp_file.name, params, video_info)
            
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
            
            return frame_data, headers
            
        except Exception as e:
            logger.error(f"Error processing video: {str(e)}")
            raise
        finally:
            # Clean up temporary file
            if temp_file and os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
