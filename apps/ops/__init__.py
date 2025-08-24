# coding=utf-8
"""
    @project: MaxKB
    @Author：虎
    @file： __init__.py.py
    @date：2024/8/16 14:47
    @desc:
"""
from .celery import app as celery_app

# Import and register advanced learning tasks
try:
    from knowledge.tasks.advanced_learning import (
        advanced_learning_by_document,
        batch_advanced_learning
    )
    # Register tasks with the celery app
    celery_app.register_task(advanced_learning_by_document)
    celery_app.register_task(batch_advanced_learning)
except ImportError:
    pass
