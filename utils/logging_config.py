"""
Централизованная настройка логирования через structlog
Структурированные логи в формате JSON для анализа и построения графиков
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

import structlog

LOG_FILE = "bot.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB
BACKUP_COUNT = 3
ENCODING = "utf-8"


def setup_logging(level: int = logging.INFO) -> None:
    """
    Настраивает structlog: JSON в файл + читаемый вывод в консоль.
    При достижении 5 MB создаётся новый файл (до 3 резервных копий).
    """
    # Настраиваем стандартный logging для structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )

    # Файловый обработчик с ротацией (JSON)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding=ENCODING,
    )
    file_handler.setLevel(level)

    # Консольный обработчик (читаемый формат)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Настраиваем structlog с JSON для всех (файл и консоль)
    # Для консоли можно использовать structlog.dev.ConsoleRenderer, но проще оставить JSON
    # и парсить при необходимости, или использовать отдельный форматтер
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # добавляет contextvars
            structlog.stdlib.add_log_level,  # добавляет level
            structlog.stdlib.add_logger_name,  # добавляет logger
            structlog.processors.TimeStamper(fmt="iso"),  # ISO timestamp
            structlog.processors.StackInfoRenderer(),  # стек при исключениях
            structlog.processors.format_exc_info,  # форматирование исключений
            structlog.processors.dict_tracebacks,  # трейсбеки как dict
            structlog.processors.JSONRenderer(),  # JSON формат
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Добавляем обработчики к root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Уменьшаем шум: HTTP-запросы telegram/httpx только при необходимости
    for name in ("httpx", "httpcore", "telegram"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # Для консоли используем форматтер, который преобразует JSON в читаемый вид
    class ReadableFormatter(logging.Formatter):
        """Форматтер для читаемого вывода в консоль из JSON"""

        def format(self, record):
            msg = record.getMessage()
            # Если это JSON строка, форматируем читаемо
            if msg.startswith("{") and msg.endswith("}"):
                try:
                    import json

                    data = json.loads(msg)
                    parts = []
                    if "timestamp" in data:
                        ts = data["timestamp"].replace("T", " ").replace("Z", "")[:19]
                        parts.append(f"[{ts}]")
                    if "level" in data:
                        level_map = {
                            "INFO": "INFO",
                            "DEBUG": "DEBUG",
                            "WARNING": "WARN",
                            "ERROR": "ERROR",
                            "CRITICAL": "CRIT",
                        }
                        parts.append(f"{level_map.get(data['level'], data['level'])}")
                    if "logger" in data:
                        parts.append(f"{data['logger']}")
                    if "event" in data:
                        parts.append(f"{data['event']}")
                    elif "message" in data:
                        parts.append(f"{data['message']}")
                    # Добавляем остальные поля (кроме служебных)
                    skip_keys = {"timestamp", "level", "logger", "event", "message", "exception"}
                    extra = {k: v for k, v in data.items() if k not in skip_keys}
                    if extra:
                        parts.append(f"{extra}")
                    return " ".join(parts)
                except Exception:
                    pass
            return msg

    console_handler.setFormatter(ReadableFormatter())
