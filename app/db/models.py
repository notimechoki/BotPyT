from datetime import datetime
import enum
from sqlalchemy import Column, String, Boolean, Float, ForeignKey, Text, DateTime, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import BIGINT, INTEGER
from app.db.base import Base

class UserRole(str, enum.Enum):
    user = "user"
    moderator = "moderator"
    admin = "admin"

class ProposalStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"

class TicketStatus(str, enum.Enum):
    open = "open"
    closed = "closed"

class SenderRole(str, enum.Enum):
    user = "user"
    moderator = "moderator"
    admin = "admin"


class User(Base):
    __tablename__ = "users"

    id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    telegram_id = Column(BIGINT(unsigned=True), unique=True, index=True, nullable=False)
    username = Column(String(64), nullable=True)

    balance = Column(Float, default=1000.0)
    role = Column(Enum(UserRole), default=UserRole.user, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow)

    bets = relationship("Bet", back_populates="user")



class Event(Base):
    __tablename__ = "events"

    id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    options = Column(Text, nullable=False)
    seed_pool = Column(Text, nullable=False)

    fee_percent = Column(Float, default=0.05)
    result_coeff = Column(Float, nullable=True)
    closed_at = Column(DateTime, nullable=True)

    photo_file_id = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True)
    result_option = Column(String(128), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)



class Bet(Base):
    __tablename__ = "bets"

    id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    user_id = Column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=False)
    event_id = Column(INTEGER(unsigned=True), ForeignKey("events.id"), nullable=False)

    option = Column(String(128), nullable=False)
    amount = Column(Float, nullable=False)

    coeff_snapshot = Column(Float, nullable=False)
    payout_coefficient = Column(Float, nullable=True)

    win_amount = Column(Float, nullable=True)
    status = Column(String(32), default="pending")

    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bets")



class Proposal(Base):
    __tablename__ = "proposals"

    id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    user_id = Column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=False)

    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    options = Column(Text, nullable=False)
    photo_file_id = Column(String(255), nullable=True)

    status = Column(Enum(ProposalStatus), default=ProposalStatus.pending, nullable=False)
    reviewer_id = Column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=True)
    reject_reason = Column(Text, nullable=True)

    approved_event_id = Column(INTEGER(unsigned=True), ForeignKey("events.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)



class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    user_id = Column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=False)

    status = Column(Enum(TicketStatus), default=TicketStatus.open, nullable=False)

    assignee_id = Column(INTEGER(unsigned=True), ForeignKey("users.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)



class TicketMessage(Base):
    __tablename__ = "ticket_messages"

    id = Column(INTEGER(unsigned=True), primary_key=True, autoincrement=True)
    ticket_id = Column(INTEGER(unsigned=True), ForeignKey("tickets.id"), nullable=False)

    sender_role = Column(Enum(SenderRole), nullable=False)
    sender_tg_id = Column(BIGINT(unsigned=True), nullable=False)

    text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)