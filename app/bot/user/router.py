from __future__ import annotations

from aiogram import Router, F, Bot
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    CallbackQuery,
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import MOD_BOT_TOKEN
from app.services import users as users_service
from app.services import events as events_service
from app.services import bets as bets_service
from app.services import proposals as proposals_service
from app.services import support as support_service

from app.services import odds as odds_service

user_router = Router()


def menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔥 События"), KeyboardButton(text="🗂 Архив")],
            [KeyboardButton(text="💰 Баланс"), KeyboardButton(text="📊 Мои ставки")],
            [KeyboardButton(text="🎯 Активные ставки")],
            [KeyboardButton(text="💡 Предложить событие"), KeyboardButton(text="🆘 Поддержка")],
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


async def _notify_staff_via_mod_bot(text: str, kb: InlineKeyboardMarkup | None = None, photo_file_id: str | None = None):
    staff_ids = users_service.get_staff_tg_ids()
    if not staff_ids:
        return

    async with Bot(MOD_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) as bot:
        for tg_id in staff_ids:
            try:
                if photo_file_id:
                    await bot.send_photo(tg_id, photo_file_id, caption=text, reply_markup=kb)
                else:
                    await bot.send_message(tg_id, text, reply_markup=kb)
            except Exception:
                pass


def _get_event_coeffs_and_pools(event_id: int, event) -> tuple[dict[str, float], float | None, float]:
    fee = float(getattr(event, "fee_percent", 0.0) or 0.0)

    if hasattr(odds_service, "compute_pools") and hasattr(odds_service, "compute_coeffs_from_pools"):
        pool_by_opt, total_pool, fee2 = odds_service.compute_pools(event_id)
        fee = float(fee2)
        coeffs = odds_service.compute_coeffs_from_pools(pool_by_opt, total_pool, fee)
        return coeffs, float(total_pool), fee

    if hasattr(odds_service, "compute_current_coeffs"):
        coeffs = odds_service.compute_current_coeffs(event_id)
        return coeffs, None, fee

    return {}, None, fee


class BetStates(StatesGroup):
    amount = State()


class ProposalStates(StatesGroup):
    title = State()
    description = State()
    options = State()
    photo = State()


class SupportStates(StatesGroup):
    chat = State()


@user_router.message(F.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    u = users_service.get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Привет! Баланс: <b>{u.balance:.2f}</b>",
        reply_markup=menu_kb(),
    )


@user_router.message(StateFilter("*"), F.text == "💰 Баланс")
async def show_balance(message: Message, state: FSMContext):
    await state.clear()
    u = users_service.get_or_create_user(message.from_user.id, message.from_user.username)
    await message.answer(f"Баланс: <b>{u.balance:.2f}</b>", reply_markup=menu_kb())


@user_router.message(StateFilter("*"), F.text == "🔥 События")
async def list_events(message: Message, state: FSMContext):
    await state.clear()
    events = events_service.get_active_events()
    if not events:
        return await message.answer("Сейчас нет активных событий.", reply_markup=menu_kb())

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"#{e.id} {e.title}", callback_data=f"ev:{e.id}")]
            for e in events
        ]
    )
    await message.answer("Выбери событие:", reply_markup=kb)


@user_router.message(StateFilter("*"), F.text == "🗂 Архив")
async def list_archive(message: Message, state: FSMContext):
    await state.clear()
    if hasattr(events_service, "get_archived_events"):
        items = events_service.get_archived_events(limit=30)
    else:
        items = []

    if not items:
        return await message.answer("Архив пуст.", reply_markup=menu_kb())

    lines = []
    for e in items:
        winner = getattr(e, "result_option", None) or "-"
        coeff = getattr(e, "result_coeff", None)
        if coeff is not None:
            lines.append(f"🏁 #{e.id} {e.title}\nПобедитель: {winner} | фин.кэф: {float(coeff):.2f}\n")
        else:
            lines.append(f"🏁 #{e.id} {e.title}\nПобедитель: {winner}\n")
    await message.answer("\n".join(lines)[:3900], reply_markup=menu_kb())


@user_router.callback_query(F.data.startswith("ev:"))
async def event_details(cb: CallbackQuery):
    event_id = int(cb.data.split(":")[1])
    e = events_service.get_event(event_id)
    if not e or not getattr(e, "is_active", False):
        return await cb.answer("Событие не активно или не найдено", show_alert=True)

    options = events_service.parse_options(e)
    coeffs, total_pool, fee = _get_event_coeffs_and_pools(event_id, e)

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{opt} (кэф ~{coeffs.get(opt, 1.0):.2f})", callback_data=f"opt:{event_id}:{i}")]
            for i, opt in enumerate(options)
        ]
    )

    header = (
        f"<b>{e.title}</b>\n"
        f"{e.description or ''}\n\n"
        f"Комиссия: <b>{fee*100:.1f}%</b>\n"
    )
    if total_pool is not None:
        header += f"Пул сейчас: <b>{total_pool:.2f}</b>\n"
    header += "\nВыбери вариант. Кэф динамический, финальная выплата считается при закрытии события."

    if getattr(e, "photo_file_id", None):
        await cb.message.answer_photo(e.photo_file_id, caption=header, reply_markup=kb)
    else:
        await cb.message.answer(header, reply_markup=kb)

    await cb.answer()


