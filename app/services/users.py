from app.db.session import session_scope
from app.db.models import User, UserRole
from app.config import ADMINS, MODERATORS

def get_or_create_user(telegram_id: int, username: str | None):
    with session_scope() as s:
        u = s.query(User).filter_by(telegram_id=telegram_id).one_or_none()
        if u:
            if username and u.username != username:
                u.username = username
            return u
        
        role = UserRole.user
        if telegram_id in ADMINS:
            role = UserRole.admin
        elif telegram_id in MODERATORS:
            role = UserRole.moderator

        u = User(telegram_id=telegram_id, username=username, role=role, balance=1000.0)
        s.add(u)
        s.flush()
        return u

def get_role(telegram_id: int) -> str:
    with session_scope() as s:
        u = s.query(User).filter_by(telegram_id=telegram_id).one_or_none()
        return (u.role.value if u else UserRole.user.value)

def set_role(telegram_id: int, role: str):
    if role not in ("user", "moderator", "admin"):
        raise ValueError("bad role")
    with session_scope() as s:
        u = s.query(User).filter_by(telegram_id=telegram_id).one()
        u.role = UserRole(role)

def get_staff_tg_ids() -> list[int]:
    with session_scope() as s:
        rows = s.query(User.telegram_id).filter(User.role.in_([UserRole.moderator, UserRole.admin])).all()
        return [int(r[0]) for r in rows]

def adjust_balance(telegram_id: int, delta: float):
    with session_scope() as s:
        u = s.query(User).filter_by(telegram_id=telegram_id).one()
        u.balance += delta
        return u