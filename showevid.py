path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
idx=text.find('e.evidence_id or "",\n')
print(repr(text[idx-100:idx+100]))
