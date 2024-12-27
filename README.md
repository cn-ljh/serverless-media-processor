# Serverless Media Processor

A serverless solution for processing various types of media files on AWS, designed specifically for AWS China regions.

## Features

- **Document Processing**: Convert between various document formats (PDF, DOCX, PPTX)
- **Image Processing**: Resize, convert formats, adjust quality, and apply watermarks
- **Video Processing**: Generate thumbnails, extract frames, and process video content
- **Task Management**: Track and manage media processing operations

## Prerequisites

1. AWS CLI with credentials configured for China region
2. AWS SAM CLI installed
3. Python 3.9+
4. Docker (for document processing capabilities)
5. S3 bucket in cn-northwest-1 region
6. IAM permissions for creating Lambda, API Gateway, DynamoDB, S3, and ECR resources

## Quick Start

1. Clone and navigate to the project:
```bash
cd serverless-media-processor
```

2. Make deploy script executable:
```bash
chmod +x deploy.sh
```

3. Deploy the stack:
```bash
./deploy.sh your-s3-bucket-name
```

## AWS China Region Setup

1. Configure AWS CLI for China region:
```bash
aws configure
# Set region to cn-northwest-1
```

2. Note: Service endpoints in China regions use the `.amazonaws.com.cn` suffix

## Architecture Overview

- API Gateway for unified API interface
- Lambda functions for media processing
- S3 for file storage
- DynamoDB for task tracking
- Container-based document processing with LibreOffice
- SQS for task queue management

## Cleanup

Remove all deployed resources:
```bash
aws cloudformation delete-stack \
    --stack-name media-processor \
    --region cn-northwest-1
```
