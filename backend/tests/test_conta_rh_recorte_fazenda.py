"""
Recorte de fazenda na busca do lançamento financeiro espelho (ContaGerencial)
feita pelo módulo de RH.

O DEFEITO que estes testes travam: várias rotinas do RH localizavam a conta a
pagar/paga gerada por elas SÓ pelo `numero_lancamento`
(`select(ContaGerencial).where(ContaGerencial.numero_lancamento == ...)`),
sem `fazenda_id`. Hoje a numeração nasce global e a colisão é improvável, mas
ela não é chave: numa base importada — ou no dia em que o Financeiro passar a
numerar por fazenda — duas fazendas têm o mesmo número, e essas consultas
REESCREVEM ou APAGAM o lançamento de outro inquilino. Não há RLS no banco: o
isolamento existe só no código da aplicação, então é aqui que ele é provado.

O cenário é sempre o mesmo e é propositalmente o pior possível: as duas
fazendas têm uma ContaGerencial com o MESMO `numero_lancamento`, e a operação
é disparada pela fazenda A. Cada teste verifica os dois lados — que a conta da
fazenda B não foi tocada (nem editada, nem apagada) E que a operação continuou
funcionando na conta da própria fazenda A, para a correção não ser um simples
"parou de achar".
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import (
    ContaCorrente, ContaGerencial, Empreitada, EmpreitadaParcela, Fazenda, FolhaPagamento,
    LancamentoItem, Pessoa, ValeAvulso,
)
from fazenda.models.pessoal import ValeFuncionario

NUMERO = "LC-2026-00042"  # o mesmo número nas duas fazendas — o coração do teste


@pytest.fixture
def session():
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda A"))
        s.add(Fazenda(id=2, nome="Fazenda B"))
        s.add(Pessoa(id=1, nome="Funcionário A", tipo="Funcionário", fazenda_id=1))
        s.add(Pessoa(id=2, nome="Funcionário B", tipo="Funcionário", fazenda_id=2))
        s.add(ContaCorrente(id=1, banco="Banco A", agencia="0001", numero_conta="1-1", fazenda_id=1))
        s.commit()
        yield s


def _conta(fazenda_id: int, **extra) -> ContaGerencial:
    """Conta a pagar com o número COMPARTILHADO entre as fazendas."""
    dados = dict(
        numero_lancamento=NUMERO, descricao=f"Original da fazenda {fazenda_id}",
        fornecedor_cliente=f"Fornecedor {fazenda_id}", data_vencimento=date(2026, 3, 10),
        data_competencia=date(2026, 3, 1), data_emissao=date(2026, 3, 5),
        valor_total=1000.0, parcela_num=1, parcela_total=1, tipo="despesa", origem="auto",
        fazenda_id=fazenda_id,
    )
    dados.update(extra)
    return ContaGerencial(**dados)


def _contas_por_fazenda(session: Session) -> dict[int, ContaGerencial]:
    contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == NUMERO)).all()
    return {c.fazenda_id: c for c in contas}


def _vizinha_intacta(session: Session) -> ContaGerencial:
    """A conta da fazenda B, exigindo que ela ainda exista e siga original."""
    conta_b = session.exec(
        select(ContaGerencial).where(
            ContaGerencial.numero_lancamento == NUMERO, ContaGerencial.fazenda_id == 2,
        )
    ).first()
    assert conta_b is not None, "a conta da fazenda B foi APAGADA por uma operação da fazenda A"
    assert conta_b.descricao == "Original da fazenda 2"
    assert conta_b.fornecedor_cliente == "Fornecedor 2"
    assert conta_b.valor_total == 1000.0
    assert conta_b.valor_pago is None
    assert conta_b.data_vencimento == date(2026, 3, 10)
    return conta_b


# ---------------------------------------------------------------------------
# 1. Vale de funcionário — `_sincronizar_conta_vale` (rh_folha.py)
# ---------------------------------------------------------------------------
def test_sincronizar_conta_vale_nao_reescreve_conta_de_outra_fazenda(session):
    from fazenda.api.routers.cadastro.rh_folha import _sincronizar_conta_vale

    session.add(_conta(2))  # a vizinha entra PRIMEIRO: sem recorte, o `.first()` cai nela
    session.add(_conta(1))
    vale = ValeFuncionario(
        pessoa_id=1, valor_total=250.0, forma_pagamento="dinheiro", data_pagamento=date(2026, 3, 20),
        competencia_inicio="2026-03", numero_lancamento_gerado=NUMERO, fazenda_id=1,
    )
    session.add(vale)
    session.commit()

    pessoa = session.get(Pessoa, 1)
    conta_corrente = session.get(ContaCorrente, 1)
    _sincronizar_conta_vale(session, vale, pessoa, conta_corrente, None, fazenda_id=1)
    session.commit()

    contas = _contas_por_fazenda(session)
    # Não regrediu: a conta DA FAZENDA A foi mesmo atualizada pelo vale.
    assert contas[1].valor_total == 250.0
    assert contas[1].valor_pago == 250.0
    assert contas[1].fornecedor_cliente == "Funcionário A"
    _vizinha_intacta(session)


def test_sincronizar_conta_vale_sem_saida_de_caixa_nao_apaga_conta_vizinha(session):
    """`conta is None` (desconto integral em folha) faz a rotina APAGAR o
    lançamento do vale — o caminho mais destrutivo desta função."""
    from fazenda.api.routers.cadastro.rh_folha import _sincronizar_conta_vale

    session.add(_conta(2))  # a vizinha entra PRIMEIRO: sem recorte, o `.first()` cai nela
    session.add(_conta(1))
    vale = ValeFuncionario(
        pessoa_id=1, valor_total=250.0, forma_pagamento="desconto_integral_folha",
        data_pagamento=date(2026, 3, 20), competencia_inicio="2026-03",
        numero_lancamento_gerado=NUMERO, fazenda_id=1,
    )
    session.add(vale)
    session.commit()

    _sincronizar_conta_vale(session, vale, session.get(Pessoa, 1), None, None, fazenda_id=1)
    session.commit()

    contas = _contas_por_fazenda(session)
    assert 1 not in contas, "a conta da própria fazenda A deveria ter sido apagada"
    _vizinha_intacta(session)


# ---------------------------------------------------------------------------
# 2. Vale avulso — `_sincronizar_conta_vale_avulso` (rh_contratos.py)
# ---------------------------------------------------------------------------
def test_sincronizar_conta_vale_avulso_nao_reescreve_conta_de_outra_fazenda(session):
    from fazenda.api.routers.cadastro.rh_contratos import _sincronizar_conta_vale_avulso

    session.add(_conta(2))  # a vizinha entra PRIMEIRO: sem recorte, o `.first()` cai nela
    session.add(_conta(1))
    vale = ValeAvulso(
        origem_tipo="empreitada", origem_id=1, pessoa_id=1, valor=300.0,
        forma_pagamento="dinheiro", data_pagamento=date(2026, 3, 20),
        numero_lancamento_gerado=NUMERO, fazenda_id=1,
    )
    session.add(vale)
    session.commit()

    _sincronizar_conta_vale_avulso(session, vale, "Empreiteiro A", session.get(ContaCorrente, 1), fazenda_id=1)
    session.commit()

    contas = _contas_por_fazenda(session)
    assert contas[1].valor_total == 300.0
    assert contas[1].valor_pago == 300.0
    assert contas[1].fornecedor_cliente == "Empreiteiro A"
    _vizinha_intacta(session)


def test_sincronizar_conta_vale_avulso_sem_saida_de_caixa_nao_apaga_conta_vizinha(session):
    from fazenda.api.routers.cadastro.rh_contratos import _sincronizar_conta_vale_avulso

    session.add(_conta(2))  # a vizinha entra PRIMEIRO: sem recorte, o `.first()` cai nela
    session.add(_conta(1))
    vale = ValeAvulso(
        origem_tipo="empreitada", origem_id=1, pessoa_id=1, valor=300.0,
        forma_pagamento="desconto_proximo_pagamento", data_pagamento=date(2026, 3, 20),
        numero_lancamento_gerado=NUMERO, fazenda_id=1,
    )
    session.add(vale)
    session.commit()

    _sincronizar_conta_vale_avulso(session, vale, "Empreiteiro A", None, fazenda_id=1)
    session.commit()

    contas = _contas_por_fazenda(session)
    assert 1 not in contas
    _vizinha_intacta(session)


# ---------------------------------------------------------------------------
# 3. Exclusão de parcela de empreitada — endpoint (rh_contratos.py)
# ---------------------------------------------------------------------------
def test_excluir_parcela_empreitada_nao_apaga_conta_de_outra_fazenda(session):
    from fazenda.api.routers.cadastro.rh_contratos import excluir_parcela_empreitada

    session.add(_conta(2))  # a vizinha entra PRIMEIRO: sem recorte, o `.first()` cai nela
    session.add(_conta(1))
    session.add(Empreitada(id=1, pessoa_id=1, descricao="Cerca", valor_total=1000.0,
                           tipo_pagamento="parcelado", fazenda_id=1))
    session.add(EmpreitadaParcela(id=1, empreitada_id=1, data_vencimento=date(2026, 3, 10),
                                  valor=1000.0, numero_lancamento_gerado=NUMERO, fazenda_id=1))
    session.commit()

    excluir_parcela_empreitada(1, session=session, fazenda_id=1)

    contas = _contas_por_fazenda(session)
    assert 1 not in contas, "a conta da própria fazenda A deveria ter sido apagada com a parcela"
    assert session.get(EmpreitadaParcela, 1) is None
    _vizinha_intacta(session)


# ---------------------------------------------------------------------------
# 4. Edição/redistribuição de parcela — `_sincronizar_conta_parcela`
# ---------------------------------------------------------------------------
def test_sincronizar_conta_parcela_nao_remarca_divida_de_outra_fazenda(session):
    from fazenda.api.routers.cadastro.rh_contratos import _sincronizar_conta_parcela

    session.add(_conta(2))  # a vizinha entra PRIMEIRO: sem recorte, o `.first()` cai nela
    session.add(_conta(1))
    session.commit()

    _sincronizar_conta_parcela(session, NUMERO, date(2026, 9, 30), 777.0, fazenda_id=1)
    session.commit()

    contas = _contas_por_fazenda(session)
    assert contas[1].valor_total == 777.0
    assert contas[1].data_vencimento == date(2026, 9, 30)
    _vizinha_intacta(session)


# ---------------------------------------------------------------------------
# 5. Abatimento/reversão de vale avulso — `_sincronizar_conta_do_item`
# ---------------------------------------------------------------------------
def test_sincronizar_conta_do_item_nao_reescreve_valor_de_outra_fazenda(session):
    from fazenda.api.routers.cadastro.rh_contratos import _sincronizar_conta_do_item

    session.add(_conta(2))  # a vizinha entra PRIMEIRO: sem recorte, o `.first()` cai nela
    session.add(_conta(1))
    parcela = EmpreitadaParcela(
        id=1, empreitada_id=1, data_vencimento=date(2026, 3, 10), valor=640.0,
        numero_lancamento_gerado=NUMERO, fazenda_id=1,
    )
    session.add(parcela)
    session.commit()

    _sincronizar_conta_do_item(session, parcela)
    session.commit()

    contas = _contas_por_fazenda(session)
    assert contas[1].valor_total == 640.0
    _vizinha_intacta(session)


def test_conta_paga_do_item_nao_ve_a_baixa_da_outra_fazenda(session):
    """A trava de reversão (`_bloquear_reversao_de_abatimento_pago`) pergunta
    a `_conta_paga_do_item` se o item já foi pago. Com a busca só pelo número,
    a BAIXA da fazenda B travava (com uma mensagem citando o lançamento
    alheio) uma reversão perfeitamente legítima da fazenda A."""
    from fazenda.api.routers.cadastro.rh_contratos import _conta_paga_do_item

    session.add(_conta(2, valor_pago=1000.0, data_pagamento=date(2026, 3, 11)))  # vizinha primeiro
    session.add(_conta(1))
    parcela = EmpreitadaParcela(
        id=1, empreitada_id=1, data_vencimento=date(2026, 3, 10), valor=1000.0,
        numero_lancamento_gerado=NUMERO, fazenda_id=1,
    )
    session.add(parcela)
    session.commit()

    assert _conta_paga_do_item(session, parcela) is None

    # E continua enxergando a baixa da PRÓPRIA fazenda (não regrediu).
    conta_a = _contas_por_fazenda(session)[1]
    conta_a.valor_pago = 1000.0
    conta_a.data_pagamento = date(2026, 3, 12)
    session.add(conta_a)
    session.commit()
    achada = _conta_paga_do_item(session, parcela)
    assert achada is not None and achada.fazenda_id == 1


# ---------------------------------------------------------------------------
# 6. Self-heal de folha duplicada — `_remover_folha_duplicada` (rh_folha.py)
# ---------------------------------------------------------------------------
def test_remover_folha_duplicada_nao_apaga_conta_de_outra_fazenda(session):
    from fazenda.api.routers.cadastro.rh_folha import _remover_folha_duplicada

    session.add(_conta(2))  # a vizinha entra PRIMEIRO: sem recorte, o `.first()` cai nela
    session.add(_conta(1))
    # Duas folhas da MESMA pessoa/competência na fazenda A: a mais nova fica,
    # a mais antiga (com o número em disputa) é varrida junto com sua conta.
    session.add(FolhaPagamento(id=1, pessoa_id=1, competencia="2026-03", valor_bruto=2000.0,
                               valor_liquido=2000.0, numero_lancamento_gerado=NUMERO, fazenda_id=1))
    session.add(FolhaPagamento(id=2, pessoa_id=1, competencia="2026-03", valor_bruto=2000.0,
                               valor_liquido=2000.0, fazenda_id=1))
    session.commit()

    _remover_folha_duplicada(session, fazenda_id=1)

    assert session.get(FolhaPagamento, 1) is None, "a folha duplicada deveria ter sido removida"
    assert session.get(FolhaPagamento, 2) is not None
    contas = _contas_por_fazenda(session)
    assert 1 not in contas, "a conta da folha duplicada da fazenda A deveria ter sido apagada"
    _vizinha_intacta(session)


# ---------------------------------------------------------------------------
# 7. Data da compra que vira `data_pagamento` do vale — rh_vale_item.py
# ---------------------------------------------------------------------------
def test_data_pagamento_do_vale_de_item_nao_sai_da_nota_de_outra_fazenda(session):
    """Leitura, não escrita — mas a data que sai daqui é gravada no vale. Com
    a busca só pelo número, o `.first()` podia devolver a nota da fazenda B e
    datar em silêncio o vale da fazenda A com a compra do vizinho."""
    from fazenda.api.routers.cadastro.rh_vale_item import _resolver_data_pagamento_vale

    session.add(_conta(2, data_emissao=date(2020, 1, 1)))  # a "vizinha" entra PRIMEIRO na tabela
    session.add(_conta(1, data_emissao=date(2026, 3, 5)))
    item = LancamentoItem(
        id=1, numero_lancamento=NUMERO, produto="Ração", valor_total=500.0,
        tipo="despesa", data_competencia=date(2026, 3, 1), fazenda_id=1,
    )
    session.add(item)
    session.commit()

    assert _resolver_data_pagamento_vale(item, session, fazenda_id=1) == date(2026, 3, 5)
