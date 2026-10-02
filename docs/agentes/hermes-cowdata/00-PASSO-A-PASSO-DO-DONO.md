# Hermes Agent + CowData — passo a passo do dono (versão 2, atualizada em 02/10/2026)

**Objetivo:** o mesmo agente (Hermes, na sua VPS, com OpenRouter) responde no **Telegram**, no **Hermes Desktop** e o chat do **CowData** volta a funcionar — sempre **somente consultando** os dados, nunca escrevendo.

## Como as peças se encaixam

- **Chat do CowData (site e app):** o backend fala com o OpenRouter. Continua com as ferramentas só de leitura, as permissões de cada usuário e a aba **Ensinamentos** para treinar.
- **Hermes (Telegram e Desktop):** consulta o CowData por uma **API de leitura**, protegida por um token só seu. Só tem consultas (GET), roda em transação somente leitura no banco e registra cada chamada.
- **Treino centralizado:** instruções do agente e "Ensinamentos" do CowData ficam num lugar só; o Hermes lê de lá.

## Regras de ouro

1. **Nunca cole chave, token ou senha no chat.** Cole só no Railway, na VPS ou no BotFather.
2. Guarde cada segredo num gerenciador de senhas.
3. Cada serviço tem a sua chave própria, para cortar uma sem derrubar as outras.
4. **Cortar o acesso do Hermes aos dados a qualquer momento:** apague `AGENTE_API_TOKEN` no Railway e aplique.
5. **Saiba em qual janela você está.** `PS C:\Users\jairo>` é o **Windows** (comandos `scp`, `git`, `$env:…`, `C:\…`). `[root@vpsbr-…]#` é a **VPS** (comandos `python3`, `chmod`, `./testar.sh`). Colar um comando na janela errada é o erro mais comum.
6. **No Railway, mudanças de variáveis ficam "pendentes" até você clicar em Deploy.** Criar a variável não basta: o servidor só passa a usá-la depois do Deploy.

---

## ETAPA 1 — Chat do CowData por OpenRouter  ✅ (feita; confira os detalhes)

1. **openrouter.ai › Keys › Create Key**, nome `cowdata-chat`, com limite de crédito mensal. Copie a chave (`sk-or-…`).
2. No **Railway** (projeto `ravishing-smile` › **production** › serviço **FazendaApp** › **Variables**), crie estas variáveis (nomes exatos, em maiúsculas):
   - `ASSISTENTE_PROVEDOR` = `openrouter`
   - `OPENROUTER_API_KEY` = a chave do passo 1
   - `ASSISTENTE_MODELO` = `nvidia/nemotron-3-ultra-550b-a55b:free` (o modelo que você escolheu; gratuito, aceita ferramentas)
   - `ASSISTENTE_MODELOS_RESERVA` = `qwen/qwen3.8-flash` (reserva automática quando o principal estiver sobrecarregado; **pago, mas muito barato** — precisa de crédito na conta do OpenRouter)
3. Clique em **Deploy** nas mudanças pendentes e espere ~2 minutos.
4. No OpenRouter, em **Credits**, adicione um pequeno saldo (por exemplo US$ 5) para o modelo reserva funcionar.
5. **Teste:** dê `Ctrl + F5` no CowData, clique no botão dourado do assistente e pergunte "Quantos animais em lactação temos?".

**Se o chat falhar**, o administrador vê o motivo na própria mensagem e na aba Ensinamentos (status do motor de IA):
- *"Service temporarily overloaded" / HTTP 503:* o modelo gratuito está sobrecarregado. O sistema tenta de novo e usa o reserva.
- *saldo/limite:* falta crédito na conta do OpenRouter ou o limite da chave acabou.
- *chave:* chave errada. Confira o nome `OPENROUTER_API_KEY`.
- *modelo:* nome do modelo errado em `ASSISTENTE_MODELO`.

**Privacidade:** modelos gratuitos podem ter os pedidos registrados pelo provedor, e as perguntas levam dados da fazenda. Para uso de verdade, prefira um modelo pago como principal (basta trocar `ASSISTENTE_MODELO`; não precisa mexer em código).

## ETAPA 2 — Liberar a leitura para o Hermes

1. Na janela do **Ubuntu (WSL)**, gere um token forte:
   ```
   python3 -c "import secrets; print(secrets.token_urlsafe(48))"
   ```
2. No **Railway** (mesmo serviço, **Variables**), crie:
   - `AGENTE_API_TOKEN` = o token gerado
   - `AGENTE_FAZENDA_ID` = `1`
   - `AGENTE_IPS_PERMITIDOS` = `143.95.160.39` (só a sua VPS consegue chamar)
