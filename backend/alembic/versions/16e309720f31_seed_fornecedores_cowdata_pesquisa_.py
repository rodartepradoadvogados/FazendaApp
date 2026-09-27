"""seed fornecedores da CowData (pesquisa aprovada pelo dono, set/2026)

20 fornecedores aprovados pelo dono para popular `fornecedor_cowdata` —
9 laboratórios/distribuidoras de medicamentos veterinários, 10 fornecedores
de alimentação para gado leiteiro (cooperativas + fábricas de concentrado),
e a COMIGO (cooperativa, ração + medicamentos + insumos), informada
diretamente pelo dono.

`FornecedorCowData` (fazenda/models/catalogo_cowdata.py) não tem campos de
endereço/cidade/estado — só nome/cnpj_cpf/telefone/email/observacoes/ativo
(ver docstring do modelo). Endereço, cidade, UF, a fonte de cada dado e
qualquer ressalva de verificação (CNPJ não confirmado, e-mail incerto etc.)
foram compatibilizados dentro de `observacoes` — nenhuma informação da
pesquisa foi descartada, só reorganizada dentro do que o cadastro atual
tem. Nenhum CNPJ/telefone/e-mail foi inventado: campo não encontrado na
pesquisa entra como None aqui (não como string vazia).

Classificação (`FornecedorCowDataClassificacao`) usa o vocabulário já
existente de `classificacao_cowdata` (semeado por d4f8a1c9e6b2) — os
fornecedores de medicamento entram em "Medicamentos e produtos
veterinários", os de alimentação em "Ração e insumos alimentares"; a
COMIGO (ração + medicamentos + insumos pecuários) entra nas duas. Não
criamos classificações novas por sub-tipo de ração (concentrado, silagem
etc.) — o cadastro de Fornecedor é por classe ampla; o detalhe de qual
produto/linha vem da pesquisa fica registrado em `observacoes`.

Idempotente: casa fornecedor existente por CNPJ/CPF normalizado (quando
tem) e por nome normalizado (minúsculas, sem acento, espaços colapsados),
pulando quem já existe — mesmo padrão de 9af2806b02ba. Sem import de
código da aplicação.

Revision ID: 16e309720f31
Revises: 9af2806b02ba
Create Date: 2026-09-27 08:10:00.000000

"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '16e309720f31'
down_revision: Union[str, Sequence[str], None] = '9af2806b02ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOME_CLASSIFICACAO_MEDICAMENTOS = "Medicamentos e produtos veterinários"
_NOME_CLASSIFICACAO_ALIMENTACAO = "Ração e insumos alimentares"

_ESPACOS = re.compile(r"\s+")
_NAO_ALFANUM = re.compile(r"[^a-z0-9]")


def _normalizar(texto: str | None) -> str:
    """Cópia local mínima de casamento_cadastro.normalizar — ver módulo 9af2806b02ba."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return _ESPACOS.sub(" ", sem_acento.lower()).strip()


def _normalizar_documento(texto: str | None) -> str:
    """CNPJ/CPF só pelos dígitos — pra comparar sem depender de máscara/pontuação."""
    return _NAO_ALFANUM.sub("", (texto or "").lower())


