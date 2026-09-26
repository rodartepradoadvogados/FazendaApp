# Catálogo de touros NAAB via Firecrawl: tarefa para o robô MilkNews

> **Para quem é este documento:** o robô **MilkNews** (Routine do Claude no repositório
> FazendaApp/CowData), que ganha uma segunda atribuição: **consultar o catálogo oficial de touros
> pelo Firecrawl e atualizar o banco de touros NAAB do CowData** (Painel CowData → Cadastros →
> Touros NAAB).
>
> ## ⛔ Antes de implementar qualquer coisa: confirme que consegue cumprir a tarefa
> Faça **só a Fase 0** (seção 3) e entregue ao dono um **relatório de viabilidade**. **Não grave
> nada no banco, não abra PR de código e não crie rotina** até o dono responder "pode seguir".
> Se algum item da Fase 0 falhar, o relatório diz exatamente o que falhou e o que seria preciso.
>
> Levantamento feito sobre `main` em 25/09/2026.

---

## 1. O que existe hoje no CowData

**Modelo** `Touro` (`backend/fazenda/models/sanidade.py`, tabela `touro`, **global**, sem
`fazenda_id`):
- `naab` (único, ex.: `7HO12345`)
- `nome`, `nome_completo`, `raca`, `central`
- PTAs: `leite_kg`, `gordura_kg`, `gordura_pct`, `proteina_kg`, `proteina_pct`
- Índices: `tpi`, `nm_dolar`
- Compostos: `tipo_composto` (PTAT), `ubere_composto` (UDC), `pernas_composto` (FLC), `ccs_score`
  (SCS), `fertilidade_filhas` (DPR), `facilidade_parto` (SCE/DCE)
- Controle: `fonte`, `rodada_prova` (ex.: `"Ago/2026"`), `observacao`, `dados_extra` (JSON
  `[[rótulo, valor], ...]`), `atualizado_em`
- **Não existe** campo de registro (HB/registro da associação) nem de nome comercial separado. Se
  precisar, vão em `dados_extra`.

**Regras** (`backend/fazenda/rules/`):
- `naab.py`: `NAAB_STUDS` (prefixo numérico → central: 1 GENEX; 7/9/14/250/507/509 Select Sires;
  11 Alta; 29/94 ABS; 97 CRV; 200/777 Semex; 288 ASCOL; 523/551/646 STgenetics; 596/796 United
  Sires; 599/799 Blondin; 719 RuAnn) e `central_por_codigo_naab`. Referência oficial citada:
  `https://www.naab-css.org/naab-icar-stud-codes` ("a NAAB não tem API pública").
- `touros.py`: `importar_touros(...)` e `importar_touros_planilha_rica(...)`. Fazem **upsert por
  código NAAB e nunca apagam**. Preenchem `central` pelo código quando falta, gravam
  `fonte`/`rodada_prova` e carimbam `atualizado_em`. Aceitam colunas pelos apelidos de `APELIDOS`
  (ex.: `naab`, `nome`, `raca`, `central`, `leite`, `fat kg`, `fat pct`, `protein kg`,
  `protein pct`, `tpi`, `nm`, `ptat`, `udc`, `flc`, `scs`, `dpr`, `sce`).
- Lembrete trimestral já existente: as provas oficiais do CDCB saem em **abril, agosto e dezembro**.

**API** (`backend/fazenda/api/routers/painel_cowdata_touros.py`, prefixo `/painel-cowdata/touros`):

| Rota | Permissão | Uso |
|---|---|---|
| `GET ""` | área `cadastros` | Lista (para mapear naab → id) |
| `POST /importar` | `pode_editar_touros_naab` | **Multipart**: `file` (.csv/.xlsx), `fonte`, `rodada`. Upsert por NAAB. **É o caminho recomendado.** |
| `POST ""` / `PUT /{id}` | `pode_editar_touros_naab` | Um a um. O PUT substitui **todos** os campos: o que não vier vira `null`. Evite. |
| `DELETE /{id}` | idem | **O robô nunca apaga touro.** |

**Autenticação:** não existe chave de API nem conta de serviço. O acesso é por **login de usuário**:
`POST /auth/login` com `{username, senha, manter_conectado}`, que devolve um token para usar em
`Authorization: Bearer <token>`. O token vale 12 h, ou 90 dias com `manter_conectado`.

