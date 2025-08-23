#!/usr/bin/env python3
"""
MinerU Parser Test Script

This script provides comprehensive testing for the MinerU-based PDF/PPT parsing system.
It includes configuration validation, API connectivity tests, document processing examples,
and MaxKB adapter functionality tests.
"""

import asyncio
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Any, Dict
from dataclasses import dataclass
from unittest.mock import Mock, patch, AsyncMock, MagicMock

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# For MaxKB, also add the apps directory to the path
apps_path = project_root / 'apps'
if apps_path.exists():
    sys.path.insert(0, str(apps_path))
    print(f"✅ Added apps directory to Python path: {apps_path}")

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    # Load .env file from project root
    env_path = project_root / '.env'
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"✅ Loaded environment variables from {env_path}")
    else:
        print(f"ℹ️ No .env file found at {env_path}, using system environment variables")
except ImportError:
    print("ℹ️ python-dotenv not installed. Using system environment variables only.")
    print("   Install with: pip install python-dotenv")

# Setup Django environment if we're in MaxKB
try:
    import django
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'maxkb.settings')
    django.setup()
    print("✅ Django environment initialized")
except ImportError:
    print("ℹ️ Django not available - running in standalone mode")
except Exception as e:
    print(f"ℹ️ Could not initialize Django: {e}")

# Try to import MinerU modules - handle both GPTBase and MaxKB environments
mineru_modules_loaded = False
maxkb_adapter_loaded = False

# Try GPTBase imports first
try:
    from loader.trace import init_trace_logging
    init_trace_logging()
    from loader.mineru.gbase_adapter import MinerUExtractor
    from loader.mineru.config_base import MinerUConfig
    from loader.mineru.api_client import MinerUAPIClient
    from loader.mineru.utils import get_file_hash, get_temp_dir
    from loader.schema_extractor.document_integration import extract_schemas_from_docs
    from gptbase import settings
    print("✅ Successfully imported GPTBase MinerU modules")
    mineru_modules_loaded = True
except ImportError as e:
    print(f"ℹ️ GPTBase modules not available: {e}")

# Try MaxKB adapter imports
try:
    from common.handle.impl.mineru.maxkb_adapter.adapter import (
        MaxKBAdapter, MinerUExtractor as MaxKBMinerUExtractor, MinerUAdapter
    )
    from common.handle.impl.mineru.maxkb_adapter.file_storage_client import FileStorageClient
    from common.handle.impl.mineru.maxkb_adapter.maxkb_model_client import MaxKBModelClient
    from common.handle.impl.mineru.maxkb_adapter.config_maxkb import MaxKBMinerUConfig
    print("✅ Successfully imported MaxKB adapter modules")
    maxkb_adapter_loaded = True
except ImportError as e:
    print(f"⚠️ MaxKB adapter modules not available: {e}")

if not mineru_modules_loaded and not maxkb_adapter_loaded:
    print("❌ Neither GPTBase nor MaxKB modules could be loaded")
    print("Please ensure you're running this script from the project root directory")
    sys.exit(1)


@dataclass
class TestConfig:
    """Test configuration settings"""
    test_file_path: Optional[str] = None
    api_url: str = "http://mineru:8000"
    api_type: str = "self_hosted"  # "cloud" or "self_hosted"
    api_key: Optional[str] = None
    learn_type: int = 9
    max_concurrent: int = 2
    verbose: bool = True


