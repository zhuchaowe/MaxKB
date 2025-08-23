"""
Enhanced prompt templates for context-aware document processing.

This module contains all the prompt templates used for different types of
content analysis with context awareness.
"""
# Vision prompts for image analysis
VISION_PROMPT_WITH_CONTEXT = """你是一个专业的文档分析助手。请根据提供的上下文信息和图片内容进行综合分析。

# 上下文信息：
页面位置：第 {page_idx} 页
页面类型：{page_type}
{page_title_info}

# 周围文本内容：
{surrounding_text}

# 任务要求：
请综合考虑上下文信息，分析这张图片并输出JSON格式结果：

{
    "detailed_description": "综合视觉描述，包括：
    - 整体构图和布局
    - 识别所有对象、人物、文本和视觉元素
    - 解释元素之间的关系以及它们与周围上下文的关系
    - 注意颜色、光线和视觉风格
    - 描述显示的任何动作或活动
    - 包括相关的技术细节
    - 引用与周围内容的连接
    - 始终使用具体名称而非代词",
    "entity_info": {
        "entity_name": "基于内容和上下文的简短标题",
        "entity_type": "image",
        "summary": "简洁总结图片内容、其重要性以及与周围内容的关系（最多100字）"
    },
    "context_relevance": "high/medium/low - 图片与上下文的相关性",
    "relationships": ["描述与周围文本或其他元素的关系"]
}

图片详情：
- 图片路径：{image_path}
- 标题：{captions}
- 脚注：{footnotes}
"""

VISION_PROMPT_WITHOUT_CONTEXT = """请分析这张图片并按照以下格式输出JSON结果：

# 分类决策规则：
1. structured_content（结构化内容）：
   - 图片包含可提取结构的元素，例如：
        * 文字为主的文档、书籍、海报
        * 表格、图表（柱状图、饼图等）、示意图、架构图、流程图、思维导图
        * 数学公式、化学方程式、代码截图
   - 注意：即使有少量非结构化元素（如图标、装饰图），只要结构化内容是主体（占比>70%）就属于此类。

2. brief_description（简要描述）：
   - 图片内容有明确主题但无法提取结构化信息，例如：
        * 人物、动物、风景的照片
        * 绘画、漫画、艺术创作
        * 实物产品、场景的展示
        * 界面截图（无核心信息区域）
        * 地图
   - 注意：若图片同时包含结构化和非结构化内容，但结构化内容占比<30%，则归入此类。

3. meaningless（无意义内容）：
   - 图片没有传达实质性信息，例如：
        * 纯色背景、渐变背景（无主体对象）
        * 抽象纹理、模糊不清无法辨认的图片
        * 页面的装饰性分隔线、纯装饰性图标（尺寸极小）
        * 水印、页眉页脚装饰条（不包含核心信息的部分）

# 输出格式：
```json
{
   "type": "分类类型",
   "description": "图片内容的详细描述（50-100字）",
   "entity_info": {
      "entity_name": "图片的简短标题",
      "entity_type": "image",
      "summary": "简洁总结（50字以内）"
   },
   "ocr_content": "提取的文字内容（仅对structured_content类型）"
}
```"""

# Table analysis prompts
TABLE_PROMPT_WITH_CONTEXT = """分析以下表格内容，并考虑其在文档中的上下文：

# 上下文信息：
{context}

# 表格内容：
{table_content}

请输出：
{
    "table_summary": "表格内容的简要总结",
    "column_headers": ["列标题列表"],
    "row_count": 行数,
    "key_insights": ["从表格中提取的关键信息"],
    "context_relevance": "表格与上下文的相关性说明"
}"""

# Equation analysis prompts
EQUATION_PROMPT_WITH_CONTEXT = """分析以下数学公式或方程式：

# 上下文信息：
{context}

# 公式内容：
{equation_content}

请输出：
{
    "equation_type": "公式类型（如：微分方程、代数方程等）",
    "variables": ["变量列表"],
    "interpretation": "公式的含义解释",
    "context_usage": "公式在上下文中的应用"
}"""

# Content refinement prompts
CONTENT_REFINEMENT_PROMPT = """请分析和优化以下文档内容：

1. 整合结构化内容与纯文本参考
2. 确保表格结构在markdown中正确格式化
3. 移除重复信息
4. 保持原始语言和术语
5. 保留所有重要细节和数据
6. 创建连贯、结构良好的文档
7. 特别注意保持图片引用的正确性

输出优化后的markdown格式内容。"""

# Chunk summarization prompts
CHUNK_SUMMARY_PROMPT_WITH_CONTEXT = """基于以下内容生成摘要：

# 前文摘要：
{previous_summary}

# 当前内容：
{current_content}

# 后续预览：
{next_preview}

请生成：
1. 当前内容的摘要（100-200字）
2. 与前后文的关联说明
3. 关键要点列表"""

# Generic content analysis with context
GENERIC_PROMPT_WITH_CONTEXT = """分析以下内容并考虑其上下文：

# 上下文信息：
{context}

# 内容类型：{content_type}
# 内容：
{content}

请提供：
{
    "content_summary": "内容摘要",
    "key_elements": ["关键元素列表"],
    "context_relationship": "与上下文的关系说明",
    "importance": "high/medium/low"
}"""

# Prompt selection function
def get_prompt(prompt_name: str, **kwargs) -> str:
    """
    Get a prompt template by name and format it with provided arguments.
    
    Args:
        prompt_name: Name of the prompt template
        **kwargs: Arguments to format the prompt
        
    Returns:
        Formatted prompt string
    """
    prompts = {
        'vision_prompt_with_context': VISION_PROMPT_WITH_CONTEXT,
        'vision_prompt': VISION_PROMPT_WITHOUT_CONTEXT,
        'table_prompt_with_context': TABLE_PROMPT_WITH_CONTEXT,
        'equation_prompt_with_context': EQUATION_PROMPT_WITH_CONTEXT,
        'content_refinement_prompt': CONTENT_REFINEMENT_PROMPT,
        'chunk_summary_prompt_with_context': CHUNK_SUMMARY_PROMPT_WITH_CONTEXT,
        'generic_prompt_with_context': GENERIC_PROMPT_WITH_CONTEXT
    }
    
    template = prompts.get(prompt_name, '')
    if not template:
        raise ValueError(f"Unknown prompt: {prompt_name}")
    
    # Format the template with provided arguments
    try:
        return template.format(**kwargs)
    except KeyError as e:
        raise ValueError(f"Missing required argument for prompt '{prompt_name}': {e}")

# Enhanced classification prompt builder
def build_classification_prompt(has_context: bool, context_info: dict = None) -> str:
    """
    Build a classification prompt based on whether context is available.
    
    Args:
        has_context: Whether context information is available
        context_info: Dictionary containing context information
        
    Returns:
        Appropriate prompt string
    """
    if has_context and context_info:
        return get_prompt('vision_prompt_with_context', **context_info)
    else:
        return VISION_PROMPT_WITHOUT_CONTEXT