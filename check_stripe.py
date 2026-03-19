import re
s = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

links = re.findall(r'<a[^>]*href=\"(https://buy\.stripe\.com[^\"]*)\"[^>]*>(.*?)</a>', s, re.DOTALL)
print('Stripe links found:', len(links))
for link, text in links:
    print('URL:', link)
    print('TEXT:', text.strip()[:100])
