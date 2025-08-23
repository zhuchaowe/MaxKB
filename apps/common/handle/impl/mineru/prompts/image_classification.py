"""
Optimized image classification prompts for MinerU with caching support.

These prompts are designed to maximize prompt caching efficiency by:
1. Keeping static content at the beginning
2. Placing variable content at the end
3. Separating simple and context-aware versions for better cache hits
"""

# Base prompt for image classification (static part)
IMAGE_CLASSIFICATION_BASE = """你是一个专业的文档分析助手。请根据图片内容进行分析。

# 任务要求：
请分析这张图片并输出JSON格式结果。输出需要包含以下字段：

1. type: 图片类型分类
   - "structured_content": 包含可提取结构的内容（文档、表格、图表、公式等）
   - "brief_description": 有明确主题但无法提取结构（照片、插图等）
   - "meaningless": 无实质内容（装饰、分隔线等）

2. title: 图片的简短标题（10字以内）
   - 应该是语义化的标题，例如："系统架构图"、"流程图"、"数据表格"、"统计图表"、"代码截图"等

3. description: 图片内容的详细描述
   - 描述图片的主要内容和视觉元素

4. ocr_content: 仅对structured_content类型，提取图片中的文字内容

# 重要禁止项：
- 绝对禁止输出任何 base64 编码的图片数据
- 禁止输出类似 "data:image/png;base64,..." 或 "data:image/jpeg;base64,..." 的内容
- 禁止输出任何 markdown 格式的图片标签
- 违反以上规则会导致输出无效

# 输出格式：
```json
{
   "type": "分类类型",
   "title": "简短标题",
   "description": "详细描述",
   "ocr_content": "提取的文字内容（如适用）"
}
```"""

# Simple classification prompt (without context)
IMAGE_CLASSIFICATION_SIMPLE = IMAGE_CLASSIFICATION_BASE + """

# 具体要求：
- description字段请控制在50-100字以内
- 仅基于图片内容本身进行分析"""

# Context-aware classification prompt (with context)
IMAGE_CLASSIFICATION_CONTEXT_BASE = IMAGE_CLASSIFICATION_BASE + """

# 具体要求：
- description字段请控制在100-200字以内，需要：
  - 解释图片与周围文本的关系
  - 说明图片在文档中的作用
- context_relevance 字段，表示图片与上下文的相关性（high/medium/low）

# 输出格式：
```json
{
   "type": "分类类型",
   "title": "简短标题",
   "description": "详细描述",
   "ocr_content": "提取的文字内容（如适用）",
   "context_relevance": "相关性等级"
}
```

# 上下文信息：
"""

# Context template suffix (variable part - placed at the end)
CONTEXT_SUFFIX_TEMPLATE = """页面位置：第 {page_idx} 页
页面类型：{page_type}
{page_title_info}

# 周围文本内容：
{surrounding_text}"""


def format_image_classification_prompt(context=None, language_code=None, has_text_content=True):
    """
    Format the image classification prompt optimized for caching.
    
    Args:
        context: Optional context information dict with keys:
                 page_idx, page_type, page_title_info, surrounding_text
        language_code: Optional language code for output language matching
        has_text_content: Whether there's text content available for language detection
    
    Returns:
        Formatted prompt string
    """
    # Add language instruction based on content availability
    language_instruction = ""
    if has_text_content and language_code:
        # Have text content and detected language
        from ..language_detector import LanguageDetector
        language_instruction = f"\n\n# 语言要求：\n{LanguageDetector.get_language_instruction(language_code)}\n"
    elif not has_text_content:
        # No text content, use image-based language detection
        from ..language_detector import LanguageDetector
        language_instruction = f"\n\n# 语言要求：\n{LanguageDetector.get_image_language_instruction(language_code)}\n"
    
    if context:
        # Build context suffix
        context_suffix = CONTEXT_SUFFIX_TEMPLATE.format(
            page_idx=context.get('page_idx', 1),
            page_type=context.get('page_type', '未知'),
            page_title_info=context.get('page_title_info', ''),
            surrounding_text=context.get('surrounding_text', '无')
        )
        # Return context-aware prompt with variable content at the end
        return IMAGE_CLASSIFICATION_CONTEXT_BASE + language_instruction + context_suffix
    else:
        # Return simple prompt with language instruction
        return IMAGE_CLASSIFICATION_SIMPLE + language_instruction