#!/bin/bash
# Render completo do Ep. 1 em 4 faixas paralelas (cada faixa: abertura index.html até 5,6 s + episodio.html depois). Uso: render_ep1.sh <pasta_saida>
OUT=${1:-q}; cd "$(dirname "$0")"
export FMT=jpg DEDUP=1
W() { # $1 porta  $2 frame0  $3 frame1
  local a=$2 b=$3 j=168
  if [ $a -lt $j ]; then PAGE=index.html PORT=$1 node render3d.mjs "$OUT" $(python3 -c "print($a/30)") $(python3 -c "print(min($b,$j)/30)") ; a=$j; fi
  if [ $a -lt $b ]; then PAGE=episodio.html PORT=$1 node render3d.mjs "$OUT" $(python3 -c "print($a/30)") $(python3 -c "print($b/30)"); fi
}
W 8151 0 740 > r0.log 2>&1 &
W 8152 740 1480 > r1.log 2>&1 &
W 8153 1480 2220 > r2.log 2>&1 &
W 8154 2220 2958 > r3.log 2>&1 &
wait
