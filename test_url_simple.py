#!/usr/bin/env python3
"""
简单测试URL生成逻辑
"""

import os
import tempfile
import shutil
import uuid

# 设置环境变量
os.environ['MAXKB_BASE_URL'] = 'http://xbase.aitravelmaster.com'

def test_url_generation():
    """模拟adapter.py中的upload_file逻辑"""
    
    # 创建测试文件
    with tempfile.NamedTemporaryFile(mode='w', suffix='.pdf', delete=False) as f:
        f.write('test')
        file_path = f.name
    
    try:
        # 模拟upload_file的逻辑
        storage_path = '/tmp/storage'  # 模拟存储路径
        
        # 创建存储目录
        sub_dir = 'mineru'
        storage_dir = os.path.join(storage_path, sub_dir, 'images')
        os.makedirs(storage_dir, exist_ok=True)
        
        # 生成文件名
        file_ext = os.path.splitext(file_path)[1]
        file_name = f"{uuid.uuid4().hex}{file_ext}"
        dest_path = os.path.join(storage_dir, file_name)
        
        # 复制文件
        shutil.copy2(file_path, dest_path)
        
        # 生成URL（这是关键部分）
        relative_path = os.path.relpath(dest_path, storage_path)
        relative_path = relative_path.replace(os.path.sep, '/')
        
        # 检查环境变量
        base_url = os.getenv('MAXKB_BASE_URL', '')
        print(f"MAXKB_BASE_URL from env: '{base_url}'")
        print(f"Relative path: {relative_path}")
        
        if base_url:
            result_url = f"{base_url.rstrip('/')}/storage/{relative_path}"
            print(f"✅ Generated full URL: {result_url}")
        else:
            result_url = f"/storage/{relative_path}"
            print(f"⚠️ Generated relative URL: {result_url}")
        
        # 验证URL格式
        if result_url.startswith(('http://', 'https://')):
            print("✅ URL is valid for Cloud API")
        else:
            print("❌ URL is NOT valid for Cloud API (must start with http:// or https://)")
            
        return result_url
        
    finally:
        # 清理
        if os.path.exists(file_path):
            os.unlink(file_path)
        # 清理存储目录
        if os.path.exists('/tmp/storage'):
            shutil.rmtree('/tmp/storage')

if __name__ == "__main__":
    print("=" * 60)
    print("Testing URL Generation Logic")
    print("=" * 60)
    print()
    
    # 测试1：有MAXKB_BASE_URL
    print("Test 1: With MAXKB_BASE_URL set")
    print("-" * 40)
    url1 = test_url_generation()
    
    print("\n" + "=" * 60)
    
    # 测试2：没有MAXKB_BASE_URL
    print("\nTest 2: Without MAXKB_BASE_URL")
    print("-" * 40)
    os.environ['MAXKB_BASE_URL'] = ''
    url2 = test_url_generation()
    
    print("\n" + "=" * 60)
    print("Summary:")
    print(f"With MAXKB_BASE_URL: {url1}")
    print(f"Without MAXKB_BASE_URL: {url2}")
    print("=" * 60)