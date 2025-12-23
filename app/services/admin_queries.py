from sqlalchemy import or_
from app.db.session import session_scope
from app.db.models import User, Bet, Event, Proposal, Ticket, TicketMessage

def find_user(query: str) -> User | None:
    q = query.strip()
    if q.startswith("@"):
        q = q[1:]

    with session_scope() as s:
        if q.isdigit():
            return s.query(User).filter(User.telegram_id == int(q)).one_or_none()
        return s.query(User).filter(User.username == q).one_or_none()

def user_bets(user_id: int, limit: int = 50):
    with session_scope() as s:
        return (
            s.query(Bet)
            .filter(Bet.user_id == user_id)
            .order_by(Bet.id.desc())
            .limit(limit)
            .all()
        )

def user_stats(user_id: int) -> dict:
    with session_scope() as s:
        bets = s.query(Bet).filter(Bet.user_id == user_id).all()
    total_bet = sum(float(b.amount) for b in bets)
    total_win = sum(float(b.win_amount or 0) for b in bets)
    won = sum(1 for b in bets if b.status == "won")
    lost = sum(1 for b in bets if b.status == "lost")
    pending = sum(1 for b in bets if b.status == "pending")
    return {
        "count": len(bets),
        "total_bet": total_bet,
        "total_win": total_win,
        "won": won,
        "lost": lost,
        "pending": pending,
    }

def proposals_history(limit: int = 50):
    with session_scope() as s:
        return s.query(Proposal).order_by(Proposal.id.desc()).limit(limit).all()

def tickets_history(limit: int = 50):
    with session_scope() as s:
        return s.query(Ticket).order_by(Ticket.id.desc()).limit(limit).all()

def ticket_messages(ticket_id: int, limit: int = 200):
    with session_scope() as s:
        return (
            s.query(TicketMessage)
            .filter(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.id.asc())
            .limit(limit)
            .all()
        )

def event_history(limit: int = 50):
    with session_scope() as s:
        return s.query(Event).order_by(Event.id.desc()).limit(limit).all()

def proposal_by_event(event_id: int) -> Proposal | None:
    with session_scope() as s:
        return s.query(Proposal).filter(Proposal.approved_event_id == event_id).one_or_none()
