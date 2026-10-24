#!/bin/bash
# (repete se o SwiftShader estourar o timeout: o render3d retoma de onde parou)
# Render completo do Ep. 7 em 4 faixas paralelas (cada faixa: abertura index_t3e7.html até 5,6 s + episodio_t3e7.html depois). Uso: render_ep7.sh <pasta_saida>
OUT=${1:-q}; cd "$(dirname "$0")"
export FMT=jpg DEDUP=1
TOTAL=${TOTAL:-2448}
W() { # $1 porta  $2 frame0  $3 frame1
  local a=$2 b=$3 j=168
  if [ $a -lt $j ]; then until PAGE=index_t3e7.html PORT=$1 node render3d.mjs "$OUT" $(python3 -c "print($a/30)") $(python3 -c "print(min($b,$j)/30)"); do sleep 2; done; a=$j; fi
  if [ $a -lt $b ]; then until PAGE=episodio_t3e7.html PORT=$1 node render3d.mjs "$OUT" $(python3 -c "print($a/30)") $(python3 -c "print($b/30)"); do sleep 2; done; fi
}
Q=$((TOTAL/4))
W 8371 0 $Q > r0.log 2>&1 &
W 8372 $Q $((2*Q)) > r1.log 2>&1 &
W 8373 $((2*Q)) $((3*Q)) > r2.log 2>&1 &
W 8374 $((3*Q)) $TOTAL > r3.log 2>&1 &
wait
