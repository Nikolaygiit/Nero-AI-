"""Очереди задач (Taskiq + Redis). Тяжёлые операции выполняются воркерами."""

from .broker import broker, get_taskiq_queue_length

__all__ = ["broker", "get_taskiq_queue_length"]
