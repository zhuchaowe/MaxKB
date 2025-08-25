#!/usr/bin/env python3
"""
测试URL修复 - 验证platform_adapter是否正确传递
"""

import os
import sys
import asyncio
from pathlib import Path

# Add paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
apps_path = project_root / 'apps'
if apps_path.exists():
    sys.path.insert(0, str(apps_path))

# Set environment variables for testing
os.environ['MAXKB_BASE_URL'] = 'http://xbase.aitravelmaster.com'
os.environ['MINERU_API_TYPE'] = 'cloud'  # Force cloud mode for testing

async def test_url_generation():
    """Test that URLs are generated correctly"""
    
    # Import after setting environment
    from apps.common.handle.impl.mineru.maxkb_adapter.adapter import MaxKBAdapter
    
    # Create adapter
    adapter = MaxKBAdapter()
    
    # Create a test file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
        f.write('test')
        test_file = f.name
    
    try:
        # Test upload_file
        print("Testing MaxKBAdapter.upload_file()...")
        url = await adapter.upload_file(test_file, ['test_knowledge_id'])
        
        print(f"\n✅ Generated URL: {url}")
        
        # Verify URL format
        if url.startswith('http://') or url.startswith('https://'):
            print("✅ URL is properly formatted for Cloud API")
        else:
            print(f"❌ URL is not valid for Cloud API: {url}")
            
        # Check if MAXKB_BASE_URL is used
        base_url = os.environ.get('MAXKB_BASE_URL', '')
        if base_url and url.startswith(base_url):
            print(f"✅ URL correctly uses MAXKB_BASE_URL: {base_url}")
        else:
            print(f"❌ URL does not use MAXKB_BASE_URL")
            
    finally:
        # Clean up
        if os.path.exists(test_file):
            os.unlink(test_file)

async def test_api_client_with_adapter():
    """Test that MinerUAPIClient receives platform_adapter correctly"""
    
    from apps.common.handle.impl.mineru.api_client import MinerUAPIClient
    from apps.common.handle.impl.mineru.maxkb_adapter.adapter import MaxKBAdapter
    from apps.common.handle.impl.mineru.maxkb_adapter.config_maxkb import MaxKBMinerUConfig
    
    print("\nTesting MinerUAPIClient with platform_adapter...")
    
    # Create components
    adapter = MaxKBAdapter()
    config = MaxKBMinerUConfig()
    
    # Create API client with adapter
    api_client = MinerUAPIClient(config, adapter)
    
    # Check if adapter is set
    if api_client.platform_adapter is not None:
        print("✅ platform_adapter is correctly set in MinerUAPIClient")
    else:
        print("❌ platform_adapter is None in MinerUAPIClient")
    
    # Test _upload_file_to_accessible_url
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
        f.write('test')
        test_file = f.name
    
    try:
        # Test upload through API client
        async with api_client:
            url = await api_client._upload_file_to_accessible_url(test_file, 'test_src_id')
            print(f"✅ URL from _upload_file_to_accessible_url: {url}")
            
            if url.startswith('http://') or url.startswith('https://'):
                print("✅ API client generates valid URL for Cloud API")
            else:
                print(f"❌ API client generates invalid URL: {url}")
                
    finally:
        if os.path.exists(test_file):
            os.unlink(test_file)

if __name__ == "__main__":
    print("=" * 60)
    print("Testing MinerU Cloud API URL Fix")
    print("=" * 60)
    
    # Check environment
    print("\nEnvironment:")
    print(f"MAXKB_BASE_URL: {os.environ.get('MAXKB_BASE_URL', 'NOT SET')}")
    print(f"MINERU_API_TYPE: {os.environ.get('MINERU_API_TYPE', 'NOT SET')}")
    
    # Run tests
    asyncio.run(test_url_generation())
    asyncio.run(test_api_client_with_adapter())
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)