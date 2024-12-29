from PIL import Image
import io
import logging
from fastapi import HTTPException
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ResizeMode(str, Enum):
    LFIT = "lfit"
    MFIT = "mfit"
    FILL = "fill"
    PAD = "pad"
    FIXED = "fixed"

def hex_to_rgb(hex_color: str) -> tuple:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4)) + (255,)

def validate_size_param(value: int, param_name: str) -> int:
    """Validate size parameters (w, h, l, s)."""
    if not 1 <= value <= 16384:
        raise ValueError(f"{param_name} must be between 1 and 16384")
    return value

def resize_image(image_data: bytes, resize_params: dict) -> bytes:
    try:
        img = Image.open(io.BytesIO(image_data))
        original_width, original_height = img.size
        limit = resize_params.get('limit', '1') == '1'
        
        logger.info(f"Starting image resize operation:")
        logger.info(f"Original dimensions: {original_width}x{original_height}")
        logger.info(f"Input parameters: {resize_params}")

        if 'p' in resize_params:
            # Percentage resize
            p = int(resize_params['p'])
            if not 1 <= p <= 1000:
                logger.error(f"Invalid percentage value: {p}")
                raise ValueError("p must be between 1 and 1000")
            
            new_width = int(original_width * p / 100)
            new_height = int(original_height * p / 100)
            
            logger.info(f"Percentage resize: {p}%")
            logger.info(f"Target dimensions: {new_width}x{new_height}")
            
            if limit and (new_width > original_width or new_height > original_height):
                logger.info("Skipping resize: target size exceeds original with limit=1")
                return image_data
                
            img = img.resize((new_width, new_height), Image.LANCZOS)
            logger.info("Percentage resize completed successfully")
            
        elif 'l' in resize_params or 's' in resize_params:
            # Longest/shortest side resize
            l_param = resize_params.get('l')
            s_param = resize_params.get('s')
            
            logger.info("Starting longest/shortest side resize")
            
            if l_param:
                l_param = validate_size_param(int(l_param), 'l')
                ratio = l_param / max(original_width, original_height)
                logger.info(f"Using longest side parameter: {l_param}")
            elif s_param:
                s_param = validate_size_param(int(s_param), 's')
                ratio = s_param / min(original_width, original_height)
                logger.info(f"Using shortest side parameter: {s_param}")
            
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            
            logger.info(f"Target dimensions: {new_width}x{new_height}")
            
            if limit and (new_width > original_width or new_height > original_height):
                logger.info("Skipping resize: target size exceeds original with limit=1")
                return image_data
                
            img = img.resize((new_width, new_height), Image.LANCZOS)
            logger.info("Side-based resize completed successfully")
            
        elif 'w' in resize_params or 'h' in resize_params:
            # Width/height based resize
            w = resize_params.get('w')
            h = resize_params.get('h')
            mode = resize_params.get('m', ResizeMode.LFIT)
            color = resize_params.get('color', 'FFFFFF')

            logger.info(f"Starting width/height resize with mode: {mode}")
            logger.info(f"Parameters - Width: {w}, Height: {h}, Color: {color}")

            if w:
                w = validate_size_param(int(w), 'w')
            if h:
                h = validate_size_param(int(h), 'h')

            # Calculate target dimensions based on mode
            if mode == ResizeMode.LFIT:
                # Scale down to fit within the specified dimensions
                if w and h:
                    ratio = min(w/original_width, h/original_height)
                elif w:
                    ratio = w/original_width
                else:
                    ratio = h/original_height
                
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                
                logger.info(f"LFIT mode - Target dimensions: {new_width}x{new_height}")
                
                if limit and (new_width > original_width or new_height > original_height):
                    logger.info("Skipping resize: target size exceeds original with limit=1")
                    return image_data
                    
                img = img.resize((new_width, new_height), Image.LANCZOS)
                logger.info("LFIT resize completed successfully")
                
            elif mode == ResizeMode.MFIT:
                # Scale up/down to cover the specified dimensions
                if w and h:
                    ratio = max(w/original_width, h/original_height)
                elif w:
                    ratio = w/original_width
                else:
                    ratio = h/original_height
                
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                
                logger.info(f"MFIT mode - Target dimensions: {new_width}x{new_height}")
                
                if limit and (new_width > original_width or new_height > original_height):
                    logger.info("Skipping resize: target size exceeds original with limit=1")
                    return image_data
                    
                img = img.resize((new_width, new_height), Image.LANCZOS)
                logger.info("MFIT resize completed successfully")
                
            elif mode == ResizeMode.FILL:
                # Scale to cover and crop to exact dimensions
                if not (w and h):
                    logger.error("Missing required dimensions for FILL mode")
                    raise ValueError("Both width and height are required for fill mode")
                    
                ratio = max(w/original_width, h/original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                
                logger.info(f"FILL mode - Intermediate dimensions: {new_width}x{new_height}")
                
                if limit and (new_width > original_width or new_height > original_height):
                    logger.info("Skipping resize: target size exceeds original with limit=1")
                    return image_data
                    
                img = img.resize((new_width, new_height), Image.LANCZOS)
                left = (img.width - w) // 2
                top = (img.height - h) // 2
                img = img.crop((left, top, left + w, top + h))
                logger.info(f"FILL mode - Final dimensions after crop: {w}x{h}")
                logger.info("FILL resize completed successfully")
                
            elif mode == ResizeMode.PAD:
                # Scale to fit and pad
                if not (w and h):
                    logger.error("Missing required dimensions for PAD mode")
                    raise ValueError("Both width and height are required for pad mode")
                    
                ratio = min(w/original_width, h/original_height)
                new_width = int(original_width * ratio)
                new_height = int(original_height * ratio)
                
                logger.info(f"PAD mode - Image dimensions before padding: {new_width}x{new_height}")
                logger.info(f"PAD mode - Using color: #{color}")
                
                if limit and (new_width > original_width or new_height > original_height):
                    logger.info("Skipping resize: target size exceeds original with limit=1")
                    return image_data
                
                img = img.resize((new_width, new_height), Image.LANCZOS)
                new_img = Image.new('RGBA', (w, h), hex_to_rgb(color))
                paste_x = (w - new_width) // 2
                paste_y = (h - new_height) // 2
                new_img.paste(img, (paste_x, paste_y))
                img = new_img
                logger.info(f"PAD mode - Final dimensions with padding: {w}x{h}")
                logger.info("PAD resize completed successfully")
                
            elif mode == ResizeMode.FIXED:
                # Force resize to exact dimensions
                if not (w and h):
                    logger.error("Missing required dimensions for FIXED mode")
                    raise ValueError("Both width and height are required for fixed mode")
                    
                if limit and (w > original_width or h > original_height):
                    logger.info("Skipping resize: target size exceeds original with limit=1")
                    return image_data
                    
                img = img.resize((w, h), Image.LANCZOS)
                logger.info(f"FIXED mode - Final dimensions: {w}x{h}")
                logger.info("FIXED resize completed successfully")
        else:
            raise ValueError("Invalid resize parameters")

        buffer = io.BytesIO()
        img.save(buffer, format=img.format or 'PNG')
        final_size = len(buffer.getvalue())
        logger.info(f"Image processing completed. Final size: {final_size} bytes")
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"Image processing failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to resize image: {e}")

# Additional image processing functions can be added here in the future
