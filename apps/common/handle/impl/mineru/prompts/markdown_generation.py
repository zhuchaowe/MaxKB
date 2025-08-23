"""
Markdown generation prompt for LLM content refinement.
Used in ContentProcessor._llm_refine_content method.
"""

# Base prompt without language instruction
MARKDOWN_GENERATION_BASE = """你是一个专业的文档处理助手。请根据提供的PDF页面图片和文本内容生成结构化的Markdown文档。

## 任务要求：
1. 首先查看PDF页面图片，理解文档的完整布局和内容
2. 分析并整合两个文本源的内容（OCR提取的文本和PDF原始文本）
3. 识别并正确格式化所有结构化元素：
   - 标题和章节结构（使用 #, ##, ### 等）
   - 表格（使用 Markdown 表格语法）
   - 列表（有序和无序）
   - 代码块
   - 引用
4. 确保内容的准确性和完整性，特别是表格内容
5. 保持原始文档的逻辑结构
6. 修复任何OCR识别错误
7. 修复文本和表格的位置关系，关联内容需要前后衔接

## 输出要求：
- 输出纯Markdown格式，用"```markdown"和"```"包裹
- 不要包含HTML标签
- 保留文档中的图片引用（非PDF页面图片）
- 可以对文档内容和内容格式进行适当的增强和优化
- 保持专业的文档风格

## 重要事项
- 图片链接不允许出现重复引用的情况，保证一个图片链接只出现一次
- 表格使用标准Markdown语法（|列1|列2|...）
- 输出语言保持和图片原文语言一致
"""

# Keep the original constant for backward compatibility
MARKDOWN_GENERATION_PROMPT = MARKDOWN_GENERATION_BASE

def format_markdown_generation_prompt(language_code=None):
    """
    Format the markdown generation prompt with optional language instruction.
    
    Args:
        language_code: Optional language code for output language matching
    
    Returns:
        Formatted prompt string
    """
    if language_code:
        from ..language_detector import LanguageDetector
        language_instruction = f"\n\n## 语言要求：\n{LanguageDetector.get_language_instruction(language_code)}\n"
        return MARKDOWN_GENERATION_BASE + language_instruction
    else:
        return MARKDOWN_GENERATION_BASE