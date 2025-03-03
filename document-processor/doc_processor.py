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
    Parse operation string like 'convert,source_doc,target_png,pages_3,5-10,15,b_base64bucket'
    
    Parameters:
    - source_{format}: Source document format
    - target_{format}: Target document format
    - pages_{range}: Page range (direct notation or base64)
    - b_{base64}: Base64 encoded target bucket name
    """
    # First get the operation type
    if ',' not in operation_str:
        raise ProcessingError(status_code=400, detail="Invalid operation string format")
    
    operation, rest = operation_str.split(',', 1)
    params = {}
    
    # Process the rest of the string
    current_param = []
    current_type = None
    
    for part in rest.split(','):
        # Check if this is a new parameter type
        if part.startswith(('source_', 'target_', 'pages_', 'b_')):
            # Save previous parameter if exists
            if current_type and current_param:
                value = ','.join(current_param)
                if current_type == 'source':
                    params['source'] = value
                elif current_type == 'target':
                    params['target'] = value
                elif current_type == 'pages':
                    # For pages, keep the original format with commas
                    params['pages'] = value
                elif current_type == 'b':
                    params['bucket'] = value
                current_param = []
            
            # Start new parameter
            if part.startswith('source_'):
                current_type = 'source'
                current_param.append(part[7:])
            elif part.startswith('target_'):
                current_type = 'target'
                current_param.append(part[7:])
            elif part.startswith('pages_'):
                current_type = 'pages'
                current_param.append(part[6:])
            elif part.startswith('b_'):
                current_type = 'b'
                current_param.append(part[2:])
        else:
            # Continue previous parameter
            current_param.append(part)
    
    # Save the last parameter
    if current_type and current_param:
        value = ','.join(current_param)
        if current_type == 'source':
            params['source'] = value
        elif current_type == 'target':
            params['target'] = value
        elif current_type == 'pages':
            # For pages parameter, check if it's base64 or direct notation
            if not any(c in value for c in ',-_'):
                # Likely base64 encoded
                try:
                    params['pages'] = custom_b64decode(value)
                except:
                    # If decode fails, use as-is
                    params['pages'] = value
            else:
                # Direct page range notation
                params['pages'] = value
        elif current_type == 'b':
            params['bucket'] = value
            
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
            logger.info(f"Found extension from key: {ext}")
            return ext
        
    # If no extension or no key, try to detect format from content
    try:
        if not data:
            s3_config = S3Config()
            s3_client = get_s3_client()
            data = download_object_from_s3(s3_client, s3_config.bucket_name, key)
                    
        import subprocess
        
        # First try MIME type detection for PowerPoint files
        logger.info("Attempting MIME type detection for PowerPoint files...")
        with tempfile.NamedTemporaryFile(suffix='.tmp') as temp:
            temp.write(data)
            temp.flush()
            
            try:
                result = subprocess.run(['file', '--mime-type', temp.name], capture_output=True, text=True, check=True)
                mime_type = result.stdout.split(': ')[1].strip()
                logger.info(f"Detected MIME type: {mime_type}")
                
                # Check for PowerPoint formats first
                if 'application/vnd.ms-powerpoint' in mime_type:
                    logger.info("Detected as PPT format (old PowerPoint)")
                    return 'ppt'
                elif 'application/vnd.openxmlformats-officedocument.presentationml.presentation' in mime_type:
                    logger.info("Detected as PPTX format (modern PowerPoint)")
                    return 'pptx'
            except Exception as e:
                logger.debug(f"MIME type detection failed: {str(e)}")
        
        logger.info("Attempting to detect modern Office formats...")
        # Try modern Office formats
        for test_ext in ['.docx', '.pptx', '.xlsx']:
            with tempfile.NamedTemporaryFile(suffix=test_ext) as temp:
                temp.write(data)
                temp.flush()
                logger.debug(f"Testing with extension: {test_ext}")
                
                try:
                    if test_ext == '.docx':
                        Document(temp.name)
                        logger.info("Detected as DOCX format")
                        return 'docx'
                    elif test_ext == '.pptx':
                        Presentation(temp.name)
                        logger.info("Detected as PPTX format")
                        return 'pptx'
                    elif test_ext == '.xlsx':
                        pd.read_excel(temp.name)
                        logger.info("Detected as XLSX format")
                        return 'xlsx'
                except Exception as e:
                    logger.debug(f"Not a {test_ext} file: {str(e)}")
                    continue
        
        logger.info("Attempting to detect older Office formats...")
        # Try older formats (except PowerPoint which was handled by MIME type)
        for test_ext in ['.doc', '.xls']:
            with tempfile.NamedTemporaryFile(suffix=test_ext) as temp:
                temp.write(data)
                temp.flush()
                logger.debug(f"Testing with extension: {test_ext}")
                
                try:
                    if test_ext == '.doc':
                        Document(temp.name)
                        logger.info("Detected as DOC format")
                        return 'doc'
                    elif test_ext == '.xls':
                        pd.read_excel(temp.name)
                        logger.info("Detected as XLS format")
                        return 'xls'
                except Exception as e:
                    logger.debug(f"Not a {test_ext} file: {str(e)}")
                    continue
        
        logger.info("Attempting final MIME type detection...")
        # Final MIME type detection for remaining formats
        with tempfile.NamedTemporaryFile(suffix='.tmp') as temp:
            temp.write(data)
            temp.flush()
            
            try:
                result = subprocess.run(['file', '--mime-type', temp.name], capture_output=True, text=True, check=True)
                mime_type = result.stdout.split(': ')[1].strip()
                logger.info(f"Detected MIME type: {mime_type}")
                
                # Map MIME types to file extensions
                if 'application/msword' in mime_type:
                    return 'doc'
                elif 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' in mime_type:
                    return 'docx'
                elif 'application/vnd.ms-excel' in mime_type:
                    return 'xls'
                elif 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' in mime_type:
                    return 'xlsx'
                elif 'application/pdf' in mime_type:
                    return 'pdf'
                
                # Check for text files
                if is_text_file(data):
                    logger.info("Detected as text file")
                    return 'txt'
            except subprocess.CalledProcessError as e:
                logger.error(f"File command failed: {e.stderr}")
            except Exception as e:
                logger.error(f"Error during file type detection: {str(e)}")
        
        logger.error("Could not determine file format")
        raise ProcessingError(
            status_code=400,
            detail="Could not determine file format. Please specify format explicitly."
        )
                            
    except Exception as e:
        if isinstance(e, ProcessingError):
            raise
        logger.error(f"Error detecting file format: {str(e)}")
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
                
            # Create output directory for multiple files if needed
            output_dir = os.path.join(temp_dir, 'output')
            os.makedirs(output_dir, exist_ok=True)

            # Convert document
            logger.info(f"Task {task_id}: Converting document from {source_format} to {target_format}")
            
            if target_format == TargetFormat.PNG:
                # Special handling for any to PNG conversion
                convert_document(
                    input_path=input_path,
                    output_path=output_dir,
                    source_format=source_format,
                    target_format=target_format,
                    pages=pages
                )
                
                # Upload each converted image with original filename as prefix
                base_prefix = os.path.splitext(object_key)[0]
                
                # List all generated PNG files
                png_files = [f for f in os.listdir(output_dir) if f.endswith('.png')]
                png_files.sort()  # Ensure consistent order
                
                for png_file in png_files:
                    page_num = png_file.split('_')[1].split('.')[0]  # Extract page number
                    output_s3_key = f"{base_prefix}/page_{page_num}.png"
                    
                    logger.info(f"Task {task_id}: Uploading page {page_num} to S3 bucket {target_bucket} with key: {output_s3_key}")
                    with open(os.path.join(output_dir, png_file), 'rb') as f:
                        upload_object_to_s3(
                            s3_client,
                            target_bucket,
                            output_s3_key,
                            f.read()
                        )
                
                # Update output_key to be the prefix directory
                output_key = f"{base_prefix}/"
                
            else:
                # Standard single-file conversion
                output_path = os.path.join(temp_dir, temp_output_name)
                logger.info(f"Task {task_id}: Converting to {output_path}")
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
        if target_format == TargetFormat.PNG:
            # For any to PNG conversion, use directory prefix
            output_key = f"{base_name}/"
        else:
            # For other conversions, use standard file naming
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
