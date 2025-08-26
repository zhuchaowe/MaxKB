# coding=utf-8
"""
高级学习任务 - 使用MinerU重新解析文档
"""
import traceback
import uuid as uuid_lib
from typing import List

from celery_once import QueueOnce
from django.db.models import QuerySet

from ops import celery_app


@celery_app.task(name='celery:advanced_learning_by_document')
def advanced_learning_by_document(document_id: str, knowledge_id: str, workspace_id: str,
                                 llm_model_id: str, vision_model_id: str):
    """
    使用MinerU高级学习处理文档
    
    @param document_id: 文档ID
    @param knowledge_id: 知识库ID
    @param workspace_id: 工作空间ID
    @param llm_model_id: 大语言模型ID
    @param vision_model_id: 视觉模型ID
    """
    # 延迟导入，避免循环依赖
    from common.event import ListenerManagement
    from common.utils.logger import maxkb_logger
    from knowledge.models import Document, Knowledge, Paragraph, State, TaskType, File, FileSourceType, get_default_status
    from knowledge.serializers.paragraph import delete_problems_and_mappings
    from knowledge.tasks.embedding import delete_embedding_by_document, embedding_by_document
    
    maxkb_logger.info(f"Starting advanced learning for document {document_id}")
    
    try:
        # 立即更新状态为解析中
        from common.event import ListenerManagement
        ListenerManagement.update_status(
            QuerySet(Document).filter(id=document_id),
            TaskType.EMBEDDING,
            State.PARSING
        )
        maxkb_logger.info(f"Updated document {document_id} status to PARSING")
        
        # 获取文档
        document = Document.objects.filter(id=document_id).first()
        if not document:
            maxkb_logger.error(f"Document {document_id} not found in database")
            return
        
        # 获取知识库
        knowledge = Knowledge.objects.filter(id=knowledge_id).first()
        if not knowledge:
            maxkb_logger.error(f"Knowledge {knowledge_id} not found")
            return
        
        # 获取源文件
        source_file_id = document.meta.get('source_file_id')
        if not source_file_id:
            maxkb_logger.warning(f"No source file for document {document.id}")
            ListenerManagement.update_status(
                QuerySet(Document).filter(id=document_id),
                TaskType.EMBEDDING,
                State.FAILURE
            )
            return
        
        source_file = File.objects.filter(id=source_file_id).first()
        if not source_file:
            maxkb_logger.warning(f"Source file not found for document {document.id}")
            ListenerManagement.update_status(
                QuerySet(Document).filter(id=document_id),
                TaskType.EMBEDDING,
                State.FAILURE
            )
            return
        
        # 删除现有的段落和向量数据
        QuerySet(Paragraph).filter(document_id=document_id).delete()
        delete_problems_and_mappings([document_id])
        delete_embedding_by_document(document_id)
        
        # 更新文档元数据，记录使用的模型
        document.meta['llm_model_id'] = llm_model_id
        document.meta['vision_model_id'] = vision_model_id
        document.save()
        
        # 使用MinerU重新解析文档
        from common.handle.impl.text.mineru_split_handle import MinerUSplitHandle
        import io
        
        mineru_handler = MinerUSplitHandle()
        
        # 获取文件内容
        file_content = source_file.get_bytes()
        temp_file = io.BytesIO(file_content)
        temp_file.name = source_file.file_name
        
        def get_buffer(file):
            file.seek(0)
            return file.read()
        
        def save_image(image_list):
            if image_list is not None and len(image_list) > 0:
                exist_image_list = [str(i.get('id')) for i in
                                    QuerySet(File).filter(id__in=[i.id for i in image_list]).values('id')]
                save_image_list = [image for image in image_list if not exist_image_list.__contains__(str(image.id))]
                save_image_list = list({img.id: img for img in save_image_list}.values())
                for file in save_image_list:
                    file_bytes = file.meta.pop('content')
                    file.meta['knowledge_id'] = knowledge_id
                    file.source_type = FileSourceType.KNOWLEDGE
                    file.source_id = knowledge_id
                    file.save(file_bytes)
        
        # 使用MinerU处理文档
        maxkb_logger.info(f"Using MinerU to reprocess document: {document.name}")
        paragraphs = mineru_handler.handle(
            temp_file,
            [],  # pattern_list
            False,  # with_filter
            0,  # limit (0表示不限制)
            get_buffer,
            save_image,
            llm_model_id=llm_model_id,
            vision_model_id=vision_model_id
        )
        
        if paragraphs and len(paragraphs) > 0:
            # 创建新的段落
            paragraph_model_list = []
            for index, paragraph in enumerate(paragraphs):
                paragraph_instance = Paragraph(
                    id=uuid_lib.uuid4(),
                    document_id=document_id,
                    knowledge_id=knowledge_id,
                    content=paragraph.get('content', ''),
                    title=paragraph.get('title', ''),
                    status=get_default_status(),
                    is_active=True,
                    hit_num=0,
                    position=index + 1
                )
                if 'image_list' in paragraph:
                    paragraph_instance.image_list = paragraph['image_list']
                paragraph_model_list.append(paragraph_instance)
            
            # 批量插入段落
            QuerySet(Paragraph).bulk_create(paragraph_model_list)
            
            # 更新文档字符数
            char_length = sum([len(p.content) for p in paragraph_model_list])
            document.char_length = char_length
            document.save()
            
            # MinerU解析完成，启动向量化任务
            embedding_model_id = knowledge.embedding_model_id
            maxkb_logger.info(f"Starting embedding for document {document_id} after MinerU parsing")
            
            # 调用向量化任务，此时embedding_by_document会自动将状态从PARSING更新为STARTED
            embedding_by_document.delay(
                str(document_id),
                str(embedding_model_id)
            )
            
            maxkb_logger.info(f"MinerU reprocessing completed for document: {document.name}, "
                            f"created {len(paragraph_model_list)} paragraphs")
        else:
            maxkb_logger.warning(f"MinerU returned no paragraphs for document: {document.name}")
            # 更新状态为失败
            ListenerManagement.update_status(
                QuerySet(Document).filter(id=document_id),
                TaskType.EMBEDDING,
                State.FAILURE
            )
    
    except Exception as e:
        maxkb_logger.error(f"Failed to process document {document_id}: {str(e)}", exc_info=True)
        # 更新状态为失败
        ListenerManagement.update_status(
            QuerySet(Document).filter(id=document_id),
            TaskType.EMBEDDING,
            State.FAILURE
        )


@celery_app.task(name='celery:batch_advanced_learning')
def batch_advanced_learning(document_id_list: List[str], knowledge_id: str, workspace_id: str,
                           llm_model_id: str, vision_model_id: str):
    """
    批量高级学习任务
    
    @param document_id_list: 文档ID列表
    @param knowledge_id: 知识库ID
    @param workspace_id: 工作空间ID
    @param llm_model_id: 大语言模型ID
    @param vision_model_id: 视觉模型ID
    """
    from common.utils.logger import maxkb_logger
    maxkb_logger.info(f"batch_advanced_learning called with {len(document_id_list)} documents")
    
    for document_id in document_id_list:
        maxkb_logger.info(f"Submitting advanced_learning_by_document for document {document_id}")
        advanced_learning_by_document.apply_async(
            args=[str(document_id), str(knowledge_id), workspace_id, llm_model_id, vision_model_id],
            queue='celery'
        )