"""
GET /cadastro/folha-pagamento-unificada — o mês de vale que a FAZENDA assumiu.

O DEFEITO QUE ISTO FECHA. `vale_assumido` nasceu no #722 e ficou só na resposta
de `GET /folha-pagamento` (Ações > Fechamento da folha). A tela de Contas >
Holerites e recibos lê o ledger unificado, e por ele o campo nunca viajou: quem
abria o holerite ali via o desconto de vale simplesmente SUMIR do mês, sem uma
palavra — e aquela tela é só consulta, não tem o painel de ações onde a
explicação já aparecia. Ficava parecendo erro de cálculo do sistema.

O QUE ESTES TESTES TRAVAM:

 A) a explicação chega ao ledger, com o motivo, a competência e a referência
    "Parcela k de n" — o suficiente para o documento dizer POR QUE o desconto
    sumiu;
 B) ela é INERTE: campo separado de `detalhe`, linha com provento/desconto
    nulos e `valor` zero, nenhum total mexido — nem o líquido do ledger, nem
    `totais`, nem um `detalhe + vale_assumido` somado por engano. Esta é a
    trava que importa: `detalhe` é somado em seis lugares (totais do holerite,
    equação do mês, verbas do pop-up de pagamento, regras do recibo, PDF e
    Excel), e um único somatório que esquecesse de pular a linha voltaria a
    cobrar do funcionário o que a fazenda pagou;
 C) isolamento entre fazendas-clientes, com contraprova dentro da fazenda
    certa — senão a ausência poderia ser só o ledger não ter a linha.

TOKEN DE VERDADE em tudo (`criar_token`), nunca `dependency_overrides` do
`get_fazenda_atual_id`: falsificar a claim tiraria do teste exatamente o que
ele precisa provar.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContaCorrente, ContratoFazenda, ContratoFazendaModulo, Fazenda, Pessoa, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import holerite


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    with Session(engine) as s:
        for fid, nome in ((1, "Fazenda Um"), (2, "Fazenda Dois")):
            s.add(Fazenda(id=fid, nome=nome, ativa=True))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        # Salário alto de propósito: o teto de 40% não pode ser o que faz um
        # teste de vale falhar.
        s.add(Pessoa(id=1, nome="Leomir Bonfim", tipo="Funcionário", salario_base=9000.0, fazenda_id=1))
        s.add(Pessoa(id=2, nome="Vizinho Silva", tipo="Funcionário", salario_base=9000.0, fazenda_id=2))
        s.add(Usuario(id=1, username="admin1", senha_hash=hash_senha("x"), papel="admin", ativo=True, pessoa_id=1))
        s.add(Usuario(id=2, username="admin2", senha_hash=hash_senha("x"), papel="admin", ativo=True, pessoa_id=2))
        s.add(UsuarioFazenda(usuario_id=1, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=2, fazenda_id=2))
        s.add(ContaCorrente(id=1, banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6", fazenda_id=1))
        s.add(ContaCorrente(id=2, banco="Sicoob", agencia="3000", numero_conta="777-1", fazenda_id=2))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _cab(username: str = "admin1", fazenda_id: int = 1) -> dict:
    return {"Authorization": f"Bearer {criar_token(username, fazenda_id=fazenda_id)}"}


def _criar_vale(c, *, pessoa_id: int = 1, competencia: str = "2026-07",
                conta_id: int | None = 1, headers: dict | None = None) -> dict:
    resposta = c.post("/cadastro/vales", headers=headers or _cab(), json={
        "pessoa_id": pessoa_id, "valor_total": 900.0, "forma_pagamento": "pix",
        "data_pagamento": "2026-06-10", "parcelas": 3, "competencia_inicio": competencia,
        "conta_corrente_id": conta_id, "observacao": "mercado",
    })
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _criar_folha(c, *, pessoa_id: int = 1, competencia: str, headers: dict | None = None) -> dict:
    resposta = c.post("/cadastro/folha-pagamento", headers=headers or _cab(), json={
        "pessoa_id": pessoa_id, "competencia": competencia, "valor_bruto": 3000.0,
    })
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _acao(c, vale_id: int, corpo: dict, headers: dict | None = None):
    return c.post(f"/cadastro/vales/{vale_id}/acoes", headers=headers or _cab(), json=corpo)


def _linha_unificada(c, competencia: str, pessoa_id: int = 1, headers: dict | None = None) -> dict:
    resposta = c.get("/cadastro/folha-pagamento-unificada", headers=headers or _cab())
    assert resposta.status_code == 200, resposta.text
    return next(
        l for l in resposta.json()
        if l["tipo"] == "funcionario" and l["pessoa_id"] == pessoa_id and l["competencia"] == competencia
    )


class TestValeAssumidoNoLedgerUnificado:
    def test_o_mes_assumido_explica_se_no_ledger_de_contas(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        _acao(c, vale["id"], {
            "acao": "desconsiderar_mes", "competencia": "2026-07", "motivo": "trator",
        })

        linha = _linha_unificada(c, "2026-07")
        assumido = linha["vale_assumido"]
        assert len(assumido) == 1
        assert assumido[0]["valor_assumido"] == 300.0
        assert assumido[0]["motivo"] == "trator"
        assert assumido[0]["competencia"] == "2026-07"
        assert assumido[0]["origem"]["vale_id"] == vale["id"]
        # A numeração é a da sequência COMPLETA do vale — a assumida continua
        # sendo a 1ª de 3, como no painel da tela de fechamento.
        assert assumido[0]["referencia"].startswith("Parcela 1 de 3")
        # O desconto sumiu do recibo, como tem de sumir.
        assert [d for d in linha["detalhe"] if d["tipo"] == "vale"] == []

    def test_a_linha_assumida_nao_entra_em_soma_nenhuma(self, ambiente):
        """A prova de inércia, igual à do #722 na outra tela: fora de
        `detalhe`, líquido e totais intactos, e — cinto e suspensórios —
        somar `detalhe + vale_assumido` por engano daria exatamente os mesmos
        totais, porque a linha nasce com provento, desconto e valor zerados."""
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07"})

        linha = _linha_unificada(c, "2026-07")
        assert linha["valor"] == 3000.0, "o líquido do ledger é o bruto: nada foi descontado"
        assert linha["totais"]["total_descontos"] == 0.0
        assert linha["totais"]["liquido"] == 3000.0
        assert [d for d in linha["detalhe"] if d["tipo"] == "vale_assumido"] == []
        assert holerite.totais_holerite(linha["detalhe"] + linha["vale_assumido"]) == linha["totais"]
        for informativa in linha["vale_assumido"]:
            assert informativa["provento"] is None
            assert informativa["desconto"] is None
            assert informativa["valor"] == 0.0

    def test_vale_cancelado_tambem_explica_o_desconto_que_sumiu(self, ambiente):
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        _acao(c, vale["id"], {"acao": "cancelar", "motivo": "acerto de contas"})

        linha = _linha_unificada(c, "2026-07")
        assert [l["motivo"] for l in linha["vale_assumido"]] == ["acerto de contas"]
        assert linha["totais"]["total_descontos"] == 0.0

    def test_mes_sem_assuncao_nenhuma_vem_com_a_lista_vazia(self, ambiente):
        """Nunca ausente: a tela faz `vale_assumido.length` direto, e um campo
        que às vezes não existe quebraria a renderização do recibo inteiro."""
        c, engine = ambiente
        _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        linha = _linha_unificada(c, "2026-07")
        assert linha["vale_assumido"] == []
        assert linha["totais"]["total_descontos"] == 300.0, "o desconto normal continua descontando"

    def test_a_fazenda_vizinha_nao_ve_o_mes_assumido_do_vale_alheio(self, ambiente):
        """Isolamento com CONTRAPROVA: a linha existe para quem é da fazenda 1
        e o ledger da fazenda 2 não tem lançamento nenhum daquela pessoa — a
        ausência é do isolamento, não de o campo não existir."""
        c, engine = ambiente
        vale = _criar_vale(c)
        _criar_folha(c, competencia="2026-07")
        _acao(c, vale["id"], {"acao": "desconsiderar_mes", "competencia": "2026-07", "motivo": "trator"})

        vizinha = c.get("/cadastro/folha-pagamento-unificada", headers=_cab("admin2", 2))
        assert vizinha.status_code == 200, vizinha.text
        assert [l for l in vizinha.json() if l["pessoa_id"] == 1] == []
        assert all(not l.get("vale_assumido") for l in vizinha.json())

        # Contraprova, dentro da fazenda certa.
        assert _linha_unificada(c, "2026-07")["vale_assumido"][0]["motivo"] == "trator"
