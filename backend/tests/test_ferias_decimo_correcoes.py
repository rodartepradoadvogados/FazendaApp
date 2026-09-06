"""
Sete defeitos de dinheiro (e um de isolamento entre fazendas) do módulo de
Férias/13º/Rescisão, cada um com o teste que o trava. Todos falham no código
anterior à correção — a ordem aqui é a da gravidade:

1. 13º pago EM DOBRO — `calcular_decimo_terceiro` devolve o 13º cheio e era
   gravado igual para "unica", "primeira" e "segunda". Salário R$ 3.000,
   lançar 1ª + 2ª parcela = R$ 6.000 em Contas a Pagar.
2. `_remover_folha_pos_rescisao` apagava folha pendente de TODAS as fazendas
   quando `fazenda_id` chegava None (token legado), e rodava dentro de um GET.
3. "Marcar como pago" recalculava com o salário de HOJE e sobrescrevia a
   conta a pagar em silêncio — faltava snapshot.
4. 40 dias de férias sobre direito de 30 (`dias_gozados` e
   `abono_pecuniario_dias` validados em separado, nunca somados).
5. A conta a pagar das férias vencia no FIM do gozo; o art. 145 da CLT manda
   pagar até 2 dias ANTES do início.
6. `valor_abono` era calculado e jogado fora.
7. Férias/13º pendentes sobreviviam à rescisão → 13º pago duas vezes.

Fixture no mesmo padrão de test_rescisao_fluxo.py (sqlite em memória +
overrides), com `monkeypatch.setattr(database, "engine", engine)` porque
parte dos testes monta cenário multi-fazenda.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContaGerencial, ContratoFazenda, ContratoFazendaModulo, DecimoTerceiro, Fazenda, FeriasFuncionario,
    FolhaPagamento, Pessoa,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules.folha_rh import (
    calcular_decimo_terceiro, retencoes_permitidas_decimo_terceiro, valor_parcela_decimo_terceiro,
)


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
    """Troca a fazenda "do token" — é assim que o vazamento multi-tenant se
    reproduz sem forjar JWT."""
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


def _criar_pessoa(
    engine, nome: str = "Fulano", salario_base: float = 3000.0,
    data_admissao: date | None = date(2020, 1, 10), fazenda_id: int | None = None,
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


def _payload_ferias(pessoa_id: int, **overrides) -> dict:
    base = {
        "pessoa_id": pessoa_id,
        "periodo_aquisitivo_inicio": "2025-01-10",
        "periodo_aquisitivo_fim": "2026-01-10",
        "dias_direito": 30,
        "dias_gozados": 30,
        "data_inicio_gozo": "2026-07-01",
        "data_fim_gozo": "2026-07-30",
        "abono_pecuniario_dias": 0,
    }
    base.update(overrides)
    return base


def _conta(engine, numero: str) -> ContaGerencial | None:
    with Session(engine) as s:
        return s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero)).first()


# ===========================================================================
# 1. 13º pago em dobro
# ===========================================================================
class TestDecimoTerceiroEmDobro:
    def test_primeira_mais_segunda_parcela_nunca_somam_mais_que_o_decimo_devido(self, client):
        """O CENÁRIO DO BUG, na íntegra: salário R$ 3.000, 12 meses. Antes da
        correção este teste falhava com 6000.0 — a 1ª e a 2ª parcela geravam
        R$ 3.000 CADA em Contas a Pagar para um 13º de R$ 3.000."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)

        r1 = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "primeira", "meses_trabalhados": 12,
        })
        assert r1.status_code == 200, r1.text
        r2 = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "segunda", "meses_trabalhados": 12,
        })
        assert r2.status_code == 200, r2.text

        # 1ª = adiantamento de 50% (Lei 4.749/1965, art. 2º); 2ª = o saldo.
        assert r1.json()["valor_bruto"] == 1500.0
        assert r2.json()["valor_bruto"] == 1500.0
        assert r1.json()["valor_integral"] == 3000.0
        assert r2.json()["valor_integral"] == 3000.0

        # E o que importa de verdade: o total em Contas a Pagar.
        with Session(engine) as s:
            contas = s.exec(
                select(ContaGerencial).where(ContaGerencial.tipo_documento == "13º salário")
            ).all()
        assert round(sum(x.valor_total for x in contas), 2) == 3000.0

    def test_segunda_parcela_sozinha_paga_o_decimo_inteiro(self, client):
        """Sem adiantamento lançado, a 2ª parcela É o 13º inteiro — a
        correção não pode virar um desconto fixo de 50%."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "segunda", "meses_trabalhados": 12,
        })
        assert r.status_code == 200, r.text
        assert r.json()["valor_bruto"] == 3000.0

    def test_parcela_unica_depois_do_adiantamento_vira_saldo(self, client):
        """Ordem esquisita, mesmo teto: "única" lançada depois de uma 1ª
        parcela paga o que falta, nunca o 13º inteiro de novo."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "primeira", "meses_trabalhados": 12,
        })
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        })
        assert r.status_code == 200, r.text
        assert r.json()["valor_bruto"] == 1500.0

    def test_terceira_parcela_no_mesmo_ano_e_recusada(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        for parcela in ("primeira", "segunda"):
            assert c.post("/cadastro/decimo-terceiro", json={
                "pessoa_id": pessoa_id, "ano": 2026, "parcela": parcela, "meses_trabalhados": 12,
            }).status_code == 200
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "segunda", "meses_trabalhados": 12,
        })
        assert r.status_code == 400, r.text
        assert "já há" in r.json()["detail"]

    def test_ano_seguinte_nao_e_afetado_pelo_ano_anterior(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        })
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2027, "parcela": "unica", "meses_trabalhados": 12,
        })
        assert r.status_code == 200, r.text
        assert r.json()["valor_bruto"] == 3000.0

    def test_primeira_parcela_nao_aceita_inss_nem_irrf(self, client):
        """INSS/IRRF só na 2ª parcela (Lei 8.212/1991, art. 28, §7º) — a 1ª é
        adiantamento pago cheio."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "primeira",
            "meses_trabalhados": 12, "valor_inss": 120.0,
        })
        assert r.status_code == 400, r.text
        assert "adiantamento" in r.json()["detail"]

    def test_segunda_parcela_aceita_retencoes_sobre_o_saldo(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "primeira", "meses_trabalhados": 12,
        })
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "segunda",
            "meses_trabalhados": 12, "valor_inss": 270.0, "valor_ir": 100.0,
        })
        assert r.status_code == 200, r.text
        assert r.json()["valor_bruto"] == 1500.0
        assert r.json()["valor_liquido"] == 1130.0

    def test_funcao_pura_da_parcela(self):
        assert valor_parcela_decimo_terceiro(3000.0, "primeira") == 1500.0
        assert valor_parcela_decimo_terceiro(3000.0, "segunda", ja_lancado=1500.0) == 1500.0
        assert valor_parcela_decimo_terceiro(3000.0, "unica") == 3000.0
        # Nunca negativo, nunca acima do devido.
        assert valor_parcela_decimo_terceiro(3000.0, "segunda", ja_lancado=3000.0) == 0.0
        assert valor_parcela_decimo_terceiro(3000.0, "primeira", ja_lancado=1500.0) == 0.0
        assert calcular_decimo_terceiro(3000.0, 12) == 3000.0
        assert retencoes_permitidas_decimo_terceiro("primeira") is False
        assert retencoes_permitidas_decimo_terceiro("segunda") is True
        with pytest.raises(ValueError):
            valor_parcela_decimo_terceiro(3000.0, "terceira")


# ===========================================================================
# 2. Isolamento — a única rotina do módulo que APAGA
# ===========================================================================
class TestRemoverFolhaPosRescisaoIsolada:
    def test_rescisao_de_uma_fazenda_nao_apaga_folha_pendente_de_outra(self, client):
        """O furo: `_remover_folha_pos_rescisao` filtrava com o padrão
        tolerante `if fazenda_id is not None` e `_rescisao_fechada_antes_de`
        consultava as rescisões SEM filtro nenhum de fazenda. Aqui as duas
        pessoas têm o MESMO pessoa_id? não — mas a rotina varria a tabela
        inteira, então a folha pendente da fazenda 2 entrava no loop da
        fazenda 1. Antes da correção, a folha da fazenda 2 sumia."""
        c, engine = client
        with Session(engine) as s:
            s.add(Fazenda(id=1, nome="Fazenda 1"))
            s.add(Fazenda(id=2, nome="Fazenda 2"))
            for fid in (1, 2):
                s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
                for modulo in MODULOS_COMERCIAIS:
                    s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.commit()

        _como_fazenda(2)
        pessoa_vizinha = _criar_pessoa(engine, nome="Vizinha", fazenda_id=2)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_vizinha, "competencia": "2026-09", "valor_bruto": 3000.0,
        })
        assert r.status_code == 200, r.text
        numero_vizinha = r.json()["numero_lancamento_gerado"]

        # A fazenda 1 fecha a rescisão da SUA pessoa. Nada da fazenda 2 pode
        # ser tocado por isso.
        _como_fazenda(1)
        pessoa_local = _criar_pessoa(engine, nome="Local", fazenda_id=1)
        sim = c.post("/cadastro/rescisoes", json={
            "pessoa_id": pessoa_local, "tipo_rescisao": "pedido_demissao",
            "data_desligamento": "2026-08-05",
        })
        assert sim.status_code == 200, sim.text
        fechar = c.post(f"/cadastro/rescisoes/{sim.json()['id']}/fechar", json={"forma_lancamento": "unico"})
        assert fechar.status_code == 200, fechar.text

        with Session(engine) as s:
            sobreviveu = s.exec(
                select(FolhaPagamento).where(FolhaPagamento.pessoa_id == pessoa_vizinha)
            ).first()
            assert sobreviveu is not None, "a folha da fazenda vizinha foi apagada"
            assert s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_vizinha)
            ).first() is not None

    def test_listagem_de_folha_nao_apaga_nada(self, client):
        """Um GET não pode destruir dado. A folha pós-rescisão continua sendo
        removida — mas no POST de fechar a rescisão, não na leitura da tela.
        Aqui a rescisão é gravada DIRETO no banco (sem passar pelo endpoint
        de fechar), então a listagem é a única coisa que roda: antes ela
        apagava a folha; agora não."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-09", "valor_bruto": 3000.0,
        })
        assert r.status_code == 200, r.text

        with Session(engine) as s:
            from fazenda.models import RescisaoFuncionario
            s.add(RescisaoFuncionario(
                pessoa_id=pessoa_id, tipo_rescisao="pedido_demissao", data_desligamento=date(2026, 8, 5),
                salario_base=3000.0, data_admissao=date(2020, 1, 10), status="fechada", valor_total=1.0,
            ))
            s.commit()

        assert c.get("/cadastro/folha-pagamento").status_code == 200
        with Session(engine) as s:
            assert s.exec(
                select(FolhaPagamento).where(FolhaPagamento.pessoa_id == pessoa_id)
            ).first() is not None


