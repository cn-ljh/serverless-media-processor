from PIL import Image
import io
from fastapi import HTTPException
from enum import Enum

class ResizeMode(str, Enum):
    LFIT = "lfit"
    MFIT = "mfit"
    FILL = "fill"
    PAD = "pad"
    FIXED = "fixed"

def resize_image(image_data: bytes, resize_params: dict) -> bytes:
    try:
        img = Image.open(io.BytesIO(image_data))
        original_width, original_height = img.size

        if 'p' in resize_params:
            p = resize_params['p']
            if 1 <= p <= 1000:
                if p < 100:
                    new_width = int(original_width * p / 100)
                    new_height = int(original_height * p / 100)
                else:
                    new_width = int(original_width * p / 100)
                    new_height = int(original_height * p / 100)
                img = img.resize((new_width, new_height), Image.LANCZOS)
            else:
                raise ValueError("p must be between 1 and 1000")
        elif 'w' in resize_params or 'h' in resize_params:
            w = resize_params.get('w')
            h = resize_params.get('h')
            mode = resize_params.get('m', ResizeMode.LFIT)

            if w:
                w = int(w)
            if h:
                h = int(h)

            if mode == ResizeMode.LFIT:
                img.thumbnail((w or original_width, h or original_height), Image.LANCZOS)
            elif mode == ResizeMode.MFIT:
                img = img.resize((w or original_width, h or original_height), Image.LANCZOS)
            elif mode == ResizeMode.FILL:
                img = img.resize((w or original_width, h or original_height), Image.LANCZOS)
                if w and h:
                    img = img.crop(((img.width - w) // 2, (img.height - h) // 2, (img.width + w) // 2, (img.height + h) // 2))
            elif mode == ResizeMode.PAD:
                img.thumbnail((w or original_width, h or original_height), Image.LANCZOS)
                if w and h:
                    new_img = Image.new('RGBA', (w, h), (255, 255, 255, 0))
                    new_img.paste(img, ((w - img.width) // 2, (h - img.height) // 2))
                    img = new_img
            elif mode == ResizeMode.FIXED:
                img = img.resize((w or original_width, h or original_height), Image.LANCZOS)
        else:
            raise ValueError("Invalid resize parameters")

        buffer = io.BytesIO()
        img.save(buffer, format=img.format or 'PNG')
        return buffer.getvalue()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resize image: {e}")

# Additional image processing functions can be added here in the future
