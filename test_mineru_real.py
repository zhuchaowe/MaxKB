#!/usr/bin/env python3
"""
MinerU Real File Processing Test

This script tests actual MinerU file processing with the MaxKB adapter.
It uses real files and real API calls (no mocking).
"""

import asyncio
import os
import sys
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any

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
    env_path = project_root / '.env'
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print(f"✅ Loaded environment variables from {env_path}")
except ImportError:
    print("ℹ️ python-dotenv not installed. Using system environment variables only.")

# Setup Django environment if we're in MaxKB
try:
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'maxkb.settings')
    django.setup()
    print("✅ Django environment initialized")
except ImportError:
    print("ℹ️ Django not available - running in standalone mode")
except Exception as e:
    print(f"ℹ️ Could not initialize Django: {e}")


class MinerURealTester:
    """Real MinerU file processing tester"""
    
    def __init__(self):
        self.test_file = os.getenv('MINERU_TEST_FILE')
        self.api_url = os.getenv('MINERU_API_URL', 'http://mineru:8000')
        self.api_type = os.getenv('MINERU_API_TYPE', 'self_hosted')
        self.api_key = os.getenv('MINERU_API_KEY')
        
    def log(self, message: str, level: str = "INFO"):
        """Log message with formatting"""
        icons = {"INFO": "ℹ️", "SUCCESS": "✅", "WARNING": "⚠️", "ERROR": "❌", "DEBUG": "🔍"}
        icon = icons.get(level, "📝")
        timestamp = time.strftime("%H:%M:%S")
        print(f"[{timestamp}] {icon} {message}")
    
    async def test_real_file_processing(self):
        """Test real file processing with MinerU"""
        if not self.test_file:
            self.log("No test file specified. Set MINERU_TEST_FILE environment variable.", "ERROR")
            return False
        
        if not os.path.exists(self.test_file):
            self.log(f"Test file not found: {self.test_file}", "ERROR")
            return False
        
        self.log(f"Testing with file: {self.test_file}", "INFO")
        self.log(f"MinerU API: {self.api_url} ({self.api_type})", "INFO")
        
        try:
            # Import MaxKB MinerU adapter
            from common.handle.impl.mineru.maxkb_adapter.adapter import MinerUExtractor
            from common.handle.impl.mineru.maxkb_adapter.config_maxkb import MaxKBMinerUConfig
            
            # Create configuration
            config = MaxKBMinerUConfig()
            config.mineru_api_type = self.api_type
            config.mineru_api_url = self.api_url
            config.mineru_api_key = self.api_key
            config.enable_cache = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
            
            self.log("Configuration created", "SUCCESS")
            self.log(f"  - API Type: {config.mineru_api_type}", "DEBUG")
            self.log(f"  - API URL: {config.mineru_api_url}", "DEBUG")
            self.log(f"  - Cache Enabled: {config.enable_cache}", "DEBUG")
            
            # Create extractor
            llm_model_id = os.getenv('MINERU_LLM_MODEL_ID')
            vision_model_id = os.getenv('MINERU_VISION_MODEL_ID')
            
            extractor = MinerUExtractor(
                llm_model_id=llm_model_id,
                vision_model_id=vision_model_id
            )
            extractor.config = config
            
            self.log("MinerU extractor created", "SUCCESS")
            if llm_model_id:
                self.log(f"  - LLM Model: {llm_model_id}", "DEBUG")
            if vision_model_id:
                self.log(f"  - Vision Model: {vision_model_id}", "DEBUG")
            
            # Process the file
            self.log("Starting file processing...", "INFO")
            start_time = time.time()
            
            # Call the actual processing method
            result = await extractor.process_file(
                filepath=self.test_file,
                src_name=os.path.basename(self.test_file),
                upload_options=None  # Will use test mode for uploads
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            self.log(f"Processing completed in {processing_time:.2f} seconds", "SUCCESS")
            
            # Analyze results
            if result:
                self.log("Processing results:", "INFO")
                
                if isinstance(result, list):
                    self.log(f"  - Document count: {len(result)}", "INFO")
                    
                    total_content_length = 0
                    total_images = 0
                    
                    for i, doc in enumerate(result):
                        if hasattr(doc, 'page_content'):
                            content = doc.page_content
                            total_content_length += len(content)
                            
                            # Show content preview
                            preview = content[:200].strip() if content else "[EMPTY]"
                            if len(content) > 200:
                                preview += "..."
                            self.log(f"  - Document {i+1} preview: {preview}", "DEBUG")
                        
                        if hasattr(doc, 'metadata'):
                            metadata = doc.metadata
                            if isinstance(metadata, dict):
                                # Check for images
                                images = metadata.get('images', [])
                                if images:
                                    total_images += len(images)
                                    self.log(f"  - Document {i+1} has {len(images)} images", "INFO")
                                
                                # Check for advanced parser info
                                advanced = metadata.get('advanced_parser')
                                if advanced:
                                    try:
                                        advanced_info = json.loads(advanced) if isinstance(advanced, str) else advanced
                                        if isinstance(advanced_info, dict):
                                            self.log(f"  - Document {i+1} parser info:", "DEBUG")
                                            self.log(f"    - API Type: {advanced_info.get('api_type', 'unknown')}", "DEBUG")
                                            self.log(f"    - Total Pages: {advanced_info.get('total_pages', 0)}", "DEBUG")
                                            self.log(f"    - Successful Pages: {advanced_info.get('successful_pages', 0)}", "DEBUG")
                                    except:
                                        pass
                    
                    self.log(f"  - Total content length: {total_content_length} characters", "INFO")
                    self.log(f"  - Total images found: {total_images}", "INFO")
                    
                elif isinstance(result, dict):
                    self.log(f"  - Result type: dictionary", "INFO")
                    if 'content' in result:
                        content = result['content']
                        if isinstance(content, str):
                            self.log(f"  - Content length: {len(content)} characters", "INFO")
                            preview = content[:200].strip() if content else "[EMPTY]"
                            if len(content) > 200:
                                preview += "..."
                            self.log(f"  - Content preview: {preview}", "DEBUG")
                        elif isinstance(content, list):
                            self.log(f"  - Content items: {len(content)}", "INFO")
                    
                    if 'images' in result:
                        images = result['images']
                        self.log(f"  - Images found: {len(images)}", "INFO")
                        for img_path in images[:5]:  # Show first 5 images
                            self.log(f"    - {img_path}", "DEBUG")
                
                else:
                    self.log(f"  - Result type: {type(result).__name__}", "INFO")
                
                self.log("✅ File processing test PASSED", "SUCCESS")
                return True
                
            else:
                self.log("No result returned from processing", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"File processing failed: {str(e)}", "ERROR")
            import traceback
            self.log(f"Traceback:\n{traceback.format_exc()}", "DEBUG")
            return False
    
    async def test_mineru_adapter(self):
        """Test MinerUAdapter for document processing"""
        if not self.test_file:
            self.log("No test file specified. Set MINERU_TEST_FILE environment variable.", "ERROR")
            return False
        
        if not os.path.exists(self.test_file):
            self.log(f"Test file not found: {self.test_file}", "ERROR")
            return False
        
        self.log(f"Testing MinerUAdapter with file: {self.test_file}", "INFO")
        
        try:
            from common.handle.impl.mineru.maxkb_adapter.adapter import MinerUAdapter
            
            # Create adapter
            adapter = MinerUAdapter()
            self.log("MinerUAdapter created", "SUCCESS")
            
            # Read file content
            with open(self.test_file, 'rb') as f:
                file_content = f.read()
            
            self.log(f"File size: {len(file_content)} bytes", "INFO")
            
            # Process document
            self.log("Processing document...", "INFO")
            start_time = time.time()
            
            result = adapter.process_document(
                file_content=file_content,
                file_name=os.path.basename(self.test_file),
                save_image_func=None  # Test mode - no image saving
            )
            
            end_time = time.time()
            processing_time = end_time - start_time
            
            self.log(f"Processing completed in {processing_time:.2f} seconds", "SUCCESS")
            
            # Analyze results
            if result and 'sections' in result:
                sections = result['sections']
                self.log(f"Sections extracted: {len(sections)}", "INFO")
                
                total_content = 0
                total_images = 0
                
                for i, section in enumerate(sections[:5]):  # Show first 5 sections
                    content = section.get('content', '')
                    title = section.get('title', '')
                    images = section.get('images', [])
                    
                    total_content += len(content)
                    total_images += len(images)
                    
                    self.log(f"  Section {i+1}:", "INFO")
                    if title:
                        self.log(f"    - Title: {title}", "DEBUG")
                    self.log(f"    - Content length: {len(content)} chars", "DEBUG")
                    if images:
                        self.log(f"    - Images: {len(images)}", "DEBUG")
                    
                    # Show content preview
                    if content:
                        preview = content[:100].strip()
                        if len(content) > 100:
                            preview += "..."
                        self.log(f"    - Preview: {preview}", "DEBUG")
                
                self.log(f"Total content extracted: {total_content} characters", "INFO")
                self.log(f"Total images found: {total_images}", "INFO")
                
                self.log("✅ MinerUAdapter test PASSED", "SUCCESS")
                return True
            else:
                self.log("No sections returned from processing", "ERROR")
                return False
                
        except Exception as e:
            self.log(f"MinerUAdapter test failed: {str(e)}", "ERROR")
            import traceback
            self.log(f"Traceback:\n{traceback.format_exc()}", "DEBUG")
            return False


async def main():
    """Main test function"""
    print("\n" + "=" * 60)
    print("🚀 MinerU Real File Processing Test")
    print("=" * 60)
    
    # Check if test file is specified
    test_file = os.getenv('MINERU_TEST_FILE')
    if not test_file:
        print("\n❌ Error: MINERU_TEST_FILE environment variable not set")
        print("\nUsage:")
        print("  export MINERU_TEST_FILE=/path/to/your/test.pdf")
        print("  python test_mineru_real.py")
        print("\nOr:")
        print("  MINERU_TEST_FILE=/path/to/your/test.pdf python test_mineru_real.py")
        return 1
    
    # Create tester
    tester = MinerURealTester()
    
    # Run tests
    print("\n" + "=" * 60)
    print("Test 1: MinerU Extractor (Direct Processing)")
    print("=" * 60)
    
    test1_passed = await tester.test_real_file_processing()
    
    print("\n" + "=" * 60)
    print("Test 2: MinerU Adapter (MaxKB Integration)")
    print("=" * 60)
    
    test2_passed = await tester.test_mineru_adapter()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    
    tests = [
        ("MinerU Extractor", test1_passed),
        ("MinerU Adapter", test2_passed)
    ]
    
    for test_name, passed in tests:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} {test_name}")
    
    passed_count = sum(1 for _, p in tests if p)
    total_count = len(tests)
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 All tests passed successfully!")
        return 0
    else:
        print(f"\n⚠️ {total_count - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Test script error: {e}")
        import traceback
        print(traceback.format_exc())
        sys.exit(1)