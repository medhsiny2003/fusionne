"""
Gestionnaire de logs pour l'application Fusion.
Sauvegarde dans logs/fusion_YYYYMMDD.log et alimente un tampon mémoire pour l'UI Streamlit.
"""

import os
import logging
from datetime import datetime
from typing import List, Dict

class StreamlitLogBuffer(logging.Handler):
    """Handler de log stockant les messages dans un buffer mémoire pour l'UI."""
    def __init__(self, capacity: int = 1000):
        super().__init__()
        self.capacity = capacity
        self.records: List[Dict[str, str]] = []

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.records.append({
                "timestamp": datetime.fromtimestamp(record.created).strftime("%H:%M:%S"),
                "level": record.levelname,
                "message": msg,
                "raw_message": record.getMessage(),
            })
            if len(self.records) > self.capacity:
                self.records.pop(0)
        except Exception:
            self.handleError(record)

    def get_logs(self) -> List[Dict[str, str]]:
        return list(self.records)

    def clear(self):
        self.records.clear()

# Instance globale du buffer pour l'interface
log_buffer = StreamlitLogBuffer()

def setup_logger(name: str = "fusion", log_dir: str = "logs") -> logging.Logger:
    """Configure et retourne le logger de l'application."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Éviter la duplication des handlers
    if not logger.handlers:
        os.makedirs(log_dir, exist_ok=True)
        date_str = datetime.now().strftime("%Y%m%d")
        log_file = os.path.join(log_dir, f"fusion_{date_str}.log")

        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # File handler
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        # Streamlit buffer handler
        log_buffer.setLevel(logging.INFO)
        log_buffer.setFormatter(formatter)
        logger.addHandler(log_buffer)

        # Console stream handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    return logger

def get_logger() -> logging.Logger:
    """Récupère l'instance active du logger."""
    return logging.getLogger("fusion")
