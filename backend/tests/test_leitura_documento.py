"""
Testes da leitura automática de documento financeiro (nota fiscal, recibo,
boleto, guia FGTS, guia DCTF) via OCR (Tesseract) + regras/regex.

Nunca chama o binário do Tesseract de verdade — sempre mocka
`pytesseract.image_to_string` (e, pra PDF, `pdf2image.convert_from_bytes`)
devolvendo um texto OCR simulado, e verifica se o parser por regex extrai os
campos certos a partir dele. Esse é o mesmo padrão que os testes anteriores
usavam pra mockar a chamada à API da Claude — só que agora mockando o OCR.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.database as database
from fazenda.models import ContaGerencial, Fornecedor
from fazenda.rules.leitura_documento import MIME_ACEITOS, ler_documento


def _mock_ocr_imagem(texto: str):
    """Mocka `pytesseract.image_to_string` pra devolver sempre `texto`,
    simulando uma imagem única (JPEG/PNG) OCR'd."""
    return patch("pytesseract.image_to_string", return_value=texto)


def _mock_ocr_pdf(textos_por_pagina: list[str]):
    """Mocka o pipeline de PDF inteiro: `pdf2image.convert_from_bytes`
    devolve uma "imagem" fake por página (objetos quaisquer, nunca abertos
    de verdade) e `pytesseract.image_to_string` devolve o texto da página
    correspondente, na ordem em que foi chamado."""
    imagens_fake = [MagicMock(name=f"pagina{i}") for i in range(len(textos_por_pagina))]
    convert_patch = patch("pdf2image.convert_from_bytes", return_value=imagens_fake)
    ocr_patch = patch("pytesseract.image_to_string", side_effect=textos_por_pagina)
    return convert_patch, ocr_patch


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


# ── Textos OCR simulados, um por tipo de documento ──────────────────────
_OCR_NOTA_FISCAL = """DANFE - DOCUMENTO AUXILIAR DA NOTA FISCAL ELETRONICA
NOTA FISCAL DE VENDA
Numero: 1234
EMITENTE: Agropecuária Central Ltda
Data de Emissão: 01/07/2026
Ração concentrada 500 3,00 1500,00
VALOR TOTAL DA NOTA R$ 1.500,00
"""

_OCR_RECIBO = """RECIBO DE PAGAMENTO
FAVORECIDO: João da Silva
Data: 05/07/2026
Valor pago R$ 300,00
BANCO DO BRASIL AG 3775-3 CC 3.615-3
Comprovante PIX enviado com sucesso
"""

_OCR_BOLETO_SIMPLES = """BOLETO BANCARIO - COBRANCA
BENEFICIARIO: Fornecedor X Comercio Ltda
Vencimento: 10/08/2026
Valor do documento R$ 1.200,00
12340.12345 12345.678901 12345.678901 1 12340000120000
"""

_OCR_GUIA_FGTS = """GUIA DE RECOLHIMENTO DO FGTS
CONTRIBUINTE: Fazenda Estreito Ponte de Pedra
Competencia: 07/2026
Valor principal R$ 1.240,00
Multa R$ 0,00
Juros R$ 0,00
Vencimento: 20/08/2026
858700000012 400123456789 012345678901 234567890123
"""

_OCR_GUIA_DCTF = """DCTFWEB - DOCUMENTO DE ARRECADACAO DE RECEITAS FEDERAIS - DARF
CONTRIBUINTE: Fazenda Estreito Ponte de Pedra
Codigo da receita: 1017
Competencia: 07/2026
Valor principal R$ 850,00
Multa R$ 20,00
Juros R$ 22,50
Vencimento: 20/08/2026
"""


