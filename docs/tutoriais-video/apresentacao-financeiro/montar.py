"""Monta os quadros finais: cada cena no seu horário; na virada, a cena que sai desliza para a esquerda e a que entra
vem da direita em 1 batida (0,5 s, easeInOutCubic), como quem passa o dedo no carrossel.

    python montar.py roteiro.json quadros/ final/
"""
import json, os, sys
from PIL import Image

R = json.load(open(sys.argv[1], encoding="utf-8"))
QD, OUT = sys.argv[2], sys.argv[3]
os.makedirs(OUT, exist_ok=True)
FPS, TR = R["fps"], R["transicao"]
NTR = int(TR * FPS)
W = 1080


def io(t):
    return 4 * t ** 3 if t < .5 else 1 - (-2 * t + 2) ** 3 / 2


def quadro(c, i):
    return Image.open(os.path.join(QD, f"c{c['id']}", f"q{i:04d}.png")).convert("RGB")


cenas = R["cenas"]
total = int(R["total"] * FPS)
for f in range(total):
    t = f / FPS
    k = max(i for i, c in enumerate(cenas) if c["inicio"] <= t + 1e-9)
    c = cenas[k]
    li = f - int(c["inicio"] * FPS)
    if k > 0 and li < NTR:
        ant = cenas[k - 1]
        e = io(li / NTR)
        dx = int(round(e * W))
        img = Image.new("RGB", (W, 1920))
        img.paste(quadro(ant, int(ant["dur"] * FPS) + li), (-dx, 0))
        img.paste(quadro(c, li), (W - dx, 0))
    else:
        img = quadro(c, li)
    img.save(os.path.join(OUT, f"f{f:05d}.png"), compress_level=1)
print("quadros finais", total)
