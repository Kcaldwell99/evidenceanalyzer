path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace('(e.detail or "")[:60]','(e.detail or "")[:80]')
open(path,"w",encoding="utf-8").write(text)
print("Done.")