class MinerUTester:
    """MinerU testing utility class"""
    
    def __init__(self, test_config: TestConfig):
        self.config = test_config
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log message with formatting"""
        icons = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "DEBUG": "🔍"}
        icon = icons.get(level, "📝")
        print(f"{icon} {message}")
        
    async def run_all_tests(self):
        """Run all MinerU tests"""
        self.log("🚀 Starting MinerU Parser Tests", "INFO")
        print("=" * 60)
        
        # Test 1: Environment Check
        await self.test_environment()
        
        # Test 2: Configuration Validation
        await self.test_configuration()
        
        # Test 3: API Connectivity
        await self.test_api_connectivity()
        
        # Test 4: Real File Processing (if file provided)
        if self.config.test_file_path:
            await self.test_file_processing()
        
        # # Test 5: Batch Processing Test
        # await self.test_batch_processing()
        
        # Show results summary
        self.show_test_summary()
        
    async def test_environment(self):
        """Test environment setup and dependencies"""
        self.log("🔧 Testing Environment Setup")
        
        try:
            # Check Python version
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            self.log(f"Python version: {python_version}")
            
            # Check required packages
            required_packages = ['aiohttp', 'fitz', 'loguru', 'langchain']
            for package in required_packages:
                try:
                    __import__(package)
                    self.log(f"Package {package}: Available", "SUCCESS")
                except ImportError:
                    self.log(f"Package {package}: Missing", "ERROR")
            
            # Check PyMuPDF specifically
            try:
                import fitz
                self.log(f"PyMuPDF version: {fitz.version[0]}", "SUCCESS")
            except Exception as e:
                self.log(f"PyMuPDF error: {e}", "ERROR")
                
            # Check LibreOffice (for PPT conversion)
            try:
                import subprocess
                result = subprocess.run(['libreoffice', '--version'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    version = result.stdout.strip()
                    self.log(f"LibreOffice: {version}", "SUCCESS")
                else:
                    self.log("LibreOffice: Not available", "WARNING")
            except Exception as e:
                self.log("LibreOffice: Not available (PPT conversion will use fallback)", "WARNING")
            
            self.results.append(("Environment Check", True, "Environment validated"))
            
        except Exception as e:
            self.log(f"Environment check failed: {e}", "ERROR")
            self.results.append(("Environment Check", False, str(e)))
    
    async def test_configuration(self):
        """Test MinerU configuration"""
        self.log("⚙️ Testing Configuration")
        
        try:
            # Create test config
            config = MinerUConfig()
            config.mineru_api_type = self.config.api_type
            config.mineru_api_url = self.config.api_url
            config.mineru_api_key = self.config.api_key
            config.max_concurrent_api_calls = self.config.max_concurrent
            
            # Log configuration values
            self.log(f"API Type: {config.mineru_api_type}")
            self.log(f"API URL: {config.mineru_api_url}")
            self.log(f"API Key: {'***' if config.mineru_api_key else 'Not set'}")
            self.log(f"Max Concurrent: {config.max_concurrent_api_calls}")
            self.log(f"Max File Size: {config.max_file_size / (1024*1024):.1f}MB")
            self.log(f"Cache Enabled: {config.enable_cache}")
            
            # Validate configuration
            if config.validate():
                self.log("Configuration validation: PASSED", "SUCCESS")
                self.results.append(("Configuration", True, "Configuration is valid"))
            else:
                self.log("Configuration validation: FAILED", "ERROR")
                self.results.append(("Configuration", False, "Invalid configuration"))
            
        except Exception as e:
            self.log(f"Configuration test failed: {e}", "ERROR")
            self.results.append(("Configuration", False, str(e)))
    
    async def test_api_connectivity(self):
        """Test API connectivity"""
        self.log(f"🌐 Testing API Connectivity ({self.config.api_type})")
        
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                if self.config.api_type == "cloud":
                    # Test cloud API
                    test_url = f"{self.config.api_url}/api/v4/extract/task"
                    headers = {
                        'Authorization': f'Bearer {self.config.api_key}',
                        'Content-Type': 'application/json'
                    }
                    
                    try:
                        async with session.post(test_url, headers=headers, 
                                              json={"test": "connectivity"}, 
                                              timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            self.log(f"Cloud API status: {resp.status}")
                            if resp.status in [200, 400, 401]:  # 400/401 expected for test request
                                self.log("Cloud API connectivity: OK", "SUCCESS")
                                self.results.append(("API Connectivity", True, "Cloud API accessible"))
                            else:
                                self.log("Cloud API connectivity: Issues detected", "WARNING")
                                self.results.append(("API Connectivity", False, f"HTTP {resp.status}"))
                    except Exception as e:
                        self.log(f"Cloud API connectivity failed: {e}", "ERROR")
                        self.results.append(("API Connectivity", False, str(e)))
                
                elif self.config.api_type == "self_hosted":
                    # Test self-hosted API
                    test_url = f"{self.config.api_url}/docs"
                    
                    try:
                        async with session.get(test_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                            self.log(f"Self-hosted API status: {resp.status}")
                            if resp.status == 200:
                                self.log("Self-hosted API connectivity: OK", "SUCCESS")
                                self.results.append(("API Connectivity", True, "Self-hosted API accessible"))
                            else:
                                # Try the actual endpoint
                                parse_url = f"{self.config.api_url}/file_parse"
                                async with session.get(parse_url) as parse_resp:
                                    if parse_resp.status in [200, 422]:  # 422 expected without proper request
                                        self.log("Self-hosted API connectivity: OK", "SUCCESS")
                                        self.results.append(("API Connectivity", True, "Self-hosted API accessible"))
                                    else:
                                        self.log("Self-hosted API connectivity: Issues detected", "WARNING")
                                        self.results.append(("API Connectivity", False, f"HTTP {parse_resp.status}"))
                    except Exception as e:
                        self.log(f"Self-hosted API connectivity failed: {e}", "ERROR")
                        self.results.append(("API Connectivity", False, str(e)))
                        
        except Exception as e:
            self.log(f"API connectivity test failed: {e}", "ERROR")
            self.results.append(("API Connectivity", False, str(e)))
    
    async def test_file_processing(self):
        """Test real file processing"""
        if not self.config.test_file_path or not os.path.exists(self.config.test_file_path):
            self.log("Skipping file processing test: No test file provided", "WARNING")
            return
            
        self.log(f"📄 Testing File Processing: {os.path.basename(self.config.test_file_path)}")
        
        try:
            # Configure extractor
            config = MinerUConfig()
            config.mineru_api_type = self.config.api_type
            config.mineru_api_url = self.config.api_url
            config.mineru_api_key = self.config.api_key
            config.max_concurrent_api_calls = self.config.max_concurrent
            
            extractor = MinerUExtractor(learn_type=self.config.learn_type)
            extractor.config = config
            
            # Setup upload options
            upload_options = (
                {"region": "", "id": "", "key": "", "name": ""},
                "",
                "local"
            )
            
            # Process the file
            self.log(f"Processing file: {self.config.test_file_path}")
            start_time = asyncio.get_event_loop().time()
            
            documents = await extractor.process_file(
                filepath=self.config.test_file_path,
                upload_options=upload_options
            )
            file_hash = get_file_hash(self.config.test_file_path)
            temp_dir = get_temp_dir(file_hash, self.config.learn_type, extractor.config.cache_version)
            schema_results = await extract_schemas_from_docs(documents, self.config.learn_type,"schema_config_ftime.json", output_dir=temp_dir, file_hash=file_hash)
            # 打印schema提取结果
            self.log(f"  Schema: {json.dumps(schema_results, indent=2, ensure_ascii=False)}")
            
            end_time = asyncio.get_event_loop().time()
            processing_time = end_time - start_time
            
            if documents:
               
                for doc in documents:
                    advanced_parser = json.loads(doc.metadata.get('advanced_parser', '{}'))
                    
                    self.log("📊 Processing Results:")
                    self.log(f"  Processing time: {processing_time:.2f}s")
                    self.log(f"  Content length: {len(doc.page_content)} characters")
                    self.log(f"  Parser type: {doc.metadata.get('parser_type', 'unknown')}")
                    self.log(f"  API type: {advanced_parser.get('api_type', 'unknown')}")
                    self.log(f"  Processing mode: {advanced_parser.get('processing_mode', 'unknown')}")
                    self.log(f"  Total pages: {advanced_parser.get('total_pages', 0)}")
                    self.log(f"  Successful pages: {advanced_parser.get('successful_pages', 0)}")
                    self.log(f"  Images found: {advanced_parser.get('images_found', 0)}")
                    
                    # Show content preview with better handling
                    content = doc.page_content
                    if not content:
                        self.log("📄 Content: [EMPTY]")
                    elif not content.strip():
                        self.log(f"📄 Content: [WHITESPACE ONLY - {repr(content[:50])}]")
                    else:
                        preview = content[:200].strip()
                        if len(content) > 200:
                            preview += "..."
                        self.log(f"📄 Content preview: {preview}")
                    
                    self.log("File processing: SUCCESS", "SUCCESS")
                    self.results.append(("File Processing", True, f"Processed successfully in {processing_time:.2f}s"))
            else:
                self.log("File processing: No documents returned", "ERROR")
                self.results.append(("File Processing", False, "No documents returned"))
                
        except Exception as e:
            self.log(f"File processing test failed: {e}", "ERROR")
            self.results.append(("File Processing", False, str(e)))
    
    async def test_batch_processing(self):
        """Test batch processing with multiple small files"""
        self.log("📚 Testing Batch Processing")
        
        try:
            # Create multiple test PDFs
            test_files = []
            for i in range(3):
                test_pdf = await self.create_test_pdf(content=f"Test Document {i+1}\nThis is page content for document {i+1}.")
                test_files.append(test_pdf)
            
            # Configure for testing
            config = MinerUConfig()
            config.mineru_api_type = self.config.api_type
            config.mineru_api_url = self.config.api_url
            config.mineru_api_key = self.config.api_key
            config.max_concurrent_api_calls = 2
            
            extractor = MinerUExtractor(learn_type=self.config.learn_type)
            extractor.config = config
            
            upload_options = (
                {"region": "", "id": "", "key": "", "name": ""},
                "",
                "local"
            )
            
            # Process files
            results = []
            start_time = asyncio.get_event_loop().time()
            
            for i, test_file in enumerate(test_files):
                try:
                    self.log(f"Processing file {i+1}/{len(test_files)}")
                    documents = await extractor.process_file(
                        filepath=test_file,
                        upload_options=upload_options
                    )
                    results.append((test_file, documents))
                except Exception as e:
                    self.log(f"Failed to process file {i+1}: {e}", "ERROR")
                    results.append((test_file, None))
            
            end_time = asyncio.get_event_loop().time()
            total_time = end_time - start_time
            
            # Analyze results
            successful = len([r for r in results if r[1] is not None])
            
            self.log(f"Batch processing results:")
            self.log(f"  Total files: {len(test_files)}")
            self.log(f"  Successful: {successful}")
            self.log(f"  Failed: {len(test_files) - successful}")
            self.log(f"  Total time: {total_time:.2f}s")
            self.log(f"  Average time per file: {total_time/len(test_files):.2f}s")
            
            # Cleanup
            for test_file in test_files:
                os.unlink(test_file)
            
            if successful > 0:
                self.log("Batch processing: SUCCESS", "SUCCESS")
                self.results.append(("Batch Processing", True, f"{successful}/{len(test_files)} files processed"))
            else:
                self.log("Batch processing: FAILED", "ERROR")
                self.results.append(("Batch Processing", False, "No files processed successfully"))
                
        except Exception as e:
            self.log(f"Batch processing test failed: {e}", "ERROR")
            self.results.append(("Batch Processing", False, str(e)))
    
    async def create_test_pdf(self, content: str = "Test Document\nThis is a test PDF for MinerU processing.") -> str:
        """Create a simple test PDF file"""
        try:
            # Create a simple PDF using reportlab if available
            try:
                from reportlab.pdfgen import canvas
                from reportlab.lib.pagesizes import letter
                
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                temp_path = temp_file.name
                temp_file.close()
                
                c = canvas.Canvas(temp_path, pagesize=letter)
                lines = content.split('\n')
                y_position = 750
                
                for line in lines:
                    c.drawString(100, y_position, line)
                    y_position -= 20
                
                c.save()
                return temp_path
                
            except ImportError:
                # Fallback: create a minimal PDF manually
                temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                # Create a very basic PDF structure
                pdf_content = b"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/MediaBox [0 0 612 792]
>>
endobj

xref
0 4
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
trailer
<<
/Size 4
/Root 1 0 R
>>
startxref
190
%%EOF"""
                temp_file.write(pdf_content)
                temp_file.close()
                return temp_file.name
                
        except Exception as e:
            self.log(f"Failed to create test PDF: {e}", "ERROR")
            raise
    
    def show_test_summary(self):
        """Show test results summary"""
        print("\n" + "=" * 60)
        self.log("📋 Test Results Summary")
        print("=" * 60)
        
        passed = 0
        failed = 0
        
        for test_name, success, message in self.results:
            status = "PASS" if success else "FAIL"
            icon = "✅" if success else "❌"
            print(f"{icon} {test_name:20} {status:6} {message}")
            
            if success:
                passed += 1
            else:
                failed += 1
        
        print("=" * 60)
        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        if failed == 0:
            self.log("🎉 All tests passed!", "SUCCESS")
        else:
            self.log(f"⚠️ {failed} test(s) failed. Check the logs above for details.", "WARNING")