---

## 2. Credenciais (o dono configura; nunca vão para o repositório)

1. **Usuário dedicado do robô** no CowData: `robo-milk-news` (criado pelo dono em 26/09/2026; o
   sistema não aceitou `robo-milknews`). Observação: `portal.py` esconde das listagens só o nome
   antigo `robo-milknews`. O novo aparece nas listas de usuários, o que é inofensivo. Membro da equipe CowData com a área **cadastros** e
   **somente** a permissão `pode_editar_touros_naab`. Não dê "dono".
2. No ambiente do Claude Code usado pela Routine do MilkNews (claude.ai → Environments →
   Environment variables), cadastrar:

| Variável | Valor |
|---|---|
| `FIRECRAWL_API_KEY` | chave do Firecrawl |
| `COWDATA_API_URL` | URL pública do backend no Railway (a mesma de `NEXT_PUBLIC_API_URL` do frontend) |
| `COWDATA_ROBO_USUARIO` | usuário do passo 1 |
| `COWDATA_ROBO_SENHA` | senha do passo 1 |

**Regra do robô:** nunca imprima, grave em arquivo, commite ou coloque em PR o valor de nenhuma
dessas variáveis nem o token de login.

---

## 3. Fase 0: viabilidade (OBRIGATÓRIA; só leitura, nada gravado)

Responda cada pergunta com **evidência** (URL lida, trecho curto do markdown, status HTTP).

**Ponto de atenção antes de começar:** "catálogo NAAB oficial" não é uma coisa só.
- A **NAAB** (naab-css.org) publica a **tabela de códigos de central** (stud codes), não as provas
  dos touros.
- As **provas genéticas oficiais** dos EUA (PTAs, TPI, NM$) vêm do **CDCB** (Council on Dairy
  Cattle Breeding), mais o índice TPI da Holstein Association USA.
- Os **catálogos comerciais** das centrais (ABS, Alta, Select Sires, Semex, STgenetics, CRV) trazem
  os mesmos touros com as provas da rodada vigente.

O relatório precisa dizer **qual dessas fontes o robô consegue ler de verdade**.

**F0.1 Firecrawl disponível?**
```bash
curl -sS https://api.firecrawl.dev/v2/team/credit-usage -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```
Informe o saldo de créditos.

**F0.2 Tabela de stud codes da NAAB.** `/scrape` em
`https://www.naab-css.org/naab-icar-stud-codes`. O markdown traz a tabela? Compare com `NAAB_STUDS`
em `naab.py` e liste códigos que faltam ou divergem.

**F0.3 Prova de um touro por código NAAB.** Escolha 3 touros **já cadastrados** (via
`GET /painel-cowdata/touros`; F0.5 primeiro, se precisar) e, para cada um:
- use `/search` para achar a página oficial do touro no CDCB e na central dona do prefixo;
- faça `/scrape` nas páginas achadas;
- extraia do markdown: NAAB, nome, raça, rodada/data da prova, leite, gordura (kg e %), proteína
  (kg e %), TPI, NM$, PTAT, UDC, FLC, SCS, DPR, SCE;
- compare com o que está no banco.

Resultado esperado: uma tabela touro × campo × (valor do site | valor do banco | igual?).

**F0.4 A fonte cobre o catálogo inteiro?** Existe página de listagem ou exportação (CSV/Excel) da
rodada vigente que o Firecrawl consiga ler (HTML paginado ou arquivo)? Ou só dá para consultar
touro a touro? Estime o custo em créditos para atualizar todos os touros cadastrados (conte com
`GET /painel-cowdata/touros`).

**F0.5 Login e permissão.** `POST $COWDATA_API_URL/auth/login` com o usuário do robô → 200?
`GET $COWDATA_API_URL/painel-cowdata/touros` → 200? **Não chame** nenhuma rota de escrita na Fase 0.

**F0.6 Termos de uso.** Leia os termos (terms of use) das fontes escolhidas e diga se proíbem coleta
automatizada. Proibição explícita = fonte descartada.

