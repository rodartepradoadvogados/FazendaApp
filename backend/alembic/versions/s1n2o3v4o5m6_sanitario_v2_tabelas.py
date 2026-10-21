"""sanitário preventivo v2: tabelas novas (caixas), catálogo central e padrão de fábrica

Migração B do plano "Sanitário Preventivo v2" (fase F3). Cria as 18 tabelas
`sanitario_*` (o prefixo é obrigatório: "caixa" já é nome do financeiro) —
ver fazenda/models/sanitario_preventivo.py para o significado de cada uma.

  - `fazenda_id NOT NULL` em todas, menos as globais do cockpit
    (`sanitario_catalogo`, `sanitario_catalogo_versao`, `sanitario_norma`);
  - UNIQUE(id, fazenda_id) nas tabelas pai e, no POSTGRES, FKs compostas
    `(x_id, fazenda_id) -> pai(id, fazenda_id)` (padrão de 472f92e0860b).
    Pai externo (animal, estoque, pessoa, categoria_manejo, lote_estoque,
    movimento_estoque) sem a UNIQUE ganha `uq_{pai}_id_fazenda_id` aqui; se a
    composição falhar, a FK fica SIMPLES e o motivo é impresso (nunca aborta
    o boot). No SQLite (suíte) as FKs são simples.
  - chaves de negócio: situação UNIQUE(fazenda, caixa, animal, ciclo, dose);
    registro UNIQUE parcial da mesma chave WHERE válido e que conta;
    idempotência UNIQUE(fazenda, chave_idempotencia); nota UNIQUE(fazenda,
    chave_dedupe); nome de caixa UNIQUE parcial entre as não arquivadas.

DADOS (uma única vez, aqui — NUNCA no boot):
  1. Catálogo central v1 com o calendário da Fazenda Estreito (modelo_v1 §9 +
     decisões §12): B19 4–8 m; RB51 novilhas; RB51 reforço (julho, a cada 4
     anos, ano-base 2026); reprodutiva primovacinação (D1+D2) e reforço
     (jan, jun/jul = 1 dose, dez); clostridiose, diarreia neonatal, botulismo
     e tifopasteurina no pré-parto; vermífugo jan/mai/set 1 mL/50 kg;
     leptospirose mar/set (novilhas IA até vacas); raiva nov; exames de
     tuberculose e brucelose (abril, exceto bezerros/bezerras, "só
     resultado"); carrapaticida; IBR/BVD; aftosa INATIVA (a confirmar).
  2. Para cada fazenda existente: `sanitario_parametros` e o PADRÃO DE
     FÁBRICA (B19, exame de tuberculose, exame de brucelose) como caixas
     INATIVAS, marcando `seed_flag('sanitario_padrao_v1:{fazenda_id}')`.
     Fazenda criada depois recebe pelo provisionamento (fazendas.py), uma vez.

O dicionário do catálogo está CONGELADO aqui de propósito (migração não
importa código do app, que muda); a cópia para a fazenda usa o mesmo formato
de `fazenda/rules/sanitario/definicao.py`.

DOWNGRADE: apaga os seed_flag `sanitario_padrao_v1:%` e derruba as 18 tabelas.

Revision ID: s1n2o3v4o5m6
Revises: s0a1r2q3v4o5
Create Date: 2026-10-21 18:00:00.000000

"""
from __future__ import annotations

import unicodedata
from datetime import date, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "s1n2o3v4o5m6"
down_revision = "s0a1r2q3v4o5"
branch_labels = None
depends_on = None

JSON_T = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
SEED_PADRAO = "sanitario_padrao_v1:{fazenda_id}"

TABELAS = (
    "sanitario_catalogo", "sanitario_catalogo_versao", "sanitario_norma",
    "sanitario_caixa", "sanitario_caixa_versao", "sanitario_caixa_versao_categoria",
    "sanitario_dispositivo", "sanitario_dia", "sanitario_log", "sanitario_carencia_aceite",
    "sanitario_dia_caixa", "sanitario_dia_item", "sanitario_registro", "sanitario_situacao",
    "sanitario_prazo_legal", "sanitario_nota_agenda", "sanitario_parametros", "sanitario_job_estado",
)

# (tabela, coluna, pai): FK entre tabelas de fazenda — composta no Postgres.
COMPOSTAS = (
    ('sanitario_caixa', 'mesclada_em_caixa_id', 'sanitario_caixa'),
    ('sanitario_caixa_versao', 'estoque_id', 'estoque'),
    ('sanitario_caixa_versao', 'caixa_id', 'sanitario_caixa'),
    ('sanitario_caixa_versao', 'pub_hist_caixa_id', 'sanitario_caixa'),
    ('sanitario_caixa_versao_categoria', 'categoria_manejo_id', 'categoria_manejo'),
    ('sanitario_caixa_versao_categoria', 'versao_id', 'sanitario_caixa_versao'),
    ('sanitario_dia', 'veterinario_pessoa_id', 'pessoa'),
    ('sanitario_log', 'animal_id', 'animal'),
    ('sanitario_log', 'caixa_id', 'sanitario_caixa'),
    ('sanitario_log', 'dia_id', 'sanitario_dia'),
    ('sanitario_carencia_aceite', 'caixa_versao_id', 'sanitario_caixa_versao'),
    ('sanitario_dia_caixa', 'estoque_id', 'estoque'),
    ('sanitario_dia_caixa', 'carencia_decisao_id', 'sanitario_carencia_aceite'),
    ('sanitario_dia_caixa', 'dia_id', 'sanitario_dia'),
    ('sanitario_dia_caixa', 'caixa_versao_id', 'sanitario_caixa_versao'),
    ('sanitario_dia_caixa', 'caixa_id', 'sanitario_caixa'),
    ('sanitario_dia_item', 'dia_id', 'sanitario_dia'),
    ('sanitario_dia_item', 'caixa_id', 'sanitario_caixa'),
    ('sanitario_dia_item', 'animal_id', 'animal'),
    ('sanitario_dia_item', 'consentimento_log_id', 'sanitario_log'),
    ('sanitario_registro', 'movimento_estoque_id', 'movimento_estoque'),
    ('sanitario_registro', 'lote_estoque_id', 'lote_estoque'),
    ('sanitario_registro', 'caixa_versao_id', 'sanitario_caixa_versao'),
    ('sanitario_registro', 'animal_id', 'animal'),
    ('sanitario_registro', 'dia_item_id', 'sanitario_dia_item'),
    ('sanitario_registro', 'dispositivo_id', 'sanitario_dispositivo'),
    ('sanitario_registro', 'estoque_id', 'estoque'),
    ('sanitario_registro', 'caixa_id', 'sanitario_caixa'),
    ('sanitario_registro', 'veterinario_pessoa_id', 'pessoa'),
    ('sanitario_registro', 'dia_id', 'sanitario_dia'),
    ('sanitario_registro', 'carencia_aceite_id', 'sanitario_carencia_aceite'),
    ('sanitario_registro', 'aplicador_pessoa_id', 'pessoa'),
    ('sanitario_situacao', 'caixa_versao_id', 'sanitario_caixa_versao'),
    ('sanitario_situacao', 'dia_id', 'sanitario_dia'),
    ('sanitario_situacao', 'caixa_id', 'sanitario_caixa'),
    ('sanitario_situacao', 'animal_id', 'animal'),
    ('sanitario_situacao', 'registro_id', 'sanitario_registro'),
    ('sanitario_prazo_legal', 'caixa_id', 'sanitario_caixa'),
    ('sanitario_nota_agenda', 'caixa_id', 'sanitario_caixa'),
    ('sanitario_nota_agenda', 'dia_id', 'sanitario_dia'),
)