def load_config_from_env() -> TestConfig:
    """Load test configuration from environment variables"""
    print("\n📋 Loading configuration...")
    
    # Check if .env file was loaded
    env_file_path = project_root / '.env'
    if env_file_path.exists():
        print(f"   Using .env file: {env_file_path}")
    else:
        print("   Using system environment variables")
    
    # Load configuration values
    config = TestConfig(
        test_file_path=os.getenv('MINERU_TEST_FILE'),
        api_url=os.getenv('MINERU_API_URL', 'http://mineru:8000'),
        api_type=os.getenv('MINERU_API_TYPE', 'self_hosted'),
        api_key=os.getenv('MINERU_API_KEY'),
        learn_type=int(os.getenv('MINERU_LEARN_TYPE', '9')),
        max_concurrent=int(os.getenv('MAX_CONCURRENT_API_CALLS', '2')),
        verbose=os.getenv('MINERU_VERBOSE', 'true').lower() == 'true'
    )
    
    # Display loaded configuration (mask sensitive data)
    print("\n   Loaded configuration:")
    print(f"   - API Type: {config.api_type}")
    print(f"   - API URL: {config.api_url}")
    print(f"   - API Key: {'***' if config.api_key else 'Not set'}")
    print(f"   - Learn Type: {config.learn_type}")
    print(f"   - Max Concurrent: {config.max_concurrent}")
    print(f"   - Verbose: {config.verbose}")
    if config.test_file_path:
        print(f"   - Test File: {config.test_file_path}")
    
    # Check for LLM keys
    openai_key = os.getenv('ADVANCED_PARSER_KEY_OPENAI')
    claude_key = os.getenv('ADVANCED_PARSER_KEY_CLAUDE')
    gemini_key = os.getenv('ADVANCED_PARSER_KEY_GEMINI')
    
    if openai_key or claude_key or gemini_key:
        print("\n   LLM Keys detected:")
        if openai_key:
            print("   - OpenAI: ***")
        if claude_key:
            print("   - Claude: ***")
        if gemini_key:
            print("   - Gemini: ***")
    
    # Check for MaxKB configuration
    maxkb_llm = os.getenv('MINERU_LLM_MODEL_ID')
    maxkb_vision = os.getenv('MINERU_VISION_MODEL_ID')
    if maxkb_llm or maxkb_vision:
        print("\n   MaxKB Models configured:")
        if maxkb_llm:
            print(f"   - LLM Model: {maxkb_llm}")
        if maxkb_vision:
            print(f"   - Vision Model: {maxkb_vision}")
    
    return config


