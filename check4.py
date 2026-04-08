path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
l=lines[173]
print(f"len={len(l)}, starts with: {repr(l[:12])}")
