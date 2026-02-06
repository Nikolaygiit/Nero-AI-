"""
Дополнительные команды бота (/translate, /summarize, /explain и т.д.)
"""
import logging
import re
import random
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from services.gemini import gemini_service
from services.image_gen import image_generator
from middlewares.rate_limit import rate_limit_middleware
import config

logger = logging.getLogger(__name__)


async def translate_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /translate для перевода текста"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            """
🌐 **Перевод текста**

❌ Укажите язык и текст для перевода.

💡 **Использование:** `/translate [язык] [текст]`

📝 **Примеры:**
• `/translate en Привет, как дела?`
• `/translate ru Hello, how are you?`

🌍 **Поддерживаемые языки:** ru, en, es, fr, de, it, pt, ja, ko, zh
""", parse_mode='Markdown')
        return
    
    target_lang = context.args[0].lower()
    text_to_translate = " ".join(context.args[1:])
    
    # Валидация
    supported_languages = ['ru', 'en', 'es', 'fr', 'de', 'it', 'pt', 'ja', 'ko', 'zh']
    if target_lang not in supported_languages:
        await update.message.reply_text(
            f"❌ Неподдерживаемый язык: {target_lang}\n\n"
            f"🌍 Поддерживаемые языки: {', '.join(supported_languages)}",
            parse_mode='Markdown'
        )
        return
    
    if not text_to_translate or len(text_to_translate.strip()) < 2:
        await update.message.reply_text("❌ Укажите текст для перевода (минимум 2 символа)", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.",
            parse_mode=None
        )
        return
    
    await update.message.reply_chat_action("typing")
    
    prompt = f"Переведи следующий текст на {target_lang}: {text_to_translate}. Верни только перевод без дополнительных комментариев."
    
    try:
        translation = await gemini_service.generate_content(prompt, user_id, use_context=False)
        await update.message.reply_text(
            f"""
🌐 **Перевод готов**

📝 **Оригинал:** {text_to_translate}
🌍 **Язык:** {target_lang.upper()}

✨ **Перевод:**
{translation}
""", parse_mode='Markdown')
        await db.update_stats(user_id, command='translate')
    except Exception as e:
        logger.error(f"Ошибка перевода: {e}")
        await update.message.reply_text(f"❌ Ошибка перевода: {str(e)[:200]}", parse_mode='Markdown')


async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /summarize для сокращения текста"""
    if not context.args:
        await update.message.reply_text(
            """
📝 **Сокращение текста**

❌ Укажите текст для сокращения.

💡 **Использование:** `/summarize [текст]`

📝 **Пример:** `/summarize Длинный текст для сокращения...`
""", parse_mode='Markdown')
        return
    
    text_to_summarize = " ".join(context.args)
    
    # Валидация
    if not text_to_summarize or len(text_to_summarize.strip()) == 0:
        await update.message.reply_text("❌ Укажите текст для сокращения.", parse_mode='Markdown')
        return
    
    if len(text_to_summarize) > 5000:
        await update.message.reply_text("❌ Текст слишком длинный. Максимум 5000 символов.", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.",
            parse_mode=None
        )
        return
    
    await update.message.reply_chat_action("typing")
    
    prompt = f"Сократи следующий текст, сохраняя основные идеи и ключевые моменты: {text_to_summarize}"
    
    try:
        summary = await gemini_service.generate_content(prompt, user_id, use_context=False)
        await update.message.reply_text(
            f"""
📝 **Сокращенный текст**

✨ **Результат:**
{summary}

📊 **Оригинал:** {len(text_to_summarize)} символов
📊 **Сокращение:** {len(summary)} символов
""", parse_mode='Markdown')
        await db.update_stats(user_id, command='summarize')
    except Exception as e:
        logger.error(f"Ошибка сокращения: {e}")
        await update.message.reply_text(f"❌ Ошибка сокращения: {str(e)[:200]}", parse_mode='Markdown')


async def explain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /explain для объяснения терминов"""
    if not context.args:
        await update.message.reply_text(
            """
💡 **Объяснение терминов**

❌ Укажите термин для объяснения.

💡 **Использование:** `/explain [термин]`