class TestLerDocumentoUnitario:
    """Testa `ler_documento` diretamente (sem passar pelo endpoint/router),
    sempre com o OCR mockado — nunca chama o binário do Tesseract de verdade."""

    def test_tipo_de_arquivo_nao_suportado(self):
        with pytest.raises(ValueError, match="não suportado"):
            ler_documento(b"oi", "text/plain")

    def test_aceita_image_jpg(self):
        assert "image/jpg" in MIME_ACEITOS
        with _mock_ocr_imagem(_OCR_RECIBO):
            with patch("PIL.Image.open"):
                dados = ler_documento(b"\xff\xd8\xff", "image/jpg")
        assert dados["tipo_documento"] == "recibo"

    def test_heic_e_aceito_no_upload_mas_da_erro_claro_e_acionavel(self):
        assert "image/heic" in MIME_ACEITOS
        with pytest.raises(ValueError) as exc_info:
            ler_documento(b"fake-heic-bytes", "image/heic")
        mensagem = str(exc_info.value)
        assert "HEIC" in mensagem
        assert "JPEG" in mensagem or "PDF" in mensagem

    def test_heif_tambem_da_erro_claro(self):
        with pytest.raises(ValueError, match="HEIF"):
            ler_documento(b"fake-heif-bytes", "image/heif")

    def test_heic_nunca_chega_a_chamar_o_ocr(self):
        # O erro tem que ser levantado antes de tentar processar a imagem —
        # não pode "falhar de forma obscura" lá no Tesseract.
        with patch("pytesseract.image_to_string") as mock_ocr:
            with pytest.raises(ValueError):
                ler_documento(b"fake-heic-bytes", "image/heic")
            mock_ocr.assert_not_called()

    def test_texto_ilegivel_ou_vazio_da_valueerror_claro(self):
        with _mock_ocr_imagem("   \n\n  "):
            with patch("PIL.Image.open"):
                with pytest.raises(ValueError, match="[Nn]enhum texto"):
                    ler_documento(b"\xff\xd8\xff", "image/jpeg")

    def test_pdf_sem_paginas_da_valueerror(self):
        with patch("pdf2image.convert_from_bytes", return_value=[]):
            with pytest.raises(ValueError, match="[Nn]enhuma página"):
                ler_documento(b"%PDF-1.4", "application/pdf")

    def test_falha_do_binario_tesseract_vira_valueerror_nao_500(self):
        """Simula o cenário real de produção antes do nixpacks.toml ser
        validado: o binário `tesseract` não está instalado — pytesseract
        levanta TesseractNotFoundError (ou qualquer OSError equivalente).
        Isso NUNCA pode virar um erro 500 ilegível; tem que virar ValueError
        com mensagem acionável (ver docstring do módulo sobre o fallback
        seguro)."""
        with patch("pytesseract.image_to_string", side_effect=OSError("tesseract não encontrado no PATH")):
            with patch("PIL.Image.open"):
                with pytest.raises(ValueError, match="OCR"):
                    ler_documento(b"\xff\xd8\xff", "image/jpeg")

    # ── Um caso de cada tipo_documento ──────────────────────────────────
    def test_extrai_nota_fiscal(self):
        with _mock_ocr_imagem(_OCR_NOTA_FISCAL):
            with patch("PIL.Image.open"):
                dados = ler_documento(b"\xff\xd8\xff", "image/jpeg")
        assert dados["tipo_documento"] == "nota_fiscal"
        assert dados["fornecedor_cliente"] == "Agropecuária Central Ltda"
        assert dados["numero_documento"] == "1234"
        assert dados["data_emissao"] == "2026-07-01"
        assert dados["valor_total"] == 1500.0
        assert len(dados["itens"]) == 1
        assert dados["itens"][0]["produto"] == "Ração concentrada"
        assert dados["itens"][0]["valor_total"] == 1500.0

    def test_extrai_recibo(self):
        with _mock_ocr_imagem(_OCR_RECIBO):
            with patch("PIL.Image.open"):
                dados = ler_documento(b"\xff\xd8\xff", "image/jpeg")
        assert dados["tipo_documento"] == "recibo"
        assert dados["fornecedor_cliente"] == "João da Silva"
        assert dados["data_pagamento"] == "2026-07-05"
        assert dados["valor_total"] == 300.0
        assert "3775-3" in dados["conta_bancaria"]

    def test_extrai_boleto_simples(self):
        with _mock_ocr_imagem(_OCR_BOLETO_SIMPLES):
            with patch("PIL.Image.open"):
                dados = ler_documento(b"\xff\xd8\xff", "image/jpeg")
        assert dados["tipo_documento"] == "boleto"
        assert dados["fornecedor_cliente"] == "Fornecedor X Comercio Ltda"
        assert dados["data_vencimento"] == "2026-08-10"
        assert dados["valor_total"] == 1200.0
        assert dados["linha_digitavel"] != ""
        assert dados["parcela_num"] is None
        assert dados["parcela_total"] is None
        assert len(dados["parcelas_detectadas"]) == 1

    def test_extrai_boleto_parcelado_multi_pagina(self):
        textos = [
            f"BENEFICIARIO: Cooperativa Agro\n"
            f"Vencimento: 10/{7 + i:02d}/2026\n"
            f"Parcela {i}/8\n"
            f"Valor do documento R$ 586,25\n"
            f"1234{i}.12345 12345.678901 12345.678901 1 1234000005862{i}"
            for i in range(1, 9)
        ]
        convert_patch, ocr_patch = _mock_ocr_pdf(textos)
        with convert_patch, ocr_patch:
            dados = ler_documento(b"%PDF-1.4", "application/pdf")
        assert dados["tipo_documento"] == "boleto"
        assert dados["parcela_num"] == 1
        assert dados["parcela_total"] == 8
        assert len(dados["parcelas_detectadas"]) == 8
        assert dados["parcelas_detectadas"][0]["valor"] == 586.25
        # A soma das 8 parcelas, não o valor de 1 via isolada (mesma rede de
        # segurança server-side de antes — ver _corrigir_valor_total_boleto).
        assert dados["valor_total"] == 4690.0
        assert dados["valor_total_corrigido"] is True

    def test_extrai_guia_fgts(self):
        with _mock_ocr_imagem(_OCR_GUIA_FGTS):
            with patch("PIL.Image.open"):
                dados = ler_documento(b"\xff\xd8\xff", "image/jpeg")
        assert dados["tipo_documento"] == "guia_fgts"
        assert dados["competencia"] == "2026-07"
        assert dados["valor_principal"] == 1240.0
        assert dados["valor_multa"] == 0.0
        assert dados["valor_juros"] == 0.0
        assert dados["valor_total"] == 1240.0
        assert dados["data_vencimento"] == "2026-08-20"

    def test_extrai_guia_dctf_com_codigo_da_receita(self):
        with _mock_ocr_imagem(_OCR_GUIA_DCTF):
            with patch("PIL.Image.open"):
                dados = ler_documento(b"\xff\xd8\xff", "image/jpeg")
        assert dados["tipo_documento"] == "guia_dctf"
        assert dados["codigo_receita"] == "1017"
        assert dados["valor_principal"] == 850.0
        assert dados["valor_multa"] == 20.0
        assert dados["valor_juros"] == 22.5
        assert dados["valor_total"] == 892.5

    def test_resposta_sempre_tem_todas_as_chaves_do_contrato(self):
        """Todo campo é obrigatório na resposta, mesmo quando o parser não
        conseguiu extrair nada — nunca falta chave, nunca `undefined`."""
        chaves_esperadas = {
            "tipo_documento", "parcela_num", "parcela_total", "linha_digitavel", "data_vencimento",
            "competencia", "codigo_receita", "valor_principal", "valor_multa", "valor_juros",
            "fornecedor_cliente", "numero_documento", "data_emissao", "data_pagamento", "valor_total",
            "parcelas_detectadas", "conta_bancaria", "itens", "observacao", "paginas_documento",
        }
        with _mock_ocr_imagem("texto qualquer sem nenhuma palavra-chave reconhecivel 12345"):
            with patch("PIL.Image.open"):
                dados = ler_documento(b"\xff\xd8\xff", "image/jpeg")
        assert chaves_esperadas <= set(dados.keys())


