# MinerU-based PDF/PPT Parsing Module

This module provides a comprehensive PDF and PowerPoint document parsing solution using MinerU technology, designed as a modular extension to the existing gzero.py parsing system.

## Features

### Core Capabilities
- **Multi-format Support**: Direct processing of PPT (.ppt/.pptx) and PDF files
- **Intelligent Format Detection**: Automatically detects PPT-origin PDFs for optimized processing
- **Page-by-Page Processing**: Splits PDFs into individual pages for parallel MinerU processing
- **Advanced Image Processing**: AI-powered image classification and content extraction
- **Table Recognition**: Specialized handling for documents containing table structures
- **Content Fusion**: Combines MinerU structured output with plain text for accuracy

### Processing Flow

#### Page-by-Page Processing
**Core Benefits**: Faster processing, better parallelization, optimal resource usage

1. **PDF Splitting**: Automatically splits PDF into individual page files using PyMuPDF
2. **Parallel Processing**: Processes multiple pages simultaneously with MinerU API
3. **Batch Management**: Smart batching to avoid API rate limits (configurable concurrency)
4. **Progress Tracking**: Real-time progress reporting with page-level status
5. **Error Resilience**: Continues processing even if individual pages fail
6. **Result Merging**: Combines all page results into structured markdown content
7. **Image Organization**: Automatically renames images with page prefixes for better organization

#### Document Processing Pipeline
1. **File Input**: Accepts PPT (.ppt/.pptx) or PDF files
2. **Format Detection**: Determines if PDF originated from PPT presentation  
3. **PPT Conversion**: Converts PPT to PDF using LibreOffice (with fallback)
4. **Page Splitting**: Splits PDF into individual pages for parallel processing
5. **MinerU Processing**: Each page processed through MinerU API with OCR, formula, and table recognition
6. **Content Integration**: Merges page results with structured content organization
7. **Image Processing**: AI-powered image classification and upload integration
8. **Final Assembly**: Creates complete document with page-organized content

## Architecture

### Module Structure
```
loader/mineru/
├── __init__.py              # Module initialization
├── maxkb_adapter/           # MaxKB adapter implementation
│   ├── __init__.py          # Adapter module initialization
│   ├── adapter.py           # MaxKBAdapter and MinerUExtractor
│   └── config_maxkb.py      # MaxKB-specific configuration
├── base_parser.py           # Base classes for platform adapters
├── config.py                # Configuration management
├── converter.py             # File conversion and detection
├── api_client.py            # MinerU API integration
├── image_processor.py       # Image recognition and processing
├── content_processor.py     # Content fusion and refinement
├── flowchart_plugin.py      # Specialized flowchart processing
├── utils.py                 # Utility functions
├── example.py               # Usage examples
└── README.md                # This file
```

### Key Components

**MinerUExtractor**: Main parser class orchestrating the complete pipeline
- Handles file processing from input to final Document output
- Manages temporary directories and caching
- Integrates with existing gzero.py patterns for compatibility

**DocumentConverter**: File type detection and conversion
- PPT to PDF conversion with LibreOffice and fallback methods
- PDF format detection (PPT-origin vs native PDF)
- Page extraction and metadata analysis

**MinerUAPIClient**: Interface to MinerU service
- Handles API communication and response processing
- Supports both cloud and self-hosted MinerU deployments
- Includes mock implementation for development/testing
- Cloud API: Asynchronous processing with polling
- Self-hosted API: Synchronous processing with direct file upload

**MinerUImageProcessor**: Advanced image handling
- AI-powered image classification (structured_content/brief_description/meaningless)
- Batch processing with concurrency control
- Integration with existing image upload infrastructure

**MinerUContentProcessor**: Content analysis and enhancement
- Table detection and specialized processing
- Plain text extraction and merging with structured content
- LLM-based content refinement for complex documents

## Configuration

