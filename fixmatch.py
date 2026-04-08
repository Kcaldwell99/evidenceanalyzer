path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace("colWidths=[1.5*inch, 2.2*inch, 2.8*inch]","colWidths=[1.4*inch, 2.0*inch, 2.95*inch]")
open(path,"w",encoding="utf-8").write(text)
print("Done.")
