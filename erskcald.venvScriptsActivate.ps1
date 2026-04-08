[1mdiff --git a/app/models.py b/app/models.py[m
[1mindex 8bdec44..5698768 100644[m
[1m--- a/app/models.py[m
[1m+++ b/app/models.py[m
[36m@@ -44,3 +44,15 @@[m [mclass EvidenceItem(Base):[m
     json_report = Column(Text, nullable=True)[m
     pdf_report = Column(Text, nullable=True)[m
     file_key = Column(String(500), nullable=True)[m
[32m+[m
[32m+[m[32mclass FingerprintIndex(Base):[m
[32m+[m[32m    __tablename__ = "fingerprint_index"[m
[32m+[m
[32m+[m[32m    id = Column(Integer, primary_key=True, index=True)[m
[32m+[m[32m    case_id = Column(String(50), nullable=True, index=True)[m
[32m+[m[32m    evidence_id = Column(String(50), nullable=True)[m
[32m+[m[32m    file_name = Column(String(255), nullable=True)[m
[32m+[m[32m    phash = Column(String(128), nullable=True)[m
[32m+[m[32m    pdf_report = Column(Text, nullable=True)[m
[32m+[m[32m    json_report = Column(Text, nullable=True)[m
[32m+[m[32m    created_at = Column(DateTime(timezone=True), server_default=func.now())[m
