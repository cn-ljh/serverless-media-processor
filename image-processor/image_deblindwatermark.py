import os
import logging
from blind_watermark import WaterMark
from typing import Optional, Tuple
from PIL import Image
import numpy as np
from ddb_operations import scan_watermark_records

logger = logging.getLogger(__name__)

FIXED_WIDTH = 600  # Must match the width used in watermarking

def extract_blind_watermark(image_data: bytes) -> dict:
    """
    Extract blind watermark from image.
    
    Args:
        image_data: Input image as bytes
    
    Returns:
        Dictionary containing extracted watermark information
    """
    try:
        # Set up file paths
        input_path = f"/tmp/input_image_extract.jpg"
        normalized_path = f"/tmp/normalized_{os.path.basename(input_path)}"

        # Save input bytes to file
        with open(input_path, 'wb') as f:
            f.write(image_data)

        # Resize image to match watermarking dimensions
        with Image.open(input_path) as img:
            # Calculate height to maintain aspect ratio
            # aspect_ratio = 1 #img.height / img.width
            # FIXED_HEIGHT = int(FIXED_WIDTH * aspect_ratio)
            
            # # Resize image
            # resized_img = img.resize((FIXED_WIDTH, FIXED_HEIGHT), Image.Resampling.LANCZOS)
            # resized_img.save(normalized_path, quality=100)
            img.save(normalized_path, quality=100)

        # Get all watermark records from DynamoDB
        watermark_records = scan_watermark_records()
        
        # Iterate through all watermark records
        for record in watermark_records:
            try:
                # Get original watermark text and parameters
                original_text = record['text']
                params = {
                    'password_wm': record['password_wm'],
                    'password_img': record['password_img'],
                    'block_shape': tuple(record['block_shape']),
                    'wm_length': record['wm_length']
                }

                # Initialize watermark extractor with these parameters
                bwm = WaterMark(
                    password_wm=params['password_wm'], 
                    password_img=params['password_img'], 
                    block_shape=params['block_shape']
                )
                
                # Extract watermark using the normalized image
                wm_extract = bwm.extract(normalized_path, wm_shape=params['wm_length'], mode='bit')
        
                # Find the end marker (1111 0000)
                end_marker = np.array([1, 1, 1, 1, 0, 0, 0, 0])
                
                # Convert wm_extract to numpy array if it isn't already
                wm_extract = np.array(wm_extract)
                
                # Find the end marker in the extracted bits
                for i in range(len(wm_extract) - 7):
                    if np.array_equal(wm_extract[i:i+8], end_marker):
                        wm_extract = wm_extract[:i]
                        break
                
                # Convert bits to bytes
                bytes_data = bytearray()
                for i in range(0, len(wm_extract), 8):
                    byte = 0
                    for bit_idx in range(8):
                        if i + bit_idx < len(wm_extract):
                            byte = (byte << 1) | wm_extract[i + bit_idx]
                    bytes_data.append(byte)

                # Decode bytes to text and compare with original
                try:
                    extracted_text = bytes_data.decode('utf-8')
                    if extracted_text == original_text:
                        # Found exact match - clean up and return result
                        os.remove(input_path)
                        os.remove(normalized_path)
                        return {
                            'status': 'success',
                            'blindwatermark': {
                                'text': extracted_text
                            }
                        }
                except UnicodeDecodeError:
                    # Skip if the extracted bits don't form valid UTF-8 text
                    continue

            except Exception as e:
                logger.warning(f"Failed to extract with parameters {params}: {str(e)}")
                continue

        # Clean up
        os.remove(input_path)
        if os.path.exists(normalized_path):
            os.remove(normalized_path)
        
        # If we get here, we tried all items without finding a match
        raise Exception("Could not find matching watermark in any known configurations")
        
    except Exception as e:
        # Clean up temporary files in case of error
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(normalized_path):
            os.remove(normalized_path)
        raise Exception(f"Error extracting blind watermark: {str(e)}")