def _fks_sqlite(tabela: str, pg: bool) -> list:
    """FKs SIMPLES das colunas de COMPOSTAS (SQLite). No Postgres elas entram
    depois, compostas, em `_compor_fks`."""
    if pg:
        return []
    return [sa.ForeignKeyConstraint([col], [f"{pai}.id"]) for t, col, pai in COMPOSTAS if t == tabela]


# ════════════════════════════════════════════════════════════════════════════
# Catálogo central v1 (congelado)
# ════════════════════════════════════════════════════════════════════════════
VACAS = ["em lactacao", "seca", "pre-parto", "pos-parto", "vazia atrasada"]
NOVILHAS_IA_ATE_VACAS = ["recria apta", "liberada", "novilha vazia", "inseminada", "prenha", *VACAS]
BEZERRAS_ATE_NOVILHA_IA = [
    "aleitamento", "recria 1", "recria 2", "recria apta", "recria atrasada", "liberada", "novilha vazia", "inseminada",
]
BEZERROS = ["aleitamento", "bezerr"]
FICHA_VACINA = ["brinco", "categoria", "idade", "dose", "aplicado", "obs"]
FICHA_EXAME = ["brinco", "categoria", "idade", "resultado", "obs"]
ATESTADO_SIDAGO = {
    "destinatario_tipo": "orgao", "destinatario_texto": "Agrodefesa · SIDAGO", "quando": "primeiro", "dias": 30,
}
PRE_PARTO = {
    "jan_usa_evento": True, "evento_tipo": "pre_parto", "evento_de_dias": -30, "evento_ate_dias": 0,
    "ao_fechar": "perder", "pub_sexo": "F", "pub_condicoes": ["prenhe"],
}


def _vac(**kw) -> dict:
    base = {
        "tipo": "vacina", "obrigatoria": False, "produto_modo": "vazio", "dose_valor": 2.0, "dose_unidade": "mL",
        "peso_ausente": "estimado", "pub_sexo": "ambos", "pub_cat_modo": "incluir", "pub_condicoes": [],
        "jan_usa_evento": False, "jan_usa_periodo": False, "periodo_grupos": [], "data_base_dia": 15,
        "ao_fechar": "manter", "serie": [], "aglo_min": 10, "aviso_antecedencia_dias": 30, "push_admin": True,
        "legal_crmv_pedir": False, "legal_reagente_aviso": False, "ficha_colunas": FICHA_VACINA,
    }
    base.update(kw)
    return base


def _exame(**kw) -> dict:
    return _vac(**{
        "tipo": "exame", "produto_modo": "nao_se_aplica", "dose_valor": None, "dose_unidade": None,
        "ficha_colunas": FICHA_EXAME, "legal_crmv_pedir": True, "legal_reagente_aviso": True,
        "car_leite_dias": 0, "car_carne_dias": 0, **kw,
    })


