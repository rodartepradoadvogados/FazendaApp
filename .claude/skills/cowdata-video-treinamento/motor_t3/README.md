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

## Episódio 2 — Protocolos IATF em andamento
Arquivos com sufixo `_t3e2` (não alteram o Ep. 1): `cena/index_t3e2.html` (abertura "T3 · MENU / EP. 2 / PROTOCOLOS IATF"), `cena/episodio_roteiro_t3e2.js` + `cena/episodio_corpo_t3e2.js` (`python3 cena/montar_episodio_t3e2.py` → `cena/episodio_t3e2.html`), `captura/capturar_t3e2_ep.mjs` (+ dados em `captura/t3e2.mjs`, `EP=t3e2` no stub; herda o t3e1), `beats_t3e2.json`, `copiar_telas_t3e2.sh`, `render_ep2.sh`, `aud/exportar_roteiro_audio_t3e2.mjs`.
```bash
cd captura && (EP=t3e2 STUB_PORT=8100 node stub-api.mjs &) ; STUB=8100 APP=3100 node capturar_t3e2_ep.mjs   # app em produção: next start -p 3100; gera shots_ep/ (+ folha.pdf, folha_pdf.png, mapa.json)
cd .. && ./copiar_telas_t3e2.sh && python3 cena/montar_episodio_t3e2.py && ./render_ep2.sh ../q   # TOTAL=2079 quadros (69,3 s)
node aud/exportar_roteiro_audio_t3e2.mjs   # → aud/roteiro_t3e2.json; depois trilha_app.py + norm.sh como no Ep. 1
```
Precisa de `pdftoppm`/`pdftotext` (poppler). `shots_ep/`, `cena/tex*` e os quadros são regenerados por episódio (não rode a captura do Ep. 1 e a do Ep. 2 na mesma pasta ao mesmo tempo).
Armadilhas: (1) o `.next` de produção chama a API em `localhost:8000`: a captura redireciona por `context.route` para a porta do stub; (2) o nome do lançamento segue `gerar_nome_lancamento` (molde em caixa alta + datas); com o molde "IATF 3 MANEJOS" o título cabe no cabeçalho do PDF — nomes mais longos (ex. com o lote) sobrepõem o "Gerado por" no PDF real; (3) D11 só aparece como etapa atual de vaca no dia da inseminação — com D0 em 10/10 e hoje 17/10 a lista mostra D7 e D9.

## Episódio 3 — Baixa e aplicação do protocolo (Menu › Protocolos)
Arquivos `*_t3e3`: `cena/index_t3e3.html` (abertura "T3 · MENU / EP. 3 / BAIXA E APLICAÇÃO"), `cena/episodio_roteiro_t3e3.js` + `cena/episodio_corpo_t3e3.js` (`python3 cena/montar_episodio_t3e3.py` → `cena/episodio_t3e3.html`), `captura/capturar_t3e3_ep.mjs` (+ `captura/t3e3.mjs`, `EP=t3e3` no stub), `beats_t3e3.json`, `copiar_telas_t3e3.sh`, `render_ep3.sh`, `aud/exportar_roteiro_audio_t3e3.mjs`.
```bash
cd ../../../../frontend && npx next build && npx next start -p 3300 &     # precisa do build com a baixa nova (PR #943)
cd captura && (EP=t3e3 STUB_PORT=8300 node stub-api.mjs &) ; STUB=8300 APP=3300 node capturar_t3e3_ep.mjs   # shots_ep/ + mapa.json
cd .. && ./copiar_telas_t3e3.sh && python3 cena/montar_episodio_t3e3.py && ./render_ep3.sh ../q          # TOTAL=2109 quadros (70,3 s)
node aud/exportar_roteiro_audio_t3e3.mjs   # → aud/roteiro_t3e3.json; depois trilha_app.py + norm.sh como no Ep. 1
```
Armadilhas: (1) "De qual lote?" só existe no protocolo sanitário (o backend só devolve `lotes` para `origem == "sanitario"`): o IATF mostra só o frasco, por isso o stub tem um sanitário fictício (id 401); (2) selects nativos não abrem no headless: lista aberta = `<select size=N>`; (3) o texto do aviso de estoque vem do POST `/baixa` do stub, no formato de `rules/estoque_baixa.py`; (4) `__reset` do stub reinicia estoque e baixas (rode antes de cada captura).
