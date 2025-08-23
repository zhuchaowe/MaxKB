#!/usr/bin/env python3
"""
MaxKB Adapter Import and Basic Functionality Test

This script specifically tests the MaxKB adapter imports and basic functionality.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# For MaxKB, also add the apps directory to the path
apps_path = project_root / 'apps'
if apps_path.exists():
    sys.path.insert(0, str(apps_path))
    print(f"✅ Added apps directory to Python path: {apps_path}")

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

def test_imports():
    """Test MaxKB adapter imports"""
    print("=" * 60)
    print("🔍 Testing MaxKB Adapter Imports")
    print("=" * 60)
    
    results = []
    
    # Test 1: Import main adapter module
    print("\n1. Testing main adapter import...")
    try:
        from common.handle.impl.mineru.maxkb_adapter import adapter
        print("   ✅ Successfully imported adapter module")
        results.append(("adapter module", True))
        
        # Check for required classes
        assert hasattr(adapter, 'MaxKBAdapter'), "MaxKBAdapter class not found"
        print("   ✅ MaxKBAdapter class found")
        
        assert hasattr(adapter, 'MinerUExtractor'), "MinerUExtractor class not found"
        print("   ✅ MinerUExtractor class found")
        
        assert hasattr(adapter, 'MinerUAdapter'), "MinerUAdapter class not found"
        print("   ✅ MinerUAdapter class found")
        
    except ImportError as e:
        print(f"   ❌ Failed to import adapter: {e}")
        results.append(("adapter module", False))
    except AssertionError as e:
        print(f"   ❌ Assertion failed: {e}")
        results.append(("adapter module", False))
    
    # Test 2: Import file storage client
    print("\n2. Testing file storage client import...")
    try:
        from common.handle.impl.mineru.maxkb_adapter import file_storage_client
        print("   ✅ Successfully imported file_storage_client module")
        
        assert hasattr(file_storage_client, 'FileStorageClient'), "FileStorageClient class not found"
        print("   ✅ FileStorageClient class found")
        results.append(("file_storage_client", True))
        
    except ImportError as e:
        print(f"   ❌ Failed to import file_storage_client: {e}")
        results.append(("file_storage_client", False))
    except AssertionError as e:
        print(f"   ❌ Assertion failed: {e}")
        results.append(("file_storage_client", False))
    
    # Test 3: Import model client
    print("\n3. Testing model client import...")
    try:
        from common.handle.impl.mineru.maxkb_adapter import maxkb_model_client
        print("   ✅ Successfully imported maxkb_model_client module")
        
        assert hasattr(maxkb_model_client, 'MaxKBModelClient'), "MaxKBModelClient class not found"
        print("   ✅ MaxKBModelClient class found")
        
        assert hasattr(maxkb_model_client, 'maxkb_model_client'), "maxkb_model_client instance not found"
        print("   ✅ maxkb_model_client instance found")
        results.append(("maxkb_model_client", True))
        
    except ImportError as e:
        print(f"   ❌ Failed to import maxkb_model_client: {e}")
        results.append(("maxkb_model_client", False))
    except AssertionError as e:
        print(f"   ❌ Assertion failed: {e}")
        results.append(("maxkb_model_client", False))
    
    # Test 4: Import configuration
    print("\n4. Testing configuration import...")
    try:
        from common.handle.impl.mineru.maxkb_adapter import config_maxkb
        print("   ✅ Successfully imported config_maxkb module")
        
        assert hasattr(config_maxkb, 'MaxKBMinerUConfig'), "MaxKBMinerUConfig class not found"
        print("   ✅ MaxKBMinerUConfig class found")
        results.append(("config_maxkb", True))
        
    except ImportError as e:
        print(f"   ❌ Failed to import config_maxkb: {e}")
        results.append(("config_maxkb", False))
    except AssertionError as e:
        print(f"   ❌ Assertion failed: {e}")
        results.append(("config_maxkb", False))
    
    # Test 5: Import logger
    print("\n5. Testing logger import...")
    try:
        from common.handle.impl.mineru.maxkb_adapter import logger
        print("   ✅ Successfully imported logger module")
        results.append(("logger", True))
        
    except ImportError as e:
        print(f"   ❌ Failed to import logger: {e}")
        results.append(("logger", False))
    
    # Test 6: Import base parser (parent module)
    print("\n6. Testing base parser import...")
    try:
        from common.handle.impl.mineru import base_parser
        print("   ✅ Successfully imported base_parser module")
        
        assert hasattr(base_parser, 'PlatformAdapter'), "PlatformAdapter class not found"
        print("   ✅ PlatformAdapter class found")
        
        assert hasattr(base_parser, 'BaseMinerUExtractor'), "BaseMinerUExtractor class not found"
        print("   ✅ BaseMinerUExtractor class found")
        results.append(("base_parser", True))
        
    except ImportError as e:
        print(f"   ❌ Failed to import base_parser: {e}")
        results.append(("base_parser", False))
    except AssertionError as e:
        print(f"   ❌ Assertion failed: {e}")
        results.append(("base_parser", False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 Import Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    for module_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status:10} {module_name}")
    
    print("-" * 60)
    print(f"Total: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All import tests passed!")
    else:
        print(f"\n⚠️ {failed} import test(s) failed")
    
    return failed == 0

def test_basic_instantiation():
    """Test basic instantiation of MaxKB adapter classes"""
    print("\n" + "=" * 60)
    print("🔧 Testing Basic Instantiation")
    print("=" * 60)
    
    results = []
    
    # Test 1: Instantiate MaxKBAdapter
    print("\n1. Testing MaxKBAdapter instantiation...")
    try:
        from common.handle.impl.mineru.maxkb_adapter.adapter import MaxKBAdapter
        
        adapter = MaxKBAdapter()
        assert adapter is not None, "Adapter is None"
        assert adapter.file_storage is not None, "File storage not initialized"
        assert adapter.model_client is not None, "Model client not initialized"
        
        print("   ✅ MaxKBAdapter instantiated successfully")
        results.append(("MaxKBAdapter", True))
        
    except Exception as e:
        print(f"   ❌ Failed to instantiate MaxKBAdapter: {e}")
        results.append(("MaxKBAdapter", False))
    
    # Test 2: Instantiate MinerUExtractor
    print("\n2. Testing MinerUExtractor instantiation...")
    try:
        from common.handle.impl.mineru.maxkb_adapter.adapter import MinerUExtractor
        
        extractor = MinerUExtractor(
            llm_model_id="test_model",
            vision_model_id="test_vision"
        )
        assert extractor is not None, "Extractor is None"
        assert extractor.llm_model_id == "test_model", "LLM model ID not set correctly"
        assert extractor.vision_model_id == "test_vision", "Vision model ID not set correctly"
        
        print("   ✅ MinerUExtractor instantiated successfully")
        results.append(("MinerUExtractor", True))
        
    except Exception as e:
        print(f"   ❌ Failed to instantiate MinerUExtractor: {e}")
        results.append(("MinerUExtractor", False))
    
    # Test 3: Instantiate MinerUAdapter (with mocked init)
    print("\n3. Testing MinerUAdapter instantiation...")
    try:
        from common.handle.impl.mineru.maxkb_adapter.adapter import MinerUAdapter
        from unittest.mock import patch
        
        with patch.object(MinerUAdapter, '_init_extractor'):
            adapter = MinerUAdapter()
            assert adapter is not None, "Adapter is None"
            
            print("   ✅ MinerUAdapter instantiated successfully")
            results.append(("MinerUAdapter", True))
        
    except Exception as e:
        print(f"   ❌ Failed to instantiate MinerUAdapter: {e}")
        results.append(("MinerUAdapter", False))
    
    # Print summary
    print("\n" + "=" * 60)
    print("📊 Instantiation Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, success in results if success)
    failed = len(results) - passed
    
    for class_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status:10} {class_name}")
    
    print("-" * 60)
    print(f"Total: {len(results)} tests")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All instantiation tests passed!")
    else:
        print(f"\n⚠️ {failed} instantiation test(s) failed")
    
    return failed == 0

def main():
    """Main test function"""
    print("\n" + "🚀 MaxKB Adapter Test Suite" + "\n")
    
    # Run import tests
    import_success = test_imports()
    
    # Run instantiation tests only if imports succeeded
    if import_success:
        instantiation_success = test_basic_instantiation()
    else:
        print("\n⚠️ Skipping instantiation tests due to import failures")
        instantiation_success = False
    
    # Final summary
    print("\n" + "=" * 60)
    print("🏁 Final Test Results")
    print("=" * 60)
    
    if import_success and instantiation_success:
        print("✅ All tests passed successfully!")
        print("\nThe MaxKB adapter is properly configured and ready to use.")
        return 0
    else:
        print("❌ Some tests failed.")
        print("\nPlease review the errors above and ensure all dependencies are installed.")
        return 1

if __name__ == "__main__":
    sys.exit(main())