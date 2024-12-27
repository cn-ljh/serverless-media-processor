# Video Processor

The Video Processor is a serverless component that handles video processing operations through AWS Lambda.

## Features

- **Frame Extraction**: Ability to extract specific frames from videos
- **Video Snapshots**: Generate thumbnail images from video content
- **S3 Integration**: Works with videos stored in S3 buckets
- **Format Support**: Handles common video formats

## Components

- `handler.py`: Main Lambda handler for processing video requests
- `video_processor.py`: Core video processing logic
- `video_snapshots.py`: Video frame extraction and thumbnail generation
- `s3_operations.py`: S3 operations for file handling
- `create_layer.sh`: Script for creating Lambda layers with required dependencies

## Usage

The processor accepts requests with the following parameters:
- `object_key`: The S3 key of the video to process
- `operations`: Video processing parameters

Example operations:
```
snapshot,time_00:00:10
frame,timestamp_5
```

## Response

The processor returns:
- Base64 encoded processed frame/snapshot
- Content-Type header indicating the image format
- Error details if processing fails

## Dependencies

The processor requires FFmpeg for video processing, which is included in the Lambda layer created by `create_layer.sh`.
