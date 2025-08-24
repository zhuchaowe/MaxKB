#!/usr/bin/env python
"""
测试图片存储和访问

这个脚本会：
1. 创建一个测试图片在存储目录
2. 打印正确的访问URL
"""

import os
import sys

def main():
    # 设置存储路径（本地开发环境）
    storage_path = os.getenv('MAXKB_STORAGE_PATH', './tmp/maxkb/storage')
    
    print("=" * 60)
    print("MaxKB 图片存储和访问测试")
    print("=" * 60)
    
    # 创建目录结构
    image_dir = os.path.join(storage_path, 'mineru', 'images')
    os.makedirs(image_dir, exist_ok=True)
    print(f"\n1. 存储目录：{image_dir}")
    
    # 创建测试图片文件
    test_image = os.path.join(image_dir, 'ac3681aaa7a346b49ef9c7ceb7b94058.jpg')
    with open(test_image, 'wb') as f:
        # 写入一个简单的测试内容（实际应该是图片二进制数据）
        f.write(b'TEST IMAGE CONTENT')
    print(f"2. 创建测试文件：{test_image}")
    
    # 生成访问URL
    print("\n3. 访问URL：")
    print(f"   本地开发：http://localhost:8080/storage/mineru/images/ac3681aaa7a346b49ef9c7ceb7b94058.jpg")
    print(f"   Docker环境：http://localhost:8080/storage/mineru/images/ac3681aaa7a346b49ef9c7ceb7b94058.jpg")
    
    # 列出当前存储目录的所有文件
    print(f"\n4. 存储目录内容：")
    for root, dirs, files in os.walk(storage_path):
        level = root.replace(storage_path, '').count(os.sep)
        indent = '  ' * level
        print(f'{indent}{os.path.basename(root)}/')
        subindent = '  ' * (level + 1)
        for file in files:
            file_path = os.path.join(root, file)
            file_size = os.path.getsize(file_path)
            print(f'{subindent}{file} ({file_size} bytes)')
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("\n注意事项：")
    print("1. 确保Django服务器正在运行")
    print("2. URL路径现在是 /storage/ 开头，简洁直接")
    print("3. 如果使用Docker，确保volume正确挂载")
    print("=" * 60)

if __name__ == "__main__":
    main()