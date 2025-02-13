from PIL import Image
import io
from fastapi import HTTPException

def auto_orient_image(image_data: bytes, orient_params: dict, quality: int = 95) -> bytes:
    """
    Apply auto-orientation to image based on EXIF data
    
    Args:
        image_data: Original image bytes
        orient_params: Dictionary containing:
            - auto: 0 to keep original orientation, 1 to apply auto-orientation
            
    Returns:
        Processed image bytes
    """
    try:
        # Get auto-orient parameter, default to 0 (keep original)
        auto_orient = orient_params.get('auto', 0)
        
        if not isinstance(auto_orient, int) or auto_orient not in [0, 1]:
            raise ValueError("auto parameter must be 0 or 1")

        # Open image
        img = Image.open(io.BytesIO(image_data))
        
        # If auto-orient is disabled or image has no EXIF, return original
        if auto_orient == 0 or not hasattr(img, '_getexif') or img._getexif() is None:
            buffer = io.BytesIO()
            save_format = img.format or 'JPEG'
            if save_format.upper() == 'JPEG':
                img.save(buffer, format=save_format, quality=quality, subsampling=0)
            else:
                img.save(buffer, format=save_format)
            return buffer.getvalue()

        # EXIF orientation tag
        ORIENTATION_TAG = 274  # 0x0112
        
        # Orientation to degrees mapping
        ORIENTATIONS = {
            1: 0,    # Normal
            2: 0,    # Mirrored horizontal
            3: 180,  # Rotated 180
            4: 180,  # Mirrored vertical
            5: 90,   # Mirrored horizontal & rotated 90 CCW
            6: -90,  # Rotated 90 CCW
            7: -90,  # Mirrored horizontal & rotated 90 CW
            8: 90,   # Rotated 90 CW
        }

        try:
            exif = img._getexif()
            orientation = exif.get(ORIENTATION_TAG, 1)
            
            # Apply rotation
            if orientation in ORIENTATIONS:
                if orientation in [2, 4, 5, 7]:  # Mirrored cases
                    img = img.transpose(Image.FLIP_LEFT_RIGHT)
                if ORIENTATIONS[orientation] != 0:
                    img = img.rotate(ORIENTATIONS[orientation], expand=True)

        except (AttributeError, KeyError, IndexError):
            # If there's any error reading EXIF, return original image
            pass

        # Save processed image
        buffer = io.BytesIO()
        save_format = img.format or 'JPEG'
        if save_format.upper() == 'JPEG':
            img.save(buffer, quality, format=save_format, subsampling=0)
        else:
            img.save(buffer, format=save_format)
        return buffer.getvalue()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to auto-orient image: {str(e)}")
