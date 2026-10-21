#!/usr/bin/env python3
# Monta cena/episodio.html = cabeçalho + base 3D do explicativo.html (celular, luzes, mesa) + roteiro + corpo.
import sys, os
d = os.path.dirname(os.path.abspath(__file__))
ex = open(os.path.join(d, "explicativo.html")).read()
a = ex.index("import * as THREE"); b = ex.index("// ---------- tela (composição por tempo)")
pre = ex[a:b].replace("const nomes = [];\n", "")
pre = pre.replace('const IMG = { agenda: await imgCarrega("tex2/agenda.png"), gaveta: await imgCarrega("tex2/gaveta.png") };\nconst MAPA = await (await fetch("tex2/mapa.json")).json();',
 'const M = await (await fetch("tex2/mapa.json")).json();\nconst B = await (await fetch("tex2/beats.json")).json();\nconst NOMES = ["menu_repro","ag0_vp","ag0","ag1","f1","f2","f3","ag2","ag3","ag5","ag7","ag8","ficha_vp","pk0","pk1","d0","dn1","dn2","dn3","dn4","dn5","dcat","dlote","dsit","dins","dde","date","dchip","dedit"];\nconst IM = {}; await Promise.all(NOMES.map(async (n) => { IM[n] = await imgCarrega(`tex2/${n}.png`); }));')
pre = pre.replace("scTex.generateMipmaps = false; scTex.minFilter = THREE.LinearFilter;", "scTex.generateMipmaps = true; scTex.minFilter = THREE.LinearMipmapLinearFilter;")
pre = pre.replace("const root = new THREE.Group(); root.add(laid); scene.add(root);", "const flip = new THREE.Group(); flip.add(laid);\nconst root = new THREE.Group(); root.add(flip); scene.add(root);")
head = ex[:ex.index('<div id="palco">')]
head = head.replace("top:62px", "top:46px").replace("font:800 34px/1 Archivo;letter-spacing:.04em", "font:800 27px/1 Archivo;letter-spacing:.04em").replace("padding:14px 28px 15px 24px", "padding:11px 22px 12px 18px;opacity:0").replace("width:14px;height:14px;border-radius:50%;background:#E0A63C;margin-right:14px", "width:11px;height:11px;border-radius:50%;background:#E0A63C;margin-right:11px")
body_html = '<div id="palco"><div id="vig"></div><div id="grao"></div><canvas id="nav" width="1080" height="1920"></canvas><div id="etq"><i></i><span id="etqt">Menu</span></div><div id="leg"><span></span></div></div>\n<script type="importmap">{"imports":{"three":"./three.module.js"}}</script>\n<script type="module">\n'
out = head + body_html + pre + open(os.path.join(d, "episodio_roteiro.js")).read() + open(os.path.join(d, "episodio_corpo.js")).read() + "</script></body></html>\n"
open(os.path.join(d, "episodio.html"), "w").write(out); print("episodio.html", len(out))
