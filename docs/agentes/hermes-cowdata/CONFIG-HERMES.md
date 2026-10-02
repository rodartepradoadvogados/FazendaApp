# Configurar o Hermes para consultar o CowData (somente leitura)

Legenda: **[doc]** = conferido na documentação oficial do Hermes (hermes-agent.nousresearch.com/docs, páginas de MCP, Telegram e Personality, consultadas em 02/10/2026);
**[a confirmar]** = não consegui verificar — teste na VPS antes de confiar. **[testado]** = executado por nós contra o backend de teste.

## 0. Variáveis de ambiente (nomes exatos)

**No Railway (backend CowData)**

| Variável | Para quê |
|---|---|
| `AGENTE_API_TOKEN` | Liga a API de leitura (`/agente/*`). Mínimo 32 caracteres. **Sem ela, tudo responde 404.** Apagar = corta o Hermes na hora. |
| `AGENTE_FAZENDA_ID` | Fazenda que o agente enxerga (padrão `1`). Fixa; o agente não escolhe. |
| `AGENTE_IPS_PERMITIDOS` | Opcional. IPs (separados por vírgula) que podem chamar. Ex.: o IP da VPS. |
| `AGENTE_RATE_LIMIT_POR_MIN` | Opcional. Chamadas por minuto por token (padrão `60`). |
| `AGENTE_MAX_BYTES` | Opcional. Teto de tamanho da resposta (padrão `100000`). |
| `AGENTE_MODULOS` | Opcional. Restringe as ferramentas por módulo (ex.: `rebanho,estoque,agenda`). Vazio = todas. Módulos: indicadores, rebanho, agenda, financeiro, estoque, sanidade, reproducao, analise, producao, pedidos. As ferramentas por período seguem o módulo da área (ex.: `consultar_contas_financeiras` = `financeiro`, `consultar_pedidos` = `pedidos`, `consultar_producao_leite` = `producao`, taxa de concepção por período = `reproducao` ou `analise`). |
| `ASSISTENTE_PROVEDOR` / `OPENROUTER_API_KEY` / `ASSISTENTE_MODELO` | Chat do site/app via OpenRouter (independente da API de leitura). |

**Na VPS (ponte MCP)**

| Variável | Para quê |
|---|---|
| `COWDATA_API_URL` | `https://fazendaapp-production.up.railway.app` |
| `COWDATA_AGENTE_TOKEN` | Mesmo valor de `AGENTE_API_TOKEN` (guardado em arquivo `chmod 600`, ver abaixo) |
| `COWDATA_TIMEOUT` | Opcional, segundos por consulta (padrão 30) |
| `COWDATA_TOKEN_FILE` | Opcional, caminho do arquivo do token (padrão `~/.cowdata-agente-token`) |

## 1. Gerar o token e ativar no Railway

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```
Cole o resultado **só** no Railway (`AGENTE_API_TOKEN`) e no arquivo da VPS (passo 2). Não mande por chat, e-mail ou commit.

> Atenção ao `AGENTE_IPS_PERMITIDOS` atrás do proxy do Railway: o backend usa a entrada **mais à direita** do `X-Forwarded-For` (a que o proxy acrescenta; a da esquerda pode ser forjada).
> **[a confirmar]** se o proxy da Railway entrega o IP real do cliente nesse cabeçalho. Teste: com a lista preenchida, `testar.sh` da VPS deve dar 200; se der 403, o IP visto pelo backend é outro (apague a variável `AGENTE_IPS_PERMITIDOS` — o token sozinho já protege — ou me avise o IP visto).

## 2. Instalar a ponte na VPS

No seu PC (PowerShell), a partir do projeto atualizado (`git pull`):
```powershell
scp -P 22022 -i $env:USERPROFILE\.ssh\id_ed25519 -r docs\agentes\hermes-cowdata root@143.95.160.39:/opt/cowdata-mcp
```
Na VPS:
```bash
cd /opt/cowdata-mcp
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
umask 077 && read -rsp "Cole o token e tecle Enter: " T && printf '%s\n' "$T" > ~/.cowdata-agente-token && unset T   # nao fica no historico
chmod 600 ~/.cowdata-agente-token ; chmod +x run-mcp-cowdata.sh testar.sh
./testar.sh        # tudo precisa dar OK (token, rotas e escrita impossivel)
```
`requirements.txt` fixa `mcp>=1.2,<2`: a série 2.x do SDK renomeou `FastMCP` para `MCPServer` e esta ponte usa a API 1.x (testada com mcp 1.30.0).

## 3. Registrar o MCP no Hermes

Arquivo `~/.hermes/config.yaml` **[doc]** (chave `mcp_servers`; campos `command`, `args`, `env`, `cwd`, `enabled`, `timeout`, `connect_timeout`; filtro `tools.include`/`tools.exclude`):

```yaml
mcp_servers:
  cowdata:
    command: "/opt/cowdata-mcp/run-mcp-cowdata.sh"   # le o token do arquivo chmod 600; nada de segredo aqui
    args: []
    timeout: 60
    connect_timeout: 30
    # Opcional: so as ferramentas de leitura (todas ja sao). Para limitar, use tools.include.
    # tools:
    #   include: [instrucoes_cowdata, consultar_*, buscar_animal, listar_lotes]
