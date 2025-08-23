"""
Flowchart recognition plugin for MinerU-based parsing.

This module provides specialized flowchart recognition capabilities,
extracted from gzero.py's gzero_gwc_flowchart function as requested.
"""

import os
import base64
import asyncio
from typing import Dict, Any
from .logger import get_module_logger
logger = get_module_logger('flowchart_plugin')

from .config_base import MinerUConfig

# Platform-specific imports (if available)
try:
    from loader.gzero import gzero_vllm_proc, gzero_vllm_page_filter
except ImportError:
    gzero_vllm_proc = None
    gzero_vllm_page_filter = None


class FlowchartPlugin:
    """Plugin for specialized flowchart recognition and processing"""
    
    def __init__(self, learn_type: int = 9):
        """
        Initialize flowchart plugin.
        
        Args:
            learn_type: Model type for AI processing
        """
        self.learn_type = learn_type
        self.logger = logger
        self.config = MinerUConfig()
        
    async def process_flowchart_page(self, page_desc: Dict, page_count: int, 
                                   image_name: str, temp_dir: str, src_name: str) -> Dict[str, Any]:
        """
        Process a page containing GWC flowchart content.
        
        Based on gzero_gwc_flowchart function from gzero.py.
        
        Args:
            page_desc: Page description with text content
            page_count: Total number of pages
            image_name: Name of page image file
            temp_dir: Temporary directory
            src_name: Source file name
            
        Returns:
            Dictionary with processed flowchart content and metadata
        """
        try:
            self.logger.info(f"flowchart-plugin: [{src_name}] processing flowchart page: {image_name}")
            
            # Load vision model
            vision_model = self.config.get_model(self.learn_type)
            
            # Load image and convert to base64
            image_file = os.path.join(temp_dir, image_name)
            with open(image_file, 'rb') as file:
                image_data = file.read()
            image_base64 = base64.b64encode(image_data).decode("utf-8")
            image_url = f"data:image/png;base64,{image_base64}"
            
            # Define processing steps
            step0_prompt = self._get_step0_prompt()
            step1_prompt = self._get_step1_prompt()
            step2_prompt = self._get_step2_prompt()
            step3_prompt = self._get_step3_prompt()
            
            hint = f"{page_desc['index']}/{page_count}"
            
            # Step 0: Identify flowchart nodes
            step0_res = await self._execute_step(
                vision_model, step0_prompt, image_url, temp_dir, src_name, 
                f"{os.path.splitext(image_name)[0]}.step0", hint
            )
            
            # Step 1: Organize nodes by department
            step1_res = await self._execute_step_with_context(
                vision_model, step0_prompt, step1_prompt, image_url, 
                step0_res['content'], temp_dir, src_name,
                f"{os.path.splitext(image_name)[0]}.step1", hint
            )
            
            # Step 2: Create mermaid flowchart
            step2_res = await self._execute_step_with_context(
                vision_model, step0_prompt, step2_prompt, image_url,
                step0_res['content'], temp_dir, src_name,
                f"{os.path.splitext(image_name)[0]}.step2", hint
            )
            
            # Step 3: Extract remaining content
            step3_res = await self._execute_complex_step(
                vision_model, step0_prompt, step2_prompt, step3_prompt,
                image_url, step0_res['content'], step2_res['content'],
                temp_dir, src_name, f"{os.path.splitext(image_name)[0]}.step3", hint
            )
            
            # Combine results
            content = self._combine_flowchart_results(
                step0_res, step1_res, step2_res, step3_res
            )
            
            # Calculate totals
            input_tokens = sum([step0_res['input_tokens'], step1_res['input_tokens'], 
                               step2_res['input_tokens'], step3_res['input_tokens']])
            output_tokens = sum([step0_res['output_tokens'], step1_res['output_tokens'],
                                step2_res['output_tokens'], step3_res['output_tokens']])
            dura = sum([step0_res['dura'], step1_res['dura'], 
                       step2_res['dura'], step3_res['dura']])
            
            self.logger.info(f"flowchart-plugin: [{src_name}] flowchart processing completed")
            
            return {
                'content': content,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'dura': dura,
                'flowchart_metadata': {
                    'steps_processed': 4,
                    'nodes_extracted': step0_res['content'].count('<node>'),
                    'departments_identified': step1_res['content'].count('#'),
                    'mermaid_generated': 'mermaid' in step2_res['content'].lower()
                }
            }
            
        except Exception as e:
            self.logger.error(f"flowchart-plugin: [{src_name}] flowchart processing failed: {str(e)}")
            raise
    
    def should_use_flowchart_plugin(self, page_text: str) -> bool:
        """
        Determine if a page should use the flowchart plugin.
        
        Based on the conditions from gzero.py.
        """
        indicators = [
            '\\n流程名稱\\n',
            '\\n流程編號\\n', 
            '\\n流程說明\\n'
        ]
        
        # Check if all indicators are present
        has_all_indicators = all(indicator in page_text for indicator in indicators)
        
        # Additional checks for flowchart-like content
        has_flowchart_keywords = any(keyword in page_text.lower() for keyword in [
            'flowchart', 'flow chart', '流程图', '流程圖', 
            'process', 'workflow', 'tcode', 'sap'
        ])
        
        return has_all_indicators or has_flowchart_keywords
    
    async def _execute_step(self, vision_model, prompt: str, image_url: str,
                           temp_dir: str, src_name: str, req_name: str, hint: str) -> Dict:
        """Execute a single step with image input"""
        step_req = [
            {'role': 'system', 'content': prompt},
            {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': image_url}}]},
        ]
        
        if gzero_vllm_proc and gzero_vllm_page_filter:
            res = await gzero_vllm_proc(vision_model, step_req, temp_dir, src_name, req_name, hint)
            res['content'] = gzero_vllm_page_filter(res['content'])
        else:
            # Fallback if platform functions not available
            res = {'content': 'Flowchart processing not available on this platform'}
        
        self.logger.info(f"flowchart-plugin: [{src_name}] step completed: {req_name}")
        return res
    
    async def _execute_step_with_context(self, vision_model, system_prompt: str, user_prompt: str,
                                       image_url: str, context: str, temp_dir: str, 
                                       src_name: str, req_name: str, hint: str) -> Dict:
        """Execute a step with previous context"""
        step_req = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': image_url}}]},
            {'role': 'assistant', 'content': context},
            {'role': 'user', 'content': user_prompt},
        ]
        
        if gzero_vllm_proc and gzero_vllm_page_filter:
            res = await gzero_vllm_proc(vision_model, step_req, temp_dir, src_name, req_name, hint)
            res['content'] = gzero_vllm_page_filter(res['content'])
        else:
            # Fallback if platform functions not available
            res = {'content': 'Flowchart processing not available on this platform'}
        
        self.logger.info(f"flowchart-plugin: [{src_name}] context step completed: {req_name}")
        return res
    
    async def _execute_complex_step(self, vision_model, system_prompt: str, step2_prompt: str,
                                  step3_prompt: str, image_url: str, step0_content: str,
                                  step2_content: str, temp_dir: str, src_name: str,
                                  req_name: str, hint: str) -> Dict:
        """Execute complex step with multiple context elements"""
        step_req = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': image_url}}]},
            {'role': 'assistant', 'content': step0_content},
            {'role': 'user', 'content': step2_prompt},
            {'role': 'assistant', 'content': step2_content},
            {'role': 'user', 'content': step3_prompt},
        ]
        
        if gzero_vllm_proc and gzero_vllm_page_filter:
            res = await gzero_vllm_proc(vision_model, step_req, temp_dir, src_name, req_name, hint)
            res['content'] = gzero_vllm_page_filter(res['content'])
        else:
            # Fallback if platform functions not available
            res = {'content': 'Flowchart processing not available on this platform'}
        
        self.logger.info(f"flowchart-plugin: [{src_name}] complex step completed: {req_name}")
        return res
    
    def _combine_flowchart_results(self, step0_res: Dict, step1_res: Dict,
                                 step2_res: Dict, step3_res: Dict) -> str:
        """Combine all flowchart processing results into final content"""
        content = ''
        content += step3_res['content'] + '\\n\\n'
        content += '流程节点：\\n' + step0_res['content'] + '\\n\\n'
        content += '流程负责部门：\\n' + step1_res['content'] + '\\n\\n'
        content += '流程图：\\n' + step2_res['content'] + '\\n\\n'
        return content
    
    def _get_step0_prompt(self) -> str:
        """Get step 0 prompt for node identification"""
        return """
图片左下方一个很大的格子内是一张大的流程图。请用你的视觉多模态能力识别这张流程图的每一个处理节点的内容文字并输出。
某些方框右上角会有一个SAP的图标，图标的上方会有一串大写英文字母、数字、横杠、斜杠组成的TCode代码，请注意识别并以[TCode:代码]的格式添加到该方框的识别结果中。
每一个节点识别的内容如有换行请替换为空格，最终用<node>与</node>标签包含并输出。
请保持识别文字原来的写法，比如是繁体中文的请输出繁体中文，不要输出为简体中文，更不要翻译为其他语种。
"""
    
    def _get_step1_prompt(self) -> str:
        """Get step 1 prompt for department organization"""
        return """
留意流程图上方还有一行标题行文字，可能中间还会有竖向分隔虚线，将流程图分隔为多个区域并标识为标题文字的负责部门。
请根据之前识别出来的流程节点信息，以及可能有中间分隔虚线划分出来的区域，将之前识别出来的node节点信息归属到标题文字标识的负责部门中，输出如下的markdown格式:
# 负责部门1(标题文字)
## 归属负责部门1的node节点内容
## 归属负责部门1的node节点内容
...
# 负责部门2(标题文字)
## 归属负责部门2的node节点内容
## 归属负责部门2的node节点内容
...
"""
    
    def _get_step2_prompt(self) -> str:
        """Get step 2 prompt for mermaid generation"""
        return """
再观察图片左下方大的格子内的流程图，
根据之前识别出来的流程图node节点信息，
参考流程图中节点间的线条和箭头，以及线条旁边的条件标签，
将整张流程图识别并输出为mermaid格式。
注意要以node节点内容信息作为mermaid节点的内容。
"""
    
    def _get_step3_prompt(self) -> str:
        """Get step 3 prompt for remaining content extraction"""
        return """
根据上面识别出来图片左下很大区域的流程图内的节点node信息和流程图mermaid信息，将图片内流程图其余部分的内容识别并输出为markdown格式。
1. 优先识别页面最左上角格子内类似"XXXX專案"的标题文字（用`#`表示）。
2. 注意不需要再识别左下角大格子内的流程图内容了，你只需要识别流程图之外的内容就可以了。识别的内容输出为markdown格式。
"""