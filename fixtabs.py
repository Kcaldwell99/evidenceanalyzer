path="app/integrity_report.py"
text=open(path,encoding="utf-8").read()
import re
text=text.expandtabs(4)
open(path,"w",encoding="utf-8").write(text)
print("Done.")