### Environment Variables
```bash
# MinerU API Configuration
MINERU_API_KEY=your_mineru_api_key          # Required for cloud API
MINERU_API_URL=https://mineru.net           # Cloud API URL
MINERU_API_TYPE=cloud                       # "cloud" or "self_hosted"

# For self-hosted MinerU (alternative configuration)
# MINERU_API_URL=http://10.128.4.1:30001   # Self-hosted API URL
# MINERU_API_TYPE=self_hosted               # No API key required

# LLM Configuration (uses existing gzero.py settings)
ADVANCED_PARSER_KEY_OPENAI=your_openai_key
ADVANCED_PARSER_KEY_CLAUDE=your_claude_key
ADVANCED_PARSER_KEY_GEMINI=your_gemini_key

# Processing Configuration
MAX_FILE_SIZE=52428800  # 50MB
LIBREOFFICE_PATH=libreoffice
CONVERSION_TIMEOUT=300  # 5 minutes

# Parallel Processing Controls
MAX_CONCURRENT_UPLOADS=5
MAX_CONCURRENT_API_CALLS=3  # Controls page processing concurrency
MAX_IMAGE_SIZE_MB=5.0
COMPRESSION_QUALITY=85
```

### API Type Comparison

| Feature | Cloud API | Self-Hosted API |
|---------|-----------|-----------------|
| **Authentication** | API key required | No authentication |
| **Processing Model** | Asynchronous with polling | Synchronous direct response |
| **File Upload** | Requires public URL | Direct multipart upload |
| **Rate Limits** | 2000 pages/day (free tier) | Limited by server resources |
| **Network Requirements** | Internet access required | Local network access |
| **Setup Complexity** | Simple (API key only) | Requires self-hosted deployment |
| **Processing Speed** | Depends on queue | Immediate processing |
| **Data Privacy** | Data sent to cloud | Data stays on-premise |

### Settings Integration
The module integrates with existing `gptbase.settings` for:
- API keys and model configurations
- Upload and storage settings  
- Cache and processing parameters
- Logging configuration

## Usage

### Basic Usage
```python
from loader.mineru.gbase_adapter import MinerUExtractor

# Initialize extractor (automatically uses page-by-page processing)
extractor = MinerUExtractor(learn_type=9)

# Process file
documents = await extractor.process_file(
    filepath="/path/to/document.pptx",
    upload_options=upload_options
)

# Access results
doc = documents[0]
content = doc.page_content
metadata = doc.metadata

# Check processing results
print(f"Processing mode: {metadata.get('processing_mode', 'page_by_page')}")
print(f"Total pages: {metadata.get('total_pages', 0)}")
print(f"Successful pages: {metadata.get('successful_pages', 0)}")
print(f"Images found: {metadata.get('images_found', 0)}")
```

### Configuring API Type
```python
from loader.mineru.gbase_adapter import MinerUExtractor
from loader.mineru.config_base import MinerUConfig

# Cloud API configuration (default)
cloud_config = MinerUConfig()
cloud_config.mineru_api_type = "cloud"
cloud_config.mineru_api_key = "your_api_key"
cloud_config.mineru_api_url = "https://mineru.net"

# Self-hosted API configuration
self_hosted_config = MinerUConfig()
self_hosted_config.mineru_api_type = "self_hosted"
self_hosted_config.mineru_api_url = "http://10.128.4.1:30001"
# No API key required for self-hosted

# Use with custom configuration
extractor = MinerUExtractor(learn_type=9)
extractor.config = self_hosted_config

documents = await extractor.process_file(
    filepath="/path/to/document.pdf",
    upload_options=upload_options
)
```

### Configuring Concurrency
```python
from loader.mineru.gbase_adapter import MinerUExtractor
from loader.mineru.config_base import MinerUConfig

# Configure parallel processing limits
config = MinerUConfig()
config.max_concurrent_api_calls = 2  # Process 2 pages simultaneously
config.max_concurrent_uploads = 3    # Upload 3 images simultaneously

# Use with custom configuration
extractor = MinerUExtractor(learn_type=9)
extractor.config = config

documents = await extractor.process_file(
    filepath="/path/to/large_document.pdf",
    upload_options=upload_options
)
```

