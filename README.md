# Serverless Media Processor

This project contains two serverless services for processing media files under a unified API:
1. Image Processor - For image processing operations
2. Document Processor - For document conversion operations

## Prerequisites

1. AWS CLI installed and configured with appropriate credentials for China region
2. AWS SAM CLI installed (see [Installing SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/serverless-sam-cli-install.html))
3. Python 3.9 or later
4. Docker installed and running (for building document processor container)
5. An S3 bucket in cn-northwest-1 region for storing media files
6. Permission to create S3 buckets (for SAM deployment artifacts)
7. Permission to create and push to ECR repositories

## Deployment

1. Clone the repository and navigate to the project directory:
```bash
cd serverless-media-processor
```

2. Make the deployment script executable:
```bash
chmod +x deploy.sh
```

3. Deploy the unified stack using the deploy script:
```bash
./deploy.sh your-s3-bucket-name
```

The script will:
- Set AWS region to cn-northwest-1 (Ningxia)
- Create Python virtual environment and install dependencies for image processor
- Create ECR repository and push document processor container image
- Create S3 bucket for SAM deployment artifacts if it doesn't exist
- Build and deploy the unified stack using AWS SAM

Notes: 
- The document processor runs in a container with LibreOffice installed, which enables document format conversion capabilities
- The deployment creates a SAM artifacts bucket named 'sam-artifacts-{account-id}-{region}' if it doesn't exist
- The ECR repository is created with the name '{stack-name}-document-processor'

## AWS China Region Considerations

1. Make sure your AWS credentials are configured for China region:
```bash
aws configure
# Set region to cn-northwest-1
```

2. Note that AWS service endpoints in China regions are different from global regions. The services use the following format:
   - S3: s3.cn-northwest-1.amazonaws.com.cn
   - API Gateway: execute-api.cn-northwest-1.amazonaws.com.cn
   - Lambda: lambda.cn-northwest-1.amazonaws.com.cn

3. ARN format in China regions uses 'aws-cn' instead of 'aws':
   - Example: arn:aws-cn:s3:::your-bucket-name

## Services

### Image Processor

Handles various image processing operations including:
- Format conversion (JPG, PNG, WEBP, etc.)
- Auto orientation
- Cropping
- Quality adjustment
- Resizing
- Watermarking

#### API Endpoint:
- POST /images/process - Process an image with specified operations

Example request:
```json
{
  "source_key": "path/to/source/image.jpg",
  "target_key": "path/to/target/image.png",
  "operations": {
    "format": {
      "f": "png",
      "q": 85
    },
    "auto_orient": true,
    "resize": {
      "w": 800,
      "h": 600
    }
  }
}
```

### Document Processor

Handles document conversion operations between various formats:
- PDF
- DOCX
- PPTX
- Images (PNG, JPG)

#### API Endpoints:
- POST /documents/process - Convert a document
- GET /documents/tasks/{taskId} - Get conversion task status

Example request:
```json
{
  "source_key": "path/to/source/document.docx",
  "operations": "convert,source_docx,target_pdf"
}
```

## Architecture

The services share a single API Gateway:
1. Requests are routed through a unified API Gateway
2. Different endpoints route to specific Lambda functions:
   - /images/* routes to image processing (standard Lambda)
   - /documents/* routes to document processing (containerized Lambda with LibreOffice)
3. Files are stored in S3
4. Document processor uses DynamoDB for task tracking
5. Document processor container image is stored in ECR

## Environment Variables

Both services require:
- S3_BUCKET_NAME: S3 bucket for storing media files (provided during deployment)
- AWS_REGION: AWS region for the services (set to cn-northwest-1)

## IAM Permissions

The services are deployed with the minimum required permissions:

Image Processor:
- S3: GetObject, PutObject

Document Processor:
- S3: GetObject, PutObject
- DynamoDB: PutItem, GetItem, UpdateItem

## Troubleshooting

### Deployment Issues

1. If deployment fails, check:
   - AWS credentials are properly configured for China region
   - S3 bucket exists in cn-northwest-1 region and is accessible
   - Required permissions are available
   - SAM CLI is properly installed
   - ICP registration if needed for public access

2. If you see SAM CLI errors:
   - Verify SAM CLI installation: `sam --version`
   - Update SAM CLI if needed
   - Check Python version compatibility

3. If processing fails:
   - Check CloudWatch logs for the specific Lambda function
   - Verify S3 bucket permissions
   - For document processor, check DynamoDB table status

## Local Development

1. Install dependencies for image processor:
```bash
cd image-processor
pip install -r requirements.txt
```

2. For document processor local testing, build the container:
```bash
cd document-processor
docker build -t document-processor .
```

3. For local testing with SAM CLI:
```bash
sam local start-api
```

Note: Local testing of the document processor requires Docker to be running.

## Cleanup

To remove all deployed resources:
```bash
aws cloudformation delete-stack \
    --stack-name media-processor \
    --region cn-northwest-1
```

This will delete all AWS resources created by the services, including:
- Lambda functions
- API Gateway endpoints
- IAM roles
- DynamoDB tables (for document processor)
