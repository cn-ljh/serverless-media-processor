import json
import logging
import tempfile
import os
from typing import Dict, Any
from doc_converter import (
    SourceFormat,
    extract_text_from_word,
    extract_text_from_ppt,
    extract_text_from_excel,
    extract_text_from_csv,
    convert_pdf_to_text
)
from s3_operations import download_object_from_s3, S3Config, get_s3_client

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class TextExtractor:
    def __init__(self):
        self.s3_config = S3Config()
        self.s3_client = get_s3_client()

    def process_text_extraction(self, object_key: str) -> Dict[str, Any]:
        """
        Process text extraction request from S3 object
        
        Args:
            object_key: S3 object key of the source document
            
        Returns:
            Dict containing extracted text and metadata or error
        """
        try:
            # Get source format from file extension
            source_format = object_key.split('.')[-1].lower()
            
            # Download file from S3
            file_data = download_object_from_s3(
                self.s3_client,
                self.s3_config.bucket_name,
                object_key
            )
            
            # Save to temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{source_format}') as temp_file:
                temp_file.write(file_data)
                temp_path = temp_file.name
            
            try:
                # Extract text from temp file
                result = self.extract_text(temp_path, source_format)
                return result
            finally:
                # Clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                    
        except Exception as e:
            error_msg = f"Failed to process text extraction: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }

    def extract_text(self, file_path: str, source_format: str) -> Dict[str, Any]:
        """
        Extract text from document and return as JSON response
        
        Args:
            file_path: Path to source document
            source_format: Source document format (from SourceFormat enum)
            
        Returns:
            Dict containing extracted text and metadata
        """
        try:
            logger.info(f"Extracting text from {source_format} document: {file_path}")
            
            text = ""
            # Word formats
            if source_format in [SourceFormat.DOC, SourceFormat.DOCX, SourceFormat.WPS, 
                               SourceFormat.DOCM, SourceFormat.DOTM, SourceFormat.DOT, 
                               SourceFormat.DOTX]:
                text = extract_text_from_word(file_path)
                
            # PowerPoint formats    
            elif source_format in [SourceFormat.PPT, SourceFormat.PPTX, SourceFormat.DPS,
                                 SourceFormat.PPTM, SourceFormat.POTM, SourceFormat.PPSM]:
                text = extract_text_from_ppt(file_path)
                
            # Excel formats
            elif source_format in [SourceFormat.XLS, SourceFormat.XLSX, SourceFormat.ET,
                                 SourceFormat.XLSM, SourceFormat.XLTM]:
                text = extract_text_from_excel(file_path)
                
            # CSV format
            elif source_format == SourceFormat.CSV:
                text = extract_text_from_csv(file_path)
                
            # PDF format
            elif source_format == SourceFormat.PDF:
                # Create temporary file for PDF text extraction
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as temp_file:
                    convert_pdf_to_text(file_path, temp_file.name)
                    # Read extracted text from temp file
                    with open(temp_file.name, 'r', encoding='utf-8') as f:
                        text = f.read()
                        
            else:
                error_msg = f"Unsupported source format for text extraction: {source_format}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg
                }

            # Return JSON response with proper encoding for Chinese characters
            return {
                "success": True,
                "text": text.strip(),  # Remove any extra whitespace
                "metadata": {
                    "source_format": source_format,
                    "file_path": file_path,
                    "encoding": "utf-8"
                }
            }
            
        except Exception as e:
            error_msg = f"Failed to extract text: {str(e)}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg
            }
