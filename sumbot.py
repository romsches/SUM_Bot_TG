import os
import asyncio
import requests
import telegram
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from bs4 import BeautifulSoup
import telegram.constants

# Включаем логирование, чтобы видеть ошибки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# --- Константы и токены ---
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

# Переменные для работы с Render
TELEGRAM_WEBHOOK_URL = os.getenv("TELEGRAM_WEBHOOK_URL")
IS_RUNNING_ON_RENDER = os.getenv("RENDER") == "true"

# URL-адреса API для суммаризации и перевода
API_SUMMARY = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
API_TRANSLATE = {
    "en": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-en",
    "de": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-de",
    "ru": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-ru"
}
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

# --- Вспомогательные функции (выполняются в отдельном потоке) ---
def get_text_from_url_sync(url):
    """Синхронно извлекает основной текст статьи с веб-страницы."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        paragraphs = soup.find_all("p")
        article_text = "\n".join([p.get_text() for p in paragraphs])
        return article_text
    except requests.exceptions.RequestException as e:
        logging.error(f"Ошибка при запросе URL: {e}")
        return None

def summarize_with_api_sync(text):
    """Синхронно отправляет текст на суммаризацию."""
    if not HF_TOKEN:
        raise ValueError("HF_TOKEN не установлен.")
    payload = {"inputs": text, "parameters": {"min_length": 50, "max_length": 150}}
    response = requests.post(API_SUMMARY, headers=headers, json=payload)
    response.raise_for_status()
    summary = response.json()[0]['summary_text']
    return summary

def translate_with_api_sync(text, lang):
    """Синхронно переводит текст с помощью API Hugging Face."""
    if not HF_TOKEN:
        raise ValueError("HF_TOKEN не установлен.")
    if lang not in API_TRANSLATE:
        raise ValueError("Неподдерживаемый язык.")
    payload = {"inputs": text}
    response = requests.post(API_TRANSLATE[lang], headers=headers, json=payload)
    response.raise_for_status()
    translated_text = response.json()[0]['translation_text']
    return translated_text

# --- Команды и обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет простое приветственное сообщение."""
    await update.message.reply_text("Привет! Отправьте мне ссылку на статью, и я сделаю краткий отчёт.")

async def summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Суммаризирует текст статьи по ссылке."""
    url = update.message.text
    await update.message.reply_text("Получаю текст и делаю отчёт...")
    
    try:
        # Запускаем синхронные функции в отдельном потоке, чтобы не блокировать бота
        article_text = await asyncio.get_event_loop().run_in_executor(None, get_text_from_url_sync, url)
        if not article_text:
            await update.message.reply_text("Не удалось получить текст по этой ссылке. Пожалуйста, проверьте URL.")
            return

        summary = await asyncio.get_event_loop().run_in_executor(None, summarize_with_api_sync, article_text[:2000])
        
        # Сохраняем в контекст, чтобы потом перевести
        context.user_data["summary"] = summary
        
        # Кнопки выбора языка
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="en")],
            [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="de")],
            [InlineKeyboardButton("Русский 🇷🇺", callback_data="ru")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text("Готово! На каком языке показать отчёт?", reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки выбора языка."""
    query = update.callback_query
    await query.answer()
    
    lang = query.data
    summary = context.user_data.get("summary", "Нет текста для перевода.")
    
    await query.edit_message_text("Перевожу...")
    
    try:
        # Запускаем синхронную функцию перевода в отдельном потоке
        translated = await asyncio.get_event_loop().run_in_executor(None, translate_with_api_sync, summary, lang)
        await query.edit_message_text(f"📌 Итоговый отчёт:\n\n{translated}", parse_mode=telegram.constants.ParseMode.MARKDOWN_V2)
    except Exception as e:
        await query.edit_message_text(f"Ошибка при переводе: {e}")

# --- Запуск бота (с автоматическим выбором режима) ---
async def main():
    """Главная асинхронная функция для запуска бота."""
    if not TOKEN_TELEGRAM:
        logging.error("Ошибка: Переменная TELEGRAM_TOKEN не найдена. Пожалуйста, добавьте ее.")
        return
    if not HF_TOKEN:
        logging.error("Ошибка: Переменная HF_TOKEN не найдена. Пожалуйста, добавьте ее.")
        return

    app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, summarize))
    app.add_handler(CallbackQueryHandler(button))

    # Определяем, где запущен бот
    if IS_RUNNING_ON_RENDER:
        if not TELEGRAM_WEBHOOK_URL:
            logging.error("Ошибка: Бот запущен на Render, но переменная TELEGRAM_WEBHOOK_URL не найдена. Пожалуйста, добавьте ее.")
            return
        
        try:
            # Сначала удаляем все старые вебхуки, чтобы избежать конфликта
            await app.bot.delete_webhook()
            # Устанавливаем новый вебхук
            await app.bot.set_webhook(url=TELEGRAM_WEBHOOK_URL)
            logging.info("Бот запущен в режиме webhook на Render.")
            await app.run_webhook(
                listen="0.0.0.0",
                port=int(os.getenv("PORT", "8080")),
                url_path="/"
            )
        except Exception as e:
            logging.error(f"Критическая ошибка при запуске в режиме webhook: {e}")
    else:
        # Режим polling для локальной разработки
        logging.info("Бот запущен в режиме polling (локально).")
        await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
