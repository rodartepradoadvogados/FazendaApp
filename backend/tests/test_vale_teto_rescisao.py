"""
Três defeitos que deixavam dinheiro real escapar do módulo de RH, e o caso
concreto que os expôs.

O CASO (Jorbeson Nunes, pessoa 3, fazenda 1, medido em produção):
  - a rescisão dele foi fechada com "Vale em aberto = R$ 0,00" e a fazenda
    pagou o líquido cheio, R$ 13.369,15;
  - ele continuou com 7 parcelas de vale abertas, somando **R$ 6.485,00**, em
    competências que nunca vão existir — sem folha, não há o que descontar;
  - a folha dele de 2026-08 fechava com líquido NEGATIVO (−R$ 866,50): quase
    R$ 4.000 de vale numa competência só contra R$ 3.393,00 de bruto, quando o
    teto de 40% do salário seria R$ 1.357,20.
Ninguém foi avisado em momento nenhum.

O QUE ESTES TESTES TRAVAM:

1. **O teto de 40% vale nas CINCO portas.** Ele era conferido em duas
   (`criar_vale`, `atualizar_vale`) e ignorado nas outras três
   (`editar_parcela_vale`, reparcelar nas Ações do vale, reparcelar no ato do
   pagamento) — por elas dava para concentrar o saldo inteiro num mês, muito
   acima do teto, em silêncio absoluto. Continua sendo um aviso CONFIRMÁVEL:
   cada teste confere que barra sem `confirmar` e passa com ele.
2. **A rescisão enxerga e RESOLVE o vale.** Traz o saldo real (era digitado à
   mão e nascia em zero), baixa as parcelas do que foi descontado (senão o
   mesmo dinheiro é cobrado duas vezes) e RECUSA o fechamento enquanto sobrar
   saldo não endereçado — antes do fechamento, porque rescisão fechada não
   reabre.
3. **Os dois menores.** A reconciliação de vale recalculava o líquido com a
   fórmula copiada à mão e sem `valor_rubricas`, apagando em silêncio a
   bonificação do líquido e da conta a pagar; e excluir uma folha "pendente"
   apagava a ContaGerencial vinculada sem conferir se ela já tinha sido paga
   no Financeiro.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaCorrente, ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, FolhaPagamento,
    Pessoa, RescisaoFuncionario, ValeFuncionario, ValeParcela,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id, get_fazenda_id_escrita
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: fazenda_id


def _pessoa(
    engine, salario_base: float = 3000.0, fazenda_id: int | None = None,
    nome: str = "Jorbeson Nunes", data_admissao: date = date(2025, 1, 20),
) -> int:
    with Session(engine) as s:
        p = Pessoa(
            nome=nome, tipo="Funcionário", salario_base=salario_base,
            data_admissao=data_admissao, fazenda_id=fazenda_id,
        )
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


def _lancar_vale(c, pessoa_id: int, conta_id: int, **extra) -> dict:
    corpo = {
        "pessoa_id": pessoa_id, "valor_total": 900.0, "forma_pagamento": "pix",
        "data_pagamento": "2026-03-01", "parcelas": 3, "competencia_inicio": "2026-04",
        "conta_corrente_id": conta_id,
    }
    corpo.update(extra)
    r = c.post("/cadastro/vales", json=corpo)
    assert r.status_code == 200, r.text
    return r.json()


def _parcelas(engine, vale_id: int) -> list[ValeParcela]:
    with Session(engine) as s:
        return sorted(
            s.exec(select(ValeParcela).where(ValeParcela.vale_id == vale_id)).all(),
            key=lambda p: p.competencia,
        )


# ===========================================================================
# DEFEITO 1 — o teto de 40% do salário nas CINCO portas
#
# Salário 3.000 ⇒ limite de R$ 1.200,00 por competência. Cada teste concentra
# mais que isso num mês e confere as duas metades do contrato: 409 com
# `competencias_excedidas` sem confirmar, e sucesso com `confirmar`.
# ===========================================================================
LIMITE = 1200.0


def _assert_409_teto(r, competencia: str):
    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe["limite"] == LIMITE
    excedidas = {c["competencia"]: c for c in detalhe["competencias_excedidas"]}
    assert competencia in excedidas, detalhe
    assert excedidas[competencia]["total"] > LIMITE
    # A mensagem tem de dizer QUAL competência, QUANTO e qual é o limite — sem
    # os números o dono não sabe o que precisa mudar.
    assert competencia in detalhe["mensagem"]
    assert f"{LIMITE:.2f}" in detalhe["mensagem"]
    assert f"{excedidas[competencia]['total']:.2f}" in detalhe["mensagem"]


class TestTetoQuarentaPorCentoNasCincoPortas:
    def test_porta_1_criar_vale(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        corpo = {
            "pessoa_id": pessoa_id, "valor_total": 1500.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-03-01", "parcelas": 1, "competencia_inicio": "2026-04",
            "conta_corrente_id": conta_id,
        }
        _assert_409_teto(c.post("/cadastro/vales", json=corpo), "2026-04")
        r = c.post("/cadastro/vales", json={**corpo, "confirmar": True})
        assert r.status_code == 200, r.text

    def test_porta_2_atualizar_vale(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        vale = _lancar_vale(c, pessoa_id, conta_id)  # 3x de 300 — dentro do teto
        # Reescrever o vale inteiro como 1x de 1.500 concentra tudo em 2026-04.
        corpo = {
            "pessoa_id": pessoa_id, "valor_total": 1500.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-03-01", "parcelas": 1, "competencia_inicio": "2026-04",
            "conta_corrente_id": conta_id,
        }
        _assert_409_teto(c.put(f"/cadastro/vales/{vale['id']}", json=corpo), "2026-04")
        r = c.put(f"/cadastro/vales/{vale['id']}", json={**corpo, "confirmar": True})
        assert r.status_code == 200, r.text

    def test_porta_3_editar_parcela_do_vale(self, client):
        """A porta que era a mais fácil de usar: editar a parcela para o valor
        cheio e "conceder" empilhava tudo num mês, sem aviso nenhum."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        vale = _lancar_vale(c, pessoa_id, conta_id)
        primeira = _parcelas(engine, vale["id"])[0]
        assert primeira.competencia == "2026-04"

        corpo = {"valor": 1500.0, "acao": "conceder", "confirmar": True}
        r = c.put(f"/cadastro/vales/{vale['id']}/parcelas/{primeira.id}", json=corpo)
        _assert_409_teto(r, "2026-04")
        # Nada foi gravado na recusa — a parcela continua valendo o que valia.
        assert _parcelas(engine, vale["id"])[0].valor == 300.0

        r = c.put(
            f"/cadastro/vales/{vale['id']}/parcelas/{primeira.id}",
            json={**corpo, "confirmar_teto": True},
        )
        assert r.status_code == 200, r.text
        assert _parcelas(engine, vale["id"])[0].valor == 1500.0

    def test_porta_3_confirmar_divergencia_nao_confirma_o_teto(self, client):
        """`confirmar` (a divergência de valor) e `confirmar_teto` são avisos
        DIFERENTES: reusar um para o outro faria quem confirma a divergência
        confirmar junto, sem ver, o estouro do teto legal."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        vale = _lancar_vale(c, pessoa_id, conta_id)
        primeira = _parcelas(engine, vale["id"])[0]
        r = c.put(
            f"/cadastro/vales/{vale['id']}/parcelas/{primeira.id}",
            json={"valor": 1500.0, "acao": "conceder", "confirmar": True},
        )
        assert r.status_code == 409
        assert "competencias_excedidas" in r.json()["detail"]

    def test_porta_3_redistribuir_confere_o_cronograma_inteiro(self, client):
        """A conferência olha as parcelas REDISTRIBUÍDAS, não só a editada:
        baixar a primeira empurra valor para os meses seguintes, e é lá que o
        teto pode estourar."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        # 3.000 em 2x de 1.500 já nasce acima do teto (confirmado), e baixar a
        # 1ª para 100 joga 2.900 na 2ª.
        vale = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=3000.0, parcelas=2, confirmar=True,
        )
        primeira = _parcelas(engine, vale["id"])[0]
        r = c.put(
            f"/cadastro/vales/{vale['id']}/parcelas/{primeira.id}",
            json={"valor": 100.0, "acao": "redistribuir_igual", "confirmar": True},
        )
        _assert_409_teto(r, "2026-05")

    def test_porta_4_reparcelar_nas_acoes_do_vale(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        # 900 em 2026-04 (cabe sozinho no teto de 1.200) e um segundo vale de
        # 600 lá na frente, em 2026-09.
        _lancar_vale(c, pessoa_id, conta_id, valor_total=900.0, parcelas=1, competencia_inicio="2026-04")
        vale2 = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=600.0, parcelas=1, competencia_inicio="2026-09",
        )

        # Reparcelar o segundo para 2026-04 empilha 900 + 600 = 1.500 num mês.
        corpo = {"acao": "reparcelar", "parcelas": 1, "competencia_inicio": "2026-04"}
        r = c.post(f"/cadastro/vales/{vale2['id']}/acoes", json=corpo)
        _assert_409_teto(r, "2026-04")
        # Recusa ANTES de escrever: o vale 2 continua com a parcela em 2026-09.
        assert [p.competencia for p in _parcelas(engine, vale2["id"])] == ["2026-09"]

        r = c.post(f"/cadastro/vales/{vale2['id']}/acoes", json={**corpo, "confirmar": True})
        assert r.status_code == 200, r.text
        assert [p.competencia for p in _parcelas(engine, vale2["id"])] == ["2026-04"]

    def test_porta_5_reparcelar_no_ato_do_pagamento(self, client):
        """A diferença não descontada volta ao saldo e é reparcelada — em 1x no
        mês seguinte, que é onde ela se empilha com o que já havia lá."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        # Vale de 2.400 em 2x (1.200 cada) — no limite exato, sem estourar.
        vale = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=2400.0, parcelas=2, competencia_inicio="2026-04",
        )
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-04", "valor_bruto": 3000.0,
        })
        assert r.status_code == 200, r.text
        folha_id = r.json()["id"]
        parcela_abril = _parcelas(engine, vale["id"])[0]

        # Desconta só 200 dos 1.200 e manda os 1.000 restantes para 2026-05,
        # onde já existe uma parcela de 1.200 ⇒ 2.200, acima do teto.
        corpo = {
            "data_pagamento": "2026-05-05",
            "verbas": [{"parcela_id": parcela_abril.id, "valor_pago": 200.0}],
            "decisao": {"tipo": "reparcelar", "parcelas": 1, "competencia_inicio": "2026-05"},
        }
        r = c.post(f"/cadastro/folha-pagamento/{folha_id}/pagar", json=corpo)
        _assert_409_teto(r, "2026-05")
        # Nada foi pago nem gravado.
        with Session(engine) as s:
            assert s.get(FolhaPagamento, folha_id).status == "pendente"
        assert sorted(p.valor for p in _parcelas(engine, vale["id"])) == [1200.0, 1200.0]

        corpo["decisao"]["confirmar"] = True
        r = c.post(f"/cadastro/folha-pagamento/{folha_id}/pagar", json=corpo)
        assert r.status_code == 200, r.text
        assert [p.valor for p in _parcelas(engine, vale["id"]) if p.competencia == "2026-05"] == [2200.0]

    def test_pessoa_sem_salario_base_nao_trava_as_portas_de_edicao(self, client):
        """Sem salário não há teto calculável. As portas de CRIAÇÃO já exigem o
        cadastro (400 próprio); as de edição seguem funcionando — recusar ali
        impediria o dono de consertar justamente o vale que ele quer ajustar."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        vale = _lancar_vale(c, pessoa_id, conta_id)
        with Session(engine) as s:
            p = s.get(Pessoa, pessoa_id)
            p.salario_base = None
            s.add(p)
            s.commit()
        primeira = _parcelas(engine, vale["id"])[0]
        r = c.put(
            f"/cadastro/vales/{vale['id']}/parcelas/{primeira.id}",
            json={"valor": 5000.0, "acao": "conceder", "confirmar": True},
        )
        assert r.status_code == 200, r.text

    def test_parcela_assumida_pela_fazenda_nao_ocupa_o_teto(self, client):
        """Mês desconsiderado não é desconto de ninguém — mesma regra de
        `_valor_vale`, e por isso não come o teto do funcionário."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        vale = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=1000.0, parcelas=1, competencia_inicio="2026-04",
        )
        r = c.post(f"/cadastro/vales/{vale['id']}/acoes", json={
            "acao": "desconsiderar_mes", "competencia": "2026-04", "motivo": "acerto",
        })
        assert r.status_code == 200, r.text
        # Os 1.000 assumidos saíram da conta: 1.100 novos ainda cabem em 1.200.
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 1100.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-03-01", "parcelas": 1, "competencia_inicio": "2026-04",
            "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200, r.text

    def test_teto_soma_todos_os_vales_da_competencia_nao_so_o_que_esta_sendo_mexido(self, client):
        """O teto é do FUNCIONÁRIO, não do documento: dois vales de R$ 700 no
        mesmo mês somam 1.400 e estouram, mesmo cada um cabendo sozinho."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        _lancar_vale(c, pessoa_id, conta_id, valor_total=700.0, parcelas=1, competencia_inicio="2026-04")
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 700.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-03-01", "parcelas": 1, "competencia_inicio": "2026-04",
            "conta_corrente_id": conta_id,
        })
        _assert_409_teto(r, "2026-04")
        assert r.json()["detail"]["competencias_excedidas"][0]["total"] == 1400.0


