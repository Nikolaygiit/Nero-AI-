"""
Taskiq worker — запуск: python -m tasks.worker
Эквивалентно: taskiq worker tasks.broker:broker tasks.image_tasks
"""
import subprocess
import sys

if __name__ == "__main__":
    from .broker import broker
    if broker is None:
        print("Redis недоступен, worker не запущен.", file=sys.stderr)
        sys.exit(1)
    rc = subprocess.run(
        [
            sys.executable, "-m", "taskiq", "worker",
            "tasks.broker:broker",
            "tasks.image_tasks",
        ],
        check=False,
    )
    sys.exit(rc.returncode)
