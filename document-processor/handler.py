import json
from typing import Dict, Any
from urllib.parse import unquote
from doc_processor import process_document, get_task_status
from text_extractor import TextExtractor

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
        
        if not object_key:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'object_key is required in path parameters'
                }, ensure_ascii=False)
            }
        
        if not operations_str:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'operations are required in query parameters'
                }, ensure_ascii=False)
            }

        # Route based on request path
        if request_path.startswith('/text/'):
            if operations_str != 'extract':
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Only extract operation is supported for /text/ endpoint'
                    }, ensure_ascii=False)
                }
            
            # Use TextExtractor for text extraction
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
            # For convert operations, validate format
            parts = operations_str.split(',')
            if len(parts) < 3 or parts[0] != 'convert':
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid operations format. Expected: convert,target_format,source_format'
                    }, ensure_ascii=False)
                }
            
            # Process document using doc_processor
            response = process_document(object_key, operations_str)
            return {
                'statusCode': response.status_code,
                'body': json.dumps(response.body, ensure_ascii=False)
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            }, ensure_ascii=False)
        }
