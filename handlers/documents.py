"""
Обработка загруженных документов (PDF) для RAG.
Пользователь отправляет PDF — бот извлекает текст, чанкует, строит эмбеддинги и сохраняет в ChromaDB.
"""

import logging

from telegram import Update
from telegram.ext import ContextTypes

from database import db
from middlewares.rate_limit import rate_limit_middleware
from middlewares.usage_limit import check_can_make_request
from services.rag import add_pdf_document, clear_rag_documents, list_rag_documents

logger = logging.getLogger(__name__)

# Максимальный размер PDF (20 MB) — лимит Telegram для файлов 50 MB, но большие долго качать
MAX_PDF_BYTES = 20 * 1024 * 1024


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка отправленного документа. Поддерживается PDF для RAG."""
    user_id = update.effective_user.id
    if await db.is_banned(user_id):
        await update.message.reply_text("⛔ Вы заблокированы.")
        return

    doc = update.message.document
    if not doc:
        return
    filename = (doc.file_name or "").lower()
    if not filename.endswith(".pdf"):
        await update.message.reply_text(
            "📎 Сейчас поддерживаются только **PDF**-файлы для базы знаний.\n"
            "Отправьте PDF — я добавлю его в контекст и буду отвечать по нему.",
            parse_mode="Markdown",
        )
        return

    if doc.file_size and doc.file_size > MAX_PDF_BYTES:
        await update.message.reply_text(
            f"⚠️ Файл слишком большой (макс. {MAX_PDF_BYTES // (1024 * 1024)} МБ). Отправьте меньший PDF."
        )
        return

    if not await rate_limit_middleware.check_rate_limit(user_id):
        await update.message.reply_text(
            "⏳ Слишком много запросов. Подождите минуту.", parse_mode=None
        )
        return
    can_proceed, limit_msg = await check_can_make_request(user_id)
    if not can_proceed:
        await update.message.reply_text(limit_msg, parse_mode=None)
        return

    status_msg = await update.message.reply_text("📄 Читаю PDF и добавляю в базу знаний...")
    try:
        file = await context.bot.get_file(doc.file_id)
        pdf_bytes = await file.download_as_bytearray()
        pdf_bytes = bytes(pdf_bytes)
        ok, message = await add_pdf_document(user_id, pdf_bytes, doc.file_name or "document.pdf")
        await status_msg.edit_text(message, parse_mode=None)
    except Exception as e:
        logger.exception("RAG document processing failed: %s", e)
        await status_msg.edit_text(
            f"❌ Ошибка обработки PDF: {str(e)[:300]}\n\n"
            "Убедитесь, что файл — это текстный PDF (не скан без OCR).",
            parse_mode=None,
        )


async def rag_docs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /docs — список загруженных документов RAG."""
    user_id = update.effective_user.id
    names = await list_rag_documents(user_id)
    if not names:
        await update.message.reply_text(
            "📚 У вас пока нет загруженных документов.\n\n"
            "Отправьте боту **PDF** (инструкцию, книгу, конспект) — я добавлю его в базу знаний и буду отвечать по нему.",
            parse_mode="Markdown",
        )
        return
    text = "📚 Ваши документы в базе знаний:\n\n• " + "\n• ".join(names[:30])
    if len(names) > 30:
        text += f"\n\n... и ещё {len(names) - 30}."
    await update.message.reply_text(text, parse_mode=None)


async def rag_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /docs_clear — удалить все свои документы из RAG."""
    user_id = update.effective_user.id
    count = await clear_rag_documents(user_id)
    if count == 0:
        await update.message.reply_text("У вас нет загруженных документов для удаления.")
        return
    await update.message.reply_text(f"✅ Удалено документов из базы знаний: {count} фрагментов.")
