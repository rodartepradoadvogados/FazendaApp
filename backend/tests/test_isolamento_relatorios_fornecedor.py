"""
Reprodução + verificação de 3 vazamentos entre fazendas encontrados na
auditoria gauntlet, todos da MESMA classe já documentada em
test_isolamento_rotas_criticas.py (B1-B6): a rota nunca compara
`registro.fazenda_id` com a fazenda autenticada — em dois casos nem declarava
`fazenda_id` como dependência.

  G1 — GET /relatorio-rastreabilidade-sanitaria/   (leitura, sem filtro nenhum)
  G2 — GET /financeiro/custo-hectare               (leitura, sem filtro nenhum)
  G3 — PUT /cadastro/fornecedores/{id}             (ESCRITA, IDOR)

G1 é o mais grave: expunha o dossiê sanitário completo (GTAs, comprador/
vendedor, resultado de exame de tuberculose/brucelose, doença, causa de morte)
de TODAS as fazendas para qualquer usuário autenticado cuja fazenda tivesse o
módulo sanitário contratado.

Mesmo fixture/convenção de test_isolamento_rotas_criticas.py.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import (
    Animal, CalendarioSanitario, CompraAnimal, ContaGerencial, ContratoFazenda, ContratoFazendaModulo,
    CronogramaSanitario, CronogramaSanitarioAnimal, EntregaLeiteMensal, EstoqueSemen, EventoSanitario, Fazenda,
    Fornecedor, Sanidade,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(Fazenda(id=2, nome="Fazenda Vizinha"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))

        # --- Fazenda 1: o dado que NÃO pode vazar para a fazenda 2 ---
        s.add(Sanidade(
            fazenda_id=1, numero_matriz="F1-VACA", produto="Vacina sigilosa F1",
            data_aplicacao=date(2026, 7, 10), atividade="Vacinação", responsavel="Vet F1",
        ))
        s.add(CompraAnimal(
            fazenda_id=1, numero_animal="F1-VACA", vendedor="Fornecedor secreto F1",
            valor=5000.0, tipo_valor="por_animal", data_compra=date(2026, 7, 1), gta="GTA-F1-0001",
        ))
        s.add(ContaGerencial(
            numero_lancamento="LC-F1", codigo_conta="3.01.01.01", descricao="Despesa F1",
            fornecedor_cliente="Fornecedor F1", tipo="despesa", origem="manual",
            valor_total=100000.0, data_competencia=date(2026, 7, 5), fazenda_id=1,
        ))
        s.add(Fornecedor(id=1, fazenda_id=1, nome="Fornecedor original da F1", tipo="fornecedor"))
        s.add(EntregaLeiteMensal(fazenda_id=1, competencia="2026-07", quantidade_litros=90000.0))
        s.add(Animal(numero="F1-VACA", fazenda_id=1, ativo=True))
        s.add(EstoqueSemen(
            fazenda_id=1, touro_nome="TOURO SIGILOSO F1", naab="7HO-F1",
            doses=42, tipo="convencional", ativo=True,
        ))
        # Cronograma sanitário da fazenda 1 — alvo do IDOR de escrita.
        s.add(EventoSanitario(id=1, fazenda_id=1, nome="Vacina F1"))
        s.add(CalendarioSanitario(
            id=1, fazenda_id=1, evento_sanitario_id=1, categoria_alvo="Vaca",
            frequencia_valor=12, frequencia_unidade="meses", data_evento=date(2026, 7, 20),
        ))
        s.add(CronogramaSanitario(
            id=1, fazenda_id=1, calendario_sanitario_id=1,
            data_evento=date(2026, 7, 20), status="agendado",
        ))
        s.add(CronogramaSanitarioAnimal(
            id=1, fazenda_id=1, cronograma_id=1, numero_matriz="F1-VACA",
            status="incluido", data_sugestao=date(2026, 7, 1),
        ))

        # --- Fazenda 2: o dado legítimo de quem está consultando ---
        s.add(Sanidade(
            fazenda_id=2, numero_matriz="F2-VACA", produto="Vacina propria F2",
            data_aplicacao=date(2026, 7, 11), atividade="Vacinação", responsavel="Vet F2",
        ))
        s.add(ContaGerencial(
            numero_lancamento="LC-F2", codigo_conta="3.01.01.01", descricao="Despesa F2",
            fornecedor_cliente="Fornecedor F2", tipo="despesa", origem="manual",
            valor_total=7.0, data_competencia=date(2026, 7, 5), fazenda_id=2,
        ))
        s.add(EntregaLeiteMensal(fazenda_id=2, competencia="2026-07", quantidade_litros=1000.0))
        s.add(Animal(numero="F2-VACA", fazenda_id=2, ativo=True))
        s.add(EstoqueSemen(
            fazenda_id=2, touro_nome="Touro proprio F2", naab="7HO-F2",
            doses=5, tipo="convencional", ativo=True,
        ))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user

    monkeypatch.setattr(main, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "outroadmin@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()

    with TestClient(main.app) as c:
        yield c, engine

    main.app.dependency_overrides.clear()


def _como_fazenda(fazenda_id: int | None):
    import main
    from fazenda.auth import get_fazenda_atual_id
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: fazenda_id


class TestG1RastreabilidadeSanitaria:
    def test_fazenda_2_nao_ve_historico_sanitario_da_fazenda_1(self, client):
        c, _ = client
        _como_fazenda(2)
        r = c.get("/relatorio-rastreabilidade-sanitaria/")
        assert r.status_code == 200, r.text
        linhas = r.json()
        assert all(l["numero_animal"] != "F1-VACA" for l in linhas), "vazou animal da fazenda 1"
        assert all(l.get("produto") != "Vacina sigilosa F1" for l in linhas), "vazou aplicação da fazenda 1"
        assert all(l.get("gta") != "GTA-F1-0001" for l in linhas), "vazou GTA da fazenda 1"
        assert all(l.get("contraparte") != "Fornecedor secreto F1" for l in linhas), "vazou contraparte da fazenda 1"

    def test_fazenda_2_continua_vendo_o_proprio_historico(self, client):
        c, _ = client
        _como_fazenda(2)
        linhas = c.get("/relatorio-rastreabilidade-sanitaria/").json()
        assert any(l["numero_animal"] == "F2-VACA" for l in linhas), "correção cegou a própria fazenda"

    def test_filtrar_por_numero_de_animal_de_outra_fazenda_nao_vaza(self, client):
        # Mesmo sabendo o número exato do animal alheio, não pode voltar nada.
        c, _ = client
        _como_fazenda(2)
        linhas = c.get("/relatorio-rastreabilidade-sanitaria/", params={"numero": "F1-VACA"}).json()
        assert linhas == []

    def test_filtrar_por_gta_de_outra_fazenda_nao_vaza(self, client):
        c, _ = client
        _como_fazenda(2)
        linhas = c.get("/relatorio-rastreabilidade-sanitaria/", params={"gta": "GTA-F1-0001"}).json()
        assert linhas == []


class TestG2CustoHectare:
    def test_despesa_da_fazenda_1_nao_entra_no_custo_da_fazenda_2(self, client):
        c, _ = client
        _como_fazenda(2)
        r = c.get("/financeiro/custo-hectare", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"})
        assert r.status_code == 200, r.text
        # Só a despesa da própria fazenda (7,00) — não os 100.000,00 da fazenda 1.
        assert r.json()["despesas_total"] == 7.0


class TestG4CustoLitroLeite:
    def test_litros_entregues_pela_fazenda_1_nao_diluem_o_custo_da_fazenda_2(self, client):
        # O custo já era filtrado por fazenda; os litros não eram. O custo por
        # litro da fazenda 2 saía dividido por 91.000 L (1.000 dela + 90.000 da
        # fazenda 1), ou seja, ~91x menor que o real.
        c, _ = client
        _como_fazenda(2)
        r = c.get("/financeiro/custo-litro-leite", params={"data_inicio": "2026-07-01", "data_fim": "2026-07-31"})
        assert r.status_code == 200, r.text
        assert r.json()["litros"] == 1000.0


class TestG5AcasalamentoVazaEstoqueDeSemen:
    def test_sugestao_da_propria_vaca_nao_lista_semen_de_outra_fazenda(self, client):
        # O pior caso: nem precisa saber nada da outra fazenda. Consultar a
        # sugestão de uma vaca PRÓPRIA já devolvia o estoque de sêmen alheio.
        c, _ = client
        _como_fazenda(2)
        r = c.get("/reproducao/acasalamento/sugestao", params={"numero_matriz": "F2-VACA"})
        assert r.status_code == 200, r.text
        nomes = {(s.get("nome") or "") for s in r.json()["sugestoes"]}
        assert "TOURO SIGILOSO F1" not in nomes, "vazou estoque de sêmen da fazenda 1"

    def test_consultar_animal_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(2)
        r = c.get("/reproducao/acasalamento/sugestao", params={"numero_matriz": "F1-VACA"})
        assert r.status_code == 404


class TestG6CronogramaSanitarioIDOR:
    def test_decidir_modo_de_cronograma_de_outra_fazenda_devolve_404(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.post("/agenda/realizados", json={
            "evento_id": "cronograma_sanitario_modo_1", "modo": "propria",
        })
        assert r.status_code == 404
        with Session(engine) as s:
            assert s.get(CronogramaSanitario, 1).modo_execucao is None, "modo do cronograma alheio foi alterado"

    def test_aplicar_cronograma_de_outra_fazenda_devolve_404(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.post("/agenda/realizados", json={
            "evento_id": "cronograma_sanitario_aplicar_1", "responsavel": "atacante",
        })
        assert r.status_code == 404
        with Session(engine) as s:
            assert s.get(CronogramaSanitario, 1).status == "agendado", "cronograma alheio foi concluído"

    def test_incluir_animal_em_cronograma_de_outra_fazenda_devolve_404(self, client):
        c, _ = client
        _como_fazenda(2)
        r = c.post("/agenda/realizados", json={
            "evento_id": "cronograma_sanitario_animal_1", "incluir": True,
        })
        assert r.status_code == 404


class TestG3FornecedorIDOR:
    def test_editar_fornecedor_de_outra_fazenda_devolve_404(self, client):
        c, engine = client
        _como_fazenda(2)
        r = c.put("/cadastro/fornecedores/1", json={"nome": "INVADIDO", "tipo": "fornecedor"})
        assert r.status_code == 404

        # E o dado da fazenda 1 continua intacto no banco.
        with Session(engine) as s:
            assert s.get(Fornecedor, 1).nome == "Fornecedor original da F1"

    def test_dono_do_registro_ainda_consegue_editar(self, client):
        c, engine = client
        _como_fazenda(1)
        r = c.put("/cadastro/fornecedores/1", json={"nome": "Nome novo legitimo", "tipo": "fornecedor"})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(Fornecedor, 1).nome == "Nome novo legitimo"
