import json
import subprocess
import shlex
from typing import Dict, Optional, Tuple, BinaryIO, List
import os
import tempfile
import math
import logging
import hashlib

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

class VideoSnapshots:
    @staticmethod
    def _run_ffmpeg_command(command: List[str], error_prefix: str) -> None:
        """
        Run an FFmpeg command with proper error handling and logging
        
        Args:
            command: FFmpeg command as list of strings
            error_prefix: Prefix for error messages
        """
        logger.info(f"Executing command: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            error_msg = f"{error_prefix}: {result.stderr}"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        if result.stderr:
            logger.debug(f"Command stderr: {result.stderr}")
    @staticmethod
    def get_video_duration(video_info: Dict) -> float:
        """
        Get video duration in seconds from video info
        
        Args:
            video_info: Video metadata from ffprobe
            
        Returns:
            float: Duration in seconds
        """
        try:
            # Try to get duration from different possible locations
            duration = None
            
            # Try duration from video stream
            if 'duration' in video_info:
                duration = float(video_info['duration'])
            
            # Try duration from format information
            elif 'format' in video_info and 'duration' in video_info['format']:
                duration = float(video_info['format']['duration'])
                
            # Try time_base * nb_frames if available
            elif all(key in video_info for key in ['time_base', 'nb_frames']):
                time_base = eval(video_info['time_base'])  # Usually in format '1/25'
                nb_frames = int(video_info['nb_frames'])
                duration = time_base * nb_frames
                
            if duration is not None and duration > 0:
                logger.info(f"Found video duration: {duration} seconds")
                return duration
                
            logger.warning("Could not determine video duration, using default")
            return 0
            
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing duration: {str(e)}")
            return 0

    @staticmethod
    def calculate_segments(video_info: Dict, frame_times: List[float]) -> List[Tuple[float, float]]:
        """
        Calculate optimal video segments based on video metadata and requested frame times
        with smart GOP (Group of Pictures) estimation
        
        Args:
            video_info: Video metadata from ffprobe including keyframe positions and fps
            frame_times: List of frame timestamps in seconds to extract
            
        Returns:
            List of tuples containing (start_time, end_time) in seconds
        """
        if not frame_times:
            return []
            
        # Get video duration and fps
        duration = float(video_info.get('duration', 0)) or float(video_info.get('format_duration', 0))
        fps = float(video_info.get('fps', 30))
        
        if duration <= 0:
            logger.warning("Could not determine video duration")
            duration = 300  # Default to 5 minutes
            
        # Ensure frame times don't exceed video duration
        frame_times = [min(t, duration) for t in frame_times]
        
        # Estimate GOP size based on fps and video properties
        bit_rate = float(video_info.get('bit_rate', 0))
        if bit_rate > 0:
            # Higher bitrate videos typically have longer GOPs
            estimated_gop_size = min(4.0, max(1.0, fps / 10))
        else:
            # Conservative GOP estimate for unknown bitrate
            estimated_gop_size = min(2.0, fps / 15)
        
        logger.info(f"Initial GOP size estimate: {estimated_gop_size:.2f}s")
        
        keyframes = video_info.get('keyframe_positions', [])
        if keyframes:
            # Calculate actual GOP size from keyframes if available
            gop_sizes = [j-i for i, j in zip(keyframes[:-1], keyframes[1:])]
            if gop_sizes:
                actual_gop_size = sum(gop_sizes) / len(gop_sizes)
                # Use weighted average of estimated and actual GOP size
                estimated_gop_size = (estimated_gop_size + actual_gop_size * 2) / 3
                logger.info(f"Adjusted GOP size using keyframe data: {estimated_gop_size:.2f}s")
            
        # Group frame times into ranges based on GOP size
        frame_ranges = []
        sorted_times = sorted(frame_times)
        current_range = [sorted_times[0]]
        
        # Use GOP size to determine grouping threshold
        group_threshold = estimated_gop_size * 10  # Group frames within 10 GOPs
        
        for time in sorted_times[1:]:
            if time - current_range[-1] > group_threshold:
                frame_ranges.append(current_range)
                current_range = [time]
            else:
                current_range.append(time)
        frame_ranges.append(current_range)
        
        # Create optimized segments based on frame ranges and GOP boundaries
        segments = []
        for frame_range in frame_ranges:
            range_start = frame_range[0]
            range_end = frame_range[-1]
            
            if keyframes:
                # Find nearest keyframes before and after the range
                prev_keyframe = max((k for k in keyframes if k <= range_start), default=range_start)
                next_keyframe = min((k for k in keyframes if k >= range_end), default=range_end)
                
                # Extend segment to include keyframes with smart buffering
                buffer = min(estimated_gop_size, 1.0)  # Use GOP size for buffer, max 1 second
                segment_start = max(0, prev_keyframe - buffer)
                segment_end = min(duration, next_keyframe + buffer)
            else:
                # If no keyframe data, use GOP-based segmentation
                buffer = estimated_gop_size * 2  # Two GOPs worth of buffer
                segment_start = max(0, range_start - buffer)
                segment_end = min(duration, range_end + buffer)
            
            # Merge segments that are close together
            if segments and segment_start - segments[-1][1] < estimated_gop_size * 2:
                segments[-1] = (segments[-1][0], segment_end)
            else:
                segments.append((segment_start, segment_end))
            
        return segments

    @staticmethod
    def get_segment_cache_key(video_path: str, start: float, end: float) -> str:
        """Generate cache key for video segment"""
        return f"{hashlib.md5(video_path.encode()).hexdigest()}_{start}_{end}"

    _segment_cache = {}  # Class variable for segment caching

    @staticmethod
    def get_cached_segment(cache_key: str) -> Optional[str]:
        """Get cached segment file path if it exists and is valid"""
        if cache_key in VideoSnapshots._segment_cache:
            path = VideoSnapshots._segment_cache[cache_key]
            if os.path.exists(path):
                return path
            else:
                del VideoSnapshots._segment_cache[cache_key]
        return None

    @staticmethod
    def cache_segment(cache_key: str, segment_path: str) -> None:
        """Cache segment file path"""
        VideoSnapshots._segment_cache[cache_key] = segment_path

    @staticmethod
    def download_segment(video_url: str, start_time: float, duration: float) -> str:
        """
        Download a specific segment of the video
        
        Args:
            video_url: URL of the video (can be a presigned URL)
            start_time: Segment start time in seconds
            duration: Segment duration in seconds
            
        Returns:
            Path to the downloaded segment file
        """
        try:
            # Create temporary file for the segment
            temp_file = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False)
            output_path = temp_file.name
            temp_file.close()
            
            # For seeking near the end of video, we need to be more careful with the command
            command = [
                'ffmpeg',
                '-y',
                '-ss', str(start_time),  # Seek before input for faster seeking
                '-i', video_url,
                '-t', str(duration),  # Use -t instead of -to for better compatibility
                '-c', 'copy',  # Copy without re-encoding
                '-copyts',  # Preserve timestamps
                output_path
            ]
            
            logger.info(f"Downloading segment: start={start_time}s, duration={duration}s")
            
            VideoSnapshots._run_ffmpeg_command(command, "Failed to download segment")
            
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise Exception("Failed to create segment file or file is empty")
                
            logger.info(f"Successfully downloaded segment to {output_path}")
                
            return output_path
            
        except Exception as e:
            raise Exception(f"Error downloading video segment: {str(e)}")

    @staticmethod
    def run_ffprobe(video_path: str, analyze_keyframes: bool = False, start_time: float = None, duration: float = None) -> Dict:
        """
        Run ffprobe command to get video metadata efficiently using HTTP range requests
        
        Args:
            video_path: Path or URL to the video file
            analyze_keyframes: Whether to analyze keyframe positions (takes longer)
            start_time: Optional start time for partial analysis (in seconds)
            duration: Optional duration for partial analysis (in seconds)
            
        Returns:
            Dict containing video metadata
        """
        # Base command for quick metadata retrieval
        base_command = [
            'ffprobe',
            '-v', 'quiet',
            '-select_streams', 'v:0',  # Only first video stream
            '-show_entries', 'stream=width,height,codec_name,duration,color_space,r_frame_rate',
            '-show_entries', 'format=duration,bit_rate,size',
            '-print_format', 'json',
        ]

        # Add time range parameters if specified
        if start_time is not None and duration is not None:
            base_command.extend([
                '-read_intervals', f'%+{duration}' if start_time == 0 else f'%{start_time}%+{duration}'
            ])
        
        if analyze_keyframes:
            # Add keyframe analysis with optimized parameters
            base_command.extend([
                '-skip_frame', 'nokey',
                '-show_entries', 'frame=best_effort_timestamp_time,pict_type',
                '-select_streams', 'v:0',
                '-count_frames'
            ])
            
        # Add input file with HTTP range optimization for remote files
        if video_path.startswith('http'):
            base_command.extend([
                '-protocol_whitelist', 'file,http,https,tcp,tls',
                '-analyzeduration', '10000000',  # 10 seconds analysis
                '-probesize', '5000000'  # 5MB probe size
            ])
            
        base_command.append(video_path)
        
        try:
            result = subprocess.run(base_command, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"ffprobe failed: {result.stderr}")
                
            data = json.loads(result.stdout)
            
            # Process and merge stream and format data
            video_info = {}
            if 'streams' in data and data['streams']:
                video_info.update(data['streams'][0])
            if 'format' in data:
                video_info.update({
                    'format_duration': data['format'].get('duration'),
                    'bit_rate': data['format'].get('bit_rate'),
                    'size': data['format'].get('size')
                })
                
            return video_info
            
        except Exception as e:
            raise Exception(f"Error running ffprobe: {str(e)}")

    @staticmethod
    def calculate_dimensions(
        original_width: int,
        original_height: int,
        target_width: int,
        target_height: int
    ) -> Tuple[int, int]:
        """Calculate output dimensions maintaining aspect ratio"""
        if target_width == 0 and target_height == 0:
            return original_width, original_height

        if target_width == 0:
            # Calculate width based on height while maintaining aspect ratio
            aspect_ratio = original_width / original_height
            return int(target_height * aspect_ratio), target_height

        if target_height == 0:
            # Calculate height based on width while maintaining aspect ratio
            aspect_ratio = original_height / original_width
            return target_width, int(target_width * aspect_ratio)

        return target_width, target_height

    @staticmethod
    def get_video_info(video_path: str, analyze_keyframes: bool = True, target_time: float = None) -> Dict:
        """
        Get video metadata using ffprobe efficiently with smart keyframe analysis
        
        Args:
            video_path: Path or URL to the video file
            analyze_keyframes: Whether to analyze keyframe positions
            target_time: Optional target time for frame extraction (in seconds)
            
        Returns:
            Dict containing video metadata including:
            - Basic stream info (codec, dimensions, etc.)
            - Frame information (keyframe positions) if analyze_keyframes is True
            - Format information (duration, bitrate)
        """
        try:
            # First get basic metadata quickly
            video_info = VideoSnapshots.run_ffprobe(video_path, analyze_keyframes=False)
            
            if not video_info:
                raise Exception("No video stream found")

            # Get frame rate for GOP size estimation
            try:
                fps_str = video_info.get('r_frame_rate', '30/1')
                if '/' in fps_str:
                    num, den = map(int, fps_str.split('/'))
                    fps = num / den
                else:
                    fps = float(fps_str)
            except (ValueError, ZeroDivisionError):
                fps = 30  # Default to 30fps
            
            video_info['fps'] = fps
                
            # If keyframe analysis is requested and we have a valid duration
            if analyze_keyframes and float(video_info.get('duration', 0)) > 0:
                try:
                    # Smart keyframe analysis based on target time
                    if target_time is not None:
                        # Analyze around the target time
                        start_time = max(0, target_time - 5)  # 5 seconds before target
                        keyframe_data = VideoSnapshots.run_ffprobe(
                            video_path,
                            analyze_keyframes=True,
                            start_time=start_time,
                            duration=10  # 10 second window
                        )
                    else:
                        # Analyze first 30 seconds for keyframe pattern
                        keyframe_data = VideoSnapshots.run_ffprobe(
                            video_path,
                            analyze_keyframes=True,
                            start_time=0,
                            duration=30
                        )
                    
                    # Extract keyframe timestamps
                    keyframes = []
                    if 'frames' in keyframe_data:
                        for frame in keyframe_data['frames']:
                            ts = frame.get('best_effort_timestamp_time')
                            if ts and ts != 'N/A':
                                try:
                                    keyframes.append(float(ts))
                                except (ValueError, TypeError):
                                    continue
                    
                    if keyframes:
                        # Calculate average GOP size
                        gop_sizes = [j-i for i, j in zip(keyframes[:-1], keyframes[1:])]
                        avg_gop = sum(gop_sizes) / len(gop_sizes) if gop_sizes else 2.0
                        
                        # Estimate keyframe positions for entire video
                        duration = float(video_info.get('duration', 0))
                        estimated_keyframes = []
                        current_time = 0
                        while current_time < duration:
                            estimated_keyframes.append(current_time)
                            current_time += avg_gop
                        
                        video_info['keyframe_positions'] = estimated_keyframes
                        logger.info(f"Estimated {len(estimated_keyframes)} keyframe positions")
                    else:
                        # Fallback to default interval if no keyframes detected
                        duration = float(video_info.get('duration', 0))
                        video_info['keyframe_positions'] = [i for i in range(0, int(duration), 2)]
                        
                except Exception as e:
                    logger.warning(f"Keyframe analysis failed, using default intervals: {str(e)}")
                    # Set default keyframe intervals
                    duration = float(video_info.get('duration', 0))
                    video_info['keyframe_positions'] = [i for i in range(0, int(duration), 2)]
            
            return video_info
            
        except Exception as e:
            raise Exception(f"Error processing video: {str(e)}")

    @staticmethod
    def extract_frame(
        video_path: str,
        params: Dict,
        video_info: Dict,
        use_segments: bool = True
    ) -> bytes:
        """
        Extract frame from video at specified time
        
        Args:
            video_path: Path or URL to the video file
            params: Frame extraction parameters
            video_info: Video metadata from ffprobe
            use_segments: Whether to use segment-based extraction (default: True)
        """
        try:
            # Calculate output dimensions
            original_width = int(video_info['width'])
            original_height = int(video_info['height'])
            output_width, output_height = VideoSnapshots.calculate_dimensions(
                original_width,
                original_height,
                params['w'],
                params['h']
            )

            # Create temporary file for output
            with tempfile.NamedTemporaryFile(suffix=f".{params['f']}", delete=False) as temp_file:
                output_path = temp_file.name

            # Get video duration
            duration = float(video_info.get('duration', 0)) or float(video_info.get('format_duration', 0))
            if duration <= 0:
                logger.warning("Could not determine video duration")
                duration = 300  # Default to 5 minutes
            
            # Convert milliseconds to seconds and validate seek time
            seek_time = params['t']/1000  # Convert to seconds
            logger.info(f"Converting seek time from {params['t']}ms to {seek_time}s")
            
            if seek_time > duration:
                logger.info(f"Requested seek time {seek_time}s exceeds video duration {duration}s, adjusting to duration")
                seek_time = duration
            
            # Ensure seek time is not negative
            seek_time = max(0, seek_time)
            logger.info(f"Final seek time: {seek_time}s")
            
            # Calculate how close we are to the end of the video
            time_to_end = duration - seek_time
            logger.info(f"Time remaining to end of video: {time_to_end}s")
            
            # Use direct extraction if:
            # 1. Segments are disabled
            # 2. Not an HTTP URL
            # 3. Too close to the end of video (less than 10% of duration or 5 seconds)
            min_remaining = min(duration * 0.1, 5)  # 10% of duration or 5 seconds, whichever is smaller
            if not use_segments or not video_path.startswith('http') or time_to_end < min_remaining:
                logger.info("Using direct frame extraction")
                try:
                    # Try keyframe-based segmentation first
                    segments = VideoSnapshots.calculate_segments(video_info, [seek_time])
                except Exception as e:
                    logger.warning(f"Keyframe-based segmentation failed: {str(e)}")
                    segments = []
                
                if not segments:
                    # Fallback to simple segmentation
                    # Calculate segment window with minimum duration
                    remaining_duration = duration - seek_time
                    min_segment_duration = 5  # Minimum 5 seconds segment
                    
                    if remaining_duration < min_segment_duration:
                        # For timestamps very close to the end, start segment earlier
                        segment_start = max(0, duration - min_segment_duration)
                        segment_end = duration
                    else:
                        # Normal segmentation with minimum duration
                        segment_duration = max(min_segment_duration, min(30, remaining_duration, duration/10))
                        segment_start = max(0, seek_time - (segment_duration/2))
                        segment_end = min(duration, segment_start + segment_duration)
                    
                    segments = [(segment_start, segment_end)]
                    logger.info(f"Using simple segmentation strategy: start={segment_start}s, end={segment_end}s, duration={segment_end-segment_start}s")
                
                segment_start, segment_end = segments[0]
                segment_duration = segment_end - segment_start
                
                # Try to get cached segment
                cache_key = VideoSnapshots.get_segment_cache_key(video_path, segment_start, segment_end)
                segment_path = VideoSnapshots.get_cached_segment(cache_key)
                
                if not segment_path:
                    # Download segment if not cached
                    # Calculate exact duration to avoid any rounding issues
                    exact_duration = segment_end - segment_start
                    logger.info(f"Downloading segment with exact duration: {exact_duration}s")
                    segment_path = VideoSnapshots.download_segment(
                        video_path,
                        segment_start,
                        exact_duration
                    )
                    # Cache the segment
                    VideoSnapshots.cache_segment(cache_key, segment_path)
                
                # Adjust seek time for segment
                adjusted_seek = seek_time - segment_start
                
                # Build FFmpeg command for segment
                command = [
                    'ffmpeg',
                    '-y',
                    '-ss', str(adjusted_seek),
                    '-i', segment_path,
                    '-vf'
                ]
                
            else:
                # Build FFmpeg command for full video
                command = [
                    'ffmpeg',
                    '-y',
                    '-ss', str(seek_time),
                    '-i', video_path,
                    '-vf'
                ]

            # Build filter string
            filters = [f'scale={output_width}:{output_height}']

            # Add rotation filter if needed
            rotation = params['ar']
            if rotation == 'h' and output_width > output_height:
                filters.append('transpose=1')  # 90 degrees clockwise
            elif rotation == 'w' and output_width < output_height:
                filters.append('transpose=2')  # 90 degrees counterclockwise

            # Add mode-specific parameters
            if params['m'] == 'fast':
                filters.append('select=eq(pict_type\,I)')  # Select only keyframes

            # Add filter string to command
            command.extend([','.join(filters)])

            # Add output format specific parameters
            if params['f'] == 'jpg':
                command.extend(['-qscale:v', '2'])  # High quality JPEG
            elif params['f'] == 'png':
                command.extend(['-compression_level', '3'])  # Balanced compression

            # Add frame limit
            command.extend(['-vframes', '1'])

            # Add output file
            command.append(output_path)

            # Run FFmpeg
            VideoSnapshots._run_ffmpeg_command(command, "Failed to extract frame")

            # Verify output file exists and has content
            if not os.path.exists(output_path):
                logger.error("Output file was not created")
                raise Exception("Output file was not created")
                
            file_size = os.path.getsize(output_path)
            if file_size == 0:
                logger.error("Output file is empty")
                raise Exception("Output file is empty")
                
            logger.info(f"Successfully created output file of size {file_size} bytes")

            # Read the output file
            with open(output_path, 'rb') as f:
                frame_data = f.read()

            if len(frame_data) == 0:
                raise Exception("No frame data was extracted")

            # Log success
            logger.info(f"Successfully extracted frame of size {len(frame_data)} bytes")

            # Clean up temporary files
            os.unlink(output_path)
            if use_segments and 'segment_path' in locals():
                os.unlink(segment_path)

            return frame_data

        except Exception as e:
            if hasattr(e, 'stderr') and e.stderr:
                stderr = e.stderr.decode()
            else:
                stderr = str(e)
            raise Exception(f"Error processing frame: {stderr}")
