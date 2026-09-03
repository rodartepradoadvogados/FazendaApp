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
from fazenda.models import Animal, ContaCorrente, Estoque, Parto, PlanoContaGerencial, SeedFlag


def _criar_conta_corrente(engine) -> int:
    """Conta bancária da fazenda usada nos testes de vale de funcionário —
    todo vale que sai em dinheiro/pix/transferência agora exige uma."""
    with Session(engine) as s:
        conta = ContaCorrente(banco="Banco do Brasil", agencia="0001-2", numero_conta="12345-6")
        s.add(conta)
        s.commit()
        s.refresh(conta)
        return conta.id


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


class TestMatrizesComParto:
    def test_lista_so_femeas_com_pelo_menos_1_parto(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="750", nome="Estrela", sexo="F", ativo=True))
            s.add(Animal(numero="751", nome="Sem parto", sexo="F", ativo=True))
            s.add(Parto(numero_matriz="750", ordem_parto=1))
            s.commit()
        r = c.get("/cadastro/animais/matrizes")
        assert r.status_code == 200
        numeros = [m["numero"] for m in r.json()]
        assert "750" in numeros
        assert "751" not in numeros
        assert next(m for m in r.json() if m["numero"] == "750")["nome"] == "Estrela"


class TestValidacaoMaeParto:
    """A ficha do animal (Configurações > Cadastro > Animal) permite informar
    a mãe manualmente, fora do lançamento de Parto — mas isso precisa casar
    com o histórico reprodutivo já lançado dela (ver
    `validar_e_vincular_mae` em fazenda/api/routers/cadastro/animais.py)."""

    def test_mae_sem_nenhum_parto_bloqueia(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="700", sexo="F", ativo=True))
            s.commit()
        r = c.post("/cadastro/animais", json={"numero": "701", "sexo": "F", "mae_numero": "700"})
        assert r.status_code == 409
        assert "nenhum parto" in r.json()["detail"]

    def test_mae_com_todos_partos_vinculados_a_outros_animais_bloqueia(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="710", sexo="F", ativo=True))
            s.add(Parto(numero_matriz="710", ordem_parto=1, numero_cria_1="711"))
            s.add(Parto(numero_matriz="710", ordem_parto=2, numero_cria_1="712"))
            s.commit()
        r = c.post("/cadastro/animais", json={"numero": "713", "sexo": "F", "mae_numero": "710"})
        assert r.status_code == 409
        detalhe = r.json()["detail"]
        assert "2" in detalhe
        assert "711" in detalhe and "712" in detalhe

    def test_mae_com_parto_livre_permite_e_vincula_a_cria(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="720", sexo="F", ativo=True))
            s.add(Parto(numero_matriz="720", ordem_parto=1, numero_cria_1="721"))
            parto_livre = Parto(numero_matriz="720", ordem_parto=2)
            s.add(parto_livre)
            s.commit()
            parto_livre_id = parto_livre.id

        r = c.post("/cadastro/animais", json={"numero": "722", "sexo": "F", "mae_numero": "720"})
        assert r.status_code == 200, r.text
        assert r.json()["mae_numero"] == "720"

        with Session(engine) as s:
            parto = s.get(Parto, parto_livre_id)
            assert parto.numero_cria_1 == "722"
            outro_parto = s.exec(select(Parto).where(Parto.numero_matriz == "720", Parto.ordem_parto == 1)).first()
            assert outro_parto.numero_cria_1 == "721"  # não mexeu no parto já ocupado por outra cria

    def test_reeditar_a_mesma_ficha_sem_mudar_mae_nao_bloqueia(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="730", sexo="F", ativo=True))
            s.add(Parto(numero_matriz="730", ordem_parto=1))
            s.commit()
        c.post("/cadastro/animais", json={"numero": "731", "sexo": "F", "mae_numero": "730"})

        r = c.put("/cadastro/animais/731", json={"numero": "731", "sexo": "F", "mae_numero": "730", "nome": "Estrela"})
        assert r.status_code == 200, r.text
        assert r.json()["nome"] == "Estrela"

    def test_remover_mae_desvincula_o_parto(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Animal(numero="740", sexo="F", ativo=True))
            parto = Parto(numero_matriz="740", ordem_parto=1)
            s.add(parto)
            s.commit()
            parto_id = parto.id
        c.post("/cadastro/animais", json={"numero": "741", "sexo": "F", "mae_numero": "740"})

        r = c.put("/cadastro/animais/741", json={"numero": "741", "sexo": "F", "mae_numero": None})
        assert r.status_code == 200, r.text
        with Session(engine) as s:
            assert s.get(Parto, parto_id).numero_cria_1 is None


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

    def test_unidade_embalagem_fora_da_lista_padrao_e_aceita(self, client):
        # unidade_embalagem/medida_embalagem viraram cadastro dinâmico
        # (Configurações > Cadastro > Estoque > Unidade (embalagem) / Unidade
        # de Medida) — o backend não tem mais lista fixa pra validar contra,
        # mesmo tratamento que categoria/finalidade/unidade já recebem (o
        # cadastro só alimenta o seletor, sem whitelist aqui). Um nome
        # cadastrado pelo usuário (ex.: "Caminhão", "doses/frasco") tem que
        # ser aceito mesmo sem estar entre os valores semeados por padrão.
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Concentrado XYZ", categoria="alimento", quantidade=10))
            s.commit()
        item_id = c.get("/cadastro/estoque-itens").json()[0]["id"]
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"unidade_embalagem": "Caminhão", "medida_embalagem": "doses/frasco"})
        assert r.status_code == 200, r.text
        assert r.json()["unidade_embalagem"] == "Caminhão"
        assert r.json()["medida_embalagem"] == "doses/frasco"

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

    def test_conta_gerencial_despesa_padrao_e_editavel_e_persiste(self, client):
        # Ao contrário do considerar_rmca legado (acima), a conta gerencial
        # padrão do item é o campo que de fato controla a elegibilidade do
        # RMCA físico — a API precisa aceitar e persistir essa mudança.
        c, engine = client
        with Session(engine) as s:
            s.add(Estoque(nome="Concentrado proteico", categoria="alimento", quantidade=50))
            s.commit()
        item_id = c.get("/cadastro/estoque-itens").json()[0]["id"]

        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"conta_gerencial_despesa_padrao": "3.01.01"})
        assert r.status_code == 200
        assert r.json()["conta_gerencial_despesa_padrao"] == "3.01.01"

        with Session(engine) as s:
            item = s.get(Estoque, item_id)
            assert item.conta_gerencial_despesa_padrao == "3.01.01"

        # Limpando o campo (envia null) também deve funcionar.
        r = c.put(f"/cadastro/estoque-itens/{item_id}", json={"conta_gerencial_despesa_padrao": None})
        assert r.status_code == 200
        assert r.json()["conta_gerencial_despesa_padrao"] is None


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

    def test_cria_pessoa_sem_contato_retorna_listas_vazias(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={"nome": "Sem Contato", "tipos": ["Funcionário"]})
        assert r.status_code == 200
        assert r.json()["telefones"] == []
        assert r.json()["emails"] == []

    def test_cria_pessoa_com_multiplos_telefones_e_emails(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={
            "nome": "Multi Contato", "tipos": ["Funcionário"],
            "telefones": ["(11) 99999-0001", "(11) 3333-0002"],
            "emails": ["principal@x.com", "backup@x.com"],
        })
        assert r.status_code == 200
        dados = r.json()
        assert dados["telefones"] == ["(11) 99999-0001", "(11) 3333-0002"]
        assert dados["emails"] == ["principal@x.com", "backup@x.com"]

    def test_lista_pessoas_traz_telefones_e_emails(self, client):
        c, engine = client
        c.post("/cadastro/pessoas", json={
            "nome": "Multi Contato 2", "tipos": ["Funcionário"],
            "telefones": ["(11) 99999-0003"], "emails": ["a@x.com", "b@x.com"],
        })
        pessoa = next(p for p in c.get("/cadastro/pessoas").json() if p["nome"] == "Multi Contato 2")
        assert pessoa["telefones"] == ["(11) 99999-0003"]
        assert pessoa["emails"] == ["a@x.com", "b@x.com"]

    def test_atualiza_pessoa_troca_lista_de_contatos(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={
            "nome": "Contato Trocado", "tipos": ["Funcionário"], "emails": ["antigo@x.com"],
        }).json()["id"]
        r = c.put(f"/cadastro/pessoas/{pessoa_id}", json={
            "nome": "Contato Trocado", "tipos": ["Funcionário"], "emails": ["novo1@x.com", "novo2@x.com"],
        })
        assert r.status_code == 200
        assert r.json()["emails"] == ["novo1@x.com", "novo2@x.com"]

    def test_normaliza_lista_de_contato_remove_vazios_e_duplicatas(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={
            "nome": "Contato Sujo", "tipos": ["Funcionário"],
            "telefones": [" (11) 99999-0004 ", "", "(11) 99999-0004"],
            "emails": ["", "  "],
        })
        assert r.status_code == 200
        assert r.json()["telefones"] == ["(11) 99999-0004"]
        assert r.json()["emails"] == []

    def test_cria_pessoa_com_dados_civis_e_endereco(self, client):
        # Campos novos (jul/2026) são aditivos — nunca bloqueiam o cadastro
        # (ver _exigir_campos_obrigatorios em routers/cadastro/pessoas.py).
        c, engine = client
        r = c.post("/cadastro/pessoas", json={
            "nome": "Com Dados Civis", "tipos": ["Funcionário"],
            "cpf_cnpj": "123.456.789-00", "rg": "MG-18.223.410", "data_nascimento": "1985-03-14",
            "genero": "Feminino", "estado_civil": "Casado(a)",
            "endereco_rua": "Rua das Palmeiras", "endereco_numero": "120", "endereco_bairro": "Centro",
            "endereco_cidade": "Uberaba", "endereco_uf": "MG",
        })
        assert r.status_code == 200
        dados = r.json()
        assert dados["rg"] == "MG-18.223.410"
        assert dados["data_nascimento"] == "1985-03-14"
        assert dados["genero"] == "Feminino"
        assert dados["estado_civil"] == "Casado(a)"
        assert dados["endereco_rua"] == "Rua das Palmeiras"
        assert dados["endereco_uf"] == "MG"

    def test_cria_pessoa_sem_dados_civis_nao_e_bloqueada(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={"nome": "Sem Dados Civis", "tipos": ["Diarista"]})
        assert r.status_code == 200
        dados = r.json()
        assert dados["rg"] is None
        assert dados["endereco_rua"] is None

    def test_email_legado_reflete_primeiro_da_lista_para_recibo(self, client):
        """A folha de pagamento resolve o e-mail do recibo lendo Pessoa.email
        diretamente (ver financeiro.destinatario_recibo) — precisa continuar
        funcionando mesmo com múltiplos e-mails cadastrados."""
        c, engine = client
        c.post("/cadastro/pessoas", json={
            "nome": "Funcionário Recibo", "tipos": ["Funcionário"],
            "emails": ["principal@x.com", "secundario@x.com"],
        })
        with Session(engine) as s:
            from fazenda.models import Pessoa
            pessoa = s.exec(select(Pessoa).where(Pessoa.nome == "Funcionário Recibo")).first()
            assert pessoa.email == "principal@x.com"

    def test_exclui_pessoa_sem_vinculo(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Descartável", "tipos": ["Diarista"]}).json()["id"]
        r = c.delete(f"/cadastro/pessoas/{pessoa_id}")
        assert r.status_code == 200
        assert r.json() == {"excluido": True}
        assert not any(p["id"] == pessoa_id for p in c.get("/cadastro/pessoas").json())

    def test_exclui_pessoa_inexistente_404(self, client):
        c, engine = client
        r = c.delete("/cadastro/pessoas/999999")
        assert r.status_code == 404

    def test_bloqueia_exclusao_de_pessoa_com_usuario_vinculado(self, client):
        """Login de usuário é FK real para pessoa.id (Usuario.pessoa_id) —
        excluir a pessoa órfã quebraria o login, então o backend bloqueia com
        409 e orienta a desativar em vez de excluir (ver excluir_pessoa)."""
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Com Login", "tipos": ["Funcionário"]}).json()["id"]
        with Session(engine) as s:
            from fazenda.models import Usuario
            s.add(Usuario(username="comlogin", senha_hash="x", pessoa_id=pessoa_id))
            s.commit()
        r = c.delete(f"/cadastro/pessoas/{pessoa_id}")
        assert r.status_code == 409
        assert "desative" in r.json()["detail"].lower()
        assert any(p["id"] == pessoa_id for p in c.get("/cadastro/pessoas").json())

    def test_bloqueia_exclusao_de_pessoa_com_cronograma_sanitario_como_veterinario(self, client):
        """CronogramaSanitario.veterinario_pessoa_id é FK real para pessoa.id
        (workflow de agendamento de vacina/exame, ver models/sanidade.py) —
        checado à parte de _TABELAS_COM_PESSOA_ID por ter nome de coluna
        diferente (ver excluir_pessoa)."""
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Dra. Vet", "tipos": ["Veterinário"]}).json()["id"]
        with Session(engine) as s:
            from fazenda.models import CalendarioSanitario, CronogramaSanitario, EventoSanitario
            evento = EventoSanitario(nome="Brucelose B19")
            s.add(evento)
            s.commit()
            s.refresh(evento)
            regra = CalendarioSanitario(
                evento_sanitario_id=evento.id, frequencia_valor=1, frequencia_unidade="anos",
                data_evento=date.today(), usa_cronograma=True,
            )
            s.add(regra)
            s.commit()
            s.refresh(regra)
            s.add(CronogramaSanitario(calendario_sanitario_id=regra.id, data_evento=date.today(), veterinario_pessoa_id=pessoa_id))
            s.commit()
        r = c.delete(f"/cadastro/pessoas/{pessoa_id}")
        assert r.status_code == 409
        assert "cronograma" in r.json()["detail"].lower()


class TestTipoPessoa:
    def test_lista_tipos_seedados(self, client):
        c, engine = client
        nomes = {t["nome"] for t in c.get("/cadastro/pessoas/tipos").json()}
        assert "Funcionário" in nomes
        assert "Empreiteiro" in nomes

    def test_administrador_e_contador_estao_seedados(self, client):
        # Administrador/Contador (ago/2026) — adicionados a TIPOS_PESSOA para
        # que usePessoasAtivas (frontend) tenha um tipo cadastrável que
        # qualifique alguém como "Responsável" sem precisar ser
        # Funcionário/Veterinário/Zootecnista (ver regra no frontend).
        c, engine = client
        nomes = {t["nome"] for t in c.get("/cadastro/pessoas/tipos").json()}
        assert "Administrador" in nomes
        assert "Contador" in nomes

    def test_seed_tipos_pessoa_continua_idempotente_com_administrador_e_contador(self, client):
        # seed_tipos_pessoa roda uma vez por fazenda (SeedFlag) — chamar a
        # rota de listagem várias vezes (ela auto-semeia via
        # seed_tipos_pessoa) não pode duplicar nenhum tipo, incluindo os dois
        # novos.
        c, engine = client
        c.get("/cadastro/pessoas/tipos")
        c.get("/cadastro/pessoas/tipos")
        r = c.get("/cadastro/pessoas/tipos")
        nomes = [t["nome"] for t in r.json()]
        assert nomes.count("Administrador") == 1
        assert nomes.count("Contador") == 1
        assert len(nomes) == len(set(nomes))

    def test_cria_pessoa_administrador_e_contador(self, client):
        c, engine = client
        r = c.post("/cadastro/pessoas", json={"nome": "Dona Rosa", "tipos": ["Administrador"]})
        assert r.status_code == 200
        assert r.json()["tipos"] == ["Administrador"]
        r = c.post("/cadastro/pessoas", json={"nome": "Seu Nelson", "tipos": ["Contador"]})
        assert r.status_code == 200
        assert r.json()["tipos"] == ["Contador"]

    def test_validar_tipos_backfill_administrador_contador_fazenda_antiga(self):
        # Reproduz o bug relatado em produção: uma fazenda cujo
        # seed_tipos_pessoa já rodou ANTES de Administrador/Contador
        # existirem em TIPOS_PESSOA (ago/2026) tem o SeedFlag
        # "tipos_pessoa_v1_fazenda_1" já marcado, mas nunca ganhou essas
        # duas linhas em TipoPessoa — chamar seed_tipos_pessoa de novo não
        # adianta nada, porque a flag já existe e a função retorna sem
        # fazer nada. Sem o backfill (seed_tipos_papel_administrativo),
        # _validar_tipos(["Administrador"]) falha com "Tipo inválido" para
        # sempre nessa fazenda, mesmo autossemeando a cada chamada.
        from fazenda.api.routers.cadastro.pessoas import _validar_tipos
        from fazenda.models import SeedFlag, TipoPessoa

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(SeedFlag(chave="tipos_pessoa_v1_fazenda_1"))
            s.add(TipoPessoa(nome="Funcionário", fazenda_id=1))
            s.add(TipoPessoa(nome="Geral", fazenda_id=1))
            s.commit()

        with Session(engine) as s:
            nomes = {t.nome for t in s.exec(select(TipoPessoa)).all()}
            assert "Administrador" not in nomes  # fazenda "antiga" simulada

            # Antes da correção este raise era exatamente o bug relatado em
            # produção: "Tipo inválido" mesmo a fazenda tendo passado pelo
            # seed. Depois da correção (seed_tipos_papel_administrativo
            # chamada dentro de _validar_tipos), o backfill acontece na
            # hora e a chamada funciona normalmente.
            resultado = _validar_tipos(s, ["Administrador"], fazenda_id=1)
            assert resultado == "Administrador"

        with Session(engine) as s:
            # Backfill não duplica nem mexe no que já existia.
            nomes_finais = [t.nome for t in s.exec(
                select(TipoPessoa).where(TipoPessoa.fazenda_id == 1)
            ).all()]
            assert nomes_finais.count("Administrador") == 1
            assert nomes_finais.count("Contador") == 1
            assert nomes_finais.count("Funcionário") == 1
            assert nomes_finais.count("Geral") == 1

            # E o Contador do mesmo backfill também passa a validar.
            assert _validar_tipos(s, ["Contador"], fazenda_id=1) == "Contador"

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


class TestBackfillTiposOrfaos:
    """Caso real de produção: "Sócio" gravado em `Pessoa.tipo` sem NUNCA ter
    sido um `TipoPessoa` cadastrado desta fazenda (dado legado de antes da
    validação estrita). Diferente do backfill de Administrador/Contador
    (cria um tipo novo que ninguém ainda usa) — aqui o tipo já ESTÁ em uso,
    só nunca foi registrado. Sem a correção, reeditar essa MESMA pessoa (o
    formulário reenvia os tipos atuais dela) falhava com "Tipo inválido",
    mesmo sem tentar adicionar nada de novo — o próprio "Sócio" já gravado
    reprovava a validação."""

    def test_validar_tipos_aceita_tipo_orfao_ja_em_uso(self):
        from fazenda.api.routers.cadastro.pessoas import _validar_tipos
        from fazenda.models import Pessoa, SeedFlag, TipoPessoa

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(SeedFlag(chave="tipos_pessoa_v1_fazenda_1"))
            s.add(TipoPessoa(nome="Funcionário", fazenda_id=1))
            # "Sócio" nunca foi um TipoPessoa desta fazenda, mas já está
            # gravado numa pessoa real (dado legado).
            s.add(Pessoa(nome="Jairo", tipo="Sócio", fazenda_id=1))
            s.commit()

        with Session(engine) as s:
            nomes = {t.nome for t in s.exec(select(TipoPessoa).where(TipoPessoa.fazenda_id == 1)).all()}
            assert "Sócio" not in nomes  # órfão: em uso, mas não cadastrado

            # Reeditar a mesma pessoa (reenviando "Sócio" + acrescentando
            # "Administrador") não pode mais falhar por causa do próprio
            # tipo que ela já tinha.
            resultado = _validar_tipos(s, ["Sócio", "Administrador"], fazenda_id=1)
            assert resultado == "Sócio,Administrador"

        with Session(engine) as s:
            nomes_finais = [t.nome for t in s.exec(select(TipoPessoa).where(TipoPessoa.fazenda_id == 1)).all()]
            assert nomes_finais.count("Sócio") == 1  # backfillado, sem duplicar

    def test_listar_tipos_pessoa_expoe_tipo_orfao_como_opcao(self, client):
        # Depois do backfill, "Sócio" também aparece na lista que alimenta os
        # checkboxes do frontend — não fica só validando "por baixo dos panos".
        c, engine = client
        with Session(engine) as s:
            from fazenda.models import Pessoa
            s.add(Pessoa(nome="Jairo", tipo="Sócio"))
            s.commit()

        nomes = {t["nome"] for t in c.get("/cadastro/pessoas/tipos").json()}
        assert "Sócio" in nomes

    def test_backfill_nao_duplica_tipo_ja_cadastrado(self):
        from fazenda.api.routers.cadastro.pessoas import backfill_tipos_orfaos
        from fazenda.models import Pessoa, TipoPessoa

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SQLModel.metadata.create_all(engine)
        with Session(engine) as s:
            s.add(TipoPessoa(nome="Sócio", fazenda_id=1))
            s.add(Pessoa(nome="Jairo", tipo="Sócio", fazenda_id=1))
            s.commit()
            backfill_tipos_orfaos(s, fazenda_id=1)

        with Session(engine) as s:
            nomes = [t.nome for t in s.exec(select(TipoPessoa).where(TipoPessoa.fazenda_id == 1)).all()]
            assert nomes.count("Sócio") == 1


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

    def test_folha_sem_centro_custo_assume_pecuaria_leiteira_editavel(self, client):
        """#504 — folha vincula por padrão a "Pecuária Leiteira" (tanto no
        registro quanto na conta a pagar gerada), mas o campo é editável."""
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/folha-pagamento", json={"pessoa_id": pessoa_id, "competencia": "2026-07", "valor_bruto": 2000.0})
        assert r.json()["centro_custo"] == "Pecuária Leiteira"
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Folha de pagamento")).first()
            assert conta.centro_custo == "Pecuária Leiteira"

        r2 = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-08", "valor_bruto": 2000.0, "centro_custo": "Arrendamento",
        })
        assert r2.json()["centro_custo"] == "Arrendamento"

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
        conta_id = _criar_conta_corrente(engine)
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 150.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-06-10", "parcelas": 1, "competencia_inicio": "2026-07",
            "conta_corrente_id": conta_id,
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
        assert corpo["competencia"] == "2026-07"

        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == corpo["numero_lancamento_gerado"])).first()
        assert conta is not None
        assert conta.valor_total == 2700.0
        assert conta.tipo == "despesa"
        # Competência = mês trabalhado (07/2026); pagamento cai no mês seguinte, dia 5.
        assert conta.data_competencia == date(2026, 7, 1)
        assert conta.data_vencimento == date(2026, 8, 5)

        # Aparece em Contas a Pagar...
        lancamentos = c.get("/financeiro/lancamentos").json()["lancamentos"]
        assert any(l["numero_lancamento"] == corpo["numero_lancamento_gerado"] for l in lancamentos)

        # ...e na Agenda, dentro da janela de vencimento (mês seguinte à competência).
        eventos = c.get("/agenda/", params={"data": "2026-08-01", "dias": 10}).json()["eventos"]
        assert any("Folha de pagamento" in e["descricao"] for e in eventos)

    def test_dia_vencimento_customizado_aplica_no_mes_seguinte(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c)
        r = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-12", "valor_bruto": 2000.0,
            "recorrente": True, "dia_vencimento": 15,
        })
        assert r.status_code == 200
        corpo = r.json()
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.numero_lancamento == corpo["numero_lancamento_gerado"])).first()
        # Competência de dezembro vira pagamento em janeiro do ano seguinte, dia 15.
        assert conta.data_vencimento == date(2027, 1, 15)
        assert conta.data_competencia == date(2026, 12, 1)

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
        conta_id = _criar_conta_corrente(engine)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 100.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-01-10", "parcelas": 3, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200
        parcelas = r.json()["parcelas_detalhe"]
        assert [p["competencia"] for p in parcelas] == ["2026-02", "2026-03", "2026-04"]
        assert round(sum(p["valor"] for p in parcelas), 2) == 100.0

    def test_rejeita_vale_em_dinheiro_sem_conta_bancaria(self, client):
        """Vale que sai em dinheiro/pix/transferência precisa de uma conta
        bancária vinculada — sem isso não há como aparecer no extrato."""
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
        })
        assert r.status_code == 400

    def test_vale_desconto_integral_folha_nao_exige_conta_nem_gera_lancamento(self, client):
        """"desconto_integral_folha" não movimenta banco nenhum na hora do
        vale (o efeito é só reduzir o líquido da folha futura) — não exige
        conta bancária e não deve gerar ContaGerencial nenhuma."""
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "desconto_integral_folha",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
        })
        assert r.status_code == 200, r.text
        assert r.json()["numero_lancamento_gerado"] is None
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            assert s.exec(select(ContaGerencial)).first() is None

    def test_vale_gera_lancamento_ja_pago_com_conta_bancaria_no_extrato(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        conta_id = _criar_conta_corrente(engine)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["numero_lancamento_gerado"]
        assert corpo["conta_corrente_id"] == conta_id

        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta_gerencial = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == corpo["numero_lancamento_gerado"])
            ).first()
        assert conta_gerencial is not None
        assert conta_gerencial.valor_total == 300.0
        assert conta_gerencial.valor_pago == 300.0  # nasce já pago — o vale é entregue no ato
        assert conta_gerencial.data_pagamento == date(2026, 1, 10)
        assert conta_gerencial.conta_bancaria == "Banco do Brasil · Agência 0001-2 · Conta corrente 12345-6"
        assert conta_gerencial.tipo == "despesa"

        # E aparece no extrato (GET /financeiro/lancamentos).
        lancamentos = c.get("/financeiro/lancamentos").json()["lancamentos"]
        assert any(l["numero_lancamento"] == corpo["numero_lancamento_gerado"] for l in lancamentos)

    def test_alerta_quando_ultrapassa_quarenta_por_cento_do_salario(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=1000.0)  # limite = 400
        conta_id = _criar_conta_corrente(engine)
        r = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 500.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        })
        assert r.status_code == 409
        detalhe = r.json()["detail"]
        assert detalhe["competencias_excedidas"][0]["competencia"] == "2026-02"

        r2 = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 500.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02", "confirmar": True,
            "conta_corrente_id": conta_id,
        })
        assert r2.status_code == 200

    def test_parcela_de_vale_e_aplicada_automaticamente_na_folha(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        conta_id = _criar_conta_corrente(engine)
        c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
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

    def test_atualiza_vale_recalcula_parcelas_e_folha(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        conta_id = _criar_conta_corrente(engine)
        vale = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        }).json()
        folha = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-02", "valor_bruto": 2000.0,
        }).json()
        assert folha["valor_vale"] == 300.0

        r = c.put(f"/cadastro/vales/{vale['id']}", json={
            "pessoa_id": pessoa_id, "valor_total": 600.0, "forma_pagamento": "pix",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200
        assert r.json()["valor_total"] == 600.0
        assert r.json()["forma_pagamento"] == "pix"
        assert [p["valor"] for p in r.json()["parcelas_detalhe"]] == [600.0]

        folha2 = c.get("/cadastro/folha-pagamento").json()
        alvo = next(f for f in folha2 if f["id"] == folha["id"])
        assert alvo["valor_vale"] == 600.0
        assert alvo["valor_liquido"] == 1400.0

        # O lançamento gerado para o vale também é sincronizado com a edição.
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta_gerencial = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == r.json()["numero_lancamento_gerado"])
            ).first()
        assert conta_gerencial.valor_total == 600.0
        assert conta_gerencial.valor_pago == 600.0
        assert conta_gerencial.forma_pagamento == "pix"

    def test_atualiza_vale_inexistente_404(self, client):
        c, engine = client
        r = c.put("/cadastro/vales/9999", json={
            "pessoa_id": 1, "valor_total": 100.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
        })
        assert r.status_code == 404

    def test_atualiza_vale_reaplica_alerta_quarenta_por_cento(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=1000.0)  # limite = 400
        conta_id = _criar_conta_corrente(engine)
        vale = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        }).json()
        r = c.put(f"/cadastro/vales/{vale['id']}", json={
            "pessoa_id": pessoa_id, "valor_total": 500.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        })
        assert r.status_code == 409
        r2 = c.put(f"/cadastro/vales/{vale['id']}", json={
            "pessoa_id": pessoa_id, "valor_total": 500.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02", "confirmar": True,
            "conta_corrente_id": conta_id,
        })
        assert r2.status_code == 200

    def test_bloqueia_edicao_e_exclusao_de_vale_ja_pago(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        conta_id = _criar_conta_corrente(engine)
        vale = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        }).json()
        folha = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-02", "valor_bruto": 2000.0,
        }).json()
        c.put(f"/cadastro/folha-pagamento/{folha['id']}", json={
            "pessoa_id": pessoa_id, "competencia": "2026-02", "valor_bruto": 2000.0,
            "status": "pago", "data_pagamento": "2026-02-05",
        })

        r = c.put(f"/cadastro/vales/{vale['id']}", json={
            "pessoa_id": pessoa_id, "valor_total": 400.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        })
        assert r.status_code == 400

        r2 = c.delete(f"/cadastro/vales/{vale['id']}")
        assert r2.status_code == 400

    def test_exclui_vale_reverte_desconto_na_folha_nao_paga(self, client):
        c, engine = client
        pessoa_id = self._pessoa(c, salario_base=3000.0)
        conta_id = _criar_conta_corrente(engine)
        vale = c.post("/cadastro/vales", json={
            "pessoa_id": pessoa_id, "valor_total": 300.0, "forma_pagamento": "dinheiro",
            "data_pagamento": "2026-01-10", "parcelas": 1, "competencia_inicio": "2026-02",
            "conta_corrente_id": conta_id,
        }).json()
        folha = c.post("/cadastro/folha-pagamento", json={
            "pessoa_id": pessoa_id, "competencia": "2026-02", "valor_bruto": 2000.0,
        }).json()
        assert folha["valor_vale"] == 300.0

        # Guarda o número do lançamento do VALE antes de excluir — é ele que
        # tem de sumir do extrato. O lançamento da FOLHA é outro documento e
        # continua existindo, então não dá para checar "sobrou zero lançamento".
        with Session(engine) as s:
            from fazenda.models import ValeFuncionario
            numero_lancamento_vale = s.get(ValeFuncionario, vale["id"]).numero_lancamento_gerado
        assert numero_lancamento_vale, "vale pago em dinheiro deveria ter gerado lançamento"

        r = c.delete(f"/cadastro/vales/{vale['id']}")
        assert r.status_code == 200

        vales = c.get("/cadastro/vales").json()
        assert not any(v["id"] == vale["id"] for v in vales)

        folha2 = c.get("/cadastro/folha-pagamento").json()
        alvo = next(f for f in folha2 if f["id"] == folha["id"])
        assert alvo["valor_vale"] == 0.0
        assert alvo["valor_liquido"] == 2000.0

        # E o lançamento gerado para o vale some junto — sem órfão no extrato.
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            orfao = s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == numero_lancamento_vale)
            ).first()
            assert orfao is None

    def test_exclui_vale_inexistente_404(self, client):
        c, engine = client
        r = c.delete("/cadastro/vales/9999")
        assert r.status_code == 404


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
        assert len(principios) == 51
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

    def test_configurar_calendario_padrao_bota_brucelose_b19_no_cronograma(self, client):
        # Brucelose B19 é "por fase fisiológica" (gatilho=nascimento, sem
        # rastreio de rebanho) — deve entrar na lista de espera do cronograma
        # (usa_cronograma=True) em vez de virar pendência de "aplicar agora"
        # direto assim que a bezerra bate a idade.
        c, engine = client
        from fazenda.api.routers.cadastro import configurar_calendario_sanitario_padrao, seed_cadastro_sanitario
        from fazenda.rules.farmacia import bootstrap_farmacia
        from fazenda.models import CalendarioSanitario, EventoSanitario
        with Session(engine) as s:
            seed_cadastro_sanitario(s)
            bootstrap_farmacia(s)
            configurar_calendario_sanitario_padrao(s)
            ev = s.exec(select(EventoSanitario).where(EventoSanitario.nome == "Brucelose B19")).first()
            assert ev.sexo_alvo == "F"
            regra = s.exec(select(CalendarioSanitario).where(CalendarioSanitario.evento_sanitario_id == ev.id)).first()
            assert regra is not None
            assert regra.usa_cronograma is True

    def test_configurar_calendario_padrao_promove_regra_orfa_sem_cronograma(self, client):
        # Uma regra "comum" (usa_cronograma=False) pré-existente pra Brucelose
        # B19 é órfã de uma tentativa de cadastro manual que não conseguiu
        # marcar "usar cronograma sanitário" (bug do checkbox, já corrigido em
        # FormCalendarioSanitario.tsx) — o seed deve promovê-la no lugar de
        # ficar bloqueado pra sempre (bug relatado: bezerras aparecendo pra
        # "aplicar agora" + calendário atrasado de Brucelose B19, quando
        # deveriam entrar na lista de espera do cronograma).
        c, engine = client
        from fazenda.api.routers.cadastro import configurar_calendario_sanitario_padrao, seed_cadastro_sanitario
        from fazenda.rules.farmacia import bootstrap_farmacia
        from fazenda.models import CalendarioSanitario, EventoSanitario
        with Session(engine) as s:
            seed_cadastro_sanitario(s)
            bootstrap_farmacia(s)
            ev = s.exec(select(EventoSanitario).where(EventoSanitario.nome == "Brucelose B19")).first()
            # Simula uma regra já cadastrada manualmente pelo usuário, sem cronograma.
            s.add(CalendarioSanitario(
                evento_sanitario_id=ev.id, categoria_alvo="Bezerras", frequencia_valor=30,
                frequencia_unidade="dias", data_evento=date.today(), usa_cronograma=False,
            ))
            s.commit()
            configurar_calendario_sanitario_padrao(s)
            regras = s.exec(select(CalendarioSanitario).where(CalendarioSanitario.evento_sanitario_id == ev.id)).all()
            assert len(regras) == 1
            assert regras[0].usa_cronograma is True
            # A regra promovida preserva o que já estava cadastrado nela (não
            # é substituída pelos valores do seed).
            assert regras[0].categoria_alvo == "Bezerras"

    def test_configurar_calendario_padrao_nao_mexe_em_regra_ja_com_cronograma(self, client):
        c, engine = client
        from fazenda.api.routers.cadastro import configurar_calendario_sanitario_padrao, seed_cadastro_sanitario
        from fazenda.rules.farmacia import bootstrap_farmacia
        from fazenda.models import CalendarioSanitario, EventoSanitario
        with Session(engine) as s:
            seed_cadastro_sanitario(s)
            bootstrap_farmacia(s)
            ev = s.exec(select(EventoSanitario).where(EventoSanitario.nome == "Brucelose B19")).first()
            s.add(CalendarioSanitario(
                evento_sanitario_id=ev.id, categoria_alvo="Bezerras (customizado)", frequencia_valor=45,
                frequencia_unidade="dias", data_evento=date.today(), usa_cronograma=True,
            ))
            s.commit()
            configurar_calendario_sanitario_padrao(s)
            regras = s.exec(select(CalendarioSanitario).where(CalendarioSanitario.evento_sanitario_id == ev.id)).all()
            assert len(regras) == 1
            assert regras[0].categoria_alvo == "Bezerras (customizado)"
            assert regras[0].frequencia_valor == 45

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

    def test_principio_e_doenca_globais_do_painel_cowdata_aparecem_na_fazenda(self, client):
        """Pedido do usuário (01/09/2026): "cadastrei o princípio ativo
        Tulatromicina [no Painel CowData], e ele não aparece para seleção no
        tenant. Todo princípio ativo cadastrado no CowData deve virar
        padrão." Causa raiz: /cadastro/principios-ativos (e /cadastro/doencas)
        filtravam fazenda_id == própria, excluindo as linhas globais
        (fazenda_id nulo) do Painel CowData — corrigido com
        `global_compartilhado=True` (união via rules.visibilidade.visivel())."""
        c, engine = client
        from fazenda.api.routers.cadastro.sanitario import _listar_doencas, _listar_principios
        from fazenda.models import Doenca, PrincipioAtivo
        with Session(engine) as s:
            s.add(PrincipioAtivo(nome="Tulatromicina", fazenda_id=None))  # cadastrado no Painel CowData
            s.add(PrincipioAtivo(nome="Só desta fazenda", fazenda_id=99))  # de OUTRA fazenda — não pode vazar
            s.add(Doenca(nome="Mastite Global", tipo="doenca", fazenda_id=None))
            s.commit()

            nomes_pa = [p["nome"] for p in _listar_principios(session=s, fazenda_id=7)]
            assert "Tulatromicina" in nomes_pa
            assert "Só desta fazenda" not in nomes_pa

            nomes_doenca = [d["nome"] for d in _listar_doencas(session=s, fazenda_id=7)]
            assert "Mastite Global" in nomes_doenca


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
        assert dados["centro_custo"] == "Pecuária Leiteira"
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            contas = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Empreitada")).all()
            assert len(contas) == 2
            assert {c.valor_total for c in contas} == {1500.0}
            assert all(c.centro_custo == "Pecuária Leiteira" for c in contas)

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

    def test_pagamento_no_inicio_ou_fim_da_empreita_gera_1_parcela_na_data_informada(self, client):
        c, engine = client
        pessoa_id = self._empreiteiro(c)
        for tipo, data_pagamento in (("inicio_empreita", "2026-08-01"), ("fim_empreita", "2026-09-30")):
            r = c.post("/cadastro/empreitadas", json={
                "pessoa_id": pessoa_id, "descricao": "Roçagem pontual", "valor_total": 800.0,
                "tipo_pagamento": tipo,
                "parcelas": [{"data_vencimento": data_pagamento, "valor": 800.0}],
            })
            assert r.status_code == 200
            dados = r.json()
            assert len(dados["parcelas"]) == 1
            assert dados["parcelas"][0]["data_vencimento"] == data_pagamento
            assert dados["parcelas"][0]["valor"] == 800.0
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            contas = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Empreitada")).all()
            assert len(contas) == 2
            assert {c.valor_total for c in contas} == {800.0}

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
        assert dados["centro_custo"] == "Pecuária Leiteira"
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            contas = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Contrato")).all()
            assert all(c.centro_custo == "Pecuária Leiteira" for c in contas)

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
        assert dados["centro_custo"] == "Pecuária Leiteira"
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(ContaGerencial.tipo_documento == "Diária")).first()
            assert conta.centro_custo == "Pecuária Leiteira"

    def test_rejeita_valor_diaria_invalido(self, client):
        c, engine = client
        pessoa_id = self._diarista(c)
        r = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 0, "data_inicio": date.today().isoformat(),
        })
        assert r.status_code == 400

    def test_editar_diaria_ajusta_numero_manualmente(self, client):
        c, engine = client
        pessoa_id = self._diarista(c)
        inicio = date.today() - timedelta(days=9)  # 10 diárias corridas
        diaria_id = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": inicio.isoformat(),
        }).json()["id"]
        r = c.put(f"/cadastro/diarias/{diaria_id}", json={
            "data_inicio": inicio.isoformat(), "ajuste_numero_diarias": 6,
        })
        assert r.status_code == 200
        dados = r.json()
        # checkpoint do ajuste é "hoje" — soma 6 + 0 dias corridos desde então
        assert dados["numero_diarias"] == 6
        assert dados["total_ate_hoje"] == 600.0

    def test_data_fim_limita_contagem(self, client):
        c, engine = client
        pessoa_id = self._diarista(c)
        inicio = date.today() - timedelta(days=9)
        fim = date.today() - timedelta(days=5)  # encerrada há 5 dias -> para de contar em fim
        diaria_id = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": inicio.isoformat(), "data_fim": fim.isoformat(),
        }).json()["id"]
        dados = next(d for d in c.get("/cadastro/diarias").json() if d["id"] == diaria_id)
        assert dados["numero_diarias"] == 5
        assert dados["total_ate_hoje"] == 500.0

    def test_encerrar_diaria_some_da_listagem_padrao_e_volta_com_incluir_finalizadas(self, client):
        c, engine = client
        pessoa_id = self._diarista(c)
        diaria_id = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": date.today().isoformat(),
        }).json()["id"]

        r = c.put(f"/cadastro/diarias/{diaria_id}/encerrar")
        assert r.status_code == 200
        assert r.json()["status"] == "encerrado"

        ids_padrao = [d["id"] for d in c.get("/cadastro/diarias").json()]
        assert diaria_id not in ids_padrao

        ids_com_finalizadas = [d["id"] for d in c.get("/cadastro/diarias", params={"incluir_finalizadas": True}).json()]
        assert diaria_id in ids_com_finalizadas

    def test_encerrar_diaria_inexistente_da_404(self, client):
        c, engine = client
        r = c.put("/cadastro/diarias/999/encerrar")
        assert r.status_code == 404


