#!/usr/bin/env python3
"""
测试配置对象的传递链
"""

import os
import sys

# 设置环境变量，避免从环境获取默认值
os.environ['MAXKB_LLM_MODEL_ID'] = ''
os.environ['MAXKB_VISION_MODEL_ID'] = ''

print("Testing config chain")
print("=" * 60)

# 模拟 dataclass
from dataclasses import dataclass

@dataclass
class BaseConfig:
    """Base configuration"""
    api_url: str = "default_url"
    
    def __post_init__(self):
        print(f"  BaseConfig.__post_init__ called")

class TestConfig(BaseConfig):
    """Test configuration with model IDs"""
    
    @classmethod
    def create(cls, llm_id=None, vision_id=None):
        print(f"TestConfig.create() called with llm_id={llm_id}, vision_id={vision_id}")
        instance = cls()
        print(f"  After cls(): llm={getattr(instance, 'llm_id', 'NOT SET')}, vision={getattr(instance, 'vision_id', 'NOT SET')}")
        
        if llm_id:
            instance.llm_id = llm_id
            print(f"  Set llm_id to {llm_id}")
        if vision_id:
            instance.vision_id = vision_id
            print(f"  Set vision_id to {vision_id}")
            
        print(f"  Final: llm={instance.llm_id}, vision={instance.vision_id}")
        return instance
    
    def __post_init__(self):
        print(f"  TestConfig.__post_init__ called")
        super().__post_init__()
        # Set defaults
        self.llm_id = "default_llm"
        self.vision_id = "default_vision"
        print(f"  Set defaults: llm={self.llm_id}, vision={self.vision_id}")

# Test 1: Direct creation
print("\nTest 1: Direct creation (should use defaults)")
config1 = TestConfig()
print(f"Result: llm={config1.llm_id}, vision={config1.vision_id}")

# Test 2: Factory method
print("\nTest 2: Factory method with IDs")
config2 = TestConfig.create(llm_id="llm_123", vision_id="vision_456")
print(f"Result: llm={config2.llm_id}, vision={config2.vision_id}")

print("\n" + "=" * 60)
print("Analysis:")
if config2.llm_id == "llm_123" and config2.vision_id == "vision_456":
    print("✅ Factory method correctly overrides defaults")
else:
    print("❌ Problem: Factory method failed to override defaults")
    print(f"   Expected: llm=llm_123, vision=vision_456")
    print(f"   Got: llm={config2.llm_id}, vision={config2.vision_id}")