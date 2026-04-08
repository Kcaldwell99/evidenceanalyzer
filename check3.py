path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
for i,l in enumerate(lines[168:180],start=169):
    print(f"{i}: {repr(l)}")
