#!/bin/bash
# Prepara os insumos NÃO versionados da cena 3D: three.module.js 0.160.0 (CDN), fontes/marca/grão/kraft do motor da T2.
set -e; cd "$(dirname "$0")"
mkdir -p cena/assets
curl -sSfL https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js -o cena/three.module.js
( cd ../motor && [ -f assets/kraft.png ] || node snap_t2.mjs )
cp -r ../motor/assets/fonts cena/assets/; cp ../motor/assets/cowdata-mark.svg ../motor/assets/grao.png ../motor/assets/kraft.png cena/assets/
echo ok
