"""
Telegram Stars — оплата и подписка
"""
import logging
from telegram import Update, LabeledPrice
from telegram.ext import ContextTypes

from database import db

logger = logging.getLogger(__name__)

# Стоимость подписки в звёздах (1 Star ≈ $0.013)
SUBSCRIPTION_STARS = 99


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /subscribe — показать кнопку оплаты"""
    user_id = update.effective_user.id
    is_premium = await db.is_premium(user_id)
    if is_premium:
        await update.message.reply_text("💎 У вас уже активна премиум-подписка!")
        return

    await update.message.reply_invoice(
        title="Nero AI — Премиум",
        description="Безлимитные запросы на 30 дней",
        payload=f"sub_{user_id}",
        provider_token="",  # Для Stars provider_token не нужен
        currency="XTR",  # Telegram Stars
        prices=[LabeledPrice(label="Премиум 30 дней", amount=SUBSCRIPTION_STARS)],
    )


async def pre_checkout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение платежа"""
    query = update.pre_checkout_query
    await query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Успешная оплата — активируем подписку"""
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    if payload.startswith("sub_"):
        user_id = int(payload.split("_")[1])
        await db.set_premium(user_id)
        await update.message.reply_text("💎 Спасибо! Премиум-подписка активирована.")
        logger.info("Premium activated for user %s", user_id)
