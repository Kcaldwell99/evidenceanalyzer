import os
from sqlalchemy import create_engine, text

DATABASE_URL = os.environ["DATABASE_URL"]
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    conn.execute(text("DROP TABLE IF EXISTS evidence_items CASCADE;"))
    conn.execute(text("DROP TABLE IF EXISTS cases CASCADE;"))
    conn.commit()
    print("Tables dropped successfully.")