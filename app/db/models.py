from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, Enum, ForeignKey, Float, JSON
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func
import enum


class Base(DeclarativeBase):
    pass


class CallStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    no_answer = "no_answer"
    voicemail = "voicemail"
    failed = "failed"
    do_not_call = "do_not_call"


class CallOutcome(str, enum.Enum):
    appointment_booked = "appointment_booked"
    interested = "interested"
    not_interested = "not_interested"
    callback_requested = "callback_requested"
    do_not_call = "do_not_call"
    voicemail_left = "voicemail_left"
    wrong_number = "wrong_number"
    bad_timing = "bad_timing"
    transferred = "transferred"
    no_answer = "no_answer"


class FollowUpType(str, enum.Enum):
    sms = "sms"
    callback = "callback"


class FollowUpStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


class AppointmentStatus(str, enum.Enum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    email = Column(String(150), nullable=True)
    do_not_call = Column(Boolean, default=False)
    # Phase 3: lead scoring & re-engagement
    lead_score = Column(Integer, default=0)          # 0-100, higher = hotter lead
    last_purchase_at = Column(DateTime(timezone=True), nullable=True)
    last_contacted_at = Column(DateTime(timezone=True), nullable=True)
    tags = Column(JSON, default=list)                # e.g. ["vip", "lapsed"]
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    calls = relationship("Call", back_populates="customer")
    appointments = relationship("Appointment", back_populates="customer")
    follow_ups = relationship("FollowUp", back_populates="customer")


class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    script_key = Column(String(50), nullable=False)        # default/fallback script
    # Phase 2: A/B testing — list of script keys to split traffic across
    script_variants = Column(JSON, default=list)           # e.g. ["default", "no_promo_variant"]
    active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    calls = relationship("Call", back_populates="campaign")


class Call(Base):
    __tablename__ = "calls"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    campaign_id = Column(Integer, ForeignKey("campaigns.id"), nullable=False)
    twilio_call_sid = Column(String(50), nullable=True, unique=True)
    status = Column(Enum(CallStatus), default=CallStatus.pending)
    outcome = Column(Enum(CallOutcome), nullable=True)
    # Phase 2: which script variant this call used (for A/B analysis)
    script_variant = Column(String(50), nullable=True)
    # Phase 3: engagement signal captured during the call (0-100)
    interest_score = Column(Integer, default=0)
    # Conversational agent: full turn-by-turn transcript [{role, content}, ...]
    transcript = Column(JSON, default=list)
    duration_seconds = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customer", back_populates="calls")
    campaign = relationship("Campaign", back_populates="calls")


class FollowUp(Base):
    """Phase 2: scheduled SMS or callback after a call."""
    __tablename__ = "follow_ups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=True)
    type = Column(Enum(FollowUpType), nullable=False)
    status = Column(Enum(FollowUpStatus), default=FollowUpStatus.pending)
    message = Column(Text, nullable=True)             # SMS body
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customer", back_populates="follow_ups")


class Appointment(Base):
    """Phase 3: in-store visit booked during a call."""
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    call_id = Column(Integer, ForeignKey("calls.id"), nullable=True)
    status = Column(Enum(AppointmentStatus), default=AppointmentStatus.scheduled)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    customer = relationship("Customer", back_populates="appointments")
