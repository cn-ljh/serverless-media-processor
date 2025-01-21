from PIL import Image, ImageDraw, ImageFont, ImageChops
from io import BytesIO
import os
import re
from b64encoder_decoder import custom_b64encode, custom_b64decode
from typing import List, Optional, Tuple, Union
from s3_operations import S3Config, get_s3_client, download_object_from_s3

class WatermarkError(Exception):
    """Custom exception for watermark processing errors"""
    pass

class BaseWatermarkParams:
    """Base watermark parameters"""
    def __init__(self, t: int = 100, g: str = 'se', x: int = 10, y: int = 10,
                 voffset: int = 0, fill: int = 0, padx: int = 0, pady: int = 0):
        self.t = t
        self.g = g
        self.x = x
        self.y = y
        self.voffset = voffset
        self.fill = fill
        self.padx = padx
        self.pady = pady
        self.validate()

    def validate(self):
        """Validate base parameters"""
        if not 0 <= self.t <= 100:
            raise WatermarkError("Transparency must be between 0 and 100")
        
        valid_positions = {'nw', 'north', 'ne', 'west', 'center', 'east', 'sw', 'south', 'se'}
        if self.g not in valid_positions:
            raise WatermarkError(f"Invalid position: {self.g}")
            
        if not 0 <= self.x <= 4096:
            raise WatermarkError("Horizontal margin must be between 0 and 4096")
            
        if not 0 <= self.y <= 4096:
            raise WatermarkError("Vertical margin must be between 0 and 4096")
            
        if not -1000 <= self.voffset <= 1000:
            raise WatermarkError("Vertical offset must be between -1000 and 1000")
            
        if self.fill not in {0, 1}:
            raise WatermarkError("Fill must be 0 or 1")
            
        if not 0 <= self.padx <= 4096:
            raise WatermarkError("Horizontal padding must be between 0 and 4096")
            
        if not 0 <= self.pady <= 4096:
            raise WatermarkError("Vertical padding must be between 0 and 4096")

class ImageWatermarkParams(BaseWatermarkParams):
    """Image watermark specific parameters"""
    def __init__(self, image: str, P: Optional[int] = None, **kwargs):
        self.image = image
        self.P = P
        super().__init__(**kwargs)

    def validate(self):
        """Validate image watermark parameters"""
        super().validate()
        if not self.image:
            raise WatermarkError("Image parameter is required")
        if self.P is not None and not 1 <= self.P <= 100:
            raise WatermarkError("Proportional scaling must be between 1 and 100")

class TextWatermarkParams(BaseWatermarkParams):
    """Text watermark specific parameters"""
    def __init__(self, text: str, type: str = "华文楷体", color: str = "FFFFFF",
                 size: int = 40, shadow: int = 40, rotate: int = 0, **kwargs):
        self.text = text
        self.type = type
        self.color = color
        self.size = size
        self.shadow = shadow
        self.rotate = rotate
        super().__init__(**kwargs)

    def validate(self):
        """Validate text watermark parameters"""
        super().validate()
        if not self.text:
            raise WatermarkError("Text parameter is required")
        if not 0 < self.size <= 1000:
            raise WatermarkError("Font size must be between 1 and 1000")
        if not 0 <= self.shadow <= 100:
            raise WatermarkError("Shadow transparency must be between 0 and 100")
        if not 0 <= self.rotate <= 360:
            raise WatermarkError("Rotation angle must be between 0 and 360")
        if not re.match(r'^[0-9A-Fa-f]{6}$', self.color):
            raise WatermarkError("Invalid color format")

class CombinedWatermarkParams:
    """Parameters for combined image and text watermarks"""
    def __init__(self, order: int = 0, align: int = 2, interval: int = 0):
        self.order = order
        self.align = align
        self.interval = interval
        self.validate()

    def validate(self):
        """Validate combined watermark parameters"""
        if self.order not in {0, 1}:
            raise WatermarkError("Order must be 0 or 1")
        if self.align not in {0, 1, 2}:
            raise WatermarkError("Align must be 0, 1, or 2")
        if not 0 <= self.interval <= 1000:
            raise WatermarkError("Interval must be between 0 and 1000")

