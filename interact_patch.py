import shutil

src = open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', encoding='utf-8').read()

# Make mouse interaction super strong and extremely visible
target = 'var dx=mx-nd.x,dy=my-nd.y,d2=dx*dx+dy*dy,R2=170*170;\n      if(d2<R2&&d2>1){var s=.006*(1-Math.sqrt(d2)/170);nd.vx+=dx*s;nd.vy+=dy*s;}'

replacement = 'var dx=mx-nd.x,dy=my-nd.y,d2=dx*dx+dy*dy,R2=350*350;\n      if(d2<R2&&d2>1){var s=.05*(1-Math.sqrt(d2)/350);nd.vx+=dx*s;nd.vy+=dy*s;}'

if target in src:
    src = src.replace(target, replacement)
    # also remove grid noise completely
    src = src.replace('opacity: 0.3', 'opacity: 0.0')

    with open(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', 'w', encoding='utf-8') as f:
        f.write(src)
    shutil.copy(r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\vp.html', r'c:\Users\fyou1\Desktop\New folder\nexus-ultra\public\vp.html')
    print("Mouse interaction and grid simplification patched successfully!")
else:
    print('Failed to find exact target string!')
