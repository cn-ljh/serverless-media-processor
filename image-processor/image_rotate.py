from PIL import Image
import io

def rotate_image(image_data: bytes, params: dict, quality: int=100) -> bytes:
    """
    Rotate an image by specified degrees clockwise.
    
    Args:
        image_data: Image data in bytes
        params: Dictionary containing:
            - degree: Rotation angle in degrees (90, 180, or 270)
    
    Returns:
        Rotated image data in bytes
    """
    # Validate degree parameter
    degree = params.get('degree', 90)
    if degree not in [90, 180, 270]:
        raise ValueError("Rotation degree must be 90, 180, or 270")
    
    # Open image from bytes
    image = Image.open(io.BytesIO(image_data))
    
    # Rotate image (PIL rotates counter-clockwise, so we negate the angle)
    rotated_image = image.rotate(-degree, expand=True)
    
    # Save the rotated image to bytes
    output = io.BytesIO()
    save_format = image.format if image.format else 'JPEG'
    if save_format.upper() == 'JPEG':
        rotated_image.save(output, format=save_format, quality=quality, subsampling=0)
    else:
        rotated_image.save(output, format=save_format)
    
    return output.getvalue()
