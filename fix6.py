path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
lines[172]='        ))\n'
open(path,"w",encoding="utf-8").write("".join(lines))
print("Done.")
