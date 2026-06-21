from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String, Text
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
    country = Column(String(2), nullable=True, index=True)
    cookie_consent = Column(Boolean, nullable=True)
    cookie_consent_at = Column(DateTime(timezone=True), nullable=True)
    cookie_consent_version = Column(String(20), nullable=True)
    email_verified = Column(Boolean, default=False, nullable=False, server_default="false")
    email_verification_token = Column(String(128), nullable=True, index=True)
    email_verification_token_expires = Column(DateTime(timezone=True), nullable=True)
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
    web_detection_enabled = Column(Boolean, nullable=False, default=False, server_default="false")

    # C2PA Content Credentials (populated from c2pa_analysis.summarize_for_certificate)
    c2pa_state = Column(String(64), nullable=True)
    c2pa_has_ai_generation = Column(Boolean, nullable=True)
    c2pa_has_ai_modification = Column(Boolean, nullable=True)
    c2pa_signature_valid = Column(Boolean, nullable=True)
    c2pa_claim_generator = Column(String(255), nullable=True)
    c2pa_signature_issuer = Column(String(255), nullable=True)
    c2pa_signature_time = Column(String(50), nullable=True)
    c2pa_plain_english = Column(Text, nullable=True)
    c2pa_analyzed_at = Column(DateTime(timezone=True), nullable=True)
    c2pa_claim_generator_version = Column(String(100), nullable=True)
    c2pa_num_assertions = Column(Integer, nullable=True)
    c2pa_num_ingredients = Column(Integer, nullable=True)
    c2pa_trust_list_status = Column(String(50), nullable=True)
    c2pa_revocation_status = Column(String(50), nullable=True)
    c2pa_ai_agents_found = Column(JSON, nullable=True)
    c2pa_has_training_mining = Column(Boolean, nullable=True)


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
    stripe_event_id = Column(String(255), unique=True, nullable=True)
    stripe_customer_email = Column(String(255), nullable=True)
    stripe_amount_total = Column(Integer, nullable=True)
    stripe_currency = Column(String(10), nullable=True)
    product = Column(String(50), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Added for file-specific Integrity Certificate entitlement (migration a3f1d9c2b8e4).
    # Columns already exist on the table; declared here so the ORM knows about them.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    case_id = Column(String(50), nullable=True, index=True)
    evidence_id = Column(String(50), nullable=True, index=True)


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


class FreeScreenLog(Base):
    """Per-account ledger of free-screen (/screen) checks, used to enforce the
    monthly quota (FREE_SCREEN_MONTHLY_QUOTA). The free screen is ephemeral and
    images-only: it persists NO file, filename, or media — only the minimal
    audit fields below. c2pa_state is sized to match evidence_items.c2pa_state
    (64) so it can hold SIGNED_UNRECOGNIZED_ISSUER; sha256 is the 64-char hex
    digest computed at screen time.
    """
    __tablename__ = "free_screen_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    c2pa_state = Column(String(64), nullable=True)
    sha256 = Column(String(64), nullable=True)