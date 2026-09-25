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

1. **Usuário dedicado do robô** no CowData, por exemplo `robo-milknews` (o código já esconde esse
   nome das listagens em `portal.py`). Membro da equipe CowData com a área **cadastros** e
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

## 4. Fase 1: atualização (só depois da aprovação)

### 4.1 Frequência
- **Rodada nova:** o CDCB publica provas em **abril, agosto e dezembro**. O robô verifica se há
  rodada nova uma vez por semana e atualiza **só quando a rodada mudar**. Isso economiza créditos.
- Fora da rodada: só touros novos pedidos pelo dono ou pela equipe.

### 4.2 Dupla verificação (mesma filosofia do MilkNews)
- Cada touro atualizado precisa ter os valores confirmados em **duas fontes independentes lidas**
  (ex.: CDCB + catálogo da central dona do prefixo).
- Havendo divergência num campo, prevalece o **CDCB** (fonte oficial da avaliação). O valor da
  central vai para `observacao` como "divergência: <campo> central=<x>".
- Touro sem nenhuma fonte oficial legível **não é atualizado**. Entra no relatório.
- Código NAAB normalizado: maiúsculas, sem espaços, com o prefixo numérico no `NAAB_STUDS`. Prefixo
  desconhecido → não grava, relata.

### 4.3 Gravação no CowData
1. Monte um CSV em `/tmp/naab/touros_<rodada>.csv` com cabeçalhos reconhecidos por `APELIDOS`:
   ```
   naab,nome,raca,central,milk kg,fat kg,fat pct,protein kg,protein pct,tpi,nm,ptat,udc,flc,scs,dpr,sce
   ```
   Convenção de unidades: o modelo guarda **kg**. Se a fonte der lbs, converta
   (1 lb = 0,453592 kg) e registre a conversão no relatório.
2. Login:
   `POST $COWDATA_API_URL/auth/login` → token em memória (nunca em arquivo).
3. Importação:
   ```bash
   curl -sS -X POST "$COWDATA_API_URL/painel-cowdata/touros/importar" \
     -H "Authorization: Bearer $TOKEN" \
     -F "file=@/tmp/naab/touros_<rodada>.csv" \
     -F "fonte=CDCB + <central> via Firecrawl (robô MilkNews)" \
     -F "rodada=<Mmm/AAAA>"
   ```
4. Confirmação: `GET /painel-cowdata/touros` e confira, por amostragem de pelo menos 5 touros, que
   os valores gravados batem com o CSV.

**Proibido:** `DELETE`, `PUT` que zere campos, `POST /recarregar-catalogo` (reimporta a planilha
embutida da Alta e pode sobrescrever dados mais novos) e gravar touro sem as duas fontes.

### 4.4 Relatório de cada execução
Enviar ao dono (ou registrar no PR do MilkNews do dia):
- rodada;
- quantos touros atualizados, criados e pulados, **com o motivo**;
- divergências;
- créditos gastos;
- as URLs lidas por touro (no mínimo por amostragem).

---

## 5. Evoluções que dependem do dono (não fazer por conta própria)
- **Conta de serviço / chave de API** no backend para o robô, em vez de login de usuário. Exige
  mudança em `auth.py`, com revisão de segurança.
- **Campos novos** no `Touro` (registro, nome comercial, data da prova): migração Alembic no padrão
  do repositório (`backend/alembic/versions/`, docstring explicando o porquê).
- **Endpoint de upsert em lote por JSON:** hoje só existe o upload de CSV/XLSX.

## 6. Checklist
- [ ] Fase 0 entregue e **aprovada pelo dono** antes de qualquer escrita.
- [ ] Usuário do robô só com `pode_editar_touros_naab`.
- [ ] Toda atualização com 2 fontes lidas; divergências anotadas; CDCB prevalece.
- [ ] Só upsert via `/importar`; nada apagado.
- [ ] Nenhuma credencial ou token em arquivo, log, commit ou PR.