# ===========================================================================
# 3. Snapshot do salário
# ===========================================================================
class TestSnapshotDoSalario:
    def test_marcar_ferias_como_pago_nao_recalcula_com_o_salario_novo(self, client):
        """CENÁRIO DO BUG: férias de 30 dias lançadas com salário R$ 2.000
        (R$ 2.666,60 com o percentual seedado de 0,3333). O salário sobe para
        R$ 3.000 no cadastro. "Marcar como pago" manda um PUT completo — que
        antes recalculava tudo pelo salário de hoje e virava R$ 4.000, sem
        aviso, inclusive na conta a pagar."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=2000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id))
        assert r.status_code == 200, r.text
        registro_id = r.json()["id"]
        valor_lancado = r.json()["valor_total"]
        numero = r.json()["numero_lancamento_gerado"]
        assert r.json()["salario_base"] == 2000.0

        with Session(engine) as s:
            p = s.get(Pessoa, pessoa_id)
            p.salario_base = 3000.0
            s.add(p)
            s.commit()

        r_put = c.put(f"/cadastro/ferias/{registro_id}", json=_payload_ferias(
            pessoa_id, status="pago", data_pagamento="2026-06-29",
        ))
        assert r_put.status_code == 200, r_put.text
        assert r_put.json()["valor_total"] == valor_lancado
        assert _conta(engine, numero).valor_total == valor_lancado

    def test_marcar_decimo_como_pago_nao_recalcula_com_o_salario_novo(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=2400.0)
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        })
        assert r.status_code == 200, r.text
        registro_id = r.json()["id"]
        numero = r.json()["numero_lancamento_gerado"]
        assert r.json()["valor_bruto"] == 2400.0
        assert r.json()["salario_base"] == 2400.0

        with Session(engine) as s:
            p = s.get(Pessoa, pessoa_id)
            p.salario_base = 5000.0
            s.add(p)
            s.commit()

        r_put = c.put(f"/cadastro/decimo-terceiro/{registro_id}", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
            "status": "pago", "data_pagamento": "2026-12-20",
        })
        assert r_put.status_code == 200, r_put.text
        assert r_put.json()["valor_bruto"] == 2400.0
        assert _conta(engine, numero).valor_total == 2400.0

    def test_registro_legado_sem_snapshot_ainda_recalcula_pelo_cadastro(self, client):
        """Compatibilidade: registro anterior à migração e0b7c3a91d24 cujo
        snapshot não pôde ser reconstituído continua caindo no salário atual —
        é o único caminho disponível, e é o comportamento antigo."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id))
        registro_id = r.json()["id"]
        with Session(engine) as s:
            reg = s.get(FeriasFuncionario, registro_id)
            reg.salario_base = None
            s.add(reg)
            s.commit()

        r_put = c.put(f"/cadastro/ferias/{registro_id}", json=_payload_ferias(pessoa_id, dias_gozados=15))
        assert r_put.status_code == 200, r_put.text
        assert r_put.json()["valor_ferias"] == 1500.0
        assert r_put.json()["salario_base"] == 3000.0


