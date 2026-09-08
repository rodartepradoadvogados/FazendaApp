"""
Motor de replicação ORIGEM → DESTINO — o "SINCRONIZAR FAZENDA JAIRO NASSER
COM FAZENDA TESTE" do Painel CowData (ver
fazenda/api/routers/painel_cowdata_sincronizacao.py, que só valida o pedido
HTTP e chama `sincronizar_fazenda_teste_destrutivo` abaixo).

Objetivo: dar à equipe uma Fazenda Teste com dado REALISTA (o estado atual
de uma fazenda-cliente de verdade), refeita sob demanda, para testar
funcionalidade nova sem tocar em produção nem inventar dado sintético.

┌─────────────────────────────────────────────────────────────────────────┐
│ REGRAS INEGOCIÁVEIS (repita antes de mexer aqui):                        │
│  1. Sentido único: ORIGEM → DESTINO. Nunca escreve na origem.            │
│  2. Destino tem que ter `Fazenda.eh_teste = True` — senão 409. Conferido │
│     em SQL, pela conexão que escreve, DUAS vezes: na entrada e dentro do  │
│     `_apagar_destino` (ver `_exigir_destino_de_teste`).                   │
│  3. origem_id == destino_id é sempre recusado.                          │
│  4. DESTRUTIVO no destino: apaga tudo do destino antes de copiar.        │
│  5. Tudo numa única transação — qualquer falha reverte o destino ao      │
│     estado anterior (nada "meio copiado").                              │
└─────────────────────────────────────────────────────────────────────────┘

────────────────────────── (a) DESCOBERTA DINÂMICA ──────────────────────────
Por que não uma lista de tabelas escrita à mão? Porque ela MENTE em silêncio.
O sistema tem ~180 tabelas com `fazenda_id` hoje e ganha tabelas novas toda
semana (a última contagem documentada no pedido original já ficou pra trás
antes mesmo deste módulo existir). Uma lista fixa começa certa e, seis meses
depois, simplesmente não copia a tabela nova — sem erro, sem log, sem aviso:
o próximo dev só descobre quando alguém reclamar que "a Fazenda Teste não
tem o módulo X". Uma rotina que existe PARA dar dado realista e falha
silenciosamente nisso é pior que não existir. Por isso a fonte de verdade
aqui é sempre `SQLModel.metadata` (o que o ORM sabe AGORA sobre as tabelas),
nunca um `set()`/`dict()` de nomes congelados no texto do código.

Exceção deliberada (não é uma lista de DADO, é uma lista de CONTROLE — ver
`_TABELAS_CONTROLE_ACESSO_EXCLUIDAS` abaixo): um punhado fixo e pequeno de
tabelas que TÊM fazenda_id mas não são "dado da fazenda" no sentido que o
dono pediu (rebanho, reprodução, sanidade, produção, financeiro...) — são a
trilha de QUEM DA COWDATA acessou o quê e quando. Replicar essas linhas para
dentro da Fazenda Teste não deixaria o sandbox mais realista, só multiplicar
histórico de auditoria de acesso e vínculo de login que não pertence a um
teste. Essa exceção é curada por nome de tabela porque é uma decisão
categórica e estável (o módulo inteiro de Cofre de acesso + o vínculo
Usuario↔Fazenda), não um catálogo de dado de negócio que cresce sozinho.

──────────────────────── (b)/(c) ORDEM + REMAPEAMENTO ────────────────────────
Grafo de FKs entre as tabelas descobertas (filha → pai). Ordena por
Kahn (topológica) para inserir pais antes de filhos. FKs que fecham um
CICLO (duas tabelas que se referenciam mutuamente, ou uma tabela que
referencia a si mesma — ex.: CategoriaAlimento.categoria_pai_id) são
"adiadas": a coluna entra NULA no INSERT e ganha o valor remapeado de
verdade numa 2ª passada de UPDATE, depois que TODAS as tabelas já têm seu
mapa (tabela, id_antigo) -> id_novo completo. Isso resolve ciclo sem
depender de conhecer os nomes das tabelas envolvidas — se amanhã nascer uma
tabela nova em ciclo, o algoritmo quebra o ciclo do mesmo jeito.

────────────────────────────── (d) CATÁLOGO ──────────────────────────────
Só linhas com `fazenda_id == origem_id` são copiadas (nunca `fazenda_id IS
NULL` — ver fazenda/rules/visibilidade.py). Uma FK que aponta para uma linha
GLOBAL do catálogo (fazenda_id IS NULL na tabela-alvo) permanece apontando
para a MESMA linha global depois da cópia — não duplicamos catálogo.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy import Table
from sqlalchemy import delete as sa_delete
from sqlalchemy import insert as sa_insert
from sqlalchemy import select as sa_select
from sqlalchemy import update as sa_update
from sqlalchemy.engine import Connection
from sqlmodel import Session, SQLModel

from fazenda.models.multitenant import Fazenda

logger = logging.getLogger(__name__)

# Linhas por página ao LER a fazenda de origem (item h — Jairo Nasser tem
# anos de dado; nunca fazemos `SELECT * FROM tabela WHERE fazenda_id = X`
# sem LIMIT). Ver `_copiar_tabela` — cada lote é lido, remapeado, inserido
# (uma linha por INSERT, porque cada uma precisa devolver o id_novo pro mapa
# de remapeamento — ver docstring de `_inserir_lote`) e descartado da
# memória do processo antes do próximo lote entrar.
TAMANHO_LOTE = 500

# ---------------------------------------------------------------------------
# (a) Exceção categórica à descoberta dinâmica: tabelas de CONTROLE DE ACESSO
# da própria CowData (Cofre de acesso — fazenda/models/cofre_acesso.py — e o
# vínculo Usuario↔Fazenda — fazenda/models/multitenant.py::UsuarioFazenda).
# Têm `fazenda_id`, então a regra pura de "toda tabela com fazenda_id" as
# pegaria — mas replicar "quem da CowData acessou esta fazenda e quando" ou
# "quais logins reais estão vinculados a ela" para dentro do sandbox não é
# o que o dono pediu (dado de REBANHO/REPRODUÇÃO/SANIDADE/FINANCEIRO — dado
# operacional da fazenda), e tem um efeito colateral ruim: replicar
# `usuario_fazenda` vincularia a conta de login REAL do cliente (ou de quem
# mais estiver vinculado à fazenda de origem) também à Fazenda Teste — a
# pessoa passaria a ver "Fazenda Teste" na tela de seleção de fazenda ao
# logar, uma surpresa que ninguém pediu. Ver relatório da tarefa.
# ---------------------------------------------------------------------------
_TABELAS_CONTROLE_ACESSO_EXCLUIDAS = frozenset({
    "usuario_fazenda",           # multitenant.py — vínculo de login, não dado de fazenda
    "pedido_acesso_suporte",     # cofre_acesso.py — trilha de acesso da CowData
    "sessao_acesso_suporte",     # cofre_acesso.py — idem
    "auditoria_acesso_suporte",  # cofre_acesso.py — idem
    "acao_auditoria_suporte",    # cofre_acesso.py — idem
})

# ---------------------------------------------------------------------------
# (f) Anexo/arquivo externo (Supabase Storage) — ver justificativa completa
# no relatório da tarefa. Resumo: todo modelo de anexo do repo guarda o
# caminho do OBJETO no Storage num campo sempre chamado `caminho_storage`
# (DocumentoArquivado, FotoCampo, LancamentoAnexo, PedidoAnexo, PessoaAnexo —
# conferido por grep, é convenção real do código, não coincidência). Copiar
# esse valor tal como está faria a linha copiada no sandbox apontar para o
# MESMO objeto físico de produção — e o botão de excluir anexo (ver
# documentos.py/financeiro.py/fotos.py) chama
# `fazenda.rules.supabase_storage.excluir_arquivo`, que APAGA o objeto de
# verdade no bucket. Ou seja: sem essa proteção, excluir um anexo qualquer
# na Fazenda Teste apagaria o arquivo real do cliente em produção — o tipo
# exato de destruição que a regra "sentido único" existe para impedir.
# Por isso este campo NUNCA é copiado com o valor original: vira um
# marcador que garante 404 no Storage (nunca aponta pra um objeto real),
# preservando metadado (nome, tipo, tamanho) só para a lista continuar
# realista. `ContratoAnexo` fica de fora desta lista de propósito: guarda o
# arquivo em bytes DENTRO do próprio Postgres (sem Storage externo), então
# copiar a linha inteira é seguro e não precisa de tratamento especial.
# ---------------------------------------------------------------------------
COLUNA_ANEXO_STORAGE = "caminho_storage"


def _marcador_anexo_nao_copiado(tabela: str, id_antigo: int, valor_original: str | None) -> str:
    """Novo valor de `caminho_storage` na cópia — nunca resolve pra um
    objeto real (por isso o prefixo fixo, que nenhum bucket usa), mas
    guarda o caminho original no próprio texto pra quem for investigar."""
    origem = valor_original or "(vazio)"
    return f"__sandbox_arquivo_nao_replicado__/{tabela}/{id_antigo}::{origem}"


@dataclass
class ResultadoSincronizacao:
    tabelas: int = 0
    linhas_copiadas: int = 0
    duracao_s: float = 0.0
    avisos: list[str] = field(default_factory=list)


class SincronizacaoInvalidaError(HTTPException):
    """409 — pedido recusado por uma das travas de segurança (regras 2 e 3
    do módulo). Sempre HTTPException pronta pra estourar direto do router,
    igual ao padrão do resto de fazenda/rules/*.py."""

    def __init__(self, detail: str):
        super().__init__(status_code=409, detail=detail)


class CicloIrreparavelError(Exception):
    """Ciclo de FK entre tabelas de fazenda em que NENHUMA coluna do ciclo é
    anulável — não dá pra quebrar inserindo NULL e corrigindo depois. Nunca
    deveria acontecer com o schema de hoje (os 2 ciclos existentes,
    dieta_simulacao↔dieta_lancamento e estoque↔alimento, têm as duas pontas
    anuláveis) — se acontecer, é sinal de schema novo que precisa de uma
    coluna nullable ou de um redesenho, não de um retry."""


# ---------------------------------------------------------------------------
# (a) Descoberta dinâmica das tabelas "dado de fazenda".
# ---------------------------------------------------------------------------
def _tabelas_fazenda() -> dict[str, Table]:
    """Toda tabela do metadata do SQLModel que tem coluna `fazenda_id`,
    menos as de controle de acesso (ver `_TABELAS_CONTROLE_ACESSO_EXCLUIDAS`
    logo acima). Chamar isso, e não uma lista escrita à mão, é o próprio
    ponto do item (a) da tarefa — ver docstring do módulo."""
    tabelas = {}
    for nome, tabela in SQLModel.metadata.tables.items():
        if "fazenda_id" not in tabela.columns:
            continue
        if nome in _TABELAS_CONTROLE_ACESSO_EXCLUIDAS:
            continue
        tabelas[nome] = tabela
    return tabelas


# ---------------------------------------------------------------------------
# (b) Grafo de dependência (FK) + ordenação topológica com quebra de ciclo.
# ---------------------------------------------------------------------------
def _fks_relevantes(tabela: Table, tabelas: dict[str, Table]):
    """FKs de `tabela` cujo ALVO também é uma tabela de fazenda (as únicas
    que precisam de ordenação/remapeamento — FK pra fora do conjunto, ex.:
    catálogo global ou `usuario.id`, nunca é remapeada, então não entra no
    grafo de dependência)."""
    for fk in tabela.foreign_keys:
        alvo = fk.column.table.name
        if alvo in tabelas:
            yield fk.parent.name, alvo


def _ordenar_com_quebra_de_ciclo(tabelas: dict[str, Table]) -> tuple[list[str], dict[str, list[str]]]:
    """Kahn com quebra de ciclo dirigida por nullability.

    Devolve (ordem_topologica, fks_adiadas) onde `fks_adiadas[tabela]` é a
    lista de nomes de coluna que devem ser inseridos como NULL e corrigidos
    numa 2ª passada (autorreferência, ex.: CategoriaAlimento.categoria_pai_id,
    e ciclo entre duas tabelas, ex.: estoque↔alimento).

    Por que não simplesmente falhar no primeiro ciclo? Porque autorreferência
    (uma tabela hierárquica apontando pra si mesma) é ciclo trivial e
    LEGÍTIMO — categoria/subcategoria, resposta de mensagem, etc. — sempre
    com a coluna nullable. Detectar isso e "adiar" em vez de estourar erro é
    o que permite copiar CategoriaAlimento (e as outras 8 autorreferências
    do schema atual) sem tratamento especial por tabela.
    """
    # arestas: filha -> {(pai, coluna)}
    arestas: dict[str, set[tuple[str, str]]] = {nome: set() for nome in tabelas}
    for nome, tabela in tabelas.items():
        for coluna, alvo in _fks_relevantes(tabela, tabelas):
            if alvo == nome:
                continue  # autorreferência tratada à parte (sempre adiada, nunca conta pro grafo)
            arestas[nome].add((alvo, coluna))

    fks_adiadas: dict[str, list[str]] = {}

    # Autorreferência: sempre adiada (é ciclo de tamanho 1, sempre quebrável
    # se a coluna for nullable — e toda autorreferência do schema atual é).
    for nome, tabela in tabelas.items():
        for coluna, alvo in _fks_relevantes(tabela, tabelas):
            if alvo == nome:
                if not tabela.columns[coluna].nullable:
                    raise CicloIrreparavelError(
                        f"{nome}.{coluna} referencia a própria tabela e não é nullable — "
                        "não dá pra copiar sem quebrar a FK."
                    )
                fks_adiadas.setdefault(nome, []).append(coluna)

    def _existe_ciclo(grafo: dict[str, set[tuple[str, str]]]) -> list[str] | None:
        BRANCO, CINZA, PRETO = 0, 1, 2
        cor = {n: BRANCO for n in grafo}
        pilha: list[str] = []

        def dfs(u: str) -> list[str] | None:
            cor[u] = CINZA
            pilha.append(u)
            for v, _coluna in grafo[u]:
                if cor[v] == CINZA:
                    i = pilha.index(v)
                    return pilha[i:] + [v]
                if cor[v] == BRANCO:
                    achado = dfs(v)
                    if achado:
                        return achado
            pilha.pop()
            cor[u] = PRETO
            return None

        for n in list(grafo):
            if cor[n] == BRANCO:
                achado = dfs(n)
                if achado:
                    return achado
        return None

    # Quebra iterativa: a cada ciclo encontrado, remove UMA aresta nullable
    # dele (a primeira que achar); se nenhuma aresta do ciclo for nullable,
    # é irreparável — relata em vez de girar pra sempre (pedido explícito
    # do item b da tarefa).
    for _tentativa in range(len(tabelas) + 10):  # cota de segurança — nunca deveria chegar perto disso
        ciclo = _existe_ciclo(arestas)
        if ciclo is None:
            break
        quebrou = False
        for i in range(len(ciclo) - 1):
            u, v = ciclo[i], ciclo[i + 1]
            for alvo, coluna in list(arestas[u]):
                if alvo == v and tabelas[u].columns[coluna].nullable:
                    arestas[u].discard((alvo, coluna))
                    fks_adiadas.setdefault(u, []).append(coluna)
                    quebrou = True
                    break
            if quebrou:
                break
        if not quebrou:
            raise CicloIrreparavelError(
                "Ciclo de FK entre tabelas de fazenda sem nenhuma coluna nullable para quebrar: "
                + " -> ".join(ciclo)
            )
    else:
        raise CicloIrreparavelError("Não foi possível eliminar todos os ciclos de FK — grafo maior do que o esperado.")

    # Kahn de verdade sobre o grafo já acíclico.
    grau_saida = {n: len(vs) for n, vs in arestas.items()}  # "preciso que estes pais sejam inseridos antes"
    prontos = [n for n, g in grau_saida.items() if g == 0]
    ordem: list[str] = []
    # predecessores: quem depende de mim (pra decrementar o grau quando eu "termino")
    dependentes: dict[str, list[str]] = {n: [] for n in tabelas}
    for filha, alvos in arestas.items():
        for alvo, _coluna in alvos:
            dependentes[alvo].append(filha)

    restante = dict(grau_saida)
    while prontos:
        n = prontos.pop()
        ordem.append(n)
        for filha in dependentes[n]:
            restante[filha] -= 1
            if restante[filha] == 0:
                prontos.append(filha)

    if len(ordem) != len(tabelas):
        # Não deveria acontecer (o grafo já foi tornado acíclico acima) —
        # fica como cinto-de-segurança caso a quebra de ciclo tenha um bug.
        faltando = set(tabelas) - set(ordem)
        raise CicloIrreparavelError(f"Ordenação topológica não fechou — tabelas restantes: {sorted(faltando)}")

    return ordem, fks_adiadas


# ---------------------------------------------------------------------------
# (d) Ids "globais" (fazenda_id IS NULL) por tabela — pré-calculado UMA vez
# por tabela (nunca por linha), pra distinguir "essa FK aponta pra uma linha
# de catálogo global, mantém como está" de "essa FK ficou órfã, é bug de
# dado" sem uma query por linha copiada.
# ---------------------------------------------------------------------------
def _ids_globais_por_tabela(conn: Connection, tabelas: dict[str, Table]) -> dict[str, set[int]]:
    globais: dict[str, set[int]] = {}
    for nome, tabela in tabelas.items():
        pk = list(tabela.primary_key.columns)[0]
        linhas = conn.execute(sa_select(pk).where(tabela.c.fazenda_id.is_(None))).scalars().all()
        if linhas:
            globais[nome] = set(linhas)
    return globais


# ---------------------------------------------------------------------------
# (e) Restrições UNIQUE "globais" (que não incluem fazenda_id) — a única
# forma de descobrir isso sem manter uma 2ª lista escrita à mão é perguntar
# ao próprio metadata quais colunas são UNIQUE e comparar com as FKs da
# tabela (ver `_colunas_para_desambiguar`).
# ---------------------------------------------------------------------------
def _restricoes_unicas(tabela: Table) -> list[tuple[str, ...]]:
    """Todas as combinações de colunas com restrição UNIQUE desta tabela —
    tanto `UniqueConstraint` explícita quanto `Column(unique=True)` (que o
    SQLAlchemy materializa como um Index unique=True de uma coluna só)."""
    grupos: list[tuple[str, ...]] = []
    for uc in tabela.constraints:
        if uc.__class__.__name__ == "UniqueConstraint":
            grupos.append(tuple(c.name for c in uc.columns))
    for ix in tabela.indexes:
        if ix.unique:
            grupos.append(tuple(c.name for c in ix.columns))
    return grupos


def _colunas_para_desambiguar(tabela: Table) -> set[str]:
    """Colunas que precisam de um valor NOVO (não o valor da origem tal
    como está) pra não violar uma UNIQUE ao copiar.

    Uma restrição UNIQUE só é um risco de colisão se ELA MESMA não inclui
    `fazenda_id` (aí já é isolada por fazenda, sem risco — ver
    animais.py/estoque.py/financeiro.py, que já seguem esse padrão) E se
    tiver pelo menos uma coluna que NÃO é FK (uma UNIQUE composta só de FKs,
    ex.: EstoquePrincipioAtivo(estoque_id, principio_ativo_id), não precisa
    de mutação — depois do remapeamento de FK, os ids novos já garantem que
    não colide com nada, porque o destino foi limpo antes da cópia).

    Hoje isto pega exatamente: `Animal.numero` (até a outra frente trocar
    por `UniqueConstraint(fazenda_id, numero)` — ver relatório da tarefa),
    `CobrancaPix.txid`, `CobrancaAsaas.referencia_asaas` e
    `ContratoAssinaturaZapSign.document_token` (essas três são referência de
    gateway externo — Asaas/ZapSign —, então nunca fariam sentido
    duplicadas mesmo depois de qualquer migração: o sandbox não fala com o
    gateway de verdade)."""
    nomes_fk = {fk.parent.name for fk in tabela.foreign_keys}
    resultado: set[str] = set()
    for colunas in _restricoes_unicas(tabela):
        if "fazenda_id" in colunas:
            continue
        candidatas = [c for c in colunas if c not in nomes_fk]
        resultado.update(candidatas)
    return resultado


def _valor_desambiguado(tabela_nome: str, coluna: str, valor_original, id_antigo: int):
    """Sufixo determinístico e único por linha de origem — nunca colide
    entre duas linhas copiadas (usa o id da linha NA ORIGEM, que é único
    naquela tabela), e roda igual em toda execução (suporta rodar a
    sincronização várias vezes seguidas, sempre limpando o destino antes)."""
    if valor_original is None:
        return None
    return f"{valor_original}::sandbox-{tabela_nome}-{id_antigo}"


# ---------------------------------------------------------------------------
# Cópia de uma tabela — lida em lotes da origem, remapeada, inserida linha a
# linha no destino (ver item h do relatório: precisamos do id_novo de CADA
# linha pra alimentar o mapa de remapeamento das tabelas filhas; não dá pra
# usar um único INSERT em massa sem perder essa informação).
# ---------------------------------------------------------------------------
def _copiar_tabela(
    conn: Connection,
    tabela: Table,
    *,
    origem_id: int,
    destino_id: int,
    tabelas: dict[str, Table],
    ids_globais: dict[str, set[int]],
    mapa_ids: dict[str, dict[int, int]],
    colunas_desambiguar: set[str],
    colunas_adiadas: list[str],
    fks_adiadas_globais: dict[str, list[tuple[str, str, int]]],
    avisos: list[str],
    contadores: dict[str, int],
) -> int:
    pk = list(tabela.primary_key.columns)[0].name
    fks_por_coluna = {fk.parent.name: fk.column.table.name for fk in tabela.foreign_keys}
    mapa_local = mapa_ids.setdefault(tabela.name, {})

    total_copiado = 0
    offset = 0
    orfas_puladas = 0
    while True:
        lote = conn.execute(
            sa_select(tabela)
            .where(tabela.c.fazenda_id == origem_id)
            .order_by(tabela.c[pk])
            .offset(offset)
            .limit(TAMANHO_LOTE)
        ).mappings().all()
        if not lote:
            break
        offset += TAMANHO_LOTE

        for linha in lote:
            id_antigo = linha[pk]
            valores: dict = {}
            linha_valida = True
            for nome_coluna, valor in linha.items():
                if nome_coluna == pk:
                    continue  # id novo é gerado pelo banco
                if nome_coluna == "fazenda_id":
                    valores[nome_coluna] = destino_id
                    continue
                if nome_coluna in colunas_adiadas:
                    # (b)/(c) autorreferência ou ciclo: entra NULL agora,
                    # corrigido na 2ª passada por `_aplicar_fks_adiadas`.
                    if valor is not None:
                        fks_adiadas_globais.setdefault(tabela.name, []).append((nome_coluna, str(id_antigo), valor))
                    valores[nome_coluna] = None
                    continue
                if nome_coluna in fks_por_coluna and valor is not None:
                    tabela_alvo = fks_por_coluna[nome_coluna]
                    if tabela_alvo not in tabelas:
                        # (d) FK pra fora do conjunto de fazenda (catálogo
                        # sem fazenda_id nenhum, ex.: touro.id, ou tabela de
                        # controle excluída) — nunca remapeia.
                        valores[nome_coluna] = valor
                        continue
                    novo = mapa_ids.get(tabela_alvo, {}).get(valor)
                    if novo is not None:
                        valores[nome_coluna] = novo
                    elif valor in ids_globais.get(tabela_alvo, ()):
                        # (d) linha de catálogo global — mantém a mesma linha.
                        valores[nome_coluna] = valor
                    else:
                        # Órfã de verdade: nem foi copiada (não pertencia à
                        # origem) nem é global. Não deveria acontecer com
                        # dado consistente — mas trava aqui em vez de gravar
                        # uma FK que aponta pra fazenda errada.
                        if tabela.columns[nome_coluna].nullable:
                            valores[nome_coluna] = None
                            avisos.append(
                                f"{tabela.name}.{nome_coluna} (linha de origem id={id_antigo}) apontava para "
                                f"{tabela_alvo}.id={valor}, que não é da fazenda de origem nem é catálogo global — "
                                "gravado como NULL na cópia."
                            )
                        else:
                            linha_valida = False
                            avisos.append(
                                f"{tabela.name} (linha de origem id={id_antigo}) IGNORADA na cópia: "
                                f"{nome_coluna} exige valor e apontava para {tabela_alvo}.id={valor}, "
                                "que não pôde ser resolvido nem como cópia nem como catálogo global."
                            )
                            break
                    continue
                if nome_coluna in colunas_desambiguar:
                    valores[nome_coluna] = _valor_desambiguado(tabela.name, nome_coluna, valor, id_antigo)
                    continue
                if nome_coluna == COLUNA_ANEXO_STORAGE and valor is not None:
                    # (f) nunca aponta pro objeto real — ver docstring do módulo.
                    valores[nome_coluna] = _marcador_anexo_nao_copiado(tabela.name, id_antigo, valor)
                    contadores["anexos_nao_copiados"] = contadores.get("anexos_nao_copiados", 0) + 1
                    continue
                valores[nome_coluna] = valor

            if not linha_valida:
                orfas_puladas += 1
                continue

            novo_id = conn.execute(sa_insert(tabela).values(**valores).returning(tabela.c[pk])).scalar_one()
            mapa_local[id_antigo] = novo_id
            total_copiado += 1

    if orfas_puladas:
        logger.warning("replicacao_fazenda: %s linha(s) órfã(s) ignoradas em %s", orfas_puladas, tabela.name)
    return total_copiado


def _aplicar_fks_adiadas(
    conn: Connection,
    tabelas: dict[str, Table],
    mapa_ids: dict[str, dict[int, int]],
    ids_globais: dict[str, set[int]],
    fks_adiadas_por_tabela: dict[str, list[tuple[str, str, int]]],
    avisos: list[str],
    *,
    destino_id: int,
) -> None:
    """2ª passada (ver docstring do módulo, seção b/c): agora que toda
    tabela já tem seu mapa (id_antigo -> id_novo) completo, resolve de
    verdade as FKs que entraram NULL na 1ª passada (autorreferência e
    ciclo entre tabelas)."""
    for nome_tabela, entradas in fks_adiadas_por_tabela.items():
        tabela = tabelas[nome_tabela]
        pk = list(tabela.primary_key.columns)[0]
        mapa_local = mapa_ids.get(nome_tabela, {})
        # A FK adiada aponta pra ESTA MESMA tabela nos casos de
        # autorreferência, ou pra outra tabela do ciclo — descobre o alvo
        # pela própria FK da coluna (não pelo nome, genérico de propósito).
        fk_alvo_por_coluna = {fk.parent.name: fk.column.table.name for fk in tabela.foreign_keys}
        for coluna, id_antigo_str, valor_antigo in entradas:
            id_antigo_linha = int(id_antigo_str)
            id_novo_linha = mapa_local.get(id_antigo_linha)
            if id_novo_linha is None:
                continue  # a própria linha foi pulada por órfã — nada a corrigir
            tabela_alvo = fk_alvo_por_coluna[coluna]
            novo_valor = mapa_ids.get(tabela_alvo, {}).get(valor_antigo)
            if novo_valor is None:
                if valor_antigo in ids_globais.get(tabela_alvo, ()):
                    novo_valor = valor_antigo
                else:
                    avisos.append(
                        f"{nome_tabela}.{coluna} (linha id_antigo={id_antigo_linha}) referenciava "
                        f"{tabela_alvo}.id={valor_antigo}, não resolvido na 2ª passada — mantido NULL."
                    )
                    continue
            # Recorte de fazenda DENTRO da consulta, junto da PK: o id novo
            # sempre pertence a uma linha recém-inserida no destino, então o
            # `fazenda_id == destino_id` é redundante hoje — e é justamente
            # por isso que ele fica. Sem ele, esta 2ª passada seria o único
            # UPDATE do módulo capaz de, em caso de mapa de ids errado (bug
            # futuro, sequência de id reiniciada, tabela cujo id não venha do
            # banco), gravar numa linha da fazenda de ORIGEM — violando a
            # regra 1 sem nenhum aviso. Com o recorte, escrever na origem é
            # impossível por construção, não por confiança no mapa.
            conn.execute(
                sa_update(tabela)
                .where(pk == id_novo_linha, tabela.c.fazenda_id == destino_id)
                .values(**{coluna: novo_valor})
            )


# ---------------------------------------------------------------------------
# A TRAVA DURA (regra 2) — a única coisa neste módulo que, se falhar, apaga a
# fazenda de um cliente de verdade. Por isso ela NÃO mora só na porta de
# entrada da rotina: é uma função própria, chamada tanto no começo de
# `sincronizar_fazenda_teste_destrutivo` (para recusar cedo, com mensagem
# boa) quanto DENTRO de `_apagar_destino`, imediatamente antes do primeiro
# DELETE — o próprio caminho de escrita.
#
# Por que repetir a checagem duas vezes num arquivo só? Porque uma validação
# feita apenas na entrada é uma convenção, não uma trava: basta alguém, um
# dia, chamar `_apagar_destino` de outro lugar (um comando de manutenção, um
# "limpar sandbox" sem cópia, uma refatoração que separe apagar de copiar)
# para o destino ser apagado sem nunca passar pela porta da frente. Duplicar
# a checagem custa um SELECT e torna esse acidente impossível por construção.
#
# E por que ler `eh_teste` com SQL cru pela `Connection` em vez de usar o
# objeto `Fazenda` do ORM? Porque a `Session` responde `session.get()` a
# partir do mapa de identidade — devolve o objeto que já está em memória,
# possivelmente com `eh_teste` alterado e ainda não gravado. A fonte de
# verdade tem que ser o BANCO, e ainda por cima lido pela MESMA conexão que
# vai executar os DELETEs (mesma transação, mesma visão de dados): não
# existe janela entre "conferi" e "apaguei".
# ---------------------------------------------------------------------------
def _exigir_destino_de_teste(conn: Connection, destino_id: int) -> None:
    """Estoura 409 se a fazenda `destino_id` não existir ou não estiver
    marcada `eh_teste = True` no banco. Incondicional: não há parâmetro,
    variável de ambiente nem flag que pule esta verificação."""
    tabela_fazenda = Fazenda.__table__
    linha = conn.execute(
        sa_select(tabela_fazenda.c.nome, tabela_fazenda.c.eh_teste).where(tabela_fazenda.c.id == destino_id)
    ).first()
    if linha is None:
        raise SincronizacaoInvalidaError(f"Fazenda de destino (id={destino_id}) não existe.")
    nome, eh_teste = linha
    if not eh_teste:
        raise SincronizacaoInvalidaError(
            f'A fazenda de destino ("{nome}") não está marcada como fazenda de TESTE '
            "(Fazenda.eh_teste=False) — a sincronização destrutiva só pode gravar em cima de uma "
            "fazenda de teste, nunca de uma fazenda-cliente real."
        )


def _apagar_destino(
    conn: Connection,
    tabelas: dict[str, Table],
    ordem: list[str],
    colunas_adiadas_por_tabela: dict[str, list[str]],
    destino_id: int,
) -> None:
    """(d) regra 4 — apaga TUDO do destino antes de copiar. Primeiro anula
    TODA coluna "adiada" (autorreferência, ex.: categoria_pai_id, E as duas
    pontas de um ciclo entre tabelas, ex.: estoque.alimento_id /
    alimento.estoque_preferido_id — mesmo conjunto de colunas calculado por
    `_ordenar_com_quebra_de_ciclo`) pra nenhum DELETE esbarrar numa FK que
    aponta pra uma linha que está prestes a ser apagada; só depois apaga
    tabela por tabela na ordem REVERSA da topológica (filhas antes de pais).

    Primeira linha do corpo, antes de qualquer escrita: a trava dura de novo
    (ver `_exigir_destino_de_teste` acima). É aqui que ela realmente importa
    — este é o ponto onde o dado morre.
    """
    _exigir_destino_de_teste(conn, destino_id)

    for nome_tabela, colunas in colunas_adiadas_por_tabela.items():
        tabela = tabelas[nome_tabela]
        conn.execute(
            sa_update(tabela).where(tabela.c.fazenda_id == destino_id).values(**{c: None for c in colunas})
        )
    for nome_tabela in reversed(ordem):
        tabela = tabelas[nome_tabela]
        conn.execute(sa_delete(tabela).where(tabela.c.fazenda_id == destino_id))


def sincronizar_fazenda_teste_destrutivo(
    session: Session, *, origem_id: int, destino_id: int
) -> ResultadoSincronizacao:
    """Refaz a Fazenda de TESTE (`destino_id`) como uma cópia completa da
    fazenda de origem — APAGANDO TUDO o que já existia no destino antes de
    copiar (regra 4). Sentido único: nunca escreve na origem (regra 1).

    Chamado só pelo endpoint POST /painel-cowdata/fazendas/{destino_id}/
    sincronizar (`exigir_area_painel_cowdata("fazendas")`, ver
    fazenda/api/routers/painel_cowdata_sincronizacao.py) — não é uma função
    de uso geral, é ESPECIFICAMENTE a rotina destrutiva do sandbox.
    """
    t0 = time.monotonic()

    if origem_id == destino_id:
        raise SincronizacaoInvalidaError("Origem e destino não podem ser a mesma fazenda.")

    # Regras 1 e 6: tudo dentro de UMA transação (conn é a MESMA conexão que
    # a Session já abriu; nenhum commit parcial acontece até o fim da
    # função — qualquer exceção sobe e o `with` da Session reverte tudo).
    # Pegamos a conexão ANTES de qualquer validação porque a trava dura tem
    # que ser lida pela mesma conexão que fará as escritas (ver
    # `_exigir_destino_de_teste`), não pelo mapa de identidade da Session.
    conn = session.connection()

    # Regra 2 — a trava dura, aqui só para recusar cedo e com mensagem boa.
    # Ela é aplicada DE NOVO, incondicionalmente, dentro de `_apagar_destino`,
    # que é o caminho de escrita de verdade — nenhuma das duas é dispensável
    # (ver o comentário longo em `_exigir_destino_de_teste`).
    _exigir_destino_de_teste(conn, destino_id)

    origem = session.get(Fazenda, origem_id)
    if not origem:
        raise SincronizacaoInvalidaError(f"Fazenda de origem (id={origem_id}) não existe.")
    # Nunca None: `_exigir_destino_de_teste` acabou de provar, pela conexão
    # desta mesma transação, que a linha existe. Carregado só para o nome
    # aparecer no log do fim da função.
    destino = session.get(Fazenda, destino_id)

    tabelas = _tabelas_fazenda()
    ordem, colunas_adiadas_por_tabela = _ordenar_com_quebra_de_ciclo(tabelas)

    avisos: list[str] = []

    _apagar_destino(conn, tabelas, ordem, colunas_adiadas_por_tabela, destino_id)

    ids_globais = _ids_globais_por_tabela(conn, tabelas)
    mapa_ids: dict[str, dict[int, int]] = {}
    fks_adiadas_globais: dict[str, list[tuple[str, str, int]]] = {}
    contadores: dict[str, int] = {}
    total_linhas = 0

    for nome_tabela in ordem:
        tabela = tabelas[nome_tabela]
        colunas_desambiguar = _colunas_para_desambiguar(tabela)
        copiadas = _copiar_tabela(
            conn,
            tabela,
            origem_id=origem_id,
            destino_id=destino_id,
            tabelas=tabelas,
            ids_globais=ids_globais,
            mapa_ids=mapa_ids,
            colunas_desambiguar=colunas_desambiguar,
            colunas_adiadas=colunas_adiadas_por_tabela.get(nome_tabela, []),
            fks_adiadas_globais=fks_adiadas_globais,
            avisos=avisos,
            contadores=contadores,
        )
        total_linhas += copiadas

    _aplicar_fks_adiadas(conn, tabelas, mapa_ids, ids_globais, fks_adiadas_globais, avisos, destino_id=destino_id)

    if contadores.get("anexos_nao_copiados"):
        # (f) só avisa se de fato existia algum anexo pra avisar — ver
        # docstring do módulo pra justificativa completa da decisão.
        avisos.insert(
            0,
            f"{contadores['anexos_nao_copiados']} anexo(s)/foto(s)/documento(s) (Supabase Storage) tiveram só o "
            "REGISTRO copiado — o arquivo físico NÃO foi duplicado. O caminho foi substituído por um marcador "
            "que nunca aponta para o objeto real de produção (ver decisão no relatório da tarefa).",
        )

    session.flush()

    duracao = time.monotonic() - t0
    logger.info(
        "replicacao_fazenda: %s -> %s, %d tabelas, %d linhas, %.1fs",
        origem.nome, destino.nome, len(tabelas), total_linhas, duracao,
    )
    return ResultadoSincronizacao(tabelas=len(tabelas), linhas_copiadas=total_linhas, duracao_s=duracao, avisos=avisos)
