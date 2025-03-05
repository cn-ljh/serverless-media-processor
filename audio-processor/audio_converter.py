import os
import subprocess
import logging
from typing import Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ConversionError(Exception):
    """Custom exception for audio conversion errors"""
    pass

def validate_params(params: dict) -> None:
    """
    Validate audio conversion parameters.
    
    Args:
        params: Dictionary of parameters to validate
        
    Raises:
        ConversionError: If parameters are invalid
    """
    # Validate required format
    if 'f' not in params:
        raise ConversionError("Output format (f) is required")
    
    format = params['f'].lower()
    if format not in {'mp3', 'm4a', 'flac', 'oga', 'ac3', 'opus', 'amr'}:
        raise ConversionError(f"Unsupported format: {format}")
    
    # Validate sample rate
    if 'ar' in params:
        ar = params['ar']
        valid_rates = {8000, 11025, 12000, 16000, 22050, 24000, 32000, 44100, 48000, 64000, 88200, 96000}
        if ar not in valid_rates:
            raise ConversionError(f"Invalid sample rate: {ar}")
        
        # Format-specific sample rate validation
        if format == 'mp3' and ar > 48000:
            raise ConversionError("MP3 only supports sample rates up to 48kHz")
        elif format == 'opus' and ar not in {8000, 12000, 16000, 24000, 48000}:
            raise ConversionError("Opus only supports 8kHz, 12kHz, 16kHz, 24kHz, and 48kHz")
        elif format == 'ac3' and ar not in {32000, 44100, 48000}:
            raise ConversionError("AC3 only supports 32kHz, 44.1kHz, and 48kHz")
        elif format == 'amr' and ar != 8000:
            raise ConversionError("AMR-NB only supports 8kHz sample rate")
    
    # Validate channels
    if 'ac' in params:
        ac = params['ac']
        if not 1 <= ac <= 8:
            raise ConversionError(f"Invalid channel count: {ac}")
        
        # Format-specific channel validation
        if format == 'mp3' and ac > 2:
            raise ConversionError("MP3 only supports mono and stereo")
        elif format == 'ac3' and ac > 6:
            raise ConversionError("AC3 supports up to 6 channels (5.1)")
        elif format == 'amr' and ac != 1:
            raise ConversionError("AMR only supports mono")
    
    # Validate quality and bitrate (mutually exclusive)
    if 'aq' in params and 'ab' in params:
        raise ConversionError("Cannot specify both quality (aq) and bitrate (ab)")
    
    if 'aq' in params:
        aq = params['aq']
        if not 0 <= aq <= 100:
            raise ConversionError(f"Invalid quality value: {aq}")
    
    if 'ab' in params:
        ab = params['ab']
        if not 1000 <= ab <= 10000000:
            raise ConversionError(f"Invalid bitrate: {ab}")
    
    # Validate bitrate option
    if 'abopt' in params and params['abopt'] not in {'0', '1', '2'}:
        raise ConversionError(f"Invalid bitrate option: {params['abopt']}")
    
    # Validate sample depth for FLAC
    if format == 'flac' and 'adepth' in params:
        adepth = params['adepth']
        if adepth not in {16, 24}:
            raise ConversionError(f"Invalid sample depth for FLAC: {adepth}")

def convert_audio(audio_data: bytes, params: dict) -> bytes:
    """
    Convert audio data using ffmpeg with specified parameters.
    
    Args:
        audio_data: Input audio data as bytes
        params: Dictionary containing conversion parameters:
            - ss (int, optional): Start time in milliseconds
            - t (int, optional): Duration in milliseconds
            - f (str, required): Output format (mp3, m4a, flac, oga, ac3, opus, amr)
            - ar (int, optional): Sample rate in Hz
            - ac (int, optional): Number of audio channels
            - aq (int, optional): Audio quality (0-100)
            - ab (int, optional): Audio bitrate in bps
            - abopt (str, optional): Bitrate option (0, 1, 2)
            - adepth (int, optional): Sample depth (16 or 24, only for flac)
        
    Returns:
        Converted audio data as bytes
        
    Raises:
        ConversionError: If conversion fails
    """
    try:
        # Validate parameters
        validate_params(params)
        
        # Create temporary files
        temp_input = '/tmp/input.wav'
        temp_output = f'/tmp/output.{params["f"]}'
        
        # Write input data to temporary file
        with open(temp_input, 'wb') as f:
            f.write(audio_data)
        
        # Build ffmpeg command
        cmd = ['ffmpeg', '-i', temp_input]
        
        # Add start time if specified
        if 'ss' in params:
            cmd.extend(['-ss', str(int(params['ss']) / 1000)])  # Convert ms to seconds
        
        # Add duration if specified
        if 't' in params:
            cmd.extend(['-t', str(int(params['t']) / 1000)])  # Convert ms to seconds
        
        # Add sample rate
        # For AMR format, force 8000Hz if not specified or if specified rate is not 8000Hz
        if params['f'] == 'amr':
            cmd.extend(['-ar', '8000'])
        elif 'ar' in params:
            cmd.extend(['-ar', str(params['ar'])])
        
        # Add channels if specified
        if 'ac' in params:
            cmd.extend(['-ac', str(params['ac'])])
        
        # Add quality or bitrate
        if 'aq' in params:
            if params['f'] == 'mp3':
                cmd.extend(['-q:a', str(int(params['aq'] * 9 / 100))])  # Convert 0-100 to MP3's 0-9 scale
            else:
                cmd.extend(['-q:a', str(params['aq'])])
        elif 'ab' in params:
            cmd.extend(['-b:a', str(params['ab'])])
        
        # Add sample depth for FLAC
        if params['f'] == 'flac' and 'adepth' in params:
            cmd.extend(['-sample_fmt', f's{params["adepth"]}'])
        
        # Add output format and file
        # For M4A (AAC), we need to use MP4 format with AAC codec
        if params['f'] == 'm4a':
            cmd.extend(['-f', 'mp4', '-c:a', 'aac'])
        else:
            cmd.extend(['-f', params['f']])
        cmd.append(temp_output)
        
        # Run ffmpeg
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            raise ConversionError(f"FFmpeg conversion failed: {stderr.decode()}")
        
        # Read converted data
        with open(temp_output, 'rb') as f:
            converted_data = f.read()
            
        # Cleanup temporary files
        os.remove(temp_input)
        os.remove(temp_output)
        
        return converted_data
        
    except Exception as e:
        logger.error(f"Error converting audio: {str(e)}")
        raise ConversionError(f"Audio conversion failed: {str(e)}")

def get_audio_format(file_name: str) -> str:
    """
    Get audio format from file name.
    
    Args:
        file_name: Name of the audio file
        
    Returns:
        Audio format as string (e.g., 'wav', 'mp3')
    """
    _, ext = os.path.splitext(file_name)
    return ext[1:].lower() if ext else ''

def get_content_type(format_str: str) -> str:
    """
    Get the correct content type for a given audio format.
    
    Args:
        format_str: Audio format string (e.g., 'wav', 'mp3')
        
    Returns:
        Content type string
    """
    format_map = {
        'wav': 'audio/wav',
        'mp3': 'audio/mpeg',
        'ogg': 'audio/ogg',
        'aac': 'audio/aac',
        'm4a': 'audio/mp4',
        'flac': 'audio/flac',
        'opus': 'audio/opus',
        'ac3': 'audio/ac3',
        'amr': 'audio/amr'
    }
    return format_map.get(format_str.lower(), 'application/octet-stream')