📝 **Примеры:**
• `/explain квантовая физика`
• `/explain API`
""", parse_mode='Markdown')
        return
    
    term = " ".join(context.args)
    
    # Валидация
    if not term or len(term.strip()) < 2:
        await update.message.reply_text("❌ Укажите термин для объяснения (минимум 2 символа)", parse_mode='Markdown')
        return
    
    if len(term) > 500:
        await update.message.reply_text("❌ Термин слишком длинный. Максимум 500 символов.", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.",
            parse_mode=None
        )
        return
    
    await update.message.reply_chat_action("typing")
    
    prompt = f"Объясни простым языком, что такое '{term}'. Используй примеры и аналогии."
    
    try:
        explanation = await gemini_service.generate_content(prompt, user_id, use_context=False)
        await update.message.reply_text(
            f"""
💡 **Объяснение: {term}**

{explanation}
""", parse_mode='Markdown')
        await db.update_stats(user_id, command='explain')
    except Exception as e:
        logger.error(f"Ошибка объяснения: {e}")
        await update.message.reply_text(f"❌ Ошибка объяснения: {str(e)[:200]}", parse_mode='Markdown')


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /quiz для создания викторин"""
    topic = " ".join(context.args) if context.args else "общая тема"
    
    # Валидация
    if len(topic) > 300:
        await update.message.reply_text("❌ Тема слишком длинная. Максимум 300 символов.", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.",
            parse_mode=None
        )
        return
    
    await update.message.reply_chat_action("typing")
    
    prompt = f"Создай викторину из 5 вопросов на тему '{topic}'. Формат: вопрос, затем варианты ответов (a, b, c, d), затем правильный ответ."
    
    try:
        quiz = await gemini_service.generate_content(prompt, user_id, use_context=False)
        await update.message.reply_text(
            f"""
🎯 **Викторина: {topic}**

{quiz}
""", parse_mode='Markdown')
        await db.update_stats(user_id, command='quiz')
    except Exception as e:
        logger.error(f"Ошибка создания викторины: {e}")
        await update.message.reply_text(f"❌ Ошибка создания викторины: {str(e)[:200]}", parse_mode='Markdown')


async def calculator_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /calculator для вычислений"""
    if not context.args:
        await update.message.reply_text(
            """
🔢 **Калькулятор**

❌ Укажите выражение для вычисления.

💡 **Использование:** `/calculator [выражение]`

📝 **Примеры:**
• `/calculator 2 + 2`
• `/calculator 100 * 5.5`
""", parse_mode='Markdown')
        return
    
    expression = " ".join(context.args)
    
    # Валидация
    if not expression or len(expression.strip()) < 1:
        await update.message.reply_text("❌ Укажите выражение для вычисления", parse_mode='Markdown')
        return
    
    # Проверка безопасности
    if re.search(r'[^0-9+\-*/().\s]', expression):
        await update.message.reply_text("❌ Выражение содержит недопустимые символы. Используйте только числа и математические операции.", parse_mode='Markdown')
        return
    
    if len(expression) > 200:
        await update.message.reply_text("❌ Выражение слишком длинное. Максимум 200 символов.", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.",
            parse_mode=None
        )
        return
    
    await update.message.reply_chat_action("typing")
    
    prompt = f"Вычисли следующее выражение: {expression}. Верни только результат."
    
    try:
        result = await gemini_service.generate_content(prompt, user_id, use_context=False)
        await update.message.reply_text(
            f"""
🔢 **Результат вычисления**

📝 **Выражение:** {expression}
✨ **Ответ:** {result}
""", parse_mode='Markdown')
        await db.update_stats(user_id, command='calculator')
    except Exception as e:
        logger.error(f"Ошибка вычисления: {e}")
        await update.message.reply_text(f"❌ Ошибка вычисления: {str(e)[:200]}", parse_mode='Markdown')


async def wiki_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /wiki для поиска в Wikipedia"""
    if not context.args:
        await update.message.reply_text(
            """
📚 **Поиск в Wikipedia**

❌ Укажите запрос для поиска.

💡 **Использование:** `/wiki [запрос]`

📝 **Примеры:**
• `/wiki Python`
• `/wiki искусственный интеллект`
""", parse_mode='Markdown')
        return
    
    query = " ".join(context.args)
    
    # Валидация
    if not query or len(query.strip()) == 0:
        await update.message.reply_text("❌ Укажите запрос для поиска.", parse_mode='Markdown')
        return
    
    if len(query) > 200:
        await update.message.reply_text("❌ Запрос слишком длинный. Максимум 200 символов.", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.",
            parse_mode=None
        )
        return
    
    await update.message.reply_chat_action("typing")
    
    prompt = f"Найди информацию о '{query}' в Wikipedia и предоставь краткую справку (2-3 абзаца)."
    
    try:
        info = await gemini_service.generate_content(prompt, user_id, use_context=False)
        await update.message.reply_text(
            f"""
📚 **Wikipedia: {query}**

{info}
""", parse_mode='Markdown')
        await db.update_stats(user_id, command='wiki')
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        await update.message.reply_text(f"❌ Ошибка поиска: {str(e)[:200]}", parse_mode='Markdown')


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /random для случайных значений"""
    if not context.args:
        await update.message.reply_text(
            """
