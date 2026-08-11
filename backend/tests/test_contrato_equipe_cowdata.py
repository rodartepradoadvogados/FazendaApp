"""
Contratos da Equipe CowData — "Baixar contrato" no Painel CowData gera a
minuta CLT ou a de prestação de serviços PJ conforme o `tipo_vinculo` do
cadastro de Pessoa. Ver fazenda/rules/contrato_equipe_render.py e o endpoint
GET /painel-cowdata/equipe/pessoas/{id}/contrato.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.auth import EMAIL_DONO, hash_senha
from fazenda.models import Fazenda, Pessoa, Usuario
from fazenda.models.multitenant import EmpresaOperadora
from fazenda.rules.contrato_equipe_render import por_extenso, render_contrato_equipe


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        # A fazenda "lógica" da CowData (eh_empresa_cowdata=True) é o que
        # ancora a Equipe — normalmente vem de seed_cowdata_empresa; aqui é
        # criada à mão para o teste não depender da ordem do seed.
        s.add(Fazenda(nome="CowData (empresa)", ativa=True, eh_empresa_cowdata=True))
        s.add(Fazenda(nome="Fazenda A", ativa=True, eh_empresa_cowdata=False))
        s.add(EmpresaOperadora(nome="CowData Tecnologia LTDA", cnpj="12.345.678/0001-90", endereco="Goiânia/GO"))
        s.add(Usuario(username="dono", nome="Jairo", senha_hash=hash_senha("123"), papel="admin", email=EMAIL_DONO))
        s.add(Usuario(username="comum", nome="Comum", senha_hash=hash_senha("123"), papel="admin", email="outro@x.com"))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _login(c, username="dono") -> str:
    r = c.post("/auth/login", json={"username": username, "senha": "123"})
    assert r.status_code == 200
    return r.json()["token"]


def _fazenda_cowdata_id(engine) -> int:
    with Session(engine) as s:
        return s.exec(select(Fazenda).where(Fazenda.eh_empresa_cowdata == True)).first().id  # noqa: E712


def _criar_pessoa(engine, **campos) -> int:
    """Grava direto no banco — o POST /equipe/pessoas exige cargo cadastrado,
    e aqui o que interessa é a geração do contrato, não o cadastro."""
    base = dict(fazenda_id=_fazenda_cowdata_id(engine), nome="Fulano de Tal", tipo="T.I.", ativo=True)
    base.update(campos)
    with Session(engine) as s:
        pessoa = Pessoa(**base)
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        return pessoa.id


def _pessoa(engine, pessoa_id: int) -> Pessoa:
    with Session(engine) as s:
        return s.get(Pessoa, pessoa_id)


# ---------------------------------------------------------------------------
# Escolha do contrato pelo vínculo
# ---------------------------------------------------------------------------
def test_funcionario_gera_contrato_clt(client):
    c, engine = client
    pid = _criar_pessoa(engine, tipo_vinculo="funcionario", salario_base=4500.0, data_admissao=date(2026, 3, 2))
    r = c.get(f"/painel-cowdata/equipe/pessoas/{pid}/contrato", headers={"Authorization": f"Bearer {_login(c)}"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.text
    assert "CONTRATO INDIVIDUAL DE TRABALHO POR PRAZO INDETERMINADO" in html
    assert "EMPREGADORA" in html
    assert "R$ 4.500,00" in html
    assert "02/03/2026" in html
    # O contrato de PJ não pode vazar para dentro do de CLT.
    assert "CONTRATADA" not in html


def test_pj_gera_contrato_de_prestacao_de_servicos(client):
    c, engine = client
    pid = _criar_pessoa(
        engine, nome="Fulano Serviços LTDA", tipo_vinculo="pj", subtipo_pj="ME",
        cpf_cnpj="11.222.333/0001-44", pagamento_mensal=7200.0,
    )
    r = c.get(f"/painel-cowdata/equipe/pessoas/{pid}/contrato", headers={"Authorization": f"Bearer {_login(c)}"})
    assert r.status_code == 200
    html = r.text
    assert "CONTRATO DE PRESTAÇÃO DE SERVIÇOS" in html
    assert "microempresa (ME)" in html
    assert "R$ 7.200,00" in html
    # A cláusula que afasta o vínculo é o núcleo deste contrato.
    assert "442-B" in html
    assert "EMPREGADORA" not in html


def test_sem_tipo_de_vinculo_recusa_em_vez_de_gerar_o_contrato_errado(client):
    c, engine = client
    pid = _criar_pessoa(engine, tipo_vinculo=None)
    r = c.get(f"/painel-cowdata/equipe/pessoas/{pid}/contrato", headers={"Authorization": f"Bearer {_login(c)}"})
    assert r.status_code == 400
    assert "vínculo" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Dados do cadastro dentro da minuta
# ---------------------------------------------------------------------------
def test_dados_do_cadastro_entram_na_qualificacao(client):
    c, engine = client
    pid = _criar_pessoa(
        engine, nome="Maria Souza", tipo_vinculo="funcionario", salario_base=3000.0,
        rg="1234567 SSP/GO", cpf_cnpj="123.456.789-00", estado_civil="Casado(a)",
        endereco_rua="Rua das Flores", endereco_numero="120", endereco_bairro="Centro",
        endereco_cidade="Goiânia", endereco_uf="GO", cep="74000-000",
    )
    html = c.get(f"/painel-cowdata/equipe/pessoas/{pid}/contrato", headers={"Authorization": f"Bearer {_login(c)}"}).text
    assert "Maria Souza" in html
    assert "1234567 SSP/GO" in html
    assert "123.456.789-00" in html
    assert "Casado(a)" in html
    assert "Rua das Flores, 120, Centro, Goiânia/GO, CEP 74000-000" in html
    # Foro/cidade da assinatura caem no endereço da pessoa quando não informados.
    assert "Goiânia" in html


def test_campo_ausente_sai_como_preencher_e_nao_quebra_a_minuta(client):
    c, engine = client
    pid = _criar_pessoa(engine, tipo_vinculo="funcionario")  # sem RG, CPF, endereço, salário
    r = c.get(f"/painel-cowdata/equipe/pessoas/{pid}/contrato", headers={"Authorization": f"Bearer {_login(c)}"})
    assert r.status_code == 200
    assert "[PREENCHER" in r.text


def test_genero_flexiona_o_contrato_clt(client):
    c, engine = client
    fem = _criar_pessoa(engine, nome="Ana", tipo_vinculo="funcionario", genero="feminino")
    masc = _criar_pessoa(engine, nome="Bruno", tipo_vinculo="funcionario", genero="masculino")
    sem = _criar_pessoa(engine, nome="Alex", tipo_vinculo="funcionario", genero=None)
    token = {"Authorization": f"Bearer {_login(c)}"}

    html_fem = c.get(f"/painel-cowdata/equipe/pessoas/{fem}/contrato", headers=token).text
    assert "EMPREGADA" in html_fem and "brasileira" in html_fem

    html_masc = c.get(f"/painel-cowdata/equipe/pessoas/{masc}/contrato", headers=token).text
    assert "EMPREGADO" in html_masc and "brasileiro," in html_masc

    # Gênero nunca é obrigatório — sem ele, o contrato usa a forma dupla.
    html_sem = c.get(f"/painel-cowdata/equipe/pessoas/{sem}/contrato", headers=token).text
    assert "EMPREGADO(A)" in html_sem


def test_query_sobrescreve_o_que_o_cadastro_nao_tem(client):
    c, engine = client
    pid = _criar_pessoa(engine, tipo_vinculo="funcionario", salario_base=2000.0)
    r = c.get(
        f"/painel-cowdata/equipe/pessoas/{pid}/contrato",
        params={"funcao": "Analista de Suporte", "local_prestacao": "sede da EMPREGADORA",
                "jornada_semanal": 40, "experiencia_dias": 45, "cidade_foro": "Goiânia", "estado_foro": "GO"},
        headers={"Authorization": f"Bearer {_login(c)}"},
    )
    html = r.text
    assert "Analista de Suporte" in html
    assert "sede da EMPREGADORA" in html
    assert "40\n(quarenta) horas semanais" in html or "quarenta) horas semanais" in html
    assert "quarenta e cinco) dias" in html


def test_nome_do_arquivo_identifica_o_tipo_de_contrato(client):
    c, engine = client
    clt = _criar_pessoa(engine, nome="José Antônio", tipo_vinculo="funcionario")
    pj = _criar_pessoa(engine, nome="Acme Serviços", tipo_vinculo="pj")
    token = {"Authorization": f"Bearer {_login(c)}"}

    r_clt = c.get(f"/painel-cowdata/equipe/pessoas/{clt}/contrato", headers=token)
    assert 'filename="contrato-clt-jose-antonio.html"' in r_clt.headers["content-disposition"]

    r_pj = c.get(f"/painel-cowdata/equipe/pessoas/{pj}/contrato", headers=token)
    assert 'filename="contrato-pj-acme-servicos.html"' in r_pj.headers["content-disposition"]


# ---------------------------------------------------------------------------
# Isolamento / autorização
# ---------------------------------------------------------------------------
def test_sem_area_equipe_e_bloqueado(client):
    c, engine = client
    pid = _criar_pessoa(engine, tipo_vinculo="funcionario")
    r = c.get(f"/painel-cowdata/equipe/pessoas/{pid}/contrato", headers={"Authorization": f"Bearer {_login(c, 'comum')}"})
    assert r.status_code == 403


def test_pessoa_de_fazenda_cliente_nao_e_membro_da_equipe(client):
    c, engine = client
    with Session(engine) as s:
        outra = s.exec(select(Fazenda).where(Fazenda.nome == "Fazenda A")).first()
        pessoa = Pessoa(fazenda_id=outra.id, nome="Peão da fazenda", tipo="Funcionário", tipo_vinculo="funcionario")
        s.add(pessoa)
        s.commit()
        s.refresh(pessoa)
        pid = pessoa.id
    r = c.get(f"/painel-cowdata/equipe/pessoas/{pid}/contrato", headers={"Authorization": f"Bearer {_login(c)}"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Regras puras
# ---------------------------------------------------------------------------
def test_por_extenso():
    assert por_extenso(0) == "zero"
    assert por_extenso(8) == "oito"
    assert por_extenso(15) == "quinze"
    assert por_extenso(40) == "quarenta"
    assert por_extenso(44) == "quarenta e quatro"
    assert por_extenso(90) == "noventa"
    assert por_extenso(100) == "cem"
    assert por_extenso(120) == "cento e vinte"
    assert por_extenso(365) == "trezentos e sessenta e cinco"


def test_render_sem_empresa_operadora_ainda_gera_a_minuta(client):
    """A EmpresaOperadora nasce sem CNPJ (ver o modelo) e pode nem existir em
    instalação nova — o contrato tem que sair mesmo assim, com [PREENCHER]."""
    c, engine = client
    pid = _criar_pessoa(engine, tipo_vinculo="pj", pagamento_mensal=1000.0)
    html = render_contrato_equipe(_pessoa(engine, pid), None)
    assert "CowData" in html
    assert "[PREENCHER — CNPJ da CowData]" in html


def test_documento_com_11_digitos_e_rotulado_cpf_no_contrato_pj(client):
    """MEI cadastrado com CPF no lugar do CNPJ não pode sair rotulado como
    CNPJ na qualificação — o rótulo vem do próprio número."""
    c, engine = client
    pid = _criar_pessoa(engine, tipo_vinculo="pj", subtipo_pj="MEI", cpf_cnpj="123.456.789-00", pagamento_mensal=1000.0)
    html = render_contrato_equipe(_pessoa(engine, pid), None)
    assert "inscrita no CPF sob o nº" in html
    assert "microempreendedor individual (MEI)" in html
