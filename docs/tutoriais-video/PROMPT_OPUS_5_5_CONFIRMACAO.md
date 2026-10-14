# Prompt de CONFIRMAÇÃO para o Opus 5.5 (copiar e colar)

> Cole tudo abaixo da linha numa sessão nova do Claude Code, com o modelo **Opus 5.5**, aberta no repositório
> `rodartepradoadvogados/fazendaapp`. Quando o Opus responder "PRONTO PARA O PROMPT DE PRODUÇÃO", envie o prompt de
> produção com o seu roteiro.

---

Você é o Opus 5.5 e vai produzir, nas próximas mensagens, peças de Instagram (stories e reels, vertical 9:16,
carrossel animado) que ensinam o **sistema financeiro do CowData**, com telas reais, motion e a voz do Jairo.
**Esta mensagem é só a etapa de ENTENDIMENTO. Não produza nada:** nenhum roteiro, áudio, vídeo, gravação final,
commit, PR ou publicação, e **nenhuma geração no HeyGen**.

## 1. Pegue o código certo
```bash
git fetch origin claude/farm-app-access-bikeej && git checkout claude/farm-app-access-bikeej
```
Se `docs/tutoriais-video/` não existir depois disso, **pare e me avise**.

## 2. Leia, nesta ordem (links na branch `claude/farm-app-access-bikeej`)
Base: https://github.com/rodartepradoadvogados/FazendaApp/tree/claude/farm-app-access-bikeej

1. Regras do projeto: `AGENTS.md` — https://github.com/rodartepradoadvogados/FazendaApp/blob/claude/farm-app-access-bikeej/AGENTS.md
2. **Registro da preparação (o principal)** — https://github.com/rodartepradoadvogados/FazendaApp/blob/claude/farm-app-access-bikeej/docs/tutoriais-video/REGISTRO_PREPARACAO.md
3. **Prompt-base de produção (regras e fases)** — https://github.com/rodartepradoadvogados/FazendaApp/blob/claude/farm-app-access-bikeej/docs/tutoriais-video/PROMPT_OPUS_5_5.md
4. Ambiente de demonstração e modelo de gravação — https://github.com/rodartepradoadvogados/FazendaApp/tree/claude/farm-app-access-bikeej/docs/tutoriais-video/ambiente-demo
5. O produto: `README.md`, `CONTEXTO_PROJETO_FAZENDA.md`, `PRODUCT.md`, `DESIGN.md`, e do financeiro
   `docs/financeiro-regras-v2.md` e `docs/financeiro-fechamento-conciliacao.md` (todos em `docs/` ou na raiz da mesma branch).
6. Cofre (Google Drive, conta rodartepradoadvogados@gmail.com), se o conector estiver disponível:
   - Mapa-mestre `00_AGENTES.md` (leitura obrigatória): https://drive.google.com/file/d/1wZk9_lN7iPggCg7Fc4D3992AshnbjFTf/view
   - Nota da preparação (14/10/2026): https://drive.google.com/file/d/1hU9H14RGnJf_SwLMgmOsAz5zJqxzjIu4/view
   - Pasta onde você grava as notas (`04_CowData/Milk/Sessoes`): https://drive.google.com/drive/folders/1sRKB_juY7D762nN0kbOaQkK_TXUm4284
   Sem o conector, diga que não alcançou o cofre (não invente caminho).

## 3. Decisões do Jairo que valem para tudo (não pergunte de novo)
- Voz: **"Voz Jairo Rodarte"** (`b7ab856295e947bab979a893cad2b326`), a do avatar dele, na conta HeyGen conectada
  (autorizada, conta correta). **Só áudio**; nenhum vídeo ou avatar no HeyGen.
- Sino e botão **News** ficam visíveis. A faixa vermelha de teste **não** aparece.
- Formato: **Instagram stories e reels, 9:16, 1080×1920, carrossel animado**. O Jairo já tem um roteiro breve e
  vai enviá-lo no prompt de produção.
- Rótulos de formulário sem `for`/`id`, Capa e cabeçalho público com o nome da fazenda real: **não corrigir**,
  só contornar na gravação (login fora da gravação; nunca gravar a Capa).
- Telas vazias ficam vazias (Orçamento, Patrimônio, Cartão, Folha, Faturas, Compra/venda de animais, Pedidos,
  Documentos): **não semear dados para elas**.
- Dados 100% fictícios ("Fazenda Vale Verde"). Nada da fazenda real, nenhum CSV da raiz, nenhuma senha ou token.
- Aprovação é do Jairo: nenhuma nota ou peça vale sem `status: aprovado` dele.

## 4. Prove que o ambiente sobe (a única coisa que você executa agora)
```bash
bash docs/tutoriais-video/ambiente-demo/rebuild.sh --front
```
Leva alguns minutos. Depois confira os números da tabela do REGISTRO §4 (DRE do mês anterior, saldos, conciliação,
custo por litro) e diga se bateram. Se algo falhar, **relate o erro e pare**: não conserte código do produto e não
mexa em nada fora de `docs/tutoriais-video/`. Não grave vídeo agora.

## 5. O que quero de volta (uma resposta só, objetiva)
1. **Entendimento em suas palavras** (até 15 linhas): o que é o produto financeiro, o que vamos produzir, formato,
   voz, regras de segredo/LGPD e o que **não** pode aparecer na imagem.
2. **O que está verificado e o que não está** (tabela curta, a partir do REGISTRO §2), incluindo o resultado do passo 4.
3. **Riscos e dúvidas reais** sobre o formato carrossel animado 9:16 com telas de um site feito para desktop
   (REGISTRO §8: opções A e B). Diga qual você recomendaria e por quê, **sem decidir sozinho**.
4. **O que você precisa receber do Jairo** no prompt de produção para começar sem perguntar (roteiro, ordem das
   peças, estilo do texto na tela, etc.).
5. A linha final, exatamente assim, só se tiver entendido tudo e o ambiente tiver subido:
   **PRONTO PARA O PROMPT DE PRODUÇÃO**
   Se algo bloquear, escreva **NÃO ESTOU PRONTO** e o motivo.