# ===========================================================================
# DEFEITO 2 — a rescisão ignorava o vale (foram R$ 6.485,00 não recuperados)
# ===========================================================================
def _payload_simulacao(pessoa_id: int, **extra) -> dict:
    base = {
        "pessoa_id": pessoa_id,
        "tipo_rescisao": "sem_justa_causa",
        "data_desligamento": "2026-07-20",
        "dias_ferias_vencidas": 0,
        "aviso_previo_trabalhado": False,
    }
    base.update(extra)
    return base


class TestRescisaoEnxergaEResolveOVale:
    def test_calculo_da_rescisao_traz_o_saldo_real_com_as_competencias(self, client):
        """O número que a tela não tinha: "Vale em aberto" era digitado à mão e
        nascia em zero. Agora o servidor devolve o saldo cobrável e as
        competências, para o campo nascer preenchido."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        _lancar_vale(
            c, pessoa_id, conta_id, valor_total=900.0, parcelas=3, competencia_inicio="2026-08",
        )
        r = c.post("/cadastro/rescisao/calcular", json=_payload_simulacao(pessoa_id))
        assert r.status_code == 200, r.text
        saldo = r.json()["vale_em_aberto"]
        assert saldo["total"] == 900.0
        assert [x["competencia"] for x in saldo["competencias"]] == ["2026-08", "2026-09", "2026-10"]
        assert [x["valor"] for x in saldo["competencias"]] == [300.0, 300.0, 300.0]

    def test_saldo_ignora_parcela_assumida_vale_cancelado_e_competencia_paga(self, client):
        """Cobrável é a mesma definição da folha: o que a fazenda assumiu, o
        vale cancelado e o mês já descontado num holerite pago não são dívida
        de ninguém — cobrá-los na rescisão cobraria duas vezes."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)

        # (a) vale cancelado — o saldo dele já virou despesa da fazenda.
        cancelado = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=500.0, parcelas=1, competencia_inicio="2026-08",
        )
        assert c.post(
            f"/cadastro/vales/{cancelado['id']}/acoes", json={"acao": "cancelar", "motivo": "acerto"},
        ).status_code == 200

        # (b) mês desconsiderado de um vale vivo.
        vivo = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=600.0, parcelas=2, competencia_inicio="2026-09",
        )
        assert c.post(f"/cadastro/vales/{vivo['id']}/acoes", json={
            "acao": "desconsiderar_mes", "competencia": "2026-09", "motivo": "acerto",
        }).status_code == 200

        # (c) competência com folha PAGA — o desconto já aconteceu.
        _lancar_vale(c, pessoa_id, conta_id, valor_total=400.0, parcelas=1, competencia_inicio="2026-06")
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-06", "valor_bruto": 3000.0,
        })
        assert r.status_code == 200, r.text
        folha_id = r.json()["id"]
        assert c.post(
            f"/cadastro/folha-pagamento/{folha_id}/pagar", json={"data_pagamento": "2026-07-05"},
        ).status_code == 200

        r = c.post("/cadastro/rescisao/calcular", json=_payload_simulacao(pessoa_id))
        saldo = r.json()["vale_em_aberto"]
        # Sobra só a 2ª parcela do vale vivo (2026-10).
        assert saldo["total"] == 300.0
        assert [x["competencia"] for x in saldo["competencias"]] == ["2026-10"]

    def test_fechar_recusa_enquanto_sobrar_vale_nao_enderecado(self, client):
        """O CASO DO JORBESON, na íntegra: rescisão fechada com "Vale em aberto
        = R$ 0,00" e R$ 6.485,00 de parcelas de pé, em competências que nunca
        vão existir. Agora o fechamento recusa — ANTES de fechar, porque
        rescisão fechada não reabre."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        _lancar_vale(
            c, pessoa_id, conta_id, valor_total=6485.0, parcelas=7, competencia_inicio="2026-08",
            confirmar=True,
        )
        r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
        assert r.status_code == 200, r.text
        registro = r.json()
        assert registro["valor_vale_em_aberto"] == 0.0
        assert registro["vale_em_aberto"]["total"] == 6485.0

        r = c.post(f"/cadastro/rescisoes/{registro['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 400, r.text
        detalhe = r.json()["detail"]
        assert "6485.00" in detalhe
        assert "2026-08" in detalhe  # diz em que competências o saldo está
        # Nada foi fechado: a rescisão continua editável.
        with Session(engine) as s:
            assert s.get(RescisaoFuncionario, registro["id"]).status == "simulacao"
        assert not c.get("/financeiro/lancamentos").json()["lancamentos"] or all(
            l["tipo_documento"] != "Rescisão" for l in c.get("/financeiro/lancamentos").json()["lancamentos"]
        )

    def test_fechar_descontando_o_saldo_baixa_as_parcelas(self, client):
        """A outra metade: descontar sem baixar cobraria o mesmo dinheiro duas
        vezes — uma no líquido reduzido, outra nas parcelas que continuariam
        de pé no relatório de vales."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        vale = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=900.0, parcelas=3, competencia_inicio="2026-08",
        )
        r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id, valor_vale_em_aberto=900.0))
        assert r.status_code == 200, r.text
        registro = r.json()

        r = c.post(f"/cadastro/rescisoes/{registro['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["status"] == "fechada"
        assert corpo["vales_baixados"] == [{"vale_id": vale["id"], "valor_abatido": 900.0, "saldo_apos": 0.0}]

        # As parcelas foram baixadas: nenhuma sobra cobrável.
        assert _parcelas(engine, vale["id"]) == []
        with Session(engine) as s:
            assert round(s.get(ValeFuncionario, vale["id"]).valor_abatido, 2) == 900.0

        # E o líquido pago já vinha reduzido dos 900 — o dinheiro é recuperado
        # uma vez só, sem lançamento novo de "devolução" no Financeiro.
        assert corpo["valor_total"] == round(corpo["valor_bruto"] - 900.0, 2)
        with Session(engine) as s:
            conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == corpo["numero_lancamento_gerado"]
            )).first()
            assert conta.valor_total == corpo["valor_total"]
            assert not s.exec(select(ContaGerencial).where(
                ContaGerencial.descricao.like("Devolução de vale%")
            )).all()

    def test_fechar_com_desconto_parcial_baixa_so_o_descontado_e_recusa_a_sobra(self, client):
        """Descontar parte é legítimo (o dono pode ter acertado o resto por
        fora) — mas o resto precisa estar RESOLVIDO, não esquecido."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        vale = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=900.0, parcelas=3, competencia_inicio="2026-08",
        )
        r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id, valor_vale_em_aberto=600.0))
        registro = r.json()
        r = c.post(f"/cadastro/rescisoes/{registro['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 400, r.text
        assert "300.00" in r.json()["detail"]

        # Resolvida a sobra pelas Ações do vale (a fazenda assume os 300 do
        # último mês), o fechamento passa e baixa exatamente os 600.
        assert c.post(f"/cadastro/vales/{vale['id']}/acoes", json={
            "acao": "desconsiderar_mes", "competencia": "2026-10", "motivo": "acerto na saída",
        }).status_code == 200
        r = c.post(f"/cadastro/rescisoes/{registro['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 200, r.text
        assert r.json()["vales_baixados"][0]["valor_abatido"] == 600.0
        restantes = _parcelas(engine, vale["id"])
        # Só a parcela assumida pela fazenda sobra — ela existe para o histórico.
        assert [(p.competencia, p.assumida_pela_fazenda) for p in restantes] == [("2026-10", True)]

    def test_fechar_recusa_desconto_maior_que_o_saldo_cobravel(self, client):
        """Descontar mais do que se tem a receber cobraria duas vezes o mesmo
        dinheiro — é o risco que existe quando o dono já acertou parte do vale
        por outra porta e digita o valor cheio aqui."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        _lancar_vale(
            c, pessoa_id, conta_id, valor_total=900.0, parcelas=3, competencia_inicio="2026-08",
        )
        r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id, valor_vale_em_aberto=1500.0))
        registro = r.json()
        r = c.post(f"/cadastro/rescisoes/{registro['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 400, r.text
        assert "1500.00" in r.json()["detail"] and "900.00" in r.json()["detail"]

    def test_baixa_reparte_entre_varios_vales_do_mais_antigo_para_o_mais_novo(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        antigo = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=500.0, parcelas=1, competencia_inicio="2026-08",
        )
        novo = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=500.0, parcelas=1, competencia_inicio="2026-09",
        )
        r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id, valor_vale_em_aberto=1000.0))
        r = c.post(f"/cadastro/rescisoes/{r.json()['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 200, r.text
        baixados = {b["vale_id"]: b["valor_abatido"] for b in r.json()["vales_baixados"]}
        assert baixados == {antigo["id"]: 500.0, novo["id"]: 500.0}
        # A ordem é do mais antigo para o mais novo (a sobra fica no recente).
        assert [b["vale_id"] for b in r.json()["vales_baixados"]] == [antigo["id"], novo["id"]]

    def test_rescisao_sem_vale_nenhum_fecha_como_sempre(self, client):
        """Contraprova de que a trava não muda o caminho de quem não tem vale —
        que é a maioria das rescisões."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_id))
        assert r.json()["vale_em_aberto"]["total"] == 0.0
        r = c.post(f"/cadastro/rescisoes/{r.json()['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 200, r.text
        assert r.json()["vales_baixados"] == []

    def test_isolamento_multi_fazenda_com_contraprova(self, client):
        """A rescisão de uma fazenda não enxerga (nem baixa) o vale da pessoa
        homônima da outra — e a contraprova: o mesmo pedido, na fazenda dona,
        enxerga o vale."""
        c, engine = client
        with Session(engine) as s:
            s.add(Fazenda(id=1, nome="Fazenda Alvo"))
            s.add(Fazenda(id=2, nome="Fazenda Atacante"))
            for fid in (1, 2):
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                for modulo in MODULOS_COMERCIAIS:
                    s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.commit()
        # Homônimos de propósito: colisão de texto entre tenants é o caso
        # normal, não o excepcional.
        pessoa_1 = _pessoa(engine, fazenda_id=1, nome="Jorbeson Nunes")
        pessoa_2 = _pessoa(engine, fazenda_id=2, nome="Jorbeson Nunes")
        conta_1 = _conta_corrente(engine, fazenda_id=1)
        conta_2 = _conta_corrente(engine, fazenda_id=2)

        _como_fazenda(1)
        vale_1 = _lancar_vale(
            c, pessoa_1, conta_1, valor_total=900.0, parcelas=3, competencia_inicio="2026-08",
        )
        _como_fazenda(2)
        vale_2 = _lancar_vale(
            c, pessoa_2, conta_2, valor_total=400.0, parcelas=1, competencia_inicio="2026-08",
        )

        # Fazenda 2 fecha a rescisão da SUA pessoa: só o vale dela entra.
        r = c.post("/cadastro/rescisao/calcular", json=_payload_simulacao(pessoa_2))
        assert r.json()["vale_em_aberto"]["total"] == 400.0
        r = c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_2, valor_vale_em_aberto=400.0))
        r = c.post(f"/cadastro/rescisoes/{r.json()['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 200, r.text
        assert [b["vale_id"] for b in r.json()["vales_baixados"]] == [vale_2["id"]]

        # O vale da fazenda 1 ficou intacto — nada foi baixado do outro tenant.
        assert [p.valor for p in _parcelas(engine, vale_1["id"])] == [300.0, 300.0, 300.0]

        # E a pessoa da fazenda 1 é INVISÍVEL para a fazenda 2: 404, nunca 403
        # (403 confirmaria que o id existe em algum lugar).
        assert c.post("/cadastro/rescisao/calcular", json=_payload_simulacao(pessoa_1)).status_code == 404
        assert c.post("/cadastro/rescisoes", json=_payload_simulacao(pessoa_1)).status_code == 404

        # CONTRAPROVA: na fazenda dona, o mesmo pedido enxerga o vale.
        _como_fazenda(1)
        r = c.post("/cadastro/rescisao/calcular", json=_payload_simulacao(pessoa_1))
        assert r.status_code == 200, r.text
        assert r.json()["vale_em_aberto"]["total"] == 900.0


# ===========================================================================
# DEFEITO 3 — os dois menores
# ===========================================================================
class TestReconciliacaoPreservaAsRubricas:
    def test_lancar_vale_nao_apaga_a_bonificacao_do_liquido_nem_da_conta(self, client):
        """FICA VERMELHO COM A FÓRMULA ANTIGA. `_reconciliar_vale_competencias`
        recalculava o líquido com a conta copiada à mão e SEM `valor_rubricas`
        — e toda ação de vale passa por ali. Uma bonificação lançada no
        holerite era apagada do líquido e da conta a pagar, em silêncio: o
        recibo mostrava a linha e o banco pagava sem ela."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-04", "valor_bruto": 3000.0,
        })
        assert r.status_code == 200, r.text
        folha_id = r.json()["id"]

        r = c.post(f"/cadastro/folha-pagamento/{folha_id}/rubricas", json={
            "especie": "vencimento", "codigo": "bonificacao_produtividade", "valor": 500.0,
        })
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            folha = s.get(FolhaPagamento, folha_id)
            assert folha.valor_rubricas == 500.0
            assert folha.valor_liquido == 3500.0

        # Um vale de 200 na mesma competência: o líquido tem de cair só o vale.
        _lancar_vale(
            c, pessoa_id, conta_id, valor_total=200.0, parcelas=1, competencia_inicio="2026-04",
        )
        with Session(engine) as s:
            folha = s.get(FolhaPagamento, folha_id)
            # Com a fórmula antiga (sem valor_rubricas) daria 2.800.
            assert folha.valor_liquido == 3300.0, "a bonificação foi apagada do líquido"
            conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == folha.numero_lancamento_gerado
            )).first()
            assert conta.valor_total == 3300.0, "a bonificação foi apagada da conta a pagar"

    def test_excluir_o_vale_devolve_o_liquido_com_a_rubrica(self, client):
        """A volta pelo mesmo caminho: excluir o vale reconcilia de novo e o
        líquido tem de voltar a 3.500, não a 3.000."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        conta_id = _conta_corrente(engine)
        folha_id = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-04", "valor_bruto": 3000.0,
        }).json()["id"]
        c.post(f"/cadastro/folha-pagamento/{folha_id}/rubricas", json={
            "especie": "vencimento", "codigo": "bonificacao_produtividade", "valor": 500.0,
        })
        vale = _lancar_vale(
            c, pessoa_id, conta_id, valor_total=200.0, parcelas=1, competencia_inicio="2026-04",
        )
        assert c.delete(f"/cadastro/vales/{vale['id']}").status_code == 200
        with Session(engine) as s:
            assert s.get(FolhaPagamento, folha_id).valor_liquido == 3500.0


class TestExcluirFolhaComContaJaPaga:
    def test_recusa_quando_a_conta_a_pagar_ja_foi_baixada_no_financeiro(self, client):
        """A folha segue "pendente" no RH e alguém dá baixa no lançamento
        direto no Financeiro (fluxo normal). Excluir a folha apagava a
        ContaGerencial sem olhar `valor_pago` — e com ela sumia do extrato um
        pagamento que ACONTECEU. Mesma regra de `excluir_guia_folha_encargo`."""
        c, engine = client
        pessoa_id = _pessoa(engine)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-04", "valor_bruto": 3000.0,
        })
        folha_id = r.json()["id"]
        with Session(engine) as s:
            folha = s.get(FolhaPagamento, folha_id)
            conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == folha.numero_lancamento_gerado
            )).first()
            conta.data_pagamento = date(2026, 5, 5)
            conta.valor_pago = conta.valor_total
            s.add(conta)
            s.commit()
            conta_id = conta.id

        r = c.delete(f"/cadastro/folha-pagamento/{folha_id}")
        assert r.status_code == 400, r.text
        assert "já foi baixada" in r.json()["detail"]
        # E o pagamento continua no extrato, junto com a folha.
        with Session(engine) as s:
            assert s.get(ContaGerencial, conta_id) is not None
            assert s.get(FolhaPagamento, folha_id) is not None

    def test_contraprova_conta_nao_paga_continua_sendo_excluida_junto(self, client):
        c, engine = client
        pessoa_id = _pessoa(engine)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-04", "valor_bruto": 3000.0,
        })
        folha_id = r.json()["id"]
        numero = r.json()["numero_lancamento_gerado"]
        assert c.delete(f"/cadastro/folha-pagamento/{folha_id}").status_code == 200
        with Session(engine) as s:
            assert s.get(FolhaPagamento, folha_id) is None
            assert s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)
            ).first() is None