class TestValeAvulso:
    def test_abate_proxima_parcela_de_empreitada(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Empreiteiro X", "tipos": ["Empreiteiro"]}).json()["id"]
        empreitada = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Roçagem", "valor_total": 3000.0, "tipo_pagamento": "mensal",
            "parcelas": [
                {"data_vencimento": "2026-08-05", "valor": 1500.0},
                {"data_vencimento": "2026-09-05", "valor": 1500.0},
            ],
        }).json()
        conta_id = _criar_conta_corrente(engine)
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 500.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-20", "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200
        dados = r.json()
        assert dados["vale"]["valor"] == 500.0
        parcelas = sorted(dados["origem"]["parcelas"], key=lambda p: p["data_vencimento"])
        assert parcelas[0]["valor"] == 1000.0  # 1500 - 500
        assert parcelas[1]["valor"] == 1500.0  # intacta
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == parcelas[0]["numero_lancamento_gerado"]
            )).first()
            assert conta.valor_total == 1000.0
            # O lançamento gerado para o VALE em si (saída de caixa imediata,
            # diferente da parcela abatida acima) também existe e já nasce pago.
            vale_conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == dados["vale"]["numero_lancamento_gerado"]
            )).first()
            assert vale_conta.valor_total == 500.0
            assert vale_conta.valor_pago == 500.0

    def test_abate_etapa_pendente_de_empreitada_por_etapa(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Empreiteiro Y", "tipos": ["Empreiteiro"]}).json()["id"]
        empreitada = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Cerca", "valor_total": 4000.0, "tipo_pagamento": "por_etapa",
            "etapas": [
                {"nome": "Etapa 1", "valor": 2000.0},
                {"nome": "Etapa 2", "valor": 2000.0},
            ],
        }).json()
        conta_id = _criar_conta_corrente(engine)
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 800.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-20", "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200
        etapas = sorted(r.json()["origem"]["etapas"], key=lambda e: e["ordem"])
        assert etapas[0]["valor"] == 1200.0  # 2000 - 800
        assert etapas[1]["valor"] == 2000.0

    def test_abate_proxima_parcela_de_contrato(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Prestador Z", "tipos": ["Prestador de serviços"]}).json()["id"]
        contrato = c.post("/cadastro/contratos", json={
            "pessoa_id": pessoa_id, "descricao": "Consultoria", "valor_total": 4000.0, "forma_pagamento": "mensal",
            "parcelas": [
                {"data_vencimento": "2026-08-10", "valor": 2000.0},
                {"data_vencimento": "2026-09-10", "valor": 2000.0},
            ],
        }).json()
        conta_id = _criar_conta_corrente(engine)
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "contrato", "origem_id": contrato["id"], "valor": 500.0,
            "forma_pagamento": "transferencia", "data_pagamento": "2026-07-20", "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200
        parcelas = sorted(r.json()["origem"]["parcelas"], key=lambda p: p["data_vencimento"])
        assert parcelas[0]["valor"] == 1500.0

    def test_reduz_saldo_devedor_de_diaria(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Diarista W", "tipos": ["Diarista"]}).json()["id"]
        inicio = date.today() - timedelta(days=4)  # 5 diárias
        diaria = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": inicio.isoformat(),
        }).json()
        conta_id = _criar_conta_corrente(engine)
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "diaria", "origem_id": diaria["id"], "valor": 200.0,
            "forma_pagamento": "dinheiro", "data_pagamento": date.today().isoformat(), "conta_corrente_id": conta_id,
        })
        assert r.status_code == 200
        dados = r.json()["origem"]
        assert dados["total_ate_hoje"] == 500.0
        assert dados["valor_vale"] == 200.0
        assert dados["saldo_devedor"] == 300.0


    def test_listar_vales_por_origem(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Diarista V", "tipos": ["Diarista"]}).json()["id"]
        diaria = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": date.today().isoformat(),
        }).json()
        conta_id = _criar_conta_corrente(engine)
        c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "diaria", "origem_id": diaria["id"], "valor": 50.0,
            "forma_pagamento": "dinheiro", "data_pagamento": date.today().isoformat(), "conta_corrente_id": conta_id,
        })
        r = c.get(f"/cadastro/vale-avulso?origem_tipo=diaria&origem_id={diaria['id']}")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["valor"] == 50.0

    def test_rejeita_origem_tipo_invalido(self, client):
        c, engine = client
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "funcionario", "origem_id": 1, "valor": 100.0,
            "forma_pagamento": "dinheiro", "data_pagamento": date.today().isoformat(),
        })
        assert r.status_code == 400

    def test_rejeita_origem_inexistente(self, client):
        c, engine = client
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "diaria", "origem_id": 999999, "valor": 100.0,
            "forma_pagamento": "dinheiro", "data_pagamento": date.today().isoformat(),
        })
        assert r.status_code == 404

    def test_rejeita_valor_nao_positivo(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Diarista U", "tipos": ["Diarista"]}).json()["id"]
        diaria = c.post("/cadastro/diarias", json={
            "pessoa_id": pessoa_id, "valor_diaria": 100.0, "data_inicio": date.today().isoformat(),
        }).json()
        r = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "diaria", "origem_id": diaria["id"], "valor": 0,
            "forma_pagamento": "dinheiro", "data_pagamento": date.today().isoformat(),
        })
        assert r.status_code == 400

    def test_listar_todos_aparece_no_relatorio_geral(self, client):
        # Reproduz o cenário relatado: vale de empreita lançado deve aparecer
        # no relatório geral de vales (GET /vale-avulso/todos), com descrição
        # de origem — antes desse endpoint existir, só aparecia filtrado por
        # origem_tipo/origem_id (ver test_listar_vales_por_origem).
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Empreiteiro Relatorio", "tipos": ["Empreiteiro"]}).json()["id"]
        empreitada = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Roçagem relatório", "valor_total": 3000.0, "tipo_pagamento": "mensal",
            "parcelas": [{"data_vencimento": "2026-08-05", "valor": 1500.0}, {"data_vencimento": "2026-09-05", "valor": 1500.0}],
        }).json()
        conta_id = _criar_conta_corrente(engine)
        c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 200.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_id,
        })
        r = c.get("/cadastro/vale-avulso/todos")
        assert r.status_code == 200
        vales = r.json()
        assert any(v["valor"] == 200.0 and v["pessoa_nome"] == "Empreiteiro Relatorio" and "Empreitada" in v["origem_descricao"] for v in vales)

    def test_editar_vale_avulso_reverte_e_reaplica(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Empreiteiro Edicao", "tipos": ["Empreiteiro"]}).json()["id"]
        empreitada = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Roçagem edição", "valor_total": 3000.0, "tipo_pagamento": "mensal",
            "parcelas": [{"data_vencimento": "2026-08-05", "valor": 1500.0}, {"data_vencimento": "2026-09-05", "valor": 1500.0}],
        }).json()
        conta_id = _criar_conta_corrente(engine)
        vale = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 200.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_id,
        }).json()["vale"]

        r = c.put(f"/cadastro/vale-avulso/{vale['id']}", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 500.0,
            "forma_pagamento": "pix", "data_pagamento": "2026-07-25", "observacao": "corrigido",
            "conta_corrente_id": conta_id,
            # valor mudou (200 -> 500): endpoint pede confirmação explícita
            # (409 sem isso) antes de reverter/reaplicar o abatimento.
            "confirmar": True,
        })
        assert r.status_code == 200
        assert r.json()["vale"]["valor"] == 500.0
        assert r.json()["vale"]["forma_pagamento"] == "pix"

        parcelas = c.get(f"/cadastro/empreitadas").json()
        empreitada_atualizada = next(e for e in parcelas if e["id"] == empreitada["id"])
        parcelas_ordenadas = sorted(empreitada_atualizada["parcelas"], key=lambda p: p["data_vencimento"])
        assert parcelas_ordenadas[0]["valor"] == 1000.0  # 1500 - 500 (não 1500-200-500)
        assert parcelas_ordenadas[1]["valor"] == 1500.0

        # O lançamento gerado para o vale em si também foi sincronizado.
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            vale_conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == r.json()["vale"]["numero_lancamento_gerado"]
            )).first()
        assert vale_conta.valor_total == 500.0
        assert vale_conta.forma_pagamento == "pix"

    def test_excluir_vale_avulso_reverte_valor(self, client):
        c, engine = client
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Empreiteiro Exclusao", "tipos": ["Empreiteiro"]}).json()["id"]
        empreitada = c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Roçagem exclusão", "valor_total": 3000.0, "tipo_pagamento": "mensal",
            "parcelas": [{"data_vencimento": "2026-08-05", "valor": 1500.0}, {"data_vencimento": "2026-09-05", "valor": 1500.0}],
        }).json()
        conta_id = _criar_conta_corrente(engine)
        vale = c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 200.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-24", "conta_corrente_id": conta_id,
        }).json()["vale"]
        assert vale["numero_lancamento_gerado"]

        r = c.delete(f"/cadastro/vale-avulso/{vale['id']}")
        assert r.status_code == 200
        assert r.json()["ok"] is True

        parcelas = c.get(f"/cadastro/empreitadas").json()
        empreitada_atualizada = next(e for e in parcelas if e["id"] == empreitada["id"])
        parcelas_ordenadas = sorted(empreitada_atualizada["parcelas"], key=lambda p: p["data_vencimento"])
        assert parcelas_ordenadas[0]["valor"] == 1500.0  # revertido integralmente

        r2 = c.get("/cadastro/vale-avulso/todos")
        assert all(v["id"] != vale["id"] for v in r2.json())

        # O lançamento gerado para o vale em si também foi removido — sem
        # órfão no extrato.
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            assert s.exec(
                select(ContaGerencial).where(ContaGerencial.numero_lancamento == vale["numero_lancamento_gerado"])
            ).first() is None


