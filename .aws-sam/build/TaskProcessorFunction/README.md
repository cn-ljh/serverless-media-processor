# Task Processor API

This Lambda function provides an API endpoint to check the status of media processing tasks. It retrieves task information from DynamoDB, including the task's current status, source and target locations, and any error messages if processing failed.

## API Endpoint

```
GET /task/{task_id}
```

## Parameters

- `task_id`: (Required) The unique identifier of the task to check

## Response Format

```json
{
  "TaskId": "1234-5678-9012",
  "Status": "completed",
  "SourceKey": "original/document.pdf",
  "TargetKey": "processed/document.png",
  "SourceBucket": "media-bucket",
  "TargetBucket": "media-bucket",
  "TaskType": "document",
  "Created_at": "2024-01-01T00:00:00Z",
  "Updated_at": "2024-01-01T00:00:05Z",
  "ErrorMessage": "Error details if failed"
}
```

## Task Status Values

1. `processing`
   - Task is currently being processed
   ```json
   {
     "TaskId": "1234-5678-9012",
     "Status": "processing",
     "SourceKey": "original/document.pdf",
     "TargetKey": "processed/document.png",
     ...
   }
   ```

2. `completed`
   - Task has finished successfully
   ```json
   {
     "TaskId": "1234-5678-9012",
     "Status": "completed",
     "SourceKey": "original/document.pdf",
     "TargetKey": "processed/document.png",
     ...
   }
   ```

3. `failed`
   - Task failed to process
   ```json
   {
     "TaskId": "1234-5678-9012",
     "Status": "failed",
     "SourceKey": "original/document.pdf",
     "TargetKey": "processed/document.png",
     "ErrorMessage": "Failed to process document: insufficient memory",
     ...
   }
   ```

## Error Responses

1. Missing Task ID
```json
{
  "error": "task_id is required in path parameters"
}
```

2. Task Not Found
```json
{
  "error": "Task not found: 1234-5678-9012"
}
```

3. Server Error
```json
{
  "error": "Failed to get task status: <error details>"
}
```

## Example Usage

Check task status:
```
GET /task/1234-5678-9012
```

## Notes

### Configuration
- Function timeout: 5 seconds
- Memory allocation: 128MB
- Uses DynamoDB table specified by DDB_TABLE_NAME environment variable
- Table schema:
  - Primary key: TaskId (String)
  - Attributes:
    - Status (String)
    - SourceKey (String)
    - TargetKey (String)
    - SourceBucket (String)
    - TargetBucket (String)
    - TaskType (String)
    - Created_at (String)
    - Updated_at (String)
    - ErrorMessage (String, optional)

### Best Practices
1. Error Handling:
   - Implement retries for 5xx errors
   - Don't retry 4xx errors
   - Log task ID with all error messages

2. Performance:
   - Keep polling intervals reasonable
   - Implement client-side caching
   - Use conditional requests when possible
