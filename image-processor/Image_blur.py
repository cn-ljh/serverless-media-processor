from PIL import Image, ImageFilter
import io

def blur_image(image_data: bytes, params: dict, quality: int = 95) -> bytes:
    """
    Apply Gaussian blur to an image.
    
    Args:
        image_data: Input image as bytes
        params: Dictionary containing:
            - radius: Blur radius (integer)
    
    Returns:
        Processed image as bytes
    """
    # Open the image
    image = Image.open(io.BytesIO(image_data))
    
    # Get blur radius from params, default to 2 if not specified
    radius = params.get('radius', 2)
    
    # Apply Gaussian blur
    blurred_image = image.filter(ImageFilter.GaussianBlur(radius=radius))
    
    # Save to bytes
    output = io.BytesIO()
    save_format = image.format or 'JPEG'
    if save_format.upper() == 'JPEG':
        blurred_image.save(output, format=save_format, quality=quality, subsampling=0)
    else:
        blurred_image.save(output, format=save_format)
    return output.getvalue()
