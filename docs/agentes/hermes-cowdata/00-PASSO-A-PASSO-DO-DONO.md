# Hermes Agent + CowData — passo a passo do dono

Objetivo: o mesmo agente (Hermes, na sua VPS, com OpenRouter) responde no **Telegram**, no **Hermes Desktop** e o chat do **CowData** volta a funcionar — sempre **somente consultando** os dados, nunca escrevendo.

## Como as peças se encaixam

- **Chat do CowData (site e app):** o backend passa a falar com o OpenRouter (em vez da Anthropic, que está sem saldo). Continua com as ferramentas de leitura, as permissões de cada usuário e a aba "Ensinamentos" para treinar.
- **Hermes (Telegram e Desktop):** consulta o CowData por uma **API de leitura** nova, protegida por um token só seu. Essa API só tem consultas (GET), roda em transação somente leitura no banco e registra cada chamada.
- **Treino centralizado:** as instruções do agente e os "Ensinamentos" do CowData ficam num lugar só; o Hermes lê de lá.

## Regras de ouro (valem para todas as etapas)

1. **Nunca cole chave, token ou senha no chat comigo.** Cole só no Railway, na VPS ou no BotFather.
2. Guarde cada segredo num gerenciador de senhas (ou num arquivo seu, fora do projeto).
3. Cada serviço tem a sua chave própria, para poder cortar uma sem derrubar as outras.
4. Para cortar o acesso do Hermes aos dados a qualquer momento: apague `AGENTE_API_TOKEN` no Railway.

---

## ETAPA 1 — Reativar o chat do CowData (OpenRouter)

**Pré-requisito:** eu avisar que o código novo está no ar (o deploy leva ~3 min). Você pode preparar a chave antes.

1. Entre em **openrouter.ai** → **Keys** → **Create Key**.
2. Nome: `cowdata-chat`. Defina um **limite de crédito** (sugestão: US$ 10 por mês). Não reaproveite a chave do Hermes.
3. Copie a chave (começa com `sk-or-`) e guarde.
4. Escolha o modelo: na página de modelos do OpenRouter, filtre os que aceitam **tools** (chamada de ferramentas). Use o mesmo que o seu Hermes usa, se ele aceitar tools. Anote o nome exato (ex.: `anthropic/claude-sonnet-4.5`).
5. No **Railway** → projeto `ravishing-smile` → **production** → serviço **FazendaApp** → **Variables**, crie:
   - `ASSISTENTE_PROVEDOR` = `openrouter`
   - `OPENROUTER_API_KEY` = a chave do passo 3
   - `ASSISTENTE_MODELO` = o modelo do passo 4
6. Clique em **Deploy** quando o Railway oferecer. Espere ~3 min.
7. **Teste:** abra o CowData, clique no botão dourado do assistente e pergunte "Quantos animais em lactação temos?". Se aparecer erro, a mensagem agora diz o motivo (saldo, chave, limite). Me mande o texto da mensagem.

## ETAPA 2 — Liberar a leitura para o Hermes

1. Na janela do **Ubuntu** (WSL), gere um token forte:
   `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`
2. Copie o resultado. No Railway (mesmo serviço, **Variables**), crie:
   - `AGENTE_API_TOKEN` = o token
   - `AGENTE_FAZENDA_ID` = `1`
   - `AGENTE_IPS_PERMITIDOS` = `143.95.160.39` (só a sua VPS consegue chamar)
3. **Deploy**. Guarde o token também para a Etapa 3.
4. **Teste (na VPS, depois da Etapa 3.1):** o script `testar.sh` desta pasta confirma que o token funciona e que escrever é impossível.

## ETAPA 3 — Instalar a ponte (MCP) na VPS

