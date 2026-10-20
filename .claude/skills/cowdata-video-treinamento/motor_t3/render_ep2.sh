#!/bin/bash
# Render completo do Ep. 2 em 4 faixas paralelas (cada faixa: abertura index_t3e2.html até 5,6 s + episodio_t3e2.html depois). Uso: render_ep2.sh <pasta_saida>
OUT=${1:-q}; cd "$(dirname "$0")"
export FMT=jpg DEDUP=1
TOTAL=${TOTAL:-2214}
W() { # $1 porta  $2 frame0  $3 frame1
  local a=$2 b=$3 j=168
  if [ $a -lt $j ]; then PAGE=index_t3e2.html PORT=$1 node render3d.mjs "$OUT" $(python3 -c "print($a/30)") $(python3 -c "print(min($b,$j)/30)") ; a=$j; fi
  if [ $a -lt $b ]; then PAGE=episodio_t3e2.html PORT=$1 node render3d.mjs "$OUT" $(python3 -c "print($a/30)") $(python3 -c "print($b/30)"); fi
}
Q=$((TOTAL/4))
W 8161 0 $Q > r0.log 2>&1 &
W 8162 $Q $((2*Q)) > r1.log 2>&1 &
W 8163 $((2*Q)) $((3*Q)) > r2.log 2>&1 &
W 8164 $((3*Q)) $TOTAL > r3.log 2>&1 &
wait
