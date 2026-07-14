"""
Conexão com o banco de dados e criação das tabelas.
Usa SQLite em desenvolvimento, PostgreSQL em produção (via DATABASE_URL).
"""
import logging

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from fazenda.config import settings

logger = logging.getLogger(__name__)

# Railway/Heroku entregam DATABASE_URL como 'postgres://', que o SQLAlchemy 2.0
# não reconhece (Can't load plugin: sqlalchemy.dialects:postgres). Normaliza.
DATABASE_URL = settings.database_url
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_sqlite = "sqlite" in DATABASE_URL

engine_kwargs: dict = {
    "echo": settings.environment == "development",
}

if is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL: pool pre-ping para reconectar automaticamente
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_size"] = 5
    engine_kwargs["max_overflow"] = 10

engine = create_engine(DATABASE_URL, **engine_kwargs)


# Migração leve: colunas adicionadas a tabelas que já podem existir em produção.
# O create_all não altera tabelas existentes, então adicionamos manualmente.
_COLUNAS_NOVAS: dict[str, list[tuple[str, str]]] = {
    "controle_leiteiro": [
        ("raca", "VARCHAR"), ("ordenha1_kg", "FLOAT"), ("ordenha2_kg", "FLOAT"), ("ordenha3_kg", "FLOAT"),
        ("usuario_id", "INTEGER"),
    ],
    "servico": [("retoque", "BOOLEAN"), ("data_reconfirmacao", "DATE"), ("diagnostico_reconfirmacao", "VARCHAR"), ("metodo_diagnostico", "VARCHAR"), ("inseminador", "VARCHAR"), ("usuario_id", "INTEGER")],
    "parto": [("numero_cria_1", "VARCHAR"), ("numero_cria_2", "VARCHAR"), ("gemelar_sexo", "VARCHAR"), ("usuario_id", "INTEGER")],
    "colostragem_bezerra": [
        ("hora_parto", "VARCHAR"), ("hora_colostro", "VARCHAR"), ("peso_nascer_kg", "FLOAT"),
        ("proteina_serica", "FLOAT"), ("apenas_colostro_po", "BOOLEAN"), ("usuario_id", "INTEGER"),
    ],
    "qualidade_leite": [("nul", "FLOAT"), ("usuario_id", "INTEGER")],
    "pesagem_corporal": [("fase", "VARCHAR"), ("usuario_id", "INTEGER")],
    "dieta_lancamento": [("base_quantidade", "VARCHAR"), ("leite_bezerros_kg_dia", "FLOAT"), ("usuario_id", "INTEGER")],
    "dieta_item_programado": [("base", "VARCHAR"), ("ms_pct", "FLOAT")],
    "dieta_registro_real": [("usuario_id", "INTEGER")],
    "protocolo_iatf_lancamento": [("retroativo", "BOOLEAN"), ("usuario_id", "INTEGER")],
    "sanidade": [("unidade", "VARCHAR"), ("via", "VARCHAR"), ("responsavel", "VARCHAR"), ("usuario_id", "INTEGER")],
    "aplicacao_agendada": [("usuario_id", "INTEGER")],
    "entrega_leite_mensal": [("usuario_id", "INTEGER")],
    "vale_funcionario": [("usuario_id", "INTEGER")],
    "movimento_estoque": [("usuario_id", "INTEGER")],
    "movimento_lote": [("usuario_id", "INTEGER")],
    "compra_animal": [("usuario_id", "INTEGER")],
    "ocorrencia_clinica": [("usuario_id", "INTEGER")],
    "registro_cocho": [("usuario_id", "INTEGER")],
    "animal": [
        ("sexo", "VARCHAR"), ("eh_semen", "BOOLEAN"), ("grupo_manual", "BOOLEAN"),
        ("grau_sangue", "VARCHAR"),
        ("nome", "VARCHAR"), ("sisbov", "VARCHAR"), ("mae_numero", "VARCHAR"), ("mae_nome", "VARCHAR"),
        ("proprietario", "VARCHAR"), ("valor", "FLOAT"), ("data_entrada", "DATE"),
        ("motivo_baixa", "VARCHAR"), ("data_baixa", "DATE"), ("observacoes", "VARCHAR"),
        ("a_descartar", "BOOLEAN DEFAULT false"), ("excluir_bst", "BOOLEAN DEFAULT false"),
    ],
    "estoque": [
        ("unidade_embalagem", "VARCHAR"), ("medida_embalagem", "VARCHAR"), ("quantidade_embalagem", "FLOAT"),
        ("fornecedor_id", "INTEGER"),
        ("ativo", "BOOLEAN"), ("observacao", "VARCHAR"), ("carencia_dias", "INTEGER"),
        ("centro_custo_padrao", "VARCHAR"), ("conta_gerencial_despesa_padrao", "VARCHAR"),
        ("conta_gerencial_receita_padrao", "VARCHAR"), ("exibir_necessidade_compra_agenda", "BOOLEAN"),
        ("gera_receita", "BOOLEAN"),
        ("estocavel", "BOOLEAN"), ("considerar_rmca", "BOOLEAN"),
        ("data_inicio_controle", "DATE"),
        ("principio_ativo", "VARCHAR"), ("classificacao_medicamento", "VARCHAR"),
        ("principio_ativo_id", "INTEGER"), ("medicamento_comercial_id", "INTEGER"),
        ("laboratorio", "VARCHAR"),
        ("volume_por_apresentacao", "FLOAT"), ("volume_unidade", "VARCHAR"),
        ("estoque_inicializado", "BOOLEAN"),
    ],
    "principio_ativo": [
        ("categoria", "VARCHAR"),
        ("categoria_software", "VARCHAR"), ("uso_principal", "VARCHAR"), ("justificativa", "VARCHAR"),
        ("doenca_id", "INTEGER"), ("eh_biologico", "BOOLEAN DEFAULT false"),
        ("unidade_base", "VARCHAR"), ("unidade_apresentacao", "VARCHAR"),
        ("estoque_minimo_apresentacoes", "FLOAT DEFAULT 1"),
    ],
    "estoque_semen": [
        ("naab", "VARCHAR"),
        ("valor_unitario", "FLOAT"), ("local_armazenamento", "VARCHAR"),
    ],
    "touro": [("nome_completo", "VARCHAR"), ("dados_extra", "TEXT")],
    "evento_sanitario": [
        ("tipo_agendamento", "VARCHAR DEFAULT 'nenhum'"), ("categoria_alvo", "VARCHAR"), ("doenca_id", "INTEGER"),
        ("data_primeiro", "DATE"), ("frequencia_valor", "INTEGER"), ("frequencia_unidade", "VARCHAR"),
        ("gatilho", "VARCHAR"), ("gatilho_lote", "VARCHAR"), ("gatilho_idade_meses", "INTEGER"), ("offset_dias", "INTEGER"),
        ("produto_padrao", "VARCHAR"), ("dose_padrao", "FLOAT"), ("unidade_padrao", "VARCHAR"), ("via_padrao", "VARCHAR"),
        ("categoria_preventiva", "VARCHAR"), ("agenda_dias_antes", "INTEGER"),
    ],
    "calendario_sanitario": [("veterinario", "VARCHAR"), ("unidade", "VARCHAR")],
    "protocolo_sanitario_etapa": [("criterio_tipo", "VARCHAR DEFAULT 'medicamento'"), ("observacao", "TEXT")],
    "protocolo_sanitario_aplicacao": [("produto", "VARCHAR")],
    "protocolo_sanitario_lancamento": [
        ("grau_mastite", "INTEGER"), ("agente", "VARCHAR"), ("del_no_caso", "INTEGER"),
        ("ccs_ultima", "FLOAT"), ("recidiva", "BOOLEAN"), ("curada", "BOOLEAN"), ("usuario_id", "INTEGER"),
    ],
    "fornecedor": [("categoria", "VARCHAR")],
    "pessoa": [("salario_base", "FLOAT")],
    "usuario": [("permissoes", "VARCHAR")],
    "conta_gerencial": [
        ("numero_lancamento", "VARCHAR"),
        ("data_prevista_entrada", "DATE"),
        ("data_pedido", "DATE"),
        ("entregue", "BOOLEAN"),
        ("tipo_documento", "VARCHAR"),
        ("numero_documento_pagamento", "VARCHAR"),
        ("conta_bancaria", "VARCHAR"),
        ("quantidade", "FLOAT"),
        ("valor_unitario", "FLOAT"),
        ("desconto_acrescimo", "FLOAT"),
        ("parcela_num", "INTEGER"),
        ("parcela_total", "INTEGER"),
        ("responsavel", "VARCHAR"),
        ("origem", "VARCHAR"),
        ("desconto_nota", "FLOAT"),
        ("acrescimo_nota", "FLOAT"),
        ("forma_pagamento", "VARCHAR"),
        ("data_vencimento_cartao", "DATE"),
        ("usuario_id", "INTEGER"),
    ],
    "plano_conta_gerencial": [
        ("rmca_receita_leite", "BOOLEAN"),
        ("rmca_custo_alimentacao", "BOOLEAN"),
    ],
    "lancamento_item": [("tipo_item", "VARCHAR")],
    "folha_pagamento": [
        ("recorrente", "BOOLEAN"),
        ("dia_vencimento", "INTEGER"),
        ("origem_recorrencia_id", "INTEGER"),
        ("numero_lancamento_gerado", "VARCHAR"),
        # Retenção INSS/IR — DEFAULT 0 para os lançamentos antigos, porque o
        # modelo e a API tratam esses campos como float obrigatório (não-nulo).
        ("percentual_inss", "FLOAT DEFAULT 0"),
        ("percentual_ir", "FLOAT DEFAULT 0"),
        ("valor_inss", "FLOAT DEFAULT 0"),
        ("valor_ir", "FLOAT DEFAULT 0"),
        ("valor_vale", "FLOAT DEFAULT 0"),
        ("usuario_id", "INTEGER"),
    ],
    "lote": [
        ("status_lactacao", "VARCHAR"),
        ("categorias", "VARCHAR"),
        ("pre_parto", "BOOLEAN"),
        ("peso_min", "FLOAT"),
        ("peso_max", "FLOAT"),
        ("dias_para_parto_min", "INTEGER"),
        ("dias_para_parto_max", "INTEGER"),
        ("em_tratamento", "BOOLEAN"),
        ("idade_dias_min", "INTEGER"),
        ("idade_dias_max", "INTEGER"),
        ("novilhas_inseminadas", "BOOLEAN"),
        ("novilhas_gestantes", "BOOLEAN"),
    ],
    "baixa_animal": [
        ("tipo_valor", "VARCHAR"),
        ("numero_lancamento_gerado", "VARCHAR"),
        ("venda_recria", "BOOLEAN"),
        ("usuario_id", "INTEGER"),
    ],
    "agenda_manual": [
        ("lotes", "VARCHAR"),
        ("tipo_evento", "VARCHAR"),
        ("recorrente", "BOOLEAN"),
        ("intervalo_dias", "INTEGER"),
        ("intervalo_meses", "INTEGER"),
        ("origem_recorrencia_id", "INTEGER"),
        ("apenas_admin", "BOOLEAN DEFAULT false"),
        ("link", "VARCHAR"),
        ("usuario_id", "INTEGER"),
    ],
}


