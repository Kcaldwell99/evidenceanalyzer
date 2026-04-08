path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
cut=next(i for i,l in enumerate(lines) if "doc.build" in l)
lines[cut-1]="        ))\n"
lines=lines[:cut]
lines.append("        doc.build(story)\n")
lines.append("        return output_path\n")
open(path,"w",encoding="utf-8").write("".join(lines))
print("Done.")