@user_router.callback_query(F.data.startswith("opt:"))
async def choose_option(cb: CallbackQuery, state: FSMContext):
    _, event_id_str, idx_str = cb.data.split(":")
    event_id = int(event_id_str)
    idx = int(idx_str)

    e = events_service.get_event(event_id)
    if not e or not getattr(e, "is_active", False):
        return await cb.answer("Событие не активно", show_alert=True)

    options = events_service.parse_options(e)
    if idx < 0 or idx >= len(options):
        return await cb.answer("Неверный вариант", show_alert=True)

    option = options[idx]

    await state.set_state(BetStates.amount)
    await state.update_data(event_id=event_id, option=option)

    await cb.message.answer(
        f"Вариант: <b>{option}</b>\nВведи сумму ставки:",
        reply_markup=cancel_kb(),
    )
    await cb.answer()


@user_router.message(BetStates.amount, F.text == "❌ Отмена")
async def cancel_bet(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=menu_kb())


@user_router.message(BetStates.amount)
async def enter_amount(message: Message, state: FSMContext):
    try:
        amount = _to_float(message.text)
        if amount <= 0:
            raise ValueError
    except Exception:
        return await message.answer("Некорректная сумма. Введи число > 0 или ❌ Отмена")

    data = await state.get_data()
    event_id = int(data["event_id"])
    option = str(data["option"])

    try:
        b = bets_service.place_bet(
            telegram_id=message.from_user.id,
            event_id=event_id,
            option=option,
            amount=amount,
        )
    except TypeError:
        b = bets_service.place_bet(message.from_user.id, event_id, option, amount)
    except ValueError as e:
        await state.clear()
        return await message.answer(f"Ошибка: {e}", reply_markup=menu_kb())

    await state.clear()

    snap = getattr(b, "coeff_snapshot", None)
    if snap is None:
        snap = getattr(b, "coefficient", 1.0)

    await message.answer(
        "✅ Ставка принята!\n"
        f"Сумма: <b>{float(b.amount):.2f}</b>\n"
        f"Кэф на момент ставки: <b>~{float(snap):.2f}</b>\n"
        "Выплата рассчитывается при закрытии события (финальный кэф зависит от пула).",
        reply_markup=menu_kb(),
    )


@user_router.message(StateFilter("*"), F.text == "📊 Мои ставки")
async def show_all_bets(message: Message, state: FSMContext):
    await state.clear()
    bets = bets_service.get_user_bets(message.from_user.id, only_active=False)
    if not bets:
        return await message.answer("У тебя пока нет ставок.", reply_markup=menu_kb())

    lines = []
    for b in bets[:30]:
        status = getattr(b, "status", "pending")
        emoji = {"pending": "⏳", "won": "✅", "lost": "❌"}.get(status, "⏳")
        snap = getattr(b, "coeff_snapshot", None)
        if snap is None:
            snap = getattr(b, "coefficient", 1.0)

        dt = getattr(b, "created_at", None)
        dt_txt = dt.strftime("%Y-%m-%d %H:%M") if dt else ""

        lines.append(
            f"{emoji} {dt_txt} | ev#{b.event_id} | {b.option} | "
            f"{float(b.amount):.2f} | кэф~{float(snap):.2f} | win:{float(getattr(b, 'win_amount', 0.0) or 0.0):.2f}"
        )

    await message.answer("\n".join(lines)[:3900], reply_markup=menu_kb())


@user_router.message(StateFilter("*"), F.text == "🎯 Активные ставки")
async def show_active_bets(message: Message, state: FSMContext):
    await state.clear()
    bets = bets_service.get_user_bets(message.from_user.id, only_active=True)
    if not bets:
        return await message.answer("У тебя нет активных ставок.", reply_markup=menu_kb())

    lines = []
    for b in bets[:30]:
        snap = getattr(b, "coeff_snapshot", None)
        if snap is None:
            snap = getattr(b, "coefficient", 1.0)

        dt = getattr(b, "created_at", None)
        dt_txt = dt.strftime("%Y-%m-%d %H:%M") if dt else ""

        lines.append(f"⏳ {dt_txt} | ev#{b.event_id} | {b.option} | {float(b.amount):.2f} | кэф~{float(snap):.2f}")

    await message.answer("\n".join(lines)[:3900], reply_markup=menu_kb())