def _migrar_colunas() -> None:
    """Cada coluna é adicionada na sua própria savepoint: um erro numa (ex.:
    sintaxe incompatível com o dialeto do banco) só pula aquela coluna — não
    aborta a transação inteira e não derruba o startup do app (já aconteceu:
    um `BOOLEAN DEFAULT 0` incompatível com Postgres travou a inicialização
    inteira em produção)."""
    insp = inspect(engine)
    tabelas = set(insp.get_table_names())
    with engine.begin() as conn:
        for tabela, colunas in _COLUNAS_NOVAS.items():
            if tabela not in tabelas:
                continue  # create_all já criou com o schema completo
            existentes = {c["name"] for c in insp.get_columns(tabela)}
            for nome, tipo in colunas:
                if nome not in existentes:
                    try:
                        with conn.begin_nested():
                            conn.execute(text(f'ALTER TABLE {tabela} ADD COLUMN {nome} {tipo}'))
                    except Exception:
                        logger.exception(
                            "Falha ao adicionar a coluna %s.%s (%s) — seguindo com as demais migrações.",
                            tabela, nome, tipo,
                        )


# Colunas que precisam virar BIGINT no Postgres: ids de chat do Telegram
# passam de 2,1 bilhões e estouram o INTEGER (32 bits). No SQLite não é preciso
# (o INTEGER já é de 64 bits).
_COLUNAS_BIGINT: list[tuple[str, str]] = [
    ("telegram_pendente", "chat_id"),
    ("telegram_sessao", "chat_id"),
    ("lancamento_pendente", "solicitante_chat_id"),
]


def _migrar_tipos_bigint() -> None:
    if is_sqlite:
        return
    insp = inspect(engine)
    tabelas = set(insp.get_table_names())
    with engine.begin() as conn:
        for tabela, coluna in _COLUNAS_BIGINT:
            if tabela not in tabelas:
                continue
            try:
                conn.execute(text(f"ALTER TABLE {tabela} ALTER COLUMN {coluna} TYPE BIGINT"))
            except Exception:
                pass  # já é BIGINT, ou o banco não deixou — segue o jogo


def create_db_and_tables() -> None:
    """Cria as tabelas (idempotente) e aplica migrações leves de colunas."""
    SQLModel.metadata.create_all(engine)
    _migrar_colunas()
    _migrar_tipos_bigint()


def get_session():
    """Dependency injection do FastAPI para obter uma sessão de banco."""
    with Session(engine) as session:
        yield session
