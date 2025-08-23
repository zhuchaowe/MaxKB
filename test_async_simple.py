#!/usr/bin/env python
"""
简单测试异步修复
"""

import asyncio
from asgiref.sync import sync_to_async


class TestModel:
    """模拟的模型类"""
    def invoke(self, messages):
        """同步调用方法"""
        return type('Response', (), {'content': 'Test response'})()


def get_model_sync():
    """模拟同步获取模型"""
    print("同步获取模型...")
    return TestModel()


async def get_model_async():
    """异步获取模型"""
    print("异步获取模型...")
    return await sync_to_async(get_model_sync)()


async def call_model_async():
    """异步调用模型"""
    print("异步调用模型...")
    model = await get_model_async()
    
    # 使用 sync_to_async 包装同步的 invoke 方法
    response = await sync_to_async(model.invoke)([{"role": "user", "content": "test"}])
    
    if hasattr(response, 'content'):
        return response.content
    else:
        return str(response)


async def main():
    """主测试函数"""
    print("=" * 60)
    print("测试异步修复")
    print("=" * 60)
    
    try:
        result = await call_model_async()
        print(f"✓ 异步调用成功: {result}")
    except Exception as e:
        print(f"✗ 异步调用失败: {e}")
    
    print("=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())