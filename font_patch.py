import re
import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

old_link_regex = r'<link href="https://fonts\.googleapis\.com[^>]*>'

new_link = '<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Space+Grotesk:wght@300;400;500;700&family=Fira+Code:wght@300;400;500&display=swap" rel="stylesheet">'

if '<link href="https://fonts.googleapis.com/css2?family=Outfit:' not in src:
    src = re.sub(old_link_regex, new_link, src)
    with open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', 'w', encoding='utf-8') as f:
        f.write(src)
    shutil.copy(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
    print("Fonts patched successfully!")
else:
    print("Fonts already patched.")
