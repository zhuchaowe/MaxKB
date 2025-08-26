#!/usr/bin/env python3
"""
简单测试配置逻辑
"""

# 模拟配置类的行为
class TestConfig:
    def __init__(self):
        self.llm_model_id = None
        self.vision_model_id = None
    
    @classmethod
    def create(cls, llm_model_id=None, vision_model_id=None):
        instance = cls()
        if llm_model_id:
            instance.llm_model_id = llm_model_id
        if vision_model_id:
            instance.vision_model_id = vision_model_id
        print(f"Config created with LLM={instance.llm_model_id}, Vision={instance.vision_model_id}")
        return instance

def test_model_selection():
    """测试模型选择逻辑"""
    
    TEST_LLM_ID = "0198e029-bfeb-7d43-a6ee-c88662697d3c"
    TEST_VISION_ID = "0198e02c-9f2e-7520-a27b-6376ad42d520"
    
    # 创建配置
    config = TestConfig.create(
        llm_model_id=TEST_LLM_ID,
        vision_model_id=TEST_VISION_ID
    )
    
    print("\nTest 1: use_llm=False (should use vision model)")
    use_llm = False
    if use_llm:
        model_id = config.llm_model_id
        print(f"  Using LLM model: {model_id}")
    else:
        model_id = config.vision_model_id
        print(f"  Using Vision model: {model_id}")
    
    if model_id == TEST_VISION_ID:
        print(f"  ✅ Correct! Using vision model ID: {TEST_VISION_ID}")
    else:
        print(f"  ❌ Wrong! Using: {model_id}, Expected: {TEST_VISION_ID}")
    
    print("\nTest 2: use_llm=True (should use LLM model)")
    use_llm = True
    if use_llm:
        model_id = config.llm_model_id
        print(f"  Using LLM model: {model_id}")
    else:
        model_id = config.vision_model_id
        print(f"  Using Vision model: {model_id}")
    
    if model_id == TEST_LLM_ID:
        print(f"  ✅ Correct! Using LLM model ID: {TEST_LLM_ID}")
    else:
        print(f"  ❌ Wrong! Using: {model_id}, Expected: {TEST_LLM_ID}")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing Model Selection Logic")
    print("=" * 60)
    test_model_selection()
    print("=" * 60)