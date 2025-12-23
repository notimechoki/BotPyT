import json
from datetime import datetime
from app.db.session import session_scope
from app.db.models import Event

DEFAULT_SEED_PER_OPTION = 100.0

def create_event(title: str, description: str | None, options: list[str], photo_file_id: str | None, fee_percent: float = 0.0):
    if len(options) < 2:
        raise ValueError("need 2+ options")
    options = [o.strip() for o in options if o.strip()]
    seed_pool = {opt: DEFAULT_SEED_PER_OPTION for opt in options}

    with session_scope() as s:
        e = Event(
            title=title,
            description=description,
            options=json.dumps(options, ensure_ascii=False),
            seed_pool=json.dumps(seed_pool, ensure_ascii=False),
            photo_file_id=photo_file_id,
            fee_percent=float(fee_percent),
            is_active=True,
            created_at=datetime.utcnow()
        )
        s.add(e)
        s.flush()
        return e

def get_active_events():
    with session_scope() as s:
        return s.query(Event).filter_by(is_active=True).order_by(Event.id.desc()).all()

def get_archived_events(limit: int = 30):
    with session_scope() as s:
        return s.query(Event).filter_by(is_active=False).order_by(Event.id.desc()).limit(limit).all()

def get_event(event_id: int):
    with session_scope() as s:
        return s.query(Event).filter_by(id=event_id).one_or_none()

def parse_options(event: Event) -> list[str]:
    return json.loads(event.options)

def parse_seed_pool(event: Event) -> dict[str, float]:
    return json.loads(event.seed_pool)