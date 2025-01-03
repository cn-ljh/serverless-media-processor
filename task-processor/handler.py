import json
from typing import Dict, Any
from ddb_operations import get_task_status, ProcessingError

def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for task status retrieval"""
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Get task_id from path parameters
        task_id = event.get('pathParameters', {}).get('task_id')
        
        if not task_id:
            return {
                'statusCode': 400,
                'body': json.dumps({
                    'error': 'task_id is required in path parameters'
                })
            }

        # Get task information from DynamoDB
        task_info = get_task_status(task_id, "document")
        
        # Convert DynamoDB response to regular Python dict
        response_body = {
            'TaskId': task_info['TaskId']['S'],
            'Status': task_info['Status']['S'],
            'SourceKey': task_info['SourceKey']['S'],
            'TargetKey': task_info['TargetKey']['S'],
            'SourceBucket': task_info['SourceBucket']['S'],
            'TargetBucket': task_info['TargetBucket']['S'],
            'TaskType': task_info['TaskType']['S'],
            'Created_at': task_info['Created_at']['S'],
            'Updated_at': task_info['Updated_at']['S']
        }

        # Add error message if present
        if 'ErrorMessage' in task_info:
            response_body['ErrorMessage'] = task_info['ErrorMessage']['S']

        return {
            'statusCode': 200,
            'body': json.dumps(response_body)
        }
            
    except ProcessingError as e:
        return {
            'statusCode': e.status_code,
            'body': json.dumps({
                'error': e.detail
            })
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }
