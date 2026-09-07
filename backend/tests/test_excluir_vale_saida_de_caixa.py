"""
DELETE de vale (funcionário e avulso) — o que vai junto, e quando a exclusão
passa a ser recusada.

EXCLUIR ≠ CANCELAR, e é essa confusão que este arquivo protege. As duas
rotinas apagavam a `ContaGerencial` do vale SEM conferir nada e SEM avisar —
o mesmo furo fechado em folha/férias/13º/guias (PRs #725 e #726). Só que aqui
a conta NASCE PAGA por desenho (o vale é entregue no ato, ver
`_sincronizar_conta_vale`): aplicar a trava daquelas quatro tornaria excluir
um vale impossível para sempre, e o DELETE é a única porta para "lancei
errado". Então o desenho é outro:

- a exclusão CONTINUA apagando a saída de caixa (é o que corrige um vale que
  nunca deveria ter existido), mas a tela recebe ANTES o que vai junto —
  lançamento nomeado, valor e data (`GET .../exclusao`);
- ela é RECUSADA quando há trabalho humano investido naquele lançamento:
  comprovante anexado ao vale, documento anexado ao lançamento, ou valor
  acertado à mão no Financeiro;
- e o diálogo ensina a porta certa quando a intenção era perdoar o vale:
  "Cancelar o vale", que mantém a saída de caixa e tem desfazer.

Cobre também a trava que já existia (vale em folha PAGA) e o isolamento
multi-fazenda das duas buscas de conta, que passaram a usar
`_conta_do_numero` (recorte de fazenda DENTRO da consulta).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaCorrente, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, DocumentoArquivado, Fazenda,
    LancamentoAnexo, Pessoa, ValeAvulso, ValeFuncionario, ValeParcela,
)


class _FakeUser:
    id = 1
    papel = "admin"
    ativo = True
    username = "teste"


def _montar_app(engine, fazenda_id: int | None):
    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    if fazenda_id is not None:
        main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
        main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fazenda_id
    return main.app


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    app = _montar_app(engine, None)
    with TestClient(app) as c:
        yield c, engine
    app.dependency_overrides.clear()


@pytest.fixture
def duas_fazendas():
    """Sessão logada na fazenda 1, com a fazenda 2 existindo ao lado."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um", ativa=True))
        s.add(Fazenda(id=2, nome="Fazenda Dois", ativa=True))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="financeiro", ativo=True))
        s.commit()
    app = _montar_app(engine, 1)
    with TestClient(app) as c:
        yield c, engine
    app.dependency_overrides.clear()


def _pessoa(engine, nome: str = "Leomir Bonfim", fazenda_id: int | None = None) -> int:
    with Session(engine) as s:
        p = Pessoa(nome=nome, tipo="Funcionário", salario_base=3000.0, fazenda_id=fazenda_id)
        s.add(p)
        s.commit()
        s.refresh(p)
        return p.id


def _conta_corrente(engine, fazenda_id: int | None = None) -> int:
    with Session(engine) as s:
        conta = ContaCorrente(
            banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6", fazenda_id=fazenda_id,
        )
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


def _lancar_vale(c, pessoa_id: int, conta_corrente_id: int, valor: float = 300.0) -> dict:
    r = c.post("/cadastro/vales", json={
        "pessoa_id": pessoa_id, "valor_total": valor, "forma_pagamento": "pix",
        "data_pagamento": "2026-07-05", "parcelas": 1, "competencia_inicio": "2026-07",
        "conta_corrente_id": conta_corrente_id,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _conta_do_vale(engine, numero: str, fazenda_id: int | None = None) -> ContaGerencial | None:
    with Session(engine) as s:
        return s.exec(
            select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == numero, ContaGerencial.fazenda_id == fazenda_id,
            )
        ).first()


def _anexar_comprovante_ao_vale(engine, *, vale_funcionario_id=None, vale_avulso_id=None, fazenda_id=None) -> int:
    """O que a rota /vales/{tipo}/{id}/comprovante grava (sem passar pelo
    Storage): o comprovante do pix guardado por quem conferiu o pagamento."""
    with Session(engine) as s:
        anexo = LancamentoAnexo(
            vale_funcionario_id=vale_funcionario_id, vale_avulso_id=vale_avulso_id,
            nome_arquivo="pix.pdf", mime_type="application/pdf", tamanho_bytes=1024,
            categoria="Comprovante", caminho_storage="fazenda-1/vales/x/0001_pix.pdf",
            fazenda_id=fazenda_id,
        )
        s.add(anexo)
        s.commit()
        s.refresh(anexo)
        return anexo.id


# ---------------------------------------------------------------------------
# A porta continua aberta — e agora diz o que leva junto
# ---------------------------------------------------------------------------
class TestExclusaoNormalDeValeDeFuncionario:
    def test_exclui_o_vale_e_a_saida_de_caixa_junto(self, client):
        """O caso que NÃO pode ser travado: vale lançado errado, conta já
        paga (ela nasce paga), exclusão funciona e o lançamento some com ele."""
        c, engine = client
        vale = _lancar_vale(c, _pessoa(engine), _conta_corrente(engine))
        numero = vale["numero_lancamento_gerado"]
        conta = _conta_do_vale(engine, numero)
        assert conta is not None and conta.valor_pago == 300.0

        assert c.delete(f"/cadastro/vales/{vale['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]) is None
            assert s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale["id"])).all() == []
            assert s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first() is None

    def test_a_previa_nomeia_a_saida_de_caixa_e_ensina_o_cancelar(self, client):
        """A tela não pode inventar essa frase: o número do lançamento, a data
        e a conta bancária da baixa vivem só no Financeiro."""
        c, engine = client
        vale = _lancar_vale(c, _pessoa(engine), _conta_corrente(engine))
        previa = c.get(f"/cadastro/vales/{vale['id']}/exclusao").json()

        assert previa["pode_excluir"] is True
        assert previa["impedimento"] is None
        assert previa["lancamento"]["numero_lancamento"] == vale["numero_lancamento_gerado"]
        assert previa["lancamento"]["valor"] == 300.0
        assert previa["lancamento"]["data_pagamento"] == "2026-07-05"
        assert vale["numero_lancamento_gerado"] in previa["confirmacao"]
        assert "05/07/2026" in previa["confirmacao"]
        assert "Leomir Bonfim" in previa["confirmacao"]
        # A diferença que o dono confundiu, dita na própria tela.
        assert "Cancelar o vale" in previa["alternativa"]

    def test_vale_sem_saida_de_caixa_avisa_que_nada_some_do_extrato(self, client):
        """Desconto integral na folha não move caixa — não há lançamento a
        apagar, e o diálogo tem de dizer isso em vez de assustar à toa."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "desconto_integral_folha",
            "data_pagamento": "2026-07-05", "parcelas": 1, "competencia_inicio": "2026-07",
        })
        assert r.status_code == 200, r.text
        previa = c.get(f"/cadastro/vales/{r.json()['id']}/exclusao").json()
        assert previa["pode_excluir"] is True
        assert previa["lancamento"] is None
        assert "não tem saída de caixa" in previa["confirmacao"]


# ---------------------------------------------------------------------------
# Trabalho humano no lançamento → 400 (com contraprova em cada sinal)
# ---------------------------------------------------------------------------
class TestRecusaPorTrabalhoHumanoNoLancamento:
    def test_comprovante_anexado_ao_vale_bloqueia_e_manda_cancelar(self, client):
        c, engine = client
        vale = _lancar_vale(c, _pessoa(engine), _conta_corrente(engine))
        numero = vale["numero_lancamento_gerado"]
        _anexar_comprovante_ao_vale(engine, vale_funcionario_id=vale["id"])

        r = c.delete(f"/cadastro/vales/{vale['id']}")
        assert r.status_code == 400, r.text
        assert "comprovante anexado" in r.json()["detail"]
        assert "Cancelar o vale" in r.json()["detail"]
        # Nada foi tocado: vale, parcelas e saída de caixa continuam de pé.
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]) is not None
            assert _conta_do_vale(engine, numero) is not None
        # E a tela recebe o mesmo motivo ANTES de perguntar qualquer coisa.
        previa = c.get(f"/cadastro/vales/{vale['id']}/exclusao").json()
        assert previa["pode_excluir"] is False
        assert "comprovante anexado" in previa["impedimento"]

    def test_contraprova_sem_comprovante_a_exclusao_passa(self, client):
        """O mesmo vale, sem o anexo: nada bloqueia — a recusa acima é do
        comprovante, não da conta estar paga."""
        c, engine = client
        vale = _lancar_vale(c, _pessoa(engine), _conta_corrente(engine))
        anexo_id = _anexar_comprovante_ao_vale(engine, vale_funcionario_id=vale["id"])
        assert c.delete(f"/cadastro/vales/{vale['id']}").status_code == 400
        with Session(engine) as s:
            s.delete(s.get(LancamentoAnexo, anexo_id))
            s.commit()
        assert c.delete(f"/cadastro/vales/{vale['id']}").status_code == 200

    def test_documento_anexado_ao_lancamento_bloqueia(self, client):
        """Anexo do lado do Financeiro (`LancamentoAnexo.numero_lancamento`):
        apagar o lançamento deixaria o documento sem nada por trás."""
        c, engine = client
        vale = _lancar_vale(c, _pessoa(engine), _conta_corrente(engine))
        with Session(engine) as s:
            s.add(LancamentoAnexo(
                numero_lancamento=vale["numero_lancamento_gerado"], nome_arquivo="recibo.pdf",
                mime_type="application/pdf", tamanho_bytes=10, caminho_storage="x/recibo.pdf",
            ))
            s.commit()

        r = c.delete(f"/cadastro/vales/{vale['id']}")
        assert r.status_code == 400, r.text
        assert "documento(s) anexado(s)" in r.json()["detail"]

    def test_documento_arquivado_no_lancamento_bloqueia(self, client):
        """Mesma natureza, pela Central de Documentos."""
        c, engine = client
        vale = _lancar_vale(c, _pessoa(engine), _conta_corrente(engine))
        with Session(engine) as s:
            s.add(DocumentoArquivado(
                categoria="Comprovante", nome_original="pix.pdf", caminho_storage="x/pix.pdf",
                mime_type="application/pdf", tamanho_bytes=10, inserir_no_balanco=True,
                numero_lancamento=vale["numero_lancamento_gerado"],
            ))
            s.commit()

        assert c.delete(f"/cadastro/vales/{vale['id']}").status_code == 400

    def test_valor_acertado_a_mao_no_financeiro_bloqueia(self, client):
        """A sincronização reescreve valor_total E valor_pago com o valor do
        vale; divergência é acerto manual em Lançamentos — alguém bateu o
        extrato do banco. Apagar levaria esse acerto embora sem rastro."""
        c, engine = client
        vale = _lancar_vale(c, _pessoa(engine), _conta_corrente(engine))
        numero = vale["numero_lancamento_gerado"]
        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()
            conta.valor_pago = 285.0  # o banco debitou menos do que o vale diz
            s.add(conta)
            s.commit()

        r = c.delete(f"/cadastro/vales/{vale['id']}")
        assert r.status_code == 400, r.text
        assert "ajustada à mão" in r.json()["detail"]
        assert _conta_do_vale(engine, numero) is not None

    def test_contraprova_valor_igual_ao_do_vale_nao_bloqueia(self, client):
        """Contraprova do sinal acima: conta paga com o valor certo (o estado
        NORMAL de todo vale) continua excluível — senão a porta fecharia para
        sempre, que é o que não pode acontecer aqui."""
        c, engine = client
        vale = _lancar_vale(c, _pessoa(engine), _conta_corrente(engine))
        assert c.delete(f"/cadastro/vales/{vale['id']}").status_code == 200


# ---------------------------------------------------------------------------
# A trava que já existia — vale que já caiu em folha PAGA
# ---------------------------------------------------------------------------
class TestValeEmFolhaPaga:
    def test_vale_de_competencia_com_folha_paga_nao_e_excluido(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        vale = _lancar_vale(c, pessoa_id, _conta_corrente(engine))
        folha = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
            "data_pagamento": "2026-08-05",
        })
        assert folha.status_code == 200, folha.text
        folha_id = folha.json()["id"]
        r = c.put(f"/cadastro/folha-pagamento/{folha_id}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0,
            "data_pagamento": "2026-08-05", "status": "pago",
        })
        assert r.status_code == 200, r.text

        r = c.delete(f"/cadastro/vales/{vale['id']}")
        assert r.status_code == 400, r.text
        assert "folha paga" in r.json()["detail"]
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]) is not None
        previa = c.get(f"/cadastro/vales/{vale['id']}/exclusao").json()
        assert previa["pode_excluir"] is False
        assert "folha paga" in previa["impedimento"]


# ---------------------------------------------------------------------------
# Vale avulso (Empreitada/Contrato/Diária)
# ---------------------------------------------------------------------------
def _empreitada(c) -> dict:
    pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Empreiteiro", "tipos": ["Empreiteiro"]}).json()["id"]
    return c.post("/cadastro/empreitadas", json={
        "pessoa_id": pessoa_id, "descricao": "Roçagem", "valor_total": 3000.0, "tipo_pagamento": "mensal",
        "parcelas": [{"data_vencimento": "2026-08-05", "valor": 1500.0},
                     {"data_vencimento": "2026-09-05", "valor": 1500.0}],
    }).json()


def _lancar_vale_avulso(c, empreitada_id: int, conta_corrente_id: int) -> dict:
    r = c.post("/cadastro/vale-avulso", json={
        "origem_tipo": "empreitada", "origem_id": empreitada_id, "valor": 500.0,
        "forma_pagamento": "pix", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_corrente_id,
    })
    assert r.status_code == 200, r.text
    return r.json()["vale"]


class TestExclusaoDeValeAvulso:
    def test_exclui_o_vale_e_a_saida_de_caixa_junto(self, client):
        c, engine = client
        vale = _lancar_vale_avulso(c, _empreitada(c)["id"], _conta_corrente(engine))
        numero = vale["numero_lancamento_gerado"]
        assert _conta_do_vale(engine, numero) is not None

        assert c.delete(f"/cadastro/vale-avulso/{vale['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(ValeAvulso, vale["id"]) is None
            assert s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first() is None

    def test_previa_nomeia_a_saida_de_caixa(self, client):
        c, engine = client
        vale = _lancar_vale_avulso(c, _empreitada(c)["id"], _conta_corrente(engine))
        previa = c.get(f"/cadastro/vale-avulso/{vale['id']}/exclusao").json()
        assert previa["pode_excluir"] is True
        assert previa["lancamento"]["numero_lancamento"] == vale["numero_lancamento_gerado"]
        assert previa["lancamento"]["valor"] == 500.0
        assert "24/07/2026" in previa["confirmacao"]
        # Não existe "cancelar" para vale avulso — a alternativa é outra.
        assert "edite o vale" in previa["alternativa"]

    def test_comprovante_anexado_bloqueia_e_o_abatimento_nao_e_revertido(self, client):
        """A recusa vem ANTES de `_reverter_vale_avulso`, que já escreve nas
        parcelas: recusar no meio deixaria o abatimento desfeito e o vale de
        pé — as duas pontas divergentes."""
        c, engine = client
        empreitada = _empreitada(c)
        vale = _lancar_vale_avulso(c, empreitada["id"], _conta_corrente(engine))
        _anexar_comprovante_ao_vale(engine, vale_avulso_id=vale["id"])

        r = c.delete(f"/cadastro/vale-avulso/{vale['id']}")
        assert r.status_code == 400, r.text
        assert "comprovante anexado" in r.json()["detail"]
        with Session(engine) as s:
            assert s.get(ValeAvulso, vale["id"]) is not None
        # O abatimento continua aplicado (1500 - 500), não foi revertido.
        parcelas = next(e for e in c.get("/cadastro/empreitadas").json() if e["id"] == empreitada["id"])["parcelas"]
        assert sorted(p["valor"] for p in parcelas) == [1000.0, 1500.0]

    def test_valor_acertado_a_mao_no_financeiro_bloqueia(self, client):
        c, engine = client
        vale = _lancar_vale_avulso(c, _empreitada(c)["id"], _conta_corrente(engine))
        with Session(engine) as s:
            conta = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale["numero_lancamento_gerado"])
            ).first()
            conta.valor_total = 480.0
            s.add(conta)
            s.commit()
        r = c.delete(f"/cadastro/vale-avulso/{vale['id']}")
        assert r.status_code == 400, r.text
        assert "ajustada à mão" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Multi-fazenda — a busca da conta passou a recortar DENTRO da consulta
# ---------------------------------------------------------------------------
def _so_a_conta_paga_da_vizinha(engine, numero: str) -> int:
    """Deixa no banco UMA conta com esse `numero_lancamento`: a da fazenda 2,
    JÁ PAGA. A da fazenda 1 sai de cena (base migrada, número reaproveitado)
    — é o arranjo em que a busca sem recorte de fazenda alcança e apaga o
    pagamento da VIZINHA."""
    with Session(engine) as s:
        minha = s.exec(
            select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == numero, ContaGerencial.fazenda_id == 1,
            )
        ).first()
        if minha is not None:
            s.delete(minha)
        conta = ContaGerencial(
            numero_lancamento=numero, descricao="Vale da vizinha", data_vencimento=date(2026, 7, 5),
            fornecedor_cliente="Vizinho", tipo_documento="Vale de funcionário", valor_total=900.0,
            parcela_num=1, parcela_total=1, tipo="despesa", origem="auto",
            data_pagamento=date(2026, 7, 5), valor_pago=900.0, fazenda_id=2,
        )
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


class TestIsolamentoEntreFazendas:
    def test_vale_de_outra_fazenda_devolve_404(self, duas_fazendas):
        c, engine = duas_fazendas
        with Session(engine) as s:
            vale = ValeFuncionario(
                pessoa_id=_pessoa(engine, nome="Vizinho", fazenda_id=2), valor_total=300.0,
                forma_pagamento="pix", data_pagamento=date(2026, 7, 5), parcelas=1,
                competencia_inicio="2026-07", fazenda_id=2,
            )
            s.add(vale)
            s.commit()
            s.refresh(vale)
            vale_id = vale.id

        assert c.delete(f"/cadastro/vales/{vale_id}").status_code == 404
        assert c.get(f"/cadastro/vales/{vale_id}/exclusao").status_code == 404
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale_id) is not None

    def test_conta_homonima_paga_da_vizinha_nao_e_alcancada(self, duas_fazendas):
        """Contraprova do recorte: excluir o MEU vale não pode apagar (nem
        ler) a conta de outra fazenda que carrega o mesmo número."""
        c, engine = duas_fazendas
        vale = _lancar_vale(c, _pessoa(engine, fazenda_id=1), _conta_corrente(engine, fazenda_id=1))
        numero = vale["numero_lancamento_gerado"]
        conta_vizinha_id = _so_a_conta_paga_da_vizinha(engine, numero)

        assert c.delete(f"/cadastro/vales/{vale['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(ValeFuncionario, vale["id"]) is None
            restantes = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).all()
            assert [conta.fazenda_id for conta in restantes] == [2]
            assert s.get(ContaGerencial, conta_vizinha_id).valor_pago == 900.0

    def test_vale_avulso_conta_homonima_paga_da_vizinha_nao_e_alcancada(self, duas_fazendas):
        c, engine = duas_fazendas
        vale = _lancar_vale_avulso(c, _empreitada(c)["id"], _conta_corrente(engine, fazenda_id=1))
        numero = vale["numero_lancamento_gerado"]
        conta_vizinha_id = _so_a_conta_paga_da_vizinha(engine, numero)

        assert c.delete(f"/cadastro/vale-avulso/{vale['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(ValeAvulso, vale["id"]) is None
            restantes = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).all()
            assert [conta.fazenda_id for conta in restantes] == [2]
            assert s.get(ContaGerencial, conta_vizinha_id).valor_pago == 900.0