# ===========================================================================
# 4. Dias gozados + abono acima do direito
# ===========================================================================
class TestSomaDiasFerias:
    def test_trinta_gozados_mais_dez_vendidos_e_recusado(self, client):
        """30 + 10 passava nas duas validações separadas e pagava 40 dias de
        férias sobre um direito de 30 (R$ 5.333,33 em vez de R$ 4.000)."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(
            pessoa_id, dias_gozados=30, abono_pecuniario_dias=10,
        ))
        assert r.status_code == 400, r.text
        assert "40 dias" in r.json()["detail"]
        with Session(engine) as s:
            assert s.exec(select(FeriasFuncionario)).first() is None

    def test_vinte_gozados_mais_dez_vendidos_continua_valendo(self, client):
        """A combinação legítima (art. 143 CLT: os dias vendidos SAEM do
        período) não pode ter sido quebrada junto."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(
            pessoa_id, dias_gozados=20, abono_pecuniario_dias=10,
        ))
        assert r.status_code == 200, r.text

    def test_a_soma_tambem_vale_na_edicao(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id, dias_gozados=20))
        registro_id = r.json()["id"]
        r_put = c.put(f"/cadastro/ferias/{registro_id}", json=_payload_ferias(
            pessoa_id, dias_gozados=25, abono_pecuniario_dias=10,
        ))
        assert r_put.status_code == 400, r_put.text