@user_router.message(StateFilter("*"), F.text == "💡 Предложить событие")
async def proposal_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ProposalStates.title)
    await message.answer("Введи название предложения:", reply_markup=cancel_kb())


@user_router.message(ProposalStates.title, F.text == "❌ Отмена")
@user_router.message(ProposalStates.description, F.text == "❌ Отмена")
@user_router.message(ProposalStates.options, F.text == "❌ Отмена")
@user_router.message(ProposalStates.photo, F.text == "❌ Отмена")
async def proposal_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменено.", reply_markup=menu_kb())


@user_router.message(ProposalStates.title)
async def proposal_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text.strip())
    await state.set_state(ProposalStates.description)
    await message.answer("Описание или '-' если без описания:", reply_markup=cancel_kb())


@user_router.message(ProposalStates.description)
async def proposal_desc(message: Message, state: FSMContext):
    desc = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(description=desc)
    await state.set_state(ProposalStates.options)
    await message.answer("Варианты через запятую (минимум 2):", reply_markup=cancel_kb())


@user_router.message(ProposalStates.options)
async def proposal_opts(message: Message, state: FSMContext):
    options = [o.strip() for o in message.text.split(",") if o.strip()]
    if len(options) < 2:
        return await message.answer("Нужно минимум 2 варианта. Введи ещё раз:")

    await state.update_data(options=options)
    await state.set_state(ProposalStates.photo)
    await message.answer("Отправь фото или '-' чтобы без фото:", reply_markup=cancel_kb())


@user_router.message(ProposalStates.photo, F.text == "-")
async def proposal_done_no_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    try:
        p = proposals_service.create_proposal(
            user_tg_id=message.from_user.id,
            title=data["title"],
            description=data.get("description"),
            options=data["options"],
            photo_file_id=None,
        )
    except TypeError:
        p = proposals_service.create_proposal(message.from_user.id, data["title"], data.get("description"), data["options"], None)

    await state.clear()
    await message.answer(f"✅ Отправлено на модерацию. ID #{p.id}", reply_markup=menu_kb())

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть", callback_data=f"prop:{p.id}")]])
    await _notify_staff_via_mod_bot(f"🆕 Предложение #{p.id}\n<b>{data['title']}</b>", kb=kb)


@user_router.message(ProposalStates.photo, F.photo)
async def proposal_done_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    file_id = message.photo[-1].file_id

    try:
        p = proposals_service.create_proposal(
            user_tg_id=message.from_user.id,
            title=data["title"],
            description=data.get("description"),
            options=data["options"],
            photo_file_id=file_id,
        )
    except TypeError:
        p = proposals_service.create_proposal(message.from_user.id, data["title"], data.get("description"), data["options"], file_id)

    await state.clear()
    await message.answer(f"✅ Отправлено на модерацию. ID #{p.id}", reply_markup=menu_kb())

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть", callback_data=f"prop:{p.id}")]])
    await _notify_staff_via_mod_bot(
        f"🆕 Предложение #{p.id}\n<b>{data['title']}</b>",
        kb=kb,
        photo_file_id=file_id,
    )


@user_router.message(StateFilter("*"), F.text == "🆘 Поддержка")
async def support_start(message: Message, state: FSMContext):
    await state.clear()
    t = support_service.get_or_create_open_ticket(message.from_user.id)
    await state.set_state(SupportStates.chat)
    await state.update_data(ticket_id=int(t.id))
    await message.answer(
        f"🆘 Поддержка.\nТикет #{t.id} открыт.\n"
        "Пиши сообщение — оно уйдёт модератору.\n"
        "❌ Отмена — выйти из режима поддержки.",
        reply_markup=cancel_kb(),
    )


@user_router.message(SupportStates.chat, F.text == "❌ Отмена")
async def support_exit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вышел из поддержки.", reply_markup=menu_kb())


@user_router.message(SupportStates.chat)
async def support_message(message: Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = int(data["ticket_id"])

    if hasattr(support_service, "is_ticket_open"):
        if not support_service.is_ticket_open(ticket_id):
            await state.clear()
            return await message.answer(
                f"Тикет #{ticket_id} уже закрыт ✅\n"
                f"Нажми 🆘 Поддержка, чтобы открыть новый.",
                reply_markup=menu_kb(),
            )

    support_service.add_user_message(ticket_id, message.from_user.id, message.text)
    await message.answer("✅ Отправлено модератору. Жди ответа.")

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Открыть тикет", callback_data=f"ticket:{ticket_id}")]])
    await _notify_staff_via_mod_bot(
        f"🆘 Тикет #{ticket_id}\nОт: <code>{message.from_user.id}</code>\n\n{message.text}",
        kb=kb
    )
