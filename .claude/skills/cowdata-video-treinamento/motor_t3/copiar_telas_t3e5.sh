#!/bin/bash
# Copia as capturas reais (captura/shots_ep) para a cena: placas do Menu → cena/tex (+ mapa.json, que dá as posições das placas), telas do episódio → cena/tex2 (+ mapa.json e beats_t3e5.json).
set -e; cd "$(dirname "$0")"; mkdir -p cena/tex cena/tex2
S=captura/shots_ep
cp $S/placa_*.png $S/menu_alim.png cena/tex/; cp $S/mapa.json cena/tex/mapa.json
for f in $S/*.png; do case "$(basename $f)" in placa_*) ;; *) cp "$f" cena/tex2/ ;; esac; done
cp $S/mapa.json cena/tex2/mapa.json; cp beats_t3e5.json cena/tex2/beats.json
echo ok
