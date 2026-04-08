path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
lines[174]="        story.append(Paragraph(\"Copyright 2026 Evidence Analyzer, LLC. All rights reserved. Evidentix is an Evidence Analyzer trademark. Unauthorized reproduction or distribution of this report is prohibited.\", disclaimer_style))\n"
del lines[175]
del lines[175]
open(path,"w",encoding="utf-8").write("".join(lines))
print("Done.")
