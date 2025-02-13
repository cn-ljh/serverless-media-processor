from PIL import Image
import io

def grayscale_image(image_data: bytes, quality:int=100) -> bytes:
    """
    Convert an image to grayscale.
    
    Args:
        image_data: Input image as bytes
        quality: JPEG quality (1-100, default 100)
    
    Returns:
        Processed grayscale image as bytes
    """
    # Validate quality parameter
    quality = max(1, min(95, quality))  # Clamp between 1 and 100
    # Open the image
    image = Image.open(io.BytesIO(image_data))
    
    # Convert to grayscale
    grayscale = image.convert('L')
    
    # Save to bytes
    output = io.BytesIO()
    save_format = image.format or 'JPEG'
    if save_format.upper() == 'JPEG':
        grayscale.save(output, format=save_format, quality=quality, subsampling=0)
    else:
        grayscale.save(output, format=save_format)
    return output.getvalue()
