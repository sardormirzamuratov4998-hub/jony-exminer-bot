from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.fsm.context import FSMContext

from keyboards import start_kb

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Assalomu alaykum! 👋\n"
        "<b>Jony Academy Examiner Bot</b>ga xush kelibsiz.\n\n"
        "Imtihon natijalarini kiritish uchun quyidagi tugmani bosing:",
        reply_markup=start_kb(),
    )
