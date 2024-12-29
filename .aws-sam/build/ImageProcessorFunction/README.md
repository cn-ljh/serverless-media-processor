# Image Processor

The Image Processor is a serverless component that provides real-time image processing capabilities through AWS Lambda.

## Features

- **Real-time Processing**: Synchronous image processing through API Gateway
- **Multiple Operations**: Supports various image manipulation operations:
  - Image resizing
  - Format conversion
  - Quality adjustment
  - Watermarking
  - Auto-orientation
  - Cropping
- **S3 Integration**: Works with images stored in S3 buckets

## Components

- `handler.py`: Main Lambda handler for processing image requests
- `image_processor.py`: Core image processing logic
- `image_resizer.py`: Image resizing operations
- `image_format_converter.py`: Image format conversion
- `image_quality.py`: Image quality adjustment
- `image_watermark.py`: Watermark application
- `image_auto_orient.py`: Image orientation correction
- `image_cropper.py`: Image cropping operations
- `s3_operations.py`: S3 operations for file handling

## Usage

The processor accepts requests with the following parameters:
- `object_key`: The S3 key of the image to process
- `operations`: Comma-separated list of operations to perform

Example operations:
```
resize,w_100,h_100
convert,format_png
quality,q_80
watermark,text_example,position_center
crop,w_200,h_200,x_0,y_0
```

## Response

The processor returns:
- Base64 encoded processed image
- Content-Type header indicating the image format
- Error details if processing fails
