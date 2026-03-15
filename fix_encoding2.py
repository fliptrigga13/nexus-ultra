"""
Fix: the file has UTF-8 content that was read as CP1252 and re-saved.
Strategy: read each character as its latin-1 byte value, reassemble bytes, decode as UTF-8.
Do this only on the garbled sections (non-ASCII latin-extended chars).
"""
import re

path = r"C:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_hub.html"

with open(path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Direct string replacement map for patterns seen in the file
# These are UTF-8 multi-byte sequences mis-read as Windows-1252
REMAP = {
    # em dash (U+2014) — appears as ΓÇö in CP1252 mis-read
    '\u0393\u00c7\u00f6': '\u2014',  # —
    # horizontal box ─ (U+2500)
    '\u0393\u00f6\u00c7': '\u2500',  # ─
    # middle dot · (U+00B7) — appears as ┬╖
    '\u252c\u2566': '\u00b7',         # ·
    # ◈ (U+25C8) — appears as Γùê
    '\u0393\u00f9\u00ea': '\u25c8',  # ◈
    # → (U+2192) — appears as ΓåÆ  
    '\u0393\u00e5\u00c6': '\u2192',  # →
    # ╔ (U+2554)
    '\u0393\u00f2\u0094': '\u2554',  # ╔
    # ═ (U+2550)
    '\u0393\u00f2\u0090': '\u2550',  # ═
    # ╗ (U+2557)
    '\u0393\u00f2\u0097': '\u2557',  # ╗
    # ║ (U+2551)
    '\u0393\u00f2\u0091': '\u2551',  # ║
    # ╚ (U+255A)
    '\u0393\u00f2\u009a': '\u255a',  # ╚
    # ╝ (U+255D)
    '\u0393\u00f2\u009d': '\u255d',  # ╝
    # left " (U+201C)
    '\u0393\u00c7\u00a3': '\u201c',  # "
    # right " (U+201D)
    '\u0393\u00c7\u00a5': '\u201d',  # "
    # ' right quote (U+2019)
    '\u0393\u00c7\u00b4': '\u2019',  # '
    # ellipsis … (U+2026)
    '\u0393\u00c7\u00a6': '\u2026',  # …
    # bullet • (U+2022)
    '\u00e2\u20ac\u00a2': '\u2022',  # •
    # non-breaking space
    '\u00c2\u00a0': '\u00a0',
}

for bad, good in REMAP.items():
    content = content.replace(bad, good)

# Also try the "re-bytes decode" trick on remaining garbled sections
# Pattern: sequences of Γ (U+0393) followed by latin extended chars
# These are 3-byte UTF-8 seqs read as CP1252
def fix_triple(m):
    try:
        s = m.group(0)
        b = bytes(ord(c) & 0xFF for c in s)
        return b.decode('utf-8')
    except:
        return m.group(0)

# Match sequences that look like mis-encoded UTF-8 (3-byte seqs starting with 0xE2-0xEF)
content = re.sub(r'[\u00e2-\u00ef][\u0080-\u00bf][\u0080-\u00bf]', fix_triple, content)
# 2-byte seqs
def fix_double(m):
    try:
        s = m.group(0)
        b = bytes(ord(c) & 0xFF for c in s)
        return b.decode('utf-8')
    except:
        return m.group(0)
content = re.sub(r'[\u00c2-\u00df][\u0080-\u00bf]', fix_double, content)

# Remove stray replacement chars
content = content.replace('\ufffd', '')

# Count remaining suspicious
lines = content.split('\n')
sus = sum(1 for l in lines if any(0x00C0 <= ord(c) <= 0x02FF or 0x0393 <= ord(c) <= 0x03FF for c in l))
print(f"Remaining suspicious lines after deep fix: {sus}")

# Show samples
for i, line in enumerate(lines):
    for c in line:
        code = ord(c)
        if (0x00C0 <= code <= 0x02FF) or (0x0391 <= code <= 0x03FF):
            print(f"  L{i+1}: {repr(line[:80])}")
            break
    if i > 400: break

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Saved.")
