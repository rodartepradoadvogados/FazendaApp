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

## Episódio 4 — Ciclos de 21 dias (Menu › Reprodução; fecha o módulo)
Arquivos `*_t3e4`: `cena/index_t3e4.html` (abertura "T3 · MENU / EP. 4 / CICLOS DE 21 DIAS"), `cena/episodio_roteiro_t3e4.js` + `cena/episodio_corpo_t3e4.js` (`python3 cena/montar_episodio_t3e4.py` → `cena/episodio_t3e4.html`), `captura/capturar_t3e4_ep.mjs` (+ `captura/t3e4.mjs`, `EP=t3e4` no stub), `beats_t3e4.json`, `copiar_telas_t3e4.sh`, `render_ep4.sh`, `aud/exportar_roteiro_audio_t3e4.mjs`.
```bash
cd ../../../../frontend && npx next start -p 3400 &        # .next atual (sem mudança de frontend desde o PR #943)
cd captura && (EP=t3e4 STUB_PORT=8400 node stub-api.mjs &) ; STUB=8400 APP=3400 node capturar_t3e4_ep.mjs   # shots_ep/ + mapa.json (menu, ci0 e cd0 altas)
cd .. && ./copiar_telas_t3e4.sh && python3 cena/montar_episodio_t3e4.py && ./render_ep4.sh ../q   # TOTAL=2310 quadros (77 s)
node aud/exportar_roteiro_audio_t3e4.mjs   # → aud/roteiro_t3e4.json; depois trilha_app.py + norm.sh como no Ep. 1
```
Armadilhas: (1) a fita 3D das taxas fica a 26 unidades da câmera (o celular fica a ~32 no zoom 1,2); (2) `SEED_CICLOS` muda o sorteio dos baldes do stub (padrão 12 dá resumo verde/âmbar/verde); (3) ciclos 5 e 6 em apuração por regra real (28 dias); (4) página alta do detalhe só rola até `docH − 844` (389 px): ajuste a câmera, não o scroll, para o último grupo.

## Episódio 5 — Alimentação: Plano por lote e Consultar dietas (Menu › Alimentação)
Arquivos `*_t3e5`: `cena/index_t3e5.html` (abertura "T3 · MENU / EP. 5 / ALIMENTAÇÃO"; a placa que avança é a seção Alimentação aberta, posições das placas lidas de `tex/mapa.json`), `cena/episodio_roteiro_t3e5.js` + `cena/episodio_corpo_t3e5.js` (`python3 cena/montar_episodio_t3e5.py` → `cena/episodio_t3e5.html`; páginas = Menu, Plano, Lançar nova dieta, Consultar dietas, dieta aberta; fitas 3D de texto `FITAS_TXT`), `captura/capturar_t3e5_ep.mjs` (+ `captura/t3e5.mjs`, `EP=t3e5` no stub), `beats_t3e5.json`, `copiar_telas_t3e5.sh`, `render_ep5.sh`, `aud/exportar_roteiro_audio_t3e5.mjs`.
```bash
cd ../../../../frontend && npx next build && npx next start -p 3500 &      # precisa do build com os tratos por dieta (PR #949)
cd captura && (EP=t3e5 STUB_PORT=8500 node stub-api.mjs &) ; STUB=8500 APP=3500 node capturar_t3e5_ep.mjs   # shots_ep/ + mapa.json (pl0, ld0, cs0, cs1 altas)
cd .. && ./copiar_telas_t3e5.sh && python3 cena/montar_episodio_t3e5.py && ./render_ep5.sh ../q   # TOTAL=2088 quadros (69,6 s)
node aud/exportar_roteiro_audio_t3e5.mjs   # → aud/roteiro_t3e5.json; depois trilha_app.py + norm.sh como no Ep. 1
```
Armadilhas: (1) o texto do cabeçalho do Plano é vários nós: `trecho()` concatena nós antes do regex; (2) o app mostra "Lote 1 · Alta"; (3) Voltar fica no topo da página (a rolagem volta a 0 antes do toque); (4) o efetivo da apresentação de dieta encerrada é o atual do lote; (5) âncoras do plano de produção vieram adiantadas: remapeie pelas palavras da voz real.

