# coding=utf-8

# Import tasks for Celery discovery
# Note: We import the specific tasks, not * to avoid circular imports
from .advanced_learning import advanced_learning_by_document, batch_advanced_learning