```
Depois de editar, no chat do Hermes: `/reload-mcp` **[doc]** (ou reinicie o gateway).

- Por que o wrapper `run-mcp-cowdata.sh`: a doc mostra o token escrito direto em `env:` do YAML; evitamos isso. Se você preferir `env:` no YAML, use `COWDATA_API_URL` e `COWDATA_AGENTE_TOKEN`. Se o Hermes aceita referência a variável (`${VAR}`) dentro do YAML: **[a confirmar]**.
- Nome das ferramentas dentro do Hermes (se leva prefixo, ex. `mcp_cowdata_...`): **[a confirmar]** — rode `/reload-mcp` e liste as ferramentas.
- Ferramentas que a ponte expõe **[testado]**: `instrucoes_cowdata` + as 10 de "foto de hoje" (`consultar_indicadores`, `buscar_animal`, `consultar_agenda_hoje`, `consultar_financeiro`, `consultar_estoque`, `consultar_calendario_sanitario`, `consultar_analise_reprodutiva`, `consultar_exames`, `listar_lotes`, `consultar_lote`) + as **18 com parâmetros de período/filtro** (`consultar_indicadores_reprodutivos`, `consultar_ciclos_21_dias`, `consultar_servicos_reprodutivos`, `consultar_partos_secagens`, `listar_relatorios`, `executar_relatorio`, `consultar_protocolos_lancados`, `consultar_bst`, `consultar_protocolos_cadastrados`, `consultar_regras_preventivo`, `consultar_lista_espera_preventivo`, `consultar_agendamentos_preventivo`, `consultar_aplicacoes_sanitarias`, `consultar_pedidos`, `consultar_cotacoes`, `consultar_contas_financeiras`, `consultar_estoque_itens`, `consultar_producao_leite`). A lista vem da API na partida; ferramenta nova no CowData aparece após `/reload-mcp` (**após cada deploy do backend, rode `/reload-mcp`**). Mapa completo: `COBERTURA-FERRAMENTAS.md`. Modelo gratuito escolhe pela descrição: se ele errar de ferramenta, ajuste o texto em `assistente_consultas.py`, não aqui.
- Se a API estiver fora do ar na partida, a ponte sobe em modo degradado (`instrucoes_cowdata` + `consultar_cowdata`); rode `/reload-mcp` depois.

## 4. Carregar as instruções do agente

`~/.hermes/SOUL.md` é a identidade principal do agente — ocupa o 1º slot do prompt de sistema **[doc]**. Opções:

1. **Recomendado:** copie `INSTRUCOES-AGENTE.md` para `~/.hermes/SOUL.md` (`cp /opt/cowdata-mcp/INSTRUCOES-AGENTE.md ~/.hermes/SOUL.md`; faça backup do SOUL.md antigo). Se esse agente também faz outras coisas, **mescle** em vez de substituir.
2. Alternativa: `agent.system_prompt` no `config.yaml` **[doc]** — só vale quando nenhuma personalidade estiver ativa; **[a confirmar]** se o seu Hermes usa personalidade por padrão.
3. `AGENTS.md` serve a instruções de projeto/pasta **[doc]**, não é o lugar da persona.

Treino centralizado: o arquivo traz as regras fixas; o conhecimento da fazenda vem dos **Ensinamentos do CowData**, via ferramenta `instrucoes_cowdata`. A instrução do arquivo manda o agente chamá-la no início da conversa. Se o Hermes **não** chamar sozinho: **[a confirmar]** — nesse caso peça "leia as instruções do CowData" no começo da sessão.

## 5. Bot do Telegram

Crie um bot **novo** no @BotFather (o CowData usa outro bot para os fluxos dele). Na VPS, `~/.hermes/.env` **[doc]**:
```
TELEGRAM_BOT_TOKEN=<token do BotFather>
TELEGRAM_ALLOWED_USERS=<id numerico 1>,<id numerico 2>
```
`TELEGRAM_ALLOWED_USERS` é a lista de IDs autorizados — **obrigatória na prática**: o link do bot é público. Descubra seu ID com @userinfobot.
Configure com `hermes gateway setup` (escolha Telegram) ou inicie com `hermes gateway` **[doc]**. Teste: mande "oi" de um ID permitido; de outro, o bot deve ignorar **[a confirmar o comportamento exato para não autorizados]**.
Como manter o gateway rodando como serviço (systemd) na VPS: **[a confirmar]** — veja a doc do gateway.

## 6. Hermes Desktop

O Desktop deve usar o **mesmo** Hermes/`~/.hermes` da VPS, então herda o MCP e o SOUL.md. **[a confirmar]**: se o seu Desktop roda um Hermes local ou conecta ao da VPS — se for local, repita os passos 2–4 nele.

## 7. Testar

- `./testar.sh` — token, rotas e "escrita impossível" **[testado contra backend local]**.
- No Telegram: "Quantos animais temos?" (usa `consultar_indicadores`); "Apague o lote 3" (deve recusar); "Previsão do tempo?" (deve desviar).
- Conferir auditoria: cada consulta gera uma linha no log do Railway, logger `fazenda.agente_auditoria`: `agente_leitura ferramenta=... params=... ip=... status=... duracao_ms=...` (o token nunca é gravado).

## 8. Dados que a API NUNCA devolve (sanitização)

Aplicada a toda resposta de `/agente/*`, em qualquer nível do JSON, **depois** de executar a ferramenta:

- **Removidos** (chave contém): `senha`, `password`, `passwd`, `hash`, `token`, `secret`, `segredo`, `api_key`, `apikey`, `authorization`, `email`, `e_mail`, `conta_bancaria`, `cartao`, `agencia`, e as palavras `pix`, `banco`, `iban`, `cvv`, `cvc`, `swift`.
- **Mascarados** (chave `cpf`/`cnpj`): `***.***.***-NN` e `**.***.***/****-NN` (só os 2 últimos dígitos).
- **Em texto livre** (observações etc.): CPF e CNPJ formatados são mascarados; e-mails viram `[e-mail oculto]`.
- As ferramentas listam campos explícitos (não despejam o registro inteiro); a sanitização é a rede de segurança para texto digitado (ex.: e-mail/CPF numa observação) e campos futuros.
- **Não** são removidos (decisão: o dono vê no site): nome/proprietário/valor de animal, fornecedor, totais financeiros, nomes de veterinário. Se quiser esconder o financeiro do Telegram, defina `AGENTE_MODULOS` sem `financeiro`.
- Limite conhecido: telefone digitado em texto livre **não** é mascarado; CPF/CNPJ sem pontuação em texto livre também não.

## 9. Garantias técnicas de somente leitura

1. Só rotas `GET` (teste automatizado confere o OpenAPI; `POST/PUT/PATCH/DELETE` dão 405).
2. Sessão de banco dedicada em modo leitura: PostgreSQL `SET TRANSACTION READ ONLY`, SQLite `PRAGMA query_only=ON`; `commit` e flush bloqueados; sempre `rollback` **[testado em PostgreSQL 16 local descartável e SQLite]**.
3. Token com comparação em tempo constante; limites de tentativas e de taxa; IP opcional.
4. Cortar tudo: apagar `AGENTE_API_TOKEN` no Railway.

## 10. Se algo falhar

| Sintoma | Causa provável |
|---|---|
| `testar.sh` dá 404 em tudo | `AGENTE_API_TOKEN` não definida (ou < 32 caracteres) no Railway, ou deploy não terminou |
| 401 | token da VPS diferente do Railway |
| 403 | IP fora de `AGENTE_IPS_PERMITIDOS` (ver nota do passo 1) |
| 429 | passou de 60 consultas/min (ou muitas tentativas inválidas) |
| 503 `Fazenda alvo...` | `AGENTE_FAZENDA_ID` aponta para fazenda inexistente |
| Hermes não lista as ferramentas | `/reload-mcp`; rode `run-mcp-cowdata.sh` na mão e veja o stderr (`[mcp-cowdata] ...`) |