# chave, nome, tipo, padrao_fabrica, ativo_no_catalogo, nota, base_legal, definicao
CATALOGO_V1 = [
    ("b19", "Brucelose B19", "vacina", True, True,
     "Versão inicial: fêmeas de 4 a 8 meses, CRMV pedido, atestado SIDAGO em 30 dias, comprovação a cada 180 dias.",
     "IN Agrodefesa 2/2025 (validar com veterinário)",
     _vac(nome="Brucelose B19", nome_curto="B19", obrigatoria=True, pub_sexo="F",
          jan_usa_evento=True, evento_tipo="idade", evento_de_dias=120, evento_ate_dias=240,
          jan_usa_periodo=True, periodo_modo="continuo", ao_fechar="perder", aglo_min=4,
          legal_crmv_pedir=True, legal_atestado=ATESTADO_SIDAGO,
          legal_comprovacao={"dias": 180, "aviso_dias": 30, "push": True, "email": True},
          legal_marca_texto="Marcar a face esquerda com o algarismo final do ano")),
    ("rb51_novilhas", "Brucelose RB51 · novilhas", "vacina", False, True,
     "Versão inicial: novilhas entrando em IA que nunca receberam B19; marca \"V\".", None,
     _vac(nome="Brucelose RB51 · novilhas", nome_curto="RB51", pub_sexo="F",
          pub_hist_tipo="nunca", pub_hist_catalogo_chave="b19",
          jan_usa_evento=True, evento_tipo="entrada_ia", evento_de_dias=0, evento_ate_dias=30, aglo_min=4,
          legal_crmv_pedir=True, legal_atestado=ATESTADO_SIDAGO, legal_marca_texto="Marcar com V no lado esquerdo")),
    ("rb51_reforco", "Brucelose RB51 · reforço", "vacina", False, True,
     "Versão inicial: vacas adultas, julho, a cada 4 anos (ano-base 2026).", None,
     _vac(nome="Brucelose RB51 · reforço", nome_curto="RB51 reforço", pub_sexo="F", categorias_ref=VACAS,
          jan_usa_periodo=True, periodo_modo="frequencia", periodo_anos=4, periodo_ano_base=2026,
          periodo_grupos=[[6]], ao_fechar="perder", legal_crmv_pedir=True)),
    ("reprodutiva_primo", "Reprodutiva · primovacinação", "vacina", False, True,
     "Versão inicial: novilhas entrando em IA, D1 e D2 após 30 dias.", None,
     _vac(nome="Reprodutiva · primovacinação", nome_curto="Reprodutiva D1/D2", pub_sexo="F", dose_valor=5.0,
          jan_usa_evento=True, evento_tipo="entrada_ia", evento_de_dias=0, evento_ate_dias=30, aglo_min=4,
          serie=[{"dose": 2, "apos_dias": 30, "janela_dias": 30}])),
    ("reprodutiva_reforco", "Reprodutiva · reforço", "vacina", False, True,
     "Versão inicial: novilhas IA até vacas já primovacinadas; jan, jun/jul (1 dose) e dez.", None,
     _vac(nome="Reprodutiva · reforço", nome_curto="Reprodutiva reforço", pub_sexo="F", dose_valor=5.0,
          categorias_ref=NOVILHAS_IA_ATE_VACAS, pub_hist_tipo="ja", pub_hist_catalogo_chave="reprodutiva_primo",
          jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=[[0], [5, 6], [11]])),
    ("clostridiose_pre_parto", "Clostridiose · pré-parto", "vacina", False, True,
     "Versão inicial: pré-parto = 30 dias antes do parto previsto até o parto real.", None,
     _vac(nome="Clostridiose · pré-parto", nome_curto="Clostridiose", obrigatoria=True, dose_valor=5.0,
          aglo_min=4, **PRE_PARTO)),
    ("diarreia_neonatal_pre_parto", "Diarreia neonatal · pré-parto", "vacina", False, True,
     "Versão inicial: pré-parto; dose conforme bula (2 a 5 mL).", None,
     _vac(nome="Diarreia neonatal · pré-parto", nome_curto="Diarreia neonatal", obrigatoria=True, dose_valor=None,
          observacao="Dose conforme bula (tabela: 2 mL; planilha: 2 a 5 mL).", aglo_min=4, **PRE_PARTO)),
    ("botulismo_pre_parto", "Botulismo · pré-parto", "vacina", False, True,
     "Versão inicial: pré-parto; dose conforme bula.", None,
     _vac(nome="Botulismo · pré-parto", nome_curto="Botulismo", obrigatoria=True, dose_valor=None,
          observacao="Dose conforme bula.", aglo_min=4, **PRE_PARTO)),
    ("tifopasteurina_pre_parto", "Tifopasteurina · pré-parto", "vacina", False, True,
     "Versão inicial: pré-parto; dose conforme bula.", None,
     _vac(nome="Tifopasteurina · pré-parto", nome_curto="Tifopasteurina", obrigatoria=True, dose_valor=None,
          observacao="Dose conforme bula.", aglo_min=4, **PRE_PARTO)),
    ("vermifugo", "Vermífugo · bezerras a novilhas IA", "vermifugo", False, True,
     "Versão inicial: jan, mai e set; 1 mL por 50 kg.", None,
     _vac(nome="Vermífugo · bezerras a novilhas IA", nome_curto="Vermífugo", tipo="vermifugo", pub_sexo="F",
          dose_valor=1.0, dose_unidade="mL_por_x_kg", dose_x_kg=50.0, categorias_ref=BEZERRAS_ATE_NOVILHA_IA,
          jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=[[0], [4], [8]])),
    ("leptospirose", "Leptospirose", "vacina", False, True,
     "Versão inicial: março e setembro, novilhas IA até vacas (segue a planilha).", None,
     _vac(nome="Leptospirose", nome_curto="Leptospirose", obrigatoria=True, pub_sexo="F", dose_valor=5.0,
          categorias_ref=NOVILHAS_IA_ATE_VACAS, jan_usa_periodo=True, periodo_modo="meses",
          periodo_grupos=[[2], [8]])),
    ("raiva", "Raiva", "vacina", False, True,
     "Versão inicial: vacas, novembro (campanha do governo).", None,
     _vac(nome="Raiva", nome_curto="Raiva", obrigatoria=True, pub_sexo="F", categorias_ref=VACAS,
          jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=[[10]])),
    ("aftosa", "Febre aftosa", "vacina", False, False,
     "A confirmar: a vacinação contra aftosa foi suspensa no país. Inativa até validação.", None,
     _vac(nome="Febre aftosa", nome_curto="Aftosa", dose_valor=5.0, categorias_ref=VACAS,
          jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=[[4]],
          observacao="A confirmar: vacinação suspensa no país.")),
    ("exame_tuberculose", "Exame de tuberculose", "exame", True, True,
     "Versão inicial: 1× ao ano (abril), exceto bezerros e bezerras; leitura 72 h ± 6 h; modo só resultado.", None,
     _exame(nome="Exame de tuberculose", nome_curto="Exame TB", obrigatoria=True, pub_cat_modo="excluir",
            categorias_ref=BEZERROS, fallback_idade_min_dias=90, jan_usa_periodo=True, periodo_modo="meses",
            periodo_grupos=[[3]], legal_leitura={"modo": "so_resultado", "horas": 72, "tolerancia": 6})),
    ("exame_brucelose", "Exame de brucelose", "exame", True, True,
     "Versão inicial: 1× ao ano (abril), exceto bezerros e bezerras; resultado por animal.", None,
     _exame(nome="Exame de brucelose", nome_curto="Exame brucelose", obrigatoria=True, pub_cat_modo="excluir",
            categorias_ref=BEZERROS, fallback_idade_min_dias=90, jan_usa_periodo=True, periodo_modo="meses",
            periodo_grupos=[[3]], legal_leitura={"modo": "so_resultado"})),
    ("carrapaticida", "Carrapaticida pour-on", "outro", False, True,
     "Versão inicial: a cada 3 meses, 1 mL por 10 kg; carência a confirmar pela bula.", None,
     _vac(nome="Carrapaticida pour-on", nome_curto="Carrapaticida", tipo="outro", dose_valor=1.0,
          dose_unidade="mL_por_x_kg", dose_x_kg=10.0, categorias_ref=NOVILHAS_IA_ATE_VACAS + ["recria"],
          jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=[[0], [3], [6], [9]])),
    ("ibr_bvd", "IBR/BVD · reforço anual", "vacina", False, True,
     "Versão inicial: anual, mês a escolher (agosto sugerido).", None,
     _vac(nome="IBR/BVD · reforço anual", nome_curto="IBR/BVD", pub_sexo="F", dose_valor=5.0,
          categorias_ref=NOVILHAS_IA_ATE_VACAS, jan_usa_periodo=True, periodo_modo="meses", periodo_grupos=[[7]])),
]

CAMPOS_VERSAO = (
    "produto_modo", "estoque_id", "produto_texto", "dose_valor", "dose_unidade", "dose_x_kg", "peso_ausente",
    "pub_sexo", "pub_cat_modo", "pub_idade_min_dias", "pub_idade_max_dias", "pub_condicoes", "pub_hist_tipo",
    "pub_hist_caixa_id",
    "jan_usa_evento", "evento_tipo", "evento_de_dias", "evento_ate_dias", "jan_usa_periodo", "periodo_modo",
    "periodo_grupos", "periodo_anos", "periodo_ano_base", "data_base_dia", "comecar_em", "ao_fechar", "serie",
    "aglo_min", "aviso_antecedencia_dias", "aviso_fim_janela_dias", "push_admin",
    "legal_crmv_pedir", "legal_atestado", "legal_comprovacao", "legal_leitura", "legal_reagente_aviso",
    "legal_marca_texto",
    "car_leite_dias", "car_carne_dias", "car_modo_leite",
    "ficha_colunas", "observacao",
)
DEFAULTS_VERSAO = {
    "produto_modo": "vazio", "peso_ausente": "estimado", "pub_sexo": "ambos", "pub_cat_modo": "incluir",
    "pub_condicoes": [], "jan_usa_evento": False, "jan_usa_periodo": False, "periodo_grupos": [],
    "data_base_dia": 15, "ao_fechar": "manter", "serie": [], "aglo_min": 4, "aviso_antecedencia_dias": 30,
    "push_admin": True, "legal_crmv_pedir": False, "legal_reagente_aviso": False, "ficha_colunas": [],
}


def _norm(txt: str | None) -> str:
    s = unicodedata.normalize("NFKD", (txt or "").strip().lower())
    return "".join(ch for ch in s if not unicodedata.combining(ch))


