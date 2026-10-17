#!/bin/bash
# uso: audio/norm.sh entrada.wav saida.wav  -> -14 LUFS integrado, pico real <= -1 dBTP, mono 48 kHz
set -e
in=$1; out=$2; tmp="${out%.wav}_comp.wav"
ffmpeg -loglevel error -y -i "$in" -af "acompressor=threshold=0.1:ratio=2.5:attack=6:release=120:makeup=1" -ac 1 "$tmp"
I=$(ffmpeg -hide_banner -i "$tmp" -af ebur128 -f null - 2>&1 | grep -E "^\s+I:" | tail -1 | awk '{print $2}')
G=$(python3 -c "print(-14-($I)+0.4)")
ffmpeg -loglevel error -y -i "$tmp" -af "volume=${G}dB,alimiter=limit=0.7:attack=1:release=50:level=false" -ar 48000 -ac 1 "$out"
rm -f "$tmp"
ffmpeg -hide_banner -i "$out" -af ebur128=peak=true -f null - 2>&1 | grep -E "^\s+(I:|Peak:)" | tail -2