# ===========================================================================
# 5. Vencimento das férias (art. 145 CLT)
# ===========================================================================
class TestVencimentoFerias:
    def test_conta_a_pagar_vence_dois_dias_antes_do_inicio_do_gozo(self, client):
        """Era `data_fim_gozo`: gozo de 01/07 a 30/07 gerava conta vencendo
        30/07 — um mês depois do prazo do art. 145 da CLT."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(
            pessoa_id, data_inicio_gozo="2026-07-01", data_fim_gozo="2026-07-30",
        ))
        assert r.status_code == 200, r.text
        conta = _conta(engine, r.json()["numero_lancamento_gerado"])
        assert conta.data_vencimento == date(2026, 6, 29)
        # A competência acompanha o início do gozo, não o fim — é no mês do
        # pagamento que a despesa acontece.
        assert conta.data_competencia == date(2026, 7, 1)

    def test_data_de_pagamento_informada_continua_mandando(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id, data_pagamento="2026-06-20"))
        conta = _conta(engine, r.json()["numero_lancamento_gerado"])
        assert conta.data_vencimento == date(2026, 6, 20)

    def test_edicao_tambem_corrige_o_vencimento(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(pessoa_id))
        numero = r.json()["numero_lancamento_gerado"]
        c.put(f"/cadastro/ferias/{r.json()['id']}", json=_payload_ferias(
            pessoa_id, data_inicio_gozo="2026-09-10", data_fim_gozo="2026-10-09",
        ))
        assert _conta(engine, numero).data_vencimento == date(2026, 9, 8)


# ===========================================================================
# 6. Abono pecuniário persistido
# ===========================================================================
class TestAbonoPersistido:
    def test_valor_abono_e_gravado_e_as_partes_fecham_com_o_total(self, client):
        """Com abono, `valor_ferias + valor_terco != valor_total` no banco e
        não havia coluna que explicasse a diferença."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(
            pessoa_id, dias_gozados=20, abono_pecuniario_dias=10,
        ))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["valor_abono"] > 0
        assert round(d["valor_ferias"] + d["valor_terco_constitucional"] + d["valor_abono"], 2) == d["valor_total"]

        with Session(engine) as s:
            reg = s.exec(select(FeriasFuncionario)).first()
            assert reg.valor_abono == d["valor_abono"]

    def test_abono_persistido_alimenta_a_linha_do_recibo(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(
            pessoa_id, dias_gozados=20, abono_pecuniario_dias=10,
        ))
        linha = next(
            l for l in c.get("/cadastro/folha-pagamento-unificada").json()
            if l["origem_subtipo"] == "ferias"
        )
        abono = next(x for x in linha["detalhe"] if x["tipo"] == "abono")
        assert abono["provento"] == r.json()["valor_abono"]

    def test_edicao_atualiza_o_abono_gravado(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(
            pessoa_id, dias_gozados=20, abono_pecuniario_dias=10,
        ))
        r_put = c.put(f"/cadastro/ferias/{r.json()['id']}", json=_payload_ferias(
            pessoa_id, dias_gozados=30, abono_pecuniario_dias=0,
        ))
        assert r_put.status_code == 200, r_put.text
        assert r_put.json()["valor_abono"] == 0.0


