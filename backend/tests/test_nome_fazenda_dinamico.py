"""
Nome da fazenda ATUAL nos textos que saem do sistema — nunca o nome fixo de
uma fazenda-cliente.

BUG CORRIGIDO: rodapé dos e-mails (recibo e diagnóstico), cabeçalho do PDF do
Manual, prompt do Assistente e contribuinte padrão da guia FGTS/DCTFWeb lida
por OCR traziam "Fazenda Estreito Ponte de Pedra" para QUALQUER fazenda. Cada
teste usa DUAS fazendas com nomes diferentes: o texto de uma não pode aparecer
no da outra, e sem fazenda conhecida o fallback é o nome do produto (ou campo
vazio, na leitura de guia — ver leitura_documento.py).
"""
from __future__ import annotations

import asyncio
import io
from datetime import date
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import fazenda.api.routers.financeiro as financeiro
import fazenda.api.routers.reproducao as reproducao
from fazenda.models import ContaGerencial, Fazenda, Servico
from fazenda.rules import assistente
from fazenda.rules.leitura_documento import ler_documento
from fazenda.rules.manual_fazenda import montar_manual
from fazenda.rules.manual_fazenda_pdf import _html_manual
from fazenda.rules.nome_fazenda import NOME_PADRAO, nome_da_fazenda, nome_fazenda_ou_padrao

NOMES = {1: "Fazenda Boa Vista", 2: "Sítio Três Irmãos"}
NOME_ANTIGO_FIXO = "Estreito Ponte de Pedra"


@pytest.fixture
def engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    with Session(eng) as s:
        for fid, nome in NOMES.items():
            s.add(Fazenda(id=fid, nome=nome))
        s.commit()
    return eng


@pytest.fixture
def emails(monkeypatch):
    """Captura (destinatario, corpo_html) em vez de mandar e-mail de verdade."""
    enviados: list[tuple[str, str]] = []

    def _falso(destino, assunto, corpo, nome_anexo=None, anexo=None):
        enviados.append((destino, corpo))

    monkeypatch.setattr(financeiro, "enviar_email", _falso)
    monkeypatch.setattr(reproducao, "enviar_email", _falso)
    return enviados


# ── helper ──────────────────────────────────────────────────────────────────
def test_helper_devolve_nome_do_cadastro_e_cai_no_produto_sem_fazenda(engine):
    with Session(engine) as s:
        assert nome_da_fazenda(s, 1) == NOMES[1]
        assert nome_da_fazenda(s, 2) == NOMES[2]
        assert nome_da_fazenda(s, None) is None
        assert nome_da_fazenda(s, 999) is None
        assert nome_fazenda_ou_padrao(s, None) == NOME_PADRAO == "CowData Milk"


# ── e-mails ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("fid", [1, 2])
def test_rodape_do_email_de_diagnostico_usa_a_fazenda_do_token(engine, emails, fid):
    with Session(engine) as s:
        s.add(Servico(
            numero_matriz="100", data_servico=date(2026, 5, 1), data_diagnostico=date(2026, 6, 1),
            diagnostico="POSITIVO", fazenda_id=fid,
        ))
        s.commit()
        reproducao.enviar_ultimo_diagnostico(
            "100", reproducao.EnviarDiagnosticoIn(destinatario="vet@x.com"), session=s, fazenda_id=fid,
        )
    corpo = emails[-1][1]
    outra = NOMES[3 - fid]
    assert f"<p>{NOMES[fid]}</p>" in corpo
    assert outra not in corpo and NOME_ANTIGO_FIXO not in corpo


def _upload() -> UploadFile:
    return UploadFile(file=io.BytesIO(b"%PDF-1.4"), filename="recibo.pdf")


