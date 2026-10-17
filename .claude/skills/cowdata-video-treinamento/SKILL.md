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

### Temporada 2 — Lançamentos (app Android) — PRÓXIMA, ~11 episódios
| Bloco | Episódios |
|---|---|
| REPRODUTIVOS (4) | lançamento de inseminação · diagnóstico · parto · protocolo de IATF |
| PRODUÇÃO (3) | controle leiteiro · pesagem corporal + secagem (um episódio) · BST |
| SANIDADE (2) | aplicação — curativa e preventiva no mesmo episódio · protocolo sanitário (curativo) |
| ALIMENTAÇÃO (1) | lançamento e sobra de cocho |
| MOVIMENTAR (1) | troca de lotes |
| PROTOCOLOS (1) | lançamento de protocolos |

Mesmo estilo Vox da Temporada 1, com variação visual para marcar a nova temporada (ex.: outra cor
de destaque nas fitas/marca-texto ou abertura própria) — decidir com o Jairo antes do 1º episódio.

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

### Ambiente
`quadros.mjs` usa o Playwright de `/opt/node-tools` e o Chromium de `/opt/pw-browsers` (sessão na
nuvem do Claude Code). Em outra máquina, ajuste esses dois caminhos.
