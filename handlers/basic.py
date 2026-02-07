"""
Базовые команды бота (/start, /help, /clear)
"""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from services.gemini import gemini_service
from utils.analytics import track
import config

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start"""
    user_id = update.effective_user.id
    user_name = update.effective_user.first_name or "друг"

    if await db.is_banned(user_id):
        await update.message.reply_text("⛔ Вы заблокированы и не можете использовать бота.")
        return

    # Создаем или обновляем пользователя в базе данных
    await db.create_or_update_user(
        telegram_id=user_id,
        username=update.effective_user.username,
        first_name=user_name,
        language='ru'
    )
    
    # Получаем статистику
    stats = await db.get_stats(user_id)
    requests_count = stats.requests_count if stats else 0
    
    # Получаем количество доступных моделей
    available_models = await gemini_service.list_available_models()
    image_models = [m for m in available_models if 'image' in m.lower() or 'imagen' in m.lower()]
    image_count = len(image_models) if image_models else 9
    
    # Приветствие
    welcome_text = f"""🌟 Добро пожаловать, {user_name}!

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
    
    # Кнопки навигации
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
    
    await update.message.reply_text(
        welcome_text,
        parse_mode=None,
        reply_markup=reply_markup
    )
    
    await db.update_stats(user_id, command='start')
    track("started_bot", str(user_id))
    
    # Получаем пользователя для проверки
    user = await db.get_user(user_id)
    if not user:
        await db.create_or_update_user(telegram_id=user_id, first_name=user_name)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /help"""
    help_text = """
📚 **Справка по командам бота**

**Основные команды:**
/start ── 🚀 Начать работу с ботом
/help ── 📚 Показать эту справку
/clear ── 🗑️ Очистить историю диалога

**Персонализация:**
/persona ── 👤 Выбрать персонажа (10 вариантов)
/settings ── ⚙️ Настройки бота

**Генерация контента:**
/image [описание] ── 🎨 Сгенерировать изображение
/code [запрос] ── 💻 Сгенерировать код

**База знаний (RAG):**
📎 Отправьте **PDF** — бот добавит его и будет отвечать по документу
/docs ── 📚 Список ваших загруженных документов
/docs_clear ── 🗑️ Удалить все документы из базы знаний

**Утилиты:**
/translate [язык] [текст] ── 🌐 Перевести текст
/summarize [текст] ── 📝 Сократить текст
/explain [термин] ── 💡 Объяснить термин
/quiz [тема] ── 🎯 Создать викторину
/calculator [выражение] ── 🔢 Вычислить
/wiki [запрос] ── 📚 Поиск в Wikipedia

💡 Используйте кнопки в главном меню для быстрого доступа!
"""
    
    keyboard = [[InlineKeyboardButton("🏠 Главное меню", callback_data="menu_main")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(help_text, parse_mode='Markdown', reply_markup=reply_markup)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /clear - очистка истории диалога"""
    user_id = update.effective_user.id
    
    # Очищаем историю в базе данных
    await db.clear_user_messages(user_id)
    
    success_msg = """
✅ **История очищена!**

💡 Теперь бот начнет диалог с чистого листа
"""
    
    await update.message.reply_text(success_msg, parse_mode='Markdown')
