from PIL import Image
import io

def grayscale_image(image_data: bytes) -> bytes:
    """
    Convert an image to grayscale.
    
    Args:
        image_data: Input image as bytes
    
    Returns:
        Processed grayscale image as bytes
    """
    # Open the image
    image = Image.open(io.BytesIO(image_data))
    
    # Convert to grayscale
    grayscale = image.convert('L')
    
    # Save to bytes
    output = io.BytesIO()
    grayscale.save(output, format=image.format or 'JPEG')
    return output.getvalue()
