# Image Processor API

This Lambda function provides comprehensive image processing capabilities through API Gateway.

## API Endpoint

```
GET /image/{key}
```

## Parameters

- `key`: The object key (path) of the image in S3 bucket
- `operations`: Query parameter specifying the image operations to perform. Multiple operations can be chained using '/'

## Supported Operations

### 1. Resize (`resize`)
Resizes the image using various methods.

Parameters:
- `w_<width>`: Target width in pixels
- `h_<height>`: Target height in pixels
- `p_<percentage>`: Scale by percentage (1-100)
- `m_<mode>`: Resize mode
- `l_<pixels>`: Resize longest side to specified pixels
- `s_<pixels>`: Resize shortest side to specified pixels
- `limit_<0/1>`: Whether to limit enlargement
- `color_<hex>`: Background color for padding (6-digit hex without #)

Examples:
```
# Resize to width 800px (maintaining aspect ratio)
resize,w_800

# Resize to 50% of original size
resize,p_50

# Resize to 800x600 with white background
resize,w_800,h_600,color_FFFFFF

# Resize longest side to 1000px
resize,l_1000
```

### 2. Crop (`crop`)
Crops the image to specified dimensions.

Parameters:
- `w_<width>`: Crop width
- `h_<height>`: Crop height
- `x_<pixels>`: X offset (default: 0)
- `y_<pixels>`: Y offset (default: 0)
- `g_<gravity>`: Crop gravity (nw, n, ne, w, c, e, sw, s, se) (default: nw)
- `p_<percentage>`: Scale percentage before crop (default: 100)

Examples:
```
# Crop 200x200 from center
crop,w_200,h_200,g_c

# Crop 300x200 from top-right corner
crop,w_300,h_200,g_ne

# Crop 400x300 with 50px offset from left
crop,w_400,h_300,x_50
```

### 3. Watermark (`watermark`)
Adds text or image watermark.

Parameters:
- `text_<text>`: Watermark text (URL-encoded)
- `image_<key>`: Image key for image watermark
- `color_<hex>`: Text color (6-digit hex without #, default: 000000)
- `t_<transparency>`: Transparency level 1-100 (default: 100)
- `g_<gravity>`: Position (nw, n, ne, w, c, e, sw, s, se) (default: se)
- `x_<pixels>`: X offset (default: 10)
- `y_<pixels>`: Y offset (default: 10)
- `size_<pixels>`: Font size for text (default: 40)
- `rotate_<degrees>`: Rotation angle (default: 0)
- `shadow_<0/1>`: Enable text shadow (default: 0)
- `padx_<pixels>`: Horizontal padding (default: 0)
- `pady_<pixels>`: Vertical padding (default: 0)

Examples:
```
# Add text watermark
watermark,text_Copyright%202024,color_FF0000,size_30,g_se

# Add semi-transparent text watermark at center
watermark,text_Confidential,t_50,g_c,size_60

# Add rotated watermark with shadow
watermark,text_Draft,rotate_45,shadow_1,color_666666
```

### 4. Format Conversion (`format`)
Converts image to different format.

Parameters:
- `f_<format>`: Target format (jpg, png, webp, etc.)
- `q_<quality>`: JPEG/WebP quality 1-100 (default: 85)

Examples:
```
# Convert to PNG
format,png

# Convert to JPEG with 90% quality
format,f_jpg,q_90

# Convert to WebP with 80% quality
format,f_webp,q_80
```

### 5. Auto Orient (`auto-orient`)
Automatically orients image based on EXIF data.

Parameters:
- `<0/1>`: Enable/disable auto orientation

Example:
```
auto-orient,1
```

### 6. Quality Transformation (`quality`)
Adjusts image quality.

Parameters:
- `q_<quality>`: JPEG quality 1-100
- `Q_<quality>`: WebP quality 1-100

Example:
```
quality,q_85
```

### 7. Blind Watermark (`blindwatermark`)
Adds invisible watermark for copyright protection.

Parameters:
- `context_<base64>`: Base64 encoded watermark text
- `block_<size>`: Block size (4, 8, 16, or 32)
- `password_wm_<number>`: Watermark password (default: 1234)
- `password_img_<number>`: Image password (default: 1234)
- `d1_<number>`: Watermark strength (default: 100)
- `d2_<number>`: Image preservation (default: 60)

Example:
```
blindwatermark,context_Q29weXJpZ2h0,block_8
```

## Complex Examples

1. Resize and Add Watermark
```
GET /image/example.jpg?operations=resize,w_1000/watermark,text_Copyright%202024,color_FF0000,g_se
```

2. Crop, Add Watermark, and Convert Format
```
GET /image/photo.png?operations=crop,w_800,h_600,g_c/watermark,text_Confidential,t_50/format,f_jpg,q_90
```

3. Auto Orient, Resize, and Add Multiple Watermarks
```
GET /image/photo.jpg?operations=auto-orient,1/resize,w_1200/watermark,text_Draft,g_nw/watermark,text_Confidential,g_se
```

4. Process Image with Blind Watermark
```
GET /image/document.jpg?operations=resize,w_2000/blindwatermark,context_Q29weXJpZ2h0IDIwMjQ,block_8/format,f_jpg,q_95
```

## Response

### Success Response
- Status Code: 200
- Body: Processed image binary
- Headers:
  ```
  Content-Type: image/[format]
  Cache-Control: public, max-age=3600
  ETag: [md5-hash]
  X-Amz-Meta-Watermarked-Key: [key] (for blind watermark)
  ```

### Error Response
- Status Code: 400/500
- Body:
  ```json
  {
    "error": "Error message"
  }
  ```

## Notes

- The function has a timeout of 60 seconds
- Maximum memory allocation is 1024MB
- Requires S3 bucket access for reading source images and writing processed results
- Uses DynamoDB table for blind watermark operations
- Supports image formats: JPEG, PNG, WebP, BMP, GIF, TIFF
- All operations are processed in the order specified in the operations parameter
- Images are cached for 1 hour (Cache-Control: public, max-age=3600)
