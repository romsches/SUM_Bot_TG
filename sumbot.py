import os
import asyncio
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from bs4 import BeautifulSoup
import telegram.constants

# --- Константы и токены ---
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")

# URL-адреса API для суммаризации и перевода
API_SUMMARY = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
API_TRANSLATE = {
    "en": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-en",
    "de": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-de",
    "ru": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-ru"
}
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

# --- Вспомогательные функции (выполняются в отдельном потоке) ---

# --- Получаем текст со страницы (более надежный метод) ---
def get_text_from_url_sync(url):
    """Синхронно извлекает основной текст статьи с веб-страницы."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Попытка найти основной контент по разным тегам
        text_content = ""
        for tag in ['article', 'main', 'div', 'p']:
            main_element = soup.find(tag)
            if main_element:
                paragraphs = main_element.find_all("p")
                text_content = "\n".join([p.get_text() for p in paragraphs])
                if len(text_content) > 200: # Считаем, что нашли достаточно текста
                    return text_content
        
        if not text_content:
             # Если не нашли, возвращаем весь текст из <p> тегов
             paragraphs = soup.find_all("p")
             text_content = "\n".join([p.get_text() for p in paragraphs])

        return text_content
    except requests.exceptions.RequestException as e:
        return f"ОШИБКА: Не удалось получить страницу. {e}"

# --- Суммаризация текста ---
def summarize_with_api_sync(text):
    """Синхронно отправляет текст на Hugging Face API для суммаризации."""
    # Ограничиваем входной текст до 1024 символов, чтобы избежать ошибок API
    input_text = text[:1024]
    payload = {"inputs": input_text, "parameters": {"min_length": 50, "max_length": 300}}
    try:
        response = requests.post(API_SUMMARY, headers=headers, json=payload, timeout=20)
        response.raise_for_status() # Проверяем на ошибки HTTP
        result = response.json()
        return result[0]["summary_text"] if isinstance(result, list) else "Не удалось сделать резюме."
    except (requests.exceptions.RequestException, IndexError) as e:
        return f"ОШИБКА: Не удалось получить резюме от API. {e}"

# --- Перевод текста ---
def translate_with_api_sync(text, lang):
    """Синхронно отправляет текст на Hugging Face API для перевода."""
    # Убедитесь, что текст не слишком длинный для перевода
    if len(text) > 500:
        text = text[:500] + "..."
    payload = {"inputs": text}
    try:
        response = requests.post(API_TRANSLATE[lang], headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        result = response.json()
        return result[0]["translation_text"] if isinstance(result, list) else text
    except (requests.exceptions.RequestException, IndexError) as e:
        return f"ОШИБКА: Не удалось перевести текст. {e}"

# --- Команды и обработчики ---

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение."""
    await update.message.reply_text("Привет! Отправь мне ссылку на статью, и я сделаю краткий пересказ.")

# Основная логика: обработка ссылки
async def summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает входящую ссылку и запускает процесс суммаризации."""
    url = update.message.text
    await update.message.reply_text("Пожалуйста, подождите, я обрабатываю статью...")
    
    # Запускаем синхронные функции в отдельном потоке, чтобы не блокировать бота
    article_text = await asyncio.get_event_loop().run_in_executor(None, get_text_from_url_sync, url)
    
    if "ОШИБКА" in article_text:
        await update.message.reply_text(article_text)
        return
        
    summary = await asyncio.get_event_loop().run_in_executor(None, summarize_with_api_sync, article_text)

    if "ОШИБКА" in summary:
        await update.message.reply_text(summary)
        return

    # Сохраняем резюме в контекст, чтобы потом перевести
    context.user_data["summary"] = summary
    
    # Кнопки выбора языка
    keyboard = [
        [InlineKeyboardButton("English 🇬🇧", callback_data="en")],
        [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="de")],
        [InlineKeyboardButton("Русский 🇷🇺", callback_data="ru")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("Готово! На каком языке показать отчёт?", reply_markup=reply_markup)

# Обработка нажатий на кнопки
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает нажатия на кнопки выбора языка."""
    query = update.callback_query
    await query.answer()
    
    lang = query.data
    summary = context.user_data.get("summary", "Нет текста для перевода.")
    
    await query.edit_message_text("Перевожу...")
    
    # Запускаем синхронную функцию перевода в отдельном потоке
    translated = await asyncio.get_event_loop().run_in_executor(None, translate_with_api_sync, summary, lang)
    
    await query.edit_message_text(f"📌 Итоговый отчёт:\n\n{translated}")

# --- Запуск бота ---
def main():
    """Главная функция для запуска бота."""
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, summarize))
    app.add_handler(CallbackQueryHandler(button))
    
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