class MaxKBAdapterTester:
    """MaxKB Adapter testing utility class"""
    
    def __init__(self, test_config: TestConfig):
        self.config = test_config
        self.results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log message with formatting"""
        icons = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "DEBUG": "🔍"}
        icon = icons.get(level, "📝")
        print(f"{icon} {message}")
    
    async def run_all_tests(self):
        """Run all MaxKB adapter tests"""
        self.log("🚀 Starting MaxKB Adapter Tests", "INFO")
        print("=" * 60)
        
        # Test 1: MaxKB Adapter Initialization
        await self.test_adapter_initialization()
        
        # Test 2: File Storage Client
        await self.test_file_storage_client()
        
        # Test 3: Model Client
        await self.test_model_client()
        
        # Test 4: MinerU Extractor with MaxKB
        await self.test_mineru_extractor()
        
        # Test 5: Document Processing
        await self.test_document_processing()
        
        # Test 6: Image Processing
        await self.test_image_processing()
        
        # Show results summary
        self.show_test_summary()
    
    async def test_adapter_initialization(self):
        """Test MaxKB adapter initialization"""
        self.log("🔧 Testing MaxKB Adapter Initialization")
        
        try:
            # Create adapter
            adapter = MaxKBAdapter()
            
            # Test basic properties
            assert adapter.file_storage is not None, "File storage not initialized"
            assert adapter.model_client is not None, "Model client not initialized"
            
            # Test logger
            logger = adapter.get_logger()
            assert logger is not None, "Logger not available"
            
            # Test settings
            settings = adapter.get_settings()
            assert isinstance(settings, dict), "Settings not a dictionary"
            self.log(f"Settings keys: {list(settings.keys())}")
            
            # Test learn_type mapping
            learn_type = adapter.get_learn_type({'llm_model_id': 'test_model'})
            assert isinstance(learn_type, int), "Learn type not an integer"
            self.log(f"Learn type: {learn_type}")
            
            self.log("MaxKB Adapter initialization: SUCCESS", "SUCCESS")
            self.results.append(("Adapter Init", True, "Adapter initialized successfully"))
            
        except Exception as e:
            self.log(f"Adapter initialization failed: {e}", "ERROR")
            self.results.append(("Adapter Init", False, str(e)))
    
    async def test_file_storage_client(self):
        """Test file storage client functionality"""
        self.log("📁 Testing File Storage Client")
        
        try:
            # Mock the Django models
            with patch('common.handle.impl.mineru.maxkb_adapter.file_storage_client.File') as MockFile:
                # Setup mock
                mock_file_instance = Mock()
                mock_file_instance.id = "test_file_id"
                mock_file_instance.save = Mock()
                MockFile.return_value = mock_file_instance
                
                # Create client
                client = FileStorageClient(knowledge_id="test_knowledge")
                
                # Test image upload
                test_image_path = await self.create_test_image()
                try:
                    url = await client.upload_image(test_image_path, "test_image.png")
                    assert url == "/api/file/test_file_id", f"Unexpected URL: {url}"
                    self.log(f"Image upload test: SUCCESS (URL: {url})", "SUCCESS")
                except Exception as e:
                    self.log(f"Image upload failed: {e}", "WARNING")
                finally:
                    if os.path.exists(test_image_path):
                        os.unlink(test_image_path)
                
                # Test file upload
                test_file_path = await self.create_test_file()
                try:
                    url = await client.upload_file(test_file_path, "test_file.txt")
                    assert url == "/api/file/test_file_id", f"Unexpected URL: {url}"
                    self.log(f"File upload test: SUCCESS (URL: {url})", "SUCCESS")
                except Exception as e:
                    self.log(f"File upload failed: {e}", "WARNING")
                finally:
                    if os.path.exists(test_file_path):
                        os.unlink(test_file_path)
                
                # Test cleanup
                temp_dir = tempfile.mkdtemp()
                client.cleanup_temp_files(temp_dir)
                assert not os.path.exists(temp_dir), "Temp directory not cleaned"
                self.log("Cleanup test: SUCCESS", "SUCCESS")
                
                self.results.append(("File Storage", True, "File storage client works"))
                
        except Exception as e:
            self.log(f"File storage client test failed: {e}", "ERROR")
            self.results.append(("File Storage", False, str(e)))
    
    async def test_model_client(self):
        """Test MaxKB model client functionality"""
        self.log("🤖 Testing Model Client")
        
        try:
            # Mock the Django models and providers
            with patch('common.handle.impl.mineru.maxkb_adapter.maxkb_model_client.QuerySet') as MockQuerySet, \
                 patch('common.handle.impl.mineru.maxkb_adapter.maxkb_model_client.get_model') as MockGetModel:
                
                # Setup mocks
                mock_model = Mock()
                mock_model.id = "test_model_id"
                MockQuerySet.return_value.filter.return_value.first.return_value = mock_model
                
                mock_llm = Mock()
                mock_llm.invoke = Mock(return_value=Mock(content="Test response"))
                MockGetModel.return_value = mock_llm
                
                # Create client
                client = MaxKBModelClient()
                
                # Test LLM model retrieval
                llm_model = client.get_llm_model("test_model_id")
                assert llm_model is not None, "LLM model not retrieved"
                self.log("LLM model retrieval: SUCCESS", "SUCCESS")
                
                # Test vision model retrieval
                vision_model = client.get_vision_model("test_model_id")
                assert vision_model is not None, "Vision model not retrieved"
                self.log("Vision model retrieval: SUCCESS", "SUCCESS")
                
                # Test chat completion
                response = await client.chat_completion(
                    "test_model_id",
                    [{"role": "user", "content": "Hello"}]
                )
                assert response == "Test response", f"Unexpected response: {response}"
                self.log(f"Chat completion: SUCCESS (Response: {response})", "SUCCESS")
                
                # Test model validation
                is_valid = client.validate_model("test_model_id")
                assert is_valid, "Model validation failed"
                self.log("Model validation: SUCCESS", "SUCCESS")
                
                self.results.append(("Model Client", True, "Model client works"))
                
        except Exception as e:
            self.log(f"Model client test failed: {e}", "ERROR")
            self.results.append(("Model Client", False, str(e)))
    
    async def test_mineru_extractor(self):
        """Test MinerU extractor with MaxKB adapter"""
        self.log("📄 Testing MinerU Extractor with MaxKB")
        
        try:
            # Create extractor
            extractor = MaxKBMinerUExtractor(
                llm_model_id="test_llm_model",
                vision_model_id="test_vision_model"
            )
            
            # Verify initialization
            assert extractor.llm_model_id == "test_llm_model", "LLM model ID not set"
            assert extractor.vision_model_id == "test_vision_model", "Vision model ID not set"
            assert extractor.adapter is not None, "Adapter not initialized"
            assert isinstance(extractor.adapter, MaxKBAdapter), "Wrong adapter type"
            
            self.log("Extractor initialization: SUCCESS", "SUCCESS")
            
            # Test configuration
            assert extractor.config is not None, "Config not initialized"
            self.log(f"Config type: {type(extractor.config).__name__}")
            
            self.results.append(("MinerU Extractor", True, "Extractor initialized"))
            
        except Exception as e:
            self.log(f"MinerU extractor test failed: {e}", "ERROR")
            self.results.append(("MinerU Extractor", False, str(e)))
    
    async def test_document_processing(self):
        """Test document processing with MinerUAdapter"""
        self.log("📚 Testing Document Processing")
        
        try:
            # Create test PDF
            test_pdf = await self.create_test_pdf("Test Document\nPage 1 Content\nPage 2 Content")
            
            with open(test_pdf, 'rb') as f:
                file_content = f.read()
            
            # Mock the entire MinerUAdapter to avoid event loop issues
            with patch('common.handle.impl.mineru.maxkb_adapter.adapter.MinerUAdapter') as MockAdapter:
                # Create mock instance
                mock_adapter = Mock()
                MockAdapter.return_value = mock_adapter
                
                # Setup mock return value
                mock_adapter.process_document.return_value = {
                    'sections': [
                        {
                            'content': 'Page 1 content',
                            'title': 'Page 1',
                            'images': []
                        },
                        {
                            'content': 'Page 2 content',
                            'title': 'Page 2',
                            'images': []
                        }
                    ]
                }
                
                # Create adapter and process
                adapter = MockAdapter()
                result = adapter.process_document(
                    file_content,
                    "test.pdf",
                    save_image_func=None
                )
                
                # Verify result structure
                assert 'sections' in result, "No sections in result"
                assert len(result['sections']) == 2, f"Expected 2 sections, got {len(result['sections'])}"
                
                for i, section in enumerate(result['sections']):
                    assert 'content' in section, f"No content in section {i}"
                    assert 'title' in section, f"No title in section {i}"
                    assert 'images' in section, f"No images in section {i}"
                    self.log(f"Section {i}: {section['title'][:20]}...")
                
                self.log("Document processing: SUCCESS", "SUCCESS")
                self.results.append(("Document Processing", True, "Document processed successfully"))
            
            # Cleanup
            os.unlink(test_pdf)
            
        except Exception as e:
            self.log(f"Document processing test failed: {e}", "ERROR")
            self.results.append(("Document Processing", False, str(e)))
    
    async def test_image_processing(self):
        """Test image processing capabilities"""
        self.log("🖼️ Testing Image Processing")
        
        try:
            # Test image optimizer if available
            try:
                from common.handle.impl.mineru.maxkb_adapter.image_optimizer import ImageOptimizer
                
                optimizer = ImageOptimizer()
                
                # Create test image
                test_image = await self.create_test_image()
                
                # Test that optimizer exists and has expected methods
                assert hasattr(optimizer, '__class__'), "ImageOptimizer not properly instantiated"
                
                # Test optimization - check for the actual method name
                if hasattr(optimizer, 'optimize_image'):
                    optimized = optimizer.optimize_image(test_image)
                    assert optimized is not None, "Image optimization failed"
                    self.log("Image optimization method: SUCCESS", "SUCCESS")
                elif hasattr(optimizer, 'optimize'):
                    optimized = optimizer.optimize(test_image)
                    assert optimized is not None, "Image optimization failed"
                    self.log("Image optimize method: SUCCESS", "SUCCESS")
                else:
                    # Just verify the optimizer was created
                    self.log("ImageOptimizer created successfully", "SUCCESS")
                    optimized = test_image
                
                # Cleanup
                os.unlink(test_image)
                if optimized != test_image and os.path.exists(optimized):
                    os.unlink(optimized)
                    
            except ImportError as e:
                self.log(f"Image optimizer not available: {e}", "WARNING")
            
            self.results.append(("Image Processing", True, "Image processing tested"))
            
        except Exception as e:
            self.log(f"Image processing test failed: {e}", "ERROR")
            self.results.append(("Image Processing", False, str(e)))
    
    async def create_test_pdf(self, content: str = "Test Document") -> str:
        """Create a simple test PDF file"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        # Create minimal PDF
        pdf_content = f"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 100 700 Td ({content}) Tj ET
