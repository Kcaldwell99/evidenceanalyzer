path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
text=text.replace("1.2*inch, 1.5*inch, 1.5*inch, 0.9*inch, 1.3*inch","1.0*inch, 1.2*inch, 1.3*inch, 0.8*inch, 2.1*inch")
open(path,"w",encoding="utf-8").write(text)
print("Done.")
