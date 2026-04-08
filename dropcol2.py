path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace('(e.detail or "")[:80],\n','')
text=text.replace('custody_data = [["Timestamp (UTC)", "User / Role", "Action", "Detail"]]','custody_data = [["Timestamp (UTC)", "User / Role", "Action"]]')
text=text.replace('custody_data.append(["No custody events recorded.", "", "", ""])','custody_data.append(["No custody events recorded.", "", ""])')
open(path,"w",encoding="utf-8").write(text)
print("Done.")
