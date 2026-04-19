import asyncio
import os
import json
import logging
import re
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.session.aiohttp import AiohttpSession
from aiohttp import ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from telethon import TelegramClient

# Загрузка переменных окружения
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID")
ASTRO_COOKIE = os.getenv("ASTRO_COOKIE")
PROXY_URL = os.getenv("PROXY_URL") # Опционально

TRON_WALLET_ADDRESS = os.getenv("TRON_WALLET_ADDRESS")
TRONGRID_API_KEY = os.getenv("TRONGRID_API_KEY")

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")

if not all([BOT_TOKEN, TELEGRAM_USER_ID, ASTRO_COOKIE]):
    raise ValueError("Пожалуйста, укажите BOT_TOKEN, TELEGRAM_USER_ID и ASTRO_COOKIE в файле .env")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()

# Инициализация клиента Telethon
telethon_client = TelegramClient('user_session', int(API_ID), API_HASH) if API_ID and API_HASH else None

previous_tron_balance = None
DATA_FILE = "data.json"

ASTRO_URL = "https://astroproxy.com/dashboard/referral"

# FSM States
class BotStates(StatesGroup):
    waiting_for_new_user = State()
    waiting_for_test_msg = State()
    waiting_for_test_target = State()

def load_data():
    if not os.path.exists(DATA_FILE):
        default_data = {
            "users": [],
            "test_settings": {},
            "auto_message_sent": False
        }
        if TELEGRAM_USER_ID and TELEGRAM_USER_ID.isdigit():
            default_data["users"].append(int(TELEGRAM_USER_ID))
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(default_data, f, indent=4)
        return default_data
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {"users": [], "test_settings": {}, "auto_message_sent": False}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def is_user_allowed(user_id):
    data = load_data()
    return user_id in data.get("users", []) or str(user_id) == str(TELEGRAM_USER_ID)

async def notify_all_users(text, parse_mode="Markdown"):
    data = load_data()
    users = set(data.get("users", []))
    if TELEGRAM_USER_ID and TELEGRAM_USER_ID.isdigit():
        users.add(int(TELEGRAM_USER_ID))
    
    for uid in users:
        try:
            await bot.send_message(chat_id=uid, text=text, parse_mode=parse_mode)
        except Exception as e:
            logger.error(f"Не удалось отправить уведомление пользователю {uid}: {e}")

