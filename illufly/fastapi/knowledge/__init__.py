"""
Knowledge Module

This module provides functionality for managing knowledge base entries.
"""

from .endpoints import create_knowledge_endpoints
from .models import Knowledge

__all__ = ['create_knowledge_endpoints', 'Knowledge']
