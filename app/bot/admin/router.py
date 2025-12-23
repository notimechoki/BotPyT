from __future__ import annotations

from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.bot.common.filters import RoleFilter
from app.config import USER_BOT_TOKEN
from app.db.session import session_scope
from app.db.models import User, Event, Proposal, Ticket, TicketMessage, Bet

from app.services import users as users_service
from app.services import events as events_service
from app.services import bets as bets_service
from app.services import proposals as proposals_service
from app.services import support as support_service


admin_router = Router()
admin_router.message.filter(RoleFilter({"admin"}))
admin_router.callback_query.filter(RoleFilter({"admin"}))


def admin_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Создать событие"), KeyboardButton(text="🔒 Закрыть событие")],
            [KeyboardButton(text="📚 История событий"), KeyboardButton(text="💡 История предложений")],
            [KeyboardButton(text="🆘 История тикетов"), KeyboardButton(text="🔎 Пользователь")],
            [KeyboardButton(text="💰 Баланс юзера")],
        ],
        resize_keyboard=True,
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="❌ Отмена")]],
        resize_keyboard=True,
    )


def _to_float(txt: str) -> float:
    return float(txt.strip().replace(",", "."))


def _chunk(text: str, size: int = 3900) -> list[str]:
    text = text or ""
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


async def _notify_user(tg_id: int, text: str):
    async with Bot(USER_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
        try:
            await bot.send_message(tg_id, text)
        except Exception:
            pass


class CreateEventStates(StatesGroup):
    title = State()
    description = State()
    photo = State()
    options = State()
    fee = State()


class UserLookupStates(StatesGroup):
    query = State()


class BalanceStates(StatesGroup):
    query = State()
    delta = State()


@admin_router.message(F.text == "/start")
async def admin_start(message: Message, state: FSMContext):
    await state.clear()
    users_service.get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer("Admin bot: меню", reply_markup=admin_menu())


@admin_router.message(StateFilter("*"), F.text == "➕ Создать событие")
async def create_event_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(CreateEventStates.title)
    await message.answer("Название события:", reply_markup=cancel_kb())


@admin_router.message(CreateEventStates.title, F.text == "❌ Отмена")
@admin_router.message(CreateEventStates.description, F.text == "❌ Отмена")
@admin_router.message(CreateEventStates.photo, F.text == "❌ Отмена")
@admin_router.message(CreateEventStates.options, F.text == "❌ Отмена")
@admin_router.message(CreateEventStates.fee, F.text == "❌ Отмена")
async def create_event_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=admin_menu())


@admin_router.message(CreateEventStates.title)
async def create_event_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(CreateEventStates.description)
    await message.answer("Описание или '-' :", reply_markup=cancel_kb())


@admin_router.message(CreateEventStates.description)
async def create_event_desc(message: Message, state: FSMContext):
    desc = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(CreateEventStates.photo)
    await message.answer("Фото или '-' :", reply_markup=cancel_kb())


@admin_router.message(CreateEventStates.photo, F.text == "-")
async def create_event_no_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=None)
    await state.set_state(CreateEventStates.options)
    await message.answer("Варианты через запятую (мин 2):", reply_markup=cancel_kb())


@admin_router.message(CreateEventStates.photo, F.photo)
async def create_event_photo(message: Message, state: FSMContext):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    await state.set_state(CreateEventStates.options)
    await message.answer("Варианты через запятую (мин 2):", reply_markup=cancel_kb())


@admin_router.message(CreateEventStates.photo)
async def create_event_photo_invalid(message: Message, state: FSMContext):
    await message.answer("Нужно фото или '-'.", reply_markup=cancel_kb())


@admin_router.message(CreateEventStates.options)
async def create_event_options(message: Message, state: FSMContext):
    options = [o.strip() for o in message.text.split(",") if o.strip()]
    if len(options) < 2:
        return await message.answer("Нужно минимум 2 варианта. Введи ещё раз:")

    await state.update_data(options=options)
    await state.set_state(CreateEventStates.fee)
    await message.answer("Комиссия % (например 5). Если 0 — без комиссии:", reply_markup=cancel_kb())