def load_message_data():
    """Загружает ID и текст сообщения из файла message.json (для реального вывода)"""
    try:
        with open("message.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("ID"), data.get("Message")
    except Exception as e:
        logger.error(f"Ошибка чтения message.json: {e}")
        return None, None

async def get_tron_usdt_balance(client_session: ClientSession):
    """Асинхронная функция для получения баланса USDT TRC20 на TronGrid."""
    if not TRON_WALLET_ADDRESS:
        return None
        
    url = f"https://api.trongrid.io/v1/accounts/{TRON_WALLET_ADDRESS}"
    headers = {"Accept": "application/json"}
    if TRONGRID_API_KEY:
        headers["TRON-PRO-API-KEY"] = TRONGRID_API_KEY

    try:
        async with client_session.get(url, headers=headers) as response:
            if response.status != 200:
                logger.error(f"Ошибка TronGrid API: {response.status}")
                return None
            
            data = await response.json()
            if not data.get("success"):
                logger.error(f"Неуспешный ответ TronGrid API: {data}")
                return None
            
            if not data.get("data"):
                return 0.0
                
            account_info = data["data"][0]
            trc20_tokens = account_info.get("trc20", [])
            
            for token_data in trc20_tokens:
                for contract_address, balance_str in token_data.items():
                    if contract_address == "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t":
                        return float(balance_str) / 1_000_000
                        
            return 0.0
    except Exception as e:
        logger.error(f"Ошибка при запросе баланса Tron: {e}")
        return None

async def get_referral_stats():
    """Получение статистики Astroproxy через Cookie."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Cookie": ASTRO_COOKIE,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    
    try:
        async with ClientSession() as session:
            async with session.get(ASTRO_URL, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Ошибка запроса Astroproxy: {response.status}")
                    return None
                
                html = await response.text()
                
                if "login" in str(response.url) or "signin" in str(response.url):
                    logger.error("Cookie истекли или недействительны. Перенаправлено на страницу входа.")
                    return {"error": "cookie_expired"}

                soup = BeautifulSoup(html, "html.parser")
                text_content = soup.get_text(separator=" ", strip=True)
                
                def extract_value(ru_key, en_key, text):
                    pattern = rf'({ru_key}|{en_key})[^\d]*([\d\.,]+)'
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        val_str = match.group(2).replace(',', '.')
                        try:
                            return float(val_str)
                        except ValueError:
                            return 0.0
                    return 0.0

                total = extract_value("ОБЩИЙ", "TOTAL", text_content)
                accumulated = extract_value("НАКОПЛЕНО", "ACCUMULATED", text_content)
                paid = extract_value("ОПЛАЧЕНО", "PAID", text_content)
                
                return {
                    "total": total,
                    "accumulated": accumulated,
                    "paid": paid
                }
    except Exception as e:
        logger.error(f"Ошибка при получении данных Astroproxy: {e}")
        return None

def get_main_keyboard(user_id):
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Проверить статистику")
    builder.button(text="🛠 Тест автовывода")
    builder.button(text="⚙️ Настройки")
    if str(user_id) == str(TELEGRAM_USER_ID):
        builder.button(text="👑 Админка")
    builder.adjust(2, 2)
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    if not is_user_allowed(message.from_user.id):
        return
    
    await message.answer(
        "Привет! Я мониторю реферальную статистику Astroproxy (каждые 10 мин) "
        "и баланс USDT в сети Tron (каждую минуту).\n"
        "Уведомлю при достижении $50 в Astroproxy или при поступлении депозита на кошелек Tron.",
        reply_markup=get_main_keyboard(message.from_user.id)
    )

@dp.message(F.text == "💰 Проверить статистику")
async def manual_balance_check(message: types.Message):
    if not is_user_allowed(message.from_user.id):
        return

    m = await message.answer("🔄 Собираю данные с Astroproxy и TronGrid...")
    
    astro_task = asyncio.create_task(get_referral_stats())
    
    async with ClientSession() as client_session:
        tron_bal = await get_tron_usdt_balance(client_session)
        
    stats = await astro_task
    
    text = "📊 **Текущая статистика:**\n\n"
    
    if stats is None:
        text += "❌ **Astroproxy:** Ошибка соединения.\n"
    elif stats.get("error") == "cookie_expired":
        text += "❌ **Astroproxy:** Cookie устарели. Обновите ASTRO_COOKIE в .env.\n"
    else:
        text += (
            "🌐 **Astroproxy:**\n"
            f"ОБЩИЙ: ${stats['total']}\n"
            f"НАКОПЛЕНО: ${stats['accumulated']}\n"
            f"ОПЛАЧЕНО: ${stats['paid']}\n"
        )
        
    text += "\n"
    
    if not TRON_WALLET_ADDRESS:
        text += "⚠️ **Tron:** Кошелек не настроен в .env (TRON_WALLET_ADDRESS)\n"
    elif tron_bal is not None:
        text += f"📈 **Tron (USDT TRC20):** ${tron_bal:.2f}\n"
    else:
        text += "❌ **Tron:** Ошибка получения баланса.\n"

    await m.edit_text(text, parse_mode="Markdown")

@dp.message(F.text == "🛠 Тест автовывода")
async def test_auto_withdraw(message: types.Message):
    if not is_user_allowed(message.from_user.id):
        return

    m = await message.answer("🔄 Тестирую отправку тестового сообщения через Telethon...")
    
    data = load_data()
    user_id_str = str(message.from_user.id)
    user_settings = data.get("test_settings", {}).get(user_id_str, {})
    
    # По умолчанию отправляем самому пользователю (target_id = ID пользователя)
    target_id = user_settings.get("target_id", user_id_str)
    message_text = user_settings.get("message", "Это тестовое сообщение (по умолчанию).")

    if not telethon_client:
        await m.edit_text("❌ **Ошибка:** Telethon клиент не инициализирован (проверьте API_ID и API_HASH в .env).", parse_mode="Markdown")
        return

    try:
        await telethon_client.send_message(int(target_id), message_text)
        await m.edit_text(f"✅ **Тест успешен!**\nТестовое сообщение успешно отправлено пользователю `{target_id}`.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка при тестовой отправке: {e}")
        await m.edit_text(f"❌ **Ошибка при отправке:**\n`{e}`", parse_mode="Markdown")

# === Админка ===
@dp.message(F.text == "👑 Админка")
async def cmd_admin(message: types.Message, state: FSMContext):
    await state.clear()
    if str(message.from_user.id) != str(TELEGRAM_USER_ID):
        return
    
    data = load_data()
    users_list = ", ".join(map(str, set(data.get("users", []))))
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="➕ Добавить пользователя")
    builder.button(text="🔙 Назад")
    builder.adjust(1, 1)
    
    await message.answer(f"👑 **Панель администратора**\n\nТекущие пользователи бота:\n{users_list}", 
                         reply_markup=builder.as_markup(resize_keyboard=True), parse_mode="Markdown")

@dp.message(F.text == "➕ Добавить пользователя")
async def add_user_start(message: types.Message, state: FSMContext):
    if str(message.from_user.id) != str(TELEGRAM_USER_ID):
        return
    await message.answer("Введите Telegram ID нового пользователя (только цифры):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(BotStates.waiting_for_new_user)

@dp.message(BotStates.waiting_for_new_user)
async def add_user_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуйте еще раз или нажмите /start.")
        return
    
    new_user_id = int(message.text)
    data = load_data()
    if new_user_id not in data.get("users", []):
        data.setdefault("users", []).append(new_user_id)
        save_data(data)
        await message.answer(f"✅ Пользователь `{new_user_id}` успешно добавлен!", 
                             reply_markup=get_main_keyboard(message.from_user.id), parse_mode="Markdown")
    else:
        await message.answer("ℹ️ Этот пользователь уже есть в списке.", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

# === Настройки ===
@dp.message(F.text == "⚙️ Настройки")
async def cmd_settings(message: types.Message, state: FSMContext):
    await state.clear()
    if not is_user_allowed(message.from_user.id):
        return
    
    data = load_data()
    user_id_str = str(message.from_user.id)
    user_settings = data.get("test_settings", {}).get(user_id_str, {})
    
    target = user_settings.get("target_id", user_id_str)
    msg_text = user_settings.get("message", "Это тестовое сообщение (по умолчанию).")
    
    builder = ReplyKeyboardBuilder()
    builder.button(text="📝 Изменить текст тест. сообщения")
    builder.button(text="🎯 Изменить получателя тест. сообщения")
    builder.button(text="🔙 Назад")
    builder.adjust(1, 1, 1)
    
    await message.answer(
        f"⚙️ **Ваши настройки тестового сообщения:**\n\n"
        f"Получатель (ID): `{target}`\n"
        f"Текст:\n_{msg_text}_",
        parse_mode="Markdown",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

@dp.message(F.text == "📝 Изменить текст тест. сообщения")
async def edit_test_msg_start(message: types.Message, state: FSMContext):
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer("Отправьте новый текст для вашего тестового сообщения:", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(BotStates.waiting_for_test_msg)

@dp.message(BotStates.waiting_for_test_msg)
async def edit_test_msg_finish(message: types.Message, state: FSMContext):
    data = load_data()
    user_id_str = str(message.from_user.id)
    if user_id_str not in data.get("test_settings", {}):
        data.setdefault("test_settings", {})[user_id_str] = {}
    
    data["test_settings"][user_id_str]["message"] = message.text
    save_data(data)
    
    await message.answer("✅ Текст тестового сообщения успешно сохранен!", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

@dp.message(F.text == "🎯 Изменить получателя тест. сообщения")
async def edit_test_target_start(message: types.Message, state: FSMContext):
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer("Введите Telegram ID получателя для вашего тестового сообщения (или свой ID, чтобы получать самому):", reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(BotStates.waiting_for_test_target)

@dp.message(BotStates.waiting_for_test_target)
async def edit_test_target_finish(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ ID должен состоять только из цифр. Попробуйте еще раз.")
        return
    
    data = load_data()
    user_id_str = str(message.from_user.id)
    if user_id_str not in data.get("test_settings", {}):
        data.setdefault("test_settings", {})[user_id_str] = {}
    
    data["test_settings"][user_id_str]["target_id"] = message.text
    save_data(data)
    
    await message.answer("✅ Получатель тестового сообщения успешно сохранен!", reply_markup=get_main_keyboard(message.from_user.id))
    await state.clear()

@dp.message(F.text == "🔙 Назад")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    if not is_user_allowed(message.from_user.id):
        return
    await message.answer("Главное меню", reply_markup=get_main_keyboard(message.from_user.id))


async def scheduled_astro_check():
    """Ежеминутная (или раз в 10 минут) проверка Astroproxy."""
    stats = await get_referral_stats()
    if stats and not stats.get("error"):
        accumulated = stats['accumulated']
        
        data = load_data()
        auto_message_sent = data.get("auto_message_sent", False)
        
        # Сброс флага, если баланс стал меньше 50
        if accumulated < 50.0 and auto_message_sent:
            data["auto_message_sent"] = False
            save_data(data)
            auto_message_sent = False
            
        if accumulated >= 50.0:
            if not auto_message_sent:
                # Уведомление всем пользователям в бота
                notify_text = (
                    "🔔 **Уведомление Astroproxy! Средства накопились и ставятся на вывод.**\n"
                    f"Ваш реферальный баланс (НАКОПЛЕНО) достиг **${accumulated}**!\n\n"
                    f"ОБЩИЙ: ${stats['total']}\n"
                    f"ОПЛАЧЕНО: ${stats['paid']}"
                )
                await notify_all_users(notify_text)
                logger.info(f"Astroproxy уведомление отправлено! Накоплено: {accumulated}")

                # Автовывод сообщения через Telethon (один раз)
                if telethon_client:
                    # Загружаем ИСХОДНЫЕ данные для реального автовывода (сообщение не меняется)
                    target_id, message_text = load_message_data()
                    if target_id and message_text:
                        try:
                            await telethon_client.send_message(int(target_id), message_text)
                            
                            data = load_data()
                            data["auto_message_sent"] = True
                            save_data(data)
                            
                            success_text = f"✅ **Автовывод инициирован!**\nСообщение на вывод успешно отправлено получателю `{target_id}`."
                            await notify_all_users(success_text)
                            logger.info(f"Сообщение об автовыводе отправлено получателю {target_id}")
                        except Exception as e:
                            logger.error(f"Ошибка автоотправки Telethon: {e}")
                            error_text = f"❌ **Ошибка автовывода!**\nНе удалось отправить сообщение на вывод: `{e}`"
                            await notify_all_users(error_text)

async def scheduled_tron_check():
    """Ежеминутный мониторинг баланса Tron."""
    global previous_tron_balance
    if not TRON_WALLET_ADDRESS:
        return
        
    async with ClientSession() as client_session:
        current_balance = await get_tron_usdt_balance(client_session)
        
    if current_balance is not None:
        if previous_tron_balance is not None and current_balance > previous_tron_balance:
            diff = current_balance - previous_tron_balance
            if diff >= 0.01: # Игнорируем микро-изменения (пыль)
                text = (
                    f"🟢 **Пополнение на кошелек Tron!**\n"
                    f"Ваш баланс USDT увеличился на **${diff:.2f}**\n\n"
                    f"Текущий баланс USDT: **${current_balance:.2f}**"
                )
                await notify_all_users(text)
                logger.info(f"Tron пополнение обнаружено: +{diff}. Текущий баланс: {current_balance}")
        previous_tron_balance = current_balance

async def main():
    # Запуск клиента Telethon
    if telethon_client:
        logger.info("Запуск сессии Telethon...")
        await telethon_client.start()
        
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_astro_check, "interval", minutes=10)
    scheduler.add_job(scheduled_tron_check, "interval", minutes=1)
    scheduler.start()

    logger.info("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")
