path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace('custody_data = [["Timestamp (UTC)", "User / Role", "Action", "Evidence ID", "Detail"]]','custody_data = [["Timestamp (UTC)", "User / Role", "Action", "Detail"]]')
text=text.replace("ts,\n                e.user_email or \"system\",\n                e.action or \"\",\n                e.evidence_id or \"\",\n                (e.detail or \"\")[:60],","ts,\n                e.user_email or \"system\",\n                e.action or \"\",\n                (e.detail or \"\")[:80],")
text=text.replace("1.0*inch, 1.2*inch, 1.3*inch, 0.8*inch, 2.1*inch","1.1*inch, 1.9*inch, 1.5*inch, 2.9*inch")
open(path,"w",encoding="utf-8").write(text)
print("Done.")
