from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    full_name = Column(String(255), nullable=True)
    firm_name = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cases = relationship("Case", back_populates="owner")


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(50), unique=True, nullable=False, index=True)
    case_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    owner = relationship("User", back_populates="cases")


class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(50), nullable=False, index=True)
    evidence_id = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    sha256 = Column(String(128), nullable=True)
    phash = Column(String(128), nullable=True)
    analysis_date = Column(String(100), nullable=True)
    json_report = Column(Text, nullable=True)
    pdf_report = Column(Text, nullable=True)
    file_key = Column(String(500), nullable=True)


class FingerprintIndex(Base):
    __tablename__ = "fingerprint_index"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(50), nullable=True, index=True)
    evidence_id = Column(String(50), nullable=True)
    file_name = Column(String(255), nullable=True)
    phash = Column(String(128), nullable=True)
    pdf_report = Column(Text, nullable=True)
    json_report = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    stripe_session_id = Column(String(255), unique=True, nullable=False, index=True)
    stripe_event_id = Column(String(255), unique=True, nullable=True, index=True)
    stripe_customer_email = Column(String(255), nullable=True)
    stripe_amount_total = Column(Integer, nullable=True)
    stripe_currency = Column(String(10), nullable=True)
    product = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    stripe_subscription_id = Column(String(255), unique=True, nullable=False, index=True)
    stripe_customer_id = Column(String(255), nullable=True, index=True)
    stripe_customer_email = Column(String(255), nullable=True)
    product = Column(String(50), nullable=True)
    tier = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="active")
    file_count = Column(Integer, nullable=True)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CustodyLog(Base):
    __tablename__ = "custody_log"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(50), nullable=False, index=True)
    evidence_id = Column(String(50), nullable=True)
    user_id = Column(Integer, nullable=True)
    user_email = Column(String(255), nullable=True)
    action = Column(String(100), nullable=False)
    detail = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)
    chain_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Certificate(Base):
    __tablename__ = "certificates"

    id = Column(Integer, primary_key=True, index=True)
    certificate_id = Column(String(36), unique=True, nullable=False, index=True)
    type = Column(String(50), nullable=False)
    case_id = Column(String(50), nullable=False, index=True)
    evidence_id = Column(String(50), nullable=True)
    generated_by = Column(String(255), nullable=True)
    pdf_key = Column(String(500), nullable=True)
    chain_verified_at_generation = Column(Boolean, nullable=True)
    file_hash_at_generation = Column(String(128), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())