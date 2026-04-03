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
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    cases = relationship("Case", back_populates="owner")


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(50), unique=True, nullable=False, index=True)
    case_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # --- NEW: owner foreign key ---
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
