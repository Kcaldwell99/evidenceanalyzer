"""Diagnostic — inspect the actual bytes of app/utils/image_fingerprint.py."""

from pathlib import Path

TARGET = Path("app/utils/image_fingerprint.py")

raw = TARGET.read_bytes()
print(f"File: {TARGET}")
print(f"Size: {len(raw)} bytes")
print()

# BOM check
if raw.startswith(b"\xef\xbb\xbf"):
    print("UTF-8 BOM: PRESENT (3 bytes)")
elif raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
    print("UTF-16 BOM: PRESENT")
else:
    print("BOM: none")
print()

# First and last bytes
print("First 20 bytes (hex):")
print(" ".join(f"{b:02X}" for b in raw[:20]))
print("First 20 bytes (repr):")
print(repr(raw[:20]))
print()

print("Last 20 bytes (hex):")
print(" ".join(f"{b:02X}" for b in raw[-20:]))
print("Last 20 bytes (repr):")
print(repr(raw[-20:]))
print()

# Line ending analysis
crlf = raw.count(b"\r\n")
total_lf = raw.count(b"\n")
lone_lf = total_lf - crlf
lone_cr = raw.count(b"\r") - crlf
print(f"CRLF count: {crlf}")
print(f"Lone LF count: {lone_lf}")
print(f"Lone CR count: {lone_cr}")
print()

# Non-ASCII check
non_ascii = [(i, b) for i, b in enumerate(raw) if b > 127]
if non_ascii:
    print(f"Non-ASCII bytes: {len(non_ascii)} found")
    for i, b in non_ascii[:10]:
        print(f"  offset {i}: 0x{b:02X}")
else:
    print("Non-ASCII bytes: none")
print()

# Decode and count lines
text = raw.decode("utf-8")
lines = text.split("\n")
print(f"Line count (split on \\n): {len(lines)}")
print()

# Show each line with its length and trailing-whitespace count
print("Per-line stats:")
for i, line in enumerate(lines):
    stripped = line.rstrip()
    trailing = len(line) - len(stripped)
    marker = f" [+{trailing} trailing]" if trailing else ""
    if line == "" and i == len(lines) - 1:
        print(f"  {i:2d}: <final empty line>{marker}")
    else:
        print(f"  {i:2d}: ({len(line)} chars){marker} {repr(line[:60])}")
