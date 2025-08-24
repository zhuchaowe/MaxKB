#!/usr/bin/env python
"""
测试MinerU图片存储和访问功能

使用方法：
1. 在本地开发环境：python test_storage.py
2. 在Docker环境：docker exec -it maxkb-dev python /opt/maxkb-app/test_storage.py
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path

def test_storage():
    """测试存储功能"""
    print("=" * 60)
    print("MinerU 图片存储测试")
    print("=" * 60)
    
    # 1. 检查存储路径配置
    storage_path = os.getenv('MAXKB_STORAGE_PATH', '/opt/maxkb/storage')
    print(f"\n1. 存储路径配置：{storage_path}")
    
    # 2. 创建测试目录结构
    test_dir = os.path.join(storage_path, 'test', 'images')
    print(f"\n2. 创建测试目录：{test_dir}")
    os.makedirs(test_dir, exist_ok=True)
    
    # 3. 创建测试图片文件
    test_image_path = os.path.join(test_dir, 'test_image.txt')
    print(f"\n3. 创建测试文件：{test_image_path}")
    with open(test_image_path, 'w') as f:
        f.write("This is a test image file for MinerU storage")
    
    # 4. 验证文件创建
    if os.path.exists(test_image_path):
        print("   ✓ 文件创建成功")
        file_size = os.path.getsize(test_image_path)
        print(f"   文件大小：{file_size} bytes")
    else:
        print("   ✗ 文件创建失败")
        return False
    
    # 5. 生成访问URL
    relative_path = os.path.relpath(test_image_path, storage_path)
    access_url = f"/api/storage/{relative_path}"
    print(f"\n4. 生成的访问URL：{access_url}")
    
    # 6. 列出存储目录内容
    print(f"\n5. 存储目录内容：")
    for root, dirs, files in os.walk(storage_path):
        level = root.replace(storage_path, '').count(os.sep)
        indent = ' ' * 2 * level
        print(f'{indent}{os.path.basename(root)}/')
        subindent = ' ' * 2 * (level + 1)
        for file in files:
            print(f'{subindent}{file}')
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("\n配置建议：")
    print("1. 确保Docker volume正确挂载：~/.maxkb/storage:/opt/maxkb/storage")
    print("2. 确保环境变量设置：MAXKB_STORAGE_PATH=/opt/maxkb/storage")
    print("3. 访问图片URL格式：http://localhost:8080/api/storage/mineru/images/xxx.jpg")
    print("=" * 60)
    
    return True

def test_mineru_adapter():
    """测试MinerU适配器"""
    print("\n" + "=" * 60)
    print("测试MinerU适配器")
    print("=" * 60)
    
    # 添加apps目录到Python路径
    sys.path.insert(0, '/opt/maxkb-app/apps' if os.path.exists('/opt/maxkb-app/apps') else './apps')
    
    try:
        from common.handle.impl.mineru.maxkb_adapter.adapter import MaxKBAdapter
        
        print("\n1. 创建MaxKB适配器实例")
        adapter = MaxKBAdapter()
        print(f"   存储路径：{adapter.storage_path}")
        
        # 创建临时测试文件
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp.write(b"Test image content")
            tmp_path = tmp.name
        
        print(f"\n2. 测试upload_file方法")
        print(f"   源文件：{tmp_path}")
        
        # 使用异步方式调用
        import asyncio
        async def test_upload():
            result = await adapter.upload_file(tmp_path, options=['test_knowledge'])
            return result
        
        # 运行异步测试
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        result_url = loop.run_until_complete(test_upload())
        print(f"   返回URL：{result_url}")
        
        # 清理临时文件
        os.unlink(tmp_path)
        
        print("\n✓ MinerU适配器测试成功")
        
    except ImportError as e:
        print(f"\n✗ 无法导入MinerU适配器：{e}")
        print("  请确保在MaxKB环境中运行此测试")
    except Exception as e:
        print(f"\n✗ 测试失败：{e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # 运行存储测试
    if test_storage():
        # 如果基础存储测试成功，尝试测试适配器
        try:
            test_mineru_adapter()
        except:
            print("\n提示：适配器测试需要在MaxKB环境中运行")