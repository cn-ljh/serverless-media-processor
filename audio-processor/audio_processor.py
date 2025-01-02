import os
import hashlib
import logging
from typing import Optional, Dict, Any

from audio_converter import convert_audio, get_audio_format, get_content_type, ConversionError
from s3_operations import S3Config, get_s3_client, download_object_from_s3

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProcessingError(Exception):
    """Custom exception for audio processing errors"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class AudioResponse:
    """Response class for processed audio"""
    def __init__(self, body: bytes, headers: Optional[Dict[str, str]] = None):
        self.body = body
        self.headers = headers or {}

def parse_operation(operation_str: str) -> tuple[str, dict]:
    """
    Parse operation string into operation name and parameters.
    
    Args:
        operation_str: Operation string (e.g., 'convert,ss_10000,t_60000,f_aac,ab_96000')
        
    Returns:
        Tuple of (operation_name, parameters_dict)
    """
    parts = operation_str.split(',')
    operation = parts[0]
    params = {}
    
    for param in parts[1:]:
        if '_' in param:
            key, value = param.split('_')
            # Convert numeric parameters to appropriate type
            if key in {'ss', 't', 'ar', 'ac', 'aq', 'ab', 'adepth'}:
                try:
                    params[key] = int(value)
                except ValueError:
                    raise ProcessingError(400, f"Invalid numeric value for parameter {key}: {value}")
            else:
                params[key] = value
    
    # Validate required format parameter for convert operation
    if operation == 'convert' and 'f' not in params:
        raise ProcessingError(400, "Output format (f) is required for convert operation")
    
    return operation, params

def process_audio(audio_key: str, operations: Optional[str] = None) -> AudioResponse:
    """
    Process audio with specified operations.
    
    Args:
        audio_key: S3 object key of the source audio
        operations: Operation string (e.g., 'convert,ss_10000,t_60000,f_aac,ab_96000')
        
    Returns:
        AudioResponse object with processed audio and headers
    """
    try:
        s3_config = S3Config()
        s3_client = get_s3_client()

        # Download audio from S3
        logger.info(f"Downloading audio from S3: {audio_key}")
        audio_data = download_object_from_s3(s3_client, s3_config.bucket_name, audio_key)
        current_audio_data = audio_data

        # Get input format
        input_format = get_audio_format(audio_key)
        if input_format.lower() != 'wav':
            raise ProcessingError(400, f"Unsupported input format: {input_format}. Only WAV format is supported.")

        # Process operations if provided
        output_format = 'wav'  # Default format if no conversion
        if operations:
            operation_chain = [op for op in operations.split('/') if op]
            
            for operation_str in operation_chain:
                operation, params = parse_operation(operation_str)
                logger.info(f"Processing operation: {operation} with params: {params}")
                
                if operation == 'convert':
                    # Convert audio with specified parameters
                    current_audio_data = convert_audio(current_audio_data, params)
                    output_format = params['f']
                else:
                    raise ProcessingError(400, f"Unknown operation: {operation}")

        # Generate ETag
        etag = hashlib.md5(current_audio_data).hexdigest()

        # Set content type and cache control
        content_type = get_content_type(output_format)
        cache_control = "public, max-age=3600"

        logger.info(f"Completed processing audio: {audio_key}")
        
        return AudioResponse(
            body=current_audio_data,
            headers={
                "Content-Type": content_type,
                "Cache-Control": cache_control,
                "ETag": etag
            }
        )

    except ConversionError as e:
        logger.error(f"Conversion error for {audio_key}: {str(e)}")
        raise ProcessingError(500, str(e))
    except Exception as e:
        logger.error(f"Error processing audio {audio_key}: {str(e)}")
        raise ProcessingError(500, str(e))
