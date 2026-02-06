"""
Централизованная настройка логирования — JSON в файл для анализа
Логи в формате JSON: кто, когда, какую команду вызвал
"""
import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any

LOG_FILE = "bot.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3
ENCODING = "utf-8"


class JSONFormatter(logging.Formatter):
    """Форматтер: одна строка JSON на запись — удобно для анализа и ELK"""

    def format(self, record: logging.LogRecord) -> str:
        d: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            d["exception"] = self.formatException(record.exc_info)
        # Доп. поля из extra (например user_id, command)
        if hasattr(record, "user_id"):
            d["user_id"] = record.user_id
        if hasattr(record, "command"):
            d["command"] = record.command
        if hasattr(record, "chat_id"):
            d["chat_id"] = record.chat_id
        return json.dumps(d, ensure_ascii=False)


def setup_logging(level: int = logging.INFO, json_format: bool = True) -> logging.Logger:
    """
    Настраивает логирование: JSON в файл + читаемый вывод в консоль.
    При достижении 5 MB создаётся новый файл (до 3 резервных копий).
    """
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Файл — JSON
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding=ENCODING,
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(JSONFormatter() if json_format else logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)

    # Консоль — читаемый формат
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    console_handler.setLevel(level)
    root.addHandler(console_handler)

    return logging.getLogger(__name__)