**Entrega da Fase 0:** relatório ao dono (mensagem da sessão ou comentário no PR de documentação)
com:
- viável / parcialmente viável / inviável;
- quais fontes funcionam para quais campos;
- custo estimado em créditos por atualização;
- riscos encontrados.

**Pare aqui e espere o "pode seguir".**

---

## 4. Fase 1: atualização (implementada em 26/09/2026, aprovada pelo dono)

**Mudança de desenho em relação ao rascunho original desta seção:** em vez de ler touro a touro
pelo Firecrawl (CDCB + catálogo da central), uma investigação confirmou que a própria NAAB publica
em `https://www.naab-css.org/database-files` um arquivo ZIP oficial — link de texto **"Complete
List of All Active (A), Foreign (F) and Genomic (G) AI Bulls"** — com o catálogo genético
**completo** de todos os touros de IA ativamente comercializados nos EUA. Esse ZIP é lido por HTTP
comum (`httpx`), sem Firecrawl e sem bloqueio de bot, e contém um único arquivo `.txt` que, apesar
do nome, é um CSV comum (vírgula, texto entre aspas, número sem aspas), uma linha por touro. O
Firecrawl fica **reservado** para uma eventual segunda confirmação pontual de um touro específico
que tenha mudado bastante (ex.: TPI mudou centenas de pontos) — não é obrigatório nesta primeira
versão, e nenhuma automação desta fase o chama.

Implementação: `backend/fazenda/rules/naab_aiss.py` (download, parsing, mapeamento, comparação) e
`backend/fazenda/rules/touros.py::aplicar_atualizacoes_confirmadas` (gravação). Testes com duas
linhas reais do arquivo, validadas campo a campo contra as páginas públicas de dois touros
(TIMETRAVELER/200HO13678, central Semex, e SABOTAGE/796HO10329, central United Sires): ver
`backend/tests/test_naab_aiss.py`.

### 4.1 Frequência
- O robô verifica **uma vez por semana** se o arquivo AISS mudou (nome do arquivo/rodada) e roda a
  comparação (`comparar_catalogo`) sempre que verificar — não só quando a rodada trimestral do CDCB
  (abril/agosto/dezembro) muda, porque o arquivo da NAAB também recebe correções fora dessas datas.
- Fora da rodada trimestral: a comparação ainda roda toda semana; o volume de mudanças detectadas é
  que tende a ser pequeno.

### 4.2 Comparação semanal — SÓ LEITURA, sem gravar nada sozinho
`fazenda.rules.naab_aiss.comparar_catalogo(session, linhas_aiss)` nunca chama
`session.add`/`session.commit`. Ela devolve um `RelatorioNaab` com três listas:

- **Alterados**: touro já cadastrado cujo NAAB está no AISS e cujos campos curados (leite, gordura,
  proteína, TPI, NM$, PTAT, UDC, FLC, SCS, DPR, SCE) mudaram além de uma tolerância de
  arredondamento (0,01) — só os campos que de fato mudaram, com antes/depois.
- **Saídos**: touro cadastrado cujo NAAB **não** aparece mais no AISS baixado — item **só com NAAB
  e nome**, sem prova nenhuma (pedido explícito do dono). "Saiu" **nunca apaga nem esconde** o
  touro automaticamente: é sempre uma nota no relatório, para o dono decidir. Se o dono já decidiu
  mantê-lo (`marcar_mantido`, que grava `"[NAAB] mantido por decisão do dono em DD/MM/AAAA: <motivo>"`
  em `Touro.observacao`, sem apagar o que já havia lá), o touro **não** volta a aparecer em "saídos"
  nas semanas seguintes.
- **Novos**: linha do AISS cujo NAAB não existe em nenhum touro do banco — **de todas as centrais,
  sem filtro** (pedido explícito do dono: ele quer ver touro novo de qualquer central). Traz a prova
  completa mapeada. Uma rodada com uma lista grande de novos ainda devolve os dados completos —
  quem exibe o relatório decide como resumir para o dono, os dados nunca são truncados aqui.

### 4.3 Aprovação — sempre por mensagem no chat, nunca automática
**Não existe gravação automática nem PR de dados nesta fase.** O robô manda o relatório da
comparação semanal ao dono **no chat** (não abre PR — isso é diferente da política do lote diário
do MilkNews) e só grava no banco depois que o dono responde aprovando, indicando quais NAABs
confirmar (pode ser "todos os alterados e novos", uma lista específica, etc.).

