from PIL import Image, ImageDraw, ImageFont, ImageChops
from io import BytesIO
import os
import re
from b64encoder_decoder import custom_b64encode, custom_b64decode
from typing import List, Optional, Tuple, Union

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
    def __init__(self, text: str, type: str = "华文楷体", color: str = "000000",
                 size: int = 40, shadow: int = 0, rotate: int = 0, **kwargs):
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

        # Save to bytes
        output_bytes = BytesIO()
        output.save(output_bytes, format=image.format or 'JPEG')
        return output_bytes.getvalue()

    def _apply_text_watermark(self, watermark: Image.Image, params: TextWatermarkParams) -> Image.Image:
        """Apply text watermark"""
        draw = ImageDraw.Draw(watermark)
        
        try:
            font = ImageFont.truetype(self.font_path, params.size)
        except Exception:
            raise WatermarkError(f"Failed to load font: {params.type}")

        text = params.text
        if len(text) > 64:
            raise WatermarkError("Text exceeds 64 characters")

        # Get text size
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Calculate position
        pos = self._calculate_position(watermark.size, (text_width, text_height), params)

        # Parse color
        try:
            r = int(params.color[0:2], 16)
            g = int(params.color[2:4], 16)
            b = int(params.color[4:6], 16)
        except ValueError:
            raise WatermarkError(f"Invalid color format: {params.color}")

        # Create a temporary image for the text
        txt = Image.new('RGBA', (text_width + 20, text_height + 20), (0,0,0,0))
        d = ImageDraw.Draw(txt)

        # Draw shadow if enabled
        if params.shadow > 0:
            shadow_color = (0, 0, 0, int(255 * params.shadow / 100))
            d.text((12, 12), text, font=font, fill=shadow_color)

        # Draw text with full color
        d.text((10, 10), text, font=font, fill=(r, g, b, 255))

        # Apply rotation if needed
        if params.rotate != 0:
            txt = txt.rotate(params.rotate, expand=True)

        # Apply transparency to the entire text layer
        if params.t != 100:
            alpha = Image.new('L', txt.size, int(255 * params.t / 100))
            txt.putalpha(ImageChops.multiply(txt.getchannel('A'), alpha))

        # Paste the text onto the watermark
        watermark.paste(txt, (int(pos[0]-10), int(pos[1]-10)), txt)

        return watermark

    def _apply_image_watermark(self, watermark: Image.Image, params: ImageWatermarkParams) -> Image.Image:
        """Apply image watermark"""
        try:
            # Decode image name and load watermark image
            image_name = custom_b64decode(params.image)
            wm_path = os.path.join(os.path.dirname(__file__), 'watermarks', image_name)
            wm_image = Image.open(wm_path).convert('RGBA')
        except Exception as e:
            raise WatermarkError(f"Failed to load watermark image: {str(e)}")

        # Scale watermark if needed
        if params.P is not None:
            original_size = wm_image.size
            new_size = tuple(int(dim * params.P / 100) for dim in original_size)
            wm_image = wm_image.resize(new_size, Image.Resampling.LANCZOS)

        # Calculate position
        pos = self._calculate_position(watermark.size, wm_image.size, params)

        # Apply transparency
        if params.t != 100:
            wm_image.putalpha(ImageChops.multiply(
                wm_image.getchannel('A'),
                Image.new('L', wm_image.size, int(255 * params.t / 100))
            ))

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
        if combined_params.align == 0:  # Top
            text_params.y = image_params.y + combined_params.interval
        elif combined_params.align == 1:  # Middle
            text_params.voffset = combined_params.interval // 2
        else:  # Bottom
            text_params.y = image_params.y - combined_params.interval

        # Apply second watermark
        watermark = self._apply_text_watermark(watermark, text_params)

        return watermark

    def _calculate_position(self, canvas_size: Tuple[int, int], 
                          element_size: Tuple[int, int], 
                          params: BaseWatermarkParams) -> Tuple[int, int]:
        """Calculate position for watermark element"""
        width, height = canvas_size
        elem_width, elem_height = element_size
        
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

        return (x, y)

def add_watermark(image_data: bytes, text: str = None, image: str = None, color: str = "000000", **kwargs) -> bytes:
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
        try:
            decoded_text = custom_b64decode(str(text))
        except Exception:
            raise WatermarkError("Invalid text encoding")
            
        text_params = {
            'text': decoded_text,
            'color': str(color),
            **kwargs
        }
        watermarks.append(TextWatermarkParams(**text_params))
    if image is not None:
        # Ensure image is a string before encoding
        image_str = str(image)
        watermarks.append(ImageWatermarkParams(image=custom_b64encode(image_str), **kwargs))
        
    return processor.process_image(image_data, watermarks)
