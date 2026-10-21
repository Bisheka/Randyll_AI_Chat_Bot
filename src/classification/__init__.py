"""Semantic category assignment without source rewriting or PDF generation."""
from .service import build_classification_report, classify_document

__all__ = ["build_classification_report", "classify_document"]
