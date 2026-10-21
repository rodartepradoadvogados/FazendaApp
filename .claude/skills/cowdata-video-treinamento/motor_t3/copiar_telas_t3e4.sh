#!/bin/bash
# Copia as capturas reais (captura/shots_ep) para a cena: placas do Menu → cena/tex, telas do episódio → cena/tex2 (+ mapa.json e beats_t3e4.json).
set -e; cd "$(dirname "$0")"; mkdir -p cena/tex cena/tex2
S=captura/shots_ep
cp $S/placa_*.png $S/menu_repro.png cena/tex/
for f in $S/*.png; do case "$(basename $f)" in placa_*) ;; *) cp "$f" cena/tex2/ ;; esac; done
cp $S/mapa.json cena/tex2/mapa.json; cp beats_t3e4.json cena/tex2/beats.json
echo ok