## Episódio 6 — Produção (Menu › Produção, módulo inteiro)
Arquivos `*_t3e6`: `cena/index_t3e6.html` (abertura "T3 · MENU / EP. 6 / PRODUÇÃO"; a placa que avança é a seção Produção aberta, posições de `tex/mapa.json`), `cena/episodio_roteiro_t3e6.js` + `cena/episodio_corpo_t3e6.js` (`python3 cena/montar_episodio_t3e6.py` → `cena/episodio_t3e6.html`; páginas = mp0/mp1 Menu, uc0/uc1/uc1b/uc2 Últimos controles, ql0/ql1 Qualidade, se0, bs0, pe0), `captura/capturar_t3e6_ep.mjs` (+ `captura/t3e6.mjs`, `EP=t3e6` no stub), `beats_t3e6.json`, `copiar_telas_t3e6.sh`, `render_ep6.sh`, `aud/exportar_roteiro_audio_t3e6.mjs`.
```bash
cd ../../../../frontend && npx next build && npx next start -p 3600 &      # precisa do build com os filtros de Produção (PR #957)
cd captura && (EP=t3e6 STUB_PORT=8600 node stub-api.mjs &) ; STUB=8600 APP=3600 node capturar_t3e6_ep.mjs   # shots_ep/ + mapa.json (todas as telas como páginas altas, máx. 5200 px)
cd .. && ./copiar_telas_t3e6.sh && python3 cena/montar_episodio_t3e6.py && ./render_ep6.sh ../q   # TOTAL=2907 quadros (96,9 s)
node aud/exportar_roteiro_audio_t3e6.mjs   # → aud/roteiro_t3e6.json; depois trilha_app.py + norm.sh como no Ep. 1
```
Armadilhas: (1) o contêiner de rolagem é o BODY e o Menu volta ao topo após Voltar; (2) `hasText: "Produção"` casa "Reprodução": use `/^Produção/`; (3) o texto do cartão junta nós sem espaço: meça trechos dentro de cada folha; (4) âncoras: transcrição local com faster-whisper (`asr.py`: modelo small, int8) em vez dos tempos do TTS; (5) o stub respeita lotes/numeros/ultimos/tipo/motivos/del_min/del_max/origem e devolve sempre `lote_fonte: "dia"`; BST genérico ("Somatotropina bovina (BST)").

## Episódio 7 — Alimentação: Lançar nova dieta e Necessidade Mensal (Menu › Alimentação; fecha o módulo Alimentação)
Arquivos `*_t3e7`: `cena/index_t3e7.html` (abertura "T3 · MENU / EP. 7 / ALIMENTAÇÃO"), `cena/episodio_roteiro_t3e7.js` + `cena/episodio_corpo_t3e7.js` (`python3 cena/montar_episodio_t3e7.py` → `cena/episodio_t3e7.html`; páginas = menu_alim, ld0…ld8 (Lançar nova dieta em 9 estados), pk_vp (seletor de produto aberto), pl0, cs0, nm0; placa 3D do diálogo `FITAS_TXT` com `corpo`/`botoes`), `captura/capturar_t3e7_ep.mjs` (+ `captura/t3e7.mjs`, `EP=t3e7` no stub — herda t3e6…t3e1, aplica o POST da dieta como o backend real), `beats_t3e7.json`, `copiar_telas_t3e7.sh`, `render_ep7.sh`, `aud/exportar_roteiro_audio_t3e7.mjs`.
```bash
cd ../../../../frontend && npx next build && npx next start -p 3700 &
cd captura && (EP=t3e7 STUB_PORT=8700 node stub-api.mjs &) ; STUB=8700 APP=3700 node capturar_t3e7_ep.mjs   # shots_ep/ + mapa.json (+ mapa.confirm.msg)
cd .. && ./copiar_telas_t3e7.sh && python3 cena/montar_episodio_t3e7.py && ./render_ep7.sh ../q   # TOTAL=2448 quadros (81,6 s)
node aud/exportar_roteiro_audio_t3e7.mjs   # → aud/roteiro_t3e7.json; depois trilha_app.py + norm.sh como no Ep. 1
```
Armadilhas: (1) o `window.confirm` é nativo e não renderiza no headless: a captura grava o texto REAL (`page.on("dialog")` → `mapa.confirm`) e aceita; o vídeo mostra uma placa 3D com esse texto e Cancelar/OK como texto; (2) o backend real encerra a dieta anterior NA DATA DE INÍCIO da nova (`data_efetivo_encerramento = data_abertura`): o Consultar dietas mostra "Fim 24/10/2026", não 23/10; (3) o cabeçalho do app lê `fazenda_atual` do localStorage (lib.mjs) — não se troca texto no DOM; (4) o seletor de produto é um modal fixo (`EstoquePicker`): vira página de viewport (`pk_vp`); (5) o campo de data do app passa da borda (390 px): o contorno é cortado em 376 px (`CL()` no roteiro); (6) `CH = M.pl_vp` (viewport) fornece cabeçalho e barra; (7) âncoras de `beats_t3e7.json` vêm de transcrição local (faster-whisper small, int8); (8) `next start -p 3700` + `EP=t3e7 STUB_PORT=8700`; relógio fixo 24/10/2026; (9) Necessidade Mensal: stub soma as dietas ATIVAS × 30, ensacados (Concentrado 40 kg, Núcleo 25 kg) em sacas arredondadas para cima, silagem a granel.