@admin_router.message(CreateEventStates.fee)
async def create_event_fee(message: Message, state: FSMContext):
    try:
        fee_percent = _to_float(message.text) / 100.0
        if fee_percent < 0 or fee_percent >= 1:
            raise ValueError
    except Exception:
        return await message.answer("Некорректно. Введи число 0..99 (например 5).")

    data = await state.get_data()
    title = data["title"]
    desc = data.get("description")
    photo_file_id = data.get("photo_file_id")
    options = data["options"]

    try:
        e = events_service.create_event(title, desc, options, photo_file_id, fee_percent=fee_percent)
    except TypeError:
        e = events_service.create_event(title, desc, options, photo_file_id)

    await state.clear()
    await message.answer(f"✅ Создано событие #{e.id}", reply_markup=admin_menu())


@admin_router.message(StateFilter("*"), F.text == "🔒 Закрыть событие")
async def close_event_start(message: Message, state: FSMContext):
    await state.clear()
    events = events_service.get_active_events()
    if not events:
        return await message.answer("Активных событий нет.", reply_markup=admin_menu())

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"#{e.id} {e.title}", callback_data=f"cl:{e.id}")]
            for e in events
        ]
    )
    await message.answer("Выбери событие для закрытия:", reply_markup=kb)


@admin_router.callback_query(F.data.startswith("cl:"))
async def close_event_choose_winner(cb: CallbackQuery):
    event_id = int(cb.data.split(":")[1])
    e = events_service.get_event(event_id)
    if not e or not getattr(e, "is_active", False):
        return await cb.answer("Событие не активно", show_alert=True)

    options = events_service.parse_options(e)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=opt, callback_data=f"win:{event_id}:{i}")]
            for i, opt in enumerate(options)
        ]
    )
    await cb.message.answer("Выбери победный вариант:", reply_markup=kb)
    await cb.answer()


@admin_router.callback_query(F.data.startswith("win:"))
async def close_event_do(cb: CallbackQuery):
    _, event_id_str, idx_str = cb.data.split(":")
    event_id = int(event_id_str)
    idx = int(idx_str)

    e = events_service.get_event(event_id)
    if not e:
        return await cb.answer("Не найдено", show_alert=True)

    options = events_service.parse_options(e)
    if idx < 0 or idx >= len(options):
        return await cb.answer("Неверный вариант", show_alert=True)

    winner = options[idx]

    try:
        settled = bets_service.settle_event(event_id, winner)
    except ValueError as ex:
        return await cb.answer(str(ex), show_alert=True)

    for r in settled.get("results", []):
        tg_id = int(r["tg_id"])
        if r["bet_status"] == "won":
            await _notify_user(
                tg_id,
                f"🏁 Событие завершено: <b>{settled.get('event_title','')}</b>\n"
                f"Победитель: <b>{winner}</b>\n"
                f"✅ Выигрыш: <b>{float(r['win_amount']):.2f}</b>\n"
                f"Финальный кэф: <b>{float(settled.get('final_coeff', 1.0)):.2f}</b>",
            )
        else:
            await _notify_user(
                tg_id,
                f"🏁 Событие завершено: <b>{settled.get('event_title','')}</b>\n"
                f"Победитель: <b>{winner}</b>\n"
                f"❌ Ставка проиграла.\n"
                f"Финальный кэф: <b>{float(settled.get('final_coeff', 1.0)):.2f}</b>",
            )

    total_pool = settled.get("total_pool")
    commission = settled.get("commission_amount")
    summary = (
        f"✅ Событие #{event_id} закрыто.\n"
        f"Победитель: <b>{winner}</b>\n"
        f"Финальный кэф: <b>{float(settled.get('final_coeff', 1.0)):.2f}</b>\n"
    )
    if total_pool is not None:
        summary += f"Пул: <b>{float(total_pool):.2f}</b>\n"
    if commission is not None:
        summary += f"Комиссия: <b>{float(commission):.2f}</b>\n"

    await cb.message.answer(summary, reply_markup=admin_menu())
    await cb.answer("Закрыто ✅", show_alert=True)


