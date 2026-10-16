"""
Re-export sample text fixtures for root test runners.
No emojis used.
"""

from backend.tests.fixtures.sample_syndkos_text import (
    VILLA_SALOMY_INVALID_MATH_TEXT,
    VILLA_SALOMY_OCR_TEXT,
    VILLA_SALOMY_TEXT_PAGE1,
)

__all__ = [
    "VILLA_SALOMY_TEXT_PAGE1",
    "VILLA_SALOMY_OCR_TEXT",
    "VILLA_SALOMY_INVALID_MATH_TEXT",
]
