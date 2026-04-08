import re
path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace('                e.evidence_id or "",\n                (e.detail or "")[:60],','                (e.detail or "")[:80],')
text=text.replace('custody_data.append(["No custody events recorded.", "", "", "", ""])','custody_data.append(["No custody events recorded.", "", "", ""])')
open(path,"w",encoding="utf-8").write(text)
print("Done.")