# ===========================================================================
# 7. Férias/13º pendentes sobrevivendo à rescisão
# ===========================================================================
class TestCancelamentoPelaRescisao:
    def _fechar(self, c, pessoa_id: int, data_desligamento: str = "2026-12-10") -> dict:
        sim = c.post("/cadastro/rescisoes", json={
            "pessoa_id": pessoa_id, "tipo_rescisao": "sem_justa_causa",
            "data_desligamento": data_desligamento,
        })
        assert sim.status_code == 200, sim.text
        r = c.post(f"/cadastro/rescisoes/{sim.json()['id']}/fechar", json={"forma_lancamento": "unico"})
        assert r.status_code == 200, r.text
        return r.json()

    def test_decimo_pendente_do_ano_do_desligamento_e_cancelado(self, client):
        """CENÁRIO DO BUG: 13º de 2026 lançado em novembro (conta a pagar de
        R$ 3.000 vencendo 20/12, pendente); pessoa desligada em 10/12 e
        rescisão fechada JÁ COM o 13º proporcional dentro. Antes ficavam DUAS
        contas a pagar do mesmo 13º e nada as relacionava."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0, data_admissao=date(2020, 1, 10))
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        })
        assert r.status_code == 200, r.text
        decimo_id, numero = r.json()["id"], r.json()["numero_lancamento_gerado"]

        fechada = self._fechar(c, pessoa_id)

        # A conta a pagar duplicada some…
        assert _conta(engine, numero) is None
        # …mas o registro NÃO é apagado: fica marcado e ligado à rescisão.
        with Session(engine) as s:
            reg = s.get(DecimoTerceiro, decimo_id)
            assert reg is not None
            assert reg.status == "cancelado_rescisao"
            assert reg.rescisao_id == fechada["id"]
        # E o fechamento diz o que encerrou junto, em vez de sumir calado.
        assert [x["tipo"] for x in fechada["lancamentos_cancelados"]] == ["decimo_terceiro"]

    def test_ferias_futuras_pendentes_sao_canceladas(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/ferias", json=_payload_ferias(
            pessoa_id, data_inicio_gozo="2027-01-05", data_fim_gozo="2027-02-03",
        ))
        assert r.status_code == 200, r.text
        numero = r.json()["numero_lancamento_gerado"]

        fechada = self._fechar(c, pessoa_id)
        assert _conta(engine, numero) is None
        with Session(engine) as s:
            assert s.get(FeriasFuncionario, r.json()["id"]).status == "cancelado_rescisao"
        assert [x["tipo"] for x in fechada["lancamentos_cancelados"]] == ["ferias"]

    def test_decimo_de_ano_anterior_e_ferias_ja_gozadas_nao_sao_tocados(self, client):
        """Limite do cancelamento: a rescisão paga o 13º proporcional DO ANO
        do desligamento e as férias vencidas/proporcionais como verba própria.
        Dívida velha (13º de 2025 em aberto) e férias já gozadas e não pagas
        continuam sendo dívida real."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        velho = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2025, "parcela": "unica", "meses_trabalhados": 12,
        })
        assert velho.status_code == 200, velho.text
        gozadas = c.post("/cadastro/ferias", json=_payload_ferias(
            pessoa_id, data_inicio_gozo="2026-03-01", data_fim_gozo="2026-03-30",
        ))
        assert gozadas.status_code == 200, gozadas.text

        fechada = self._fechar(c, pessoa_id)
        assert fechada["lancamentos_cancelados"] == []
        assert _conta(engine, velho.json()["numero_lancamento_gerado"]) is not None
        assert _conta(engine, gozadas.json()["numero_lancamento_gerado"]) is not None

    def test_lancamento_ja_pago_nunca_e_cancelado(self, client):
        """Se o dinheiro já saiu, cancelar seria reescrever histórico."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
            "status": "pago", "data_pagamento": "2026-11-30",
        })
        assert r.status_code == 200, r.text
        self._fechar(c, pessoa_id)
        with Session(engine) as s:
            assert s.get(DecimoTerceiro, r.json()["id"]).status == "pago"
        assert _conta(engine, r.json()["numero_lancamento_gerado"]) is not None

    def test_cancelado_nao_pode_ser_editado_e_aparece_como_cancelado_no_ledger(self, client):
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        })
        self._fechar(c, pessoa_id)

        r_put = c.put(f"/cadastro/decimo-terceiro/{r.json()['id']}", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
            "status": "pago", "data_pagamento": "2026-12-20",
        })
        assert r_put.status_code == 400, r_put.text

        linha = next(
            l for l in c.get("/cadastro/folha-pagamento-unificada").json()
            if l["origem_subtipo"] == "decimo_terceiro"
        )
        assert linha["status"] == "cancelado_rescisao"

    def test_cancelado_libera_o_teto_do_ano_para_um_relancamento(self, client):
        """Reversibilidade prática: cancelado não conta mais no teto do ano —
        senão desfazer/relançar ficaria travado para sempre."""
        c, engine = client
        pessoa_id = _criar_pessoa(engine, salario_base=3000.0)
        c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        })
        self._fechar(c, pessoa_id)
        r = c.post("/cadastro/decimo-terceiro", json={
            "pessoa_id": pessoa_id, "ano": 2026, "parcela": "unica", "meses_trabalhados": 12,
        })
        assert r.status_code == 200, r.text
        assert r.json()["valor_bruto"] == 3000.0
