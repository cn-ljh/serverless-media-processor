from PIL import Image
import io
from enum import Enum
from fastapi import HTTPException
from typing import Tuple

class CropGravity(str, Enum):
    """Enum for crop gravity points"""
    NW = "nw"      # Left top
    NORTH = "north"  # Center top
    NE = "ne"      # Right top
    WEST = "west"   # Left center
    CENTER = "center" # Center
    EAST = "east"   # Right center
    SW = "sw"      # Left bottom
    SOUTH = "south"  # Center bottom
    SE = "se"      # Right bottom
    FACE = "face"   # Face detection (requires IMM)
    AUTO = "auto"   # Auto detection (requires IMM)

def calculate_crop_coordinates(
    img_width: int,
    img_height: int,
    crop_width: int,
    crop_height: int,
    x: int = 0,
    y: int = 0,
    gravity: str = "nw"
) -> Tuple[int, int, int, int]:
    """Calculate crop coordinates based on gravity and offset"""
    
    # Ensure crop dimensions don't exceed image dimensions
    crop_width = min(crop_width, img_width)
    crop_height = min(crop_height, img_height)
    
    # Calculate base coordinates according to gravity
    if gravity in [CropGravity.NW, CropGravity.WEST, CropGravity.SW]:
        base_x = 0
    elif gravity in [CropGravity.NORTH, CropGravity.CENTER, CropGravity.SOUTH]:
        base_x = (img_width - crop_width) // 2
    else:  # NE, EAST, SE
        base_x = img_width - crop_width

    if gravity in [CropGravity.NW, CropGravity.NORTH, CropGravity.NE]:
        base_y = 0
    elif gravity in [CropGravity.WEST, CropGravity.CENTER, CropGravity.EAST]:
        base_y = (img_height - crop_height) // 2
    else:  # SW, SOUTH, SE
        base_y = img_height - crop_height

    # Apply offset
    x1 = max(0, min(base_x + x, img_width - crop_width))
    y1 = max(0, min(base_y + y, img_height - crop_height))
    x2 = x1 + crop_width
    y2 = y1 + crop_height

    return (x1, y1, x2, y2)

def crop_image(image_data: bytes, crop_params: dict, quality: int = 95) -> bytes:
    """
    Crop image with specified parameters
    
    Args:
        image_data: Original image bytes
        crop_params: Dictionary containing:
            - w: Crop width (optional)
            - h: Crop height (optional)
            - x: X-axis offset (default: 0)
            - y: Y-axis offset (default: 0)
            - g: Gravity point (default: "nw")
            - p: Scale percentage (default: 100)
    
    Returns:
        Cropped image bytes
    """
    try:
        img = Image.open(io.BytesIO(image_data))
        original_width, original_height = img.size

        # Extract parameters
        x = crop_params.get('x', 0)
        y = crop_params.get('y', 0)
        gravity = crop_params.get('g', 'nw')
        scale = crop_params.get('p', 100)
        crop_width = crop_params.get('w', original_width)
        crop_height = crop_params.get('h', original_height)

        # Validate parameters
        if crop_width <= 0 or crop_height <= 0:
            raise ValueError("Crop dimensions must be positive")
        if x < 0 or y < 0:
            raise ValueError("Offset coordinates must be non-negative")
        if gravity not in [g.value for g in CropGravity]:
            raise ValueError(f"Invalid gravity parameter: {gravity}")
        if gravity in ['face', 'auto']:
            raise ValueError("Face and auto detection require IMM integration")
        if not 1 <= scale <= 200:
            raise ValueError("Scale parameter must be between 1 and 200")

        # Calculate crop coordinates
        crop_box = calculate_crop_coordinates(
            original_width, original_height,
            crop_width, crop_height,
            x, y, gravity
        )

        # Perform cropping
        img = img.crop(crop_box)

        # Apply scaling if needed
        if scale != 100:
            new_width = int(img.width * scale / 100)
            new_height = int(img.height * scale / 100)
            img = img.resize((new_width, new_height), Image.LANCZOS)

        # Save the result
        buffer = io.BytesIO()
        save_format = img.format or 'JPEG'
        if save_format.upper() == 'JPEG':
            img.save(buffer, format=save_format, quality=quality, subsampling=0)
        else:
            img.save(buffer, format=save_format)
        return buffer.getvalue()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process image: {str(e)}")
