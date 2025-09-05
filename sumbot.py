import os
import asyncio
import logging
import telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Включаем логирование, чтобы видеть, что происходит
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# --- Константы и токены ---
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")

# Проверяем, где запущен бот - на Render или локально
TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL")
IS_RUNNING_ON_RENDER = os.getenv("RENDER") == "true"

# --- Команды и обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет простое приветственное сообщение.
    Эта функция проверяет, что бот успешно подключился к Telegram.
    """
    await update.message.reply_text("Привет! Я работаю.")

# --- Функции запуска для разных режимов ---
async def run_webhook_bot():
    """Запускает бота в режиме webhook для Render."""
    if not TELEGRAM_WEBHOOK_URL:
        logging.error("Ошибка: Бот запущен на Render, но переменная TELEGRAM_WEBHOOK_URL не найдена. Пожалуйста, добавьте ее.")
        return
    
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    app.add_handler(CommandHandler("start", start))

    try:
        # Удаляем все старые вебхуки, чтобы избежать конфликта
        await app.bot.delete_webhook()
        # Устанавливаем новый вебхук
        await app.bot.set_webhook(url=TELEGRAM_WEBHOOK_URL)
        logging.info("Бот запущен в режиме webhook на Render.")
        # Запускаем сервер для обработки запросов
        await app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "8080")),
            url_path="/",
            webhook_url=TELEGRAM_WEBHOOK_URL
        )
    except telegram.error.Conflict as e:
        logging.error(f"Конфликт вебхука: {e}. Похоже, бот уже запущен в другом месте.")
    except Exception as e:
        logging.error(f"Критическая ошибка при запуске в режиме webhook: {e}")

async def run_polling_bot():
    """Запускает бота в режиме polling для локальной отладки."""
    logging.info("Бот запущен в режиме polling (локально).")
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    app.add_handler(CommandHandler("start", start))
    await app.run_polling()

# --- Главная точка входа ---
if __name__ == "__main__":
    if not TOKEN_TELEGRAM:
        logging.error("Ошибка: Переменная TELEGRAM_TOKEN не найдена.")
    else:
        if IS_RUNNING_ON_RENDER:
            asyncio.run(run_webhook_bot())
        else:
            asyncio.run(run_polling_bot())
