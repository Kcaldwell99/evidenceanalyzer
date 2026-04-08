from sqlalchemy import create_engine, text

db = "postgresql://evidenceanalyzer_db_user:ZLWz5FrdXAUd9WOCuFi4EDSzMCizhu9U@dpg-d7021t0gjchc73cv6ej0-a.oregon-postgres.render.com/evidenceanalyzer_db"
engine = create_engine(db)

with engine.connect() as conn:
    r1 = conn.execute(text("DELETE FROM custody_log WHERE case_id = 'CASE-0001'"))
    r2 = conn.execute(text("DELETE FROM custody_log WHERE case_id = 'CASE-0002'"))
    conn.commit()
    print(f"Deleted {r1.rowcount} from CASE-0001, {r2.rowcount} from CASE-0002.")