@admin_router.message(StateFilter("*"), F.text == "📚 История событий")
async def history_events(message: Message, state: FSMContext):
    await state.clear()
    with session_scope() as s:
        events = s.query(Event).order_by(Event.id.desc()).limit(30).all()

    if not events:
        return await message.answer("Событий нет.", reply_markup=admin_menu())

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"#{e.id} {'🟢' if e.is_active else '🏁'} {e.title}", callback_data=f"hev:{e.id}")]
            for e in events
        ]
    )
    await message.answer("События:", reply_markup=kb)


@admin_router.callback_query(F.data.startswith("hev:"))
async def history_event_open(cb: CallbackQuery):
    event_id = int(cb.data.split(":")[1])
    with session_scope() as s:
        e = s.query(Event).filter_by(id=event_id).one_or_none()
        if not e:
            return await cb.answer("Не найдено", show_alert=True)

        p = s.query(Proposal).filter(Proposal.approved_event_id == e.id).one_or_none()

        src = "создано вручную"
        if p:
            author = s.query(User).filter_by(id=p.user_id).one_or_none()
            reviewer = s.query(User).filter_by(id=p.reviewer_id).one_or_none()
            src = (
                f"из предложения #{p.id}\n"
                f"автор: {author.telegram_id if author else '-'} @{author.username if author and author.username else '-'}\n"
                f"одобрил: {reviewer.telegram_id if reviewer else '-'} @{reviewer.username if reviewer and reviewer.username else '-'}"
            )

    fee = float(getattr(e, "fee_percent", 0.0) or 0.0)
    text = (
        f"🏟 Событие #{e.id}\n"
        f"Название: <b>{e.title}</b>\n"
        f"Активно: {bool(e.is_active)}\n"
        f"Комиссия: <b>{fee*100:.1f}%</b>\n"
        f"Победитель: <b>{getattr(e, 'result_option', None) or '-'}</b>\n"
        f"Фин.кэф: <b>{float(getattr(e, 'result_coeff', 0.0)):.2f}</b>\n" if getattr(e, "result_coeff", None) is not None else
        f"🏟 Событие #{e.id}\nНазвание: <b>{e.title}</b>\nАктивно: {bool(e.is_active)}\nКомиссия: <b>{fee*100:.1f}%</b>\nПобедитель: <b>{getattr(e, 'result_option', None) or '-'}</b>\n"
    )
    closed_at = getattr(e, "closed_at", None)
    if closed_at:
        text += f"Закрыто: {closed_at}\n"
    text += f"\nИсточник:\n{src}"

    for part in _chunk(text):
        await cb.message.answer(part)
    await cb.answer()


@admin_router.message(StateFilter("*"), F.text == "💡 История предложений")
async def history_proposals(message: Message, state: FSMContext):
    await state.clear()
    with session_scope() as s:
        props = s.query(Proposal).order_by(Proposal.id.desc()).limit(30).all()

    if not props:
        return await message.answer("Предложений нет.", reply_markup=admin_menu())

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"#{p.id} {p.status.value} | {p.title}", callback_data=f"hpr:{p.id}")]
            for p in props
        ]
    )
    await message.answer("Предложения:", reply_markup=kb)