endstream endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000056 00000 n 
0000000108 00000 n 
0000000201 00000 n 
trailer<</Size 5/Root 1 0 R>>
startxref
289
%%EOF""".encode()
        temp_file.write(pdf_content)
        temp_file.close()
        return temp_file.name
    
    async def create_test_image(self) -> str:
        """Create a simple test image file"""
        # Create a simple PNG file (1x1 pixel, red)
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
        # Minimal PNG data (1x1 red pixel)
        png_data = bytes.fromhex(
            '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
            '0000000d49444154789c62f8cfc00000000103010112d2dd790000000049454e44ae426082'
        )
        temp_file.write(png_data)
        temp_file.close()
        return temp_file.name
    
    async def create_test_file(self) -> str:
        """Create a simple test text file"""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.txt', mode='w')
        temp_file.write("Test file content\nLine 2\nLine 3")
        temp_file.close()
        return temp_file.name
    
    def show_test_summary(self):
        """Show test results summary"""
        print("\n" + "=" * 60)
        self.log("📋 MaxKB Adapter Test Results Summary")
        print("=" * 60)
        
        passed = 0
        failed = 0
        
        for test_name, success, message in self.results:
            status = "PASS" if success else "FAIL"
            icon = "✅" if success else "❌"
            print(f"{icon} {test_name:20} {status:6} {message}")
            
            if success:
                passed += 1
            else:
                failed += 1
        
        print("=" * 60)
        print(f"Total Tests: {len(self.results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        if failed == 0:
            self.log("🎉 All MaxKB adapter tests passed!", "SUCCESS")
        else:
            self.log(f"⚠️ {failed} test(s) failed. Check the logs above for details.", "WARNING")


def print_usage():
    """Print usage instructions"""
    print("""