## Episódio 8 — Sanidade (Menu › Sanidade, módulo inteiro)
Arquivos `*_t3e8`: `cena/index_t3e8.html` (abertura "T3 · MENU / EP. 8 / SANIDADE"; a placa que avança é a seção Sanidade aberta, posições de `tex/mapa.json`), `cena/episodio_roteiro_t3e8.js` + `cena/episodio_corpo_t3e8.js` (`python3 cena/montar_episodio_t3e8.py` → `cena/episodio_t3e8.html`; páginas = menu_sanid, vl0/vl1 (lista), ex0…ex8 (o dia: preparação, quem aplica, como aplicar, tronco, sem sinal), na_vp (gaveta "Não aplicar"), hs0…hs3 (Histórico), rm0/rm1 (Remédios)), `captura/capturar_t3e8_ep.mjs` (+ `captura/t3e8.mjs`, `EP=t3e8` no stub — herda t3e7…t3e1), `beats_t3e8.json`, `copiar_telas_t3e8.sh`, `render_ep8.sh`, `aud/exportar_roteiro_audio_t3e8.mjs`.
```bash
cd ../../../../frontend && npx next build && npx next start -p 3800 &      # precisa do build com o PR #967 (Sanidade no app)
cd captura && (EP=t3e8 STUB_PORT=8800 node stub-api.mjs &) ; STUB=8800 APP=3800 node capturar_t3e8_ep.mjs   # shots_ep/ + mapa.json (pág. altas; ex8, na_vp e menu_sanid são capturas de viewport)
cd .. && ./copiar_telas_t3e8.sh && python3 cena/montar_episodio_t3e8.py && ./render_ep8.sh <pasta_de_quadros>   # TOTAL=3102 quadros (103,4 s)
node aud/exportar_roteiro_audio_t3e8.mjs   # → aud/roteiro_t3e8.json; depois trilha_app.py + norm.sh como no Ep. 1
```
Armadilhas: (1) o roteiro escolhe as caixas por TEXTO (`BT`/`FO`/`RO` sobre `botoes`/`folhas`/`rotulos` do `mapa.json`): um rótulo que mude no app quebra na hora do `acha()` — valide todas as caixas e a rolagem antes do render (script de validação: avalie `WP` e `TAPS` contra o `mapa.json`, conferindo página no ar, área visível 96–775 px e rolagem ≤ `docH − 844`); (2) "sem sinal" de verdade: `SEM_SINAL=true` faz o `context.route` abortar a API e o toque em "Atualizar" cai na cópia guardada ("Sem sinal: usando o dia guardado neste celular"); o app mostra um aviso laranja global de conexão que empurra o conteúdo ~100 px e some só com "Tentar novamente" depois de a API voltar — por isso essa tela é viewport (`vp("ex8")`) e a captura limpa o aviso antes das telas seguintes; (3) na preparação o último checkbox é o "Estou ciente" do cartão de ciência (some quando tudo está conferido); (4) o servidor já tira o vendido/morto da fila: o stub manda `dia.saidos` e `contagens.saidos`, e o aviso aparece na lista e no dia; (5) `eu.administrador = true` mostra Editar/Excluir nos curativos (real; o app esconde de quem não é administrador); (6) o app mostra "Lote 01 - Alta" no histórico e agrupa por lote (blocos "N vacas · M aplicações") ao escolher Lote(s); (7) âncoras: transcrição local (faster-whisper small, int8) corrigida com `silencedetect` — o início da 1ª palavra depois de pausa vem ~0,3 s adiantado; (8) `next start -p 3800` + `EP=t3e8 STUB_PORT=8800`; relógio fixo 24/10/2026.
(9) Fitas 3D de cadastro (`FITAS_TXT` do roteiro): "CONFORME O CADASTRO DA FAZENDA / dose e carência — neste exemplo" em 61,5–69,5 s (Histórico, no alto) e 83,7–91,4 s (Remédios, embaixo, `py: 1090`, para não cobrir o aviso e as linhas contornadas). Regra do dono: o que vem de cadastro nunca é regra fixa.
