import base64

def custom_b64decode(encoded: str) -> str:
    """
    Decode custom base64 string:
    - Replace - with +
    - Replace _ with /
    - Add padding =
    """
    encoded = encoded.replace('-', '+').replace('_', '/')
    padding = 4 - (len(encoded) % 4)
    if padding != 4:
        encoded += '=' * padding
    return base64.b64decode(encoded).decode('utf-8')

def custom_b64encode(decoded: str) -> str:
    """
    Encode string to custom base64:
    - Replace + with -
    - Replace / with _
    - Remove padding =
    """
    encoded = base64.b64encode(decoded.encode('utf-8')).decode('utf-8')
    return encoded.replace('+', '-').replace('/', '_').rstrip('=')