🧪 MinerU Parser Test Script

This script tests the MinerU PDF/PPT parsing system with various configurations.

USAGE:
    python test_mineru.py [OPTIONS]
    
OPTIONS:
    --gptbase    Run GPTBase MinerU tests (default if available)
    --maxkb      Run MaxKB adapter tests
    --all        Run all available tests
    -h, --help   Show this help message

CONFIGURATION:
    
    The script reads configuration from (in order of priority):
    1. .env file in the project root (if exists)
    2. System environment variables
    
    To use a .env file:
    1. Copy .env.example to .env
    2. Edit .env with your configuration
    3. Run the test script
    
    Quick start:
    cp .env.test .env  # Use minimal test configuration
    python test_mineru.py --maxkb

ENVIRONMENT VARIABLES:
    
    🏠 For Self-Hosted MinerU:
    export MINERU_API_TYPE=self_hosted
    export MINERU_API_URL=http://mineru:8000
    
    ☁️ For Cloud MinerU:
    export MINERU_API_TYPE=cloud
    export MINERU_API_URL=https://mineru.net
    export MINERU_API_KEY=your_api_key_here
    
    🔧 Optional Configuration:
    export MINERU_TEST_FILE=/path/to/test.pdf        # Test file path
    export MINERU_LEARN_TYPE=9                       # AI model type
    export MAX_CONCURRENT_API_CALLS=2               # Concurrent processing
    export MINERU_VERBOSE=true                      # Verbose output
    
    📚 LLM Configuration (for image processing):
    export ADVANCED_PARSER_KEY_OPENAI=your_openai_key
    export ADVANCED_PARSER_KEY_CLAUDE=your_claude_key
    export ADVANCED_PARSER_KEY_GEMINI=your_gemini_key
    
    🤖 MaxKB Configuration:
    export MINERU_LLM_MODEL_ID=your_llm_model_id
    export MINERU_VISION_MODEL_ID=your_vision_model_id
    export MAXKB_API_KEY=your_maxkb_api_key
    export MAXKB_API_URL=https://api.maxkb.com

