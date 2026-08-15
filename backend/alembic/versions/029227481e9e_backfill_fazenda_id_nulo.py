"""backfill fazenda_id nulo

Fecha o Passo 2 do retrofit "fazenda_id nunca nulo" (PR claude/fazenda-id-raiz):
preenche todo `fazenda_id` NULO que sobrou nas ~147 tabelas do multi-tenant
piloto — resíduo de escritas feitas por token legado (sem "fid"), usuário sem
fazenda vinculada, ou chamada direta fora do ciclo HTTP (telegram_fluxos.py),
que é exatamente a causa raiz fechada no Passo 1 (fazenda.auth::
resolver_fazenda_id_escrita). Sem isso a Agenda/Central de Protocolos não
podem voltar ao filtro estrito por fazenda_id (Passo 3) sem esconder dado
legado.

Estratégia por tabela, NESTA ordem de preferência (idêntica à docstring do
PR):

  a) DERIVAR DO PAI — quando a linha tem uma FK para outra tabela que já tem
     fazenda_id (ex.: ProtocoloInducaoAplicacao/Medicamento -> Lancamento;
     ProtocoloSanitarioEtapa -> ProtocoloSanitario; qualquer registro de
     folha/férias/13º/rescisão/vale/empreitada/contrato/diária -> Pessoa).
     É a fonte mais confiável: não depende de quantas fazendas existem.
  b) FAZENDA ÚNICA — o que sobrar nulo depois de (a): se a instalação tem
     exatamente UMA fazenda REAL (ignorando a fazenda "lógica" da CowData,
     `eh_empresa_cowdata=True` — ver fazenda/models/multitenant.py), atribui
     essa. É o caso de hoje: preenchimento trivial, sem ambiguidade.
  c) NÃO ADIVINHA — o que ainda estiver nulo (0 ou 2+ fazendas reais e sem
     pai pra derivar) fica nulo mesmo, e entra no relatório final impresso
     por `alembic upgrade` — chutar o dono do registro é pior que deixar
     pendente (decisão explícita do dono do produto).

Cada tabela roda (a) e depois (b) sobre o que sobrou; o total afetado por
cada estratégia é contado e impresso ao final (ver `_relatorio`).

Revision ID: 029227481e9e
Revises: 39bcd3f22a95
Create Date: 2026-08-11 20:27:34.438062

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '029227481e9e'
down_revision: Union[str, Sequence[str], None] = '39bcd3f22a95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# (a) Derivar do pai — (tabela_filha, coluna_fk_na_filha, tabela_pai).
# ORDEM IMPORTA: uma filha só deriva corretamente se o próprio pai já estiver
# preenchido — por isso os "cabeçalhos" (protocolo/lançamento/pessoa/…) vêm
# antes de quem referencia o cabeçalho, e cadeias de 2 elos (ex.: fatura de
# cartão -> cartão; lançamento de cartão -> fatura) respeitam a ordem.
# ---------------------------------------------------------------------------
_DERIVAR_DO_PAI: list[tuple[str, str, str]] = [
    # Protocolo IATF
    ('protocolo_iatf_etapa', 'protocolo_id', 'protocolo_iatf'),
    ('protocolo_iatf_lancamento', 'protocolo_id', 'protocolo_iatf'),
    ('protocolo_iatf_aplicacao', 'lancamento_id', 'protocolo_iatf_lancamento'),
    ('protocolo_iatf_hormonio', 'lancamento_id', 'protocolo_iatf_lancamento'),
    # Protocolo sanitário — ProtocoloSanitarioEtapa é a tabela "molde" citada
    # na auditoria da Agenda (agenda.py) como a que nunca grava fazenda_id
    # na prática; aqui ela ganha o valor do protocolo-pai mesmo assim (não
    # muda o filtro de leitura — Passo 3 continua sem filtrar esta tabela
    # direto por fazenda_id, só corrige o dado parado).
    ('protocolo_sanitario_etapa', 'protocolo_id', 'protocolo_sanitario'),
    ('protocolo_sanitario_lancamento', 'protocolo_id', 'protocolo_sanitario'),
    ('protocolo_sanitario_aplicacao', 'lancamento_id', 'protocolo_sanitario_lancamento'),
    # Protocolo de indução de lactação — é o par citado no sintoma original
    # (D6 sumindo da Agenda).
    ('protocolo_inducao_lactacao_etapa', 'protocolo_id', 'protocolo_inducao_lactacao'),
    ('protocolo_inducao_lancamento', 'protocolo_id', 'protocolo_inducao_lactacao'),
    ('protocolo_inducao_medicamento', 'lancamento_id', 'protocolo_inducao_lancamento'),
    ('protocolo_inducao_aplicacao', 'lancamento_id', 'protocolo_inducao_lancamento'),
    # Protocolo customizado
    ('protocolo_customizado_etapa', 'protocolo_id', 'protocolo_customizado'),
    ('protocolo_customizado_lancamento', 'protocolo_id', 'protocolo_customizado'),
    ('protocolo_customizado_aplicacao', 'lancamento_id', 'protocolo_customizado_lancamento'),
    # Lida
    ('lida_etapa', 'lida_id', 'lida'),
    ('lida_lancamento', 'lida_id', 'lida'),
    ('lida_aplicacao', 'lancamento_id', 'lida_lancamento'),
    # Pessoal — toda ficha de funcionário/prestador referencia uma Pessoa,
    # que já carrega fazenda_id (cadastro único por fazenda).
    ('folha_pagamento', 'pessoa_id', 'pessoa'),
    ('ferias_funcionario', 'pessoa_id', 'pessoa'),
    ('decimo_terceiro', 'pessoa_id', 'pessoa'),
    ('rescisao_funcionario', 'pessoa_id', 'pessoa'),
    ('vale_funcionario', 'pessoa_id', 'pessoa'),
    ('vale_avulso', 'pessoa_id', 'pessoa'),
    ('empreitada', 'pessoa_id', 'pessoa'),
    ('contrato', 'pessoa_id', 'pessoa'),
    ('diaria', 'pessoa_id', 'pessoa'),
    ('vale_parcela', 'pessoa_id', 'pessoa'),
    ('empreitada_parcela', 'empreitada_id', 'empreitada'),
    ('empreitada_etapa', 'empreitada_id', 'empreitada'),
    ('contrato_parcela', 'contrato_id', 'contrato'),
    ('diaria_pagamento', 'diaria_id', 'diaria'),
    ('diaria_auditoria', 'diaria_id', 'diaria'),
    ('diaria_dia', 'diaria_id', 'diaria'),
    # Financeiro
    ('planejamento_item', 'cenario_id', 'planejamento_cenario'),
    ('pedido_item', 'pedido_id', 'pedido'),
    ('manutencao_patrimonio', 'patrimonio_id', 'patrimonio'),
    ('fatura_cartao', 'cartao_id', 'cartao_credito'),
    ('lancamento_cartao', 'fatura_id', 'fatura_cartao'),
]

# Todas as demais tabelas com fazenda_id (Optional[int]) espalhadas pelos 19
# arquivos de fazenda/models/ — sem pai claro pra derivar (catálogos de
# cadastro, cabeçalhos-raiz, ou ligadas por texto — numero_matriz/
# numero_lancamento — não por id, o que tornaria o join ambíguo entre
# fazendas e por isso NÃO é usado aqui; só ganham a estratégia (b)/(c)).
_TABELAS_SEM_PAI: list[str] = [
    'safra', 'alerta_indicador',
    'categoria_alimento', 'alimento', 'dieta', 'dieta_lancamento', 'dieta_item_programado',
    'ingrediente_ms', 'tabela_nutricional_produto', 'tabela_nutricional_valor',
    'analise_bromatologica', 'dieta_registro_real', 'alimentacao_estado',
    'animal', 'lote', 'movimento_lote', 'motivo_baixa', 'motivo_venda', 'raca',
    'grau_sangue_cadastro', 'motivo_movimentacao', 'parametro_sugestao_movimentacao',
    'baixa_animal', 'compra_animal', 'venda_animal', 'comissao_corretagem',
    'documento_arquivado', 'chamado',
    'estoque', 'local_armazenamento', 'categoria_estoque', 'finalidade_estoque',
    'unidade_estoque', 'unidade_embalagem_estoque', 'unidade_medida_embalagem_estoque',
    'fornecedor', 'movimento_estoque', 'estoque_semen', 'compra_semen',
    'filtro_salvo',
    'conta_gerencial', 'lancamento_item', 'lancamento_anexo', 'plano_conta_gerencial',
    'conta_corrente', 'centro_custo', 'tipo_documento', 'forma_pagamento_cadastro',
    'orcamento_item', 'planejamento_cenario', 'pedido', 'patrimonio',
    'lancamento_recorrente', 'cartao_credito', 'curva_abc',
    'alimento_nutricional',
    'foto_campo',
    'idempotencia_chave',
    'lida',
    'tipo_pessoa', 'pessoa', 'parametro_diaria_padrao', 'guia_folha_encargo',
    'controle_leiteiro', 'pesagem_corporal', 'agendamento_pesagem', 'qualidade_leite',
    'entrega_leite_mensal', 'secagem', 'faixa_bonificacao_qualidade',
    'protocolo_customizado',
    'ocorrencia_clinica', 'meta_recria', 'peso_alvo_idade', 'fase_recria',
    'janela_ponto_critico', 'benchmark_recria', 'registro_cocho', 'categoria_manejo',
    'servico', 'tipo_servico_reprodutivo', 'metodo_servico_reprodutivo', 'protocolo_iatf',
    'parto', 'colostragem_bezerra',
    'sanidade', 'aplicacao_agendada', 'principio_ativo', 'medicamento_comercial', 'doenca',
    'indicacao_terapeutica', 'exame_definicao', 'exame_resultado', 'evento_sanitario',
    'calendario_sanitario', 'cronograma_sanitario', 'cronograma_sanitario_animal',
    'servico_cadastro', 'protocolo_sanitario', 'protocolo_inducao_lactacao',
    'parametro_fazenda', 'lancamento_pendente', 'agenda_manual', 'evento_realizado',
    'solicitacao_exclusao', 'portal_mensagem', 'parametro_manual_fazenda',
    'assistente_ensinamento', 'sugestao_manual_fazenda',
]


def _fazenda_real_unica(conn) -> int | None:
    """Id da única fazenda REAL cadastrada (ignora a fazenda "lógica" da
    CowData, eh_empresa_cowdata=True), ou None se não houver exatamente uma
    — nesse caso a estratégia (b) não se aplica a nenhuma tabela e o que
    sobrar fica pendente (estratégia c)."""
    linhas = conn.execute(sa.text(
        "SELECT id FROM fazenda WHERE eh_empresa_cowdata IS NOT TRUE"
    )).fetchall()
    return linhas[0][0] if len(linhas) == 1 else None


def _derivar_do_pai(conn, tabela: str, coluna_fk: str, tabela_pai: str) -> int:
    resultado = conn.execute(sa.text(
        f"UPDATE {tabela} SET fazenda_id = ("
        f"  SELECT p.fazenda_id FROM {tabela_pai} p WHERE p.id = {tabela}.{coluna_fk}"
        f") WHERE fazenda_id IS NULL AND {coluna_fk} IS NOT NULL AND EXISTS ("
        f"  SELECT 1 FROM {tabela_pai} p WHERE p.id = {tabela}.{coluna_fk} AND p.fazenda_id IS NOT NULL"
        f")"
    ))
    return resultado.rowcount or 0


def _preencher_fazenda_unica(conn, tabela: str, fazenda_id: int) -> int:
    resultado = conn.execute(
        sa.text(f"UPDATE {tabela} SET fazenda_id = :fid WHERE fazenda_id IS NULL"),
        {"fid": fazenda_id},
    )
    return resultado.rowcount or 0


def _contar_nulos(conn, tabela: str) -> int:
    return conn.execute(sa.text(f"SELECT COUNT(*) FROM {tabela} WHERE fazenda_id IS NULL")).scalar() or 0


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    fazenda_unica_id = _fazenda_real_unica(conn)

    # Nem toda tabela com fazenda_id no model chegou a ser criada por uma
    # migração Alembic — drift pré-existente, alheio a este PR (ex.:
    # protocolo_iatf/protocolo_iatf_etapa só existem via
    # SQLModel.metadata.create_all, usado em dev/teste; nunca ganharam
    # op.create_table). UPDATE numa tabela inexistente derrubaria a migração
    # inteira num banco que só tem o schema do Alembic — pula essas e avisa,
    # em vez de falhar.
    tabelas_existentes = set(sa.inspect(conn).get_table_names())

    # Todas as tabelas tocadas nesta migração — pai primeiro (na ordem já
    # declarada em _DERIVAR_DO_PAI), depois as sem pai (ordem não importa).
    tabelas_com_pai = [t for t, _, _ in _DERIVAR_DO_PAI]
    todas_as_tabelas = [t for t in tabelas_com_pai + _TABELAS_SEM_PAI if t in tabelas_existentes]
    ausentes = sorted(set(tabelas_com_pai + _TABELAS_SEM_PAI) - tabelas_existentes)

    por_pai: dict[str, int] = {}
    for tabela, coluna_fk, tabela_pai in _DERIVAR_DO_PAI:
        if tabela not in tabelas_existentes or tabela_pai not in tabelas_existentes:
            continue
        por_pai[tabela] = _derivar_do_pai(conn, tabela, coluna_fk, tabela_pai)

    por_fallback: dict[str, int] = {}
    pendente: dict[str, int] = {}
    if fazenda_unica_id is not None:
        for tabela in todas_as_tabelas:
            por_fallback[tabela] = _preencher_fazenda_unica(conn, tabela, fazenda_unica_id)
    for tabela in todas_as_tabelas:
        n = _contar_nulos(conn, tabela)
        if n:
            pendente[tabela] = n

    # Relatório — Alembic imprime stdout/stderr de upgrade() direto no
    # terminal de quem roda `alembic upgrade head`; é o único jeito de
    # auditar depois quantas linhas foram tocadas e por qual estratégia,
    # já que o downgrade não desfaz nada (ver docstring de downgrade()).
    total_pai = sum(por_pai.values())
    total_fallback = sum(por_fallback.values())
    total_pendente = sum(pendente.values())
    print(f"[fazenda_id backfill] fazenda real única: {fazenda_unica_id!r}")
    if ausentes:
        print(f"[fazenda_id backfill] tabela(s) do model sem migração de criação (drift pré-existente, puladas): {ausentes}")
    print(f"[fazenda_id backfill] preenchidas via PAI: {total_pai} linha(s) em {sum(1 for v in por_pai.values() if v)} tabela(s)")
    for tabela, n in por_pai.items():
        if n:
            print(f"  - {tabela}: {n} via pai")
    print(f"[fazenda_id backfill] preenchidas via FAZENDA ÚNICA: {total_fallback} linha(s) em {sum(1 for v in por_fallback.values() if v)} tabela(s)")
    for tabela, n in por_fallback.items():
        if n:
            print(f"  - {tabela}: {n} via fazenda única")
    if pendente:
        print(f"[fazenda_id backfill] AINDA NULO (não adivinhado): {total_pendente} linha(s) em {len(pendente)} tabela(s) — "
              f"revisar manualmente (2+ fazendas reais e sem pai pra derivar):")
        for tabela, n in pendente.items():
            print(f"  - {tabela}: {n} linha(s) pendente(s)")
    else:
        print("[fazenda_id backfill] nenhuma linha ficou nula — preenchimento completo.")


def downgrade() -> None:
    """Downgrade schema."""
    # Não há como desfazer um backfill sem recriar o próprio bug que esta
    # migração corrige (registro voltando a ficar sem fazenda_id) — e não há
    # como distinguir "fazenda_id que já veio preenchido" de "fazenda_id que
    # esta migração preencheu" pra reverter só o que foi tocado. No-op de
    # propósito.
    pass
