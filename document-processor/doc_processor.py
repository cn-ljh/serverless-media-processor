import os
import tempfile
import logging
import pandas as pd
from docx import Document
from pptx import Presentation

from s3_operations import (
    S3Config, get_s3_client, download_object_from_s3, 
    upload_object_to_s3, get_full_s3_key, create_presigned_url
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

def is_text_file(data):
    # Quick check for small files that are likely text
    if len(data) < 512:  # Small files are often text files
        try:
            sample = data.decode('utf-8')
            printable_chars = sum(c.isprintable() or c.isspace() for c in sample)
            if printable_chars / len(sample) > 0.50:  # Very lenient for small files
                return True
        except UnicodeDecodeError:
            pass

    # Common text file signatures and patterns
    if data.startswith(b'\xEF\xBB\xBF'):  # UTF-8 BOM
        return True
    if data.startswith(b'\xFF\xFE') or data.startswith(b'\xFE\xFF'):  # UTF-16 BOM
        return True
    if data.startswith(b'#!') or data.startswith(b'<?xml'):  # Common script/markup headers
        return True
        
    # Try different encodings
    encodings = ['utf-8', 'ascii', 'utf-16', 'latin1']
    for encoding in encodings:
        try:
            # Take a smaller initial sample for quick check
            sample = data[:1024].decode(encoding)
            
            # Quick check for obvious text content
            printable_chars = sum(c.isprintable() or c.isspace() for c in sample)
            if printable_chars / len(sample) > 0.60:  # More lenient initial check
                return True
                
            # If not obvious, do a more thorough check with a larger sample
            sample = data[:4096].decode(encoding)
            lines = sample.splitlines()
            
            # Skip if no lines
            if not lines:
                continue
                
            # Count lines with mostly printable characters
            text_lines = 0
            for line in lines:
                if not line:  # Skip empty lines
                    continue
                    
                # Check for common text patterns
                if any(pattern in line for pattern in [
                    '=', ':', ',', ';',  # Common delimiters
                    '{', '}', '[', ']',  # Brackets
                    '<', '>', '/',        # XML/HTML tags
                    '#', '//', '/*',      # Comments
                    'http://', 'https://' # URLs
                ]):
                    return True
                    
                # Count printable characters
                printable_chars = sum(c.isprintable() or c.isspace() for c in line)
                if printable_chars / len(line) > 0.60:  # More lenient ratio
                    text_lines += 1
                    
            # If we have multiple lines and some are printable
            if len(lines) > 0 and text_lines / len(lines) > 0.5:  # More lenient ratio
                return True
                
        except (UnicodeDecodeError, UnicodeError):
            continue
            
    return False

def get_file_extension(key: str = None, data: bytes = None) -> str:
    """
    Get file extension from key or detect format from file content
    Args:
        key: Optional S3 object key to get extension from
        data: Optional file data to detect format from
    Returns: Detected file format as string
    Raises: ProcessingError if format cannot be determined
    """
    # First try to get extension from key if provided
    if key:
        ext = os.path.splitext(key)[1][1:].lower()
        if ext:
            return ext
        
    # If no extension or no key, try to detect format from content
    try:
        if not data:
            s3_config = S3Config()
            s3_client = get_s3_client()
            data = download_object_from_s3(s3_client, s3_config.bucket_name, key)
                    
        # Check file signatures (magic numbers)
        if data.startswith(b'%PDF'):
            return 'pdf'
        elif data.startswith(b'PK\x03\x04'):
            # Office Open XML formats (docx, xlsx, pptx)
            # Need to check internal content
            with tempfile.NamedTemporaryFile() as temp:
                temp.write(data)
                temp.flush()
                
                try:
                    Document(temp.name)
                    return 'docx'
                except:
                    try:
                        Presentation(temp.name)
                        return 'pptx'
                    except:
                        try:
                            pd.read_excel(temp.name)
                            return 'xlsx'
                        except:
                            pass
        elif data.startswith(b'\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1'):
            # Compound File Binary Format (doc, xls, ppt)
            # Try opening with different libraries to determine exact type
            with tempfile.NamedTemporaryFile() as temp:
                temp.write(data)
                temp.flush()
                
                try:
                    Document(temp.name)
                    return 'doc'
                except:
                    try:
                        Presentation(temp.name)
                        return 'ppt'
                    except:
                        try:
                            pd.read_excel(temp.name)
                            return 'xls'
                        except:
                            pass
        elif is_text_file(data):
            return 'txt' 
        
        raise ProcessingError(
            status_code=400,
            detail="Could not determine file format. Please specify format explicitly."
        )
                            
    except Exception as e:
        if isinstance(e, ProcessingError):
            raise
        raise ProcessingError(
            status_code=500,
            detail=f"Error detecting file format: {str(e)}"
        )

def process_document_sync(task_id: str, object_key: str, s3_config: S3Config, s3_client, output_key: str, target_bucket: str, source_format: SourceFormat, target_format: TargetFormat, pages=None):
    """
    Synchronous document processing function
    """
    task_type = "doc/convert"
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
        # Update task status
        logger.info(f"Task {task_id}: Conversion completed successfully")
        update_task_status(task_id, task_type, TaskStatus.COMPLETED)
        
    except (IOError, OSError) as e:
        # Handle file system related errors
        error_msg = f"File operation error: {str(e)}"
        logger.error(f"Task {task_id}: {error_msg}")
        update_task_status(task_id, task_type, TaskStatus.FAILED, error_msg)
        raise ProcessingError(status_code=500, detail=error_msg)
    except Exception as e:
        # Update task status with error
        error_msg = str(e)
        logger.error(f"Task {task_id}: Conversion failed - {error_msg}")
        update_task_status(task_id, task_type, TaskStatus.FAILED, error_msg)
        raise

def process_document(task_id: str, object_key: str, operations: str = None):
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
            conversion_params=conversion_params,
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
        
        # Create presigned URL only after successful processing
        presigned_url = create_presigned_url(s3_client, target_bucket, output_key)
        
        return Response(
            status_code=202,
            body={
                'task_id': task_id,
                'status': TaskStatus.COMPLETED.value,
                'task_type': conversion_task,
                'source_key': object_key,
                'target_key': output_key,
                'source_bucket': s3_config.bucket_name,
                'target_bucket': target_bucket,
                'target_object_url': presigned_url
            }
        )
            
    except (IOError, OSError) as e:
        error_msg = f"File operation error: {str(e)}"
        logger.error(f"Task {task_id}: {error_msg}")
        raise ProcessingError(status_code=500, detail=error_msg)
    except ValueError as e:
        error_msg = f"Invalid parameter value: {str(e)}"
        logger.error(f"Task {task_id}: {error_msg}")
        raise ProcessingError(status_code=400, detail=error_msg)
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Task {task_id}: {error_msg}")
        raise ProcessingError(status_code=500, detail=error_msg)

def get_task_status(task_id: str, task_type: str):
    """
    Get document conversion task status from DynamoDB
    
    Args:
        task_id: Task identifier
        task_type: Type of task to retrieve (e.g., "doc/convert")
        
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
        
        presigned_url = create_presigned_url(task['TargetBucket']['S'], task['TargetKey']['S'])

        return Response(
            status_code=200,
            body={
                'task_id': task_id,
                'task_type': task_type,
                'target_object_url': presigned_url,
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
