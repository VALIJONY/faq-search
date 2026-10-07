"""Telegram bot (aiogram 3). Qidiruvni o'zi qilmaydi — API'ga HTTP so'rov yuboradi."""
import asyncio
import logging

import httpx
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import API_URL, BOT_TOKEN

log = logging.getLogger("bot")
dp = Dispatcher()
http = httpx.AsyncClient(base_url=API_URL, timeout=60)  # CPU'da embedding sekin bo'lishi mumkin

ERROR_TEXT = "Kechirasiz, xizmat hozir ishlamayapti. Birozdan keyin qayta urinib ko'ring."


@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Assalomu alaykum! Davlat xizmatlari bo'yicha savolingizni yozing.")


@dp.message(F.text)
async def ask(message: Message):
    try:
        resp = await http.post("/ask", json={"question": message.text})
        resp.raise_for_status()
        result = resp.json()
    except httpx.HTTPError as e:
        log.error("API xatosi: %s", e)
        await message.answer(ERROR_TEXT)
        return

    if result["status"] == "found":
        await message.answer(result["answer"])

    elif result["status"] == "ambiguous":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=o["question"][:60], callback_data=f"ans:{o['answer_id']}")]
            for o in result["options"]
        ])
        await message.answer("Savolingiz quyidagilardan qaysi biriga tegishli?", reply_markup=kb)

    else:
        await message.answer(
            "Kechirasiz, bu savolga bazada javob topilmadi. "
            "Savolni boshqacha so'zlar bilan yozib ko'ring."
        )


@dp.callback_query(F.data.startswith("ans:"))
async def choose(callback: CallbackQuery):
    answer_id = int(callback.data.split(":")[1])
    try:
        resp = await http.get(f"/answers/{answer_id}")
        text = resp.json()["answer"] if resp.status_code == 200 else "Javob topilmadi"
    except httpx.HTTPError as e:
        log.error("API xatosi: %s", e)
        text = ERROR_TEXT
    await callback.message.edit_text(text)
    await callback.answer()


async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN topilmadi. .env faylga BOT_TOKEN=... yozing.")
    await dp.start_polling(Bot(BOT_TOKEN))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main())
