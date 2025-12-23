import json
from datetime import datetime
from app.db.session import session_scope
from app.db.models import Proposal, ProposalStatus, User
from app.services import events as events_service

def create_proposal(user_tg_id: int, title: str, description: str | None, options: list[str], photo_file_id: str | None):
    options = [o.strip() for o in options if o.strip()]
    if len(options) < 2:
        raise ValueError("Нужно минимум 2 варианта")
    with session_scope() as s:
        u = s.query(User).filter_by(telegram_id=user_tg_id).one()
        p = Proposal(
            user_id=u.id,
            title=title.strip(),
            description=description,
            options=json.dumps(options, ensure_ascii=False),
            photo_file_id=photo_file_id,
            status=ProposalStatus.pending,
            created_at=datetime.utcnow()
        )
        s.add(p)
        s.flush()
        return p

def list_pending(limit: int = 30):
    with session_scope() as s:
        return s.query(Proposal).filter_by(status=ProposalStatus.pending).order_by(Proposal.id.desc()).limit(limit).all()

def get(proposal_id: int):
    with session_scope() as s:
        return s.query(Proposal).filter_by(id=proposal_id).one_or_none()

def parse_options(p: Proposal) -> list[str]:
    return json.loads(p.options)

def approve(proposal_id: int, reviewer_tg_id: int, fee_percent: float = 0.0):
    with session_scope() as s:
        reviewer = s.query(User).filter_by(telegram_id=reviewer_tg_id).one()
        p = s.query(Proposal).filter_by(id=proposal_id).one()
        if p.status != ProposalStatus.pending:
            raise ValueError("Уже обработано")

        opts = json.loads(p.options)
        event = events_service.create_event(p.title, p.description, opts, p.photo_file_id, fee_percent=fee_percent)

        p.status = ProposalStatus.approved
        p.reviewer_id = reviewer.id
        p.approved_event_id = event.id
        p.reviewed_at = datetime.utcnow()

        s.flush()
        return p, event

def reject(proposal_id: int, reviewer_tg_id: int, reason: str):
    with session_scope() as s:
        reviewer = s.query(User).filter_by(telegram_id=reviewer_tg_id).one()
        p = s.query(Proposal).filter_by(id=proposal_id).one()
        if p.status != ProposalStatus.pending:
            raise ValueError("Уже обработано")
        p.status = ProposalStatus.rejected
        p.reviewer_id = reviewer.id
        p.reject_reason = reason.strip()
        p.reviewed_at = datetime.utcnow()
        s.flush()
        return p
