path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
lines[125]='            custody_data.append([\n'
lines[126]='                ts,\n'
lines[127]='                e.user_email or "system",\n'
lines[128]='                e.action or "",\n'
lines[129]='                (e.detail or "")[:80],\n'
lines[130]='            ])\n'
lines[131]='\n'
lines[132]='        if len(custody_data) == 1:\n'
lines[133]='            custody_data.append(["No custody events recorded.", "", "", ""])\n'
lines[134]='\n'
open(path,"w",encoding="utf-8").write("".join(lines))
print("Done.")