@admin_router.callback_query(F.data.startswith("hpr:"))
async def history_proposal_open(cb: CallbackQuery):
    pid = int(cb.data.split(":")[1])
    with session_scope() as s:
        p = s.query(Proposal).filter_by(id=pid).one_or_none()
        if not p:
            return await cb.answer("Не найдено", show_alert=True)

        author = s.query(User).filter_by(id=p.user_id).one_or_none()
        reviewer = s.query(User).filter_by(id=p.reviewer_id).one_or_none()

    text = (
        f"💡 Предложение #{p.id}\n"
        f"Статус: <b>{p.status.value}</b>\n"
        f"Название: <b>{p.title}</b>\n"
        f"Автор: <code>{author.telegram_id if author else '-'}</code> @{author.username if author and author.username else '-'}\n"
        f"Проверил: <code>{reviewer.telegram_id if reviewer else '-'}</code> @{reviewer.username if reviewer and reviewer.username else '-'}\n"
        f"Создано: {p.created_at}\n"
        f"Проверено: {p.reviewed_at or '-'}\n"
        f"Event: {p.approved_event_id or '-'}\n"
        f"Причина отклонения: {p.reject_reason or '-'}"
    )
    for part in _chunk(text):
        await cb.message.answer(part)
    await cb.answer()


@admin_router.message(StateFilter("*"), F.text == "🆘 История тикетов")
async def history_tickets(message: Message, state: FSMContext):
    await state.clear()
    with session_scope() as s:
        tickets = s.query(Ticket).order_by(Ticket.id.desc()).limit(30).all()

    if not tickets:
        return await message.answer("Тикетов нет.", reply_markup=admin_menu())

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"#{t.id} {t.status.value}", callback_data=f"htk:{t.id}")]
            for t in tickets
        ]
    )
    await message.answer("Тикеты:", reply_markup=kb)


@admin_router.callback_query(F.data.startswith("htk:"))
async def history_ticket_open(cb: CallbackQuery):
    tid = int(cb.data.split(":")[1])
    with session_scope() as s:
        t = s.query(Ticket).filter_by(id=tid).one_or_none()
        if not t:
            return await cb.answer("Не найдено", show_alert=True)

        author = s.query(User).filter_by(id=t.user_id).one_or_none()
        msgs = (
            s.query(TicketMessage)
            .filter(TicketMessage.ticket_id == tid)
            .order_by(TicketMessage.id.asc())
            .limit(300)
            .all()
        )

    header = (
        f"🧾 Тикет #{tid}\n"
        f"Статус: <b>{t.status.value}</b>\n"
        f"От: <code>{author.telegram_id if author else '-'}</code> @{author.username if author and author.username else '-'}\n"
        f"Создан: {t.created_at}\n"
        f"Закрыт: {t.closed_at or '-'}\n\n"
        f"Диалог:\n"
    )

    lines = [header]
    for m in msgs:
        who = "👤" if m.sender_role.value == "user" else "🛠"
        lines.append(f"{who} {m.text}")

    text = "\n".join(lines)
    for part in _chunk(text):
        await cb.message.answer(part)
    await cb.answer()


@admin_router.message(StateFilter("*"), F.text == "🔎 Пользователь")
async def user_lookup_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserLookupStates.query)
    await message.answer("Введи telegram_id или @username:", reply_markup=cancel_kb())


@admin_router.message(UserLookupStates.query, F.text == "❌ Отмена")
async def user_lookup_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=admin_menu())


