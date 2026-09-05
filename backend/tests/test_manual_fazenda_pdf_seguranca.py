"""
Injeção de HTML no PDF do Manual da Fazenda (fazenda/rules/manual_fazenda_pdf.py)
→ SSRF via xhtml2pdf (F-E-02, CWE-918 via CWE-80).

BUG DE SEGURANÇA CORRIGIDO: nome de item de estoque, protocolo/animal do
calendário sanitário, sugestão cadastrada pelo usuário e responsável pelo
manejo reprodutivo entravam CRUS nas f-strings de HTML do Manual — sem
`html.escape` nenhum. Como `gerar_pdf_manual` chamava `pisa.CreatePDF` sem
`link_callback`, um `<img src="http://...">` injetado por qualquer um destes
campos virava uma requisição HTTP de verdade do backend (metadata da cloud,
rede interna do Railway) quando alguém baixava o PDF.

Este arquivo prova as duas camadas da correção:
  1. `_esc()` — o texto malicioso sai NEUTRALIZADO (tags viram texto literal).
  2. `_bloquear_recursos_externos` (link_callback) — mesmo que uma tag real
     chegasse ao xhtml2pdf, ele nunca chegaria a abrir uma conexão de rede.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import Estoque, SugestaoManualFazenda
from fazenda.rules.manual_fazenda_pdf import _bloquear_recursos_externos, _html_manual, gerar_pdf_manual

PAYLOAD_SSRF = '<img src="http://169.254.169.254/computeMetadata/v1/">'


# ---------------------------------------------------------------------------
# Camada 1 — escape: o HTML montado nunca contém uma tag nova vinda de dado
# do usuário, só a versão escapada dela.
# ---------------------------------------------------------------------------
class TestEscapeNoTemplate:
    def _manual_malicioso(self) -> dict:
        return {
            "responsavel_manejo": {"nome": f"Dr. {PAYLOAD_SSRF}", "empresa": PAYLOAD_SSRF},
            "rotina": {
                "bst": None,
                "visita_reprodutiva": {"titulo": f"Visita {PAYLOAD_SSRF}", "proximas_datas": []},
                "sanitario": {
                    "titulo": "Calendário sanitário preventivo",
                    "vencidas": 1,
                    "proxima": {"protocolo": PAYLOAD_SSRF, "animal": PAYLOAD_SSRF, "data": "2026-01-01"},
                },
                "compras": [{"nome": PAYLOAD_SSRF, "quantidade": 1, "estoque_minimo": 10}],
            },
            "resultado": {},
            "insights": [{
                "categoria": PAYLOAD_SSRF, "tendencia": "queda", "texto": PAYLOAD_SSRF,
            }],
            "sugestoes": [{"texto": PAYLOAD_SSRF, "categoria": "geral", "origem": "usuario"}],
        }

    def test_html_gerado_nao_contem_a_tag_maliciosa_crua(self):
        html_gerado = _html_manual(self._manual_malicioso())
        # O ponto central do achado: o <img> injetado NUNCA pode aparecer
        # como tag de verdade no HTML entregue ao xhtml2pdf.
        assert "<img src=\"http://169.254.169.254" not in html_gerado
        # E precisa aparecer neutralizado (texto literal) em cada um dos
        # pontos de injeção (compras, sanitário, insights, sugestões,
        # responsável) — prova que _esc() foi realmente aplicado em todos.
        assert html_gerado.count("&lt;img src=&quot;http://169.254.169.254") >= 6

    def test_compras_com_nome_malicioso_sai_escapado(self):
        from fazenda.rules.manual_fazenda_pdf import _bloco_rotina
        rotina = {"compras": [{"nome": PAYLOAD_SSRF, "quantidade": 1, "estoque_minimo": 10}]}
        out = _bloco_rotina(rotina)
        assert "<img" not in out
        assert "&lt;img" in out

    def test_sugestao_com_texto_malicioso_sai_escapada(self):
        from fazenda.rules.manual_fazenda_pdf import _bloco_sugestoes
        out = _bloco_sugestoes([{"texto": PAYLOAD_SSRF, "categoria": "geral", "origem": "usuario"}])
        assert "<img" not in out
        assert "&lt;img" in out


# ---------------------------------------------------------------------------
# Camada 2 — link_callback: mesmo que uma tag real chegasse ao xhtml2pdf,
# nenhuma conexão de rede é aberta.
# ---------------------------------------------------------------------------
class TestLinkCallbackBloqueiaRede:
    def test_callback_devolve_data_uri_invalido_para_qualquer_uri(self):
        # Não pode devolver None (isso faria o xhtml2pdf seguir com a URI
        # original — ver docstring de _bloquear_recursos_externos).
        assert _bloquear_recursos_externos("http://169.254.169.254/x", None) == "data:,"
        assert _bloquear_recursos_externos("http://qualquer-coisa.com/x.png", "/base") == "data:,"

    def test_gerar_pdf_manual_nunca_abre_conexao_de_rede_mesmo_com_img_no_html(self, monkeypatch):
        """Simula o pior cenário (escape falhou por algum motivo futuro): um
        <img src="http://..."> chega cru ao xhtml2pdf. Mesmo assim, nenhuma
        conexão HTTP pode ser aberta — é o que o link_callback garante."""
        from xhtml2pdf.files import NetworkFileUri

        chamadas = []
        monkeypatch.setattr(
            NetworkFileUri, "get_httplib",
            lambda self, uri: (chamadas.append(uri), (None, False))[1],
        )

        manual = {
            "responsavel_manejo": {},
            "rotina": {"bst": None, "visita_reprodutiva": None, "sanitario": {}, "compras": []},
            "resultado": {},
            "insights": [],
            "sugestoes": [],
        }
        html_com_img_cru = _html_manual(manual).replace(
            "</body>", '<img src="http://169.254.169.254/computeMetadata/v1/" /></body>',
        )
        from io import BytesIO
        from xhtml2pdf import pisa
        buffer = BytesIO()
        pisa.CreatePDF(html_com_img_cru, dest=buffer, link_callback=_bloquear_recursos_externos)

        assert chamadas == []  # nenhuma requisição de rede foi feita
        assert buffer.getvalue()[:4] == b"%PDF"  # e o PDF ainda saiu (falha graciosa)


# ---------------------------------------------------------------------------
# Fim a fim: exatamente o PoC do achado (Estoque.nome malicioso → PDF).
# ---------------------------------------------------------------------------
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


class TestPoCFimAFim:
    def test_item_de_estoque_com_img_malicioso_nao_dispara_requisicao_ao_baixar_pdf(self, client, monkeypatch):
        from xhtml2pdf.files import NetworkFileUri

        chamadas = []
        monkeypatch.setattr(
            NetworkFileUri, "get_httplib",
            lambda self, uri: (chamadas.append(uri), (None, False))[1],
        )

        c, engine = client
        with Session(engine) as s:
            # Exatamente o PoC do achado: nome de item de estoque com <img>
            # apontando pro metadata da cloud, abaixo do mínimo (entra no
            # bloco "Compras recorrentes" do Manual).
            s.add(Estoque(nome=f"Ração {PAYLOAD_SSRF}", quantidade=0, estoque_minimo=10, estocavel=True))
            s.commit()

        r = c.get("/manual-fazenda/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:4] == b"%PDF"
        assert chamadas == []  # o backend NUNCA tentou buscar o recurso injetado

    def test_sugestao_cadastrada_pelo_usuario_com_img_malicioso_nao_dispara_requisicao(self, client, monkeypatch):
        from xhtml2pdf.files import NetworkFileUri

        chamadas = []
        monkeypatch.setattr(
            NetworkFileUri, "get_httplib",
            lambda self, uri: (chamadas.append(uri), (None, False))[1],
        )

        c, engine = client
        with Session(engine) as s:
            s.add(SugestaoManualFazenda(texto=PAYLOAD_SSRF, categoria="geral", ativo=True, ordem=1))
            s.commit()

        r = c.get("/manual-fazenda/pdf")
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"
        assert chamadas == []
