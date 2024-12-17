import telebot
import sqlite3
from datetime import datetime, timedelta
from telebot import types
import threading
import time
import logging

bot = telebot.TeleBot('7836835141:AAEP9sQl6vsljcdBx1ArnoXQt5HVctI0sII')

logging.basicConfig(level=logging.INFO, filename="bot_log.txt", filemode="a",
                    format="%(asctime)s - %(levelname)s - %(message)s")

def init_db():
    conn = sqlite3.connect("bot_schedule.db")
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS trainings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        training_date TEXT,
        training_time TEXT,
        training_link TEXT,
        FOREIGN KEY(user_id) REFERENCES users(user_id)
    )
    """)
    conn.commit()
    conn.close()

init_db()

def add_user(user_id, username):
    conn = sqlite3.connect("bot_schedule.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def add_training(user_id, date, time, link):
    conn = sqlite3.connect("bot_schedule.db")
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO trainings (user_id, training_date, training_time, training_link)
    VALUES (?, ?, ?, ?)
    """, (user_id, date, time, link))
    conn.commit()
    conn.close()

def get_trainings(user_id):
    conn = sqlite3.connect("bot_schedule.db")
    cursor = conn.cursor()
    cursor.execute("""
    SELECT training_date, training_time, training_link
    FROM trainings
    WHERE user_id = ?
    ORDER BY training_date, training_time
    """, (user_id,))
    trainings = cursor.fetchall()
    conn.close()
    return trainings

def reset_trainings(user_id):
    conn = sqlite3.connect("bot_schedule.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM trainings WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def check_reminders():
    while True:
        try:
            conn = sqlite3.connect("bot_schedule.db")
            cursor = conn.cursor()

            now = datetime.now()
            current_time = now.strftime('%Y-%m-%d %H:%M')

            target_time = (now + timedelta(hours=12)).strftime('%Y-%m-%d %H:%M')

            cursor.execute("""
            SELECT user_id, training_date, training_time, training_link
            FROM trainings
            """)
            trainings = cursor.fetchall()

            for user_id, training_date, training_time, training_link in trainings:
                training_datetime_str = f"{training_date} {training_time}"
                training_datetime = datetime.strptime(training_datetime_str, '%Y-%m-%d %H:%M')


                delta = training_datetime - now
                if timedelta(hours=24) <= delta < timedelta(hours=24, minutes=1):
                    bot.send_message(
                        user_id,
                        f"Напоминание: Завтра у вас тренировка в — {training_time}!\nСсылка: {training_link}"
                    )
                    logging.info(f"Отправлено напоминание пользователю {user_id} за 12 часов до тренировки.")

        except Exception as e:
            logging.error(f"Ошибка в check_reminders: {e}")
        finally:
            conn.close()
            time.sleep(60)


@bot.message_handler(commands=['start'])
def send_welcome(message):
    add_user(message.chat.id, message.chat.username)
    bot.reply_to(message, "Добро пожаловать! Выберите действие:", reply_markup=main_keyboard())

def main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        types.KeyboardButton('Добавить тренировку'),
        types.KeyboardButton('Мои тренировки'),
        types.KeyboardButton('Сбросить расписание')
    ]
    keyboard.add(*buttons)
    return keyboard

@bot.message_handler(func=lambda message: message.text == 'Добавить тренировку')
def add_training_step1(message):
    bot.reply_to(message, "Укажите день недели (например, Понедельник):")
    user_states[message.chat.id] = 'waiting_for_day'

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id] == 'waiting_for_day')
def add_training_step2(message):
    days_of_week = {
        'понедельник': 0, 'вторник': 1, 'среда': 2,
        'четверг': 3, 'пятница': 4, 'суббота': 5, 'воскресенье': 6
    }
    day = message.text.lower()
    if day in days_of_week:
        user_states[message.chat.id] = {'day': days_of_week[day], 'state': 'waiting_for_time'}
        bot.reply_to(message, "Теперь отправьте время тренировки (в формате ЧЧ:ММ):")
    else:
        bot.reply_to(message, "Некорректный день недели. Попробуйте снова.")

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id]['state'] == 'waiting_for_time')
def add_training_step3(message):
    try:
        training_time = datetime.strptime(message.text, '%H:%M')
        user_states[message.chat.id]['time'] = training_time
        user_states[message.chat.id]['state'] = 'waiting_for_link'
        bot.reply_to(message, "Теперь отправьте ссылку на программу тренировки:")
    except ValueError:
        bot.reply_to(message, "Неверный формат времени. Попробуйте снова (ЧЧ:ММ).")

@bot.message_handler(func=lambda message: message.chat.id in user_states and user_states[message.chat.id]['state'] == 'waiting_for_link')
def add_training_step4(message):
    user_id = message.chat.id
    state = user_states.pop(user_id)

    day_offset = (state['day'] - datetime.now().weekday() + 7) % 7
    training_date = (datetime.now() + timedelta(days=day_offset)).strftime('%Y-%m-%d')
    training_time = state['time'].strftime('%H:%M')

    add_training(user_id, training_date, training_time, message.text)
    bot.reply_to(message, "Тренировка добавлена!")

@bot.message_handler(func=lambda message: message.text == 'Мои тренировки')
def show_trainings(message):
    trainings = get_trainings(message.chat.id)
    if trainings:
        response = "Ваши тренировки:\n"
        for date, time, link in trainings:
            response += f"- {date} {time} | Ссылка: {link}\n"
        bot.reply_to(message, response)
    else:
        bot.reply_to(message, "У вас пока нет записанных тренировок.")

@bot.message_handler(func=lambda message: message.text == 'Сбросить расписание')
def reset_schedule(message):
    reset_trainings(message.chat.id)
    bot.reply_to(message, "Ваше расписание было сброшено.")

user_states = {}

reminder_thread = threading.Thread(target=check_reminders, daemon=True)
reminder_thread.start()

bot.polling()
