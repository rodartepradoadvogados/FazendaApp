# Vídeo de apresentação do Financeiro (reel 9:16, 56 s) — fontes

**Estado:** rodada 1 entregue ao Jairo em 14/10/2026, aguardando aprovação (`status: aprovado` é dele).
Reproduzir: `produzir.sh` (precisa da demo no ar e do arquivo da locução, que fica no Drive).

## O que é
Reel de ~1 minuto que apresenta o Financeiro a quem ainda não usa o CowData. São 8 cenas em "carrossel animado"
(deslize de 0,5 s entre elas), com telas reais da demo fictícia "Fazenda Vale Verde", a voz do Jairo (HeyGen, só
áudio, 1 geração) e trilha original sintetizada. Identidade visual: a do CowData (nota no cofre
`04_CowData/Milk/Sessoes/2026-10-14_identidade_visual_videos_cowdata.md`).

| # | Início | Dur. | Cena | Tela (captura 2x) | Número em destaque |
|---|---|---|---|---|---|
| 1 | 0 s | 4 s | Gancho "Quanto sobra em cada litro?" | — | — |
| 2 | 4 | 6 | Como está o caixa hoje? | Resumo | R$ 90.170 no banco · R$ 15.200 vencida |
| 3 | 10 | 6 | O que vence esta semana? | Contas a pagar + gaveta Dar baixa (sem confirmar) | R$ 2.840 em 7 dias |
| 4 | 16 | 10 | Estou ganhando? | DRE da fazenda (set/2026) | R$ 41.150 · R$ 11.210 · 27,2% |
| 5 | 26 | 10 | Quanto sobra por litro? | Resultado por litro | R$ 2,95 − R$ 2,30 = R$ 0,65 |
| 6 | 36 | 8 | O banco bate com o sistema? | Conciliação bancária | 8 de 9 · R$ 29,90 |
| 7 | 44 | 6 | Pronto para o contador? | Fechamento do mês | 7 de 8 · falta conciliação |
| 8 | 50 | 6 | Fecho: logo + "O financeiro da fazenda, sem planilha." + @cowdata | — | — |

## Como funciona (método do "carrossel vivo", adaptado)
- `roteiro.json` é a fonte única: tempos das cenas, trechos da voz, câmera, cursor, cliques, grifos, números e
  efeitos. O render (imagem) e a `trilha.py` (som) leem o mesmo arquivo, por isso não se desencontram.
- `cena.html` / `especial.html`: `montar(cfg)` + `seek(t)` desenham o quadro de `t` como função pura (sem
  `requestAnimationFrame`, timer ou acaso). `render_todas.mjs` fotografa cada quadro (Chromium com
  `--disable-gpu --disable-partial-raster`).
- `trilha.py`: 120 BPM, F(add9) | C/E | Dm7 | B♭(add9)→C, camadas por cena, ducking sob a voz, 3 efeitos
  (impacto, whoosh, clique), ruído com semente fixa.
- `montar.py`: deslize easeInOutCubic de 0,5 s entre as cenas. Saída: H.264 High 1080×1920 30 fps, AAC 48 kHz.
- Zona segura do reel: nada acima de y=260 nem abaixo de y≈1540, nada à direita na coluna dos ícones.

## Medições da rodada 1 (verificadas nesta sessão)
- 56,0 s · 1080×1920 · 30 fps · H.264 + AAC 48 kHz · −14,3 LUFS integrado · pico −1,1 dBTP (medido no MP4).
- Voz ~8 dB acima da música nos respiros (RMS medido por trecho).
- Determinismo: 34 de 39 quadros idênticos em ordem embaralhada; os 5 restantes, todos em movimento de câmera,
  diferem abaixo de 1 nível de cor (PSNR 56–95 dB), invisível.
