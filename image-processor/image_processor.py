import os
import hashlib
import logging

from image_resizer import resize_image, ResizeMode
from image_cropper import crop_image
from s3_operations import S3Config, get_s3_client, download_object_from_s3
from image_watermark import add_watermark
from image_format_converter import convert_format
from image_auto_orient import auto_orient_image
from image_quality import transform_quality
from image_blindwatermark import add_blind_watermark
from image_deblindwatermark import extract_blind_watermark
import json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProcessingError(Exception):
    """Custom exception for image processing errors"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class ImageResponse:
    """Response class for processed images"""
    def __init__(self, body, headers=None):
        self.body = body
        self.headers = headers or {}

def parse_operation(operation_str: str) -> tuple[str, dict]:
    """Parse operation string like 'resize,p_50' or 'format,png' into (operation, params)"""
    parts = operation_str.split(',')
    operation = parts[0]
    params = {}
    
    for param in parts[1:]:
        if operation == 'auto-orient':
            # Special handling for auto-orient parameter
            try:
                params['auto'] = int(param)
            except ValueError:
                raise ValueError("auto-orient parameter must be 0 or 1")
        elif '_' in param:
            key, value = param.split('_')
            # Keep color and text as strings, try to convert others to int
            if key not in {'color', 'text'}:
                try:
                    value = int(value)
                except ValueError:
                    pass
            params[key] = value
        else:
            # Handle direct format specification (e.g., 'format,png' instead of 'format,f_png')
            if operation == 'format':
                params['f'] = param
    
    return operation, params

def get_content_type(format_str: str) -> str:
    """Get the correct content type for a given format"""
    format_map = {
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'png': 'image/png',
        'webp': 'image/webp',
        'bmp': 'image/bmp',
        'gif': 'image/gif',
        'tiff': 'image/tiff'
    }
    return format_map.get(format_str.lower(), 'image/jpeg')

def process_image(image_key: str, operations: str = None):
    """
    Process an image with chained operations.
    
    Args:
        image_key: S3 object key of the source image
        operations: Operation string (e.g., 'resize,p_50/crop,w_200,h_200')
        
    Returns:
        ImageResponse object with processed image and headers
        
    Raises:
        ProcessingError: If operation fails
    """
    try:
        s3_config = S3Config()
        s3_client = get_s3_client()

        # Download image from S3
        logger.info(f"Downloading image from S3: {image_key}")
        image_data = download_object_from_s3(s3_client, s3_config.bucket_name, image_key)
        current_image_data = image_data
        content_type = None

        # Process operations if provided
        if operations:
            # Split and process operations
            operation_chain = [op for op in operations.split('/') if op]
            
            for operation_str in operation_chain:
                operation, params = parse_operation(operation_str)
                logger.info(f"Processing operation: {operation} with params: {params}")
                
                if operation == 'auto-orient':
                    orient_params = {
                        'auto': params.get('auto', 0)
                    }
                    current_image_data = auto_orient_image(current_image_data, orient_params)
                
                elif operation == 'resize':
                    resize_params = {}
                    # Percentage resize
                    if 'p' in params:
                        resize_params['p'] = params['p']
                    
                    # Width/height resize
                    if 'w' in params:
                        resize_params['w'] = params['w']
                    if 'h' in params:
                        resize_params['h'] = params['h']
                    if 'm' in params:
                        resize_params['m'] = ResizeMode(params['m'])
                    
                    # Longest/shortest side resize
                    if 'l' in params:
                        resize_params['l'] = params['l']
                    if 's' in params:
                        resize_params['s'] = params['s']
                    
                    # Additional parameters
                    if 'limit' in params:
                        resize_params['limit'] = params['limit']
                    if 'color' in params:
                        # Ensure color is properly formatted
                        color = params['color']
                        if color and len(color) < 6:
                            color = color.zfill(6)  # Pad with leading zeros
                        resize_params['color'] = color
                    
                    logger.info(f"Resize parameters: {resize_params}")
                    current_image_data = resize_image(current_image_data, resize_params)    
                elif operation == 'crop':
                    crop_params = {
                        'w': params.get('w'),
                        'h': params.get('h'),
                        'x': params.get('x', 0),
                        'y': params.get('y', 0),
                        'g': params.get('g', 'nw'),
                        'p': params.get('p', 100)
                    }
                    current_image_data = crop_image(current_image_data, crop_params)
                    
                elif operation == 'watermark':
                    # Ensure color is properly formatted
                    color = params.get('color', '000000')
                    if color and len(color) < 6:
                        color = color.zfill(6)  # Pad with leading zeros if needed
                        
                    watermark_params = {
                        'color': color,
                        't': params.get('t', 100),
                        'g': params.get('g', 'se'),
                        'x': params.get('x', 10),
                        'y': params.get('y', 10),
                        'voffset': params.get('voffset', 0),
                        'fill': params.get('fill', 0),
                        'padx': params.get('padx', 0),
                        'pady': params.get('pady', 0),
                        'size': params.get('size', 40),
                        'shadow': params.get('shadow', 0),
                        'rotate': params.get('rotate', 0)
                    }
                    
                    # Handle either text or image watermark
                    if 'text' in params:
                        watermark_params['text'] = params['text']
                    elif 'image' in params:
                        watermark_params['image'] = params['image']
                        if 'P' in params:
                            watermark_params['P'] = params['P']
                    else:
                        watermark_params['text'] = 'Watermark'  # Default text if neither specified
                        
                    current_image_data = add_watermark(current_image_data, **watermark_params)
                    
                elif operation == 'format':
                    format_params = {
                        'f': params.get('f', 'jpg'),
                        'q': params.get('q', 85)
                    }
                    current_image_data = convert_format(current_image_data, format_params)
                    content_type = get_content_type(format_params['f'])
                
                elif operation == 'quality':
                    quality_params = {}
                    if 'q' in params:
                        quality_params['q'] = params['q']
                    if 'Q' in params:
                        quality_params['Q'] = params['Q']
                    current_image_data = transform_quality(current_image_data, quality_params)
                
                elif operation == 'blindwatermark':
                    # Decode base64-encoded watermark text
                    encoded_text = params.get('context', 'UHJvdGVjdGVk')  # Default to base64('Protected')
                    try:
                        import base64
                        watermark_text = base64.b64decode(encoded_text).decode('utf-8')
                    except Exception as e:
                        raise ProcessingError(
                            status_code=400,
                            detail=f"Invalid base64-encoded watermark text: {str(e)}"
                        )
                    
                    # Validate block size
                    block_size = params.get('block', 4)
                    if block_size not in {4, 8, 16, 32}:
                        raise ProcessingError(
                            status_code=400,
                            detail=f"Invalid block size: {block_size}. Must be one of: 4, 8, 16, 32"
                        )
                    
                    watermark_params = {
                        'text': watermark_text,
                        'original_object_key': image_key,
                        'password_wm': params.get('password_wm', 1234),
                        'password_img': params.get('password_img', 1234),
                        # block_shape must be one of: 4, 8, 16, 32
                        'block_shape': (params.get('block', 4), params.get('block', 4)),
                        'd1': params.get('d1', 100),
                        'd2': params.get('d2', 60)
                    }
                    current_image_data, new_key = add_blind_watermark(current_image_data, **watermark_params)
                    # Add the new S3 key to response headers
                    headers = {
                        "X-Amz-Meta-Watermarked-Key": new_key
                    }
                
                elif operation == 'deblindwatermark':
                    result = extract_blind_watermark(current_image_data)
                    current_image_data = json.dumps(result).encode('utf-8')
                    content_type = 'application/json'
                
                else:
                    raise ProcessingError(
                        status_code=400,
                        detail=f"Unknown operation: {operation}"
                    )

        # If no format operation was specified, determine content type from file extension
        if content_type is None:
            _, file_extension = os.path.splitext(image_key)
            content_type = get_content_type(file_extension[1:] if file_extension else 'jpeg')

        # Generate ETag
        etag = hashlib.md5(current_image_data).hexdigest()

        # Set cache control (1 hour)
        cache_control = "public, max-age=3600"

        logger.info(f"Completed processing image: {image_key}")
        # Return the processed image with caching headers and any operation-specific headers
        response_headers = {
            "Content-Type": content_type,
            "Cache-Control": cache_control,
            "ETag": etag
        }
        # Add operation-specific headers if they exist
        if 'headers' in locals():
            response_headers.update(headers)
            
        return ImageResponse(
            body=current_image_data,
            headers=response_headers
        )

    except Exception as e:
        logger.error(f"Error processing image {image_key}: {str(e)}")
        raise ProcessingError(status_code=500, detail=str(e))
