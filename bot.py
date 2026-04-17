import asyncio
import os
import json
import logging
import re
from bs4 import BeautifulSoup
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
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
auto_message_sent = False

ASTRO_URL = "https://astroproxy.com/dashboard/referral"

def load_message_data():
    """Загружает ID и текст сообщения из файла message.json"""
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
                # В trc20_tokens формат элементов может быть { "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t": "1000000" }
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

def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Проверить статистику")
    builder.button(text="🛠 Тест автовывода")
    builder.adjust(1, 1)
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    if str(message.from_user.id) != TELEGRAM_USER_ID:
        return
    
    await message.answer(
        "Привет! Я мониторю реферальную статистику Astroproxy (каждые 10 мин) "
        "и баланс USDT в сети Tron (каждую минуту).\n"
        "Уведомлю при достижении $50 в Astroproxy или при поступлении депозита на кошелек Tron.",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "💰 Проверить статистику")
async def manual_balance_check(message: types.Message):
    if str(message.from_user.id) != TELEGRAM_USER_ID:
        return

    m = await message.answer("🔄 Собираю данные с Astroproxy и TronGrid...")
    
    astro_task = asyncio.create_task(get_referral_stats())
    
    async with ClientSession() as client_session:
        tron_bal = await get_tron_usdt_balance(client_session)
        
    stats = await astro_task
    
    text = "📊 **Текущая статистика:**\n\n"
    
    # Секция Astroproxy
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
    
    # Секция Tron
    if not TRON_WALLET_ADDRESS:
        text += "⚠️ **Tron:** Кошелек не настроен в .env (TRON_WALLET_ADDRESS)\n"
    elif tron_bal is not None:
        text += f"📈 **Tron (USDT TRC20):** ${tron_bal:.2f}\n"
    else:
        text += "❌ **Tron:** Ошибка получения баланса.\n"

    await m.edit_text(text, parse_mode="Markdown")

@dp.message(F.text == "🛠 Тест автовывода")
async def test_auto_withdraw(message: types.Message):
    if str(message.from_user.id) != TELEGRAM_USER_ID:
        return

    m = await message.answer("🔄 Тестирую отправку сообщения об автовыводе через Telethon...")
    
    target_id, message_text = load_message_data()
    if not target_id or not message_text:
        await m.edit_text("❌ **Ошибка:** Не удалось загрузить ID или Message из файла `message.json`.", parse_mode="Markdown")
        return

    if not telethon_client:
        await m.edit_text("❌ **Ошибка:** Telethon клиент не инициализирован (проверьте API_ID и API_HASH в .env).", parse_mode="Markdown")
        return

    try:
        await telethon_client.send_message(int(target_id), message_text)
        await m.edit_text(f"✅ **Тест успешен!**\nСообщение успешно отправлено пользователю `{target_id}`.", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Ошибка при тестовой отправке: {e}")
        await m.edit_text(f"❌ **Ошибка при отправке:**\n`{e}`", parse_mode="Markdown")

async def scheduled_astro_check():
    """Ежеминутная (или раз в 10 минут) проверка Astroproxy."""
    global auto_message_sent
    
    stats = await get_referral_stats()
    if stats and not stats.get("error"):
        accumulated = stats['accumulated']
        
        # Сброс флага, если баланс стал меньше 50
        if accumulated < 50.0:
            auto_message_sent = False
            
        if accumulated >= 50.0:
            if not auto_message_sent:
                # Уведомление в бота
                await bot.send_message(
                    chat_id=TELEGRAM_USER_ID,
                    text=(
                        "🔔 **Уведомление Astroproxy!**\n"
                        f"Ваш реферальный баланс (НАКОПЛЕНО) достиг **${accumulated}**!\n\n"
                        f"ОБЩИЙ: ${stats['total']}\n"
                        f"ОПЛАЧЕНО: ${stats['paid']}"
                    ),
                    parse_mode="Markdown"
                )
                logger.info(f"Astroproxy уведомление отправлено! Накоплено: {accumulated}")

                # Автовывод сообщения через Telethon (один раз)
                if telethon_client:
                    target_id, message_text = load_message_data()
                    if target_id and message_text:
                        try:
                            await telethon_client.send_message(int(target_id), message_text)
                            auto_message_sent = True
                            
                            await bot.send_message(
                                chat_id=TELEGRAM_USER_ID,
                                text=f"✅ **Автовывод!**\nСообщение успешно отправлено пользователю `{target_id}`.",
                                parse_mode="Markdown"
                            )
                            logger.info(f"Сообщение об автовыводе отправлено пользователю {target_id}")
                        except Exception as e:
                            logger.error(f"Ошибка автоотправки Telethon: {e}")
                            await bot.send_message(
                                chat_id=TELEGRAM_USER_ID,
                                text=f"❌ **Ошибка автовывода!**\nНе удалось отправить сообщение: `{e}`",
                                parse_mode="Markdown"
                            )

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
                await bot.send_message(
                    chat_id=TELEGRAM_USER_ID,
                    text=(
                        f"🟢 **Пополнение на кошелек Tron!**\n"
                        f"Ваш баланс USDT увеличился на **${diff:.2f}**\n\n"
                        f"Текущий баланс USDT: **${current_balance:.2f}**"
                    ),
                    parse_mode="Markdown"
                )
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
