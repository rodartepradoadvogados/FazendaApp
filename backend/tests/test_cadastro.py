"""
Testes do router de Cadastro — fornecedores, ficha do animal e metadados de
itens de estoque (Configurações > Cadastro).
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

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


class TestFornecedores:
    def test_criar_listar_atualizar(self, client):
        c, engine = client
        r = c.post("/cadastro/fornecedores", json={"nome": "Agropecuária Central", "tipo": "fornecedor"})
        assert r.status_code == 200
        fid = r.json()["id"]

        r = c.get("/cadastro/fornecedores")
        assert len(r.json()) == 1

        r = c.put(f"/cadastro/fornecedores/{fid}", json={"nome": "Agropecuária Central Ltda", "tipo": "fabricante"})
        assert r.status_code == 200
        assert r.json()["nome"] == "Agropecuária Central Ltda"
        assert r.json()["tipo"] == "fabricante"

    def test_tipo_invalido_rejeitado(self, client):
        c, engine = client
        r = c.post("/cadastro/fornecedores", json={"nome": "X", "tipo": "invalido"})
        assert r.status_code == 400

    def test_nome_vazio_rejeitado(self, client):
        c, engine = client
        r = c.post("/cadastro/fornecedores", json={"nome": "  ", "tipo": "cliente"})
        assert r.status_code == 400


class TestFichaAnimal:
    def test_criar_animal_grava_na_tabela_real(self, client):
        c, engine = client
        r = c.post("/cadastro/animais", json={"numero": "500", "nome": "Estrela", "sexo": "F", "raca": "Girolando"})
        assert r.status_code == 200
        d = r.json()
        assert d["numero"] == "500"
        assert d["nome"] == "Estrela"
        assert d["ativo"] is True

        # O mesmo animal aparece no endpoint real de animais usado no resto do site.
        r2 = c.get("/animais/")
        assert any(a["numero"] == "500" for a in r2.json())

    def test_numero_duplicado_rejeitado(self, client):
        c, engine = client
        c.post("/cadastro/animais", json={"numero": "501"})
        r = c.post("/cadastro/animais", json={"numero": "501"})
        assert r.status_code == 400

    def test_listagem_em_ordem_numerica_crescente_nao_alfabetica(self, client):
        c, engine = client
        # Cadastrados fora de ordem — "9" deve vir antes de "10" e "80"
        # (ordenação lexicográfica erraria isso: "10" < "80" < "9").
        for numero in ["80", "10", "9", "1"]:
            c.post("/cadastro/animais", json={"numero": numero, "sexo": "F"})

        numeros = [a["numero"] for a in c.get("/animais/").json()]
        assert numeros == ["1", "9", "10", "80"]

    def test_atualizar_ficha_e_baixa_desativa(self, client):
        c, engine = client
        c.post("/cadastro/animais", json={"numero": "502"})
        r = c.put("/cadastro/animais/502", json={"numero": "502", "motivo_baixa": "venda", "data_baixa": "2026-07-01"})
        assert r.status_code == 200
        assert r.json()["ativo"] is False
        assert r.json()["motivo_baixa"] == "venda"

    def test_animal_inexistente_404(self, client):
        c, engine = client
        r = c.put("/cadastro/animais/999", json={"numero": "999"})
        assert r.status_code == 404


class TestMetaEstoque:
    def test_atualizar_metadados_embalagem(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Ração concentrada", categoria="alimento", quantidade=100))
            s.commit()
        r = c.get("/cadastro/estoque-itens")
        item_id = r.json()[0]["id"]

        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"unidade_embalagem": "Saca", "medida_embalagem": "kg/saca", "quantidade_embalagem": 40.0})
        assert r.status_code == 200
        assert r.json()["unidade_embalagem"] == "Saca"
        assert r.json()["medida_embalagem"] == "kg/saca"
        assert r.json()["quantidade_embalagem"] == 40.0

    def test_unidade_embalagem_invalida_rejeitada(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Concentrado XYZ", categoria="alimento", quantidade=10))
            s.commit()
        item_id = c.get("/cadastro/estoque-itens").json()[0]["id"]
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"unidade_embalagem": "Caminhão"})
        assert r.status_code == 400

    def test_fornecedor_inexistente_rejeitado(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Sal mineral", categoria="alimento", quantidade=10))
            s.commit()
        item_id = c.get("/cadastro/estoque-itens").json()[0]["id"]
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"fornecedor_id": 999})
        assert r.status_code == 400

    def test_atualizar_considerar_rmca(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Medicamento X", categoria="sanidade", quantidade=10))
            s.commit()
        item_id = c.get("/cadastro/estoque-itens").json()[0]["id"]
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"considerar_rmca": False})
        assert r.status_code == 200
        assert r.json()["considerar_rmca"] is False


class TestPessoas:
    def test_seed_cria_funcionarios_padrao(self, client):
        c, engine = client
        with Session(engine) as s:
            from fazenda.api.routers.cadastro import seed_pessoas
            seed_pessoas(s)
        nomes = {p["nome"] for p in c.get("/cadastro/pessoas").json()}
        assert "Leomir Bonfim" in nomes
        assert "Alexandre Scarpa" in nomes
        assert len(nomes) == 5

    def test_seed_e_idempotente(self, client):
        c, engine = client
        with Session(engine) as s:
            from fazenda.api.routers.cadastro import seed_pessoas
            seed_pessoas(s)
            seed_pessoas(s)
        assert len(c.get("/cadastro/pessoas").json()) == 5

    def test_cria_pessoa(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={"nome": "Dr. Huerik", "tipo": "Veterinário"})
        assert r.status_code == 200
        assert r.json()["tipo"] == "Veterinário"

    def test_rejeita_tipo_invalido(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={"nome": "Fulano", "tipo": "Gerente"})
        assert r.status_code == 400

    def test_atualiza_pessoa(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Diarista X", "tipo": "Diarista"}).json()["id"]
        r = c.put(f"/cadastro/pessoas/{pessoa_id}", json={"nome": "Diarista X", "tipo": "Diarista", "ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False


class TestFolhaPagamento:
    def _pessoa(self, c):
        return c.post("/cadastro/pessoas", json={"nome": "Funcionário Teste", "tipo": "Funcionário"}).json()["id"]

    def test_cria_lancamento_de_folha(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0, "descontos": 200.0,
        })
        assert r.status_code == 200
        assert r.json()["valor_liquido"] == 1800.0
        assert r.json()["status"] == "pendente"

    def test_lista_traz_nome_da_pessoa(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        c.post("/cadastro/folha-pagamento", json={"pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0})
        registros = c.get("/cadastro/folha-pagamento").json()
        assert registros[0]["pessoa_nome"] == "Funcionário Teste"

    def test_pessoa_inexistente_rejeitada(self, client):
        c, engine = client
        r = c.post("/cadastro/folha-pagamento", json={"pessoa_id": 999, "competencia": "2026-07", "valor_bruto": 2000.0})
        assert r.status_code == 404

    def test_valor_liquido_negativo_rejeitado(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/folha-pagamento", json={"pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 100.0, "descontos": 200.0})
        assert r.status_code == 400

    def test_atualiza_para_pago(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        registro_id = c.post("/cadastro/folha-pagamento", json={"pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0}).json()["id"]
        r = c.put(f"/cadastro/folha-pagamento/{registro_id}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0,
            "status": "pago", "data_pagamento": "2026-07-05",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "pago"
        assert r.json()["data_pagamento"] == "2026-07-05"

    def test_retencao_inss_ir_calcula_liquido_automaticamente(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0,
            "percentual_inss": 8.0, "valor_inss": 160.0, "percentual_ir": 5.0, "valor_ir": 100.0,
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["valor_inss"] == 160.0
        assert corpo["valor_ir"] == 100.0
        assert corpo["valor_liquido"] == 1740.0

    def test_nao_permite_editar_folha_ja_paga(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        registro_id = c.post("/cadastro/folha-pagamento", json={"pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0}).json()["id"]
        c.put(f"/cadastro/folha-pagamento/{registro_id}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0,
            "status": "pago", "data_pagamento": "2026-07-05",
        })
        r = c.put(f"/cadastro/folha-pagamento/{registro_id}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2500.0, "status": "pago",
        })
        assert r.status_code == 400

    def test_edicao_sincroniza_conta_a_pagar_gerada(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        registro = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0, "descontos": 200.0,
        }).json()
        c.put(f"/cadastro/folha-pagamento/{registro['id']}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2400.0, "descontos": 200.0,
        })
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == registro["numero_lancamento_gerado"])).first()
        assert conta.valor_total == 2200.0

    def test_listagem_traz_detalhe_discriminado_com_vale(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        c.put(f"/cadastro/pessoas/{pessoa_id}", json={"nome": "Funcionário Teste", "tipo": "Funcionário", "salario_base": 3000.0})
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 150.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-06-10", "parcelas": 1, "competencia_inicio": "2026-07",
        })
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0,
            "percentual_inss": 8.0, "valor_inss": 160.0,
        })
        registros = c.get("/cadastro/folha-pagamento").json()
        detalhe = registros[0]["detalhe"]
        labels = [d["label"] for d in detalhe]
        assert any("INSS" in l for l in labels)
        assert any("Vale" in l for l in labels)
        assert detalhe[-1]["label"] == "Valor líquido"
        assert detalhe[-1]["valor"] == registros[0]["valor_liquido"]


class TestFolhaPagamentoRecorrente:
    def _pessoa(self, c):
        return c.post("/cadastro/pessoas", json={"nome": "Funcionário Recorrente", "tipo": "Funcionário"}).json()["id"]

    def _competencia_anterior(self, competencia: str, meses: int) -> str:
        ano, mes = (int(x) for x in competencia.split("-"))
        for _ in range(meses):
            ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
        return f"{ano:04d}-{mes:02d}"

    def test_rejeita_recorrente_sem_dia_vencimento(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-01", "valor_bruto": 2000.0, "recorrente": True,
        })
        assert r.status_code == 400

    def test_lancamento_de_folha_gera_conta_a_pagar_imediatamente(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 3000.0, "descontos": 300.0,
        })
        assert r.status_code == 200
        corpo = r.json()
        assert corpo["numero_lancamento_gerado"]

        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == corpo["numero_lancamento_gerado"])).first()
        assert conta is not None
        assert conta.valor_total == 2700.0
        assert conta.tipo == "despesa"
        assert conta.data_vencimento == date(2026, 7, 5)

        # Aparece em Contas a Pagar...
        lancamentos = c.get("/financeiro/lancamentos").json()["lancamentos"]
        assert any(l["numero_lancamento"] == corpo["numero_lancamento_gerado"] for l in lancamentos)

        # ...e na Agenda, dentro da janela de vencimento.
        eventos = c.get("/agenda/", params={"data": "2026-07-01", "dias": 10}).json()["eventos"]
        assert any("Folha de pagamento" in e["descricao"] for e in eventos)

    def test_gera_competencias_seguintes_ate_o_mes_atual(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        competencia_atual = date.today().strftime("%Y-%m")
        competencia_inicial = self._competencia_anterior(competencia_atual, 3)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": competencia_inicial, "valor_bruto": 2000.0,
            "descontos": 200.0, "recorrente": True, "dia_vencimento": 5,
        })
        assert r.status_code == 200

        registros = c.get("/cadastro/folha-pagamento").json()
        competencias = sorted(r["competencia"] for r in registros)
        assert competencias == sorted({competencia_inicial, competencia_atual} | {
            self._competencia_anterior(competencia_atual, m) for m in range(3)
        })

        gerados = [r for r in registros if r["origem_recorrencia_id"]]
        assert len(gerados) == 3
        assert all(r["numero_lancamento_gerado"] for r in gerados)
        assert all(r["valor_liquido"] == 1800.0 for r in gerados)

        # O lançamento inicial (o "modelo" recorrente) também gera sua própria
        # conta a pagar — antes só as competências seguintes geradas
        # automaticamente ganhavam esse vínculo.
        assert all(r["numero_lancamento_gerado"] for r in registros)
        numeros_gerados = {r["numero_lancamento_gerado"] for r in registros}
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            contas_criadas = s.exec(select(ContaGerencial).where(ContaGerencial.origem == "auto")).all()
        assert {c.numero_lancamento for c in contas_criadas} == numeros_gerados
        assert len(contas_criadas) == 4
        assert all(c.tipo_documento == "Folha de pagamento" for c in contas_criadas)
        assert all(c.valor_total == 1800.0 for c in contas_criadas)

    def test_nao_duplica_ao_chamar_duas_vezes(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        competencia_atual = date.today().strftime("%Y-%m")
        competencia_inicial = self._competencia_anterior(competencia_atual, 2)
        c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": competencia_inicial, "valor_bruto": 1500.0,
            "recorrente": True, "dia_vencimento": 10,
        })
        c.get("/cadastro/folha-pagamento")
        primeira = c.get("/cadastro/folha-pagamento").json()
        segunda = c.get("/cadastro/folha-pagamento").json()
        assert len(primeira) == len(segunda)

    def test_marcar_pago_preserva_recorrencia(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        registro = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-01", "valor_bruto": 1500.0,
            "recorrente": True, "dia_vencimento": 10,
        }).json()
        r = c.put(f"/cadastro/folha-pagamento/{registro['id']}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-01", "valor_bruto": 1500.0,
            "status": "pago", "data_pagamento": "2026-01-10",
            "recorrente": True, "dia_vencimento": 10,
        })
        assert r.status_code == 200
        assert r.json()["recorrente"] is True
        assert r.json()["dia_vencimento"] == 10


class TestValeFuncionario:
    def _pessoa(self, c, salario_base=None):
        r = c.post("/cadastro/pessoas", json={"nome": "Funcionário Vale", "tipo": "Funcionário"}).json()
        if salario_base is not None:
            c.put(f"/cadastro/pessoas/{r['id']}", json={
                "nome": "Funcionário Vale", "tipo": "Funcionário", "salario_base": salario_base,
            })
        return r["id"]

    def test_rejeita_sem_salario_base_cadastrado(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
        })
        assert r.status_code == 400

    def test_rejeita_forma_pagamento_invalida(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "cheque",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
        })
        assert r.status_code == 400

    def test_cria_vale_parcelado_com_arredondamento_na_ultima_parcela(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 100.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-01-10", "parcelas": 3, "competencia_inicio": "2026-02",
        })
        assert r.status_code == 200
        parcelas = r.json()["parcelas_detalhe"]
        assert [p["competencia"] for p in parcelas] == ["2026-02", "2026-03", "2026-04"]
        assert round(sum(p["valor"] for p in parcelas), 2) == 100.0

    def test_alerta_quando_ultrapassa_quarenta_por_cento_do_salario(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=1000.0)  # limite = 400
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 500.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
        })
        assert r.status_code == 409
        detalhe = r.json()["detail"]
        assert detalhe["competencias_excedidas"][0]["competencia"] == "2026-02"

        r2 = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 500.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02", "confirmar": True,
        })
        assert r2.status_code == 200

    def test_parcela_de_vale_e_aplicada_automaticamente_na_folha(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
        })
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-02", "valor_bruto": 2000.0,
        })
        assert r.status_code == 200
        # Vale agora é coluna SEPARADA (valor_vale); descontos = descontos de folha manuais.
        assert r.json()["valor_vale"] == 300.0
        assert r.json()["descontos"] == 0.0
        assert r.json()["valor_liquido"] == 1700.0

        # outra competência (2026-03) não tem parcela de vale → sem desconto de vale
        r2 = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-03", "valor_bruto": 2000.0,
        })
        assert r2.json()["valor_vale"] == 0.0
        assert r2.json()["descontos"] == 0.0


class TestCadastroSanitario:
    """Princípio ativo / Doença / Evento sanitário — cadastros simples nome+ativo."""

    def test_seed_cria_eventos_doencas_e_principios_padrao(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import seed_cadastro_sanitario
        with Session(engine) as s:
            seed_cadastro_sanitario(s)
        eventos = c.get("/cadastro/eventos-sanitarios").json()
        doencas = c.get("/cadastro/doencas").json()
        principios = c.get("/cadastro/principios-ativos").json()
        assert any(e["nome"] == "Vermífugo" for e in eventos)
        assert any(d["nome"] == "Brucelose" for d in doencas)
        assert len(principios) >= 1

    def test_seed_e_idempotente(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import seed_cadastro_sanitario
        with Session(engine) as s:
            seed_cadastro_sanitario(s)
            seed_cadastro_sanitario(s)
        n1 = len(c.get("/cadastro/eventos-sanitarios").json())
        with Session(engine) as s:
            seed_cadastro_sanitario(s)
        n2 = len(c.get("/cadastro/eventos-sanitarios").json())
        assert n1 == n2

    def test_cria_e_atualiza_doenca(self, client):
        c, engine = client
        doenca_id = c.post("/cadastro/doencas", json={"nome": "Raiva bovina"}).json()["id"]
        r = c.put(f"/cadastro/doencas/{doenca_id}", json={"nome": "Raiva bovina", "ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False

    def test_nao_permite_evento_sanitario_duplicado(self, client):
        c, engine = client
        c.post("/cadastro/eventos-sanitarios", json={"nome": "Vacina X"})
        r = c.post("/cadastro/eventos-sanitarios", json={"nome": "Vacina X"})
        assert r.status_code == 409

    def test_cria_principio_ativo(self, client):
        c, engine = client
        r = c.post("/cadastro/principios-ativos", json={"nome": "Doramectina"})
        assert r.status_code == 200
        assert "Doramectina" in [p["nome"] for p in c.get("/cadastro/principios-ativos").json()]


class TestMotivoBaixa:
    """Motivo de baixa (Rebanho > Baixar animal) — mesmo padrão nome+ativo."""

    def test_seed_cria_motivos_padrao(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import seed_motivos_baixa
        with Session(engine) as s:
            seed_motivos_baixa(s)
        motivos = c.get("/cadastro/motivos-baixa").json()
        assert any(m["nome"] == "Mastite" for m in motivos)
        assert len(motivos) >= 30

    def test_seed_e_idempotente(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import seed_motivos_baixa
        with Session(engine) as s:
            seed_motivos_baixa(s)
            seed_motivos_baixa(s)
        n1 = len(c.get("/cadastro/motivos-baixa").json())
        with Session(engine) as s:
            seed_motivos_baixa(s)
        n2 = len(c.get("/cadastro/motivos-baixa").json())
        assert n1 == n2

    def test_cria_edita_e_desativa_motivo(self, client):
        c, engine = client
        motivo_id = c.post("/cadastro/motivos-baixa", json={"nome": "Queda de barranco"}).json()["id"]
        r = c.put(f"/cadastro/motivos-baixa/{motivo_id}", json={"nome": "Queda de barranco", "ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False

    def test_nao_permite_motivo_duplicado(self, client):
        c, engine = client
        c.post("/cadastro/motivos-baixa", json={"nome": "Cobra"})
        r = c.post("/cadastro/motivos-baixa", json={"nome": "Cobra"})
        assert r.status_code == 409

    def test_baixas_motivos_so_traz_ativos(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import seed_motivos_baixa
        with Session(engine) as s:
            seed_motivos_baixa(s)
        inativo_id = c.post("/cadastro/motivos-baixa", json={"nome": "Motivo Descontinuado"}).json()["id"]
        c.put(f"/cadastro/motivos-baixa/{inativo_id}", json={"nome": "Motivo Descontinuado", "ativo": False})
        opcoes = c.get("/baixas/motivos").json()
        assert "Motivo Descontinuado" not in opcoes["motivos_doenca"]
        assert "Mastite" in opcoes["motivos_doenca"]


class TestServicoCadastro:
    """Cadastro de Serviços (lançamento financeiro > produto ou serviço) — nome+ativo."""

    def test_seed_cria_servicos_padrao(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import seed_servicos
        with Session(engine) as s:
            seed_servicos(s)
        servicos = c.get("/cadastro/servicos").json()
        assert any(s["nome"] == "Frete" for s in servicos)
        assert any(s["nome"] == "Manutenção em tratores" for s in servicos)
        # 9 serviços padrão + 4 serviços de exames (Exames + 3 categorias).
        assert any(s["nome"] == "Exames" for s in servicos)
        assert any(s["nome"] == "Exame de tuberculose" for s in servicos)
        assert len(servicos) == 13

    def test_seed_e_idempotente(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import seed_servicos
        with Session(engine) as s:
            seed_servicos(s)
            seed_servicos(s)
        n1 = len(c.get("/cadastro/servicos").json())
        with Session(engine) as s:
            seed_servicos(s)
        n2 = len(c.get("/cadastro/servicos").json())
        assert n1 == n2

    def test_cria_edita_e_desativa_servico(self, client):
        c, engine = client
        servico_id = c.post("/cadastro/servicos", json={"nome": "Limpeza de silo"}).json()["id"]
        r = c.put(f"/cadastro/servicos/{servico_id}", json={"nome": "Limpeza de silo", "ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False

    def test_nao_permite_servico_duplicado(self, client):
        c, engine = client
        c.post("/cadastro/servicos", json={"nome": "Roçagem"})
        r = c.post("/cadastro/servicos", json={"nome": "Roçagem"})
        assert r.status_code == 409
