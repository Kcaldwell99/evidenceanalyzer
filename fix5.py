path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
lines[173]='        story.append(Paragraph(\n'
lines[174]='            "Copyright 2026 Evidence Analyzer, LLC. All rights reserved.",\n'
lines[175]='            disclaimer_style\n'
lines[176]='        ))\n'
lines[177]='        doc.build(story)\n'
lines[178]='        return output_path\n'
open(path,"w",encoding="utf-8").write("".join(lines[:179]))
print("Done.")
