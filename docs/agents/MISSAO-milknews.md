# MISSÃO: MilkNews passa a usar o Firecrawl (matéria diária + catálogo NAAB)

> **Destinatário:** o **robô MilkNews** (Routine do Claude Code, repositório
> `rodartepradoadvogados/FazendaApp`, skill `.claude/skills/milknews/SKILL.md`).
> **Quem enviou:** o dono do CowData (rodartepradoadvogados@gmail.com). Ele acompanha só por você:
> **você executa e guia o dono** em cada passo que só ele pode fazer.
>
> Documento escrito em 25/09/2026.

---

## 1. O que muda para você

| # | Mudança | Especificação (já está no repositório) |
|---|---|---|
| 1 | Coleta de cotações, notícias e conteúdo técnico **pelo Firecrawl** (lendo a página de verdade, inclusive PDF e sites que bloqueiam acesso automatizado) | `docs/agents/milknews-firecrawl.md` |
| 2 | **Matéria diária** (decisão do dono): 1 a 3 posts por dia com pauta verificada, nunca forçando | idem, seção 5 |
| 3 | Nova atribuição: **catálogo de touros NAAB**, consultando as provas oficiais pelo Firecrawl e atualizando o banco do Painel CowData, **só depois** de uma fase de viabilidade aprovada | `docs/agents/naab-catalogo-firecrawl.md` |

**Leia as duas especificações inteiras antes de começar.** Este documento diz **em que ordem**
trabalhar e **quando parar para falar com o dono**.

## 2. Regras que não mudam
- Todas as regras "inegociáveis" do `SKILL.md`: 2 fontes independentes por número, divergência não
  publica, snippet não é fonte, paráfrase, formato do lote, nunca editar lote antigo, e o teste de
  formato `backend/tests/test_milknews_lotes_formato.py` verde.
- **Segredos:** nunca imprima, grave, commite ou coloque em PR o valor de `FIRECRAWL_API_KEY`,
  senha ou token. Nunca peça ao dono para colar valor de segredo no chat. Oriente-o a colocar a
  variável no ambiente da Routine.

## 3. Como falar com o dono
Em cada **ponto de parada (🛑)**: diga o que foi feito, o que precisa dele (passos numerados, dizendo
onde clicar) e a pergunta objetiva. Depois **espere a resposta**. Sem jargão de código.

---

## Etapa 0: chave do Firecrawl no seu ambiente 🛑
Verifique `test -n "$FIRECRAWL_API_KEY"` (sem imprimir o valor). Se faltar, guie:
> 1. claude.ai → Claude Code → **Routines** → MilkNews → veja qual **Environment** ela usa.
> 2. claude.ai → Claude Code → **Environments** → esse ambiente → **Environment variables**.
> 3. Adicione `FIRECRAWL_API_KEY` com a chave do Firecrawl (a mesma do Railway) → salvar.
> 4. Me avise. A próxima execução já enxerga a chave.

Com a chave presente, consulte o saldo (`/v2/team/credit-usage`) e informe ao dono.

## Etapa 1: atualizar a sua própria skill e o prompt da Routine 🛑
**Fato apurado em 26/09/2026:** a Routine "Milknews: matéria diária" (08:00 UTC, sessão nova a cada
disparo) **não invoca a skill**. O prompt dela traz instruções próprias:
- pesquisa por WebSearch/WebFetch;
- 1 a 3 matérias por dia;
- **abre o PR e mergeia sozinha (hands-off)**.

Por isso as duas mudanças abaixo são necessárias.

1. **🛑 Confirme com o dono a política de merge:**
   > "Hoje a Routine abre o PR do lote e **mergeia sozinha**. Mantemos assim (recomendado: o lote
   > passa pelo teste de formato antes, e o post só aparece depois do 'revisado final'), ou prefere
   > que eu só abra o PR?"
2. Com a resposta, abra um PR que:
   - atualize `.claude/skills/milknews/SKILL.md`:
     - **frequência diária** (1 a 3 posts, nunca forçar; dia sem pauta verificada = sem post, com
       explicação);
     - **coleta via Firecrawl** conforme `docs/agents/milknews-firecrawl.md` (com referência
       explícita ao arquivo);
     - **política de merge** escolhida;
     - **atribuição NAAB** apontando para `docs/agents/naab-catalogo-firecrawl.md`;
   - ajuste `docs/milknews-rotina-publicacao.md` para ficar igual ao `SKILL.md`.
