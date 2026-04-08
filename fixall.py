path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace("Caldwell Law Firm, P.C.","CLF The Woodlands, LLC. dba Evidence Analyzer")
text=text.replace("(e.detail or \"\")[:40]","(e.detail or \"\")[:60]")
text=text.replace("        doc.build(story)","        story.append(Paragraph(\"Copyright 2026 Evidence Analyzer, LLC. All rights reserved.\", disclaimer_style))\n        doc.build(story)")
open(path,"w",encoding="utf-8").write(text)
print("Done.")
