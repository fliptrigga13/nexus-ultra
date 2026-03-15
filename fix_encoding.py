import sys, re

path = r"C:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_hub.html"
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    content = f.read()

# Map of garbled Windows-1252-read-as-Latin1 sequences to correct UTF-8
# These appear when a file saved as UTF-8 is later read/saved incorrectly
FIXES = {
    # Box drawing / separators
    '\u0393\u00f2\u00c9': '═',   # ═
    '\u0393\u00fb\u00c2': '──',  # ──
    '\u0393\u00fb\u00b5': '─',
    # Symbols
    '\u0393\u00dc\u00ad': '⚡',
    '\u0393\u00a5\u00ce': '❌',
    '\u0393\u00a4\u00fc': '✅',
    '\u0393\u00d6\u00be': '↕',
    '\u0393\u00d6\u00b8': '⇒',
    '\u0393\u009c\u00a4': '📬',
    '\u0393\u009c\u00a7': '🧠',
    '\u0393\u009c\u00a5': '🤖',
    # Arrow
    '\u0393\u00fb\u00a1': '◈',
    '&#9608;': '█',
    # Common replacements
    '\u00e2\u20ac\u201c': '—',   # em dash
    '\u00e2\u20ac\u201d': '"',
    '\u00e2\u20ac\u009c': '"',
    '\u00e2\u20ac\u2122': "'",
    '\u00e2\u20ac\u00a6': '…',
    # Degree / special
    '\ufffd': '',   # replacement char - remove
}

original = content
for bad, good in FIXES.items():
    content = content.replace(bad, good)

# Also fix specific patterns seen in the file
# ΓòÉΓòÉΓòÉ... (garbled repeated box chars in JS comments)
content = re.sub(r'[\u0393][\u00f2\u00f2][\u00c9]{1,}', '═══════════════════════════════════════════', content)
content = re.sub(r'[\u0393][\u00fb][\u00c2]{1,}', '──────────────────────────────────────────', content)

# Count fixes
changed = sum(1 for a,b in zip(original, content) if a != b)
print(f"Fixed {changed} chars")

# Now find which lines still have non-ASCII non-emoji chars (potential garble)
lines = content.split('\n')
suspicious = []
for i, line in enumerate(lines):
    for c in line:
        code = ord(c)
        # Flag Latin Extended chars that aren't emojis or proper unicode symbols
        if 0x00C0 <= code <= 0x02FF:  # Latin Extended
            suspicious.append((i+1, repr(line[:100])))
            break
        if 0x0393 <= code <= 0x03FF:  # Greek range (often garbled)
            suspicious.append((i+1, repr(line[:100])))
            break

print(f"Remaining suspicious lines: {len(suspicious)}")
for ln, txt in suspicious[:10]:
    print(f"  L{ln}: {txt}")

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Saved.")
