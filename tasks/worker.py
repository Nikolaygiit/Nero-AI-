"""
Taskiq worker — запуск: python -m tasks.worker
Эквивалентно: taskiq worker tasks.broker:broker tasks.image_tasks
"""

import subprocess
import sys

import structlog

logger = structlog.get_logger(__name__)

if __name__ == "__main__":
    from .broker import broker

    if broker is None:
        logger.error("worker_start_failed", reason="Redis недоступен")
        sys.exit(1)
    rc = subprocess.run(
        [
            sys.executable,
            "-m",
            "taskiq",
            "worker",
            "tasks.broker:broker",
            "tasks.image_tasks",
        ],
        check=False,
    )
    sys.exit(rc.returncode)
