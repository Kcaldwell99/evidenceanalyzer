path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace("colWidths=[1.3*inch, 2.5*inch, 3.2*inch]","colWidths=[1.2*inch, 2.3*inch, 3.0*inch]")
open(path,"w",encoding="utf-8").write(text)
print("Done.")
