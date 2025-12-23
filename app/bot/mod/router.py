from aiogram import Router, F, Bot
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from app.bot.common.filters import RoleFilter
from app.services import users as users_service
from app.services import proposals as proposals_service
from app.services import support as support_service
from app.config import USER_BOT_TOKEN
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

mod_router = Router()
mod_router.message.filter(RoleFilter({"moderator", "admin"}))
mod_router.callback_query.filter(RoleFilter({"moderator", "admin"}))

def mod_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Предложения"), KeyboardButton(text="🆘 Тикеты")],
        ],
        resize_keyboard=True
    )

def cancel_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

class RejectState(StatesGroup):
    proposal_id = State()
    reason = State()

class ReplyTicketState(StatesGroup):
    ticket_id = State()
    text = State()

@mod_router.message(F.text == "/start")
async def start(message: Message, state: FSMContext):
    await state.clear()
    u = users_service.get_or_create_user(message.from_user.id, message.from_user.username)
    if u.role.value not in ("moderator", "admin"):
        return await message.answer("Нет доступа.")
    await message.answer("Mod bot: меню", reply_markup=mod_menu())

@mod_router.message(F.text == "📋 Предложения")
async def proposals_list(message: Message):
    items = proposals_service.list_pending()
    if not items:
        return await message.answer("Нет pending предложений.", reply_markup=mod_menu())
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"#{p.id} {p.title}", callback_data=f"prop:{p.id}")]
        for p in items
    ])
    await message.answer("Выбери предложение:", reply_markup=kb)

@mod_router.callback_query(F.data.startswith("prop:"))
async def proposal_view(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    p = proposals_service.get(pid)
    if not p:
        return await cb.answer("Не найдено", show_alert=True)

    opts = proposals_service.parse_options(p)
    text = (
        f"💡 Предложение #{p.id}\n"
        f"Название: <b>{p.title}</b>\n"
        f"Описание: {p.description or '-'}\n"
        f"Варианты: {', '.join(opts)}\n"
        f"Статус: {p.status.value}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"prop_ok:{pid}")],
        [InlineKeyboardButton(text="❌ Отклонить", callback_data=f"prop_no:{pid}")],
    ])
    if p.photo_file_id:
        await cb.message.answer_photo(p.photo_file_id, caption=text, reply_markup=kb)
    else:
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@mod_router.callback_query(F.data.startswith("prop_ok:"))
async def prop_approve(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    try:
        p, event = proposals_service.approve(pid, cb.from_user.id, fee_percent=0.0)
    except Exception as e:
        return await cb.answer(str(e), show_alert=True)

    await notify_user(p.user_id, f"✅ Твоё предложение #{p.id} одобрено! Создано событие #{event.id}: {event.title}")
    await cb.message.answer(f"✅ Одобрено. Создано событие #{event.id}", reply_markup=mod_menu())
    await cb.answer()

@mod_router.callback_query(F.data.startswith("prop_no:"))
async def prop_reject_start(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[1])
    await state.set_state(RejectState.reason)
    await state.update_data(proposal_id=pid)
    await cb.message.answer("Введи причину отклонения:", reply_markup=cancel_kb())
    await cb.answer()

@mod_router.message(RejectState.reason, F.text == "❌ Отмена")
async def reject_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=mod_menu())

@mod_router.message(RejectState.reason)
async def prop_reject_done(message: Message, state: FSMContext):
    data = await state.get_data()
    pid = int(data["proposal_id"])
    reason = message.text.strip()
    try:
        p = proposals_service.reject(pid, message.from_user.id, reason)
    except Exception as e:
        await state.clear()
        return await message.answer(f"Ошибка: {e}", reply_markup=mod_menu())

    await notify_user(p.user_id, f"❌ Твоё предложение #{p.id} отклонено.\nПричина: {reason}")
    await state.clear()
    await message.answer("Отклонено.", reply_markup=mod_menu())

async def notify_user(user_db_id: int, text: str):
    from app.db.session import session_scope
    from app.db.models import User
    with session_scope() as s:
        u = s.query(User).filter_by(id=user_db_id).one()
        tg_id = int(u.telegram_id)

    async with Bot(USER_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
        await bot.send_message(tg_id, text)

@mod_router.message(F.text == "🆘 Тикеты")
async def tickets_list(message: Message):
    items = support_service.list_open_tickets()
    if not items:
        return await message.answer("Открытых тикетов нет.", reply_markup=mod_menu())

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"Тикет #{t.id}", callback_data=f"ticket:{t.id}")]
        for t in items
    ])
    await message.answer("Выбери тикет:", reply_markup=kb)

@mod_router.callback_query(F.data.startswith("ticket:"))
async def ticket_view(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    t = support_service.get_ticket(tid)
    if not t:
        return await cb.answer("Не найден", show_alert=True)

    msgs = support_service.get_ticket_messages(tid, limit=15)
    text_lines = [f"🆘 Тикет #{tid} (open)\nПоследние сообщения:"]
    for m in msgs:
        prefix = "👤" if m.sender_role.value == "user" else "🛠"
        text_lines.append(f"{prefix} {m.text}")
    text = "\n".join(text_lines)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 Взять", callback_data=f"take:{tid}")],
        [InlineKeyboardButton(text="✍️ Ответить", callback_data=f"reply:{tid}")],
        [InlineKeyboardButton(text="✅ Закрыть", callback_data=f"close:{tid}")],
    ])
    await cb.message.answer(text, reply_markup=kb)
    await cb.answer()

@mod_router.callback_query(F.data.startswith("take:"))
async def ticket_take(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    support_service.assign_ticket(tid, cb.from_user.id)
    await cb.answer("Взял тикет")

@mod_router.callback_query(F.data.startswith("reply:"))
async def ticket_reply_start(cb: CallbackQuery, state: FSMContext):
    tid = int(cb.data.split(":")[1])
    await state.set_state(ReplyTicketState.text)
    await state.update_data(ticket_id=tid)
    await cb.message.answer("Введи ответ пользователю:", reply_markup=cancel_kb())
    await cb.answer()

@mod_router.message(ReplyTicketState.text, F.text == "❌ Отмена")
async def ticket_reply_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=mod_menu())

@mod_router.message(ReplyTicketState.text)
async def ticket_reply_done(message: Message, state: FSMContext):
    data = await state.get_data()
    tid = int(data["ticket_id"])
    staff_role = users_service.get_role(message.from_user.id)

    support_service.add_staff_message(tid, message.from_user.id, staff_role, message.text.strip())

    user_tg_id = support_service.get_ticket_user_tg_id(tid)
    async with Bot(USER_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
        await bot.send_message(user_tg_id, f"🆘 Ответ по тикету #{tid}:\n{message.text.strip()}")

    await state.clear()
    await message.answer("✅ Ответ отправлен пользователю.", reply_markup=mod_menu())

@mod_router.callback_query(F.data.startswith("close:"))
async def ticket_close(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    support_service.close_ticket(tid)
    user_tg_id = support_service.get_ticket_user_tg_id(tid)
    async with Bot(USER_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
        await bot.send_message(user_tg_id, f"✅ Тикет #{tid} закрыт. Если нужно — открой новый через 🆘 Поддержка.")
    await cb.message.answer(f"✅ Тикет #{tid} закрыт.", reply_markup=mod_menu())
    await cb.answer()
