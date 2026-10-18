"""Monta o HTML de um episódio da Temporada 2.   python3 build_t2.py t2e1 <pasta_de_saida> <pasta_com_shots_e_mapa.json>
A saída recebe um link `assets` (fontes, papel kraft, lucide) e `shots` (capturas reais do app)."""
import sys, os
ep, out, cap = sys.argv[1], sys.argv[2], sys.argv[3]
aqui = os.path.dirname(os.path.abspath(__file__))
rd = lambda p: open(os.path.join(aqui, p), encoding='utf-8').read()
s = rd('t2.src.html').replace('__LUCIDE__', rd('assets/lucide.json')).replace('__TL__', rd(f'audio/tl_{ep}.json'))
s = s.replace('__MAPA__', open(os.path.join(cap, 'mapa.json'), encoding='utf-8').read()).replace('__EP__', rd(f'episodios/{ep}.js'))
os.makedirs(out, exist_ok=True)
open(os.path.join(out, f'{ep}.html'), 'w', encoding='utf-8').write(s)
for nome, alvo in (('assets', os.path.join(aqui, 'assets')), ('shots', os.path.abspath(os.path.join(cap, 'shots')))):
    ln = os.path.join(out, nome)
    if os.path.lexists(ln): os.remove(ln)
    os.symlink(alvo, ln)
print('ok', ep)
