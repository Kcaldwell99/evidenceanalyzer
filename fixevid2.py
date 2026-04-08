path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
old='ts,\n\t\t\t\te.user_email or "system",\n\t\t\t\te.action or "",\n\t\t\t\te.evidence_id or "",\n\t\t\t\t(e.detail or "")[:60],'
new='ts,\n\t\t\t\te.user_email or "system",\n\t\t\t\te.action or "",\n\t\t\t\t(e.detail or "")[:80],'
if old in text:
    text=text.replace(old,new)
    open(path,"w",encoding="utf-8").write(text)
    print("Done.")
else:
    print("NOT FOUND")
    print(repr(text[text.find('e.evidence_id'):text.find('e.evidence_id')+50]))
