"""
Наблюдатель за изменениями файлов. Каждые 5 изменений создаёт резервную копию
в подпапки с датами: "Проект 3 (Git Копия)/2025-02-07_14-30-25/"
"""

import shutil
import time
from datetime import datetime
from pathlib import Path

import structlog
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = structlog.get_logger(__name__)

# Настройки
CHANGES_BEFORE_BACKUP = 5
BACKUP_BASE_FOLDER = "Проект 3 (Git Копия)"
DEBOUNCE_SECONDS = 2  # Изменения в течение 2 сек считаются одним "пакетом"

# Исключения при копировании
IGNORE_PATTERNS = {
    ".git",
    "__pycache__",
    "venv",
    "env",
    ".venv",
    "bot_database.db",
    "bot.log",
    ".env",
    "node_modules",
    ".idea",
    ".vscode",
    "*.pyc",
    BACKUP_BASE_FOLDER,  # Не копировать саму папку бэкапа
}


def should_ignore(path: Path) -> bool:
    """Проверяет, нужно ли игнорировать путь."""
    parts = path.parts
    for ignore in IGNORE_PATTERNS:
        if ignore in parts or path.name == ignore:
            return True
        if ignore.startswith("*") and path.suffix == ignore[1:]:
            return True
    return False


def copy_project(src: Path, base_backup: Path):
    """Копирует проект в подпапку с датой (версия_YYYY-MM-DD_HH-MM-SS)."""
    version_name = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    dst = base_backup / version_name

    def ignore_func(directory, files):
        return [
            f
            for f in files
            if f in (".git", ".env", "bot_database.db", "bot.log")
            or f == "__pycache__"
            or f == "venv"
            or f.endswith(".pyc")
        ]

    dst.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst, ignore=ignore_func)
    logger.info("backup_created", backup_path=str(dst))


class BackupHandler(FileSystemEventHandler):
    def __init__(self, project_path: Path, backup_path: Path):
        self.project_path = project_path
        self.backup_path = backup_path
        self.change_count = 0
        self.last_change_time = 0

    def _handle_change(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if should_ignore(path):
            return
        # Дебаунс: изменения в течение DEBOUNCE_SECONDS считаются одним
        now = time.time()
        if now - self.last_change_time > DEBOUNCE_SECONDS:
            self.change_count += 1
        self.last_change_time = now

        if self.change_count >= CHANGES_BEFORE_BACKUP:
            self.change_count = 0
            try:
                copy_project(self.project_path, self.backup_path)
            except Exception as e:
                logger.error("backup_failed", error=str(e))

    def on_modified(self, event):
        self._handle_change(event)

    def on_created(self, event):
        self._handle_change(event)


def main():
    project_path = Path(__file__).resolve().parent
    backup_base = project_path.parent / BACKUP_BASE_FOLDER
    backup_base.mkdir(parents=True, exist_ok=True)

    logger.info("backup_watcher_started", changes_threshold=CHANGES_BEFORE_BACKUP, backup_path=str(backup_base))

    event_handler = BackupHandler(project_path, backup_base)
    observer = Observer()
    observer.schedule(event_handler, str(project_path), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("backup_watcher_stopped")


if __name__ == "__main__":
    main()
