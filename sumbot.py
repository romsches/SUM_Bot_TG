import os
import asyncio
import requests
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from bs4 import BeautifulSoup
import logging

# Включаем логирование, чтобы видеть ошибки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)

# --- Константы и токены ---
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

# Проверяем, где запущен бот - на Render или локально
# Для работы на Render вам нужно установить TELEGRAM_WEBHOOK_URL в Environment Variables
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
        
        text_content = ""
        content_tags = ['article', 'main', 'section', 'div', 'p']
        
        for tag in content_tags:
            elements = soup.find_all(tag)
            if elements:
                for elem in elements:
                    text_content += elem.get_text(separator=' ', strip=True) + " "
                if len(text_content) > 200:
                    return text_content
        
        if not text_content:
            return "ОШИБКА: Не удалось найти основной текст статьи на этой странице."

        return text_content
    except requests.exceptions.RequestException as e:
        return f"ОШИБКА: Не удалось получить страницу. {e}"

def summarize_with_api_sync(text):
    """Синхронно отправляет текст на Hugging Face API для суммаризации."""
    if len(text) > 1024:
        input_text = text[:1024]
    else:
        input_text = text

    payload = {"inputs": input_text, "parameters": {"min_length": 50, "max_length": 300}}
    try:
        response = requests.post(API_SUMMARY, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        result = response.json()
        return result[0]["summary_text"] if isinstance(result, list) else f"Не удалось сделать резюме. Ответ API: {result}"
    except (requests.exceptions.RequestException, IndexError) as e:
        return f"ОШИБКА: Не удалось получить резюме от API. {e}"

def translate_with_api_sync(text, lang):
    """Синхронно отправляет текст на Hugging Face API для перевода."""
    if len(text) > 500:
        text = text[:500] + "..."
    payload = {"inputs": text}
    try:
        response = requests.post(API_TRANSLATE[lang], headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        result = response.json()
        return result[0]["translation_text"] if isinstance(result, list) else f"Не удалось перевести текст. Ответ API: {result}"
    except (requests.exceptions.RequestException, IndexError) as e:
        return f"ОШИБКА: Не удалось перевести текст. {e}"

# --- Команды и обработчики ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение."""
    await update.message.reply_text("Привет! Отправь мне ссылку на статью, и я сделаю краткий пересказ.")

async def summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящую ссылку и запускает процесс суммаризации."""
    url = update.message.text
    await update.message.reply_text("Пожалуйста, подождите, я обрабатываю статью...")
    
    article_text = await asyncio.get_event_loop().run_in_executor(None, get_text_from_url_sync, url)
    
    if article_text.startswith("ОШИБКА"):
        await update.message.reply_text(article_text)
        return
        
    summary = await asyncio.get_event_loop().run_in_executor(None, summarize_with_api_sync, article_text)

    if summary.startswith("ОШИБКА"):
        await update.message.reply_text(summary)
        return

    context.user_data["summary"] = summary
    
    keyboard = [
        [InlineKeyboardButton("English 🇬🇧", callback_data="en")],
        [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="de")],
        [InlineKeyboardButton("Русский 🇷🇺", callback_data="ru")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Готово! На каком языке показать отчёт?", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки выбора языка."""
    query = update.callback_query
    await query.answer()
    
    lang = query.data
    summary = context.user_data.get("summary", "Нет текста для перевода.")
    
    await query.edit_message_text("Перевожу...")
    
    translated = await asyncio.get_event_loop().run_in_executor(None, translate_with_api_sync, summary, lang)
    
    await query.edit_message_text(f"📌 Итоговый отчёт:\n\n{translated}")

# --- Запуск бота (с автоматическим выбором режима) ---
async def main():
    """Главная асинхронная функция для запуска бота."""
    if not TOKEN_TELEGRAM:
        logging.error("Ошибка: Переменная TELEGRAM_TOKEN не найдена.")
        return
    if not HF_TOKEN:
        logging.error("Ошибка: Переменная HF_TOKEN не найдена.")
        return

    app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, summarize))
    app.add_handler(CallbackQueryHandler(button))

    if IS_RUNNING_ON_RENDER:
        if not TELEGRAM_WEBHOOK_URL:
            logging.error("Ошибка: Бот запущен на Render, но переменная TELEGRAM_WEBHOOK_URL не найдена. Пожалуйста, добавьте ее.")
            return
        await app.bot.set_webhook(url=TELEGRAM_WEBHOOK_URL)
        print("Бот запущен в режиме webhook на Render.")
        await app.run_webhook(
            listen="0.0.0.0",
            port=int(os.getenv("PORT", "8080")),
            url_path=f"/{os.getenv('TOKEN_TELEGRAM')}",
            webhook_url=TELEGRAM_WEBHOOK_URL
        )
    else:
        print("Бот запущен в режиме polling (локально).")
        await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
