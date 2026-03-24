from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.sql import func

from app.db import Base


class Case(Base):
    __tablename__ = "cases"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(String(50), unique=True, nullable=False, index=True)
    case_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


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