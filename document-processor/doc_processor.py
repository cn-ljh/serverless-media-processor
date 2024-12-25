import os
import uuid
import tempfile
import logging

from s3_operations import (
    S3Config, get_s3_client, download_object_from_s3, 
    upload_object_to_s3, get_full_s3_key
)
from doc_converter import (
    SourceFormat, TargetFormat, convert_document, parse_pages_param
)
from ddb_operations import (
    TaskStatus, create_task_record, update_task_status, get_task_status as get_ddb_task_status
)
from b64encoder_decoder import custom_b64decode

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ProcessingError(Exception):
    """Custom exception for processing errors"""
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class Response:
    """Custom response class"""
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self.body = body

def parse_operation(operation_str: str) -> tuple[str, dict]:
    """
    Parse operation string like 'convert,source_doc,target_png,pages_base64string,b_base64bucket'
    
    Parameters:
    - source_{format}: Source document format
    - target_{format}: Target document format
    - pages_{base64}: Base64 encoded page range
    - b_{base64}: Base64 encoded target bucket name
    """
    parts = operation_str.split(',')
    operation = parts[0]
    params = {}
    
    for param in parts[1:]:
        if param.startswith('source_'):
            params['source'] = param[7:]
        elif param.startswith('target_'):
            params['target'] = param[7:]
        elif param.startswith('pages_'):
            # Store the raw base64 encoded string
            params['pages'] = param[6:]
        elif param.startswith('b_'):
            # Store the raw base64 encoded bucket name
            params['bucket'] = param[2:]
            
    return operation, params

def get_file_extension(key: str) -> str:
    """Get file extension from key"""
    return os.path.splitext(key)[1][1:].lower()

def process_document_sync(task_id: str, object_key: str, s3_config: S3Config, s3_client, output_key: str, target_bucket: str, source_format: SourceFormat, target_format: TargetFormat, pages=None):
    """
    Synchronous document processing function
    """
    # Download source document
    try:
        full_key = get_full_s3_key(object_key)
        logger.info(f"Task {task_id}: Downloading source document from S3 with key: {full_key}")
        source_data = download_object_from_s3(
            s3_client, 
            s3_config.bucket_name,
            full_key
        )
    except ProcessingError as e:
        if e.status_code == 404:
            # Try without prefix
            logger.info(f"Task {task_id}: Retrying download without prefix: {object_key}")
            source_data = download_object_from_s3(
                s3_client,
                s3_config.bucket_name,
                object_key
            )
        else:
            logger.error(f"Task {task_id}: Failed to download source document: {str(e)}")
            raise
    
    try:
        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            # Use original filename as temp filename to maintain extension
            temp_input_name = f"source_{os.path.basename(object_key)}"
            temp_output_name = f"output_{os.path.basename(output_key)}"
            
            # Save source document
            input_path = os.path.join(temp_dir, temp_input_name)
            logger.info(f"Task {task_id}: Saving source document to {input_path}")
            with open(input_path, 'wb') as f:
                f.write(source_data)
                
            # Convert document
            output_path = os.path.join(temp_dir, temp_output_name)
            logger.info(f"Task {task_id}: Converting to {output_path}")
            logger.info(f"Task {task_id}: Converting document from {source_format} to {target_format}")
            convert_document(
                input_path=input_path,
                output_path=output_path,
                source_format=source_format,
                target_format=target_format,
                pages=pages
            )
            
            # Upload converted document
            output_s3_key = get_full_s3_key(output_key)
            logger.info(f"Task {task_id}: Uploading converted document to S3 bucket {target_bucket} with key: {output_s3_key}")
            with open(output_path, 'rb') as f:
                upload_object_to_s3(
                    s3_client,
                    target_bucket,
                    output_s3_key,
                    f.read()
                )
        task_type = "doc/convert"
        # Update task status
        logger.info(f"Task {task_id}: Conversion completed successfully")
        update_task_status(task_id, task_type, TaskStatus.COMPLETED)
        
    except Exception as e:
        # Update task status with error
        error_msg = str(e)
        logger.error(f"Task {task_id}: Conversion failed - {error_msg}")
        update_task_status(task_id, task_type, TaskStatus.FAILED, error_msg)
        raise

