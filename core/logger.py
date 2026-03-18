"""
core/logger.py — Standart Python loglama (rich bağımlılığı yok)
"""
import logging
import os
from datetime import datetime
from config import config


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Terminal çıktısı
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(name)-18s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S"
    ))
    logger.addHandler(console_handler)

    # Dosya — tam debug logu
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    log_file = os.path.join(
        config.LOGS_DIR,
        f"smartmailer_{datetime.now().strftime('%Y-%m-%d')}.log"
    )
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s"
    ))
    logger.addHandler(file_handler)

    return logger
