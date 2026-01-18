"""
PII (Personally Identifiable Information) Sanitizer Module.

This module provides functionality to sanitize text by removing or redacting
sensitive information such as emails, IP addresses, credit cards, and API keys.

Critical for Air-Gap and Privacy compliance in Mnemosyne Core.
"""

import re
import logging
from typing import Pattern

logger = logging.getLogger(__name__)


class DataSanitizer:
    """
    Sanitizes text by removing PII and sensitive information.
    
    Uses regex patterns to detect and redact:
    - Email addresses
    - IP addresses (IPv4)
    - Credit card numbers (13-19 digits)
    - API keys (OpenAI, GitHub, AWS, etc.)
    """
    
    # Email pattern: standard RFC 5322 simplified
    EMAIL_PATTERN = re.compile(
        r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    )
    
    # IPv4 address pattern
    IPV4_PATTERN = re.compile(
        r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
    )
    
    # Credit card pattern: 13-19 digits (Luhn check not required for redaction)
    # Matches sequences that could be credit card numbers
    CREDIT_CARD_PATTERN = re.compile(
        r'\b(?:\d[ -]*?){13,19}\b'
    )
    
    # OpenAI API Key: sk- followed by 20+ alphanumeric characters
    # Note: OpenAI key format has evolved; length varies (40-60+ chars)
    OPENAI_KEY_PATTERN = re.compile(
        r'\bsk-[a-zA-Z0-9]{20,}\b'
    )
    
    # GitHub Personal Access Token: ghp_ followed by 36+ alphanumeric characters
    # Note: GitHub PAT format can vary in length
    GITHUB_KEY_PATTERN = re.compile(
        r'\bghp_[a-zA-Z0-9]{36,}\b'
    )
    
    # AWS Access Key ID: AKIA followed by 16 alphanumeric characters
    AWS_KEY_PATTERN = re.compile(
        r'\bAKIA[0-9A-Z]{16}\b'
    )
    
    # Generic API key pattern: common prefixes
    GENERIC_API_KEY_PATTERN = re.compile(
        r'\b(api[_-]?key|token|secret)[\s=:]+[a-zA-Z0-9_\-]{20,}\b',
        re.IGNORECASE
    )
    
    # UUID pattern (can be sensitive in some contexts)
    UUID_PATTERN = re.compile(
        r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'
    )
    
    REDACTION_MARKER = '[REDACTED]'
    
    def __init__(self):
        """Initialize the DataSanitizer with all patterns."""
        self.patterns: list[tuple[Pattern, str]] = [
            (self.EMAIL_PATTERN, 'EMAIL'),
            (self.IPV4_PATTERN, 'IP'),
            (self.CREDIT_CARD_PATTERN, 'CREDIT_CARD'),
            (self.OPENAI_KEY_PATTERN, 'API_KEY'),
            (self.GITHUB_KEY_PATTERN, 'API_KEY'),
            (self.AWS_KEY_PATTERN, 'API_KEY'),
            (self.GENERIC_API_KEY_PATTERN, 'API_KEY'),
            (self.UUID_PATTERN, 'UUID'),
        ]
        
        logger.info("DataSanitizer initialized with %d patterns", len(self.patterns))
    
    def clean_text(self, text: str) -> str:
        """
        Sanitize text by replacing all detected PII with [REDACTED].
        
        Args:
            text: The input text to sanitize.
            
        Returns:
            The sanitized text with PII replaced by [REDACTED].
        """
        if not text:
            return text
        
        result = text
        redactions = {}
        
        for pattern, category in self.patterns:
            matches = pattern.findall(result)
            if matches:
                redactions[category] = redactions.get(category, 0) + len(matches)
                result = pattern.sub(self.REDACTION_MARKER, result)
        
        if redactions:
            logger.debug("Sanitized text: %s", redactions)
        
        return result
    
    def clean_dict(self, data: dict) -> dict:
        """
        Sanitize all string values in a dictionary.
        
        Args:
            data: Dictionary with string values to sanitize.
            
        Returns:
            New dictionary with sanitized values.
        """
        result = {}
        for key, value in data.items():
            if isinstance(value, str):
                result[key] = self.clean_text(value)
            elif isinstance(value, dict):
                result[key] = self.clean_dict(value)
            elif isinstance(value, list):
                result[key] = self.clean_list(value)
            else:
                result[key] = value
        return result
    
    def clean_list(self, data: list) -> list:
        """
        Sanitize all string values in a list.
        
        Args:
            data: List with string values to sanitize.
            
        Returns:
            New list with sanitized values.
        """
        result = []
        for item in data:
            if isinstance(item, str):
                result.append(self.clean_text(item))
            elif isinstance(item, dict):
                result.append(self.clean_dict(item))
            elif isinstance(item, list):
                result.append(self.clean_list(item))
            else:
                result.append(item)
        return result
    
    def contains_pii(self, text: str) -> bool:
        """
        Check if text contains any PII patterns.
        
        Args:
            text: The input text to check.
            
        Returns:
            True if PII is detected, False otherwise.
        """
        if not text:
            return False
        
        for pattern, _ in self.patterns:
            if pattern.search(text):
                return True
        return False


# Singleton instance for easy import
_sanitizer_instance = None


def get_sanitizer() -> DataSanitizer:
    """Get or create the singleton DataSanitizer instance."""
    global _sanitizer_instance
    if _sanitizer_instance is None:
        _sanitizer_instance = DataSanitizer()
    return _sanitizer_instance
