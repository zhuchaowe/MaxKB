#!/usr/bin/env python
"""
测试 MinerU 异步上下文修复
"""

import os
import sys
import asyncio
import django

# 设置 Django 环境
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartdoc.settings')
django.setup()

from apps.common.handle.impl.mineru.maxkb_adapter.maxkb_model_client import maxkb_model_client


async def test_async_model_calls():
    """测试异步模型调用"""
    print("测试异步模型调用...")
    
    # 测试获取 LLM 模型
    try:
        print("\n1. 测试获取 LLM 模型...")
        llm_model = await maxkb_model_client.get_llm_model("0198cbd9-c1a6-7b13-b16d-d85ad77ac03d")
        if llm_model:
            print("   ✓ LLM 模型获取成功")
        else:
            print("   ✗ LLM 模型获取失败")
    except Exception as e:
        print(f"   ✗ LLM 模型获取出错: {e}")
    
    # 测试获取视觉模型
    try:
        print("\n2. 测试获取视觉模型...")
        vision_model = await maxkb_model_client.get_vision_model("0198cbd9-c1a6-7b13-b16d-d85ad77ac03d")
        if vision_model:
            print("   ✓ 视觉模型获取成功")
        else:
            print("   ✗ 视觉模型获取失败")
    except Exception as e:
        print(f"   ✗ 视觉模型获取出错: {e}")
    
    # 测试聊天完成
    try:
        print("\n3. 测试聊天完成...")
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, this is a test."}
        ]
        response = await maxkb_model_client.chat_completion(
            "0198cbd9-c1a6-7b13-b16d-d85ad77ac03d",
            messages
        )
        if response:
            print(f"   ✓ 聊天完成成功: {response[:100]}...")
        else:
            print("   ✗ 聊天完成返回空响应")
    except Exception as e:
        print(f"   ✗ 聊天完成出错: {e}")
    
    # 测试模型验证
    try:
        print("\n4. 测试模型验证...")
        is_valid = await maxkb_model_client.validate_model("0198cbd9-c1a6-7b13-b16d-d85ad77ac03d")
        if is_valid:
            print("   ✓ 模型验证成功")
        else:
            print("   ✗ 模型不存在或无效")
    except Exception as e:
        print(f"   ✗ 模型验证出错: {e}")
    
    print("\n测试完成！")


async def test_mineru_image_processing():
    """测试 MinerU 图像处理流程"""
    print("\n测试 MinerU 图像处理流程...")
    
    from apps.common.handle.impl.mineru.config_base import MinerUConfig
    from apps.common.handle.impl.mineru.image_processor import MinerUImageProcessor
    
    # 创建配置
    config = MinerUConfig()
    
    # 创建图像处理器
    processor = MinerUImageProcessor(config)
    await processor.initialize()
    
    print("✓ 图像处理器初始化成功")
    
    # 清理资源
    await processor.cleanup()
    print("✓ 图像处理器清理成功")


async def main():
    """主测试函数"""
    print("=" * 60)
    print("MinerU 异步上下文修复测试")
    print("=" * 60)
    
    # 测试异步模型调用
    await test_async_model_calls()
    
    # 测试图像处理流程
    await test_mineru_image_processing()
    
    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())