#!/usr/bin/env bash
# Reproduz o vídeo de apresentação do Financeiro (reel 9:16, 56 s) a partir do ambiente de demonstração.
#
#   bash docs/tutoriais-video/ambiente-demo/rebuild.sh --front      # antes: demo fictícia no ar
#   VOZ=/caminho/locucao_heygen.wav bash docs/tutoriais-video/apresentacao-financeiro/produzir.sh
#
# VOZ = o arquivo da locução gerada no HeyGen ("Voz Jairo Rodarte", request c3150e544b05437da077515113ffdafd).
# Ele fica no Drive, NÃO no repositório. Apesar da extensão .wav, o HeyGen entrega MP3: este script converte.
# Tudo é gerado em $OBRA (fora do repositório). Nada aqui toca produção.
set -euo pipefail
AQUI="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$AQUI/../../.." && pwd)"
OBRA="${OBRA:-/tmp/cowdata-video}"
: "${VOZ:?informe VOZ=<arquivo da locução do HeyGen>}"
mkdir -p "$OBRA/voz" "$OBRA/fontes"
cp "$AQUI"/{cena.html,especial.html,roteiro.json,trilha.py,montar.py,render_todas.mjs,capturar.mjs} "$OBRA/"
cp "$REPO"/frontend/public/brand/cowdata-*.svg "$OBRA/"

# Fonte Archivo (OFL), mesma família do site
if [ ! -f "$OBRA/fontes/archivo-latin-800-normal.woff2" ]; then
  (cd "$OBRA" && npm pack @fontsource/archivo@5.0.19 --silent >/dev/null && tar xzf fontsource-archivo-5.0.19.tgz \
    && cp package/files/archivo-latin-{400,600,700,800}-normal.woff2 fontes/ && rm -rf package fontsource-archivo-*.tgz)
fi
# Python com numpy + Pillow (trilha e montagem)
[ -x "$OBRA/venv/bin/python" ] || { python3 -m venv "$OBRA/venv"; "$OBRA/venv/bin/pip" install -q numpy pillow; }

ffmpeg -nostdin -y -loglevel error -i "$VOZ" -ac 1 -ar 48000 -c:a pcm_s16le "$OBRA/voz/locucao_pcm.wav"

cd "$OBRA"
# 1) telas reais da demo (2x), por cliques: a URL ?sub= não abre relatório (ver REGISTRO §6)
node capturar.mjs "$OBRA" "resumo=/financeiro" "pagar=/financeiro|Contas" "gaveta=/financeiro|Contas|Dar baixa" \
  "dre=/financeiro|Relatórios|Resultado|DRE da fazenda" "litro=/financeiro|Relatórios|Abrir o Resultado por litro" \
  "conc=/financeiro|Relatórios|Entrega ao contador|Conciliação bancária" "fech=/financeiro|Relatórios|Entrega ao contador|Fechamento do mês"
# 2) quadros de cada cena (seek(t) puro) 3) trilha + voz + efeitos 4) deslizes 5) volume −14 LUFS e MP4
node render_todas.mjs roteiro.json quadros
venv/bin/python trilha.py roteiro.json mix.wav
rm -rf final && venv/bin/python montar.py roteiro.json quadros final
ffmpeg -nostdin -y -loglevel error -i mix.wav -af "volume=6dB,alimiter=limit=0.38:attack=3:release=60:level=disabled" -c:a pcm_s24le mix_lim.wav
read -r ii itp ilra ith off <<< "$(ffmpeg -nostdin -hide_banner -i mix_lim.wav -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 \
  | sed -n '/^{/,/^}/p' | python3 -c "import json,sys;d=json.load(sys.stdin);print(d['input_i'],d['input_tp'],d['input_lra'],d['input_thresh'],d['target_offset'])")"
ffmpeg -nostdin -y -loglevel error -i mix_lim.wav \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=$ii:measured_TP=$itp:measured_LRA=$ilra:measured_thresh=$ith:offset=$off:linear=true,aresample=48000" \
  -c:a pcm_s16le mix_norm.wav
ffmpeg -nostdin -y -loglevel error -framerate 30 -i final/f%05d.png -i mix_norm.wav -c:v libx264 -profile:v high -pix_fmt yuv420p \
  -crf 17 -preset slow -g 60 -c:a aac -b:a 160k -ar 48000 -shortest -movflags +faststart CowData_Financeiro_apresentacao.mp4
echo "pronto: $OBRA/CowData_Financeiro_apresentacao.mp4"