### Integration with Existing Code
The module is designed to be a drop-in replacement for gzero.py processing:

```python
# Replace gzero_load with mineru processing
from loader.mineru.gbase_adapter import MinerUExtractor

async def process_with_mineru(file_path, learn_type, upload_options):
    extractor = MinerUExtractor(learn_type)
    return await extractor.process_file(file_path, upload_options=upload_options)

# Batch processing multiple files
async def batch_process_files(file_paths, learn_type, upload_options):
    extractor = MinerUExtractor(learn_type)
    results = []
    
    for file_path in file_paths:
        try:
            documents = await extractor.process_file(file_path, upload_options=upload_options)
            results.append((file_path, documents[0]))
        except Exception as e:
            print(f"Failed to process {file_path}: {e}")
            results.append((file_path, None))
    
    return results
```

## Advanced Features

### Flowchart Plugin
Specialized processing for complex flowchart documents:
- Multi-step node identification
- Department organization mapping
- Mermaid diagram generation
- Enhanced visual element extraction

### Content Fusion
Sophisticated content merging strategies:
- Plain text + structured content integration
- Table-aware processing workflows
- LLM-based content refinement
- Context-preserving enhancement

### Image Intelligence
Advanced image processing capabilities:
- Semantic classification of document images
- OCR content extraction and integration
- Meaningless image filtering
- Batch processing with optimization

## Logging and Tracing

Comprehensive logging with trace_id support:
- File ID-based tracing throughout pipeline
- Detailed processing metrics and timing
- Error handling with context preservation
- Integration with existing logging infrastructure

## Compatibility

### gzero.py Integration
- Uses same `learn_infos` configuration structure
- Compatible with existing upload and storage systems
- Follows same Document metadata patterns
- Maintains cache and temporary file conventions

### Dependencies
- **Core**: Built on existing project dependencies
- **LibreOffice**: For PPT conversion (with fallback options)
- **PyMuPDF (fitz)**: For PDF processing and analysis
- **Optional**: python-pptx, reportlab for alternative conversion

## Performance Considerations

### Optimization Features
- **Page-by-Page Processing**: Parallel processing of individual pages for faster results
- **Smart Batching**: Configurable concurrency limits to optimize API usage
- **Concurrent Processing**: Parallel image classification and upload
- **Intelligent Caching**: Reuses processed results when possible  
- **Selective Processing**: Filters meaningless images before upload
- **Progress Monitoring**: Real-time tracking of page processing status

### Resource Management
- **Memory Efficient**: Streams large files and cleans up resources
- **Configurable Limits**: Adjustable concurrency and size limits
- **Error Recovery**: Graceful handling of processing failures
- **Timeout Management**: Prevents hanging operations

## Development and Testing

### Mock Implementation
The module includes mock MinerU processing for development:
- Simulates API responses for testing
- Provides realistic processing results
- Enables development without actual MinerU service

### Example Scripts
- `example.py`: Comprehensive usage examples
- Configuration validation helpers
- Batch processing demonstrations

### Error Handling
- Comprehensive exception handling throughout pipeline
- Graceful fallbacks for conversion failures
- Detailed error logging with context
- Recovery strategies for partial failures

## Future Enhancements

### Planned Features
- **Enhanced File Upload**: Integrated temporary file hosting for MinerU API
- **Advanced Table Processing**: More sophisticated table structure analysis
- **Multi-language Support**: Extended language detection and processing
- **Performance Monitoring**: Built-in metrics and performance tracking
- **Adaptive Batching**: Dynamic concurrency adjustment based on API performance

### Extensibility
- **Plugin Architecture**: Easy addition of specialized processors
- **Custom Workflows**: Configurable processing pipelines
- **API Extensions**: Support for additional MinerU service features
- **Format Extensions**: Framework for additional input formats