import re
from typing import List
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from utils.i18n import t

def make_regenerate_keyboard(uid: int, req_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками 'В избранное', 'Перегенерировать', 'Перефразировать'."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(t("btn_favorite"), callback_data=f"fav_{uid}"),
            InlineKeyboardButton(t("btn_regenerate"), callback_data=f"retry_{uid}_{req_id}"),
        ],
        [InlineKeyboardButton(t("btn_rephrase"), callback_data=f"rephrase_{uid}")],
    ])

def split_long_message(text: str, max_length: int = 4096) -> List[str]:
    """
    Разбивает длинное сообщение на части, стараясь не разрывать блоки кода.
    Если часть получается слишком большой даже после разбиения по блокам,
    она разбивается жестко по лимиту.
    """
    if len(text) <= max_length:
        return [text]

    parts = []
    current_part = ""
    # Разбиваем по блокам кода
    code_blocks = re.split(r'(```[\s\S]*?```)', text)

    for block in code_blocks:
        if not block:
            continue

        # Если текущий кусок + новый блок влезают в лимит (с запасом)
        if len(current_part) + len(block) <= max_length:
            current_part += block
        else:
            # Если текущий кусок не пустой, сохраняем его
            if current_part:
                parts.append(current_part)
                current_part = ""

            # Если сам блок больше лимита, придется его разбить жестко
            if len(block) > max_length:
                # Разбиваем длинный блок на куски
                for i in range(0, len(block), max_length):
                    parts.append(block[i:i + max_length])
            else:
                current_part = block

    if current_part:
        parts.append(current_part)

    return parts
