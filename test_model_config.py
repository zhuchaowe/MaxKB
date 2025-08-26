#!/usr/bin/env python3
"""
测试模型ID配置是否正确传递
"""

import os
import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
apps_path = project_root / 'apps'
if apps_path.exists():
    sys.path.insert(0, str(apps_path))

# 模拟传入的模型ID
TEST_LLM_ID = "0198e029-bfeb-7d43-a6ee-c88662697d3c"
TEST_VISION_ID = "0198e02c-9f2e-7520-a27b-6376ad42d520"

def test_config_creation():
    """测试配置创建"""
    print("=" * 60)
    print("Testing MaxKBMinerUConfig creation")
    print("=" * 60)
    
    from apps.common.handle.impl.mineru.maxkb_adapter.config_maxkb import MaxKBMinerUConfig
    
    # 方法1：直接创建（使用默认值或环境变量）
    print("\n1. Default creation:")
    config1 = MaxKBMinerUConfig()
    print(f"   LLM ID: {config1.llm_model_id}")
    print(f"   Vision ID: {config1.vision_model_id}")
    
    # 方法2：使用工厂方法
    print("\n2. Factory method creation:")
    config2 = MaxKBMinerUConfig.create(
        llm_model_id=TEST_LLM_ID,
        vision_model_id=TEST_VISION_ID
    )
    print(f"   LLM ID: {config2.llm_model_id}")
    print(f"   Vision ID: {config2.vision_model_id}")
    
    # 验证
    print("\n3. Verification:")
    if config2.llm_model_id == TEST_LLM_ID:
        print("   ✅ LLM ID correctly set")
    else:
        print(f"   ❌ LLM ID mismatch: expected {TEST_LLM_ID}, got {config2.llm_model_id}")
    
    if config2.vision_model_id == TEST_VISION_ID:
        print("   ✅ Vision ID correctly set")
    else:
        print(f"   ❌ Vision ID mismatch: expected {TEST_VISION_ID}, got {config2.vision_model_id}")
    
    return config2

def test_model_selection():
    """测试模型选择逻辑"""
    print("\n" + "=" * 60)
    print("Testing model selection logic")
    print("=" * 60)
    
    config = MaxKBMinerUConfig.create(
        llm_model_id=TEST_LLM_ID,
        vision_model_id=TEST_VISION_ID
    )
    
    # 模拟 call_litellm 中的逻辑
    print("\n1. When use_llm=True:")
    use_llm = True
    if use_llm:
        model_id = config.llm_model_id
    else:
        model_id = config.vision_model_id
    print(f"   Selected model ID: {model_id}")
    print(f"   Expected: {TEST_LLM_ID}")
    print(f"   Match: {model_id == TEST_LLM_ID}")
    
    print("\n2. When use_llm=False:")
    use_llm = False
    if use_llm:
        model_id = config.llm_model_id
    else:
        model_id = config.vision_model_id
    print(f"   Selected model ID: {model_id}")
    print(f"   Expected: {TEST_VISION_ID}")
    print(f"   Match: {model_id == TEST_VISION_ID}")

if __name__ == "__main__":
    print("Testing Model Configuration")
    print("=" * 60)
    print(f"Test LLM ID: {TEST_LLM_ID}")
    print(f"Test Vision ID: {TEST_VISION_ID}")
    
    config = test_config_creation()
    test_model_selection()
    
    print("\n" + "=" * 60)
    print("Test completed!")
    print("=" * 60)