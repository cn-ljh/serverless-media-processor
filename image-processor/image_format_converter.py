from PIL import Image
import io
from enum import Enum
from fastapi import HTTPException

class ImageFormat(str, Enum):
    """Enum for supported image formats"""
    JPG = "jpg"
    JPEG = "jpeg"
    PNG = "png"
    WEBP = "webp"
    BMP = "bmp"
    GIF = "gif"
    TIFF = "tiff"

def convert_format(image_data: bytes, format_params: dict) -> bytes:
    """
    Convert image to specified format
    
    Args:
        image_data: Original image bytes
        format_params: Dictionary containing:
            - f: Target format (required)
            - q: Quality for lossy formats (default: 85)
            
        Note: format can be specified either as a direct value or with f_ prefix
        Examples:
            - {'f': 'png'} or {'png': True}
            - {'q': 85} for quality
    
    Returns:
        Converted image bytes
    """
    try:
        # Extract parameters, handling both direct format value and f_ prefix cases
        target_format = None
        if 'f' in format_params:
            target_format = format_params['f'].lower()
        else:
            # Check if format is specified directly (e.g., 'png' instead of 'f_png')
            for fmt in ImageFormat:
                if fmt.value in format_params:
                    target_format = fmt.value
                    break
        
        if not target_format:
            target_format = 'jpg'  # default format
            
        quality = format_params.get('q', 85)

        # Validate parameters
        if target_format not in [f.value for f in ImageFormat]:
            raise ValueError(f"Unsupported format: {target_format}")
        if not 1 <= quality <= 100:
            raise ValueError("Quality must be between 1 and 100")

        # Open image
        img = Image.open(io.BytesIO(image_data))

        # Handle format-specific conversions
        if target_format in ['jpg', 'jpeg']:
            # Convert to RGB if necessary (remove alpha channel)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[3])
                img = background
            save_format = 'JPEG'
            save_kwargs = {'quality': quality, 'optimize': True}
        
        elif target_format == 'png':
            save_format = 'PNG'
            save_kwargs = {'optimize': True}
        
        elif target_format == 'webp':
            save_format = 'WEBP'
            save_kwargs = {'quality': quality, 'method': 6}
        
        elif target_format == 'bmp':
            save_format = 'BMP'
            save_kwargs = {}
        
        elif target_format == 'gif':
            save_format = 'GIF'
            save_kwargs = {'optimize': True}
        
        elif target_format == 'tiff':
            save_format = 'TIFF'
            save_kwargs = {'quality': quality}

        # Save in new format
        buffer = io.BytesIO()
        img.save(buffer, format=save_format, **save_kwargs)
        return buffer.getvalue()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to convert image format: {str(e)}")