# ════════════════════════════════════════════════════════════════════════════
# Upgrade
# ════════════════════════════════════════════════════════════════════════════
def upgrade() -> None:
    conn = op.get_bind()
    pg = conn.dialect.name == "postgresql"
    insp = sa.inspect(conn)
    if insp.has_table("sanitario_caixa"):
        # A rede de segurança do boot (create_all) já criou — só garante os dados.
        tabelas = {t: sa.Table(t, sa.MetaData(), autoload_with=conn) for t in TABELAS}
        _dados(conn, tabelas)
        return
    tabelas: dict[str, sa.Table] = {}
    tabelas['sanitario_catalogo'] = op.create_table(
        'sanitario_catalogo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chave', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('versao_atual', sa.Integer(), nullable=False),
        sa.Column('padrao_fabrica', sa.Boolean(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False),
        sa.Column('uf_sugerida', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        *_fks_sqlite('sanitario_catalogo', pg),
    )
    op.create_index('ix_sanitario_catalogo_chave', 'sanitario_catalogo', ['chave'], unique=True)

    tabelas['sanitario_catalogo_versao'] = op.create_table(
        'sanitario_catalogo_versao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('catalogo_id', sa.Integer(), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.Column('definicao', JSON_T, nullable=False),
        sa.Column('nota_mudanca', sa.String(), nullable=True),
        sa.Column('base_legal', sa.String(), nullable=True),
        sa.Column('publicado_em', sa.DateTime(), nullable=False),
        sa.Column('publicado_por_usuario_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('catalogo_id', 'versao', name='uq_sanitario_catalogo_versao'),
        sa.ForeignKeyConstraint(['catalogo_id'], ["sanitario_catalogo.id"]),
        sa.ForeignKeyConstraint(['publicado_por_usuario_id'], ["usuario.id"]),
        *_fks_sqlite('sanitario_catalogo_versao', pg),
    )
    op.create_index('ix_sanitario_catalogo_versao_catalogo_id', 'sanitario_catalogo_versao', ['catalogo_id'], unique=False)

    tabelas['sanitario_norma'] = op.create_table(
        'sanitario_norma',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uf', sa.String(), nullable=False),
        sa.Column('chave', sa.String(), nullable=False),
        sa.Column('texto', sa.String(), nullable=False),
        sa.Column('base_legal', sa.String(), nullable=True),
        sa.Column('valores_sugeridos', JSON_T, nullable=True),
        sa.Column('vigente_desde', sa.Date(), nullable=True),
        sa.Column('versao', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('uf', 'chave', 'versao', name='uq_sanitario_norma_uf_chave_versao'),
        *_fks_sqlite('sanitario_norma', pg),
    )
    op.create_index('ix_sanitario_norma_uf', 'sanitario_norma', ['uf'], unique=False)

    tabelas['sanitario_caixa'] = op.create_table(
        'sanitario_caixa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('nome_normalizado', sa.String(), nullable=False),
        sa.Column('nome_curto', sa.String(), nullable=True),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('estado', sa.String(), nullable=False),
        sa.Column('obrigatoria', sa.Boolean(), nullable=False),
        sa.Column('padrao_fabrica', sa.Boolean(), nullable=False),
        sa.Column('versao_atual_id', sa.Integer(), nullable=True),
        sa.Column('catalogo_id', sa.Integer(), nullable=True),
        sa.Column('catalogo_versao', sa.Integer(), nullable=True),
        sa.Column('ativada_em', sa.Date(), nullable=True),
        sa.Column('mesclada_em_caixa_id', sa.Integer(), nullable=True),
        sa.Column('arquivada_em', sa.DateTime(), nullable=True),
        sa.Column('arquivada_motivo', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_caixa_id_fazenda_id'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        sa.ForeignKeyConstraint(['catalogo_id'], ["sanitario_catalogo.id"]),
        sa.ForeignKeyConstraint(['criado_por_usuario_id'], ["usuario.id"]),
        *_fks_sqlite('sanitario_caixa', pg),
    )
    op.create_index('uq_sanitario_caixa_nome_vivo', 'sanitario_caixa', ['fazenda_id', 'nome_normalizado'], unique=True, sqlite_where=sa.text("estado <> 'arquivada'"), postgresql_where=sa.text("estado <> 'arquivada'"))
    op.create_index('ix_sanitario_caixa_fazenda_id', 'sanitario_caixa', ['fazenda_id'], unique=False)
    op.create_index('ix_sanitario_caixa_fazenda_estado', 'sanitario_caixa', ['fazenda_id', 'estado'], unique=False)
    op.create_index('ix_sanitario_caixa_versao_atual_id', 'sanitario_caixa', ['versao_atual_id'], unique=False)

    tabelas['sanitario_caixa_versao'] = op.create_table(
        'sanitario_caixa_versao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('caixa_id', sa.Integer(), nullable=False),
        sa.Column('numero', sa.Integer(), nullable=False),
        sa.Column('vigente_desde', sa.Date(), nullable=False),
        sa.Column('vigente_ate', sa.Date(), nullable=True),
        sa.Column('produto_modo', sa.String(), nullable=False),
        sa.Column('estoque_id', sa.Integer(), nullable=True),
        sa.Column('produto_texto', sa.String(), nullable=True),
        sa.Column('dose_valor', sa.Float(), nullable=True),
        sa.Column('dose_unidade', sa.String(), nullable=True),
        sa.Column('dose_x_kg', sa.Float(), nullable=True),
        sa.Column('peso_ausente', sa.String(), nullable=False),
        sa.Column('pub_sexo', sa.String(), nullable=False),
        sa.Column('pub_cat_modo', sa.String(), nullable=False),
        sa.Column('pub_idade_min_dias', sa.Integer(), nullable=True),
        sa.Column('pub_idade_max_dias', sa.Integer(), nullable=True),
        sa.Column('pub_condicoes', JSON_T, nullable=False),
        sa.Column('pub_hist_tipo', sa.String(), nullable=True),
        sa.Column('pub_hist_caixa_id', sa.Integer(), nullable=True),
        sa.Column('jan_usa_evento', sa.Boolean(), nullable=False),
        sa.Column('evento_tipo', sa.String(), nullable=True),
        sa.Column('evento_de_dias', sa.Integer(), nullable=True),
        sa.Column('evento_ate_dias', sa.Integer(), nullable=True),
        sa.Column('jan_usa_periodo', sa.Boolean(), nullable=False),
        sa.Column('periodo_modo', sa.String(), nullable=True),
        sa.Column('periodo_grupos', JSON_T, nullable=False),
        sa.Column('periodo_anos', sa.Integer(), nullable=True),
        sa.Column('periodo_ano_base', sa.Integer(), nullable=True),
        sa.Column('data_base_dia', sa.Integer(), nullable=False),
        sa.Column('comecar_em', sa.Date(), nullable=True),
        sa.Column('ao_fechar', sa.String(), nullable=False),
        sa.Column('serie', JSON_T, nullable=False),
        sa.Column('aglo_min', sa.Integer(), nullable=False),
        sa.Column('aviso_antecedencia_dias', sa.Integer(), nullable=False),
        sa.Column('aviso_fim_janela_dias', sa.Integer(), nullable=True),
        sa.Column('push_admin', sa.Boolean(), nullable=False),
        sa.Column('legal_crmv_pedir', sa.Boolean(), nullable=False),
        sa.Column('legal_atestado', JSON_T, nullable=True),
        sa.Column('legal_comprovacao', JSON_T, nullable=True),
        sa.Column('legal_leitura', JSON_T, nullable=True),
        sa.Column('legal_reagente_aviso', sa.Boolean(), nullable=False),
        sa.Column('legal_marca_texto', sa.String(), nullable=True),
        sa.Column('car_leite_dias', sa.Integer(), nullable=True),
        sa.Column('car_carne_dias', sa.Integer(), nullable=True),
        sa.Column('car_modo_leite', sa.String(), nullable=True),
        sa.Column('ficha_colunas', JSON_T, nullable=False),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('caixa_id', 'numero', name='uq_sanitario_caixa_versao_numero'),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_caixa_versao_id_fazenda_id'),
        sa.ForeignKeyConstraint(['criado_por_usuario_id'], ["usuario.id"]),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_caixa_versao', pg),
    )
    op.create_index('ix_sanitario_caixa_versao_caixa_id', 'sanitario_caixa_versao', ['caixa_id'], unique=False)
    op.create_index('ix_sanitario_caixa_versao_fazenda_id', 'sanitario_caixa_versao', ['fazenda_id'], unique=False)

    tabelas['sanitario_caixa_versao_categoria'] = op.create_table(
        'sanitario_caixa_versao_categoria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('versao_id', sa.Integer(), nullable=False),
        sa.Column('categoria_manejo_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('versao_id', 'categoria_manejo_id', name='uq_sanitario_versao_categoria'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_caixa_versao_categoria', pg),
    )
    op.create_index('ix_sanitario_caixa_versao_categoria_versao_id', 'sanitario_caixa_versao_categoria', ['versao_id'], unique=False)
    op.create_index('ix_sanitario_caixa_versao_categoria_fazenda_id', 'sanitario_caixa_versao_categoria', ['fazenda_id'], unique=False)

    tabelas['sanitario_dispositivo'] = op.create_table(
        'sanitario_dispositivo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('dispositivo_uid', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=True),
        sa.Column('ultimo_contato_em', sa.DateTime(), nullable=True),
        sa.Column('fila_pendentes', sa.Integer(), nullable=False),
        sa.Column('fila_mais_antigo_em', sa.DateTime(), nullable=True),
        sa.Column('aviso_admin_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('fazenda_id', 'usuario_id', 'dispositivo_uid', name='uq_sanitario_dispositivo'),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_dispositivo_id_fazenda_id'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        sa.ForeignKeyConstraint(['usuario_id'], ["usuario.id"]),
        *_fks_sqlite('sanitario_dispositivo', pg),
    )
    op.create_index('ix_sanitario_dispositivo_fazenda_id', 'sanitario_dispositivo', ['fazenda_id'], unique=False)

    tabelas['sanitario_dia'] = op.create_table(
        'sanitario_dia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('hora', sa.String(), nullable=True),
        sa.Column('data_prevista', sa.Date(), nullable=True),
        sa.Column('estado', sa.String(), nullable=False),
        sa.Column('veterinario_pessoa_id', sa.Integer(), nullable=True),
        sa.Column('veterinario_texto', sa.String(), nullable=True),
        sa.Column('crmv_texto', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('decisao_riscos', JSON_T, nullable=True),
        sa.Column('fechado_em', sa.DateTime(), nullable=True),
        sa.Column('fechado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('fechamento_auto', sa.Boolean(), nullable=False),
        sa.Column('motivo_cancelamento', sa.String(), nullable=True),
        sa.Column('versao_lock', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_dia_id_fazenda_id'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        sa.ForeignKeyConstraint(['fechado_por_usuario_id'], ["usuario.id"]),
        sa.ForeignKeyConstraint(['criado_por_usuario_id'], ["usuario.id"]),
        *_fks_sqlite('sanitario_dia', pg),
    )
    op.create_index('ix_sanitario_dia_fazenda_id', 'sanitario_dia', ['fazenda_id'], unique=False)
    op.create_index('ix_sanitario_dia_fazenda_data_estado', 'sanitario_dia', ['fazenda_id', 'data', 'estado'], unique=False)

    tabelas['sanitario_log'] = op.create_table(
        'sanitario_log',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('dia_id', sa.Integer(), nullable=True),
        sa.Column('caixa_id', sa.Integer(), nullable=True),
        sa.Column('animal_id', sa.Integer(), nullable=True),
        sa.Column('registro_id', sa.Integer(), nullable=True),
        sa.Column('motivo_exibido', sa.String(), nullable=True),
        sa.Column('decisao', sa.String(), nullable=True),
        sa.Column('texto_livre', sa.String(), nullable=True),
        sa.Column('payload', JSON_T, nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('dispositivo_id', sa.Integer(), nullable=True),
        sa.Column('em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_log_id_fazenda_id'),
        sa.ForeignKeyConstraint(['usuario_id'], ["usuario.id"]),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_log', pg),
    )
    op.create_index('ix_sanitario_log_fazenda_em', 'sanitario_log', ['fazenda_id', 'em'], unique=False)
    op.create_index('ix_sanitario_log_fazenda_id', 'sanitario_log', ['fazenda_id'], unique=False)

    tabelas['sanitario_carencia_aceite'] = op.create_table(
        'sanitario_carencia_aceite',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('escopo', sa.String(), nullable=False),
        sa.Column('caixa_versao_id', sa.Integer(), nullable=True),
        sa.Column('dia_caixa_id', sa.Integer(), nullable=True),
        sa.Column('modo_leite', sa.String(), nullable=True),
        sa.Column('leite_dias', sa.Integer(), nullable=True),
        sa.Column('carne_dias', sa.Integer(), nullable=True),
        sa.Column('origem', sa.String(), nullable=False),
        sa.Column('aceito_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('aceito_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_carencia_aceite_id_fazenda_id'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        sa.ForeignKeyConstraint(['aceito_por_usuario_id'], ["usuario.id"]),
        *_fks_sqlite('sanitario_carencia_aceite', pg),
    )
    op.create_index('ix_sanitario_carencia_aceite_fazenda_id', 'sanitario_carencia_aceite', ['fazenda_id'], unique=False)

    tabelas['sanitario_dia_caixa'] = op.create_table(
        'sanitario_dia_caixa',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('dia_id', sa.Integer(), nullable=False),
        sa.Column('caixa_id', sa.Integer(), nullable=False),
        sa.Column('caixa_versao_id', sa.Integer(), nullable=True),
        sa.Column('produto_modo', sa.String(), nullable=False),
        sa.Column('estoque_id', sa.Integer(), nullable=True),
        sa.Column('produto_texto', sa.String(), nullable=True),
        sa.Column('dose_valor', sa.Float(), nullable=True),
        sa.Column('dose_unidade', sa.String(), nullable=True),
        sa.Column('dose_x_kg', sa.Float(), nullable=True),
        sa.Column('carencia_decisao_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_dia_caixa_id_fazenda_id'),
        sa.UniqueConstraint('dia_id', 'caixa_id', name='uq_sanitario_dia_caixa'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_dia_caixa', pg),
    )
    op.create_index('ix_sanitario_dia_caixa_dia_id', 'sanitario_dia_caixa', ['dia_id'], unique=False)
    op.create_index('ix_sanitario_dia_caixa_fazenda_id', 'sanitario_dia_caixa', ['fazenda_id'], unique=False)

    tabelas['sanitario_dia_item'] = op.create_table(
        'sanitario_dia_item',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('dia_id', sa.Integer(), nullable=False),
        sa.Column('animal_id', sa.Integer(), nullable=False),
        sa.Column('caixa_id', sa.Integer(), nullable=False),
        sa.Column('origem', sa.String(), nullable=False),
        sa.Column('estado', sa.String(), nullable=False),
        sa.Column('consentimento_log_id', sa.Integer(), nullable=True),
        sa.Column('situacao_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_dia_item_id_fazenda_id'),
        sa.UniqueConstraint('dia_id', 'animal_id', 'caixa_id', name='uq_sanitario_dia_item'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_dia_item', pg),
    )
    op.create_index('ix_sanitario_dia_item_animal_id', 'sanitario_dia_item', ['animal_id'], unique=False)
    op.create_index('ix_sanitario_dia_item_fazenda_id', 'sanitario_dia_item', ['fazenda_id'], unique=False)
    op.create_index('ix_sanitario_dia_item_dia_id', 'sanitario_dia_item', ['dia_id'], unique=False)

    tabelas['sanitario_registro'] = op.create_table(
        'sanitario_registro',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('animal_id', sa.Integer(), nullable=True),
        sa.Column('numero_animal_texto', sa.String(), nullable=True),
        sa.Column('caixa_id', sa.Integer(), nullable=True),
        sa.Column('caixa_versao_id', sa.Integer(), nullable=True),
        sa.Column('outro_texto', sa.String(), nullable=True),
        sa.Column('ciclo_chave', sa.String(), nullable=True),
        sa.Column('dose_num', sa.Integer(), nullable=False),
        sa.Column('dia_id', sa.Integer(), nullable=True),
        sa.Column('dia_item_id', sa.Integer(), nullable=True),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('hora', sa.String(), nullable=True),
        sa.Column('origem', sa.String(), nullable=False),
        sa.Column('canal', sa.String(), nullable=False),
        sa.Column('so_registro', sa.Boolean(), nullable=False),
        sa.Column('decisao_curral', sa.Boolean(), nullable=False),
        sa.Column('apos_fechamento', sa.Boolean(), nullable=False),
        sa.Column('retroativo', sa.Boolean(), nullable=False),
        sa.Column('retroativo_motivo', sa.String(), nullable=True),
        sa.Column('fora_da_regra', sa.Boolean(), nullable=False),
        sa.Column('produto_modo', sa.String(), nullable=True),
        sa.Column('estoque_id', sa.Integer(), nullable=True),
        sa.Column('lote_estoque_id', sa.Integer(), nullable=True),
        sa.Column('partida_texto', sa.String(), nullable=True),
        sa.Column('fabricante', sa.String(), nullable=True),
        sa.Column('validade', sa.Date(), nullable=True),
        sa.Column('produto_texto', sa.String(), nullable=True),
        sa.Column('dose_valor', sa.Float(), nullable=True),
        sa.Column('dose_unidade', sa.String(), nullable=True),
        sa.Column('quantidade_baixada', sa.Float(), nullable=True),
        sa.Column('movimento_estoque_id', sa.Integer(), nullable=True),
        sa.Column('custo', sa.Float(), nullable=True),
        sa.Column('peso_usado', sa.Float(), nullable=True),
        sa.Column('peso_estimado', sa.Boolean(), nullable=False),
        sa.Column('aplicador_pessoa_id', sa.Integer(), nullable=True),
        sa.Column('aplicador_texto', sa.String(), nullable=True),
        sa.Column('veterinario_pessoa_id', sa.Integer(), nullable=True),
        sa.Column('veterinario_texto', sa.String(), nullable=True),
        sa.Column('crmv_texto', sa.String(), nullable=True),
        sa.Column('resultado', sa.String(), nullable=True),
        sa.Column('resultado_valor', sa.Float(), nullable=True),
        sa.Column('resultado_detalhe', JSON_T, nullable=True),
        sa.Column('leitura_em', sa.DateTime(), nullable=True),
        sa.Column('carencia_leite_ate', sa.Date(), nullable=True),
        sa.Column('carencia_carne_ate', sa.Date(), nullable=True),
        sa.Column('carencia_modo', sa.String(), nullable=True),
        sa.Column('carencia_aceite_id', sa.Integer(), nullable=True),
        sa.Column('atestado_numero', sa.String(), nullable=True),
        sa.Column('atestado_destinatario', sa.String(), nullable=True),
        sa.Column('numero_lancamento_vinculado', sa.String(), nullable=True),
        sa.Column('estado', sa.String(), nullable=False),
        sa.Column('estornado_em', sa.DateTime(), nullable=True),
        sa.Column('estornado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('estornado_motivo', sa.String(), nullable=True),
        sa.Column('chave_idempotencia', sa.String(), nullable=True),
        sa.Column('dispositivo_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('id', 'fazenda_id', name='uq_sanitario_registro_id_fazenda_id'),
        sa.UniqueConstraint('fazenda_id', 'chave_idempotencia', name='uq_sanitario_registro_idempotencia'),
        sa.ForeignKeyConstraint(['criado_por_usuario_id'], ["usuario.id"]),
        sa.ForeignKeyConstraint(['estornado_por_usuario_id'], ["usuario.id"]),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_registro', pg),
    )
    op.create_index('ix_sanitario_registro_fazenda_id', 'sanitario_registro', ['fazenda_id'], unique=False)
    op.create_index('ix_sanitario_registro_fazenda_data', 'sanitario_registro', ['fazenda_id', 'data'], unique=False)
    op.create_index('ix_sanitario_registro_fazenda_animal', 'sanitario_registro', ['fazenda_id', 'animal_id'], unique=False)
    op.create_index('uq_sanitario_registro_chave_valida', 'sanitario_registro', ['fazenda_id', 'animal_id', 'caixa_id', 'ciclo_chave', 'dose_num'], unique=True, sqlite_where=sa.text("estado = 'valido' AND so_registro = 0 AND caixa_id IS NOT NULL"), postgresql_where=sa.text("estado = 'valido' AND so_registro = false AND caixa_id IS NOT NULL"))

    tabelas['sanitario_situacao'] = op.create_table(
        'sanitario_situacao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('caixa_id', sa.Integer(), nullable=False),
        sa.Column('caixa_versao_id', sa.Integer(), nullable=True),
        sa.Column('animal_id', sa.Integer(), nullable=False),
        sa.Column('ciclo_chave', sa.String(), nullable=False),
        sa.Column('dose_num', sa.Integer(), nullable=False),
        sa.Column('estado', sa.String(), nullable=False),
        sa.Column('janela_inicio', sa.Date(), nullable=True),
        sa.Column('janela_fim', sa.Date(), nullable=True),
        sa.Column('data_base', sa.Date(), nullable=True),
        sa.Column('motivo', sa.String(), nullable=True),
        sa.Column('dia_id', sa.Integer(), nullable=True),
        sa.Column('registro_id', sa.Integer(), nullable=True),
        sa.Column('dispensada_em', sa.DateTime(), nullable=True),
        sa.Column('dispensada_motivo', sa.String(), nullable=True),
        sa.Column('dispensada_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('calculado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('fazenda_id', 'caixa_id', 'animal_id', 'ciclo_chave', 'dose_num', name='uq_sanitario_situacao_chave'),
        sa.ForeignKeyConstraint(['dispensada_por_usuario_id'], ["usuario.id"]),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_situacao', pg),
    )
    op.create_index('ix_sanitario_situacao_fazenda_janela_inicio', 'sanitario_situacao', ['fazenda_id', 'janela_inicio'], unique=False)
    op.create_index('ix_sanitario_situacao_fazenda_id', 'sanitario_situacao', ['fazenda_id'], unique=False)
    op.create_index('ix_sanitario_situacao_fazenda_estado', 'sanitario_situacao', ['fazenda_id', 'estado'], unique=False)
    op.create_index('ix_sanitario_situacao_fazenda_caixa_estado', 'sanitario_situacao', ['fazenda_id', 'caixa_id', 'estado'], unique=False)
    op.create_index('ix_sanitario_situacao_animal_id', 'sanitario_situacao', ['animal_id'], unique=False)

    tabelas['sanitario_prazo_legal'] = op.create_table(
        'sanitario_prazo_legal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('caixa_id', sa.Integer(), nullable=False),
        sa.Column('referencia_chave', sa.String(), nullable=False),
        sa.Column('registro_ids', JSON_T, nullable=False),
        sa.Column('vence_em', sa.Date(), nullable=False),
        sa.Column('destinatario', sa.String(), nullable=True),
        sa.Column('estado', sa.String(), nullable=False),
        sa.Column('cumprido_em', sa.Date(), nullable=True),
        sa.Column('documento_numero', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('fazenda_id', 'tipo', 'caixa_id', 'referencia_chave', name='uq_sanitario_prazo_legal'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_prazo_legal', pg),
    )
    op.create_index('ix_sanitario_prazo_legal_fazenda_id', 'sanitario_prazo_legal', ['fazenda_id'], unique=False)

    tabelas['sanitario_nota_agenda'] = op.create_table(
        'sanitario_nota_agenda',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('caixa_id', sa.Integer(), nullable=True),
        sa.Column('ciclo_chave', sa.String(), nullable=True),
        sa.Column('dia_id', sa.Integer(), nullable=True),
        sa.Column('chave_dedupe', sa.String(), nullable=False),
        sa.Column('titulo', sa.String(), nullable=False),
        sa.Column('texto', sa.String(), nullable=True),
        sa.Column('dados', JSON_T, nullable=True),
        sa.Column('so_admin', sa.Boolean(), nullable=False),
        sa.Column('data_ref', sa.Date(), nullable=True),
        sa.Column('resolvida_em', sa.DateTime(), nullable=True),
        sa.Column('push_enviado_em', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('fazenda_id', 'chave_dedupe', name='uq_sanitario_nota_dedupe'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_nota_agenda', pg),
    )
    op.create_index('ix_sanitario_nota_agenda_fazenda_id', 'sanitario_nota_agenda', ['fazenda_id'], unique=False)

    tabelas['sanitario_parametros'] = op.create_table(
        'sanitario_parametros',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('uf', sa.String(), nullable=True),
        sa.Column('prazos_legais_ativo', sa.Boolean(), nullable=False),
        sa.Column('antecedencia_padrao_dias', sa.Integer(), nullable=False),
        sa.Column('corrigir_ate', sa.String(), nullable=False),
        sa.Column('dose_externa_sem_data', sa.String(), nullable=False),
        sa.Column('peso_estimado', sa.String(), nullable=False),
        sa.Column('modo_tuberculina', sa.String(), nullable=False),
        sa.Column('aviso_offline_horas', sa.Integer(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.Column('atualizado_por_usuario_id', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('fazenda_id', name='uq_sanitario_parametros_fazenda'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        sa.ForeignKeyConstraint(['atualizado_por_usuario_id'], ["usuario.id"]),
        *_fks_sqlite('sanitario_parametros', pg),
    )
    op.create_index('ix_sanitario_parametros_fazenda_id', 'sanitario_parametros', ['fazenda_id'], unique=False)

    tabelas['sanitario_job_estado'] = op.create_table(
        'sanitario_job_estado',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fazenda_id', sa.Integer(), nullable=False),
        sa.Column('ultima_diaria_em', sa.Date(), nullable=True),
        sa.Column('em_execucao_ate', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('erro', sa.String(), nullable=True),
        sa.Column('contagens', JSON_T, nullable=True),
        sa.Column('atualizado_em', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint('fazenda_id', name='uq_sanitario_job_estado_fazenda'),
        sa.ForeignKeyConstraint(['fazenda_id'], ["fazenda.id"]),
        *_fks_sqlite('sanitario_job_estado', pg),
    )
    op.create_index('ix_sanitario_job_estado_fazenda_id', 'sanitario_job_estado', ['fazenda_id'], unique=False)

    if pg:
        _compor_fks(conn)
    _dados(conn, tabelas)


def _compor_fks(conn) -> None:
    """Postgres: UNIQUE(id, fazenda_id) no pai externo (se faltar) e FK
    composta. Cada passo no seu SAVEPOINT; falhou, fica a FK simples."""
    pais_externos = sorted({pai for _t, _c, pai in COMPOSTAS if not pai.startswith("sanitario_")})
    for pai in pais_externos:
        tem = conn.execute(sa.text("""
            SELECT 1 FROM pg_constraint con JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = :pai AND con.contype IN ('u', 'p')
              AND (SELECT array_agg(att.attname::text ORDER BY att.attname)
                   FROM unnest(con.conkey) k(attnum)
                   JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = k.attnum)
                  = ARRAY['fazenda_id', 'id']
        """), {"pai": pai}).first()
        if tem:
            continue
        marca = conn.begin_nested()
        try:
            conn.execute(sa.text(f'ALTER TABLE "{pai}" ADD CONSTRAINT "uq_{pai}_id_fazenda_id" UNIQUE (id, fazenda_id)'))
            marca.commit()
        except sa.exc.SQLAlchemyError as erro:
            marca.rollback()
            print(f"[sanitario v2] UNIQUE(id, fazenda_id) em {pai} não criada: {str(erro.__cause__ or erro)[:200]}")
    for tabela, coluna, pai in COMPOSTAS:
        nome = f"fk_{tabela}_{coluna}_fazenda"[:63]
        marca = conn.begin_nested()
        try:
            conn.execute(sa.text(
                f'ALTER TABLE "{tabela}" ADD CONSTRAINT "{nome}" '
                f'FOREIGN KEY ({coluna}, fazenda_id) REFERENCES "{pai}" (id, fazenda_id)'
            ))
            marca.commit()
        except sa.exc.SQLAlchemyError as erro:
            marca.rollback()
            print(f"[sanitario v2] FK composta {tabela}.{coluna} -> {pai} pulada (fica simples): "
                  f"{str(erro.__cause__ or erro)[:200]}")
            simples = f"fk_{tabela}_{coluna}"[:63]
            conn.execute(sa.text(
                f'ALTER TABLE "{tabela}" ADD CONSTRAINT "{simples}" FOREIGN KEY ({coluna}) REFERENCES "{pai}" (id)'
            ))


def _dados(conn, tabelas: dict) -> None:
    """Catálogo central v1 (se ainda vazio) + parâmetros e padrão de fábrica
    (INATIVO) de cada fazenda existente, uma única vez por fazenda."""
    agora = datetime.utcnow()
    hoje = agora.date()
    cat_t, catv_t = tabelas["sanitario_catalogo"], tabelas["sanitario_catalogo_versao"]
    ja = {r[0] for r in conn.execute(sa.select(cat_t.c.chave))}
    for chave, nome, tipo, padrao, ativo, nota, base_legal, definicao in CATALOGO_V1:
        if chave in ja:
            continue
        cid = conn.execute(cat_t.insert().values(
            chave=chave, nome=nome, tipo=tipo, versao_atual=1, padrao_fabrica=padrao, ativo=ativo,
            uf_sugerida="GO" if chave.startswith(("b19", "rb51")) else None, criado_em=agora,
        )).inserted_primary_key[0]
        conn.execute(catv_t.insert().values(
            catalogo_id=cid, versao=1, definicao=definicao, nota_mudanca=nota, base_legal=base_legal,
            publicado_em=agora,
        ))

    fazendas = conn.execute(sa.text("SELECT id, uf FROM fazenda ORDER BY id")).all()
    if not fazendas:
        return
    padrao = conn.execute(
        sa.select(cat_t.c.id, cat_t.c.chave, catv_t.c.versao, catv_t.c.definicao)
        .select_from(cat_t.join(catv_t, sa.and_(catv_t.c.catalogo_id == cat_t.c.id, catv_t.c.versao == cat_t.c.versao_atual)))
        .where(cat_t.c.padrao_fabrica == sa.true(), cat_t.c.ativo == sa.true())
        .order_by(cat_t.c.id)
    ).all()
    par_t = tabelas["sanitario_parametros"]
    for fid, uf in fazendas:
        if conn.execute(sa.select(par_t.c.id).where(par_t.c.fazenda_id == fid)).first() is None:
            conn.execute(par_t.insert().values(
                fazenda_id=fid, uf=uf, prazos_legais_ativo=False, antecedencia_padrao_dias=30,
                corrigir_ate="fechar_dia", dose_externa_sem_data="contar", peso_estimado="aceitar",
                modo_tuberculina="so_resultado", aviso_offline_horas=24, atualizado_em=agora,
            ))
        flag = SEED_PADRAO.format(fazenda_id=fid)
        if conn.execute(sa.text("SELECT 1 FROM seed_flag WHERE chave = :c"), {"c": flag}).first():
            continue
        cats = conn.execute(
            sa.text("SELECT id, nome FROM categoria_manejo WHERE fazenda_id = :f AND ativo = :t"),
            {"f": fid, "t": True},
        ).all()
        for catalogo_id, _chave, versao, definicao in padrao:
            _criar_caixa(conn, tabelas, fid, catalogo_id, versao, definicao, cats, agora, hoje)
        conn.execute(sa.text("INSERT INTO seed_flag (chave, aplicado_em) VALUES (:c, :a)"), {"c": flag, "a": agora})


def _criar_caixa(conn, tabelas, fid, catalogo_id, versao, definicao, cats, agora, hoje) -> None:
    caixa_t, ver_t = tabelas["sanitario_caixa"], tabelas["sanitario_caixa_versao"]
    vcat_t, log_t = tabelas["sanitario_caixa_versao_categoria"], tabelas["sanitario_log"]
    d = dict(definicao or {})
    nome = d["nome"].strip()
    if conn.execute(sa.select(caixa_t.c.id).where(
        caixa_t.c.fazenda_id == fid, caixa_t.c.nome_normalizado == _norm(nome), caixa_t.c.estado != "arquivada",
    )).first():
        return
    caixa_id = conn.execute(caixa_t.insert().values(
        fazenda_id=fid, nome=nome, nome_normalizado=_norm(nome), nome_curto=d.get("nome_curto") or nome,
        tipo=d.get("tipo") or "vacina", estado="inativa", obrigatoria=bool(d.get("obrigatoria")),
        padrao_fabrica=True, catalogo_id=catalogo_id, catalogo_versao=versao, criado_em=agora,
    )).inserted_primary_key[0]
    refs = [_norm(r) for r in (d.get("categorias_ref") or [])]
    cat_ids = sorted(cid for cid, cnome in cats if any(r in _norm(cnome) for r in refs)) if refs else []
    kw = {k: d.get(k, DEFAULTS_VERSAO.get(k)) for k in CAMPOS_VERSAO}
    avisos = []
    if refs and not cat_ids:
        avisos.append("Nenhuma categoria da fazenda casou com o público do catálogo: revise o público.")
        if d.get("fallback_idade_min_dias") is not None and kw.get("pub_idade_min_dias") is None:
            kw["pub_idade_min_dias"] = int(d["fallback_idade_min_dias"])
    if avisos:
        kw["observacao"] = " ".join(filter(None, [kw.get("observacao"), *avisos]))
    if isinstance(kw.get("comecar_em"), str):
        kw["comecar_em"] = date.fromisoformat(kw["comecar_em"])
    versao_id = conn.execute(ver_t.insert().values(
        fazenda_id=fid, caixa_id=caixa_id, numero=1, vigente_desde=hoje, criado_em=agora, **kw,
    )).inserted_primary_key[0]
    for cid in cat_ids:
        conn.execute(vcat_t.insert().values(fazenda_id=fid, versao_id=versao_id, categoria_manejo_id=cid))
    conn.execute(caixa_t.update().where(caixa_t.c.id == caixa_id).values(versao_atual_id=versao_id))
    conn.execute(log_t.insert().values(
        fazenda_id=fid, tipo="caixa.versao", caixa_id=caixa_id, em=agora,
        texto_livre="Padrão de fábrica criado (inativo) a partir do catálogo central.",
        payload={"avisos": avisos} if avisos else None,
    ))


# ════════════════════════════════════════════════════════════════════════════
# Downgrade
# ════════════════════════════════════════════════════════════════════════════
def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if insp.has_table("seed_flag"):
        conn.execute(sa.text("DELETE FROM seed_flag WHERE chave LIKE 'sanitario_padrao_v1:%'"))
    existentes = set(insp.get_table_names())
    if conn.dialect.name == "postgresql":
        for t in reversed(TABELAS):
            if t in existentes:
                conn.execute(sa.text(f'DROP TABLE IF EXISTS "{t}" CASCADE'))
        return
    for t in reversed(TABELAS):
        if t in existentes:
            op.drop_table(t)
