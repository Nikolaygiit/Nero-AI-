"""
Утилиты для работы с текстом и разметкой Telegram
"""


def sanitize_markdown(text: str) -> str:
    """
    Очищает разметку Markdown от незакрытых тегов.
    Telegram не отправляет сообщение при некорректной разметке.
    """
    if not text or not isinstance(text, str):
        return text or ""

    result = text

    # Исправление незакрытых звёздочек (жирный/курсив)
    stars = result.count('*')
    if stars % 2 != 0:
        result = result.replace('*', '', 1)

    # Исправление незакрытых подчёркиваний (_)
    underscores = result.count('_')
    if underscores % 2 != 0:
        result = result.replace('_', '\\_', 1)

    # Закрываем незакрытые блоки кода ```
    code_blocks = result.count('```')
    if code_blocks % 2 != 0:
        result += '\n```'

    return result


def truncate_for_telegram(text: str, max_length: int = 4096) -> str:
    """Обрезает текст под лимит Telegram (4096 символов)"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."
