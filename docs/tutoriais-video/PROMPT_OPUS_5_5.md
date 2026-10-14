# Prompt para o Opus 5.5 — produção dos tutoriais em vídeo do Financeiro do CowData

> Cole tudo abaixo da linha numa sessão nova do Claude Code, com o modelo Opus 5.5, neste repositório
> (`rodartepradoadvogados/fazendaapp`). Antes, confirme que `docs/tutoriais-video/` existe no checkout.

---

Você vai produzir **vídeos-tutorial de 1 minuto** sobre o **sistema financeiro do CowData** (software de gestão
de fazenda leiteira), com **telas reais**, **motion simples e dinâmico** e a **minha voz** (Jairo, clonada no
HeyGen). Uso institucional: ensinar o produtor a usar o sistema. **Os dados são todos fictícios.**

## 0. Regras que valem para tudo
1. Leia `AGENTS.md` e, do cofre, `00_AGENTES.md`. Você escreve só em `04_CowData/Milk/Sessoes/` e `04_CowData/Sessoes/`
   (o conector do Drive só **cria** arquivo novo; só diga "gravada" se o conector confirmar o arquivo criado; sem
   conector, entregue o texto da nota na resposta). Nada em `Hermes/`, `06_Publicacao/` etc. **Aprovação é minha.**
2. **Segredos e LGPD**: nenhuma senha, token, CPF, dado de saúde ou dado de cliente em vídeo, nota, repositório ou
   cofre. A senha do usuário de teste fica só em `/tmp/cowdata-demo/cred.txt`.
3. **Nunca** use dados, nomes ou CSV da fazenda real ("Jairo Nasser", "Estreito Ponte de Pedra") no vídeo. Os CSV/XLSM
   da raiz são dados reais da fazenda (Ideagri): não reescreva, não copie.
4. **Nada de vídeo ou avatar no HeyGen.** Do HeyGen use **somente áudio** (`create_speech`) com a minha voz. Cada
   geração gasta crédito: uma por vez, texto fechado e aprovado; após erro/timeout, **pergunte antes de repetir**.
5. **Não publique, não envie, não faça PR** sem eu pedir. Não escreva roteiro de vídeo novo sem passar pelo gate da Fase 2.
6. **Disciplina de verificação**: separe sempre "verificado nesta sessão" de "não verificado". Se faltar acesso,
   diga e marque.

## 1. Leia primeiro (nesta ordem)
1. `docs/tutoriais-video/REGISTRO_PREPARACAO.md` — **tudo que foi verificado, as telas e URLs, os números de
   referência, as armadilhas de gravação e as lacunas**. Não refaça o que já está provado; confirme só o que a
   Fase 0 manda.
2. `README.md`, `CONTEXTO_PROJETO_FAZENDA.md`, `PRODUCT.md`, `DESIGN.md`, `docs/financeiro-regras-v2.md`,
   `docs/financeiro-fechamento-conciliacao.md`.
3. `docs/tutoriais-video/ambiente-demo/` — scripts do ambiente fictício e o modelo de gravação.

## 2. Fases e portões (pare em cada **GATE** e espere minha resposta)

**Fase 0 — Ambiente.** Rode `bash docs/tutoriais-video/ambiente-demo/rebuild.sh --front`. Confira os números da
tabela de referência do REGISTRO §4 (DRE do mês anterior, saldos, conciliação, custo por litro). Se algum divergir,
investigue antes de seguir. Registre o resultado.

**Fase 1 — Voz.** Gere **uma frase curta** (até ~15 palavras, neutra, sem dado sensível) com cada uma das duas vozes
("Jairo Rodarte" `43ccb8544a6b48af8272a2798f6465ec`; "Voz Jairo Rodarte" `b7ab856295e947bab979a893cad2b326`),
baixe os áudios, meça com `ffprobe` e me entregue os arquivos. **GATE: eu escolho a voz.** (A conta HeyGen conectada
tem titular diferente de mim — se o conector bloquear ou pedir confirmação, pare e me diga.)