@admin_router.message(UserLookupStates.query)
async def user_lookup_done(message: Message, state: FSMContext):
    q = message.text.strip()
    if q.startswith("@"):
        q = q[1:]

    with session_scope() as s:
        if q.isdigit():
            u = s.query(User).filter(User.telegram_id == int(q)).one_or_none()
        else:
            u = s.query(User).filter(User.username == q).one_or_none()

        if not u:
            await state.clear()
            return await message.answer(
                "Пользователь не найден.\n"
                "Важно: он должен хотя бы 1 раз нажать /start в user_bot.",
                reply_markup=admin_menu(),
            )

        bets = s.query(Bet).filter(Bet.user_id == u.id).order_by(Bet.id.desc()).limit(20).all()

        total_bet = float(sum(float(b.amount) for b in bets))
        total_win = float(sum(float(b.win_amount or 0.0) for b in bets))
        won = sum(1 for b in bets if b.status == "won")
        lost = sum(1 for b in bets if b.status == "lost")
        pending = sum(1 for b in bets if b.status == "pending")

        role_value = u.role.value if hasattr(u.role, "value") else str(u.role)

    await state.clear()

    text = (
        f"👤 <b>{u.username or '-'}</b>\n"
        f"tg_id: <code>{u.telegram_id}</code>\n"
        f"роль: <b>{role_value}</b>\n"
        f"баланс: <b>{float(u.balance):.2f}</b>\n\n"
        f"последние ставки (20): ✅{won} ❌{lost} ⏳{pending}\n"
        f"поставил (по 20): {total_bet:.2f}\n"
        f"выиграл (по 20): {total_win:.2f}\n\n"
    )

    if bets:
        lines = []
        for b in bets:
            dt = b.created_at.strftime("%Y-%m-%d %H:%M") if b.created_at else ""
            lines.append(
                f"{dt} | {b.status} | ev#{b.event_id} | {b.option} | "
                f"{float(b.amount):.2f} | win:{float(b.win_amount or 0.0):.2f}"
            )
        text += "Ставки:\n" + "\n".join(lines)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Сделать USER", callback_data=f"setrole:{u.telegram_id}:user"),
                InlineKeyboardButton(text="Сделать MOD", callback_data=f"setrole:{u.telegram_id}:moderator"),
            ],
            [InlineKeyboardButton(text="Сделать ADMIN", callback_data=f"setrole:{u.telegram_id}:admin")],
        ]
    )

    for part in _chunk(text):
        await message.answer(part, reply_markup=kb if part == _chunk(text)[0] else None)


@admin_router.callback_query(F.data.startswith("setrole:"))
async def set_role_cb(cb: CallbackQuery):
    _, tg_id_str, role = cb.data.split(":")
    tg_id = int(tg_id_str)
    try:
        users_service.set_role(tg_id, role)
        await cb.answer("Роль обновлена ✅", show_alert=True)
    except Exception as e:
        await cb.answer(str(e), show_alert=True)


@admin_router.message(StateFilter("*"), F.text == "💰 Баланс юзера")
async def balance_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(BalanceStates.query)
    await message.answer("Введи telegram_id или @username:", reply_markup=cancel_kb())


@admin_router.message(BalanceStates.query, F.text == "❌ Отмена")
@admin_router.message(BalanceStates.delta, F.text == "❌ Отмена")
async def balance_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=admin_menu())


@admin_router.message(BalanceStates.query)
async def balance_user(message: Message, state: FSMContext):
    q = message.text.strip()
    if q.startswith("@"):
        q = q[1:]

    with session_scope() as s:
        if q.isdigit():
            u = s.query(User).filter(User.telegram_id == int(q)).one_or_none()
        else:
            u = s.query(User).filter(User.username == q).one_or_none()

    if not u:
        await state.clear()
        return await message.answer("Пользователь не найден.", reply_markup=admin_menu())

    await state.update_data(tg_id=int(u.telegram_id))
    await state.set_state(BalanceStates.delta)
    await message.answer(
        f"Пользователь найден: <code>{u.telegram_id}</code> @{u.username or '-'}\n"
        "Введи delta (например 100 или -50):",
        reply_markup=cancel_kb()
    )


@admin_router.message(BalanceStates.delta)
async def balance_delta(message: Message, state: FSMContext):
    data = await state.get_data()
    tg_id = int(data["tg_id"])
    try:
        delta = _to_float(message.text)
    except Exception:
        return await message.answer("Delta должно быть числом (например 100 или -50).")

    u = users_service.adjust_balance(tg_id, delta)
    await state.clear()
    await message.answer(f"✅ Новый баланс: <b>{float(u.balance):.2f}</b>", reply_markup=admin_menu())
