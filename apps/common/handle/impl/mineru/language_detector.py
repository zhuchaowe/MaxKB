"""
Language detection utility for MinerU.

This module provides language detection functionality to ensure
generated content matches the source document language.
"""

import re
from typing import Optional, Dict, Tuple
from collections import Counter


class LanguageDetector:
    """Simple language detector based on character patterns and common words."""
    
    # Character range patterns for different languages
    LANGUAGE_PATTERNS = {
        'chinese': {
            'char_range': r'[\u4e00-\u9fff]',  # CJK Unified Ideographs
            'common_words': ['的', '是', '在', '和', '了', '有', '我', '不', '人', '这'],
            'name': '中文'
        },
        'japanese': {
            'char_range': r'[\u3040-\u309f\u30a0-\u30ff]',  # Hiragana and Katakana
            'common_words': ['の', 'は', 'を', 'が', 'に', 'と', 'で', 'から', 'まで', 'です'],
            'name': '日本語'
        },
        'korean': {
            'char_range': r'[\uac00-\ud7af]',  # Hangul
            'common_words': ['의', '은', '는', '이', '가', '을', '를', '에', '에서', '으로'],
            'name': '한국어'
        },
        'english': {
            'char_range': r'[a-zA-Z]',
            'common_words': ['the', 'is', 'at', 'and', 'of', 'to', 'in', 'for', 'with', 'on'],
            'name': 'English'
        }
    }
    
    @classmethod
    def detect_language(cls, text: str) -> Tuple[str, float]:
        """
        Detect the primary language of the given text.
        
        Priority: Japanese > Korean > Chinese > English
        Japanese has highest priority because it contains Kanji (Chinese characters).
        If Hiragana/Katakana are found, it's definitely Japanese.
        
        Args:
            text: Text to analyze
            
        Returns:
            Tuple of (language_code, confidence_score)
        """
        if not text or len(text.strip()) == 0:
            return 'english', 0.0
            
        # Log text sample for debugging
        from .logger import logger
        text_sample = text[:200] if len(text) > 200 else text
        logger.debug(f"LanguageDetector: Analyzing text sample: {text_sample}...")
        
        # Check for Japanese characters FIRST (highest priority)
        # Japanese text contains Hiragana/Katakana which are unique to Japanese
        japanese_chars = re.findall(cls.LANGUAGE_PATTERNS['japanese']['char_range'], text)
        if japanese_chars:
            # If we find Hiragana/Katakana, it's definitely Japanese
            confidence = min(len(japanese_chars) / 30, 1.0)  # Japanese text often mixed with Kanji
            logger.debug(f"LanguageDetector: Found {len(japanese_chars)} Japanese characters (Hiragana/Katakana)")
            return 'japanese', max(confidence, 0.95)  # Very high confidence for Japanese
        
        # Check for Korean characters (second priority)
        korean_chars = re.findall(cls.LANGUAGE_PATTERNS['korean']['char_range'], text)
        if korean_chars:
            # If we find Hangul characters, it's Korean
            confidence = min(len(korean_chars) / 100, 1.0)
            logger.debug(f"LanguageDetector: Found {len(korean_chars)} Korean characters")
            return 'korean', max(confidence, 0.9)
        
        # Check for Chinese characters (third priority)
        # Only classify as Chinese if no Japanese/Korean specific characters found
        chinese_chars = re.findall(cls.LANGUAGE_PATTERNS['chinese']['char_range'], text)
        if chinese_chars:
            # Found CJK ideographs without Hiragana/Katakana/Hangul, likely Chinese
            confidence = min(len(chinese_chars) / 100, 1.0)
            logger.debug(f"LanguageDetector: Found {len(chinese_chars)} Chinese characters (no Japanese/Korean markers)")
            return 'chinese', max(confidence, 0.9)
        
        # No CJK characters found, default to English
        # Check if there are actual English characters
        english_chars = re.findall(cls.LANGUAGE_PATTERNS['english']['char_range'], text)
        if english_chars:
            # Verify with common English words for higher confidence
            text_lower = text.lower()
            english_words = cls.LANGUAGE_PATTERNS['english']['common_words']
            word_matches = sum(1 for word in english_words if f' {word} ' in f' {text_lower} ')
            
            if word_matches >= 3:  # Found at least 3 common English words
                confidence = 0.95
            elif word_matches >= 1:
                confidence = 0.8
            else:
                confidence = 0.6  # Has English chars but no common words
            
            logger.debug(f"LanguageDetector: Detected English (found {word_matches} common words)")
            return 'english', confidence
        
        # No recognizable characters at all
        logger.debug("LanguageDetector: No specific language detected, defaulting to English")
        return 'english', 0.5
    
    @classmethod
    def get_language_name(cls, language_code: str) -> str:
        """Get the display name for a language code."""
        return cls.LANGUAGE_PATTERNS.get(language_code, {}).get('name', 'English')
    
    @classmethod
    def get_language_instruction(cls, language_code: str) -> str:
        """Get instruction text for generating content in specific language."""
        language_name = cls.get_language_name(language_code)
        
        instructions = {
            'chinese': '请使用中文生成所有描述和内容。',
            'japanese': '日本語ですべての説明と内容を生成してください。',
            'korean': '한국어로 모든 설명과 내용을 생성하십시오.',
            'english': 'Please generate all descriptions and content in English.'
        }
        
        return instructions.get(language_code, instructions['english'])
    
    @classmethod
    def get_image_language_instruction(cls, language_code: Optional[str] = None) -> str:
        """Get instruction for image processing when no text content is available."""
        if language_code:
            # If we have detected language from previous pages or document
            return cls.get_language_instruction(language_code)
        else:
            # If no language detected, instruct to match image text language
            return (
                "请根据图片中文本的语言生成相应语言的描述。\n"
                "如果图片中包含中文文本，请用中文描述；\n"
                "如果包含日文文本，请用日语描述；\n"
                "如果包含韩文文本，请用韩语描述；\n"
                "如果包含英文文本，请用英语描述。\n"
                "如果图片中没有文本或无法确定语言，请使用英语描述。"
            )