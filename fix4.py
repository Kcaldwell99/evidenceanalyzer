path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
lines[174]='        story.append(Paragraph(\n'
lines[175]='            "Copyright 2026 Evidence Analyzer, LLC. All rights reserved.",\n'
lines[176]='            disclaimer_style\n'
open(path,"w",encoding="utf-8").write("".join(lines))
print("Done.")
