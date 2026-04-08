path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace('custody_data = [["Timestamp (UTC)", "User / Role", "Action", "Detail"]]','custody_data = [["Timestamp (UTC)", "User / Role", "Action"]]')
text=text.replace('ts,\n\t\t\t\te.user_email or "system",\n\t\t\t\te.action or "",\n\t\t\t\t(e.detail or "")[:80],','ts,\n\t\t\t\te.user_email or "system",\n\t\t\t\te.action or "",')
text=text.replace('custody_data.append(["No custody events recorded.", "", "", ""])','custody_data.append(["No custody events recorded.", "", ""])')
text=text.replace("colWidths=[1.1*inch, 1.9*inch, 1.5*inch, 2.9*inch]","colWidths=[1.3*inch, 2.5*inch, 3.2*inch]")
text=text.replace("colWidths=[1.1*inch, 1.7*inch, 1.4*inch, 2.8*inch]","colWidths=[1.3*inch, 2.5*inch, 3.2*inch]")
open(path,"w",encoding="utf-8").write(text)
print("Done.")
