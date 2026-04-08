path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
idx=text.find('custody_data.append')
chunk=text[idx:idx+200]
print(repr(chunk))
