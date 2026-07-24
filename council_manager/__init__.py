"""
Council Manager Package.

Exposes global settings, project config parameters, and bootstrap adapters 
for multi-team AI project governance and alignment management.
"""

from council_manager.config import settings, Settings

__all__ = [
    "settings",
    "Settings",
]
