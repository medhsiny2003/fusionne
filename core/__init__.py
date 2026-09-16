"""
Package Core pour l'application Fusion.
Fournit la lecture de fichiers, la déduplication en cascade, l'exportation, le logging et l'assistant de filtrage.
"""

from .logger import setup_logger, get_logger, log_buffer
from .file_reader import read_excel_files, read_single_excel
from .deduplicator import deduplicate_contacts, filter_contacts, detect_column_roles
from .exporter import export_to_excel
from .filter_assistant import (
    parse_line_ranges,
    delete_by_indices,
    delete_by_companies,
    execute_smart_command,
)

__all__ = [
    "setup_logger",
    "get_logger",
    "log_buffer",
    "read_excel_files",
    "read_single_excel",
    "deduplicate_contacts",
    "filter_contacts",
    "detect_column_roles",
    "export_to_excel",
    "parse_line_ranges",
    "delete_by_indices",
    "delete_by_companies",
    "execute_smart_command",
]
