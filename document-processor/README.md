# Document Processor

The Document Processor is a serverless component responsible for document format conversion operations. It provides asynchronous document processing capabilities through AWS Lambda.

## Features

- **Asynchronous Document Processing**: Handles document conversion tasks asynchronously using AWS Lambda
- **Format Conversion**: Supports conversion between different document formats
- **Task Status Tracking**: Uses DynamoDB to track the status of processing tasks
- **S3 Integration**: Works with documents stored in S3 buckets

## Components

- `handler.py`: Main Lambda handler for processing document requests
- `doc_processor.py`: Core document processing logic
- `doc_converter.py`: Document format conversion implementation
- `ddb_operations.py`: DynamoDB operations for task tracking
- `s3_operations.py`: S3 operations for file handling
- `b64encoder_decoder.py`: Utilities for base64 encoding/decoding

## Usage

The processor accepts requests with the following parameters:
- `object_key`: The S3 key of the document to process
- `operations`: Conversion parameters in the format `convert,target_format,source_format`

Example operation:
```
convert,pdf,docx
```

## Response

The processor returns:
- Task ID for asynchronous processing
- Status of the conversion task
- Error details if the conversion fails
