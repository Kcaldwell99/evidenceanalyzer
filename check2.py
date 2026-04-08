path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
for i,l in enumerate(lines[171:180],start=172):
    print(f"{i}: {repr(l)}")
