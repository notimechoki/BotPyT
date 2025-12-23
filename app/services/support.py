from datetime import datetime
from app.db.session import session_scope
from app.db.models import Ticket, TicketMessage, TicketStatus, SenderRole, User, UserRole

def get_or_create_open_ticket(user_tg_id: int) -> Ticket:
    with session_scope() as s:
        u = s.query(User).filter_by(telegram_id=user_tg_id).one()
        t = s.query(Ticket).filter_by(user_id=u.id, status=TicketStatus.open).one_or_none()
        if t:
            return t
        t = Ticket(user_id=u.id, status=TicketStatus.open, created_at=datetime.utcnow())
        s.add(t)
        s.flush()
        return t

def add_user_message(ticket_id: int, user_tg_id: int, text: str):
    with session_scope() as s:
        msg = TicketMessage(
            ticket_id=ticket_id,
            sender_role=SenderRole.user,
            sender_tg_id=user_tg_id,
            text=text,
            created_at=datetime.utcnow(),
        )
        s.add(msg)
        s.flush()
        return msg

def add_staff_message(ticket_id: int, staff_tg_id: int, staff_role: str, text: str):
    role = SenderRole.moderator if staff_role == "moderator" else SenderRole.admin
    with session_scope() as s:
        msg = TicketMessage(
            ticket_id=ticket_id,
            sender_role=role,
            sender_tg_id=staff_tg_id,
            text=text,
            created_at=datetime.utcnow(),
        )
        s.add(msg)
        s.flush()
        return msg

def list_open_tickets(limit: int = 30):
    with session_scope() as s:
        return s.query(Ticket).filter_by(status=TicketStatus.open).order_by(Ticket.id.desc()).limit(limit).all()

def get_ticket(ticket_id: int):
    with session_scope() as s:
        return s.query(Ticket).filter_by(id=ticket_id).one_or_none()

def get_ticket_messages(ticket_id: int, limit: int = 20):
    with session_scope() as s:
        return (
            s.query(TicketMessage)
            .filter_by(ticket_id=ticket_id)
            .order_by(TicketMessage.id.desc())
            .limit(limit)
            .all()[::-1]
        )

def assign_ticket(ticket_id: int, staff_tg_id: int):
    with session_scope() as s:
        staff = s.query(User).filter_by(telegram_id=staff_tg_id).one()
        t = s.query(Ticket).filter_by(id=ticket_id).one()
        t.assignee_id = staff.id
        s.flush()
        return t

def close_ticket(ticket_id: int):
    with session_scope() as s:
        t = s.query(Ticket).filter_by(id=ticket_id).one()
        t.status = TicketStatus.closed
        t.closed_at = datetime.utcnow()
        s.flush()
        return t

def get_ticket_user_tg_id(ticket_id: int) -> int:
    with session_scope() as s:
        t = s.query(Ticket).filter_by(id=ticket_id).one()
        u = s.query(User).filter_by(id=t.user_id).one()
        return int(u.telegram_id)
    
def is_ticket_open(ticket_id: int) -> bool:
    with session_scope() as s:
        t = s.query(Ticket).filter_by(id=ticket_id).one_or_none()
        return bool(t and t.status == TicketStatus.open)
    
