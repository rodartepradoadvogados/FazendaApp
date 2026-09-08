"""
A exclusão SEM FAZENDA deixou de ser tolerada — e a exclusão COM fazenda
deixou de enxergar o lançamento do vizinho.

A REGRA DO DONO, textual: "Fazenda chegar vazia, tem que dar erro e pedido de
acionamento do suporte CowData. Isso só é resolvido se tiver uma fazenda
cadastrada, a pessoa cadastrada e usuário atribuído a uma pessoa cadastrada
dentro de uma fazenda."

Dois eixos, os dois provados aqui:

1. RECUSA. `fazenda_id=None` chegando ao motor de exclusões
   (`api/routers/exclusoes.py::_alvos` e as funções `_alvos_*` de
   `rules/exclusao_tipos/pessoal.py`) era o padrão tolerante: sem fazenda no
   token, nenhum `where` era aplicado e a rotina montava a lista de deleção
   a partir do banco INTEIRO. Agora é 409 com `ERRO_OPERACAO_SEM_FAZENDA` —
   e o teste cobra o TEXTO, porque essa mensagem é a única explicação que o
   usuário travado recebe (um "dados inválidos" genérico apagaria a
   instrução). A escape hatch continua: instalação com a tabela `fazenda`
   VAZIA não tem tenant a isolar e segue passando.

2. RECORTE. Com fazenda, o filtro entrou DENTRO da consulta. O cenário é
   sempre o pior possível e é o mesmo de tests/test_conta_rh_recorte_fazenda.py:
   as duas fazendas têm uma `ContaGerencial` com o MESMO `numero_lancamento`
   (ele é sequencial por ano, não é chave global), e a operação parte da
   fazenda A. A linha da fazenda B entra no banco PRIMEIRO de propósito —
   sem isso um `.first()`/`.in_()` sem recorte cairia na linha certa por
   acidente de ordenação e o teste passaria contra o código antigo.

Cada caso verifica os dois lados: que a fazenda B não foi tocada E que a
operação continua funcionando na fazenda A (contraprova), para a correção não
ser um simples "parou de achar".
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi import HTTPException
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import ERRO_OPERACAO_SEM_FAZENDA
from fazenda.models import (
    ContaGerencial,
    Contrato,
    ContratoParcela,
    Diaria,
    DiariaPagamento,
    Empreitada,
    EmpreitadaParcela,
    Fazenda,
    LancamentoItem,
    Pessoa,
    ValeAvulso,
    ValeAvulsoAbatimento,
)

NUMERO = "LC-2026-00042"  # o mesmo número nas duas fazendas — o coração do teste


def _engine():
    return create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False},
    )


@pytest.fixture
def session():
    """Duas fazendas cadastradas — ou seja, `multifazenda_provisionado` True,
    que é o corte a partir do qual a falta de fazenda deixa de ser legado
    tolerado e passa a ser recusa."""
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda A"))
        s.add(Fazenda(id=2, nome="Fazenda B"))
        s.add(Pessoa(id=1, nome="Empreiteiro A", tipo="Funcionário", fazenda_id=1))
        s.add(Pessoa(id=2, nome="Empreiteiro B", tipo="Funcionário", fazenda_id=2))
        s.commit()
        yield s


@pytest.fixture
def session_sem_fazenda():
    """Instalação anterior ao multi-fazenda: tabela `fazenda` vazia, todo
    registro com `fazenda_id` nulo. É a escape hatch — aqui a operação sem
    fazenda continua passando."""
    engine = _engine()
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Pessoa(id=1, nome="Empreiteiro legado", tipo="Funcionário"))
        s.commit()
        yield s


def _conta(fazenda_id: int | None, **extra) -> ContaGerencial:
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


def _contas_por_fazenda(session: Session) -> dict[int | None, ContaGerencial]:
    contas = session.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == NUMERO)).all()
    return {c.fazenda_id: c for c in contas}


def _ids(objetos: list) -> set[tuple[str, int]]:
    """(classe, id) de tudo que a exclusão levaria — a lista que o motor
    apaga em seguida (ver `confirmar` em exclusoes.py)."""
    return {(type(o).__name__, o.id) for o in objetos}


def _montar_empreitada_das_duas_fazendas(session: Session) -> None:
    """Fazenda B primeiro, sempre. Empreitada só na A — o que a B tem é a
    conta a pagar homônima, que é o que a exclusão da A não pode alcançar."""
    session.add(_conta(2))
    session.add(_conta(1))
    session.add(Empreitada(id=1, pessoa_id=1, descricao="Cerca", valor_total=1000.0,
                           tipo_pagamento="parcelado", fazenda_id=1))
    session.add(EmpreitadaParcela(id=1, empreitada_id=1, data_vencimento=date(2026, 3, 10),
                                  valor=1000.0, numero_lancamento_gerado=NUMERO, fazenda_id=1))
    session.commit()


def _montar_contrato_das_duas_fazendas(session: Session) -> None:
    session.add(_conta(2))
    session.add(_conta(1))
    session.add(Contrato(id=1, pessoa_id=1, descricao="Manutenção", valor_total=1000.0,
                         forma_pagamento="mensal", fazenda_id=1))
    session.add(ContratoParcela(id=1, contrato_id=1, data_vencimento=date(2026, 3, 10),
                                valor=1000.0, numero_lancamento_gerado=NUMERO, fazenda_id=1))
    session.commit()


# ---------------------------------------------------------------------------
# 1. A recusa: fazenda vazia não apaga mais nada
# ---------------------------------------------------------------------------
class TestRecusaSemFazenda:
    def test_mensagem_ensina_o_caminho_inteiro(self):
        """A constante é cobrada por teste de propósito: ela é a única
        explicação que o usuário travado recebe, e precisa dizer a ordem que o
        dono fixou (fazenda → pessoa dentro dela → usuário dessa pessoa) e para
        quem ligar quando ele mesmo não conseguir resolver."""
        texto = ERRO_OPERACAO_SEM_FAZENDA.lower()
        assert "fazenda" in texto
        assert "pessoa" in texto
        assert "usuário" in texto
        assert "suporte cowdata" in texto

    @pytest.mark.parametrize("tipo", ["empreitada", "contrato", "diaria", "diaria_pagamento", "financeiro"])
    def test_alvos_recusa_com_409(self, session, tipo):
        from fazenda.api.routers.exclusoes import _alvos

        _montar_empreitada_das_duas_fazendas(session)
        session.add(Diaria(id=1, pessoa_id=1, valor_diaria=50.0, data_inicio=date(2026, 3, 1), fazenda_id=1))
        session.commit()
        session.add(DiariaPagamento(id=1, diaria_id=1, data_pagamento=date(2026, 3, 5), valor=50.0, fazenda_id=1))
        session.commit()

        alvo = "1" if tipo != "financeiro" else str(_contas_por_fazenda(session)[1].id)
        with pytest.raises(HTTPException) as erro:
            _alvos(tipo, alvo, session, fazenda_id=None)
        assert erro.value.status_code == 409
        assert erro.value.detail == ERRO_OPERACAO_SEM_FAZENDA

    def test_recusa_nao_apaga_nem_desfaz_nada(self, session):
        """`_alvos_empreitada` MUTA antes de devolver a lista: reverte os vales
        avulsos (apagando os `ValeAvulsoAbatimento` e devolvendo o valor às
        parcelas). A recusa tem que acontecer ANTES disso — senão a operação
        recusada teria mexido no dinheiro do mesmo jeito."""
        from fazenda.rules.exclusao_tipos.pessoal import _alvos_empreitada

        _montar_empreitada_das_duas_fazendas(session)
        session.add(ValeAvulso(id=1, origem_tipo="empreitada", origem_id=1, pessoa_id=1, valor=200.0,
                               forma_pagamento="desconto_proximo_pagamento",
                               data_pagamento=date(2026, 3, 15), fazenda_id=1))
        session.commit()
        session.add(ValeAvulsoAbatimento(id=1, vale_avulso_id=1, item_tipo="empreitada_parcela",
                                         item_id=1, valor_abatido=200.0, fazenda_id=1))
        session.commit()

        with pytest.raises(HTTPException) as erro:
            _alvos_empreitada("1", session, fazenda_id=None)
        assert erro.value.status_code == 409

        session.expire_all()
        assert session.get(Empreitada, 1) is not None
        assert session.get(EmpreitadaParcela, 1).valor == 1000.0, "a reversão do vale NÃO podia ter rodado"
        assert session.get(ValeAvulso, 1) is not None
        assert session.get(ValeAvulsoAbatimento, 1) is not None
        contas = _contas_por_fazenda(session)
        assert set(contas) == {1, 2}, "nenhuma conta a pagar podia ter sumido"

    def test_instalacao_sem_nenhuma_fazenda_continua_passando(self, session_sem_fazenda):
        """A escape hatch, e é a mesma de `resolver_fazenda_id_escrita`: com
        zero fazendas não há tenant a isolar, e o recorte incondicional vira
        `fazenda_id IS NULL` — exatamente o conjunto de linhas desse ambiente.
        É o caso da maior parte da suíte de testes."""
        from fazenda.rules.exclusao_tipos.pessoal import _alvos_empreitada

        s = session_sem_fazenda
        s.add(_conta(None))
        s.add(Empreitada(id=1, pessoa_id=1, descricao="Cerca", valor_total=1000.0,
                         tipo_pagamento="parcelado"))
        s.add(EmpreitadaParcela(id=1, empreitada_id=1, data_vencimento=date(2026, 3, 10),
                                valor=1000.0, numero_lancamento_gerado=NUMERO))
        s.commit()

        _, objetos = _alvos_empreitada("1", s, fazenda_id=None)
        conta_legada = _contas_por_fazenda(s)[None]
        assert ("ContaGerencial", conta_legada.id) in _ids(objetos)


# ---------------------------------------------------------------------------
# 2. O recorte: a fazenda A não alcança a linha da fazenda B
# ---------------------------------------------------------------------------
class TestExclusaoNaoAlcancaAFazendaVizinha:
    def test_empreitada_leva_so_a_propria_conta(self, session):
        from fazenda.rules.exclusao_tipos.pessoal import _alvos_empreitada

        _montar_empreitada_das_duas_fazendas(session)
        contas = _contas_por_fazenda(session)

        _, objetos = _alvos_empreitada("1", session, fazenda_id=1)

        levados = _ids(objetos)
        assert ("ContaGerencial", contas[2].id) not in levados, \
            "a exclusão da fazenda A levaria embora a conta a pagar da fazenda B"
        # Contraprova: não é um "parou de achar" — a conta da PRÓPRIA fazenda
        # continua entrando na lista de exclusão, junto com a empreitada.
        assert ("ContaGerencial", contas[1].id) in levados
        assert ("Empreitada", 1) in levados
        assert ("EmpreitadaParcela", 1) in levados

    def test_contrato_leva_so_a_propria_conta(self, session):
        from fazenda.rules.exclusao_tipos.pessoal import _alvos_contrato

        _montar_contrato_das_duas_fazendas(session)
        contas = _contas_por_fazenda(session)

        _, objetos = _alvos_contrato("1", session, fazenda_id=1)

        levados = _ids(objetos)
        assert ("ContaGerencial", contas[2].id) not in levados
        assert ("ContaGerencial", contas[1].id) in levados
        assert ("Contrato", 1) in levados

    def test_pagamento_de_diaria_leva_so_a_propria_conta(self, session):
        from fazenda.rules.exclusao_tipos.pessoal import _alvos_diaria_pagamento

        session.add(_conta(2))  # a vizinha entra PRIMEIRO
        session.add(_conta(1))
        session.add(Diaria(id=1, pessoa_id=1, valor_diaria=50.0, data_inicio=date(2026, 3, 1), fazenda_id=1))
        session.commit()
        session.add(DiariaPagamento(id=1, diaria_id=1, data_pagamento=date(2026, 3, 5), valor=50.0,
                                    numero_lancamento_gerado=NUMERO, fazenda_id=1))
        session.commit()
        contas = _contas_por_fazenda(session)

        _, objetos = _alvos_diaria_pagamento("1", session, fazenda_id=1)

        levados = _ids(objetos)
        assert ("ContaGerencial", contas[2].id) not in levados
        assert ("ContaGerencial", contas[1].id) in levados
        assert ("DiariaPagamento", 1) in levados

    def test_diaria_leva_so_a_propria_conta_de_vale(self, session):
        from fazenda.rules.exclusao_tipos.pessoal import _alvos_diaria

        session.add(_conta(2))  # a vizinha entra PRIMEIRO
        session.add(_conta(1))
        session.add(Diaria(id=1, pessoa_id=1, valor_diaria=50.0, data_inicio=date(2026, 3, 1), fazenda_id=1))
        session.commit()
        session.add(ValeAvulso(id=1, origem_tipo="diaria", origem_id=1, pessoa_id=1, valor=100.0,
                               forma_pagamento="desconto_proximo_pagamento",
                               data_pagamento=date(2026, 3, 15), numero_lancamento_gerado=NUMERO,
                               fazenda_id=1))
        session.commit()
        contas = _contas_por_fazenda(session)

        _, objetos = _alvos_diaria("1", session, fazenda_id=1)

        levados = _ids(objetos)
        assert ("ContaGerencial", contas[2].id) not in levados
        assert ("ContaGerencial", contas[1].id) in levados
        assert ("Diaria", 1) in levados
        assert ("ValeAvulso", 1) in levados

    def test_financeiro_nao_leva_parcelas_nem_itens_da_vizinha(self, session):
        """O tipo "financeiro" apaga TODAS as parcelas do lançamento e os
        itens da nota. Sem recorte, "todas as parcelas de LC-2026-00042"
        incluía as da outra fazenda."""
        from fazenda.api.routers.exclusoes import _alvos

        # Vizinha primeiro, e parcelada (parcela_total > 1) dos dois lados,
        # que é o ramo que junta os "irmãos".
        session.add(_conta(2, parcela_num=1, parcela_total=2))
        session.add(_conta(2, parcela_num=2, parcela_total=2))
        session.add(_conta(1, parcela_num=1, parcela_total=2))
        session.add(_conta(1, parcela_num=2, parcela_total=2))
        session.add(LancamentoItem(id=1, numero_lancamento=NUMERO, produto="Ração B",
                                   valor_total=500.0, tipo="despesa",
                                   data_competencia=date(2026, 3, 1), fazenda_id=2))
        session.add(LancamentoItem(id=2, numero_lancamento=NUMERO, produto="Ração A",
                                   valor_total=500.0, tipo="despesa",
                                   data_competencia=date(2026, 3, 1), fazenda_id=1))
        session.commit()

        contas = session.exec(
            select(ContaGerencial).where(ContaGerencial.numero_lancamento == NUMERO)
        ).all()
        da_a = [c for c in contas if c.fazenda_id == 1]
        da_b = [c for c in contas if c.fazenda_id == 2]

        impacto, objetos = _alvos("financeiro", str(da_a[0].id), session, fazenda_id=1)

        levados = _ids(objetos)
        assert not any(("ContaGerencial", c.id) in levados for c in da_b), \
            "a exclusão do lançamento da fazenda A levaria as parcelas da B"
        assert ("LancamentoItem", 1) not in levados, "o item de nota da fazenda B foi levado junto"
        # Contraprova: as duas parcelas da fazenda A e o item dela vão mesmo.
        assert all(("ContaGerencial", c.id) in levados for c in da_a)
        assert ("LancamentoItem", 2) in levados
        assert "2 parcela(s) no total — todas serão excluídas" in impacto


# ---------------------------------------------------------------------------
# 3. `_numeros_pagos` — a baixa da fazenda B não é mais a baixa da fazenda A
# ---------------------------------------------------------------------------
class TestNumerosPagosNaoContamina:
    def test_baixa_da_vizinha_nao_marca_a_parcela_como_paga(self, session):
        from fazenda.api.routers.cadastro.rh_contratos import _numeros_pagos

        session.add(_conta(2, valor_pago=1000.0, data_pagamento=date(2026, 3, 11)))  # vizinha PAGA, primeiro
        session.add(_conta(1))  # a da fazenda A segue EM ABERTO
        session.commit()

        assert _numeros_pagos(session, [NUMERO], 1) == set()
        # Contraprova: a baixa da própria fazenda continua sendo vista.
        conta_a = _contas_por_fazenda(session)[1]
        conta_a.valor_pago = 1000.0
        conta_a.data_pagamento = date(2026, 3, 12)
        session.add(conta_a)
        session.commit()
        assert _numeros_pagos(session, [NUMERO], 1) == {NUMERO}

    def test_exclusao_de_empreitada_nao_e_bloqueada_pela_baixa_da_vizinha(self, session):
        """O efeito visível do defeito: a exclusão legítima de uma empreitada
        em aberto era recusada com 400 "parcela já paga — estorne a baixa",
        citando um lançamento de OUTRA fazenda, que o usuário não consegue
        nem abrir para estornar."""
        from fazenda.rules.exclusao_tipos.pessoal import _alvos_empreitada

        session.add(_conta(2, valor_pago=1000.0, data_pagamento=date(2026, 3, 11)))
        session.add(_conta(1))
        session.add(Empreitada(id=1, pessoa_id=1, descricao="Cerca", valor_total=1000.0,
                               tipo_pagamento="parcelado", fazenda_id=1))
        session.add(EmpreitadaParcela(id=1, empreitada_id=1, data_vencimento=date(2026, 3, 10),
                                      valor=1000.0, numero_lancamento_gerado=NUMERO, fazenda_id=1))
        session.commit()

        _, objetos = _alvos_empreitada("1", session, fazenda_id=1)
        assert ("Empreitada", 1) in _ids(objetos)

        # Contraprova: com a baixa na PRÓPRIA fazenda, a recusa volta.
        conta_a = _contas_por_fazenda(session)[1]
        conta_a.valor_pago = 1000.0
        conta_a.data_pagamento = date(2026, 3, 12)
        session.add(conta_a)
        session.commit()
        with pytest.raises(HTTPException) as erro:
            _alvos_empreitada("1", session, fazenda_id=1)
        assert erro.value.status_code == 400
        assert "já foi(ram) paga(s)" in erro.value.detail