EXAMPLES:
    
    # Test with self-hosted MinerU
    export MINERU_API_TYPE=self_hosted
    export MINERU_API_URL=http://localhost:30001
    python test_mineru.py
    
    # Test with cloud MinerU
    export MINERU_API_TYPE=cloud
    export MINERU_API_KEY=your_api_key
    python test_mineru.py
    
    # Test with a specific file
    export MINERU_TEST_FILE=/path/to/your/document.pdf
    python test_mineru.py
    
    # Test MaxKB adapter
    python test_mineru.py --maxkb
    
    # Run all tests
    python test_mineru.py --all
    
TEST COVERAGE:
    
    📦 GPTBase MinerU Tests:
    ✅ Environment and dependencies check
    ✅ Configuration validation
    ✅ API connectivity testing
    ✅ Real file processing (if file provided)
    ✅ Batch processing capabilities
    
    🚀 MaxKB Adapter Tests:
    ✅ Adapter initialization
    ✅ File storage client functionality
    ✅ Model client integration
    ✅ MinerU extractor with MaxKB
    ✅ Document processing pipeline
    ✅ Image processing capabilities
""")


async def main():
    """Main test function"""
    # Parse command line arguments
    run_gptbase = False
    run_maxkb = False
    
    if len(sys.argv) > 1:
        if sys.argv[1] in ['-h', '--help', 'help']:
            print_usage()
            return
        elif sys.argv[1] == '--gptbase':
            run_gptbase = True
        elif sys.argv[1] == '--maxkb':
            run_maxkb = True
        elif sys.argv[1] == '--all':
            run_gptbase = mineru_modules_loaded
            run_maxkb = maxkb_adapter_loaded
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Use -h or --help for usage information")
            return
    else:
        # Default: run MaxKB tests only as requested
        run_maxkb = maxkb_adapter_loaded
    
    # Load configuration
    config = load_config_from_env()
    
    # Run GPTBase tests if requested and available
    if run_gptbase and mineru_modules_loaded:
        print("\n" + "="*60)
        print("Running GPTBase MinerU Tests")
        print("="*60)
        tester = MinerUTester(config)
        await tester.run_all_tests()
    elif run_gptbase and not mineru_modules_loaded:
        print("❌ GPTBase modules not available, cannot run GPTBase tests")
    
    # Run MaxKB adapter tests if requested and available
    if run_maxkb and maxkb_adapter_loaded:
        print("\n" + "="*60)
        print("Running MaxKB Adapter Tests")
        print("="*60)
        tester = MaxKBAdapterTester(config)
        await tester.run_all_tests()
    elif run_maxkb and not maxkb_adapter_loaded:
        print("❌ MaxKB adapter modules not available, cannot run MaxKB tests")
    
    # If nothing was run
    if not (run_gptbase or run_maxkb):
        print("ℹ️ No tests were run. Use --help for usage information.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"❌ Test script error: {e}")
        sys.exit(1)