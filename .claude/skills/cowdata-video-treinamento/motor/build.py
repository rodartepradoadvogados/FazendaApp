import sys
ep=sys.argv[1]
s=open('ep.src.html',encoding='utf-8').read()
s=s.replace('__LUCIDE__',open('assets/lucide.json').read()).replace('__TL__',open(f'audio/tl_{ep}.json',encoding='utf-8').read()).replace('__EP__',open(f'episodios/{ep}.js',encoding='utf-8').read())
open(f'{ep}.html','w',encoding='utf-8').write(s);print('ok',ep)
