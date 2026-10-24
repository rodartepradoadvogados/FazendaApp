"""Logomarca CowData Milk nos documentos gerados pelo backend."""
from pathlib import Path

from fazenda.rules.manual_fazenda_pdf import _LOGO_URI, _bloquear_recursos_externos, gerar_pdf_manual

TEMPLATES = Path(__file__).resolve().parent.parent / "fazenda" / "templates"


def test_manual_pdf_sai_com_a_logomarca():
    pdf = gerar_pdf_manual({"rotina": {}, "resultado": {}, "insights": []})
    assert pdf.startswith(b"%PDF") and b"/Image" in pdf


def test_callback_so_libera_a_propria_logomarca():
    assert _bloquear_recursos_externos(_LOGO_URI, "") == _LOGO_URI
    assert _bloquear_recursos_externos("http://169.254.169.254/x.png", "") == "data:,"
    assert _bloquear_recursos_externos("data:image/png;base64,AAAA", "") == "data:,"


def test_contrato_do_cliente_leva_o_milk_e_o_da_equipe_nao():
    cliente = (TEMPLATES / "contrato_cowdata.html").read_text(encoding="utf-8")
    equipe = (TEMPLATES / "contrato_equipe_base.html").read_text(encoding="utf-8")
    assert 'aria-label' not in cliente.split('class="wordmark"')[1][:60] and "<svg" in cliente.split('class="wordmark"')[1][:400]
    assert "<svg" not in equipe.split('class="wordmark"')[1][:200]
