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
            # Parse request body
            body = json.loads(event.get('body', '{}'))
            object_key = body.get('source_key')
            operations = body.get('operations')
            
            if not object_key or not operations:
                return {
                    'statusCode': 400,
                    'body': json.dumps({
                        'error': 'source_key and operations are required'
                    })
                }
            
            # Process document using existing module
            response = await process_document(object_key, operations)
            return {
                'statusCode': response.status_code,
                'body': json.dumps(response.body)
            }
            
        elif http_method == 'GET':
            # Get task status
            task_id = event.get('pathParameters', {}).get('taskId')
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
