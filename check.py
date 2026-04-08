path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
for i,l in enumerate(lines[172:182],start=173):
    print(f"{i}: {repr(l)}")
