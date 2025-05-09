import json
import base64
import logging
import traceback
from typing import Dict, Any

from audio_processor import process_audio, ProcessingError
from error_handler import capture_error, error_handler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_response(status_code: int, body: Any, headers: Dict[str, str] = None) -> Dict[str, Any]:
    """Create API Gateway response"""
    response = {
        'statusCode': status_code,
        'isBase64Encoded': False
    }
    
    if isinstance(body, bytes):
        response['body'] = base64.b64encode(body).decode('utf-8')
        response['isBase64Encoded'] = True
    else:
        response['body'] = body if isinstance(body, str) else json.dumps(body)
    
    if headers:
        response['headers'] = headers
        
    return response

@capture_error
def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    AWS Lambda handler for audio processing.
    
    Expected URL format:
    /audio/{proxy+}?operations=operation1,param1_value1,param2_value2
    
    Example:
    /audio/example.wav?operations=convert,f_m4a,ab_96000
    
    Returns:
        API Gateway response dictionary with base64 encoded audio data
    """
    try:
        # Extract path parameters
        path_parameters = event.get('pathParameters', {})
        if not path_parameters or 'proxy' not in path_parameters:
            return create_response(400, {'error': 'Missing audio path in path parameters'})
            
        audio_key = path_parameters['proxy']
        
        # Get operations from query parameters
        query_parameters = event.get('queryStringParameters', {})
        operations = query_parameters.get('operations')
        
        # Process the audio
        logger.info(f"Processing audio {audio_key} with operations: {operations}")
        result = process_audio(audio_key, operations)
        
        # Return the processed audio with headers
        return create_response(
            status_code=200,
            body=result.body,
            headers=result.headers
        )
        
    except ProcessingError as e:
        logger.error(f"Processing error: {str(e)}")
        return create_response(
            status_code=e.status_code,
            body={'error': e.detail}
        )
        
    except Exception as e:
        # Get task ID from context
        task_id = context.aws_request_id
        
        # Extract error details
        error_message = str(e)
        error_details = {
            'traceback': traceback.format_exc(),
            'error_type': e.__class__.__name__,
            'operations': query_parameters.get('operations') if 'query_parameters' in locals() else None
        }
        
        # Record error in DynamoDB and send notification
        error_handler.record_error(
            task_id=task_id,
            task_type="audio/process",
            source_key=audio_key if 'audio_key' in locals() else "unknown",
            error_message=error_message,
            error_details=error_details
        )
        
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(traceback.format_exc())
        
        return create_response(
            status_code=500,
            body={
                'error': f"Internal server error: {str(e)}",
                'task_id': task_id,
                'message': 'Error details have been recorded and will be investigated.'
            }
        )
