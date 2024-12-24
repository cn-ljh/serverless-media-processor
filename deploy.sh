#!/bin/bash

# Check if bucket name is provided
if [ -z "$1" ]; then
    echo "Usage: ./deploy.sh <s3-bucket-name>"
    echo "Example: ./deploy.sh my-media-bucket"
    exit 1
fi

S3_BUCKET=$1

# Set AWS region for China
export AWS_DEFAULT_REGION=cn-northwest-1

echo "Starting deployment process in China Northwest (Ningxia) region..."

# Install dependencies for image processor
echo "Installing image processor dependencies..."
cd image-processor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..

# Build and push document processor container image
echo "Building and pushing document processor container image..."
cd document-processor

# Get ECR repository URI
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO="${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com.cn/media-processor-document-processor"

# Authenticate Docker to ECR
aws ecr get-login-password --region ${AWS_DEFAULT_REGION} | docker login --username AWS --password-stdin ${ACCOUNT_ID}.dkr.ecr.${AWS_DEFAULT_REGION}.amazonaws.com.cn

# Create ECR repository if it doesn't exist
aws ecr create-repository --repository-name media-processor-document-processor --region ${AWS_DEFAULT_REGION} || true

# Build and push the image
docker build -t ${ECR_REPO}:latest .
docker push ${ECR_REPO}:latest

cd ..

# Build and deploy the unified stack with container image
echo "Deploying unified media processor stack..."
sam build

# Create S3 bucket for SAM artifacts if it doesn't exist
SAM_BUCKET="sam-artifacts-${ACCOUNT_ID}-${AWS_DEFAULT_REGION}"
aws s3 mb s3://${SAM_BUCKET} --region ${AWS_DEFAULT_REGION} || true

sam deploy --stack-name media-processor \
    --parameter-overrides BucketName=$S3_BUCKET \
    --capabilities CAPABILITY_IAM \
    --region cn-northwest-1 \
    --confirm-changeset \
    --image-repository ${ECR_REPO} \
    --s3-bucket ${SAM_BUCKET}

echo "Deployment completed!"
echo "Check the AWS Console for the API Gateway endpoints."