# Cada entrada: (nome, cnpj_cpf, telefone, email, observacoes, [classificações])
_FORNECEDORES_SEED: list[tuple[str, str | None, str | None, str | None, str, list[str]]] = [
    (
        "Vallée S.A.", "20.557.161/0001-98", "(38) 3229-7078", "lamarck@vallee.com.br",
        "Endereço: Avenida Comendador Antônio Loureiro Ramos, 1500 — Distrito Industrial, "
        "Montes Claros/MG. Categoria: Medicamentos e produtos veterinários. "
        "Obs.: e-mail encontrado em fonte pública, pode não ser o canal comercial padrão — verificar. "
        "Pesquisa 27/09/2026. Fontes: https://www.econodata.com.br/consulta-empresa/20557161000198-vallee-sa ; "
        "https://guiafacil.com/site/vallee/montes-claros/mg/3832297000/",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "Laboratórios Vencofarma do Brasil Ltda.", None, "(43) 3325-0784 / (43) 3329-6633 / 0800 400 7997", None,
        "Endereço: Travessa Dalva de Oliveira, 237 — Parque das Indústrias Leves, Londrina/PR. "
        "Categoria: Medicamentos e produtos veterinários. "
        "Obs.: CNPJ não confirmado com confiança suficiente na pesquisa — verificar na Receita Federal antes "
        "de usar para NF/pagamento. Empresa adquirida pelo grupo britânico Dechra Pharmaceuticals em 2018; "
        "matriz operacional continua em Londrina/PR. Pesquisa 27/09/2026. "
        "Fontes: https://www.yelp.com/biz/laborat%C3%B3rios-vencofarma-do-brasil-londrina ; "
        "https://jmba.com.br/transacao/7/dechra-pharmaceuticals-plc-adquiriu-a-totalidade-do-capital-social-da-venco-saude-animal- ; "
        "https://www.vencofarma.com.br/",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "Laboratórios Calbos Ltda.", "76.719.525/0003-05", "0800-645-8218 / (41) 3333-7920", "contato@calbos.com.br",
        "Endereço: Rua Antônio Moro, 340, Térreo — Costeira, São José dos Pinhais/PR. "
        "Categoria: Medicamentos e produtos veterinários. Pesquisa 27/09/2026. "
        "Fontes: https://www.econodata.com.br/consulta-empresa/76719525000305-laboratorios-calbos-ltda ; "
        "https://calbos.com.br/contato/",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "Laboratório Bravet Ltda.", "42.486.076/0001-19", "0800-025-1622 / (21) 2480-6868", "sac@bravet.com.br",
        "Endereço: Rua Visconde de Santa Cruz, 276 — Engenho Novo, Rio de Janeiro/RJ. "
        "Categoria: Medicamentos e produtos veterinários. Pesquisa 27/09/2026. "
        "Fontes: https://www.econodata.com.br/consulta-empresa/42486076000119-laboratorio-bravet-ltda ; "
        "https://www.bravet.com.br/contato",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "Ouro Fino Saúde Animal Ltda.", "57.624.462/0001-05", "0800-941-2000 / (16) 3518-2025 (SAC técnico)", None,
        "Endereço: Rodovia Anhanguera, SP-330, Km 298 — Distrito Industrial, Cravinhos/SP. "
        "Categoria: Medicamentos e produtos veterinários. "
        "Obs.: e-mail comercial não confirmado com confiança — verificar em ourofinosaudeanimal.com/contato. "
        "Pesquisa 27/09/2026. Fontes: https://www.econodata.com.br/consulta-empresa/57624462000105-ouro-fino-saude-animal-ltda ; "
        "https://www.ourofinosaudeanimal.com/contato/",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "Agener União (União Química Farmacêutica Nacional S.A.)", "60.665.981/0001-18", "0800-701-1799", None,
        "Endereço (escritório da divisão Agener União): Avenida Magalhães de Castro, 4.800, 16º andar, "
        "conj. 161/162, Edifício Continental Tower, São Paulo/SP. Matriz industrial do grupo em Embu-Guaçu/SP. "
        "Categoria: Medicamentos e produtos veterinários. "
        "Obs.: Agener União é uma divisão de negócio da União Química, não pessoa jurídica própria — "
        "verificar qual CNPJ de faturamento específico usar antes de cadastrar cotação/pedido. "
        "Pesquisa 27/09/2026. Fontes: https://agener.com.br/ ; "
        "https://www.uniaoquimica.com.br/sobre-nos/institucional/unidades-fabris/embu-guacu-sp/ ; "
        "https://cnpjagora.com/cnpj/uniao-quimica-farmaceutica-nacional-s-a/60665981000118",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "Vetnil Indústria e Comércio de Produtos Veterinários Ltda.", "73.196.438/0001-60", "(11) 3848-8500",
        "vetnil@vetnil.com.br",
        "Endereço: Avenida José Nicolau Estabile, 53 — Residencial Burch, Louveira/SP. "
        "Categoria: Medicamentos e produtos veterinários. Pesquisa 27/09/2026. "
        "Fontes: https://www.econodata.com.br/consulta-empresa/73196438000160-VETNIL-INDUSTRIA-E-COMERCIO-DE-PRODUTOS-VETERIN-LTDA ; "
        "https://vetnil.com.br/en/contact-us/",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "J.A. Saúde Animal S.A.", "03.749.465/0001-38", "(16) 3145-9920", "contato@jasaudeanimal.com.br",
        "Endereço: Travessa José Coelho de Freitas, 1679/1712 — Centro, Patrocínio Paulista/SP. "
        "Categoria: Medicamentos e produtos veterinários. Pesquisa 27/09/2026. "
        "Fontes: https://www.informecadastral.com.br/cnpj/ja-saude-animal-sa-03749465000138 ; "
        "https://www.jasaudeanimal.com.br/contato",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "Laboratório Bio-Vet Ltda. (Biovet)", "60.411.527/0001-30", "0800-055-6642", None,
        "Endereço: Rua Coronel José Nunes dos Santos, 639 — Centro, Vargem Grande Paulista/SP. "
        "Categoria: Medicamentos e produtos veterinários. "
        "Obs.: e-mail comercial não confirmado com confiança — verificar em biovet.com.br. "
        "Pesquisa 27/09/2026. Fontes: https://www.econodata.com.br/consulta-empresa/60411527000130-laboratorio-biovet-ltda ; "
        "https://www.biovet.com.br/a-empresa/",
        [_NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
    (
        "Alisul Alimentos S.A.", "89.548.523/0001-80", "(51) 2123-1400", "alisul.stm@alisul.com.br",
        "Endereço: Avenida João Carlos Hohendorff, 900 — Arroio da Manteiga, São Leopoldo/RS. "
        "Categoria: Alimentação leiteira — concentrado (linha \"Supra\", pré-parto). Pesquisa 27/09/2026. "
        "Fontes: https://www.econodata.com.br/empresas/rs/fabricacao-de-alimentos-para-animais-c-1066000 ; "
        "https://www.alisul.com.br/en/contact/ ; "
        "https://www.alisul.com.br/alisul-supra-racao-para-bovinos-de-leite-em-fase-de-pre-parto/",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "Puro Trato Nutrição Animal Ltda.", "92.730.902/0001-00", "(55) 3781-3476", "supervisao@purotrato.com.br",
        "Endereço: Avenida do Comércio, 1201 — Santa Fé, Santo Augusto/RS. "
        "Categoria: Alimentação leiteira — concentrado (linha \"Puro Milk\", pré-parto). Pesquisa 27/09/2026. "
        "Fontes: https://www.purotrato.com.br/contato ; https://www.purotrato.com.br/produtos/Puro-Milk-Pre-Parto-Especial",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "Cooperativa Languiru Ltda.", "89.774.160/0001-00", "0800-600-5834 / (51) 3762-5600", "sac@languiru.com.br",
        "Endereço: Rua Três de Outubro, 120 — Languiru, Teutônia/RS. "
        "Categoria: Alimentação leiteira — ração formulada (rede de lojas agropecuárias \"Agrocenter\", "
        "vende também insumos veterinários). Pesquisa 27/09/2026. "
        "Fontes: https://www.languiru.com.br/divisoes/agrocenters/ ; https://www.languiru.com.br/institucional/contato/",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "Cotrijal Cooperativa Agropecuária e Industrial", "91.495.549/0001-50", "(54) 3332-2500", None,
        "Endereço: Rua Júlio Graeff, 01 — Centro, Não-Me-Toque/RS. "
        "Categoria: Alimentação leiteira — ração formulada (divisão \"Cotrijal Nutrição Animal\"). "
        "Obs.: e-mail comercial não encontrado — usar formulário em cotrijal.com.br/fale-conosco. "
        "Pesquisa 27/09/2026. Fontes: https://www.econodata.com.br/consulta-empresa/91495549000150-cotrijal-cooperativa-agropecuaria-e-industrial ; "
        "https://www.cotrijal.com.br/cotrijal-nutricao",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "Castrolanda — Cooperativa Agroindustrial Ltda.", "76.108.349/0001-03", "(42) 3234-8000",
        "comunicacao@castrolanda.coop.br",
        "Endereço: Praça dos Imigrantes, 03 — Colônia Castrolanda, Castro/PR. "
        "Categoria: Alimentação leiteira — ração formulada (cooperativa com forte foco em pecuária leiteira). "
        "Pesquisa 27/09/2026. Fontes: https://www.econodata.com.br/consulta-empresa/76108349000103-castrolanda-cooperativa-agroindustrial-ltda ; "
        "https://www.castrolanda.coop.br/fale-conosco/",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "C.Vale Cooperativa Agroindustrial", "77.863.223/0001-07", "(44) 3649-6469", "faleconosco@cvale.com.br",
        "Endereço: Avenida Independência, 2347 — Centro, Palotina/PR. "
        "Categoria: Alimentação leiteira — ração formulada e alimentos balanceados (entre outras espécies). "
        "Pesquisa 27/09/2026. Fontes: https://www.econodata.com.br/consulta-empresa/77863223000107-cvale-cooperativa-agroindustrial ; "
        "https://pt.wikipedia.org/wiki/C._Vale_Cooperativa_Agroindustrial",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "Frísia Cooperativa Agroindustrial", "76.107.770/0001-08", "(42) 3231-9000", "tributario@frisia.coop.br",
        "Endereço: Avenida dos Pioneiros, 2.324, Carambeí/PR. "
        "Categoria: Alimentação leiteira — ração formulada (lojas agropecuárias próprias vendem ração para "
        "gado de leite, medicamentos veterinários para grandes animais e insumos). "
        "Obs.: CNPJ marcado \"verificar\" na pesquisa (diversos sufixos associados à cooperativa em fontes "
        "diferentes); e-mail acima é institucional/tributário — verificar canal comercial específico. "
        "Pesquisa 27/09/2026. Fontes: https://www.informecadastral.com.br/cnpj/frisia-cooperativa-agroindustrial-76107770000108 ; "
        "https://opresenterural.com.br/frisia-inaugura-sua-12a-loja-agropecuaria-e-expande-atuacao-no-segmento/",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "Capal Cooperativa Agroindustrial", "78.320.397/0001-96", "(43) 3512-1000", "faleconosco@capal.coop.br",
        "Endereço: Rua Saladino de Castro, 1375 — Centro, Arapoti/PR. "
        "Categoria: Alimentação leiteira — ração formulada (atua em leite e corte; duas fábricas de ração "
        "em Arapoti/PR — incluído pela linha leiteira). Pesquisa 27/09/2026. "
        "Fontes: https://www.econodata.com.br/consulta-empresa/78320397000196-capal-cooperativa-agroindustrial ; "
        "https://www.capal.coop.br/site/contato.php",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "Cooperativa Regional Auriverde", "83.731.927/0001-29", "(49) 3646-3700", "sac@cooperauriverde.com.br",
        "Endereço: Rua Moura Brasil, 791 — Centro, Cunha Porã/SC. "
        "Categoria: Alimentação leiteira — ração formulada (fábrica de ração para bovinos + divisão própria "
        "de bovinocultura leiteira/laticínio). Pesquisa 27/09/2026. "
        "Fontes: https://www.econodata.com.br/consulta-empresa/83731927000129-cooperativa-regional-auriverde ; "
        "https://www2.cooperauriverde.com.br/fabrica-de-racoes/bovinos/",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "Guabi Nutrição e Saúde Animal Ltda.", "02.918.654/0011-04", "0800-940-3100", None,
        "Endereço: Avenida Cambacica, 520, Conj. 712 — Parque dos Resedás, Campinas/SP. "
        "Categoria: Alimentação leiteira — ração formulada (entre outras espécies). "
        "Obs.: CNPJ acima é da unidade administrativa consultada em Campinas — verificar se é de fato o CNPJ "
        "da matriz legal (empresa tem ~19 filiais em 12 estados); grupo Alltech (EUA) tem participação "
        "societária — confirmar se atende ao critério de sede no Brasil antes de aprovar; e-mail comercial "
        "oficial não confirmado. Pesquisa 27/09/2026. "
        "Fontes: https://www.econodata.com.br/consulta-empresa/02918654001104-guabi-nutricao-e-saude-animal-ltda ; "
        "https://www.guabi.com.br/contato ; https://www.alltech.com/pt-BR/nossas-empresas/guabi",
        [_NOME_CLASSIFICACAO_ALIMENTACAO],
    ),
    (
        "COMIGO - Cooperativa Agropecuária dos Produtores Rurais do Sudoeste Goiano",
        "02.077.618/0030-10", "(64) 3629-7300", None,
        "Endereço: Rodovia GO-174 KM 45 à esquerda, s/n, zona rural, CEP 75915-000, Rio Verde/GO. "
        "Categoria: Ração formulada para bovinos de leite e de corte, medicamentos veterinários e insumos "
        "pecuários. Site institucional: www.comigo.com.br (informado pelo dono como \"e-mail\" — é o site, "
        "não um endereço de e-mail; nenhum e-mail comercial foi informado). "
        "Fornecedor informado diretamente pelo dono em 27/09/2026 (não passou pela pesquisa web).",
        [_NOME_CLASSIFICACAO_ALIMENTACAO, _NOME_CLASSIFICACAO_MEDICAMENTOS],
    ),
]


def upgrade() -> None:
    conn = op.get_bind()

    classificacao_ids_por_nome: dict[str, int] = {
        nome: cid for nome, cid in conn.execute(
            sa.text("SELECT nome, id FROM classificacao_cowdata")
        ).all()
    }
    faltantes = {
        nome for _, _, _, _, _, classificacoes in _FORNECEDORES_SEED for nome in classificacoes
    } - set(classificacao_ids_por_nome)
    if faltantes:
        print(f"[fornecedores cowdata] classificação(ões) não encontrada(s), pulando vínculo: {sorted(faltantes)!r}")

    existentes_nome = {_normalizar(n) for (n,) in conn.execute(sa.text("SELECT nome FROM fornecedor_cowdata")).all()}
    existentes_doc = {
        _normalizar_documento(d) for (d,) in conn.execute(
            sa.text("SELECT cnpj_cpf FROM fornecedor_cowdata WHERE cnpj_cpf IS NOT NULL")
        ).all()
    }
    existentes_doc.discard("")

    agora = datetime.utcnow()
    fornecedor_cowdata = sa.table(
        'fornecedor_cowdata',
        sa.column('nome', sa.String()), sa.column('cnpj_cpf', sa.String()), sa.column('telefone', sa.String()),
        sa.column('email', sa.String()), sa.column('observacoes', sa.Text()), sa.column('ativo', sa.Boolean()),
        sa.column('criado_em', sa.DateTime()),
    )
    fornecedor_cowdata_classificacao = sa.table(
        'fornecedor_cowdata_classificacao',
        sa.column('fornecedor_cowdata_id', sa.Integer()), sa.column('classificacao_id', sa.Integer()),
    )

    criados, pulados = 0, 0
    for nome, cnpj_cpf, telefone, email, observacoes, classificacoes in _FORNECEDORES_SEED:
        chave_nome = _normalizar(nome)
        chave_doc = _normalizar_documento(cnpj_cpf)
        if chave_nome in existentes_nome or (chave_doc and chave_doc in existentes_doc):
            pulados += 1
            continue

        conn.execute(fornecedor_cowdata.insert().values(
            nome=nome, cnpj_cpf=cnpj_cpf, telefone=telefone, email=email,
            observacoes=observacoes, ativo=True, criado_em=agora,
        ))
        novo_id = conn.execute(
            sa.text("SELECT id FROM fornecedor_cowdata WHERE nome = :nome ORDER BY id DESC LIMIT 1"),
            {"nome": nome},
        ).scalar()
        vinculos = [
            {"fornecedor_cowdata_id": novo_id, "classificacao_id": classificacao_ids_por_nome[c]}
            for c in classificacoes if c in classificacao_ids_por_nome
        ]
        if vinculos:
            conn.execute(fornecedor_cowdata_classificacao.insert(), vinculos)

        existentes_nome.add(chave_nome)
        if chave_doc:
            existentes_doc.add(chave_doc)
        criados += 1

    print(f"[fornecedores cowdata] {criados} fornecedor(es) criado(s), {pulados} já existiam (pulados).")


def downgrade() -> None:
    # Mesmo espírito de 9af2806b02ba: reverter um catálogo que a CowData já
    # pode ter editado/referenciado (cotações, vínculos) depois do seed é
    # mais arriscado do que deixar como está. No-op de propósito.
    pass
