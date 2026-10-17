---
name: cowdata-video-treinamento
description: >
  Produz e registra os vídeos de treinamento do CowData para os funcionários da fazenda (série
  "Treinamento", app Android, estilo Vox, 9:16) e os vídeos de apresentação do sistema: onde salvar
  (H:\Meu Drive\COWDATA), o aviso obrigatório quando não der para salvar, o plano de temporadas
  (Temporada 1 Rebanho concluída; Temporada 2 Lançamentos com ~11 episódios) e o motor de animação
  reaproveitável em motor/. Use sempre que o pedido envolver vídeo, tutorial, treinamento de
  funcionário, episódio, motion graphics ou locução do CowData.
---

# Vídeos de treinamento do CowData

## 1. Onde ficam os arquivos (repositório de mídias)

- **Pasta oficial de tudo o que é produzido no CowData:** `H:\Meu Drive\COWDATA`
  (Google Drive da conta do escritório, pasta `COWDATA` na raiz do Meu Drive).
  - `COWDATA\Tutoriais\FINANCEIRO\` — vídeos do financeiro (desktop).
  - `COWDATA\Tutoriais\APP - REBANHO\` — Temporada 1 (app Android).
- O cofre do Obsidian guarda **notas e caminhos**, nunca o vídeo (regra 6 do `00_AGENTES.md`).
- O repositório guarda o **motor** (código), nunca o MP4.

## 2. Regra obrigatória: vídeo que não foi salvo

O conector do Google Drive **não sobe arquivo de vídeo** (só cria nota/pasta). Sempre que um vídeo
for produzido e não puder ser salvo na pasta acima — por esse ou qualquer outro motivo —:

1. disponibilize o arquivo para download na conversa (envio de arquivo da sessão);
2. escreva, em destaque, na resposta final:

   **ATENÇÃO: AÇÃO NECESSÁRIA - SALVAR VÍDEO**
   seguido do nome do arquivo e da pasta de destino exata em `H:\Meu Drive\COWDATA\...`;
3. registre o mesmo aviso na nota da sessão no cofre (`04_CowData/Milk/Sessoes/`).

Nunca diga "salvo" sem confirmação da ferramenta.

## 3. Séries e episódios

### Temporada 1 — Rebanho (app Android) — CONCLUÍDA em 2026-10-16
| Ep. | Tema | Duração |
|---|---|---|
| 1 | Ficha do animal (busca, Resumo, Reprodução, Produção, Dados gerais, Sanidade, Movimentações) | 1:19 |
| 2 | Lotes (Composição, Indicadores, Exportar PDF / Compartilhar) | 0:56 |
| 3 | Listas do painel (Gestantes, Inseminadas, PEV, Vazias, Aptas, Atrasadas, IA atual, Parto previsto, Secagens, DEL/Produção, IEP, Ver Animal) | 1:30 |

### Temporada 2 — Lançamentos (app Android) — EM ANDAMENTO (Ep. 1 concluído em 2026-10-17), ~11 episódios
| Bloco | Episódios |
|---|---|
| REPRODUTIVOS (4) | lançamento de inseminação · diagnóstico · parto · protocolo de IATF |
| PRODUÇÃO (3) | controle leiteiro · pesagem corporal + secagem (um episódio) · BST |
| SANIDADE (2) | aplicação — curativa e preventiva no mesmo episódio · protocolo sanitário (curativo) |
| ALIMENTAÇÃO (1) | lançamento e sobra de cocho |
| MOVIMENTAR (1) | troca de lotes — **Ep. 1 CONCLUÍDO** (`APP-Lancamentos_Ep1_Troca-de-lotes.mp4`, 1:01) |
| PROTOCOLOS (1) | lançamento de protocolos |

Mesmo estilo Vox da Temporada 1, com a variação visual da Temporada 2 definida no Ep. 1 (ver "Padrões visuais da
Temporada 2" abaixo). Pasta de destino: `H:\Meu Drive\COWDATA\Tutoriais\APP - LANÇAMENTOS\`.

### Fora das séries de app
- FINANCEIRO (desktop, motion graphics clássico): apresentação v1 e "Contas a pagar" v2 (1:15).

## 4. Como produzir (fluxo que funcionou)

1. **Mapear o código da tela antes do roteiro.** Rótulos exatos, condicionais por plataforma
   (ex.: "Compartilhar" só no Android; "Já foi pago" só em lançamento à vista; Vazias é
   guarda-chuva). Divergência entre o pedido e o app vira pergunta ao Jairo, não suposição.
2. Roteiro (~2 palavras/s com pausas) → aprovação → locução.
3. **Voz:** clone "Voz Jairo Rodarte" no HeyGen (voice_id da conta; motor padrão orca). Velocidade
   natural (1,0×). Voz tratada: passa-alta 85 Hz, redução de ruído, de-esser, compressão.
4. **Linha do tempo:** `motor/tl.py` coloca cada frase com folgas entre elas e gera âncoras por
   palavra (`audio/tl_epN.json`). Toda animação é ancorada nessas palavras.
5. **Animação:** `motor/ep.src.html` (motor) + `motor/episodios/epN.js` (roteiro de câmera, toques,
   telas, anotações, fitas, títulos, capa). Tudo é função pura do tempo (`window.seek(t)`).
6. **Render:** `python3 build.py epN` → `HTML=epN.html node quadros.mjs q 0 <total>` (dividir em 4
   faixas em paralelo) → trilha `audio/trilha_app.py` (numpy) → `audio/norm.sh` → ffmpeg
   (H.264 CRF 23 preset slow, AAC mono 128k, `+faststart`).
7. **Conferir antes de entregar:** folha de contato do MP4 final e quadros DURANTE os movimentos
   (não só nas chegadas); números fictícios precisam fechar entre si em toda a série; nenhuma
   anotação pode vazar para a tela seguinte.
8. Nota datada em `04_CowData/Milk/Sessoes/` + aviso da seção 2 quando aplicável.

### Padrões visuais do estilo Vox (app)
- Fundo de papel (`papel.html`/`grao.html` → `snap.mjs` gera os PNG; não versionar os PNG).
- Celular grande (tela ≈ 960 px de largura no quadro 1080×1920), zoom dinâmico dentro da tela.
- Toque: círculo translúcido do tamanho de um dedo, rastro, aperto e onda dourada; o "voltar"
  também é tocado em cena.
- Marca-texto dourado no título, anotações à mão (stop-motion 12 qps), fitas crepe para códigos.
- Dados sempre fictícios ("Fazenda Boa Esperança"); nunca nome real de fazenda/cliente.
- Áudio mono, -14 LUFS, música baixa sob a voz.

### Padrões visuais da Temporada 2 (Lançamentos) — motor `t2.src.html` + `episodios/t2e1.js`
- **A tela do celular são capturas do app real** (nada desenhado à mão): Playwright em modo produção (`next build` + `next start`) contra
  uma API de mentira com dados fictícios da Fazenda Boa Esperança. Viewport 390×844, `locale pt-BR`, fuso `America/Sao_Paulo`,
  relógio fixo 17/10/2026 10:05, tema claro, `--lang=pt-BR` (senão o campo de data sai mm/dd/aaaa). Capturas em 1440 px de largura
  (1,5× os 960 px do quadro) para o zoom não borrar. O cabeçalho do app tem um nome de fazenda real escrito no layout; a captura
  troca esse texto por "Fazenda Boa Esperança" via MutationObserver (não mexe no app).
- Telas altas = captura normal (cabeçalho, barra fixa, navegação) + captura "tall" (viewport alto, barra escondida); o motor rola a
  imagem alta por trás do cabeçalho/barra fixos. `mapa.json` guarda as caixas (px CSS) de cada alvo de toque/grifo.
- Fundo **papel Kraft** (`papel_kraft.html` → `snap_t2.mjs` gera `assets/kraft.png`, não versionado) com grade pontilhada e vinheta;
  **grampo de prancheta**; **selo Dymo** "TEMP. 02 · MÓDULO LANÇAMENTOS"; fita crepe de abertura com o nome do episódio.
- Cores: Dourado #E0A63C (toques com rastro e onda, destaque do botão final), Verde Manejo #2E7D52 e Azul Operacional #1E6FA8
  (grifos de seleção e seta tracejada De → Para a 12 qps), tinta #1A2638. **Carimbo de borracha** verde-escuro "✔ LANÇADO NO REBANHO"
  com tremida de 3 quadros. Legenda e títulos em zona segura (topo 220, base 380, laterais 80).
- Regra de limpeza: toda anotação presa a uma tela some EXATAMENTE no quadro da troca de tela seguinte (o motor aplica sozinho).
- Áudio: música a **−6 dB** do padrão da T1 (`ganho_musica` 0,065 no roteiro), SFX sintetizados (rasgo de fita, caneta, toque, carimbo, whoosh),
  voz com highpass/afftdn/deesser/compressor. Master `norm.sh` → −14 LUFS, pico real ≤ −1 dBTP.
- Receita: `python3 tl_t2e1.py` (gera `audio/tl_t2e1.json`) → capturar telas → `python3 build_t2.py t2e1 <saida> <captura>` →
  `node dump_t2.mjs` (beats/camadas) → `audio/roteiro_t2.py` → `audio/trilha_app.py` → `audio/norm.sh` → `HTML=<saida>/t2e1.html node quadros.mjs`
  em 4 faixas → ffmpeg `-crf 18 -pix_fmt yuv420p -movflags +faststart`, AAC mono. Voz do HeyGen pode vir como MP3 com extensão .wav:
  converter com ffmpeg antes de passar ao `trilha_app.py`.

### Ambiente
`quadros.mjs` usa o Playwright de `/opt/node-tools` e o Chromium de `/opt/pw-browsers` (sessão na
nuvem do Claude Code). Em outra máquina, ajuste esses dois caminhos.
