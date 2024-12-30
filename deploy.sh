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

# Install dependencies for task processor
echo "Installing task processor dependencies..."
cd task-processor
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
deactivate
cd ..

# Get account ID for resource naming
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
STACK_NAME="media-processor-bwm"

# Create S3 bucket for SAM artifacts if it doesn't exist
SAM_BUCKET="sam-artifacts-${ACCOUNT_ID}-${AWS_DEFAULT_REGION}"
aws s3 mb s3://${SAM_BUCKET} --region ${AWS_DEFAULT_REGION} || true

# Remove any previous build artifacts
rm -rf .aws-sam

# Build the SAM application
echo "Building SAM application..."
sam build --parallel

# Deploy the application
echo "Deploying SAM application..."
sam deploy \
    --stack-name ${STACK_NAME} \
    --parameter-overrides BucketName=$S3_BUCKET \
    --capabilities CAPABILITY_IAM \
    --region ${AWS_DEFAULT_REGION} \
    --s3-bucket ${SAM_BUCKET} \
    --no-fail-on-empty-changeset \
    --resolve-image-repos

echo "Deployment completed!"
echo "Check the AWS Console for the API Gateway endpoints."