1. No PowerShell do Windows: `ssh -p 22022 -i $env:USERPROFILE\.ssh\id_ed25519 root@143.95.160.39`
2. Atualize o projeto no seu Windows (`git pull` em `C:\Users\jairo\FazendaApp`) e envie a pasta `docs/agentes/hermes-cowdata` para a VPS com `scp`. Os comandos exatos (com caminhos) estarão no arquivo `CONFIG-HERMES.md`, gerado junto com o código.
3. Na VPS, instale as dependências da ponte e guarde o token em arquivo com permissão restrita (`chmod 600`). Nunca no histórico de comandos.
4. Rode `testar.sh`. Resultado esperado: rotas de consulta respondem; tentativa de escrita falha; token errado dá 401.

## ETAPA 4 — Configurar o Hermes

1. Registre a ponte MCP do CowData na configuração do Hermes (trecho pronto em `CONFIG-HERMES.md`).
2. Carregue as instruções do agente (`INSTRUCOES-AGENTE.md`): persona, vocabulário, regras de somente leitura e limites.
3. Reinicie o Hermes e confirme que ele lista as ferramentas do CowData.

## ETAPA 5 — Bot do Telegram

1. No Telegram, abra **@BotFather** → `/newbot` → escolha nome e username (terminando em `bot`). Guarde o token.
   - **Importante:** crie um bot **novo**. O CowData já usa outro bot (variável `TELEGRAM_BOT_TOKEN` no Railway) para os fluxos dele; dois sistemas no mesmo bot se atrapalham.
2. Descubra o seu número de usuário: converse com **@userinfobot** e anote o `Id`. Faça o mesmo para cada pessoa que for usar.
3. Na VPS, configure o gateway do Hermes com o token do bot e com a **lista de usuários permitidos** (só esses números). Isso é essencial: o link do bot é público, e sem a lista qualquer pessoa poderia conversar com ele.
4. Inicie o gateway e mande "oi" ao bot. Quem não estiver na lista deve ser ignorado.

## ETAPA 6 — Hermes Desktop

1. Aponte o Hermes Desktop para o Hermes da VPS (como você já usa).
2. Pergunte algo do CowData e confira que a resposta vem com dados reais.

## ETAPA 7 — Testes de aceitação (10 minutos)

Faça estas perguntas no Telegram e no Desktop:
- "Quantos animais temos e quantos em lactação?"
- "O que vence na agenda hoje?" · "Como está o estoque de vacinas?"
- "Quantos animais estão na lista de espera da vacina?"
- **Limites:** "Apague o lote 3." / "Lance uma vacina no animal 1234." → ele deve **recusar** e dizer que só consulta.
- **Fora do escopo:** "Qual a previsão do tempo?" → recusar ou desviar educadamente.
- Confira em Concluídos/Auditoria do CowData que **nada foi gravado**.

## ETAPA 8 — Treinar e impor limites no dia a dia

- **Instruções fixas** (tom, regras, o que nunca fazer): edite `INSTRUCOES-AGENTE.md` e recarregue no Hermes.
- **Conhecimento da fazenda** (regras de manejo, siglas, metas): cadastre em **CowData → assistente → Ensinamentos**. O Hermes lê isso sempre.
- **Corrigir resposta errada:** diga ao agente o que estava errado; se for regra permanente, vira um Ensinamento.
- Revise o que o agente respondeu uma vez por mês e o gasto no OpenRouter.

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| Chat do CowData diz "indisponível" | Admin vê o motivo na aba Ensinamentos (saldo, chave, limite). Confira o OpenRouter. |
| Hermes não acha os dados | Rode `testar.sh`; confira `AGENTE_API_TOKEN` e o IP em `AGENTE_IPS_PERMITIDOS`. |
| Suspeita de vazamento do token | Apague `AGENTE_API_TOKEN` no Railway (corta tudo na hora) e gere outro. |
| Gasto estranho | Reduza o limite da chave no OpenRouter. |

## Fora desta primeira entrega

O chat do site responder **pelo próprio Hermes** (em vez de direto pelo OpenRouter) exige expor o servidor de API do Hermes na internet com HTTPS e definir como passar as permissões de cada usuário. Fica para depois que Telegram e Desktop estiverem estáveis.
