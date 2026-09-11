"""
Package Core pour l'application Fusion.
Fournit la lecture de fichiers, la déduplication en cascade, l'exportation et le logging.
"""

from .logger import setup_logger, get_logger, log_buffer
from .file_reader import read_excel_files, validate_dataframe, EXPECTED_COLUMNS
from .deduplicator import deduplicate_contacts, filter_contacts
from .exporter import export_to_excel

__all__ = [
    "setup_logger",
    "get_logger",
    "log_buffer",
    "read_excel_files",
    "validate_dataframe",
    "EXPECTED_COLUMNS",
    "deduplicate_contacts",
    "filter_contacts",
    "export_to_excel",
]
