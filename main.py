import asyncio
import logging
import sys
from os import getenv
from typing import Optional

from aiogram import Bot, Dispatcher, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.filters import CommandStart, Command
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.base import JobLookupError

from dotenv import load_dotenv
from config import ADMIN_LIST  # sizning config faylingizda ADMIN_LIST bo'lishi kerak
from aiogram.fsm.state import StatesGroup, State

class SendForm(StatesGroup):
    text = State()
    hour = State()
    minute = State()

load_dotenv()
TOKEN = getenv("TOKEN")

# Global scheduler (yaratilmagan bo'lishi mumkin)
scheduler: Optional[AsyncIOScheduler] = None

router = Router()
dp = Dispatcher()


async def task_one(bot: Bot, msg: str):
    """Oddiy yuboruvchi vazifa — xatoliklarni tutib logging qiladi."""
    try:
        # ADMIN_LIST[0] ga xabar yuborish (ro'yxat bo'sh emasligini tekshiring)
        if not ADMIN_LIST:
            logging.error("ADMIN_LIST bo'sh, qabul qiluvchi yo'qligiga ko'ra xabar yuborilmadi.")
            return
        await bot.send_message(ADMIN_LIST[0], msg)
        logging.info("Xabar yuborildi: %s", msg)
    except Exception as exc:
        logging.exception("task_one yuborishda xatolik yuz berdi: %s", exc)


@router.message(CommandStart())
async def cmd_start(message: Message):
    """/start tugmasi — bot ishga tushganini bildiradi."""
    await message.answer("Bot ishga tushdi.")

@router.message(Command("send"))
async def cmd_send(message: Message, state: FSMContext):
    text = message.text.removeprefix("/send").strip()
    if not text:
        await message.answer("Matn yozing: /send Salom")
        return

    await state.update_data(text=text)
    await state.set_state(SendForm.hour)
    await message.answer("Soatni kiriting (0–23):")

@router.message(SendForm.hour)
async def get_hour(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Soat faqat son bo‘lsin (0–23).")
        return

    hour = int(message.text)
    if not 0 <= hour <= 23:
        await message.answer("Soat 0–23 oralig‘ida bo‘lsin.")
        return

    await state.update_data(hour=hour)
    await state.set_state(SendForm.minute)
    await message.answer("Minutni kiriting (0–59):")


@router.message(SendForm.minute)
async def get_minute(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Minut faqat son bo‘lsin (0–59).")
        return

    minute = int(message.text)
    if not 0 <= minute <= 59:
        await message.answer("Minut 0–59 oralig‘ida bo‘lsin.")
        return

    data = await state.get_data()
    text = data["text"]
    hour = data["hour"]

    scheduler.add_job(
        task_one,
        trigger="cron",
        hour=hour,
        minute=minute,
        kwargs={"bot": message.bot, "msg": text},
    )

    await message.answer(f"Qo‘shildi: {hour}:{minute:02d}")
    await state.clear()


@router.message(Command(commands=["start_"]))
async def starter(message: Message):
    """/start_ — schedulerni ishga tushiradi."""
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()

    if not scheduler.running:
        # Start scheduler; u asyncio event loopga bog'lanadi
        scheduler.start()
        await message.answer(f"Scheduler ishga tushirildi soat.")
        logging.info("Scheduler start qilindi.")
    else:
        await message.answer("Scheduler allaqachon ishga tushgan.")


@router.message(Command(commands=["stop_"]))
async def stop(message: Message):
    """/stop_ — schedulerni to'xtatadi."""
    global scheduler
    if scheduler and scheduler.running:
        try:
            # shutdown() bloklovchi bo'lishi mumkin — ammo AsyncIOScheduler uchun u event loopda ishlaydi
            scheduler.shutdown(wait=False)
            await message.answer("Scheduler to'xtatildi.")
            logging.info("Scheduler to'xtatildi.")
        except Exception:
            logging.exception("Schedulerni to'xtatishda xatolik.")
            await message.answer("Schedulerni to'xtatishda xatolik yuz berdi.")
    else:
        await message.answer("Scheduler ishlamayapti.")


async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    bot = Bot(
        token=TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    # global scheduler yaratamiz — event loop hozir mavjud bo'ladi
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler()

    dp.include_router(router)
    # pollingni boshlaymiz
    await dp.start_polling(bot)


if __name__ == "__main__":
    # asyncio.run bilan mainni ishga tushiramiz
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")
