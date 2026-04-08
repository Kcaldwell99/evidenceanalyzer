path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace("colWidths=[1.1*inch, 1.9*inch, 1.5*inch, 2.9*inch]","colWidths=[1.1*inch, 1.7*inch, 1.4*inch, 2.8*inch]")
open(path,"w",encoding="utf-8").write(text)
print("Done.")