class TestLerDocumentoEndpoint:
    def test_tipo_de_arquivo_nao_suportado_retorna_400(self, client):
        c, engine = client
        r = c.post("/financeiro/ler-documento", files={"file": ("nota.txt", b"oi", "text/plain")})
        assert r.status_code == 400

    def test_texto_ilegivel_retorna_400(self, client):
        c, engine = client
        with _mock_ocr_imagem(""):
            with patch("PIL.Image.open"):
                r = c.post("/financeiro/ler-documento", files={"file": ("borrado.jpg", b"\xff\xd8\xff", "image/jpeg")})
        assert r.status_code == 400

    def test_extrai_nota_fiscal_via_endpoint(self, client):
        c, engine = client
        with _mock_ocr_imagem(_OCR_NOTA_FISCAL):
            with patch("PIL.Image.open"):
                r = c.post("/financeiro/ler-documento", files={"file": ("nota.jpg", b"\xff\xd8\xff", "image/jpeg")})
        assert r.status_code == 200
        d = r.json()
        assert d["tipo_documento"] == "nota_fiscal"
        assert d["fornecedor_cliente"] == "Agropecuária Central Ltda"

    def test_boleto_multiplas_paginas_corrige_valor_total_para_a_soma_via_endpoint(self, client):
        c, engine = client
        textos = [
            f"BENEFICIARIO: Cooperativa Agro\nVencimento: 10/08/2026\nParcela {i}/8\n"
            f"Valor do documento R$ 586,25\n1234{i}.12345 12345.678901 12345.678901 1 1234000005862{i}"
            for i in range(1, 9)
        ]
        convert_patch, ocr_patch = _mock_ocr_pdf(textos)
        with convert_patch, ocr_patch:
            r = c.post("/financeiro/ler-documento", files={"file": ("boleto8x.pdf", b"%PDF-1.4", "application/pdf")})
        assert r.status_code == 200
        d = r.json()
        assert d["valor_total"] == 4690.0
        assert d["valor_total_corrigido"] is True
        assert len(d["parcelas_detectadas"]) == 8

    def test_boleto_uma_parcela_nao_mexe_no_valor_total(self, client):
        c, engine = client
        with _mock_ocr_imagem(_OCR_BOLETO_SIMPLES):
            with patch("PIL.Image.open"):
                r = c.post("/financeiro/ler-documento", files={"file": ("boleto_unico.jpg", b"\xff\xd8\xff", "image/jpeg")})
        assert r.status_code == 200
        d = r.json()
        assert d["valor_total"] == 1200.0
        assert "valor_total_corrigido" not in d


