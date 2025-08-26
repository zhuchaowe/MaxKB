"""
Global parallel processor pool for MinerU.

This module provides a singleton pool of parallel processors to avoid
creating multiple thread pools when processing multiple files.
"""

import threading
from typing import Optional
from .logger import get_module_logger
logger = get_module_logger('parallel_processor_pool')

from .parallel_processor import ParallelMinerUProcessor
from .config_base import MinerUConfig


class ParallelProcessorPool:
    """Singleton pool for managing parallel processors"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self._initialized = True
        self._processors = {}
        self._pool_lock = threading.Lock()
        self.logger = logger
        
    def get_processor(self, learn_type: int, platform_adapter=None, config=None) -> ParallelMinerUProcessor:
        """
        Get or create a parallel processor for the given learn_type.
        
        Args:
            learn_type: Model type for AI processing
            platform_adapter: Platform-specific adapter for operations
            config: Configuration instance to use (optional)
            
        Returns:
            ParallelMinerUProcessor instance
        """
        with self._pool_lock:
            if learn_type not in self._processors:
                self.logger.info(f"Creating new parallel processor for learn_type={learn_type}")
                # Use provided config or create default
                if config is None:
                    config = MinerUConfig()
                # Log the config being used
                if hasattr(config, 'llm_model_id') and hasattr(config, 'vision_model_id'):
                    self.logger.info(f"Using config with LLM={getattr(config, 'llm_model_id', 'N/A')}, Vision={getattr(config, 'vision_model_id', 'N/A')}")
                processor = ParallelMinerUProcessor(config, learn_type, platform_adapter)
                self._processors[learn_type] = processor
            
            return self._processors[learn_type]
    
    async def shutdown_all(self):
        """Shutdown all processors in the pool"""
        self.logger.info("Shutting down all parallel processors...")
        
        with self._pool_lock:
            for learn_type, processor in self._processors.items():
                try:
                    await processor.shutdown()
                    self.logger.info(f"Shutdown processor for learn_type={learn_type}")
                except Exception as e:
                    self.logger.error(f"Error shutting down processor {learn_type}: {e}")
            
            self._processors.clear()
        
        self.logger.info("All processors shutdown complete")


# Global instance
_processor_pool = ParallelProcessorPool()


def get_parallel_processor(learn_type: int, platform_adapter=None, config=None) -> ParallelMinerUProcessor:
    """
    Get a parallel processor from the global pool.
    
    Args:
        learn_type: Model type for AI processing
        platform_adapter: Platform-specific adapter for operations
        config: Configuration instance to use (optional)
        
    Returns:
        ParallelMinerUProcessor instance
    """
    return _processor_pool.get_processor(learn_type, platform_adapter, config)


async def shutdown_processor_pool():
    """Shutdown the global processor pool"""
    await _processor_pool.shutdown_all()