3. Esse PR (de instrução, não de lote) **sempre** é mergeado pelo dono. Mande o link e peça
   "confira e mergeie".
4. **🛑 Depois do merge, guie o dono a trocar o prompt da Routine** (quem clica é ele):
   > claude.ai/code → **Routines** → "Milknews: matéria diária" → editar → apague o prompt atual e
   > cole:
   >
   > "Rode o ciclo diário do robô MilkNews no repositório rodartepradoadvogados/FazendaApp
   > seguindo **integralmente** a skill `.claude/skills/milknews/SKILL.md` (invoque pela Skill tool;
   > se não aparecer, leia o arquivo) e `docs/agents/milknews-firecrawl.md`. Use o Firecrawl
   > (variável de ambiente FIRECRAWL_API_KEY) para ler as fontes. Tudo em português do Brasil com
   > acentuação completa. Sessão nova a cada disparo."
   >
   > Salve. Não crie Routine nova e não apague a atual: só troque o prompt.

   Ofereça-se também para atualizar da mesma forma a Routine semanal "Milknews: checar fonte do
   simulador de preço do leite": ela hoje evita o WebFetch por causa de 403, e o Firecrawl resolve
   isso.

## Etapa 2: rotina diária com Firecrawl
A partir do merge da Etapa 1, cada execução segue `docs/agents/milknews-firecrawl.md`:
cotações (Cepea, Notícias Agrícolas, USDA AMS, GDT), notícias, conteúdo técnico; teto de 25
chamadas; 2 fontes lidas por número; lote validado pelo `pytest`; PR listando as URLs por número.

**🛑 Na primeira execução, avise o dono:**
> "Os posts do robô só aparecem em /news depois que alguém da equipe CowData marca **'revisado
> final'** em cada matéria (Painel CowData → News → matérias). Quem vai fazer isso todo dia?"

## Etapa 3: catálogo NAAB, só viabilidade primeiro 🛑
1. **Preparação já feita pelo dono em 26/09/2026. Só confira, sem imprimir valores:**
   - usuário `robo-milk-news` criado no Painel CowData (área Cadastros + "editar touros NAAB"),
     com login testado pelo dono;
   - no seu ambiente: `COWDATA_API_URL` (= `https://fazendaapp-production.up.railway.app`, o
     backend que o site usa), `COWDATA_ROBO_USUARIO` e `COWDATA_ROBO_SENHA`.

   Teste `POST $COWDATA_API_URL/auth/login` e `GET $COWDATA_API_URL/painel-cowdata/touros`.
   - Se o login falhar, peça ao dono para conferir usuário e senha no ambiente (nomes exatos, com
     `COWDATA` junto).
   - Se a lista de touros der 403, peça para marcar a área **Cadastros** no usuário.
   - **Recomende ao dono tirar do usuário o que ele não usa** ("editar News" e áreas além de
     Cadastros): o MilkNews publica por PR, não pelo painel.
2. Execute **apenas a Fase 0** de `docs/agents/naab-catalogo-firecrawl.md` (só leitura; nenhuma
   escrita no banco).
3. **🛑 Entregue o relatório de viabilidade** (viável / parcial / inviável; quais fontes servem
   para quais campos; créditos por atualização; riscos) e pergunte: "Posso seguir para a Fase 1?"
4. **Só com "pode seguir"**: passe a verificar **uma vez por semana** se saiu rodada nova de provas
   (CDCB: abril, agosto, dezembro) e, quando sair, atualize os touros conforme a Fase 1 (upsert via
   `/painel-cowdata/touros/importar`, 2 fontes por touro, nada apagado). Mande relatório a cada
   atualização.

## Etapa 4: resumo ao dono
Quando as Etapas 0 a 3 estiverem concluídas (ou a Etapa 3 estiver parada, esperando decisão),
mande um resumo:
- o que ficou ligado;
- a política de merge escolhida;
- quem marca "revisado final";
- o saldo de créditos;
- o status do NAAB.

Daí em diante, siga a rotina normalmente.
