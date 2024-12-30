# Task Processor

The Task Processor is a serverless component that manages and tracks the status of asynchronous media processing tasks.

## Features

- **Task Status Management**: Track the status of processing tasks
- **DynamoDB Integration**: Store and retrieve task information
- **Error Handling**: Capture and report processing errors
- **Task History**: Maintain creation and update timestamps

## Components

- `handler.py`: Main Lambda handler for task status retrieval
- `ddb_operations.py`: DynamoDB operations for task management
- `s3_operations.py`: S3 operations for file handling

## Task Information

The processor tracks the following information for each task:
- Task ID
- Status (Processing, Completed, Failed)
- Source and Target S3 keys
- Source and Target S3 buckets
- Task Type
- Creation and Update timestamps
- Error messages (if any)

## Usage

The processor accepts requests with the following parameter:
- `task_id`: The unique identifier of the task to retrieve

## Response

The processor returns:
- Complete task information including status and file locations
- Error details if task retrieval fails