class WatermarkProcessor:
    """Main watermark processing class"""
    
    SUPPORTED_FORMATS = {'JPEG', 'PNG', 'BMP', 'WEBP', 'TIFF'}
    MAX_WATERMARKS = 3
    
    def __init__(self):
        self.font_path = os.path.join(os.path.dirname(__file__), 'font', '华文楷体.ttf')

    def process_image(self, image_data: bytes, watermarks: List[Union[ImageWatermarkParams, TextWatermarkParams]], 
                     combined_params: Optional[CombinedWatermarkParams] = None) -> bytes:
        """Process image with watermarks"""
        if len(watermarks) > self.MAX_WATERMARKS:
            raise WatermarkError(f"Maximum {self.MAX_WATERMARKS} watermarks allowed")

        # Open and validate image
        try:
            image = Image.open(BytesIO(image_data))
            if image.format not in self.SUPPORTED_FORMATS:
                raise WatermarkError(f"Unsupported image format: {image.format}")
            image = image.convert('RGBA')
        except Exception as e:
            raise WatermarkError(f"Failed to open image: {str(e)}")

        # Create watermark layer
        watermark = Image.new('RGBA', image.size, (0,0,0,0))
        
        # Process watermarks
        if len(watermarks) == 2 and combined_params:
            # Handle combined watermarks
            if not (isinstance(watermarks[0], ImageWatermarkParams) and 
                   isinstance(watermarks[1], TextWatermarkParams)):
                raise WatermarkError("Combined watermarks must be one image and one text")
            watermark = self._apply_combined_watermarks(watermark, watermarks[0], watermarks[1], combined_params)
        else:
            # Apply individual watermarks
            for wm in watermarks:
                if isinstance(wm, ImageWatermarkParams):
                    watermark = self._apply_image_watermark(watermark, wm)
                elif isinstance(wm, TextWatermarkParams):
                    watermark = self._apply_text_watermark(watermark, wm)

        # Composite final image
        output = Image.alpha_composite(image, watermark)
        output = output.convert('RGB')

        # Save to bytes with high quality
        output_bytes = BytesIO()
        save_params = {'format': image.format or 'JPEG'}
        if save_params['format'] == 'JPEG':
            save_params['quality'] = 95
            save_params['optimize'] = True
        elif save_params['format'] == 'PNG':
            save_params['optimize'] = True
        output.save(output_bytes, **save_params)
        return output_bytes.getvalue()

    def _apply_text_watermark(self, watermark: Image.Image, params: TextWatermarkParams) -> Image.Image:
        """Apply text watermark"""
        draw = ImageDraw.Draw(watermark)
        
        try:
            font = ImageFont.truetype(self.font_path, params.size)
        except Exception:
            raise WatermarkError(f"Failed to load font: {params.type}")

        text = params.text
        padding = 10  # Further reduced padding
        
        # Calculate maximum available space
        max_width = watermark.size[0] - 2 * params.x - padding * 2
        max_height = watermark.size[1] - 2 * params.y - padding * 2
        
        # Function to wrap text and calculate size
        def get_wrapped_text_size(text, font, max_width):
            lines = []
            words = text.split()
            current_line = []
            
            for word in words:
                current_line.append(word)
                line = ' '.join(current_line)
                bbox = draw.textbbox((0, 0), line, font=font)
                if bbox[2] - bbox[0] > max_width and len(current_line) > 1:
                    current_line.pop()
                    lines.append(' '.join(current_line))
                    current_line = [word]
            
            if current_line:
                lines.append(' '.join(current_line))
            
            return lines
        
        # Initial text wrapping and size calculation
        lines = get_wrapped_text_size(text, font, max_width)
        line_spacing = int(params.size * 0.2)  # 20% of font size for line spacing
        
        # Calculate total text height with line spacing
        total_height = (len(lines) * (params.size + line_spacing)) - line_spacing + padding * 2
        max_line_width = max(draw.textbbox((0, 0), line, font=font)[2] for line in lines)
        total_width = max_line_width + padding * 2
        
        # Reduce font size if needed while maintaining readability
        while (total_height > max_height or total_width > max_width) and params.size > 12:
            params.size = int(params.size * 0.9)  # Reduce by 10%
            font = ImageFont.truetype(self.font_path, params.size)
            lines = get_wrapped_text_size(text, font, max_width)
            line_spacing = int(params.size * 0.2)  # Keep consistent with initial spacing
            total_height = (len(lines) * (params.size + line_spacing)) - line_spacing + padding * 2
            max_line_width = max(draw.textbbox((0, 0), line, font=font)[2] for line in lines)
            total_width = max_line_width + padding * 2

        # Create a temporary image for the text with semi-transparent gray background
        txt = Image.new('RGBA', (total_width, total_height), (128, 128, 128, 180))  # Semi-transparent gray background
        d = ImageDraw.Draw(txt)
        
        # Calculate centered text position within the temporary image
        text_x = padding
        text_y = padding  # Start from top padding since we're drawing multiple lines

        # Use white color for text
        r, g, b = 255, 255, 255  # White color for better visibility on gray background
        
        # Draw text with shadow and color
        y_offset = text_y
        for line in lines:
            # Draw shadow first (if enabled)
            if params.shadow > 0:
                shadow_opacity = min(255, int(255 * params.shadow / 40))  # Further increased opacity
                shadow_color = (0, 0, 0, shadow_opacity)
                for dx, dy in [(4, 4), (4, 3), (3, 4), (3, 3)]:  # Thicker shadow
                    d.text((text_x + dx, y_offset + dy), line, font=font, fill=shadow_color)

            # Draw outline for better visibility
            outline_positions = [
                (-1, -1), (0, -1), (1, -1),
                (-1, 0),           (1, 0),
                (-1, 1),  (0, 1),  (1, 1)
            ]
            for dx, dy in outline_positions:
                for i in range(2):  # Draw outline twice for thickness
                    d.text((text_x + dx, y_offset + dy), line, font=font, fill=(0, 0, 0, 255))
            
            # Draw main text with specified color
            d.text((text_x, y_offset), line, font=font, fill=(r, g, b, 255))
            y_offset += params.size + line_spacing

        # Apply rotation if needed
        if params.rotate != 0:
            txt = txt.rotate(params.rotate, expand=True)

        # Apply transparency to the entire text layer
        if params.t != 100:
            alpha = Image.new('L', txt.size, int(255 * params.t / 100))
            txt.putalpha(ImageChops.multiply(txt.getchannel('A'), alpha))

        # Calculate position based on watermark position parameter
        width, height = watermark.size
        if params.g in {'nw', 'north', 'ne'}:  # Top positions
            y = params.y
        elif params.g in {'west', 'center', 'east'}:  # Middle positions
            y = (height - total_height) // 2 + params.voffset
        else:  # Bottom positions
            y = height - total_height - params.y

        if params.g in {'nw', 'west', 'sw'}:  # Left positions
            x = params.x
        elif params.g in {'north', 'center', 'south'}:  # Center positions
            x = (width - total_width) // 2
        else:  # Right positions
            x = width - total_width - params.x

        # Ensure position stays within image boundaries
        x = max(0, min(x, width - total_width))
        y = max(0, min(y, height - total_height))

        # Paste the text onto the watermark
        watermark.paste(txt, (x, y), txt)

        return watermark

    def _apply_image_watermark(self, watermark: Image.Image, params: ImageWatermarkParams) -> Image.Image:
        """Apply image watermark"""
        try:
            # Get watermark image from S3
            print(f"INFO: params.imgae: {params.image}")
            image_key = custom_b64decode(params.image)
            print(f"INFO: image key: {image_key}")
            s3_config = S3Config()
            s3_client = get_s3_client()
            wm_data = download_object_from_s3(s3_client, s3_config.bucket_name, image_key)
            wm_image = Image.open(BytesIO(wm_data)).convert('RGBA')
        except Exception as e:
            raise WatermarkError(f"Failed to load watermark image: {str(e)}")

        # Scale watermark if needed using high-quality resampling
        if params.P is not None:
            original_size = wm_image.size
            new_size = tuple(int(dim * params.P / 100) for dim in original_size)
            wm_image = wm_image.resize(new_size, Image.Resampling.LANCZOS)

        # Calculate position
        pos = self._calculate_position(watermark.size, wm_image.size, params)

        # Apply transparency
        if params.t != 100:
            alpha = Image.new('L', wm_image.size, int(255 * params.t / 100))
            wm_image.putalpha(ImageChops.multiply(wm_image.getchannel('A'), alpha))

        # Paste watermark
        watermark.paste(wm_image, pos, wm_image)

        return watermark

    def _apply_combined_watermarks(self, watermark: Image.Image, 
                                 image_params: ImageWatermarkParams,
                                 text_params: TextWatermarkParams,
                                 combined_params: CombinedWatermarkParams) -> Image.Image:
        """Apply combined image and text watermarks"""
        if combined_params.order == 1:
            image_params, text_params = text_params, image_params

        # Apply first watermark
        watermark = self._apply_image_watermark(watermark, image_params)
        
        # Adjust position for second watermark based on alignment
        original_y = text_params.y  # Store original y value
        
        if combined_params.align == 0:  # Top
            text_params.y = image_params.y + combined_params.interval
        elif combined_params.align == 1:  # Middle
            text_params.voffset = combined_params.interval // 2
        else:  # Bottom
            text_params.y = image_params.y + combined_params.interval

        # Apply second watermark
        watermark = self._apply_text_watermark(watermark, text_params)
        
        # Restore original y value
        text_params.y = original_y
        
        return watermark
    
    def _calculate_position(self, canvas_size: Tuple[int, int], 
                          element_size: Tuple[int, int], 
                          params: BaseWatermarkParams) -> Tuple[int, int]:
        """Calculate position for watermark element"""
        width, height = canvas_size
        elem_width, elem_height = element_size
        
        # Calculate base positions
        positions = {
            'nw': (params.x, params.y),
            'north': ((width - elem_width) // 2, params.y),
            'ne': (width - elem_width - params.x, params.y),
            'west': (params.x, (height - elem_height) // 2),
            'center': ((width - elem_width) // 2, (height - elem_height) // 2),
            'east': (width - elem_width - params.x, (height - elem_height) // 2),
            'sw': (params.x, height - elem_height - params.y),
            'south': ((width - elem_width) // 2, height - elem_height - params.y),
            'se': (width - elem_width - params.x, height - elem_height - params.y)
        }

        x, y = positions.get(params.g, positions['se'])
        
        if params.g in {'west', 'center', 'east'}:
            y += params.voffset

        # Ensure position stays within image boundaries with padding
        margin = 5  # Reduced safety margin
        y = max(margin, min(y, height - elem_height - margin))
        x = max(margin, min(x, width - elem_width - margin))

        return (x, y)

def add_watermark(image_data: bytes, text: str = None, image: str = None, color: str = "FFFFFF", **kwargs) -> bytes:
    """
    Legacy interface for backward compatibility
    
    Args:
        image_data: Original image bytes
        text: Text to use as watermark (base64 encoded)
        image: Image filename to use as watermark
        color: Hex color code for text watermark (e.g., "FF0000" for red)
        **kwargs: Additional parameters for watermark
    """
    processor = WatermarkProcessor()
    watermarks = []
    
    if text is not None:
        # Decode the base64 encoded text
        # try:
        #     decoded_text = custom_b64decode(str(text))
        # except Exception:
        #     raise WatermarkError("Invalid text encoding")
            
        text_params = {
            'text': text,
            'color': str(color),
            **kwargs
        }
        watermarks.append(TextWatermarkParams(**text_params))
    if image is not None:
        # Ensure image is a string before encoding
        image_str = str(image)
        # Filter out text-specific parameters
        image_params = {k: v for k, v in kwargs.items() 
                       if k in {'t', 'g', 'x', 'y', 'voffset', 'fill', 'padx', 'pady', 'P'}}
        watermarks.append(ImageWatermarkParams(image=image_str, **image_params))
        
    return processor.process_image(image_data, watermarks)
