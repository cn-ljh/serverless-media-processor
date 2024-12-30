# Document Processor API

This Lambda function provides document processing capabilities through API Gateway with both synchronous and asynchronous processing options.

## API Endpoints

### 1. Synchronous Document Processing
```
POST /doc/{object_key}
```

#### Parameters
- `object_key`: The object key (path) of the document in S3 bucket
- `operations`: Query parameter specifying the document operations to perform

#### Supported Operations

1. Document Conversion (`convert`)
Parameters:
- `target_<format>`: Target format to convert to
- `source_<format>`: Source document format
- `quality_<1-100>`: Output quality for image formats (default: 90)
- `dpi_<number>`: DPI for image output (default: 300)

Supported Format Combinations:
- Source formats: docx, pdf, pptx, xlsx
- Target formats: pdf, png, jpg, txt

Examples:
```
# Convert DOCX to PDF
POST /doc/document.docx?operations=convert,target_pdf,source_docx

# Convert PDF to PNG with custom quality and DPI
POST /doc/document.pdf?operations=convert,target_png,source_pdf,quality_95,dpi_400

# Convert PowerPoint to JPG
POST /doc/presentation.pptx?operations=convert,target_jpg,source_pptx
```

### 2. Text Extraction
```
GET /text/{object_key}
```

#### Parameters
- `object_key`: The object key (path) of the document in S3 bucket
- `operations`: Set to "extract" for text extraction
- `format_<type>`: Output format (plain, json) (default: plain)
- `include_metadata_<0/1>`: Include document metadata (default: 0)

Examples:
```
# Extract plain text
GET /text/document.pdf?operations=extract

# Extract text with metadata in JSON format
GET /text/document.docx?operations=extract,format_json,include_metadata_1
```

### 3. Asynchronous Document Processing
```
POST /async-doc/{object_key}
```

#### Parameters
Same parameters as synchronous processing, but operations are performed asynchronously.

Example:
```
# Async conversion of large document
POST /async-doc/large-document.pdf?operations=convert,target_png,source_pdf,quality_95
```

#### Response
```json
{
  "TaskId": "request-id",
  "message": "Document processing task received and started"
}
```

## Response Formats

### Synchronous Processing Response

#### Success
- Status Code: 200
- Headers:
  ```
  Content-Type: application/[format]
  Content-Disposition: attachment; filename="processed-document.[ext]"
  ```
- Body: Processed document binary

#### Error
- Status Code: 400/500
- Body:
  ```json
  {
    "error": "Error message",
    "details": {
      "operation": "convert",
      "source": "document.docx",
      "target_format": "pdf"
    }
  }
  ```

### Text Extraction Response

#### Plain Text Format
```
Extracted text content...
```

#### JSON Format
```json
{
  "content": "Extracted text content",
  "metadata": {
    "title": "Document Title",
    "author": "Author Name",
    "created": "2024-01-01T00:00:00Z",
    "pages": 10
  },
  "statistics": {
    "characters": 1000,
    "words": 200,
    "paragraphs": 20
  }
}
```

### Asynchronous Processing Response

#### Initial Response
```json
{
  "TaskId": "task-uuid",
  "message": "Document processing task received and started"
}
```

#### Status Check Response (via /task/{task_id})
```json
{
  "TaskId": "task-uuid",
  "Status": "PROCESSING",
  "Progress": {
    "current_page": 5,
    "total_pages": 10,
    "percent_complete": 50
  }
}
```

## Error Handling

Common error scenarios and their status codes:

1. Invalid Input (400)
```json
{
  "error": "Invalid input",
  "details": "Unsupported conversion: docx to xyz"
}
```

2. File Not Found (404)
```json
{
  "error": "File not found",
  "details": "Object key 'document.pdf' does not exist"
}
```

3. Processing Error (500)
```json
{
  "error": "Processing error",
  "details": "Failed to convert document: insufficient memory"
}
```

## Notes

### Configuration
- Function Configuration:
  - Timeout: 60 seconds
  - Memory: 1024MB
  - Maximum document size: 100MB for synchronous processing
  - No size limit for async processing

### Performance Considerations
- Use async processing for:
  * Large documents (>100MB)
  * Batch processing
  * Complex conversions
  * High-resolution image output
- Use synchronous processing for:
  * Small documents
  * Simple text extraction
  * Quick format conversions

### Security
- All processed documents are stored in the configured S3 bucket
- Access control is managed through IAM roles
- Document metadata is stored in DynamoDB for async processing

### Best Practices
1. Document Processing:
   - Always specify source format for reliable conversion
   - Use appropriate DPI settings for image output
   - Consider file size when choosing sync/async processing
   - Use text extraction for searchable content

2. Error Handling:
   - Implement retry logic for failed async tasks
   - Handle timeouts appropriately
   - Validate input formats before processing

3. Performance Optimization:
   - Use async processing for large files
   - Monitor memory usage
   - Implement client-side caching
   - Use appropriate quality settings

### Limitations
- Maximum synchronous processing size: 100MB
- Supported source formats: PDF, DOCX, PPTX, XLSX
- Supported target formats: PDF, PNG, JPG, TXT
- Maximum concurrent requests: 100/minute
