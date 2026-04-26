import c2pa
import json

reader = c2pa.Reader.from_file(r"C:\Users\kcald\Pictures\test.jpg")
raw = reader.json()
data = json.loads(raw)
print(json.dumps(data, indent=2))