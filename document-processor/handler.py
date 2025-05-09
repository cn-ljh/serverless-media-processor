import json
import uuid
import os
import traceback
from typing import Dict, Any
from urllib.parse import unquote
from b64encoder_decoder import custom_b64decode
from doc_processor import process_document, get_task_status
from text_extractor import TextExtractor
from error_handler import capture_error, error_handler

@capture_error
def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for document processing"""
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Handle different HTTP methods and paths
        path_params = event.get('pathParameters', {})
        proxy_path = path_params.get('proxy', '')
        request_path = event.get('path', '')
        object_key = unquote(proxy_path)
        query_params = event.get('queryStringParameters', {}) or {}
        operations_str = query_params.get('operations', '')

        if not operations_str:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'operations are required in query parameters'
                }, ensure_ascii=False)
            }
        
        # Route based on request path
        if request_path.startswith('/text/fetch_http_url'):
            if operations_str != 'extract':
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Only extract operation is supported for /text/fetch_http_url endpoint'
                    }, ensure_ascii=False)
                }
            
            # Get URL from request body (decode base64 first)
            try:
                encoded_body = event.get('body', '{}')
                decoded_body = custom_b64decode(encoded_body)
                body = json.loads(decoded_body)
                url = body.get('url')
                if not url:
                    return {
                        'statusCode': 400,
                        'body': json.dumps({
                            'error': 'url parameter is required in request body'
                        }, ensure_ascii=False)
                    }
            except json.JSONDecodeError:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid JSON in request body'
                    }, ensure_ascii=False)
                }
            
            # Use TextExtractor for text extraction from URL
            extractor = TextExtractor()
            result = extractor.process_url_text_extraction(url)
            
            if result['success']:
                return {
                    'statusCode': 200,
                    'body': json.dumps(result, ensure_ascii=False)
                }
            else:
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': result['error']
                    }, ensure_ascii=False)
                }
            
        elif request_path.startswith('/text/'):
            if operations_str != 'extract':
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Only extract operation is supported for /text/ endpoint'
                    }, ensure_ascii=False)
                }
            # Use TextExtractor for text extraction from S3
            extractor = TextExtractor()
            result = extractor.process_text_extraction(object_key)
            
            if result['success']:
                return {
                    'statusCode': 200,
                    'body': json.dumps(result, ensure_ascii=False)
                }
            else:
                return {
                    'statusCode': 500,
                    'body': json.dumps({
                        'error': result['error']
                    }, ensure_ascii=False)
                }
        else:
            # For convert operations, validate format and target parameter
            parts = operations_str.split(',')
            if parts[0] != 'convert' or not any(param.startswith('target_') for param in parts[1:]):
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid operations format. Operation must be "convert" and must include a target_format parameter'
                    }, ensure_ascii=False)
                }
            
            # Process document using doc_processor
            if request_path.startswith('/async-doc/'):
                task_id = event.get("TaskId", {})
            else:
                task_id = str(uuid.uuid4())
            response = process_document(task_id, object_key, operations_str)

            return {
                'statusCode': response.status_code,
                'body': json.dumps(response.body, ensure_ascii=False)
            }
            
    except Exception as e:
        # Get task ID from event or context
        task_id = event.get("TaskId", context.aws_request_id)
        
        # Extract error details
        error_message = str(e)
        stack_trace = traceback.format_exc()
        error_details = {
            'traceback': stack_trace,
            'error_type': e.__class__.__name__,
            'event_path': request_path,
            'operation': operations_str
        }
        
        # Log the full error details
        logger.error(f"Document processor error: {error_message}")
        logger.error(f"Stack trace: {stack_trace}")
        
        # Record error in DynamoDB and send notification
        error_handler.record_error(
            task_id=task_id,
            task_type="doc/convert",
            source_key=object_key,
            error_message=error_message,
            error_details=error_details
        )
        
        # Return error response
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': error_message,
                'task_id': task_id,
                'message': 'Error details have been recorded and will be investigated.'
            }, ensure_ascii=False)
        }
