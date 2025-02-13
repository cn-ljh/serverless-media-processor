import json
import os
import boto3
import datetime
import logging
from blind_watermark import WaterMark
from urllib.parse import unquote_plus
import s3_operations
from ddb_operations import create_watermark_record

logger = logging.getLogger(__name__)

def add_blind_watermark(image_data: bytes, quality: int=95, text: str = 'Protected', 
                       password_wm: int = 1234, password_img: int = 1234, 
                       block_shape: tuple = (4, 4), d1: int = 30, d2: int = 20) -> tuple[bytes, str]:
    """
    Add blind watermark to image.
    
    Args:
        image_data: Input image as bytes
        text: Watermark text
        password_wm: Password for watermark
        password_img: Password for image
        block_shape: Block shape for watermark (width, height)
        d1: Watermark strength parameter
        d2: Watermark robustness parameter
    
    Returns:
        Watermarked image as bytes
    """
    try:
        # Set up file paths
        input_path = f"/tmp/input_image.jpg"
        output_path = f"/tmp/watermarked_image.jpg"
        normalized_path = f"/tmp/normalized_image.jpg"
        
        # Save input bytes to file
        with open(input_path, 'wb') as f:
            f.write(image_data)
        
        # Resize image to fixed size before watermarking
        from PIL import Image
        # FIXED_WIDTH = 600  # Fixed width for watermarking
        
        with Image.open(input_path) as img:
            # Calculate height to maintain aspect ratio
            # aspect_ratio = img.height / img.width
            # FIXED_HEIGHT = int(FIXED_WIDTH * aspect_ratio)
            
            # # Resize image
            # resized_img = img.resize((FIXED_WIDTH, FIXED_HEIGHT), Image.Resampling.LANCZOS)
            # resized_img.save(normalized_path, quality=95)
            img.save(normalized_path, quality=quality)
        
        # Apply watermark with more robust parameters
        bwm = WaterMark(password_wm=password_wm, password_img=password_img, block_shape=block_shape)
        bwm.bwm_core.d1 = d1  # Increased strength
        bwm.bwm_core.d2 = d2  # Increased robustness
        
        # Process normalized image
        bwm.read_img(normalized_path)
        # Convert text to bits and use bit mode for more reliable encoding
        text_bits = []
        for byte in text.encode('utf-8'):
            text_bits.extend([1 if bit == '1' else 0 for bit in format(byte, '08b')])
        # Add error detection bits
        text_bits.extend([1, 1, 1, 1, 0, 0, 0, 0])  # Marker for end of data
        bwm.read_wm(text_bits, mode='bit')
        bwm.embed(output_path)
        
        # Read output file as bytes
        with open(output_path, 'rb') as f:
            output_data = f.read()
        
        # Clean up
        os.remove(input_path)
        os.remove(normalized_path)
        os.remove(output_path)
        
        # Save watermark info to DynamoDB using ddb_operations
        try:
            
            create_watermark_record(
                text=text,
                password_wm=password_wm,
                password_img=password_img,
                block_shape=block_shape,
                d1=d1,
                d2=d2,
                wm_length=len(bwm.wm_bit)
            )
            logger.info(f"Saved watermark info to DynamoDB for image: {input_path}")
        except Exception as e:
            logger.error(f"Failed to save watermark info to DynamoDB: {str(e)}")
            # Continue processing even if DDB save fails
            
        return output_data
        
    except Exception as e:
        # Clean up temporary files in case of error
        for path in [input_path, output_path, normalized_path]:
            if os.path.exists(path):
                os.remove(path)
        raise Exception(f"Error adding blind watermark: {str(e)}")
