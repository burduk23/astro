import asyncio
import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiohttp import ClientSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ASTROPROXY_API_KEY = os.getenv("ASTROPROXY_API_KEY")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID")

if not all([BOT_TOKEN, ASTROPROXY_API_KEY, TELEGRAM_USER_ID]):
    raise ValueError("Please provide BOT_TOKEN, ASTROPROXY_API_KEY, and TELEGRAM_USER_ID in .env file")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

ASTRO_API_URL = "https://astroproxy.com/api/v1/referrals"

async def get_referral_balance():
    """Fetch referral balance from Astroproxy API."""
    params = {"token": ASTROPROXY_API_KEY}
    try:
        async with ClientSession() as session:
            async with session.get(ASTRO_API_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    # According to search results, 'balance' is the field for current withdrawable reward
                    return data.get("balance", 0)
                else:
                    logger.error(f"Error fetching balance: {response.status} {await response.text()}")
                    return None
    except Exception as e:
        logger.error(f"Exception during balance fetch: {e}")
        return None

def get_main_keyboard():
    """Create a reply keyboard with a 'Check Balance' button."""
    builder = ReplyKeyboardBuilder()
    builder.button(text="💰 Check Balance")
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Handle /start command."""
    if str(message.from_user.id) != TELEGRAM_USER_ID:
        await message.answer("Access denied. This bot is private.")
        return
    
    await message.answer(
        "Welcome! I will monitor your Astroproxy referral balance every 10 minutes.\n"
        "I'll notify you if it reaches $50 or more.",
        reply_markup=get_main_keyboard()
    )

@dp.message(F.text == "💰 Check Balance")
async def manual_balance_check(message: types.Message):
    """Handle manual balance check request."""
    if str(message.from_user.id) != TELEGRAM_USER_ID:
        return

    balance = await get_referral_balance()
    if balance is not None:
        await message.answer(f"Your current referral balance: **${balance}**", parse_mode="Markdown")
    else:
        await message.answer("Failed to retrieve balance. Please check logs.")

async def scheduled_balance_check():
    """Background task to check balance and notify if >= $50."""
    balance = await get_referral_balance()
    if balance is not None and balance >= 50:
        await bot.send_message(
            chat_id=TELEGRAM_USER_ID,
            text=f"🔔 **Notification!**\nYour Astroproxy referral balance has reached **${balance}**!",
            parse_mode="Markdown"
        )
        logger.info(f"Notification sent for balance: {balance}")
    elif balance is not None:
        logger.info(f"Balance check: {balance} (threshold not met)")

async def main():
    # Setup scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_balance_check, "interval", minutes=10)
    scheduler.start()

    # Start polling
    logger.info("Bot started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