Com a aprovação:
```python
from fazenda.rules.touros import aplicar_atualizacoes_confirmadas

resultado = aplicar_atualizacoes_confirmadas(
    session, naabs_confirmados, linhas_aiss, fonte="NAAB AISS", rodada="Ago/2026",
)
```
`aplicar_atualizacoes_confirmadas` filtra `linhas_aiss` para só os NAABs confirmados, mapeia com
`naab_aiss.mapear_para_touro` e delega o upsert (por NAAB, nunca apaga) para o mesmo núcleo que
`importar_touros` usa — sem lógica de upsert duplicada entre os dois caminhos.

Para um touro que "saiu" e o dono decide manter mesmo assim:
```python
from fazenda.rules.naab_aiss import marcar_mantido

marcar_mantido(session, naab, motivo="genética boa, mantém no plantel")
```

### 4.4 Unidades e mapeamento
O arquivo AISS traz produção em **libras** (`PTA Milk`, `PTA Fat Pounds`, `PTA Protein Pounds`) —
`mapear_para_touro` converte para kg (1 lb = 0,453592 kg, arredondado a 2 casas) antes de gravar em
`leite_kg`/`gordura_kg`/`proteina_kg`. Campo ausente na linha de origem (string vazia após o
parsing) nunca vira `0.0` — fica de fora do dict mapeado, mesmo espírito de "só grava o que está
presente" de `importar_touros`. `central` é derivada do prefixo do NAAB por
`fazenda.rules.naab.central_por_codigo_naab` — a mesma função já usada pelo resto do sistema.

### 4.5 Frontend
O Painel CowData (`frontend/components/CadastroTouros.tsx`, usado tanto em modo "painel" quanto em
modo "fazenda" — só leitura) ganhou um alternador kg ⇄ lb para as colunas Leite/Gordura/Proteína —
só exibição (o banco continua em kg), preferência guardada em `localStorage` do navegador.

**Proibido, sem exceção:** `DELETE`, `PUT` que zere campos, `POST /recarregar-catalogo` (reimporta a
planilha embutida da Alta e pode sobrescrever dados mais novos) e gravar qualquer touro sem
aprovação explícita do dono no chat.

### 4.6 Relatório de cada execução
Enviar ao dono no chat:
- rodada (extraída do nome do arquivo AISS baixado, quando reconhecível);
- quantos touros comparados, quantos alterados/saídos/novos;
- a lista de alterados e de novos (resumida se for grande) e de saídos (só NAAB + nome);
- pergunta objetiva: quais confirmar para gravar.

---

## 5. Evoluções que dependem do dono (não fazer por conta própria)
- **Conta de serviço / chave de API** no backend para o robô, em vez de login de usuário. Exige
  mudança em `auth.py`, com revisão de segurança.
- **Campos novos** no `Touro` (registro, nome comercial, data da prova): migração Alembic no padrão
  do repositório (`backend/alembic/versions/`, docstring explicando o porquê).
- **Endpoint de upsert em lote por JSON:** hoje só existe o upload de CSV/XLSX.
- **Segunda confirmação pontual pelo Firecrawl** (CDCB/central) para um touro específico com mudança
  grande — reservada, não implementada nesta fase (ver seção 4).

## 6. Checklist
- [ ] Fase 0 entregue e **aprovada pelo dono** antes de qualquer escrita (histórico — já concluída).
- [ ] Usuário do robô só com `pode_editar_touros_naab`.
- [ ] `comparar_catalogo` roda toda semana e **nunca** grava sozinha — só leitura.
- [ ] Relatório mandado ao dono **no chat**; gravação só depois de aprovação explícita por NAAB.
- [ ] "Saiu" nunca apaga automaticamente; `marcar_mantido` evita repetir a mesma nota toda semana.
- [ ] "Novo" cobre todas as centrais, sem filtro.
- [ ] Só upsert via `aplicar_atualizacoes_confirmadas`/`importar_touros`; nada apagado.
- [ ] Nenhuma credencial ou token em arquivo, log, commit ou PR.