class TestSugestoesCadastroNoEndpoint:
    """O endpoint /financeiro/ler-documento já devolve, junto dos campos
    extraídos, as sugestões de casamento com o cadastro (fornecedor/produto/
    serviço parecidos) — ver fazenda.rules.sugestao_documento. Continua
    valendo independente de como os dados foram extraídos."""

    def test_fornecedor_parecido_aparece_em_sugestoes_cadastro(self, client):
        c, engine = client
        with Session(engine) as s:
            s.add(Fornecedor(nome="Agropecuária São José", tipo="fornecedor"))
            s.commit()
        texto = _OCR_NOTA_FISCAL.replace("Agropecuária Central Ltda", "Agropecuaria Sao Jose Norte")
        with _mock_ocr_imagem(texto):
            with patch("PIL.Image.open"):
                r = c.post("/financeiro/ler-documento", files={"file": ("nota.jpg", b"\xff\xd8\xff", "image/jpeg")})
        assert r.status_code == 200
        sug = r.json()["sugestoes_cadastro"]
        assert sug["fornecedor"]["candidato"] == "Agropecuária São José"
        assert sug["fornecedor"]["confianca"] == "provavel"

    def test_sem_nenhum_cadastro_parecido_sugestoes_ficam_vazias(self, client):
        c, engine = client
        texto = _OCR_NOTA_FISCAL.replace("Agropecuária Central Ltda", "Fornecedor Sem Nenhum Cadastro Parecido")
        with _mock_ocr_imagem(texto):
            with patch("PIL.Image.open"):
                r = c.post("/financeiro/ler-documento", files={"file": ("nota.jpg", b"\xff\xd8\xff", "image/jpeg")})
        assert r.status_code == 200
        assert r.json()["sugestoes_cadastro"] == {"fornecedor": None, "fornecedor_confianca": "incerto", "itens": []}
