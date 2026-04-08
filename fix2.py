path="app/integrity_report.py"
lines=open(path,encoding="utf-8").readlines()
for i,l in enumerate(lines):
    if 'now.year' in l or 'Evidence Analyzer All rights' in l or 'Evidentix\u2122' in l or 'ibited' in l:
        print(f"Found bad line {i+1}: {repr(l)}")
