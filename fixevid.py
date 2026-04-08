path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
old='ts,\n                e.user_email or "system",\n                e.action or "",\n                e.evidence_id or "",\n                (e.detail or "")[:60],'
new='ts,\n                e.user_email or "system",\n                e.action or "",\n                (e.detail or "")[:80],'
if old in text:
    text=text.replace(old,new)
    open(path,"w",encoding="utf-8").write(text)
    print("Done.")
else:
    print("NOT FOUND - checking tabs")
    print(repr(text[text.find('ts,'):text.find('ts,')+200]))