class TestEditarERedistribuirParcelas:
    def _empreitada(self, c):
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Empreiteiro Editor", "tipos": ["Empreiteiro"]}).json()["id"]
        return c.post("/cadastro/empreitadas", json={
            "pessoa_id": pessoa_id, "descricao": "Roçagem", "valor_total": 3000.0, "tipo_pagamento": "mensal",
            "parcelas": [
                {"data_vencimento": "2026-08-05", "valor": 1000.0},
                {"data_vencimento": "2026-09-05", "valor": 1000.0},
                {"data_vencimento": "2026-10-05", "valor": 1000.0},
            ],
        }).json()

    def _contrato(self, c):
        pessoa_id = c.post("/cadastro/pessoas", json={"nome": "Prestador Editor", "tipos": ["Prestador de serviços"]}).json()["id"]
        return c.post("/cadastro/contratos", json={
            "pessoa_id": pessoa_id, "descricao": "Consultoria", "valor_total": 3000.0, "forma_pagamento": "mensal",
            "parcelas": [
                {"data_vencimento": "2026-08-10", "valor": 1000.0},
                {"data_vencimento": "2026-09-10", "valor": 1000.0},
                {"data_vencimento": "2026-10-10", "valor": 1000.0},
            ],
        }).json()

    def _pagar_por_numero_lancamento(self, c, engine, numero_lancamento, valor):
        from fazenda.models import ContaGerencial
        with Session(engine) as s:
            conta_id = s.exec(select(ContaGerencial.id).where(ContaGerencial.numero_lancamento == numero_lancamento)).first()
        return c.put(f"/financeiro/lancamentos/{conta_id}/pagar", json={
            "data_pagamento": "2026-08-01", "valor_pago": valor, "forma_pagamento": "pix",
        })

    def test_edita_parcela_pendente_de_empreitada_e_sincroniza_conta(self, client):
        c, engine = client
        empreitada = self._empreitada(c)
        parcela = empreitada["parcelas"][0]
        r = c.put(f"/cadastro/empreitadas/parcelas/{parcela['id']}", json={
            "data_vencimento": "2026-08-15", "valor": 1234.56,
        })
        assert r.status_code == 200
        dados = r.json()
        editada = next(p for p in dados["parcelas"] if p["id"] == parcela["id"])
        assert editada["data_vencimento"] == "2026-08-15"
        assert editada["valor"] == 1234.56
        with Session(engine) as s:
            from fazenda.models import ContaGerencial
            conta = s.exec(select(ContaGerencial).where(
                ContaGerencial.numero_lancamento == editada["numero_lancamento_gerado"]
            )).first()
            assert conta.valor_total == 1234.56
            assert conta.data_vencimento.isoformat() == "2026-08-15"

    def test_edita_parcela_pendente_de_contrato(self, client):
        c, engine = client
        contrato = self._contrato(c)
        parcela = contrato["parcelas"][0]
        r = c.put(f"/cadastro/contratos/parcelas/{parcela['id']}", json={
            "data_vencimento": "2026-08-20", "valor": 777.0,
        })
        assert r.status_code == 200
        dados = r.json()
        editada = next(p for p in dados["parcelas"] if p["id"] == parcela["id"])
        assert editada["data_vencimento"] == "2026-08-20"
        assert editada["valor"] == 777.0

    def test_edita_parcela_rejeita_valor_nao_positivo(self, client):
        c, engine = client
        empreitada = self._empreitada(c)
        parcela = empreitada["parcelas"][0]
        r = c.put(f"/cadastro/empreitadas/parcelas/{parcela['id']}", json={
            "data_vencimento": "2026-08-15", "valor": 0,
        })
        assert r.status_code == 400

    def test_edita_parcela_ja_paga_e_bloqueada(self, client):
        c, engine = client
        empreitada = self._empreitada(c)
        parcela = empreitada["parcelas"][0]
        r = self._pagar_por_numero_lancamento(c, engine, parcela["numero_lancamento_gerado"], 1000.0)
        assert r.status_code == 200
        r = c.put(f"/cadastro/empreitadas/parcelas/{parcela['id']}", json={
            "data_vencimento": "2026-08-15", "valor": 500.0,
        })
        assert r.status_code == 400

    def test_redistribui_parcelas_pendentes_de_empreitada_preserva_total(self, client):
        c, engine = client
        empreitada = self._empreitada(c)
        parcelas = sorted(empreitada["parcelas"], key=lambda p: p["data_vencimento"])
        # Simula um vale que abateu desproporcionalmente a 1ª parcela.
        conta_id = _criar_conta_corrente(engine)
        c.post("/cadastro/vale-avulso", json={
            "origem_tipo": "empreitada", "origem_id": empreitada["id"], "valor": 700.0,
            "forma_pagamento": "dinheiro", "data_pagamento": "2026-07-20", "conta_corrente_id": conta_id,
        })
        r = c.post(f"/cadastro/empreitadas/{empreitada['id']}/parcelas/redistribuir")
        assert r.status_code == 200
        dados = r.json()
        novas = sorted(dados["parcelas"], key=lambda p: p["data_vencimento"])
        assert len(novas) == 3
        total = round(sum(p["valor"] for p in novas), 2)
        assert total == round(sum(p["valor"] for p in parcelas) - 700.0, 2)
        valores = [p["valor"] for p in novas]
        assert max(valores) - min(valores) < 0.02  # divisão igual (com resto na última)

    def test_redistribui_parcelas_pendentes_de_contrato(self, client):
        c, engine = client
        contrato = self._contrato(c)
        r = c.post(f"/cadastro/contratos/{contrato['id']}/parcelas/redistribuir")
        assert r.status_code == 200
        dados = r.json()
        valores = [p["valor"] for p in dados["parcelas"]]
        assert round(sum(valores), 2) == 3000.0
        assert max(valores) - min(valores) < 0.02

    def test_redistribuir_nao_toca_parcelas_ja_pagas(self, client):
        c, engine = client
        empreitada = self._empreitada(c)
        parcelas = sorted(empreitada["parcelas"], key=lambda p: p["data_vencimento"])
        paga = parcelas[0]
        self._pagar_por_numero_lancamento(c, engine, paga["numero_lancamento_gerado"], 1000.0)
        r = c.post(f"/cadastro/empreitadas/{empreitada['id']}/parcelas/redistribuir")
        assert r.status_code == 200
        dados = r.json()
        reencontrada_paga = next(p for p in dados["parcelas"] if p["id"] == paga["id"])
        assert reencontrada_paga["valor"] == 1000.0  # intocada
        pendentes = [p for p in dados["parcelas"] if p["id"] != paga["id"]]
        assert round(sum(p["valor"] for p in pendentes), 2) == 2000.0

    def test_redistribuir_com_menos_de_2_pendentes_da_erro(self, client):
        c, engine = client
        empreitada = self._empreitada(c)
        parcelas = sorted(empreitada["parcelas"], key=lambda p: p["data_vencimento"])
        for p in parcelas[:2]:
            self._pagar_por_numero_lancamento(c, engine, p["numero_lancamento_gerado"], p["valor"])
        r = c.post(f"/cadastro/empreitadas/{empreitada['id']}/parcelas/redistribuir")
        assert r.status_code == 400