3. Clique em **Deploy** e espere terminar.
4. Guarde o token também para a Etapa 3 (você vai colá-lo na VPS).

**Se o teste da Etapa 3 der 403:** o Railway pode não entregar o IP real da VPS. Apague só `AGENTE_IPS_PERMITIDOS`, aplique o Deploy e teste de novo. O token sozinho já protege.

## ETAPA 3 — Instalar a ponte (MCP) na VPS

### 3.1 Enviar a pasta da ponte para a VPS (no **PowerShell do Windows**)
```
cd C:\Users\jairo\FazendaApp
git pull
scp -P 22022 -i $env:USERPROFILE\.ssh\id_ed25519 -r C:\Users\jairo\FazendaApp\docs\agentes\hermes-cowdata root@143.95.160.39:/opt/cowdata-mcp
```
O `scp` termina listando os arquivos copiados. (Se repetir o envio depois e a pasta já existir, os arquivos vão para dentro de `/opt/cowdata-mcp/hermes-cowdata`; nesse caso copie por cima ou avise.)

### 3.2 Entrar na VPS (ainda no PowerShell do Windows)
```
ssh -p 22022 -i $env:USERPROFILE\.ssh\id_ed25519 root@143.95.160.39
```
O prompt passa a mostrar `[root@vpsbr-…]#`. **Os comandos a seguir são todos na VPS.**

### 3.3 Instalar um Python novo e as dependências
O Python padrão da VPS é antigo (3.6) e a biblioteca da ponte exige 3.10 ou mais novo. Instale o 3.11 **ao lado** do atual, sem trocar o do sistema:
```
dnf install -y python3.11
python3.11 --version
cd /opt/cowdata-mcp
rm -rf venv
python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```
No fim deve aparecer "Successfully installed…" com `mcp` e `httpx`. Se `python3.11` não existir, use `dnf install -y python3.12` e troque `python3.11` por `python3.12`.

### 3.4 Guardar o token em arquivo, sem aparecer na tela
```
umask 077
read -rsp "Cole o token e tecle Enter: " T
printf '%s\n' "$T" > ~/.cowdata-agente-token
unset T
chmod 600 ~/.cowdata-agente-token
chmod +x run-mcp-cowdata.sh testar.sh
```
Cole o token (o mesmo do `AGENTE_API_TOKEN`) e aperte Enter. Nada aparece enquanto você cola, e isso é normal. O arquivo fica legível só pelo dono, e o token não vai para o histórico do terminal nem para a configuração do Hermes.

### 3.5 Testar
```
./testar.sh
```
Todos os itens têm que dar **OK**: token aceito, rotas de consulta respondendo e escrita impossível.

| Resultado | O que significa |
|---|---|
| 404 em tudo | `AGENTE_API_TOKEN` não foi aplicado no Railway (falta Deploy) ou o deploy não terminou |
| 401 | o token do arquivo é diferente do Railway; refaça o 3.4 |
| 403 | checagem de IP; apague `AGENTE_IPS_PERMITIDOS` no Railway, aplique e teste de novo |
| 429 | passou de 60 consultas por minuto; espere um pouco |

## ETAPA 4 — Configurar o Hermes (na VPS)

1. **Registrar a ponte.** Edite `~/.hermes/config.yaml` e acrescente (se já existir `mcp_servers`, só inclua o bloco `cowdata` dentro dele):
   ```yaml
   mcp_servers:
     cowdata:
       command: "/opt/cowdata-mcp/run-mcp-cowdata.sh"
       args: []
       timeout: 60
       connect_timeout: 30
   ```
   O script lê o token do arquivo do passo 3.4, então não há segredo no YAML.
2. **Instruções do agente.** Faça backup do arquivo atual e copie as instruções novas:
   ```
   cp ~/.hermes/SOUL.md ~/.hermes/SOUL.md.bak 2>/dev/null
   cp /opt/cowdata-mcp/INSTRUCOES-AGENTE.md ~/.hermes/SOUL.md
   ```
   Se esse Hermes também faz outras coisas para você, **mescle** o conteúdo em vez de substituir.
3. **Recarregar.** No chat do Hermes digite `/reload-mcp` (ou reinicie o gateway).
4. Confira que o Hermes lista as ferramentas do CowData (`consultar_indicadores`, `buscar_animal`, `consultar_estoque`, `listar_lotes` e outras, mais `instrucoes_cowdata`).

## ETAPA 5 — Bot do Telegram

