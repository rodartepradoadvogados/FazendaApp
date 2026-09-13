"""Testes do Manual da Fazenda: parâmetros, CRUD de sugestões, montagem do
manual (rotina/resultado/insights/sugestões), geração do PDF e envio semanal."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Animal, ControleLeiteiro, Estoque, ParametroManualFazenda, Parto, Sanidade, Servico, Usuario
from fazenda.rules.manual_fazenda import (
    _insights, deve_enviar_manual_semanal, emails_administradores_fazenda, enviar_manual_semanal_se_necessario,
)


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


def test_parametros_get_or_create_e_atualiza(client):
    c, engine = client
    r = c.get("/manual-fazenda/parametros")
    assert r.status_code == 200
    assert r.json()["email_semanal_ativo"] is False

    r = c.put("/manual-fazenda/parametros", json={
        "email_semanal_ativo": True, "responsavel_manejo_nome": "Dr. Carlos Mendes",
        "responsavel_manejo_empresa": "VetRepro", "tem_contrato_manejo": True,
    })
    assert r.status_code == 200
    dados = r.json()
    assert dados["email_semanal_ativo"] is True
    assert dados["responsavel_manejo_nome"] == "Dr. Carlos Mendes"

    r = c.get("/manual-fazenda/parametros")
    assert r.json()["responsavel_manejo_empresa"] == "VetRepro"


def test_sugestoes_crud(client):
    c, engine = client
    r = c.post("/manual-fazenda/sugestoes", json={"texto": "Revisar dieta do lote 3", "categoria": "producao"})
    assert r.status_code == 200
    sugestao_id = r.json()["id"]

    r = c.get("/manual-fazenda/sugestoes")
    assert len(r.json()) == 1

    r = c.put(f"/manual-fazenda/sugestoes/{sugestao_id}", json={"texto": "Revisar dieta do lote 3 (urgente)", "categoria": "producao", "ativo": True, "ordem": 1})
    assert r.status_code == 200
    assert r.json()["texto"] == "Revisar dieta do lote 3 (urgente)"

    r = c.delete(f"/manual-fazenda/sugestoes/{sugestao_id}")
    assert r.status_code == 200
    assert c.get("/manual-fazenda/sugestoes").json() == []


def test_sugestao_vazia_rejeitada(client):
    c, engine = client
    r = c.post("/manual-fazenda/sugestoes", json={"texto": "   "})
    assert r.status_code == 400


def test_manual_monta_rotina_resultado_insights_sugestoes(client):
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        s.add(Animal(numero="1", sexo="F", ativo=True, del_dias=60, sit_rep="Ges."))
        s.add(Parto(numero_matriz="1", data_parto=hoje - timedelta(days=100), ordem_parto=1))
        s.add(Servico(numero_matriz="1", data_servico=hoje - timedelta(days=5), ordem_tentativa=1, diagnostico="POSITIVO"))
        s.add(Sanidade(numero_matriz="1", produto="Boostin", data_aplicacao=hoje - timedelta(days=8), atividade="BST"))
        s.add(Estoque(nome="Silagem", quantidade=10, estoque_minimo=50, estocavel=True))
        s.commit()
    c.post("/manual-fazenda/sugestoes", json={"texto": "Sugestão manual de teste"})

    r = c.get("/manual-fazenda/")
    assert r.status_code == 200
    manual = r.json()
    assert manual["rotina"]["bst"] is not None
    assert manual["rotina"]["bst"]["proximas_datas"][0] is not None
    assert manual["rotina"]["visita_reprodutiva"] is not None
    assert len(manual["rotina"]["compras"]) == 1
    assert manual["resultado"]["total_animais"] == 1
    assert any(s["texto"] == "Sugestão manual de teste" for s in manual["sugestoes"])
    # Estoque abaixo do mínimo deve gerar sugestão automática.
    assert any("Silagem" in s["texto"] for s in manual["sugestoes"])


def test_insights_nao_gera_queda_de_concepcao_por_mes_incompleto(client):
    """Reproduz e prova a correção do bug relatado: o mês corrente, cuja
    janela de DG (R7) ainda não fechou, tem que sair da comparação de
    `_insights`. Sem isto, o mês corrente — quase sem diagnóstico por
    definição, e enviesado para os poucos resultados que resolvem rápido
    (aqui, um NEGATIVO precoce) — inventa uma "queda de concepção" que é só
    falta de tempo, e vira sugestão automática de revisar o manejo com o
    responsável técnico."""
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        # 5 meses maduros, bem no passado (2020, longe de qualquer "hoje" real
        # de execução do teste) — histórico estável em 50% de concepção.
        for mes in range(1, 6):
            data = date(2020, mes, 5)
            s.add(Servico(numero_matriz=f"m{mes}-1", data_servico=data, diagnostico="POSITIVO"))
            s.add(Servico(numero_matriz=f"m{mes}-2", data_servico=data + timedelta(days=1), diagnostico="NEGATIVO"))
        # Mês corrente: um único serviço, já resolvido (rápido) como NEGATIVO.
        # A vaca que vai dar positivo nesse mês ainda nem teve tempo de
        # confirmar — é exatamente a amostra pequena e enviesada do relato.
        s.add(Servico(numero_matriz="atual-1", data_servico=hoje, diagnostico="NEGATIVO"))
        s.commit()

    with Session(engine) as s:
        insights = _insights(s, None)

    quedas_concepcao = [i for i in insights if i["metrica"] == "Taxa de concepção" and i["tendencia"] == "queda"]
    assert quedas_concepcao == []


def test_insights_gera_queda_normalmente_para_metrica_sem_dependencia_de_dg(client):
    """Nem toda métrica de METRICAS_INSIGHT depende de diagnóstico — só
    `taxa_concepcao` (ver METRICAS_DEPENDEM_DE_DG). `producao_leite` continua
    comparando o mês corrente normalmente; a correção do R7 não pode virar
    "nunca comparar o mês corrente com nada"."""
    c, engine = client
    hoje = date.today()
    with Session(engine) as s:
        for mes in range(1, 4):
            s.add(ControleLeiteiro(numero_matriz=f"m{mes}", data_controle=date(2020, mes, 5), producao_kg=30.0))
        for mes in range(4, 6):
            s.add(ControleLeiteiro(numero_matriz=f"m{mes}", data_controle=date(2020, mes, 5), producao_kg=15.0))
        s.add(ControleLeiteiro(numero_matriz="atual", data_controle=hoje, producao_kg=15.0))
        s.commit()

    with Session(engine) as s:
        insights = _insights(s, None)

    producao = [i for i in insights if i["metrica"] == "Produção de leite (média)"]
    assert len(producao) == 1
    assert producao[0]["tendencia"] == "queda"


def test_pdf_gera_arquivo_binario(client):
    c, engine = client
    r = c.get("/manual-fazenda/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_contrato_anexo_placeholder(client):
    c, engine = client
    r = c.post("/manual-fazenda/contrato-anexo", files={"arquivo": ("contrato.pdf", b"conteudo", "application/pdf")})
    assert r.status_code == 200
    # Nome estruturado (chave de storage pronta pro Supabase), não o nome
    # bruto que o navegador manda — ver fazenda/api/routers/manual_fazenda.py.
    nome = r.json()["contrato_manejo_arquivo_nome"]
    assert nome == f"contrato-manejo-reprodutivo-fazenda1-{date.today().isoformat()}.pdf"


def test_contrato_anexo_preserva_extensao_do_arquivo(client):
    c, engine = client
    r = c.post("/manual-fazenda/contrato-anexo", files={"arquivo": ("contrato assinado.docx", b"conteudo", "application/octet-stream")})
    assert r.status_code == 200
    assert r.json()["contrato_manejo_arquivo_nome"].endswith(".docx")


class TestEnvioSemanal:
    def test_deve_enviar_so_segunda_apos_7h_uma_vez_por_semana(self):
        p = ParametroManualFazenda(email_semanal_ativo=True)
        segunda_7h = datetime(2026, 7, 27, 7, 0)  # 27/07/2026 é uma segunda-feira
        assert segunda_7h.weekday() == 0
        assert deve_enviar_manual_semanal(p, segunda_7h) is True
        assert deve_enviar_manual_semanal(p, segunda_7h.replace(hour=6)) is False
        assert deve_enviar_manual_semanal(p, segunda_7h + timedelta(days=1)) is False

        p_desligado = ParametroManualFazenda(email_semanal_ativo=False)
        assert deve_enviar_manual_semanal(p_desligado, segunda_7h) is False

        p.ultimo_envio_semanal_em = segunda_7h
        assert deve_enviar_manual_semanal(p, segunda_7h.replace(hour=10)) is False  # já enviou nesta semana ISO
        assert deve_enviar_manual_semanal(p, segunda_7h + timedelta(days=7)) is True  # semana seguinte

    def test_envio_desligado_nao_envia(self, client):
        c, engine = client
        segunda_7h = datetime(2026, 7, 27, 7, 0)
        with Session(engine) as s:
            enviado = enviar_manual_semanal_se_necessario(s, fazenda_id=None, agora=segunda_7h)
        assert enviado is False  # email_semanal_ativo começa desligado por padrão

    def test_envio_ligado_sem_resend_configurado_nao_derruba(self, client, monkeypatch):
        """Com um admin com e-mail cadastrado, envio ligado, segunda-feira
        depois das 7h e sem RESEND_API_KEY configurada, o erro deve ser
        capturado (retorna False) em vez de propagar exceção."""
        c, engine = client
        c.put("/manual-fazenda/parametros", json={"email_semanal_ativo": True})
        monkeypatch.setattr("fazenda.config.settings.resend_api_key", "")
        segunda_7h = datetime(2026, 7, 27, 7, 0)
        with Session(engine) as s:
            s.add(Usuario(username="admin2", senha_hash="x", papel="admin", ativo=True, email="admin@fazenda.com"))
            s.commit()
            assert emails_administradores_fazenda(s, None) == ["admin@fazenda.com"]
            enviado = enviar_manual_semanal_se_necessario(s, fazenda_id=None, agora=segunda_7h)
        assert enviado is False