def process_document(object_key: str, operations: str = None):
    """
    Process document with specified operations
    
    Args:
        object_key: S3 object key of the source document
        operations: Operation string (e.g., 'convert,source_doc,target_png,pages_1,2,4-10,b_base64bucket')
        
    Returns:
        Response object with task details
        
    Raises:
        ProcessingError: If operation fails
    """
    try:
        s3_config = S3Config()
        s3_client = get_s3_client()
        
        # Generate task ID
        task_id = str(uuid.uuid4())
        logger.info(f"Starting document conversion task {task_id} for {object_key}")
        
        # Parse operations
        if not operations:
            logger.error(f"Task {task_id}: No operations specified")
            raise ProcessingError(
                status_code=400,
                detail="No operations specified"
            )
            
        operation, params = parse_operation(operations)
        if operation != 'convert':
            raise ProcessingError(
                status_code=400,
                detail=f"Unknown operation: {operation}"
            )
            
        # Validate parameters
        if 'target' not in params:
            raise ProcessingError(
                status_code=400,
                detail="Target format not specified"
            )
            
        # Determine source format
        source_format = params.get('source')
        if not source_format:
            source_format = get_file_extension(object_key)
            
        try:
            source_format = SourceFormat(source_format)
        except ValueError:
            raise ProcessingError(
                status_code=400,
                detail=f"Unsupported source format: {source_format}"
            )
            
        # Validate target format
        try:
            target_format = TargetFormat(params['target'])
        except ValueError:
            raise ProcessingError(
                status_code=400,
                detail=f"Unsupported target format: {params['target']}"
            )
            
        # Parse pages parameter
        pages = parse_pages_param(params.get('pages'))
        
        # Generate output key
        base_name = os.path.splitext(object_key)[0]
        if pages:
            # If pages specified, add page numbers to filename
            page_indices = '_'.join(str(p) for p in pages)
            output_key = f"{base_name}_p{page_indices}.{target_format.value}"
        else:
            # If no pages specified, use original filename
            output_key = f"{base_name}.{target_format.value}"
        
        # Determine target bucket
        target_bucket = s3_config.bucket_name
        if 'bucket' in params:
            try:
                target_bucket = custom_b64decode(params['bucket'])
                logger.info(f"Task {task_id}: Using custom target bucket: {target_bucket}")
            except Exception as e:
                logger.error(f"Task {task_id}: Invalid target bucket encoding: {str(e)}")
                raise ProcessingError(
                    status_code=400,
                    detail="Invalid target bucket encoding"
                )

        # Create task record
        conversion_params = {
            'source_format': source_format,
            'target_format': target_format,
            'pages': pages,
            'target_bucket': target_bucket
        }
        conversion_task = "doc/convert"

        logger.info(f"Task {task_id}: Creating {conversion_task} record with params: {conversion_params}")
        create_task_record(
            task_id=task_id,
            source_key=object_key,
            target_key=output_key,
            task_type=conversion_task,
            conversion_params=conversion_params
        )
        
        # Process document synchronously
        process_document_sync(
            task_id=task_id,
            object_key=object_key,
            s3_config=s3_config,
            s3_client=s3_client,
            output_key=output_key,
            target_bucket=target_bucket,
            source_format=source_format,
            target_format=target_format,
            pages=pages
        )
        
        return Response(
            status_code=202,
            body={
                'task_id': task_id,
                'status': TaskStatus.PROCESSING.value,
                'task_type': conversion_task,
                'source_key': object_key,
                'target_key': output_key,
                'source_bucket': s3_config.bucket_name,
                'target_bucket': target_bucket
            }
        )
            
    except Exception as e:
        raise ProcessingError(status_code=500, detail=str(e))

def get_task_status(task_id: str, task_type: str):
    """
    Get document conversion task status from DynamoDB
    
    Args:
        task_id: Task identifier
        
    Returns:
        Response object with task status details
        
    Raises:
        ProcessingError: If task not found or other error occurs
    """
    try:
        logger.info(f"Retrieving status for task {task_id}")
        # Get latest task status from DynamoDB
        task = get_ddb_task_status(task_id, task_type)
        if not task:
            raise ProcessingError(status_code=404, detail=f"Task {task_id} not found")
            
        return Response(
            status_code=200,
            body={
                'task_id': task_id,
                'task_type': task_type,
                'status': task['Status']['S'],
                'source_key': task['SourceKey']['S'],
                'target_key': task['TargetKey']['S'],
                'source_bucket': task['SourceBucket']['S'],
                'target_bucket': task['TargetBucket']['S'],
                'created_at': task['Created_at']['S'],
                'updated_at': task['Updated_at']['S'],
                'error_message': task.get('ErrorMessage', {}).get('S')
            }
        )
            
    except ProcessingError:
        raise
    except Exception as e:
        logger.error(f"Error retrieving task {task_id}: {str(e)}")
        raise ProcessingError(status_code=500, detail=str(e))