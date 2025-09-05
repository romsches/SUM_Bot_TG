import os
import asyncio
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Включаем логирование, чтобы видеть, что происходит
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# --- Константы и токены ---
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL")
IS_RUNNING_ON_RENDER = os.getenv("RENDER") == "true"

# --- Команды и обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Отправляет простое приветственное сообщение.
    Эта функция проверяет, что бот успешно подключился к Telegram.
    """
    await update.message.reply_text("Привет!")

# --- Запуск бота (с автоматическим выбором режима) ---
async def main():
    """Главная асинхронная функция для запуска бота."""
    if not TOKEN_TELEGRAM:
        logging.error("Ошибка: Переменная TELEGRAM_TOKEN не найдена. Пожалуйста, добавьте ее.")
        return
    
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    # Добавляем обработчик команды /start
    app.add_handler(CommandHandler("start", start))

    if IS_RUNNING_ON_RENDER:
        if not TELEGRAM_WEBHOOK_URL:
            logging.error("Ошибка: Бот запущен на Render, но переменная TELEGRAM_WEBHOOK_URL не найдена. Пожалуйста, добавьте ее.")
            return
        
        try:
            # Сначала удаляем все старые вебхуки, чтобы избежать конфликта
            await app.bot.delete_webhook()
            await app.bot.set_webhook(url=TELEGRAM_WEBHOOK_URL)
            logging.info("Бот запущен в режиме webhook на Render.")
            await app.run_webhook(
                listen="0.0.0.0",
                port=int(os.getenv("PORT", "8080")),
                url_path="/",
                webhook_url=TELEGRAM_WEBHOOK_URL
            )
        except Exception as e:
            logging.error(f"Ошибка при запуске webhook: {e}")
            
    else:
        logging.info("Бот запущен в режиме polling (локально).")
        await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
