import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from bs4 import BeautifulSoup

import os
TOKEN_TELEGRAM = os.getenv("TELEGRAM_TOKEN")
HF_TOKEN = os.getenv("HF_TOKEN")


API_SUMMARY = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
API_TRANSLATE = {
    "en": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-en",
    "de": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-de",
    "ru": "https://api-inference.huggingface.co/models/Helsinki-NLP/opus-mt-en-ru"
}
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

# --- Получаем текст со страницы ---
def get_text_from_url(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.text, "html.parser")
    paragraphs = soup.find_all("p")
    article_text = "\n".join([p.get_text() for p in paragraphs])
    return article_text

# --- Суммаризация ---
def summarize_with_api(text):
    payload = {"inputs": text, "parameters": {"min_length": 30, "max_length": 100}}
    response = requests.post(API_SUMMARY, headers=headers, json=payload)
    result = response.json()
    return result[0]["summary_text"] if isinstance(result, list) else "Не удалось сделать резюме."

# --- Перевод ---
def translate_with_api(text, lang):
    payload = {"inputs": text}
    response = requests.post(API_TRANSLATE[lang], headers=headers, json=payload)
    result = response.json()
    return result[0]["translation_text"] if isinstance(result, list) else text

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Отправь мне ссылку на статью, и я сделаю краткий пересказ.")

# --- Основная логика ---
async def summarize(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    try:
        article_text = get_text_from_url(url)
        summary = summarize_with_api(article_text[:2000])  # ограничиваем текст
        
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

# --- Обработка кнопок ---
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    lang = query.data
    summary = context.user_data.get("summary", "Нет текста для перевода.")
    translated = translate_with_api(summary, lang)
    
    await query.edit_message_text(f"📌 Итоговый отчёт:\n\n{translated}")

# --- Запуск бота ---
def main():
    app = Application.builder().token(TOKEN_TELEGRAM).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, summarize))
    app.add_handler(CallbackQueryHandler(button))
    
    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
