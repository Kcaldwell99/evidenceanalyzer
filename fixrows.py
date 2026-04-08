path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
lines[129]=""
lines[131]='                (e.detail or "")[:80],\n'
lines[134]='        if len(custody_data) == 1:\n'
lines[135]='            custody_data.append(["No custody events recorded.", "", "", ""])\n'
open(path,"w",encoding="utf-8").write("".join(lines))
print("Done.")
