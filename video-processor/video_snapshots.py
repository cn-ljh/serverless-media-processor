import json
import subprocess
import shlex
from typing import Dict, Optional, Tuple, BinaryIO
import os
import tempfile
from typing import Dict

class VideoSnapshots:
    @staticmethod
    def run_ffprobe(video_path: str) -> Dict:
        """Run ffprobe command to get video metadata"""
        command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            video_path
        ]
        
        try:
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"ffprobe failed: {result.stderr}")
            return json.loads(result.stdout)
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
    def get_video_info(video_path: str) -> Dict:
        """Get video metadata using ffprobe"""
        try:
            probe_data = VideoSnapshots.run_ffprobe(video_path)
            video_stream = next(
                (stream for stream in probe_data['streams'] if stream['codec_type'] == 'video'),
                None
            )

            if not video_stream:
                raise Exception("No video stream found")

            return video_stream
        except Exception as e:
            raise Exception(f"Error processing video: {str(e)}")

    @staticmethod
    def extract_frame(
        video_path: str,
        params: Dict,
        video_info: Dict
    ) -> bytes:
        """Extract frame from video at specified time"""
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

            # Build FFmpeg command
            command = [
                'ffmpeg',
                '-y',  # Overwrite output file
                '-ss', str(params['t']/1000),  # Seek position in seconds
                '-i', video_path,  # Input file
                '-vf'  # Video filters
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
            result = subprocess.run(command, capture_output=True, text=True)
            if result.returncode != 0:
                raise Exception(f"ffmpeg failed: {result.stderr}")

            # Read the output file
            with open(output_path, 'rb') as f:
                frame_data = f.read()

            # Clean up temporary file
            os.unlink(output_path)

            return frame_data

        except Exception as e:
            if hasattr(e, 'stderr') and e.stderr:
                stderr = e.stderr.decode()
            else:
                stderr = str(e)
            raise Exception(f"Error processing frame: {stderr}")