🎲 **Случайные значения**

💡 **Использование:**
• `/random number [min] [max]` - случайное число
• `/random choice [вариант1] [вариант2] ...` - случайный выбор
• `/random coin` - подбросить монету
• `/random dice` - бросить кубик

📝 **Примеры:**
• `/random number 1 100`
• `/random choice яблоко банан апельсин`
• `/random coin`
""", parse_mode='Markdown')
        return
    
    user_id = update.effective_user.id
    action = context.args[0].lower()
    
    try:
        if action == "number" and len(context.args) >= 3:
            min_val = int(context.args[1])
            max_val = int(context.args[2])
            result = random.randint(min_val, max_val)
            await update.message.reply_text(f"🎲 **Случайное число:** {result}", parse_mode='Markdown')
        elif action == "choice" and len(context.args) > 1:
            choices = context.args[1:]
            result = random.choice(choices)
            await update.message.reply_text(f"🎲 **Выбран:** {result}", parse_mode='Markdown')
        elif action == "coin":
            result = random.choice(["Орел", "Решка"])
            await update.message.reply_text(f"🪙 **Результат:** {result}", parse_mode='Markdown')
        elif action == "dice":
            result = random.randint(1, 6)
            await update.message.reply_text(f"🎲 **Выпало:** {result}", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Неверный формат команды. Используйте /random для справки.", parse_mode='Markdown')
            return
        
        await db.update_stats(user_id, command='random')
    except Exception as e:
        logger.error(f"Ошибка random: {e}")
        await update.message.reply_text(f"❌ Ошибка: {str(e)[:200]}", parse_mode='Markdown')


async def code_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /code для генерации кода"""
    if not context.args:
        await update.message.reply_text(
            """
💻 **Генерация кода**

❌ Укажите, какой код нужен.

💡 **Примеры:**
• `/code функция на Python для сортировки`
• `/code класс для работы с API на JavaScript`
• `/code алгоритм бинарного поиска`
""", parse_mode='Markdown')
        return
    
    prompt = " ".join(context.args)
    prompt = f"Напиши код: {prompt}. Обязательно используй markdown форматирование с блоками кода."
    
    user_id = update.effective_user.id
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.",
            parse_mode=None
        )
        return
    
    await update.message.reply_chat_action("typing")
    
    try:
        code = await gemini_service.generate_content(prompt, user_id, use_context=False)
        await update.message.reply_text(code, parse_mode='Markdown')
        await db.update_stats(user_id, command='code')
    except Exception as e:
        logger.error(f"Ошибка генерации кода: {e}")
        await update.message.reply_text(f"❌ Ошибка генерации кода: {str(e)[:200]}", parse_mode='Markdown')


