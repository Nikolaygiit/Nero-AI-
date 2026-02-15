"""
Обработчик callback кнопок
"""
import logging
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from database import db
from services.gemini import gemini_service
from services.image_gen import image_generator
from handlers.media import handle_photo
from utils.i18n import t
import config

logger = logging.getLogger(__name__)


async def safe_callback_answer(query, text=None, show_alert=False):
    """Ответ на callback. Не падаем, если запрос устарел (Telegram даёт ~10–15 сек)."""
    try:
        await query.answer(text=text, show_alert=show_alert)
    except BadRequest as e:
        msg = str(e).lower()
        if "too old" in msg or "invalid" in msg or "expired" in msg:
            logger.debug("Callback answer skipped (query expired): %s", e)
        else:
            raise


async def show_models_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, query):
    """Вспомогательная функция для отображения меню моделей"""
    try:
        user_id = query.from_user.id
        
        # Получаем пользователя и настройки
        user = await db.get_user(user_id)
        if not user:
            await db.create_or_update_user(telegram_id=user_id)
            user = await db.get_user(user_id)
        
        current_text_model = user.model if user else 'auto'
        current_image_model = user.image_model if user else 'auto'
        
        # Получаем доступные модели
        available_models = await gemini_service.list_available_models()
        
        # Категоризируем модели
        text_models = {'pro': [], 'flash': []}
        image_models = {'premium': [], 'high': [], 'medium': []}
        
        for model in available_models:
            model_lower = model.lower()
            if 'image' in model_lower or 'imagen' in model_lower:
                if '3-pro-image' in model_lower or '4.0-ultra' in model_lower:
                    image_models['premium'].append(model)
                elif '4.0-generate' in model_lower and 'ultra' not in model_lower:
                    image_models['high'].append(model)
                elif '2.5-flash-image-preview' in model_lower:
                    image_models['high'].append(model)
                else:
                    image_models['medium'].append(model)
            elif 'pro' in model_lower and 'image' not in model_lower:
                text_models['pro'].append(model)
            elif 'flash' in model_lower and 'image' not in model_lower:
                text_models['flash'].append(model)
        
        text = f"""🤖 ВЫБОР МОДЕЛИ GEMINI

✅ Текущая текстовая модель: {current_text_model if current_text_model != 'auto' else 'Автоматический выбор'}
✅ Текущая модель изображений: {current_image_model if current_image_model != 'auto' else 'Автоматический выбор'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 ТЕКСТОВЫЕ МОДЕЛИ GEMINI

"""
        
        keyboard = []
        
        # Добавляем кнопки для текстовых моделей
        pro_models = text_models['pro'][:2]
        flash_models = text_models['flash'][:2]
        
        if pro_models:
            pro_buttons = []
            for model in pro_models:
                model_short = model.replace('gemini-', '').replace('-preview', '').replace('-pro', ' Pro').title()
                if current_text_model == model:
                    pro_buttons.append(InlineKeyboardButton(f"✅ {model_short[:18]}", callback_data=f"set_text_model_{model}"))
                else:
                    pro_buttons.append(InlineKeyboardButton(f"🔥 {model_short[:18]}", callback_data=f"set_text_model_{model}"))
            if pro_buttons:
                keyboard.append(pro_buttons[:2] if len(pro_buttons) >= 2 else pro_buttons)
        
        if flash_models:
            flash_buttons = []
            for model in flash_models:
                model_short = model.replace('gemini-', '').replace('-preview', '').replace('-flash', ' Flash').title()
                if current_text_model == model:
                    flash_buttons.append(InlineKeyboardButton(f"✅ {model_short[:18]}", callback_data=f"set_text_model_{model}"))
                else:
                    flash_buttons.append(InlineKeyboardButton(f"⚡ {model_short[:18]}", callback_data=f"set_text_model_{model}"))
            if flash_buttons:
                keyboard.append(flash_buttons[:2] if len(flash_buttons) >= 2 else flash_buttons)
        
        # Кнопка автоматического выбора для текста
        if current_text_model == 'auto':
            keyboard.append([InlineKeyboardButton("✅ Автоматический выбор (текст)", callback_data="set_text_model_auto")])
        else:
            keyboard.append([InlineKeyboardButton("🔄 Автоматический выбор (текст)", callback_data="set_text_model_auto")])
        
        text += "\n🎨 МОДЕЛИ ДЛЯ ИЗОБРАЖЕНИЙ GEMINI\n\n"
        
        # Добавляем кнопки для моделей изображений
        premium_models = image_models['premium'][:2]
        high_models = image_models['high'][:2]
        medium_models = image_models['medium'][:2]
        
        if premium_models:
            premium_buttons = []
            for model in premium_models:
                model_short = model.replace('gemini-', '').replace('-preview', '').replace('-image', ' Img').replace('-pro', ' Pro').replace('imagen-', '').replace('-ultra-generate-001', ' Ultra').replace('-generate-001', '').title()
                if current_image_model == model:
                    premium_buttons.append(InlineKeyboardButton(f"✅ {model_short[:18]}", callback_data=f"set_image_model_{model}"))
                else:
                    premium_buttons.append(InlineKeyboardButton(f"🔴 {model_short[:18]}", callback_data=f"set_image_model_{model}"))
            if premium_buttons:
                keyboard.append(premium_buttons[:2] if len(premium_buttons) >= 2 else premium_buttons)
        
        if high_models:
            high_buttons = []
            for model in high_models:
                model_short = model.replace('gemini-', '').replace('-preview', '').replace('-image', ' Img').replace('-flash', ' Flash').replace('imagen-', '').replace('-fast-generate-001', ' Fast').replace('-generate-001', '').title()
                if current_image_model == model:
                    high_buttons.append(InlineKeyboardButton(f"✅ {model_short[:18]}", callback_data=f"set_image_model_{model}"))
                else:
                    high_buttons.append(InlineKeyboardButton(f"🟠 {model_short[:18]}", callback_data=f"set_image_model_{model}"))
            if high_buttons:
                keyboard.append(high_buttons[:2] if len(high_buttons) >= 2 else high_buttons)
        
        if medium_models:
            medium_buttons = []
            for model in medium_models:
                model_short = model.replace('gemini-', '').replace('-image', ' Img').replace('-flash', ' Flash').replace('imagen-', '').replace('-fast-generate-001', ' Fast').replace('-generate-001', '').title()
                if current_image_model == model:
                    medium_buttons.append(InlineKeyboardButton(f"✅ {model_short[:18]}", callback_data=f"set_image_model_{model}"))
                else:
                    medium_buttons.append(InlineKeyboardButton(f"🟡 {model_short[:18]}", callback_data=f"set_image_model_{model}"))
            if medium_buttons:
                keyboard.append(medium_buttons[:2] if len(medium_buttons) >= 2 else medium_buttons)
        
        # Кнопка автоматического выбора для изображений
        if current_image_model == 'auto':
            keyboard.append([InlineKeyboardButton("✅ Автоматический выбор (изображения)", callback_data="set_image_model_auto")])
        else:
            keyboard.append([InlineKeyboardButton("🔄 Автоматический выбор (изображения)", callback_data="set_image_model_auto")])
        
        keyboard.append([InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Безопасное редактирование сообщения
        try:
            message = query.message
            if message.photo and not message.text:
                await query.message.reply_text(text, parse_mode=None, reply_markup=reply_markup)
            else:
                await query.edit_message_text(text, parse_mode=None, reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение, отправляем новое: {e}")
            await query.message.reply_text(text, parse_mode=None, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка в show_models_menu: {e}", exc_info=True)
        await safe_callback_answer(
            query,
            "❌ Произошла ошибка при загрузке меню моделей. Пожалуйста, попробуйте еще раз.",
            show_alert=True,
        )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий на кнопки"""
    query = update.callback_query
    
    if not query:
        logger.error("button_callback вызван без callback_query")
        return
    
    data = query.data
    user_id = query.from_user.id

    if await db.is_banned(user_id):
        await safe_callback_answer(query, "⛔ Вы заблокированы.", show_alert=True)
        return

    logger.debug(f"Обработка callback: {data} от пользователя {user_id}")
    
    # Вспомогательная функция для безопасного редактирования сообщений
    async def safe_edit_message(text, reply_markup=None):
        try:
            message = query.message
            if message.photo and not message.text:
                await query.message.reply_text(text, parse_mode=None, reply_markup=reply_markup)
            else:
                await query.edit_message_text(text, parse_mode=None, reply_markup=reply_markup)
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение, отправляем новое: {e}")
            await query.message.reply_text(text, parse_mode=None, reply_markup=reply_markup)
    
    # Главное меню
    if data == "menu_main":
        await safe_callback_answer(query, "🏠 Возвращаемся в главное меню...")
        user_name = query.from_user.first_name or "друг"
        
        # Получаем статистику из базы данных
        stats = await db.get_stats(user_id)
        requests_count = stats.requests_count if stats else 0
        
        # Получаем количество моделей
        available_models = await gemini_service.list_available_models()
        image_models = [m for m in available_models if 'image' in m.lower() or 'imagen' in m.lower()]
        image_count = len(image_models) if image_models else 9
        
        menu_text = f"""🌟 Добро пожаловать, {user_name}!

Рад познакомиться! Я — твой умный помощник на базе Gemini AI от Google.
Спроси меня о чём угодно — отвечу, помогу, создам или переведу.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💬 **Что я умею:**

• 💬 Умный диалог с контекстом
• 🎨 Генерация изображений ({image_count} моделей)
• 📸 Анализ фотографий через Vision AI
• 💻 Генерация кода с подсветкой
• 🌐 Переводы на 10+ языков
• 📝 Сокращение и объяснение текстов
• 🎯 Викторины и калькулятор
• 📚 Поиск в Wikipedia

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 **Ваша статистика:** {requests_count} запросов

💡 Просто напишите вопрос — я отвечу!

❓ Поддержка: @nik_solt
"""
        
        keyboard = [
            [
                InlineKeyboardButton("💬 Чат с Gemini", callback_data="menu_chat"),
                InlineKeyboardButton("🎨 Создать изображение", callback_data="menu_create_image")
            ],
            [
                InlineKeyboardButton("🤖 Выбрать модель", callback_data="menu_models"),
                InlineKeyboardButton("👤 Персонажи", callback_data="menu_personas")
            ],
            [
                InlineKeyboardButton("📸 Анализ фото", callback_data="menu_photo_analysis"),
                InlineKeyboardButton("💻 Генерация кода", callback_data="menu_code_gen")
            ],
            [
                InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
                InlineKeyboardButton("⚙️ Настройки", callback_data="menu_settings_new")
            ]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(menu_text, reply_markup)
        return
    
    # Меню чата
    elif data == "menu_chat":
        await safe_callback_answer(query, "💬 Чат с Gemini...")
        text = """💬 ЧАТ С GEMINI

Просто напишите вопрос или запрос, и я отвечу используя модели Gemini!

🤖 Доступные модели:
• Gemini 3 Pro — для сложных задач
• Gemini 3 Flash — быстрая модель
• Gemini 2.5 Pro — продвинутая модель
• Gemini 2.5 Flash — для повседневных задач

💡 Возможности:
• Работа с текстом, голосом и изображениями
• Анализ до 10 картинок в одном запросе
• Генерация кода с подсветкой синтаксиса
• 10 уникальных персонажей

📝 Просто напишите сообщение боту, и он ответит!
"""
        keyboard = [
            [InlineKeyboardButton("👤 Выбрать персонажа", callback_data="menu_personas")],
            [InlineKeyboardButton("🤖 Выбрать модель", callback_data="menu_models")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(text, reply_markup)
        return
    
    # Меню создания изображений
    elif data == "menu_create_image":
        await safe_callback_answer(query, "🎨 Создание изображения...")
        text = """🎨 СОЗДАНИЕ ИЗОБРАЖЕНИЙ

💡 Использование: /image [описание] или просто напишите "создай картинку [описание]"

📝 Примеры:
• создай картинку красивая природа с горами
• создай фото кот в космосе
• создай изображение футуристический город

✨ Просто напишите "создай картинку [описание]" и я создам!

🤖 Доступные модели Gemini:
🔴 Премиум — Gemini 3 Pro Image Preview
🟠 Высокое качество — Imagen 4.0, Gemini 2.5 Flash Image Preview
🟡 Среднее качество — Gemini 2.5 Flash Image, Imagen 3.0

⏱️ Время генерации: 10-180 секунд
"""
        keyboard = [
            [InlineKeyboardButton("🤖 Выбрать модель", callback_data="menu_models")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(text, reply_markup)
        return
    
    # Меню выбора моделей
    elif data == "menu_models":
        await safe_callback_answer(query, "🤖 Выбор модели...")
        await show_models_menu(update, context, query)
        return
    
    # Установка текстовой модели
    elif data.startswith("set_text_model_"):
        model_key = data.replace("set_text_model_", "")
        await safe_callback_answer(query, f"✅ Текстовая модель установлена: {model_key if model_key != 'auto' else 'Автоматический выбор'}")
        await db.create_or_update_user(telegram_id=user_id, model=model_key)
        await show_models_menu(update, context, query)
        return
    
    # Установка модели изображений
    elif data.startswith("set_image_model_"):
        model_key = data.replace("set_image_model_", "")
        await safe_callback_answer(query, f"✅ Модель изображений установлена: {model_key if model_key != 'auto' else 'Автоматический выбор'}")
        await db.create_or_update_user(telegram_id=user_id, image_model=model_key)
        await show_models_menu(update, context, query)
        return
    
    # Меню персонажей
    elif data == "menu_personas" or data == "menu_persona":
        await safe_callback_answer(query, "👤 Выбор персонажа...")
        user = await db.get_user(user_id)
        current_persona_key = user.persona if user else 'assistant'
        current_persona_name = config.PERSONAS.get(current_persona_key, {}).get('name', 'Помощник')
        
        text = f"""👤 ВЫБОР ПЕРСОНАЖА

Выберите стиль общения:

🎓 Учитель — объясняет сложные темы простым языком
💻 Программист — помогает с кодом и техническими вопросами
🤝 Помощник — универсальный помощник для любых задач
🎨 Креативщик — творческий подход к задачам
📊 Аналитик — анализирует данные и делает выводы
🌐 Переводчик — помогает с переводами
✍️ Писатель — помогает с текстами и сочинениями
🔬 Ученый — научный подход к вопросам
💼 Бизнес-консультант — деловой стиль общения
🧠 Психолог — помогает с психологическими вопросами

✅ Текущий: {current_persona_name}

💡 Используйте кнопки ниже или команду /persona [название]
"""
        keyboard = [
            [
                InlineKeyboardButton("🎓 Учитель", callback_data="set_persona_teacher"),
                InlineKeyboardButton("💻 Программист", callback_data="set_persona_programmer")
            ],
            [
                InlineKeyboardButton("🤝 Помощник", callback_data="set_persona_assistant"),
                InlineKeyboardButton("🎨 Креативщик", callback_data="set_persona_creative")
            ],
            [
                InlineKeyboardButton("📊 Аналитик", callback_data="set_persona_analyst"),
                InlineKeyboardButton("🌐 Переводчик", callback_data="set_persona_translator")
            ],
            [
                InlineKeyboardButton("✍️ Писатель", callback_data="set_persona_writer"),
                InlineKeyboardButton("🔬 Ученый", callback_data="set_persona_scientist")
            ],
            [
                InlineKeyboardButton("💼 Бизнес", callback_data="set_persona_business"),
                InlineKeyboardButton("🧠 Психолог", callback_data="set_persona_psychologist")
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(text, reply_markup)
        return
    
    # Установка персонажа
    elif data.startswith("set_persona_"):
        persona_key = data.replace("set_persona_", "")
        if persona_key in config.PERSONAS:
            persona_info = config.PERSONAS[persona_key]
            await safe_callback_answer(query, f"✅ Установлен: {persona_info['name']}")
            await db.create_or_update_user(telegram_id=user_id, persona=persona_key)
            
            # Возвращаемся в меню персонажей
            user = await db.get_user(user_id)
            current_persona_key = user.persona if user else 'assistant'
            current_persona_name = config.PERSONAS.get(current_persona_key, {}).get('name', 'Помощник')
            
            text = f"""👤 ВЫБОР ПЕРСОНАЖА

Выберите стиль общения:

🎓 Учитель — объясняет сложные темы простым языком
💻 Программист — помогает с кодом и техническими вопросами
🤝 Помощник — универсальный помощник для любых задач
🎨 Креативщик — творческий подход к задачам
📊 Аналитик — анализирует данные и делает выводы
🌐 Переводчик — помогает с переводами
✍️ Писатель — помогает с текстами и сочинениями
🔬 Ученый — научный подход к вопросам
💼 Бизнес-консультант — деловой стиль общения
🧠 Психолог — помогает с психологическими вопросами

✅ Текущий: {current_persona_name}

💡 Используйте кнопки ниже или команду /persona [название]
"""
            keyboard = [
                [
                    InlineKeyboardButton("🎓 Учитель", callback_data="set_persona_teacher"),
                    InlineKeyboardButton("💻 Программист", callback_data="set_persona_programmer")
                ],
                [
                    InlineKeyboardButton("🤝 Помощник", callback_data="set_persona_assistant"),
                    InlineKeyboardButton("🎨 Креативщик", callback_data="set_persona_creative")
                ],
                [
                    InlineKeyboardButton("📊 Аналитик", callback_data="set_persona_analyst"),
                    InlineKeyboardButton("🌐 Переводчик", callback_data="set_persona_translator")
                ],
                [
                    InlineKeyboardButton("✍️ Писатель", callback_data="set_persona_writer"),
                    InlineKeyboardButton("🔬 Ученый", callback_data="set_persona_scientist")
                ],
                [
                    InlineKeyboardButton("💼 Бизнес", callback_data="set_persona_business"),
                    InlineKeyboardButton("🧠 Психолог", callback_data="set_persona_psychologist")
                ],
                [InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await safe_edit_message(text, reply_markup)
        return
    
    # Меню анализа фото
    elif data == "menu_photo_analysis":
        await safe_callback_answer(query, "📸 Анализ фото...")
        text = """📸 АНАЛИЗ ФОТО

📸 Анализ изображений через Gemini Vision:
Загрузите фото, и бот проанализирует его содержимое.

💡 Примеры использования:
• Загрузите фото с подписью "Опиши это изображение"
• Загрузите фото с подписью "Что на этом фото?"

🤖 Используется: Gemini Vision для анализа изображений
"""
        keyboard = [
            [InlineKeyboardButton("🎨 Создать изображение", callback_data="menu_create_image")],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(text, reply_markup)
        return
    
    # Меню генерации кода
    elif data == "menu_code_gen":
        await safe_callback_answer(query, "💻 Генерация кода...")
        text = """💻 ГЕНЕРАЦИЯ КОДА

💡 Использование: /code [запрос]

📝 Примеры:
• /code функция сортировки на Python
• /code класс для работы с API на JavaScript
• /code алгоритм бинарного поиска

✨ Код будет отформатирован с подсветкой синтаксиса!

🤖 Используется: Gemini для генерации кода
"""
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(text, reply_markup)
        return
    
    # Меню статистики
    elif data == "menu_stats":
        await safe_callback_answer(query, "📊 Загружаю статистику...")
        stats = await db.get_stats(user_id)
        
        if stats:
            days_active = max((datetime.now() - stats.start_date).days, 1) if stats.start_date else 1
            avg_requests_per_day = stats.requests_count / days_active if days_active > 0 else 0
            avg_tokens_per_request = stats.tokens_used / max(stats.requests_count, 1)
            
            text = f"""📊 ВАША СТАТИСТИКА

📝 Запросов: {stats.requests_count}
🎨 Изображений: {stats.images_generated}
🔤 Токенов использовано: {stats.tokens_used:,}
📅 Дней активен: {days_active}
📈 Среднее в день: {avg_requests_per_day:.1f} запросов
🔤 Среднее токенов: {avg_tokens_per_request:.0f} на запрос
"""
        else:
            text = """📊 ВАША СТАТИСТИКА

📝 Запросов: 0
🎨 Изображений: 0
🔤 Токенов использовано: 0

💡 Начните использовать бота для накопления статистики!
"""
        
        keyboard = [[InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(text, reply_markup)
        return
    
    # Меню настроек
    elif data == "menu_settings_new":
        await safe_callback_answer(query, "⚙️ Открываю настройки...")
        user = await db.get_user(user_id)
        
        if user:
            persona_name = config.PERSONAS.get(user.persona, {}).get('name', 'Помощник')
            text = f"""⚙️ НАСТРОЙКИ БОТА

🌐 Язык: {user.language}
🤖 Текстовая модель: {user.model if user.model != 'auto' else 'Автоматический выбор'}
🎨 Модель изображений: {user.image_model if user.image_model != 'auto' else 'Автоматический выбор'}
👤 Персонаж: {persona_name}

💡 Использование:
• /persona [название] — изменить персонажа
• Используйте меню выбора модели для изменения моделей
"""
        else:
            text = """⚙️ НАСТРОЙКИ БОТА

Используйте кнопки ниже для изменения настроек.
"""
        
        keyboard = [
            [
                InlineKeyboardButton("👤 Изменить персонажа", callback_data="menu_personas"),
                InlineKeyboardButton("🤖 Выбрать модель", callback_data="menu_models")
            ],
            [InlineKeyboardButton("⬅️ Назад", callback_data="menu_main")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await safe_edit_message(text, reply_markup)
        return
    
    # Перегенерировать ответ (Retry) — в callback_data: retry_{user_id} или retry_{user_id}_{request_id}
    elif data.startswith("retry_"):
        parts = data.split("_", 2)  # ["retry", user_id] или ["retry", user_id, request_id]
        request_id = parts[2] if len(parts) >= 3 else None
        ud = context.user_data or {}
        prompt = ud.get("prompts", {}).get(request_id) if request_id else ud.get("last_prompt")
        if not prompt:
            await safe_callback_answer(query, "Нет запроса для перегенерации", show_alert=True)
            return
        await safe_callback_answer(query, "🔄 Перегенерирую...")
        from handlers.chat_utils import generate_and_reply_text
        from utils.text_tools import sanitize_markdown
        from services.rag import get_rag_context
        try:
            await query.message.delete()
        except Exception:
            pass
        status_msg = await query.message.reply_text(t("thinking"))
        rag_context = await get_rag_context(user_id, prompt)
        try:
            response = await generate_and_reply_text(
                chat=query.message.chat,
                user_id=user_id,
                prompt=prompt,
                context=context,
                rag_context=rag_context,
            )
            await status_msg.delete()
            # Новый request_id для этого ответа — кнопка «Перегенерировать» под ним снова перезапустит тот же промпт
            new_req_id = uuid.uuid4().hex[:8]
            if "prompts" not in context.user_data:
                context.user_data["prompts"] = {}
            context.user_data["prompts"][new_req_id] = prompt
            prompts_dict = context.user_data["prompts"]
            if len(prompts_dict) > 20:
                for k in list(prompts_dict.keys())[:-20]:
                    del prompts_dict[k]
            keyboard = [
                [
                    InlineKeyboardButton(t("btn_favorite"), callback_data=f"fav_{user_id}"),
                    InlineKeyboardButton(t("btn_regenerate"), callback_data=f"retry_{user_id}_{new_req_id}"),
                ],
                [InlineKeyboardButton(t("btn_rephrase"), callback_data=f"rephrase_{user_id}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            safe = sanitize_markdown(response)
            try:
                await query.message.reply_text(safe, parse_mode="Markdown", reply_markup=reply_markup)
            except BadRequest as e:
                if "parse" in str(e).lower() or "entities" in str(e).lower():
                    await query.message.reply_text(response, parse_mode=None, reply_markup=reply_markup)
                else:
                    raise
        except Exception as e:
            logger.error("Retry error: %s", e)
            await status_msg.edit_text(t("error_generic") + f": {str(e)[:200]}")
        return

    # Обработка избранного
    elif data.startswith("fav_"):
        original_text = query.message.text or query.message.caption or ""
        
        await db.add_favorite(
            user_id=user_id,
            content=original_text,
            content_type='image' if query.message.photo else 'text'
        )
        
        await safe_callback_answer(query, t("favorite_added"))
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except:
            pass
    
    # Переанализ фото
    elif data.startswith("reanalyze_"):
        await safe_callback_answer(query, "🔄 Переанализирую фото...")
        if query.message.photo:
            try:
                # Создаем временный Update объект для анализа
                class TempUpdate:
                    def __init__(self, message):
                        self.message = message
                        self.effective_user = message.from_user
                        self.effective_chat = message.chat
                
                temp_update = TempUpdate(query.message)
                await handle_photo(temp_update, context)
            except Exception as e:
                logger.error(f"Ошибка переанализа фото: {e}")
                await safe_callback_answer(query, f"❌ Ошибка переанализа: {str(e)[:100]}", show_alert=True)
    
    # Остальные обработчики (regenerate, rephrase и т.д.) можно добавить позже
    else:
        logger.warning(f"Неизвестный callback: {data}")
