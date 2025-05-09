# Serverless Media Processor

A serverless solution for processing various types of media files (images, documents, videos, audio) using AWS Lambda and API Gateway. This project provides a set of RESTful APIs for media processing operations including image manipulation, document conversion, video frame extraction, and audio processing.

## Features

- **Image processing**: resize, crop, watermark, format conversion, auto-orient, grayscale
- **Document processing**: format conversion (PDF, DOCX, PNG, etc.), text extraction
- **Video processing**: format conversion, frame extraction, snapshot generation
- **Audio processing**: format conversion, bitrate adjustment
- **Asynchronous processing** for long-running tasks
- **Task status tracking** and retrieval
- **Comprehensive error handling** with DLQ, SNS notifications, and error tracking

## Architecture

The project follows a serverless microservices architecture with specialized processors for different media types:

![Serverless Media Processor Architecture](architecture.png)

*Note: The architecture diagram is available in both PNG format for direct viewing and draw.io format for editing. You can open the draw.io file with [draw.io](https://app.diagrams.net/) or any compatible viewer.*

### Components

- **API Gateway**: RESTful API endpoints for media processing
- **Lambda Functions**:
  - **Image Processor**: Image manipulation (resize, crop, watermark, etc.)
  - **Document Processor**: Document conversion and text extraction
  - **Video Processor**: Video frame extraction and snapshot generation
  - **Audio Processor**: Audio format conversion and processing
  - **Task Processor**: Asynchronous task status tracking
- **S3**: Storage for source and processed media files
- **DynamoDB**: Task status tracking for asynchronous operations
- **SQS**: Dead Letter Queue for failed processing
- **SNS**: Notifications for processing errors

### Processing Flow

1. Client uploads media to S3 or provides a URL
2. Client calls the appropriate API endpoint with processing parameters
3. API Gateway routes the request to the appropriate Lambda function
4. Lambda processes the media and stores results in S3
5. For asynchronous operations, task status is stored in DynamoDB
6. Client can check task status using the Task API

## API Endpoints

- `/image/{key}?operations=...` - Process images
- `/doc/{key}?operations=...` - Process documents
- `/video/{key}?operations=...` - Process videos
- `/audio/{key}?operations=...` - Process audio
- `/task/{task_id}` - Get task status
- `/async-image/{key}?operations=...` - Asynchronous image processing
- `/async-doc/{key}?operations=...` - Asynchronous document processing
- `/text/{key}?operations=extract` - Extract text from documents

## Prerequisites

- AWS CLI installed and configured
- AWS SAM CLI installed
- Docker installed (for local testing)
- An S3 bucket for storing media files

## Deployment

Use the provided deploy.sh script:

```bash
./deploy.sh <bucket-name>
```

During deployment, you'll need to provide:
- Stack Name (e.g., media-processor)
- AWS Region
- S3 Bucket Name for media storage
- Confirm changes before deployment
- Allow SAM CLI to create IAM roles

## Quick Start

After deployment, you'll receive API endpoints for different media processing operations. Here are some examples:

### 1. Image Processing
```bash
# Resize an image to width 800px
curl "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/image/example.jpg?operations=resize,w_800"

# Add a watermark
curl "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/image/example.jpg?operations=watermark,text_Copyright"
```

### 2. Document Processing
```bash
# Convert DOCX to PDF
curl -X POST "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/doc/document.docx?operations=convert,target_pdf,source_docx"

# Extract text from PDF
curl "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/text/document.pdf?operations=extract"
```

### 3. Audio Processing
```bash
# Convert audio format from MP3 to WAV
curl "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/audio/audio.mp3?operations=convert,target_wav"

# Convert audio format from WAV to MP3
curl "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/audio/audio.wav?operations=convert,target_mp3"
```

### 4. Video Processing
```bash
# Take a snapshot at 5 seconds
curl "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/video/video.mp4?operations=snapshot,t_5000,f_jpg"
```

### 5. Async Task Status
```bash
# Check task status
curl "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/task/<task-id>"
```

## Detailed Documentation

Each processor has its own detailed documentation:

- [Image Processor](image-processor/README.md) - Image manipulation operations
- [Document Processor](document-processor/README.md) - Document conversion and text extraction
- [Video Processor](video-processor/README.md) - Video frame extraction
- [Audio Processor](audio-processor/README.md) - Audio format conversion
- [Task Processor](task-processor/README.md) - Async task status tracking

## Configuration

The project uses AWS SAM template (template.yaml) for infrastructure configuration:

- API Gateway:
  - Binary media types support
  - CORS enabled
  - CloudWatch logging
- Lambda Functions:
  - Custom memory allocation
  - Timeout configurations
  - IAM roles and policies
- DynamoDB:
  - Task tracking table
  - Blind watermark table
- SQS:
  - Dead Letter Queue for failed processing
- SNS:
  - Error notification topic

## Development

### Local Testing

1. Start local API:
```bash
sam local start-api
```

2. Test endpoints:
```bash
# Test image processing
curl "http://localhost:3000/image/test.jpg?operations=resize,w_800"

# Test document processing
curl -X POST "http://localhost:3000/doc/test.docx?operations=convert,target_pdf"
```

### Adding New Features

1. Modify Lambda function code in respective directories
2. Update template.yaml for infrastructure changes
3. Build and deploy:
```bash
sam build
sam deploy
```

## Monitoring

- CloudWatch Logs are enabled for API Gateway and all Lambda functions
- API Gateway access logs track request/response details
- DynamoDB tables track task status and processing details
- CloudWatch alarms monitor DLQ message count

## Limitations

- Maximum file sizes:
  - Images: 10MB
  - Documents: 100MB (sync), unlimited (async)
  - Audio: 100MB
  - Videos: 500MB
- Processing timeouts:
  - Image Processor: 30 seconds
  - Document Processor: 60 seconds
  - Video Processor: 30 seconds
  - Audio Processor: 30 seconds
  - Task Processor: 5 seconds

## Security

- API Gateway endpoints use AWS IAM for authentication
- S3 bucket access is restricted to Lambda functions
- DynamoDB access is controlled via IAM roles
- All processed files inherit source file permissions

## Error Handling Mechanisms

The application includes comprehensive error handling mechanisms:

### 1. Dead Letter Queue (DLQ)

Failed Lambda invocations are sent to an SQS Dead Letter Queue, which:
- Captures errors that occur during asynchronous processing
- Preserves the original request for debugging and retry
- Triggers CloudWatch alarms when errors occur

### 2. Error Recording in DynamoDB

All errors are recorded in DynamoDB with:
- Task ID for tracking
- Error message and stack trace
- Request details (source file, operations)
- Timestamp information

### 3. Error Notifications via SNS

Critical errors trigger SNS notifications that can be:
- Sent to email addresses
- Integrated with monitoring systems
- Used to trigger automated remediation

### 4. Centralized Error Handling

Each processor module includes:
- Custom error handler class
- Error capture decorators
- Consistent error response format

### 5. CloudWatch Monitoring

The system includes:
- CloudWatch alarms for DLQ message count
- API Gateway access logging
- Lambda function logging