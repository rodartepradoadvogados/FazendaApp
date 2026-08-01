"""
Testes da leitura automática de nota fiscal/recibo (PDF/JPEG/PNG) via IA.
Nunca chama a API de verdade — sempre com o cliente Anthropic mockado.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial, Fornecedor
from fazenda.rules.leitura_documento import MIME_ACEITOS, MODEL, ler_documento


def _resposta_mock(payload: dict, stop_reason: str = "end_turn"):
    bloco = MagicMock()
    bloco.type = "text"
    bloco.text = json.dumps(payload)
    resposta = MagicMock()
    resposta.content = [bloco]
    resposta.stop_reason = stop_reason
    return resposta


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


class TestLerDocumento:
    def test_sem_chave_de_api_retorna_503(self, client, monkeypatch):
        c, engine = client
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        r = c.post("/financeiro/ler-documento", files={"file": ("nota.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 503
        assert "ANTHROPIC_API_KEY" in r.json()["detail"]

    def test_tipo_de_arquivo_nao_suportado(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        r = c.post("/financeiro/ler-documento", files={"file": ("nota.txt", b"oi", "text/plain")})
        assert r.status_code == 400

    def test_extrai_nota_fiscal(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        payload = {
            "tipo_documento": "nota_fiscal", "fornecedor_cliente": "Agropecuária Central",
            "numero_documento": "1234", "data_emissao": "2026-07-01", "data_pagamento": None,
            "valor_total": 1500.0, "conta_bancaria": None,
            "itens": [{"produto": "Ração concentrada", "quantidade": 500, "valor_unitario": 3.0, "valor_total": 1500.0}],
            "observacao": None,
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(payload)
            r = c.post("/financeiro/ler-documento", files={"file": ("nota.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 200
        d = r.json()
        assert d["tipo_documento"] == "nota_fiscal"
        assert d["fornecedor_cliente"] == "Agropecuária Central"
        assert d["itens"][0]["produto"] == "Ração concentrada"

    def test_extrai_recibo(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        payload = {
            "tipo_documento": "recibo", "fornecedor_cliente": "João da Silva",
            "numero_documento": None, "data_emissao": None, "data_pagamento": "2026-07-05",
            "valor_total": 300.0, "conta_bancaria": "Banco do Brasil ag 3775-3 cc 3.615-3",
            "itens": [], "observacao": "PIX enviado",
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(payload)
            r = c.post("/financeiro/ler-documento", files={"file": ("recibo.jpg", b"\xff\xd8\xff", "image/jpeg")})
        assert r.status_code == 200
        d = r.json()
        assert d["tipo_documento"] == "recibo"
        assert d["data_pagamento"] == "2026-07-05"

    def test_extrai_boleto_parcelado(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        payload = {
            "tipo_documento": "boleto", "fornecedor_cliente": "Cooperativa Agro",
            "numero_documento": "00001-2", "data_emissao": None, "data_pagamento": None,
            "valor_total": 850.0, "conta_bancaria": None, "itens": [], "observacao": None,
            "parcela_num": 2, "parcela_total": 6, "linha_digitavel": "12345.67890 12345.678901 12345.678901 1 12340000085000",
            "data_vencimento": "2026-08-10",
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(payload)
            r = c.post("/financeiro/ler-documento", files={"file": ("boleto.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 200
        d = r.json()
        assert d["tipo_documento"] == "boleto"
        assert d["parcela_num"] == 2
        assert d["parcela_total"] == 6
        assert d["data_vencimento"] == "2026-08-10"

    def test_recusa_da_ia_vira_erro_400(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock({}, stop_reason="refusal")
            r = c.post("/financeiro/ler-documento", files={"file": ("nota.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 400

    def test_boleto_multiplas_paginas_corrige_valor_total_para_a_soma(self, client, monkeypatch):
        """Reproduz o bug relatado: um PDF de 8 páginas, uma parcela de
        R$586,25 por página — a IA devolveu valor_total=586.25 (valor de
        1 parcela) em vez de 4690.00 (a soma das 8). O servidor precisa
        corrigir isso a partir de `parcelas_detectadas`, sem depender só do
        que a IA disse em `valor_total`."""
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        payload = {
            "tipo_documento": "boleto", "fornecedor_cliente": "Cooperativa Agro",
            "numero_documento": "00001-2", "data_emissao": None, "data_pagamento": None,
            "valor_total": 586.25,  # <- exatamente o bug: valor de 1 parcela, não a soma
            "conta_bancaria": None, "itens": [], "observacao": None,
            "parcela_num": 1, "parcela_total": 8, "linha_digitavel": "12340000058625",
            "data_vencimento": "2026-08-10",
            "parcelas_detectadas": [
                {"numero": i, "valor": 586.25, "data_vencimento": f"2026-{7 + i:02d}-10", "linha_digitavel": f"1234000005862{i}"}
                for i in range(1, 9)
            ],
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(payload)
            r = c.post("/financeiro/ler-documento", files={"file": ("boleto8x.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 200
        d = r.json()
        assert d["valor_total"] == 4690.0
        assert d["valor_total_corrigido"] is True
        assert len(d["parcelas_detectadas"]) == 8
        assert d["parcelas_detectadas"][0]["valor"] == 586.25

    def test_boleto_uma_parcela_nao_mexe_no_valor_total(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        payload = {
            "tipo_documento": "boleto", "fornecedor_cliente": "Fornecedor X",
            "numero_documento": "999", "data_emissao": None, "data_pagamento": None,
            "valor_total": 1200.0, "conta_bancaria": None, "itens": [], "observacao": None,
            "parcela_num": None, "parcela_total": None, "linha_digitavel": "12340000012000",
            "data_vencimento": "2026-08-10",
            "parcelas_detectadas": [{"numero": 1, "valor": 1200.0, "data_vencimento": "2026-08-10", "linha_digitavel": "12340000012000"}],
        }
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(payload)
            r = c.post("/financeiro/ler-documento", files={"file": ("boleto_unico.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 200
        d = r.json()
        assert d["valor_total"] == 1200.0
        assert "valor_total_corrigido" not in d


_PAYLOAD_MINIMO = {
    "tipo_documento": "nota_fiscal", "fornecedor_cliente": "Fornecedor Teste",
    "numero_documento": "1", "data_emissao": "2026-07-01", "data_pagamento": None,
    "valor_total": 10.0, "conta_bancaria": None, "itens": [], "observacao": None,
    "parcela_num": None, "parcela_total": None, "linha_digitavel": None,
    "data_vencimento": None, "parcelas_detectadas": [],
}


class TestLerDocumentoUnitario:
    """Testa `ler_documento` diretamente (sem passar pelo endpoint/router),
    sempre com o cliente Anthropic mockado — nunca chama a API de verdade."""

    def test_usa_o_modelo_correto(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(_PAYLOAD_MINIMO)
            ler_documento(b"%PDF-1.4", "application/pdf")
            _, kwargs = MockAnthropic.return_value.messages.create.call_args
            assert kwargs["model"] == MODEL
            # Regressão do bug: "claude-opus-4-8" não é um ID de modelo válido.
            assert kwargs["model"] != "claude-opus-4-8"

    def test_aceita_image_jpg_e_normaliza_para_image_jpeg(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        assert "image/jpg" in MIME_ACEITOS
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(_PAYLOAD_MINIMO)
            ler_documento(b"\xff\xd8\xff", "image/jpg")
            _, kwargs = MockAnthropic.return_value.messages.create.call_args
            bloco_imagem = kwargs["messages"][0]["content"][0]
            assert bloco_imagem["source"]["media_type"] == "image/jpeg"

    def test_heic_e_aceito_no_upload_mas_da_erro_claro_e_acionavel(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        assert "image/heic" in MIME_ACEITOS
        with pytest.raises(ValueError) as exc_info:
            ler_documento(b"fake-heic-bytes", "image/heic")
        mensagem = str(exc_info.value)
        assert "HEIC" in mensagem
        assert "JPEG" in mensagem or "PDF" in mensagem

    def test_heif_tambem_da_erro_claro(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        with pytest.raises(ValueError, match="HEIF"):
            ler_documento(b"fake-heif-bytes", "image/heif")

    def test_heic_nunca_chega_a_chamar_a_api(self, monkeypatch):
        # O erro tem que ser levantado antes de tentar mandar pro Claude —
        # não pode "falhar de forma obscura" lá na API.
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        with patch("anthropic.Anthropic") as MockAnthropic:
            with pytest.raises(ValueError):
                ler_documento(b"fake-heic-bytes", "image/heic")
            MockAnthropic.return_value.messages.create.assert_not_called()


class TestSugestoesCadastroNoEndpoint:
    """O endpoint /financeiro/ler-documento já devolve, junto dos campos
    extraídos, as sugestões de casamento com o cadastro (fornecedor/produto/
    serviço parecidos) — ver fazenda.rules.sugestao_documento."""

    def test_fornecedor_parecido_aparece_em_sugestoes_cadastro(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        with Session(engine) as s:
            s.add(Fornecedor(nome="Agropecuária São José", tipo="fornecedor"))
            s.commit()
        payload = {**_PAYLOAD_MINIMO, "fornecedor_cliente": "Agropecuaria Sao Jose Norte"}
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(payload)
            r = c.post("/financeiro/ler-documento", files={"file": ("nota.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 200
        sug = r.json()["sugestoes_cadastro"]
        assert sug["fornecedor"]["candidato"] == "Agropecuária São José"
        assert sug["fornecedor"]["confianca"] == "provavel"

    def test_sem_nenhum_cadastro_parecido_sugestoes_ficam_vazias(self, client, monkeypatch):
        c, engine = client
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
        with patch("anthropic.Anthropic") as MockAnthropic:
            MockAnthropic.return_value.messages.create.return_value = _resposta_mock(_PAYLOAD_MINIMO)
            r = c.post("/financeiro/ler-documento", files={"file": ("nota.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 200
        assert r.json()["sugestoes_cadastro"] == {"fornecedor": None, "itens": []}