1. No Telegram, abra **@BotFather** › `/newbot` › escolha nome e username (terminando em `bot`). Guarde o token.
   - **Crie um bot novo.** O CowData já usa outro bot nos fluxos dele (variável `TELEGRAM_BOT_TOKEN` no Railway). Não troque o valor dessa variável.
2. Converse com **@userinfobot** e anote o seu `Id` numérico. Faça o mesmo para cada pessoa que for usar.
3. Na VPS, edite `~/.hermes/.env` e acrescente:
   ```
   TELEGRAM_BOT_TOKEN=<token do BotFather>
   TELEGRAM_ALLOWED_USERS=<seu id>,<id de outra pessoa>
   ```
   A lista de usuários permitidos é **obrigatória na prática**: o link do bot é público, e sem a lista qualquer pessoa poderia conversar com ele.
4. Configure e inicie o gateway: `hermes gateway setup` (escolha Telegram) e depois `hermes gateway`.
5. Mande "oi" ao bot. Quem não estiver na lista deve ser ignorado.
6. Para o gateway continuar rodando depois que você fechar o terminal, ele precisa virar um serviço. Peça-me os comandos quando chegar aqui.

## ETAPA 6 — Hermes Desktop

O Desktop deve usar o **mesmo** Hermes da VPS e herda o MCP e o `SOUL.md`. Se o seu Desktop rodar um Hermes local, repita as Etapas 3 e 4 nele. Pergunte algo do CowData e confira que a resposta vem com dados reais.

## ETAPA 7 — Testes de aceitação (10 minutos)

No Telegram e no Desktop:
- "Quantos animais temos e quantos em lactação?"
- "O que vence na agenda hoje?" · "Como está o estoque de vacinas?"
- **Limites:** "Apague o lote 3." / "Lance uma vacina no animal 1234." → ele deve **recusar** e dizer que só consulta.
- **Fora do escopo:** "Qual a previsão do tempo?" → recusar ou desviar educadamente.
- **Ainda não responde:** lista de espera, agendamentos e concluídos do preventivo não têm ferramenta de consulta ainda. O agente deve indicar Protocolos › Aplicar.
- Confirme no CowData que **nada foi gravado**.

## ETAPA 8 — Treinar e impor limites no dia a dia

- **Instruções fixas** (tom, regras, o que nunca fazer): edite `INSTRUCOES-AGENTE.md`, copie de novo para `~/.hermes/SOUL.md` e use `/reload-mcp`.
- **Conhecimento da fazenda** (regras de manejo, siglas, metas): cadastre em **CowData › assistente › Ensinamentos**. O Hermes lê isso pela ferramenta `instrucoes_cowdata`. Se ele não a chamar sozinho, peça "leia as instruções do CowData" no começo da conversa.
- **Resposta errada:** diga ao agente o que estava errado; se for regra permanente, vira um Ensinamento.
- **Esconder o financeiro do Telegram:** no Railway, defina `AGENTE_MODULOS` sem `financeiro` (ex.: `indicadores,rebanho,agenda,estoque,sanidade,reproducao`) e aplique.
- Revise as respostas e o gasto no OpenRouter uma vez por mês.

## Se algo der errado

| Sintoma | O que fazer |
|---|---|
| Chat do CowData diz "indisponível" | O administrador vê o motivo na mensagem e na aba Ensinamentos. Confira o OpenRouter (saldo, limite, modelo). |
| Variável nova no Railway não faz efeito | Falta clicar em **Deploy** nas mudanças pendentes. |
| Hermes não acha os dados | Rode `./testar.sh`; confira `AGENTE_API_TOKEN` e `AGENTE_IPS_PERMITIDOS`. |
| Hermes não lista as ferramentas | `/reload-mcp`; rode `/opt/cowdata-mcp/run-mcp-cowdata.sh` na mão e veja a mensagem de erro. |
| Suspeita de vazamento do token | Apague `AGENTE_API_TOKEN` no Railway (corta tudo na hora) e gere outro. |
| Gasto estranho no OpenRouter | Reduza o limite da chave no OpenRouter. |

## Fora desta primeira entrega

O chat do site responder **pelo próprio Hermes** exige expor o servidor de API do Hermes na internet com HTTPS e definir como repassar as permissões de cada usuário. Fica para depois que Telegram e Desktop estiverem estáveis.

## Onde você está agora

- ✅ Etapas 1 e 2 (variáveis no Railway).
- ✅ Etapa 3 até o item 3.3 (Python 3.11 e dependências instaladas).
- ➡️ **Próximo:** itens 3.4 (guardar o token) e 3.5 (`./testar.sh`).
