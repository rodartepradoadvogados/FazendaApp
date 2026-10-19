# motor_t3 — Temporada 3 "APP - MENU" (Estúdio 3D)

Só código reaproveitável: nenhum binário, nenhuma cópia do frontend, nenhum `three.module.js` (o `preparar.sh` baixa do CDN).
Pré-requisitos (sessão na nuvem do Claude Code): Node 22, Playwright em `/opt/node-tools`, Chromium em `/opt/pw-browsers`
(não rodar `playwright install`), ffmpeg, Python 3 com numpy/Pillow, e o frontend em produção (`cd frontend && npx next build && npx next start -p 3000`).

## Como o episódio é montado
| Peça | Arquivo | O que faz |
|---|---|---|
| Abertura 3D (~5,6 s) | `cena/index.html` | celular pousa, Menu explode em placas, Reprodução entra; fitas "T3 · MENU" e "EP. 1 · AGENDA REPRODUTIVA"; a câmera orbital se funde na pose frontal em 5,6 s |
| Modo explicativo (teste 2) | `cena/explicativo.html` | celular DE FRENTE, tela real em DPR 3, navegador dourado (anel → contorno que abraça o elemento, rastro, onda de toque) |
| Episódio (explicativo + encerramento) | `cena/episodio.html` (gerado) | montado por `cena/montar_episodio.py` a partir da base 3D de `explicativo.html` + `episodio_roteiro.js` (instantes, estados, navegador, câmera, legendas) + `episodio_corpo.js` (motor). Páginas altas rolam por trás do cabeçalho/barra reais, folhas (gavetas) deslizam, selo 3D "AGENDA PRONTA", celular vira de costas + fitas do próximo episódio |
| Quadros | `render3d.mjs` | Three.js 0.160 + SwiftShader (headless), um quadro por `window.seek(t)`; `FMT=jpg`, `DEDUP=1` (reaproveita quadros com mesma `window.sig(t)`), retoma de onde parou (pula quadros já gravados) |
| Telas reais | `captura/capturar_t3e1.mjs` (placas do Menu), `capturar_t3e2.mjs` (teste 2), `capturar_t3e1_ep.mjs` (episódio: páginas altas, folhas, mapa.json de caixas reais) | contra `captura/stub-api.mjs` com `EP=t3e1` (dados em `captura/t3e1.mjs`, cards salvos com estado) |
| Voz/áudio | `aud/exportar_roteiro_audio.mjs` + `../motor/audio/trilha_app.py` + `norm.sh` | beats.json → roteiro de efeitos (whoosh nas chegadas do navegador, tique nos toques, carimbo) → mix → −14 LUFS |
| Âncoras | `beats.json` | âncoras da locução remapeadas na voz real (`silencedetect`) |

## Receita
```bash
./preparar.sh                       # baixa three.module.js 0.160.0, gera kraft/grao (../motor), copia fontes
cd captura && (EP=t3e1 node stub-api.mjs &) ; DSF=3 node capturar_t3e1_ep.mjs   # → captura/shots_ep/ (+ mapa.json)
cd .. && ./copiar_telas.sh          # shots_ep → cena/tex (placas) e cena/tex2 (+ beats.json)
python3 cena/montar_episodio.py     # gera cena/episodio.html
./render_ep1.sh ../q                # 4 faixas em paralelo: abertura (index.html) + episódio (episodio.html) → q/q#####.jpg
# áudio: voz tratada (highpass 85, afftdn, deesser, compressor) → trilha → norm
ffmpeg -y -i voz.wav -af "highpass=f=85,afftdn=nr=10:nf=-30,deesser=i=0.35,acompressor=threshold=0.08:ratio=3:attack=5:release=90:makeup=2" -ar 48000 -ac 1 aud/voz_tratada.wav
node aud/exportar_roteiro_audio.mjs && python3 ../motor/audio/trilha_app.py aud/roteiro_t3e1.json aud/mix_bruto.wav && bash ../motor/audio/norm.sh aud/mix_bruto.wav aud/audio_final.wav
ffmpeg -framerate 30 -i ../q/q%05d.jpg -i aud/audio_final.wav -c:v libx264 -preset slow -crf 26 -profile:v high -level 4.1 -pix_fmt yuv420p -c:a aac -b:a 128k -movflags +faststart -shortest saida_leve.mp4
```
Rodar `aud/*.mjs` e os scripts de render a partir desta pasta (`motor_t3/`).

## Armadilhas
- `pkill -f render3d` dentro do mesmo comando de shell mata o próprio shell (a linha contém o padrão): use `pgrep -x node` + `kill`.
- O custo por quadro (~2,5 s) é raster do WebGL em SwiftShader; a atualização do mapa de sombra só roda no 1º quadro, no selo e no encerramento.
- O stub de T3 reinicia os cards com `GET /__reset`; o app em produção lê o stub em `localhost:8000`.
- `@keyframes ft-pulso` não existe no CSS do app (o `.ft-cartao-breve` não pulsa de verdade): o pulso do cartão é animado no motor a partir da captura.
- Voltar da ficha do animal recolhe os cards e listas (o componente remonta); o vídeo mostra o retorno ao estado anterior (corte).
