# Serverless Media Processor

A serverless solution for processing various types of media files (images, documents, videos) using AWS Lambda and API Gateway. This project provides a set of RESTful APIs for media processing operations including image manipulation, document conversion, and video frame extraction.

## Architecture

The project follows a serverless microservices architecture:

```
API Gateway
    │
    ├── /image/* → Image Processor Lambda
    │   - Handles image resizing, cropping, watermarking
    │   - Uses S3 for storage
    │
    ├── /doc/* → Document Processor Lambda
    │   - Handles document conversion, text extraction
    │   - Uses S3 for storage
    │   - Uses DynamoDB for async tasks
    │
    ├── /video/* → Video Processor Lambda
    │   - Handles video frame extraction
    │   - Uses S3 for storage
    │
    └── /task/* → Task Processor Lambda
        - Tracks async operation status
        - Uses DynamoDB for task tracking
```

Components:
- API Gateway: RESTful API endpoints for media processing
- Lambda Functions:
  - Image Processor: Image manipulation (resize, crop, watermark, etc.)
  - Document Processor: Document conversion and text extraction
  - Video Processor: Video frame extraction and snapshot generation
  - Task Processor: Asynchronous task status tracking
- S3: Storage for source and processed media files
- DynamoDB: Task status tracking for asynchronous operations

## Prerequisites

- AWS CLI installed and configured
- AWS SAM CLI installed
- Docker installed (for local testing)
- An S3 bucket for storing media files

## Deployment

1. Clone the repository:
```bash
git clone <repository-url>
cd serverless-media-processor
```

2. Build the project:
```bash
sam build
```

3. Deploy to AWS:
```bash
sam deploy --guided
```

During the guided deployment, you'll need to provide:
- Stack Name (e.g., media-processor)
- AWS Region
- S3 Bucket Name for media storage
- Confirm changes before deployment
- Allow SAM CLI to create IAM roles

## Quick Start

After deployment, you'll receive API endpoints for different media processing operations. Here are some quick examples:

### 1. Image Processing
```bash
# Resize an image to width 800px
curl "https://<api-id>.execute-api.<region>.amazonaws.com.cn/prod/image/example.jpg?operations=resize,w_800"

# Add a watermark
curl "https://<api-id>.execute-api.<region>.amazonaws.com/prod/image/example.jpg?operations=watermark,text_Copyright"
```

### 2. Document Processing
```bash
# Convert DOCX to PDF
curl -X POST "https://<api-id>.execute-api.<region>.amazonaws.com/prod/doc/document.docx?operations=convert,target_pdf,source_docx"

# Extract text from PDF
curl "https://<api-id>.execute-api.<region>.amazonaws.com/prod/text/document.pdf?operations=extract"
```

### 3. Video Processing
```bash
# Take a snapshot at 5 seconds
curl "https://<api-id>.execute-api.<region>.amazonaws.com/prod/video/video.mp4?operations=snapshot,t_5000,f_jpg"
```

### 4. Async Task Status
```bash
# Check task status
curl "https://<api-id>.execute-api.<region>.amazonaws.com/prod/task/<task-id>"
```

## Detailed Documentation

Each processor has its own detailed documentation:

- [Image Processor](image-processor/README.md) - Image manipulation operations
- [Document Processor](document-processor/README.md) - Document conversion and text extraction
- [Video Processor](video-processor/README.md) - Video frame extraction
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

## Limitations

- Maximum file sizes:
  - Images: 10MB
  - Documents: 100MB (sync), unlimited (async)
  - Videos: 500MB
- Processing timeouts:
  - Image Processor: 30 seconds
  - Document Processor: 60 seconds
  - Video Processor: 30 seconds
  - Task Processor: 5 seconds

## Security

- API Gateway endpoints use AWS IAM for authentication
- S3 bucket access is restricted to Lambda functions
- DynamoDB access is controlled via IAM roles
- All processed files inherit source file permissions

## Support

For detailed information about specific operations, refer to the README.md files in each processor's directory:
- Image operations: [image-processor/README.md](image-processor/README.md)
- Document operations: [document-processor/README.md](document-processor/README.md)
- Video operations: [video-processor/README.md](video-processor/README.md)
- Task status: [task-processor/README.md](task-processor/README.md)
