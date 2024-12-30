# Video Processor API

This Lambda function provides video processing capabilities through API Gateway, allowing you to generate snapshots from video files stored in S3.

## API Endpoint

```
GET /video/{key}
```

## Parameters

- `key`: (Required) The object key (path) of the video in S3 bucket
- `operations`: (Required) Query parameter specifying the video operations to perform

## Supported Operations

### Snapshot (`snapshot`)
Takes a screenshot from the video at a specified timestamp.

Parameters:
- `t_<milliseconds>`: (Required) Timestamp to take snapshot from
- `f_<format>`: (Required) Output format (jpg, png)
- `w_<pixels>`: (Optional) Output width
- `h_<pixels>`: (Optional) Output height

Example:
```
# Take a snapshot at 5 seconds in JPG format
GET /video/example.mp4?operations=snapshot,t_5000,f_jpg,w_1280,h_720
```

## Response Format

### Success Response
- Status Code: 200
- Headers:
  ```
  Content-Type: image/[format]
  Content-Disposition: attachment; filename="snapshot.[ext]"
  ```
- Body: Processed image binary

### Error Response
- Status Code: 400/500
- Body:
  ```json
  {
    "error": "Error message",
    "details": {
      "operation": "snapshot",
      "timestamp": 5000,
      "reason": "Invalid timestamp - video duration is 3000ms"
    }
  }
  ```

## Example Usage

1. Basic Snapshot
```
GET /video/example.mp4?operations=snapshot,t_5000,f_jpg
```

2. High Resolution Snapshot
```
GET /video/example.mp4?operations=snapshot,t_5000,f_jpg,w_1920,h_1080
```

## Error Scenarios

1. Invalid Timestamp
```json
{
  "error": "Invalid timestamp",
  "details": "Timestamp exceeds video duration"
}
```

2. Invalid Dimensions
```json
{
  "error": "Invalid dimensions",
  "details": "Width or height exceeds maximum allowed (1920x1080)"
}
```

3. Processing Error
```json
{
  "error": "Processing failed",
  "details": "Failed to decode video frame at 5000ms"
}
```

## Notes

### Configuration
- Function timeout: 60 seconds
- Memory allocation: 2048MB
- Maximum video file size: 500MB
- Maximum output dimensions: 1920x1080
- Supported input formats: MP4, MOV, AVI, MKV
- Supported output formats: JPG, PNG

### Best Practices
1. Video Processing:
   - Use appropriate output dimensions for your use case
   - Consider mobile device limitations
   - Validate timestamps against video duration

2. Error Handling:
   - Implement retry logic for transient failures
   - Handle timeout errors appropriately
   - Validate input parameters before processing

3. Performance:
   - Keep snapshot requests reasonable
   - Implement client-side caching
   - Use appropriate quality settings

### Limitations
- Maximum video duration: 30 minutes
- Maximum output resolution: 1920x1080
- Maximum concurrent requests: 100/minute
