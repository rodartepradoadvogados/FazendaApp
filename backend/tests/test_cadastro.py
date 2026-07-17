"""
Testes do router de Cadastro — fornecedores, ficha do animal e metadados de
itens de estoque (Configurações > Cadastro).
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import Estoque, PlanoContaGerencial, SeedFlag


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

    def test_considerar_rmca_nao_e_mais_editavel_pela_api(self, client):
        # A elegibilidade do RMCA físico passou a ser automática, a partir da
        # conta gerencial padrão do item — este campo legado não é mais aceito
        # pela API (extra ignorado), então o valor do item não muda.
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Medicamento X", categoria="sanidade", quantidade=10, considerar_rmca=True))
            s.commit()
        item_id = c.get("/cadastro/estoque-itens").json()[0]["id"]
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"considerar_rmca": False})
        assert r.status_code == 200
        assert r.json()["considerar_rmca"] is True


class TestSindicanciaContaGerencialEstoque:
    """Sindicância automática: item de estoque -> conta gerencial padrão."""

    _CHAVE = "estoque_conta_gerencial_padrao_202607"

    def _limpar_marca(self, session):
        # A lifespan da app já roda a sindicância (SeedFlag) com o banco vazio
        # ao subir o TestClient — remove a marca para poder testar de novo com
        # os itens inseridos pelo teste.
        flag = session.get(SeedFlag, self._CHAVE)
        if flag:
            session.delete(flag)
            session.commit()

    def test_vincula_por_finalidade_e_nunca_sobrescreve_manual(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import sindicar_conta_gerencial_estoque

        with Session(engine) as s:
            self._limpar_marca(s)
            s.add(PlanoContaGerencial(codigo="3.01.01", nome="Alimentação do rebanho", ativa=True))
            s.add(PlanoContaGerencial(codigo="3.02.01", nome="Sanidade animal", ativa=True))
            s.add(Estoque(nome="Ração concentrada", finalidade="Ração/Alimento", quantidade=10))
            s.add(Estoque(nome="Vacina X", finalidade="Medicamento", quantidade=5))
            s.add(Estoque(nome="Já vinculado", finalidade="Ração/Alimento", quantidade=5, conta_gerencial_despesa_padrao="9.99.99"))
            s.add(Estoque(nome="Sem finalidade", quantidade=5))
            s.commit()

        with Session(engine) as s:
            sindicar_conta_gerencial_estoque(s)

        with Session(engine) as s:
            por_nome = {e.nome: e for e in s.exec(select(Estoque)).all()}
            assert por_nome["Ração concentrada"].conta_gerencial_despesa_padrao == "3.01.01"
            assert por_nome["Vacina X"].conta_gerencial_despesa_padrao == "3.02.01"
            assert por_nome["Já vinculado"].conta_gerencial_despesa_padrao == "9.99.99"  # não sobrescreve
            assert por_nome["Sem finalidade"].conta_gerencial_despesa_padrao is None

    def test_roda_uma_unica_vez(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import sindicar_conta_gerencial_estoque

        with Session(engine) as s:
            self._limpar_marca(s)
            s.add(PlanoContaGerencial(codigo="3.01.01", nome="Alimentação do rebanho", ativa=True))
            s.add(Estoque(nome="Ração", finalidade="Ração/Alimento", quantidade=10))
            s.commit()

        with Session(engine) as s:
            sindicar_conta_gerencial_estoque(s)
        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração")).first()
            item.conta_gerencial_despesa_padrao = None  # simula um ajuste manual, "desvinculando"
            s.add(item)
            s.commit()

        with Session(engine) as s:
            sindicar_conta_gerencial_estoque(s)  # já rodou uma vez — não deve rodar de novo

        with Session(engine) as s:
            item = s.exec(select(Estoque).where(Estoque.nome == "Ração")).first()
            assert item.conta_gerencial_despesa_padrao is None


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
        r = c.post("/cadastro/pessoas", json={"nome": "Dr. Huerik", "tipos": ["Veterinário"]})
        assert r.status_code == 200
        assert r.json()["tipos"] == ["Veterinário"]

    def test_cria_pessoa_com_multiplos_tipos(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={"nome": "Zé Inseminador", "tipos": ["Funcionário", "Inseminador"]})
        assert r.status_code == 200
        assert r.json()["tipos"] == ["Funcionário", "Inseminador"]
        r = c.get("/cadastro/pessoas/inseminadores")
        assert r.json() == ["Zé Inseminador"]

    def test_rejeita_tipo_invalido(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={"nome": "Fulano", "tipos": ["Gerente"]})
        assert r.status_code == 400

    def test_rejeita_sem_nenhum_tipo(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={"nome": "Fulano", "tipos": []})
        assert r.status_code == 400

    def test_atualiza_pessoa(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Diarista X", "tipos": ["Diarista"]}).json()["id"]
        r = c.put(f"/cadastro/pessoas/{pessoa_id}", json={"nome": "Diarista X", "tipos": ["Diarista"], "ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False


class TestTipoPessoa:
    def test_lista_tipos_seedados(self, client):
        c, engine = client
        nomes = {t["nome"] for t in c.get("/cadastro/pessoas/tipos").json()}
        assert "Funcionário" in nomes
        assert "Empreiteiro" in nomes

    def test_cria_novo_tipo_e_usa_na_pessoa(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas/tipos", json={"nome": "Consultor"})
        assert r.status_code == 200
        r = c.post("/cadastro/pessoas", json={"nome": "Fulano Consultor", "tipos": ["Consultor"]})
        assert r.status_code == 200
        assert r.json()["tipos"] == ["Consultor"]

    def test_nao_permite_tipo_duplicado(self, client):
        c, engine = client
        c.get("/cadastro/pessoas/tipos")  # garante seed
        r = c.post("/cadastro/pessoas/tipos", json={"nome": "Funcionário"})
        assert r.status_code == 409

    def test_atualiza_tipo(self, client):
        c, engine = client
        tipo_id = c.post("/cadastro/pessoas/tipos", json={"nome": "Estagiário"}).json()["id"]
        r = c.put(f"/cadastro/pessoas/tipos/{tipo_id}", json={"nome": "Estagiário", "ativo": False})
        assert r.status_code == 200
        assert r.json()["ativo"] is False


class TestProporcionalAdmissao:
    def _pessoa(self, c, data_admissao=None):
        return c.post("/cadastro/pessoas", json={
            "nome": "Funcionário Novo", "tipos": ["Funcionário"], "data_admissao": data_admissao,
        }).json()["id"]

    def test_sem_data_admissao_retorna_none(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.get("/cadastro/folha-pagamento/proporcional-admissao", params={"pessoa_id": pessoa_id, "competencia": "2026-07"})
        assert r.status_code == 200
        assert r.json() is None

    def test_fora_do_mes_de_admissao_retorna_none(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, "2026-06-15")
        r = c.get("/cadastro/folha-pagamento/proporcional-admissao", params={"pessoa_id": pessoa_id, "competencia": "2026-07"})
        assert r.status_code == 200
        assert r.json() is None

    def test_calcula_fracao_do_mes_de_admissao(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, "2026-07-16")
        r = c.get("/cadastro/folha-pagamento/proporcional-admissao", params={"pessoa_id": pessoa_id, "competencia": "2026-07"})
        assert r.status_code == 200
        dados = r.json()
        assert dados["dias_mes"] == 31
        assert dados["dias_trabalhados"] == 16
        assert dados["fracao"] == round(16 / 31, 6)

    def test_pessoa_inexistente_404(self, client):
        c, engine = client
        r = c.get("/cadastro/folha-pagamento/proporcional-admissao", params={"pessoa_id": 999999, "competencia": "2026-07"})
        assert r.status_code == 404


class TestFolhaPagamento:
    def _pessoa(self, c):
        return c.post("/cadastro/pessoas", json={"nome": "Funcionário Teste", "tipos": ["Funcionário"]}).json()["id"]

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
        c.put(f"/cadastro/pessoas/{pessoa_id}", json={"nome": "Funcionário Teste", "tipos": ["Funcionário"], "salario_base": 3000.0})
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
        return c.post("/cadastro/pessoas", json={"nome": "Funcionário Recorrente", "tipos": ["Funcionário"]}).json()["id"]

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
        r = c.post("/cadastro/pessoas", json={"nome": "Funcionário Vale", "tipos": ["Funcionário"]}).json()
        if salario_base is not None:
            c.put(f"/cadastro/pessoas/{r['id']}", json={
                "nome": "Funcionário Vale", "tipos": ["Funcionário"], "salario_base": salario_base,
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

    def test_seed_cria_eventos_e_doencas_padrao(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import seed_cadastro_sanitario
        with Session(engine) as s:
            seed_cadastro_sanitario(s)
        eventos = c.get("/cadastro/eventos-sanitarios").json()
        doencas = c.get("/cadastro/doencas").json()
        assert any(e["nome"] == "Vermífugo" for e in eventos)
        assert any(d["nome"] == "Brucelose" for d in doencas)

    def test_bootstrap_farmacia_cria_catalogo_de_principios_com_categoria(self, client):
        # O catálogo de princípios ativos (documento base) é responsabilidade de
        # bootstrap_farmacia, não de seed_cadastro_sanitario — roda em todo start.
        c, engine = client
        from fazenda.rules.farmacia import bootstrap_farmacia
        with Session(engine) as s:
            bootstrap_farmacia(s)
        principios = c.get("/cadastro/principios-ativos").json()
        assert len(principios) == 39
        assert all(p["categoria"] for p in principios)
        assert any(p["nome"] == "Ivermectina" for p in principios)

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


class TestEmpreitada:
    def _empreiteiro(self, c):
        return c.post("/cadastro/pessoas", json={"nome": "João Empreiteiro", "tipos": ["Empreiteiro"]}).json()["id"]

    def test_global_por_frequencia_gera_parcelas_e_contas_a_pagar(self, client):
        c, engine = client
        pessoa_id = self._empreiteiro(c)
        r = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Roçagem geral", "valor_total": 3000.0,
            "tipo_pagamento": "mensal",
            "parcelas": [
                {"data_vencimento": "2026-08-05", "valor": 1500.0},
                {"data_vencimento": "2026-09-05", "valor": 1500.0},
            ],
        })
        assert r.status_code == 200
        dados = r.json()
        assert len(dados["parcelas"]) == 2
        assert all(p["status"] == "pendente" for p in dados["parcelas"])
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            contas = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Empreitada")).all()
            assert len(contas) == 2
            assert {c.valor_total for c in contas} == {1500.0}

    def test_por_etapa_cria_etapas_editaveis(self, client):
        c, engine = client
        pessoa_id = self._empreiteiro(c)
        r = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Construção de cerca", "valor_total": 4000.0,
            "tipo_pagamento": "por_etapa",
            "etapas": [
                {"nome": "Etapa 1 - mourões", "valor": 2000.0},
                {"nome": "Etapa 2 - arame", "valor": 2000.0},
            ],
        })
        assert r.status_code == 200
        dados = r.json()
        assert len(dados["etapas"]) == 2
        assert all(not et["concluida"] for et in dados["etapas"])

    def test_concluir_etapa_gera_conta_no_dia_1_do_mes_seguinte(self, client):
        c, engine = client
        pessoa_id = self._empreiteiro(c)
        empreitada = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Cerca", "valor_total": 1000.0,
            "tipo_pagamento": "por_etapa",
            "etapas": [{"nome": "Única etapa", "valor": 1000.0}],
        }).json()
        etapa_id = empreitada["etapas"][0]["id"]
        r = c.put(f"/cadastro/empreitadas/{empreitada['id']}/etapas/{etapa_id}/concluir")
        assert r.status_code == 200
        dados = r.json()
        assert dados["etapas"][0]["concluida"] is True
        assert dados["status"] == "concluida"
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == dados["etapas"][0]["numero_lancamento_gerado"]
            )).first()
            assert conta is not None
            assert conta.data_vencimento.day == 1
            assert conta.valor_total == 1000.0

    def test_rejeita_pessoa_inexistente(self, client):
        c, engine = client
        r = c.post("/cadastro/empreitadas", json={
            "pessoa_id": 999999, "descricao": "X", "valor_total": 100.0, "tipo_pagamento": "mensal",
            "parcelas": [{"data_vencimento": "2026-08-05", "valor": 100.0}],
        })
        assert r.status_code == 404

    def test_rejeita_tipo_pagamento_invalido(self, client):
        c, engine = client
        pessoa_id = self._empreiteiro(c)
        r = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "X", "valor_total": 100.0, "tipo_pagamento": "anual",
        })
        assert r.status_code == 400


class TestContrato:
    def _pessoa(self, c):
        return c.post("/cadastro/pessoas", json={"nome": "Prestador X", "tipos": ["Prestador de serviços"]}).json()["id"]

    def test_com_frequencia_gera_parcelas(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/contratos", json={
            "pessoa_id": pessoa_id, "descricao": "Consultoria mensal", "valor_total": 6000.0,
            "forma_pagamento": "mensal",
            "parcelas": [
                {"data_vencimento": "2026-08-10", "valor": 2000.0},
                {"data_vencimento": "2026-09-10", "valor": 2000.0},
                {"data_vencimento": "2026-10-10", "valor": 2000.0},
            ],
        })
        assert r.status_code == 200
        dados = r.json()
        assert len(dados["parcelas"]) == 3
        assert dados["status"] == "ativo"

    def test_sem_frequencia_cria_lembrete_recorrente_na_agenda(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/contratos", json={
            "pessoa_id": pessoa_id, "descricao": "Parceria sem data fixa", "valor_total": 5000.0,
        })
        assert r.status_code == 200
        dados = r.json()
        assert dados["parcelas"] == []
        assert dados["origem_lembrete_agenda_id"] is not None
        with Session(engine) as s:
            from fazenda.models import AgendaManual
            lembrete = s.get(AgendaManual, dados["origem_lembrete_agenda_id"])
            assert lembrete is not None
            assert lembrete.recorrente is True
            assert lembrete.intervalo_meses == 1
            assert lembrete.data_evento.day == 1

    def test_encerrar_contrato_desativa_lembrete(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        contrato = c.post("/cadastro/contratos", json={
            "pessoa_id": pessoa_id, "descricao": "Parceria", "valor_total": 1000.0,
        }).json()
        r = c.put(f"/cadastro/contratos/{contrato['id']}/encerrar")
        assert r.status_code == 200
        assert r.json()["status"] == "encerrado"
        with Session(engine) as s:
            from fazenda.models import AgendaManual
            lembrete = s.get(AgendaManual, contrato["origem_lembrete_agenda_id"])
            assert lembrete.recorrente is False

    def test_rejeita_forma_pagamento_invalida(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/contratos", json={
            "pessoa_id": pessoa_id, "descricao": "X", "valor_total": 100.0, "forma_pagamento": "anual",
        })
        assert r.status_code == 400


class TestDiaria:
    def _diarista(self, c):
        return c.post("/cadastro/pessoas", json={"nome": "Maria Diarista", "tipos": ["Diarista"]}).json()["id"]

    def test_calcula_dias_e_saldo_devedor(self, client):
        c, engine = client
        pessoa_id = self._diarista(c)
        inicio = date.today() - timedelta(days=4)  # hoje + 4 dias atrás = 5 diárias
        r = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": inicio.isoformat(),
        })
        assert r.status_code == 200
        dados = r.json()
        assert dados["numero_diarias"] == 5
        assert dados["total_ate_hoje"] == 500.0
        assert dados["valor_pago"] == 0.0
        assert dados["saldo_devedor"] == 500.0

    def test_registrar_pagamento_abate_saldo(self, client):
        c, engine = client
        pessoa_id = self._diarista(c)
        inicio = date.today() - timedelta(days=1)  # 2 diárias
        diaria_id = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": inicio.isoformat(),
        }).json()["id"]
        r = c.post(f"/cadastro/diarias/{diaria_id}/pagamentos", json={
            "data_pagamento": date.today().isoformat(), "valor": 150.0,
        })
        assert r.status_code == 200
        dados = r.json()
        assert dados["valor_pago"] == 150.0
        assert dados["saldo_devedor"] == 50.0
        assert len(dados["pagamentos"]) == 1

    def test_rejeita_valor_diaria_invalido(self, client):
        c, engine = client
        pessoa_id = self._diarista(c)
        r = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 0, "data_inicio": date.today().isoformat(),
        })
        assert r.status_code == 400
