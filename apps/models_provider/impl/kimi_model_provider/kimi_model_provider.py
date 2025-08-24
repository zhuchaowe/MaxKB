# coding=utf-8
"""
    @project: maxkb
    @Author：虎
    @file： kimi_model_provider.py
    @date：2024/3/28 16:26
    @desc:
"""
import os

from common.utils.common import get_file_content
from models_provider.base_model_provider import IModelProvider, ModelProvideInfo, ModelInfo, \
    ModelTypeConst, ModelInfoManage
from models_provider.impl.kimi_model_provider.credential.llm import KimiLLMModelCredential
from models_provider.impl.kimi_model_provider.credential.image import KimiImageModelCredential
from models_provider.impl.kimi_model_provider.model.llm import KimiChatModel
from models_provider.impl.kimi_model_provider.model.image import KimiImageModel
from maxkb.conf import PROJECT_DIR

kimi_llm_model_credential = KimiLLMModelCredential()
kimi_image_model_credential = KimiImageModelCredential()

# LLM Models
moonshot_v1_8k = ModelInfo('moonshot-v1-8k', '', ModelTypeConst.LLM, kimi_llm_model_credential,
                           KimiChatModel)
moonshot_v1_32k = ModelInfo('moonshot-v1-32k', '', ModelTypeConst.LLM, kimi_llm_model_credential,
                            KimiChatModel)
moonshot_v1_128k = ModelInfo('moonshot-v1-128k', '', ModelTypeConst.LLM, kimi_llm_model_credential,
                             KimiChatModel)

# Vision/Image Models
moonshot_v1_8k_vision = ModelInfo('moonshot-v1-8k-vision-preview', 'Kimi 视觉模型 8K', ModelTypeConst.IMAGE, 
                                  kimi_image_model_credential, KimiImageModel)
moonshot_v1_32k_vision = ModelInfo('moonshot-v1-32k-vision-preview', 'Kimi 视觉模型 32K', ModelTypeConst.IMAGE,
                                   kimi_image_model_credential, KimiImageModel)
moonshot_v1_128k_vision = ModelInfo('moonshot-v1-128k-vision-preview', 'Kimi 视觉模型 128K', ModelTypeConst.IMAGE,
                                    kimi_image_model_credential, KimiImageModel)

model_info_manage = (ModelInfoManage.builder()
    .append_model_info(moonshot_v1_8k)
    .append_model_info(moonshot_v1_32k)
    .append_default_model_info(moonshot_v1_128k)
    .append_default_model_info(moonshot_v1_8k)
    .append_model_info(moonshot_v1_8k_vision)
    .append_model_info(moonshot_v1_32k_vision)
    .append_model_info(moonshot_v1_128k_vision)
    .append_default_model_info(moonshot_v1_128k_vision)
    .build())


class KimiModelProvider(IModelProvider):

    def get_model_info_manage(self):
        return model_info_manage

    def get_dialogue_number(self):
        return 3

    def get_model_provide_info(self):
        return ModelProvideInfo(provider='model_kimi_provider', name='Kimi', icon=get_file_content(
            os.path.join(PROJECT_DIR, "apps", 'models_provider', 'impl', 'kimi_model_provider', 'icon',
                         'kimi_icon_svg')))