**Fase 2 — Proposta do vídeo-piloto.** Proponha o **piloto** (sugestão: "Lançar uma despesa e dar baixa", fluxo já
provado com cliques reais no REGISTRO §3). Entregue: objetivo, público, 1 minuto dividido em cenas (tela,
clique/zoom/legenda, texto falado em pt-BR por cena, duração por cena). Palavras faladas ~2,5 por segundo (60 s ≈ 140–150 palavras).
**GATE: eu aprovo o roteiro** (`status: aprovado`).

**Fase 3 — Locução do piloto.** Gere a locução aprovada com a voz escolhida; meça a duração real de cada cena.

**Fase 4 — Gravação.** Parta de `ambiente-demo/gravar_exemplo.mjs`. Estado inicial = ambiente recém-reconstruído
(fluxos que escrevem alteram os números; reconstrua entre gravações). Casar o ritmo dos cliques com a locução.
Login **fora** da gravação; o vídeo começa dentro do Financeiro; nunca gravar a Capa nem a tela de login.

**Fase 5 — Motion simples (ffmpeg).** Zoom nos elementos citados (`zoompan`), destaque (`drawbox`), legendas na
tela (`drawtext`, fonte Inter), transições (`xfade`), áudio nivelado (`loudnorm`), saída H.264/AAC 1080p 30 fps,
16:9. Entregue o arquivo e um quadro de cada cena. **GATE: eu aprovo a rodada 1.**

**Fase 6 — Refinamento no HyperFrames local.** Instale e teste o CLI (`hyperframes`, pacote npm; MCP do
HyperFrames só lê projetos — `compose`/`render_video` ficam desligados em agente de terminal). Reaproveite a
captura de tela e a locução; refine o motion em HTML/GSAP. Se não conseguir instalar ou renderizar aqui, **diga o
que faltou** e prepare o pacote (captura + áudio + especificação de motion) para eu rodar localmente.
**GATE: eu aprovo a rodada 2.**

**Fase 7 — Série.** Só depois do piloto aprovado. Temas candidatos por pergunta que a tela responde (REGISTRO §3):
Resumo, Contas a pagar/receber, baixa em lote, Painel do dono, DRE ("Estou ganhando?"), Resultado por litro,
Caixa real, Conciliação bancária, Fechamento do mês. **Temas cujas telas estão vazias na demo** (Orçamento,
Patrimônio, Cartão, Folha, Faturas, Compra/venda de animais) **pedem antes um passo de seed** em
`seed_demo.py` — proponha e teste o seed, mostre-me o resultado e só então roteirize.

## 3. Padrão de qualidade (cada vídeo só sai se passar)
- Duração 55–65 s. Uma ideia por vídeo. A tela mostra o que a voz diz, no momento em que diz.
- Todo número na tela bate com o sistema rodando (confira por API ou pela própria tela, não de memória).
- Português do Brasil correto: R$ 1.234,56 · datas dd/mm/aaaa · acentos. Sem jargão que o produtor não use;
  quando precisar do termo (competência, caixa, DRE), explique em meia frase.
- Imagem: 1920×1080, sem faixa "AMBIENTE DE TESTE", sem selo do modo dev, sem nome de fazenda real, sem
  mensagem de erro, sem janela de carregamento, datas em dd/mm/aaaa, cursor visível.
- Áudio: voz nítida, sem corte de palavra, volume uniforme, sem música que cubra a fala.
- Legenda na tela com o texto falado resumido (acessibilidade e vídeo sem som).
- Entrega por vídeo: o `.mp4`, o roteiro final, o texto falado, a lista de cliques e a de números conferidos.

## 4. Antes de tudo, me pergunte (uma mensagem só, objetiva)
1. Autoriza o uso da conta HeyGen conectada e o gasto de crédito de **áudio**?
2. Mantemos o sino e o botão "News" visíveis no canto superior direito, ou escondemos?
3. Formato: só 16:9, ou também 9:16 para celular?
4. Quer que eu corrija agora a Capa (nome da fazenda fixo), o cabeçalho público e a acessibilidade dos rótulos, ou
   só contorne na gravação? (Se for corrigir, **abra PR separado**, não misture com os vídeos.)

## 5. Ao terminar cada sessão
Grave a nota datada em `04_CowData/Milk/Sessoes/AAAA-MM-DD_tutoriais_video_<assunto>.md` (o que mudou, o que ficou
de fora, armadilhas) e, se surgiu regra generalizável, registre-a junto. Informe o que ficou "não verificado".
