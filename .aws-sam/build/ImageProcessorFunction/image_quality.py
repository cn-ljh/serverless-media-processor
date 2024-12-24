from PIL import Image
import io
from fastapi import HTTPException

def transform_quality(image_data: bytes, quality_params: dict) -> bytes:
    """
    Transform image quality using relative or absolute quality parameters
    
    Args:
        image_data: Original image bytes
        quality_params: Dictionary containing:
            - q: Relative quality (1-100)
            - Q: Absolute quality (1-100)
            
    Returns:
        Transformed image bytes
    """
    try:
        # Open image
        img = Image.open(io.BytesIO(image_data))
        
        # Check if format is supported
        if img.format not in ['JPEG', 'WEBP']:
            raise ValueError(f"Quality transformation only supports JPEG and WebP formats, got {img.format}")
        
        # Get quality parameter
        relative_quality = quality_params.get('q')
        absolute_quality = quality_params.get('Q')
        
        if relative_quality is not None and absolute_quality is not None:
            raise ValueError("Cannot specify both relative and absolute quality")
        
        if relative_quality is None and absolute_quality is None:
            raise ValueError("Must specify either relative (q) or absolute (Q) quality")
        
        # Validate quality parameter
        quality = relative_quality if relative_quality is not None else absolute_quality
        if not 1 <= quality <= 100:
            raise ValueError("Quality must be between 1 and 100")
        
        # For WebP, both relative and absolute quality have the same effect
        if img.format == 'WEBP':
            save_format = 'WEBP'
            save_kwargs = {'quality': quality, 'method': 6}
        
        # For JPEG, handle relative vs absolute quality
        else:  # JPEG
            save_format = 'JPEG'
            if relative_quality is not None:
                # For relative quality, directly use the parameter
                save_kwargs = {'quality': quality, 'optimize': True}
            else:
                # For absolute quality, only compress if original quality is higher
                try:
                    # Try to estimate original quality
                    original_quality = img.info.get('quality', 100)
                    final_quality = min(original_quality, quality)
                except:
                    # If can't determine original quality, use target quality
                    final_quality = quality
                save_kwargs = {'quality': final_quality, 'optimize': True}
        
        # Save with new quality
        buffer = io.BytesIO()
        img.save(buffer, format=save_format, **save_kwargs)
        return buffer.getvalue()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to transform image quality: {str(e)}")
