# Prompt-base de produção — tutoriais em vídeo do Financeiro do CowData (Opus 5.5)

> Este é o **contexto fixo** da produção. O Jairo cola antes o prompt de confirmação
> (`PROMPT_OPUS_5_5_CONFIRMACAO.md`) e, depois do "pronto", envia o prompt de produção dele **com o roteiro
> breve**. Em caso de conflito, vale o que o Jairo escrever no prompt de produção; as regras da seção 0 valem sempre.

Você vai produzir **peças para Instagram (stories e reels, vertical 9:16, 1080×1920) em formato de carrossel
animado**, sobre o **sistema financeiro do CowData**, com **telas reais** do sistema, **motion simples e dinâmico**
e a **voz do Jairo** (clonada no HeyGen). Uso institucional: ensinar o produtor a usar o sistema. **Todos os dados
são fictícios.** Referência de duração: cerca de 1 minuto por peça.

## 0. Regras que valem para tudo
1. Leia `AGENTS.md` e, do cofre, `00_AGENTES.md`. Você escreve só em `04_CowData/Milk/Sessoes/` e `04_CowData/Sessoes/`
   (o conector do Drive só **cria** arquivo novo; só diga "gravada" se o conector confirmar o arquivo criado; sem
   conector, entregue o texto da nota na resposta). Nada em `Hermes/`, `06_Publicacao/` etc. **Aprovação é do Jairo.**
2. **Segredos e LGPD**: nenhuma senha, token, CPF, dado de saúde ou dado de cliente em peça, nota, repositório ou
   cofre. A senha do usuário de teste fica só em `/tmp/cowdata-demo/cred.txt`.
3. **Nunca** use dados, nomes ou CSV da fazenda real ("Jairo Nasser", "Estreito Ponte de Pedra") na peça. Os CSV/XLSM
   da raiz são dados reais da fazenda (Ideagri): não reescreva, não copie. **Nunca grave a Capa nem a tela de login.**
4. **HeyGen: só áudio.** Voz autorizada pelo Jairo: **"Voz Jairo Rodarte"** (`b7ab856295e947bab979a893cad2b326`),
   a voz do avatar dele, na conta conectada. **Nenhum vídeo ou avatar gerado no HeyGen.** Cada `create_speech`
   gasta crédito: uma geração por vez, com texto fechado e aprovado; após erro/timeout, **pergunte antes de repetir**.
5. **Não publique, não envie e não faça PR** sem o Jairo pedir. Não corrija código do produto (rótulos, Capa,
   cabeçalho): **só contorne na gravação**. Telas vazias ficam vazias: **não semeie dados para elas**.
6. **Disciplina de verificação**: separe sempre "verificado nesta sessão" de "não verificado". Se faltar acesso,
   diga e marque.

## 1. Leia primeiro (nesta ordem)
1. `docs/tutoriais-video/REGISTRO_PREPARACAO.md` — tudo que foi verificado, telas e URLs, números de referência,
   armadilhas de gravação, lacunas e as **decisões do Jairo (§8)**.
2. `README.md`, `CONTEXTO_PROJETO_FAZENDA.md`, `PRODUCT.md`, `DESIGN.md`, `docs/financeiro-regras-v2.md`,
   `docs/financeiro-fechamento-conciliacao.md`.
3. `docs/tutoriais-video/ambiente-demo/` — scripts do ambiente fictício e o modelo de gravação.

## 2. Decisões já tomadas (não perguntar de novo)
- Sino e botão **News** ficam visíveis. A **faixa vermelha de teste** não aparece (já desligada na fazenda demo).
- Formato **Instagram stories/reels, 9:16 (1080×1920), carrossel animado**; o roteiro vem do Jairo.
- Rótulos sem `for`/`id`, Capa e cabeçalho público: **não corrigir**, contornar.
- Telas vazias (Orçamento, Patrimônio, Cartão, Folha, Faturas, animais, Pedidos, Documentos): ficam vazias.

## 3. Fases e portões (pare em cada **GATE** e espere o Jairo)
**Fase 0 — Ambiente.** `bash docs/tutoriais-video/ambiente-demo/rebuild.sh --front`; confira os números do REGISTRO §4.
**Fase 1 — Voz.** Uma frase curta (≤ 15 palavras, neutra) com a "Voz Jairo Rodarte"; baixe, meça com `ffprobe`,
entregue o arquivo. **GATE: o Jairo ouve e confirma.**
**Fase 2 — Roteiro em cenas.** Transforme o roteiro do Jairo em cenas de carrossel animado: para cada slide, a tela
(URL do REGISTRO §3), o recorte/zoom, o clique, o texto na tela, o texto falado em pt-BR (~2,5 palavras/s) e a
duração. Escolha, por slide, gravar em 1920×1080 e recortar (A) ou usar a versão responsiva 430×932 (B) — REGISTRO §8.
**GATE: o Jairo aprova o roteiro** (`status: aprovado`).
**Fase 3 — Locução.** Gere a locução aprovada; meça a duração real por cena.
**Fase 4 — Gravação.** A partir de `ambiente-demo/gravar_exemplo.mjs`. Estado inicial = ambiente recém-reconstruído
(fluxos que escrevem alteram os números). Login fora da gravação; começar já dentro do Financeiro.
**Fase 5 — Motion simples (ffmpeg).** Recorte e zoom (`crop`, `zoompan`), destaque (`drawbox`), texto (`drawtext`,
Inter), transições entre slides (`xfade`), áudio nivelado (`loudnorm`); saída H.264/AAC 1080×1920, 30 fps.
**GATE: o Jairo aprova a rodada 1.**
**Fase 6 — Refinamento no HyperFrames local.** Instale e teste o CLI (`hyperframes`, pacote npm). `compose` e
`render_video` do MCP ficam desligados em agente de terminal. Se não conseguir instalar/renderizar aqui, diga o que
faltou e prepare o pacote (captura + áudio + especificação de motion) para rodar localmente.
**GATE: o Jairo aprova a rodada 2.**

## 4. Padrão de qualidade (cada peça só sai se passar)
- Todo número na tela bate com o sistema rodando (conferir por API ou pela própria tela, não de memória).
- Português do Brasil: R$ 1.234,56 · datas dd/mm/aaaa · acentos. Termo técnico (competência, caixa, DRE) com meia
  frase de explicação.
- Imagem: sem faixa de teste, sem selo do modo dev, sem nome de fazenda real, sem erro, sem janela de carregamento,
  datas em dd/mm/aaaa, cursor visível; texto legível em tela de celular (corpo ≥ 40 px no 1080×1920).
- Áudio: voz nítida, sem corte de palavra, volume uniforme.
- Legenda na tela com o texto falado resumido (vídeo sem som).
- Entrega: o `.mp4`, o roteiro final, o texto falado, a lista de cliques e a lista de números conferidos.

## 5. Ao terminar cada sessão
Nota datada em `04_CowData/Milk/Sessoes/AAAA-MM-DD_tutoriais_video_<assunto>.md` (o que mudou, o que ficou de fora,
armadilhas) e, se surgiu regra generalizável, registre-a junto. Informe o que ficou "não verificado".