async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /persona для выбора персонажа"""
    user_id = update.effective_user.id
    
    if not context.args:
        # Показываем список персонажей
        personas_text = "👤 **Доступные персонажи:**\n\n"
        for key, persona in config.PERSONAS.items():
            personas_text += f"• `{key}` — {persona['name']}\n"
        
        personas_text += "\n💡 **Использование:** `/persona [название]`\n"
        personas_text += "📝 **Пример:** `/persona teacher`"
        
        await update.message.reply_text(personas_text, parse_mode='Markdown')
        return
    
    persona_key = context.args[0].lower()
    
    if persona_key in config.PERSONAS:
        await db.create_or_update_user(telegram_id=user_id, persona=persona_key)
        persona_info = config.PERSONAS[persona_key]
        await update.message.reply_text(
            f"✅ **Персонаж установлен:** {persona_info['name']}\n\n"
            f"💡 Теперь бот будет общаться в стиле этого персонажа.",
            parse_mode='Markdown'
        )
        await db.update_stats(user_id, command='persona')
    else:
        await update.message.reply_text(
            f"❌ Неизвестный персонаж: {persona_key}\n\n"
            f"💡 Используйте `/persona` для просмотра доступных персонажей.",
            parse_mode='Markdown'
        )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /stats для просмотра статистики"""
    user_id = update.effective_user.id
    stats = await db.get_stats(user_id)
    
    if stats:
        days_active = max((datetime.now() - stats.start_date).days, 1) if stats.start_date else 1
        avg_requests_per_day = stats.requests_count / days_active if days_active > 0 else 0
        avg_tokens_per_request = stats.tokens_used / max(stats.requests_count, 1)
        
        text = f"""
📊 **Ваша статистика использования**

📝 **Запросов:** `{stats.requests_count}`
🎨 **Изображений:** `{stats.images_generated}`
🔤 **Токенов использовано:** `{stats.tokens_used:,}`
📅 **Дней активен:** `{days_active}`

📈 **Средние показатели:**

📊 Запросов в день: `{avg_requests_per_day:.1f}`
🔤 Токенов на запрос: `{avg_tokens_per_request:.0f}`

💡 Продолжайте использовать бота для улучшения статистики!
"""
    else:
        text = """
📊 **Ваша статистика использования**

📝 **Запросов:** `0`
🎨 **Изображений:** `0`
🔤 **Токенов использовано:** `0`

💡 Начните использовать бота для накопления статистики!
"""
    
    await update.message.reply_text(text, parse_mode='Markdown')
    await db.update_stats(user_id, command='stats')


async def image_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /image для генерации изображений"""
    if not context.args:
        await update.message.reply_text(
            """
🎨 **Генерация изображения**

❌ Укажите описание изображения.

💡 **Использование:** `/image [описание]`

📝 **Примеры:**
• `/image красивая природа с горами`
• `/image кот в космосе`
• `/image футуристический город`

🎨 **Дополнительные параметры:**
• `/image [описание] --style [стиль]` - выбрать стиль (realistic, anime, cartoon и др.)
• `/image [описание] --size [размер]` - выбрать размер (square, portrait, landscape, wide)

💡 Также можно просто написать "создай картинку [описание]"
""", parse_mode='Markdown')
        return
    
    # Парсинг аргументов для стиля и размера
    args = context.args
    prompt_parts = []
    style = None
    size = None
    
    i = 0
    while i < len(args):
        if args[i] == "--style" and i + 1 < len(args):
            style = args[i + 1].lower()
            i += 2
        elif args[i] == "--size" and i + 1 < len(args):
            size = args[i + 1].lower()
            i += 2
        else:
            prompt_parts.append(args[i])
            i += 1
    
    prompt = " ".join(prompt_parts)
    user_id = update.effective_user.id
    
    # Проверка rate limit
    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            f"⏳ Слишком много запросов. Подождите {rate_limit_middleware.time_window} секунд.",
            parse_mode=None
        )
        return
    
    await update.message.reply_chat_action("upload_photo")
    status_msg = await update.message.reply_text("🎨 Генерирую изображение...")
    
    try:
        image_bytes, strategy_name = await image_generator.generate(prompt, user_id, style=style, size=size)
        
        # Отправляем изображение
        from io import BytesIO
        photo_file = BytesIO(image_bytes)
        photo_file.name = "image.png"
        
        caption = f"✨ Изображение готово!\n\n📝 Описание: {prompt}\n💡 Использовано: {strategy_name}"
        
        await update.message.reply_photo(
            photo=photo_file,
            caption=caption,
            parse_mode=None
        )
        
        try:
            await status_msg.delete()
        except:
            pass
        
        await db.update_stats(user_id, command='image')
    except Exception as e:
        logger.error(f"Ошибка генерации изображения: {e}")
        await status_msg.edit_text(f"❌ Ошибка генерации изображения: {str(e)[:200]}")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /settings для просмотра настроек"""
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    
    if user:
        persona_name = config.PERSONAS.get(user.persona, {}).get('name', 'Помощник')
        text = f"""⚙️ **НАСТРОЙКИ БОТА**

🌐 Язык: {user.language}
🤖 Текстовая модель: {user.model if user.model != 'auto' else 'Автоматический выбор'}
🎨 Модель изображений: {user.image_model if user.image_model != 'auto' else 'Автоматический выбор'}
👤 Персонаж: {persona_name}

💡 Использование:
• /persona [название] — изменить персонажа
• Используйте меню выбора модели для изменения моделей
"""
    else:
        text = """⚙️ **НАСТРОЙКИ БОТА**

Используйте команды и меню для изменения настроек.
"""
    
    await update.message.reply_text(text, parse_mode='Markdown')
