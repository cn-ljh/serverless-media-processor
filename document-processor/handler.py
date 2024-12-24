import json
from typing import Dict, Any
from doc_processor import process_document, get_task_status

async def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for document processing"""
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Handle different HTTP methods
        http_method = event.get('httpMethod', 'POST')
        
        if http_method == 'POST':
            # Get parameters
            object_key = event.get('pathParameters', {}).get('object_key')
            query_params = event.get('queryStringParameters', {}) or {}
            operations_str = query_params.get('operations', '')
            
            if not object_key:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'object_key is required in path parameters'
                    })
                }
            
            if not operations_str:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'operations are required in query parameters'
                    })
                }

            # Parse operations string
            parts = operations_str.split(',')
            if len(parts) < 3 or parts[0] != 'convert':
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Invalid operations format. Expected: convert,target_format,source_format'
                    })
                }

            operations = {
                'convert': {
                    'target': parts[1].split('_')[1],
                    'source': parts[2].split('_')[1]
                }
            }
            
            # Process document using existing module
            response = await process_document(object_key, operations)
            return {
                'statusCode': response.status_code,
                'body': json.dumps(response.body)
            }
            
        elif http_method == 'GET':
            # Get task status
            task_id = event.get('pathParameters', {}).get('task_id')
            if not task_id:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'Task ID is required'
                    })
                }
                
            response = await get_task_status(task_id)
            return {
                'statusCode': response.status_code,
                'body': json.dumps(response.body)
            }
            
        else:
            return {
                'statusCode': 405,
                'body': json.dumps({
                    'error': f'Method {http_method} not allowed'
                })
            }
            
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
