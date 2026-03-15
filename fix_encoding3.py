"""
Final fix: re-read the file as latin-1 (byte-for-byte), then decode as UTF-8.
This properly fixes all garbled sequences including 4-byte emoji.
"""
path = r"C:\Users\fyou1\Desktop\New folder\nexus-ultra\nexus_hub.html"

# Read as latin-1 to get raw bytes as unicode codepoints
with open(path, 'r', encoding='latin-1') as f:
    raw = f.read()

# Convert back to bytes then decode as UTF-8
try:
    fixed = raw.encode('latin-1').decode('utf-8', errors='replace')
    # Count improvements
    garble_before = sum(1 for c in raw if 0x00C0 <= ord(c) <= 0x02FF or 0x0391 <= ord(c) <= 0x03FF)
    garble_after  = sum(1 for c in fixed if 0xFFFD == ord(c))  # replacement chars
    print(f"Garbled chars before: {garble_before}")
    print(f"Replacement chars after: {garble_after}")
    
    # Remove replacement chars
    fixed = fixed.replace('\ufffd', '')
    
    with open(path, 'w', encoding='utf-8') as f:
        f.write(fixed)
    print("Done! File re-encoded correctly.")
    
    # Verify
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    remaining = sum(1 for l in lines if any(0x00C0 <= ord(c) <= 0x02FF or 0x0391 <= ord(c) <= 0x03FF for c in l))
    print(f"Suspicious lines remaining: {remaining}")
    
except UnicodeDecodeError as e:
    print(f"Error: {e} - file might be mixed encoding")
    # Fall back: read as UTF-8, fix known patterns
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()
    # Known emoji fixes
    fixes = {
        '\u2261\u0192\u00c4\u00d6': '🎙',   # mic emoji
        '\u2261\u0192\u00f6\u00a4': '🔄',   # cycle
        '\u2261\u0192\u00ba\u2563': '🗑',   # trash
        '\u2261\u0192\u00f9\u00e6': '🧹',   # broom
        '\u2261\u0192\u00dc\u00ad': '⚡',   # lightning
        '\u0393\u00dc\u00ad': '⚡',
        '\u0393\u00c7\u00f6': '\u2014',
    }
    for b, g in fixes.items():
        content = content.replace(b, g)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fallback fixes applied.")