@pytest.mark.parametrize("fid", [1, 2])
def test_rodape_do_email_de_recibo_usa_a_fazenda_do_token(engine, emails, fid):
    with Session(engine) as s:
        s.add(ContaGerencial(numero_lancamento=f"LC-2026-0000{fid}", fazenda_id=fid, valor_total=10.0))
        s.commit()
        asyncio.run(financeiro.enviar_recibo(
            f"LC-2026-0000{fid}", destinatario="a@x.com", arquivo=_upload(), session=s, fazenda_id=fid,
        ))
    corpo = emails[-1][1]
    assert f"<p>{NOMES[fid]}</p>" in corpo
    assert NOMES[3 - fid] not in corpo and NOME_ANTIGO_FIXO not in corpo


def test_rodape_sem_fazenda_conhecida_cai_no_nome_do_produto(engine, emails):
    with Session(engine) as s:
        s.add(ContaGerencial(numero_lancamento="LC-2026-00009", valor_total=1.0))
        s.commit()
        asyncio.run(financeiro.enviar_recibo(
            "LC-2026-00009", destinatario="a@x.com", arquivo=_upload(), session=s, fazenda_id=None,
        ))
    assert "<p>CowData Milk</p>" in emails[-1][1]


# ── Manual da Fazenda (PDF) ─────────────────────────────────────────────────
@pytest.mark.parametrize("fid", [1, 2])
def test_cabecalho_do_manual_usa_a_fazenda_do_recorte(engine, fid):
    with Session(engine) as s:
        manual = montar_manual(s, fid)
    assert manual["nome_fazenda"] == NOMES[fid]
    html = _html_manual(manual)
    assert NOMES[fid].upper() in html
    assert NOMES[3 - fid].upper() not in html and NOME_ANTIGO_FIXO.upper() not in html


def test_cabecalho_do_manual_sem_fazenda_usa_o_produto_e_escapa_o_nome():
    assert "COWDATA MILK" in _html_manual({"nome_fazenda": None})
    html = _html_manual({"nome_fazenda": "<b>X</b>"})
    assert "<B>X</B>" not in html and "&lt;B&gt;X&lt;/B&gt;" in html


# ── leitura de guia FGTS por OCR ────────────────────────────────────────────
_OCR_GUIA_SEM_CONTRIBUINTE = """GUIA DE RECOLHIMENTO DO FGTS
Competencia: 07/2026
Valor principal R$ 1.240,00
Vencimento: 20/08/2026
"""


def _ler_guia(nome_fazenda):
    with patch("pytesseract.image_to_string", return_value=_OCR_GUIA_SEM_CONTRIBUINTE):
        with patch("PIL.Image.open"):
            return ler_documento(b"\xff\xd8\xff", "image/jpeg", nome_fazenda=nome_fazenda)


@pytest.mark.parametrize("nome", list(NOMES.values()))
def test_guia_sem_contribuinte_legivel_recebe_o_nome_da_fazenda_atual(nome):
    dados = _ler_guia(nome)
    assert dados["tipo_documento"] == "guia_fgts"
    assert dados["fornecedor_cliente"] == nome


def test_guia_sem_fazenda_conhecida_fica_sem_fornecedor():
    """Nem o nome de outra fazenda, nem o do produto — viraria fornecedor de
    verdade no lançamento. Vazio, o formulário/robô pede o campo."""
    assert not _ler_guia(None)["fornecedor_cliente"]


# ── Assistente (prompt enviado ao provedor de IA) ───────────────────────────
@pytest.mark.parametrize("fid", [1, 2])
def test_prompt_do_assistente_traz_so_o_nome_da_fazenda_atual(engine, fid):
    with Session(engine) as s:
        prompt = assistente._system_prompt(s, fid)
    assert prompt == assistente.prompt_base(NOMES[fid])
    assert f'da fazenda "{NOMES[fid]}"' in prompt
    assert NOMES[3 - fid] not in prompt and NOME_ANTIGO_FIXO not in prompt


def test_prompt_sem_fazenda_e_generico(engine):
    with Session(engine) as s:
        assert assistente._system_prompt(s, None) == assistente.SYSTEM_PROMPT
    assert "sistema de gestão da fazenda (fazenda leiteira" in assistente.SYSTEM_PROMPT
    assert NOME_ANTIGO_FIXO not in assistente.SYSTEM_PROMPT
