from datetime import datetime
from app.db.session import session_scope
from app.db.models import Bet, User, Event
from app.services.odds import compute_pools, compute_coeffs_from_pools


def place_bet(telegram_id: int, event_id: int, option: str, amount: float) -> Bet:
    if amount <= 0:
        raise ValueError("Sum need > 0")
    
    with session_scope() as s:
        user = s.query(User).filter_by(telegram_id=telegram_id).one()
        event = s.query(Event).filter_by(id=event_id, is_active=True).one_or_none()

        if not event:
            raise ValueError("Event is not active or not found")
        
        pool_by_opt, total_pool, fee = compute_pools(event_id)
        coeffs = compute_coeffs_from_pools(pool_by_opt, total_pool, fee)
        if option not in coeffs:
            raise ValueError("Wrong Option")
        
        if user.balance < amount:
            raise ValueError("Not enought money")
        
        user.balance -= amount

        b = Bet(
            user_id=user.id,
            event_id=event.id,
            option=option,
            amount=float(amount),
            coeff_snapshot=float(coeffs[option]),
            payout_coefficient=None,
            win_amount=None,
            status="pending",
            created_at=datetime.utcnow(),
        )

        s.add(b)
        s.flush()
        return b

def get_user_bets(telegram_id: int, only_active: bool):
    with session_scope() as s:
        q = s.query(Bet).join(User, Bet.user_id == User.id).filter(User.telegram_id == telegram_id).order_by(Bet.id.desc())
        if only_active:
            q = q.filter(Bet.status == "pending")
        return q.limit(50).all()

def settle_event(event_id: int, winner_option: str) -> dict:
    with session_scope() as s:
        event = s.query(Event).filter_by(id=event_id).one_or_none()
        if not event:
            raise ValueError("Событие не найдено")
        if not event.is_active:
            raise ValueError("Событие уже закрыто")

        pool_by_opt, total_pool, fee = compute_pools(event_id)
        coeffs = compute_coeffs_from_pools(pool_by_opt, total_pool, fee)

        if winner_option not in coeffs:
            raise ValueError("Победный вариант не существует")

        final_coeff = float(coeffs[winner_option])

        event.is_active = False
        event.result_option = winner_option
        event.result_coeff = final_coeff
        event.closed_at = datetime.utcnow()

        rows = (
            s.query(Bet, User)
            .join(User, Bet.user_id == User.id)
            .filter(Bet.event_id == event_id)
            .all()
        )

        results = []
        for bet, user in rows:
            bet.payout_coefficient = final_coeff
            if bet.option == winner_option:
                bet.status = "won"
                bet.win_amount = float(bet.amount) * final_coeff
                user.balance += bet.win_amount
            else:
                bet.status = "lost"
                bet.win_amount = 0.0

            results.append({
                "tg_id": int(user.telegram_id),
                "bet_status": bet.status,
                "amount": float(bet.amount),
                "option": bet.option,
                "win_amount": float(bet.win_amount or 0.0),
            })

        commission_amount = total_pool * fee

        return {
            "event_id": event_id,
            "event_title": event.title,
            "winner_option": winner_option,
            "final_coeff": final_coeff,
            "total_pool": float(total_pool),
            "commission_amount": float(commission_amount),
            "pool_by_opt": {k: float(v) for k, v in pool_by_opt.items()},
            "results": results,
        }