"""
Robô do Telegram: fluxo documento → pergunta receita/despesa → lançamento.
As chamadas de rede ao Telegram e a leitura do documento são simuladas.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.api.routers import telegram
from fazenda.api.routers.telegram import _ler_documento_pendente as _ler_documento_pendente_real
from fazenda.auth import get_current_user
from fazenda.config import settings
from fazenda.models import ContaGerencial, Fornecedor, LancamentoPendente, TelegramPendente, Usuario

SECRET = "segredo-teste"
CHAT = 123456


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    main.app.dependency_overrides[database.get_session] = _get_session_override

    # Liga o bot e libera o chat de teste.
    monkeypatch.setattr(settings, "telegram_bot_token", "token-teste")
    monkeypatch.setattr(settings, "telegram_webhook_secret", SECRET)
    monkeypatch.setattr(settings, "telegram_allowed_chat_ids", str(CHAT))

    # Simula as chamadas de rede ao Telegram (send/answer) capturando o que sairia.
    enviados: list[dict] = []
    monkeypatch.setattr(telegram, "_tg", lambda metodo, payload: (enviados.append({"metodo": metodo, **payload}) or {"ok": True}))
    # Simula a leitura do documento (sem baixar nem chamar IA).
    monkeypatch.setattr(telegram, "_ler_documento_pendente", lambda pend: {
        "tipo_documento": "nota_fiscal",
        "fornecedor_cliente": "Casa do Produtor",
        "numero_documento": "NF-777",
        "data_emissao": "2026-07-05",
        "data_pagamento": None,
        "valor_total": 250.0,
        "conta_bancaria": None,
        "itens": [{"produto": "Ração", "quantidade": 5, "valor_unitario": 50.0, "valor_total": 250.0}],
        "observacao": None,
    })

    with TestClient(main.app) as c:
        yield c, engine, enviados
    main.app.dependency_overrides.clear()


def _hdr():
    return {"X-Telegram-Bot-Api-Secret-Token": SECRET}


def _criar_admin(engine) -> Usuario:
    with Session(engine) as s:
        user = Usuario(username="admin-teste", nome="Admin", senha_hash="x", papel="admin")
        s.add(user)
        s.commit()
        s.refresh(user)
        s.expunge(user)
        return user


def test_documento_pergunta_e_lanca_despesa(client):
    """O lançamento financeiro do robô NUNCA materializa direto — sempre vira
    um LancamentoPendente aguardando aprovação, igual aos lançamentos
    operacionais (pesagem, parto, etc.)."""
    c, engine, enviados = client
    # 1) Chega um XML → deve criar um pendente e perguntar receita/despesa com botões.
    upd_msg = {"message": {"chat": {"id": CHAT}, "document": {"file_id": "FID1", "file_name": "nota.xml", "mime_type": "text/xml"}}}
    r = c.post("/telegram/webhook", json=upd_msg, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        pend = s.exec(select(TelegramPendente)).first()
        assert pend is not None and pend.kind == "xml"
        pid = pend.id
    assert any(e["metodo"] == "sendMessage" and "reply_markup" in e for e in enviados)

    # 2) Usuário toca em "Despesa" → lê o documento e mostra um resumo rico
    # com Confirmar/Corrigir/Cancelar; ainda NÃO cria LancamentoPendente nem
    # apaga o TelegramPendente (fica em espera de confirmação).
    upd_cb = {"callback_query": {"id": "cb1", "message": {"chat": {"id": CHAT}}, "data": f"lanc:{pid}:despesa"}}
    r = c.post("/telegram/webhook", json=upd_cb, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(LancamentoPendente)).first() is None  # ainda não confirmou
        pend = s.exec(select(TelegramPendente)).first()
        assert pend is not None and pend.tipo == "despesa"
        assert json.loads(pend.dados_lidos)["fornecedor_cliente"] == "Casa do Produtor"
    ultima = enviados[-1]
    assert "confirmar" in ultima["text"].lower() or any(
        "confirmar" in b["text"].lower() for linha in ultima.get("reply_markup", {}).get("inline_keyboard", []) for b in linha
    )

    # 3) Usuário toca em "Confirmar" → cria um LancamentoPendente (fila de
    # aprovação), NÃO um lançamento de verdade, e apaga o pendente do documento.
    upd_confirma = {"callback_query": {"id": "cb2", "message": {"chat": {"id": CHAT}}, "data": f"confirmarlanc:{pid}"}}
    r = c.post("/telegram/webhook", json=upd_confirma, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(ContaGerencial)).first() is None  # nada lançado de verdade ainda
        assert s.exec(select(TelegramPendente)).first() is None  # pendente do documento consumido
        pendente = s.exec(select(LancamentoPendente)).first()
        assert pendente is not None
        assert pendente.tipo == "despesa"
        assert pendente.status == "pendente"
        dados = json.loads(pendente.payload)
        assert dados["fornecedor_cliente"] == "Casa do Produtor"
        assert dados["valor_total"] == 250.0

    # 3) Aprovar sem o fornecedor cadastrado deve FALHAR (e não criar nada) —
    # este é o bug relatado: "Comercial Montividiu" nunca tinha sido cadastrado.
    import main
    admin = _criar_admin(engine)
    main.app.dependency_overrides[get_current_user] = lambda: admin
    r = c.post(f"/aprovacoes/{pendente.id}/aprovar")
    assert r.status_code == 400
    assert "não está cadastrado" in r.json()["detail"]
    with Session(engine) as s:
        assert s.exec(select(ContaGerencial)).first() is None
        p = s.get(LancamentoPendente, pendente.id)
        assert p.status == "pendente"  # continua pendente, não vira "aprovado" sozinho
        assert p.erro  # erro fica registrado para o admin ver na tela

    # 4) Cadastrando o fornecedor e aprovando de novo agora materializa de verdade.
    with Session(engine) as s:
        s.add(Fornecedor(nome="Casa do Produtor", tipo="fornecedor"))
        s.commit()
    r = c.post(f"/aprovacoes/{pendente.id}/aprovar")
    assert r.status_code == 200
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial)).first()
        assert conta is not None
        assert conta.tipo == "despesa"
        assert conta.origem == "telegram"
        assert conta.valor_total == 250.0
        assert conta.data_pagamento is None  # nota fiscal nasce em aberto
        p = s.get(LancamentoPendente, pendente.id)
        assert p.status == "aprovado"


def test_aprovar_despesa_com_itens_em_texto_solto(client, monkeypatch):
    """Bug relatado: a extração do documento às vezes devolve "itens" como uma
    lista de textos soltos (ex.: ["Impressora", "Brother"]) em vez de objetos
    {produto, quantidade, ...} — isso derrubava a aprovação com
    "'str' object has no attribute 'get'". Aprovar deve funcionar mesmo assim,
    tratando cada texto como um item sem preço."""
    c, engine, enviados = client
    monkeypatch.setattr(telegram, "_ler_documento_pendente", lambda pend: {
        "tipo_documento": "recibo",
        "fornecedor_cliente": "Kalunga S.A.",
        "numero_documento": "0000000071501",
        "data_emissao": "2026-07-15",
        "data_pagamento": "2026-07-15",
        "valor_total": 1355.7,
        "conta_bancaria": "Banco do Brasil ag 3775-3 cc 3615-3",
        "itens": ["Impressora", "Brother"],
        "observacao": None,
    })
    with Session(engine) as s:
        s.add(Fornecedor(nome="Kalunga S.A.", tipo="fornecedor"))
        s.commit()

    upd_msg = {"message": {"chat": {"id": CHAT}, "document": {"file_id": "FID-ITENS", "file_name": "recibo.pdf", "mime_type": "application/pdf"}}}
    r = c.post("/telegram/webhook", json=upd_msg, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        pid = s.exec(select(TelegramPendente)).first().id

    upd_cb = {"callback_query": {"id": "cb1", "message": {"chat": {"id": CHAT}}, "data": f"lanc:{pid}:despesa"}}
    r = c.post("/telegram/webhook", json=upd_cb, headers=_hdr())
    assert r.status_code == 200
    upd_confirma = {"callback_query": {"id": "cb2", "message": {"chat": {"id": CHAT}}, "data": f"confirmarlanc:{pid}"}}
    r = c.post("/telegram/webhook", json=upd_confirma, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        pendente = s.exec(select(LancamentoPendente)).first()

    import main
    admin = _criar_admin(engine)
    main.app.dependency_overrides[get_current_user] = lambda: admin
    r = c.post(f"/aprovacoes/{pendente.id}/aprovar")
    assert r.status_code == 200, r.json()
    with Session(engine) as s:
        conta = s.exec(select(ContaGerencial)).first()
        assert conta is not None
        assert conta.tipo == "despesa"
        p = s.get(LancamentoPendente, pendente.id)
        assert p.status == "aprovado"


def test_chat_nao_liberado_nao_lanca(client, monkeypatch):
    c, engine, enviados = client
    monkeypatch.setattr(settings, "telegram_allowed_chat_ids", "999")  # CHAT não está liberado
    upd = {"message": {"chat": {"id": CHAT}, "document": {"file_id": "FID2", "file_name": "x.xml", "mime_type": "text/xml"}}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None  # nada guardado


def test_webhook_rejeita_segredo_errado(client):
    c, _, _ = client
    r = c.post("/telegram/webhook", json={"message": {}}, headers={"X-Telegram-Bot-Api-Secret-Token": "errado"})
    assert r.status_code == 403


def test_pdf_sem_mime_type_correto_ainda_e_reconhecido(client):
    """Alguns clientes do Telegram enviam PDF sem preencher mime_type (ou com
    um valor genérico) — antes, isso fazia o arquivo ser descartado em
    silêncio; agora cai no fallback pela extensão .pdf, igual ao XML."""
    c, engine, enviados = client
    upd = {"message": {"chat": {"id": CHAT}, "document": {
        "file_id": "FID-PDF", "file_name": "nota_fiscal.pdf", "mime_type": "application/octet-stream",
    }}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        pend = s.exec(select(TelegramPendente)).first()
        assert pend is not None and pend.kind == "documento"
    assert any(e["metodo"] == "sendMessage" and "reply_markup" in e for e in enviados)


def test_webp_e_gif_sao_reconhecidos_como_documento(client):
    """Comprovantes fotografados em WebP/GIF (ex.: print de app que salva
    nesse formato) devem ser aceitos como qualquer outra imagem — a IA
    (Claude Vision) já lê esses formatos nativamente."""
    c, engine, enviados = client
    upd = {"message": {"chat": {"id": CHAT}, "document": {
        "file_id": "FID-WEBP", "file_name": "comprovante.webp", "mime_type": "image/webp",
    }}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        pend = s.exec(select(TelegramPendente)).first()
        assert pend is not None and pend.kind == "documento"


def test_heic_orienta_enviar_como_foto(client):
    """Fotos de iPhone em HEIC/HEIF não são lidas pela IA — o bot deve
    orientar o usuário a reenviar como "foto" (o Telegram recomprime para
    JPEG no servidor, contornando o formato), em vez da mensagem genérica de
    "não reconheci"."""
    c, engine, enviados = client
    upd = {"message": {"chat": {"id": CHAT}, "document": {
        "file_id": "FID-HEIC", "file_name": "IMG_0001.HEIC", "mime_type": "image/heic",
    }}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None
    ultima = enviados[-1]
    assert "foto" in ultima["text"].lower()
    assert "heic" in ultima["text"].lower()


def test_arquivo_tipo_nao_reconhecido_avisa_usuario(client):
    """Um arquivo que não é XML/PDF/JPG/PNG nem por mime nem por extensão deve
    avisar o usuário, não cair na mensagem genérica de comando (como se nada
    tivesse sido enviado)."""
    c, engine, enviados = client
    upd = {"message": {"chat": {"id": CHAT}, "document": {
        "file_id": "FID-ZIP", "file_name": "arquivo.zip", "mime_type": "application/zip",
    }}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None
    ultima = enviados[-1]
    assert "não reconheci" in ultima["text"].lower()


def _enviar_documento(c, file_id="FID-DOC"):
    upd = {"message": {"chat": {"id": CHAT}, "document": {"file_id": file_id, "file_name": "doc.pdf", "mime_type": "application/pdf"}}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200


def _callback(c, data, cbid="cb"):
    upd = {"callback_query": {"id": cbid, "message": {"chat": {"id": CHAT}}, "data": data}}
    r = c.post("/telegram/webhook", json=upd, headers=_hdr())
    assert r.status_code == 200


def test_corrigir_marca_lancamento_para_revisao(client, monkeypatch):
    """#397 — tocar em "Corrigir" ainda envia para aprovação (a correção em si
    acontece na tela de Aprovações, que já tem edição completa), mas marca o
    resumo para chamar a atenção do admin."""
    c, engine, enviados = client
    _enviar_documento(c)
    with Session(engine) as s:
        pid = s.exec(select(TelegramPendente)).first().id
    _callback(c, f"lanc:{pid}:despesa")
    _callback(c, f"corrigirlanc:{pid}")
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None
        pendente = s.exec(select(LancamentoPendente)).first()
        assert pendente is not None
        assert "revisar" in pendente.resumo.lower()
    ultima = enviados[-1]
    assert "aprovações" in ultima["text"].lower()


def test_cancelar_apos_ler_documento_nao_lanca(client):
    """Cancelar depois de já ter lido o documento (mas antes de confirmar) não
    deve criar nenhum LancamentoPendente."""
    c, engine, enviados = client
    _enviar_documento(c)
    with Session(engine) as s:
        pid = s.exec(select(TelegramPendente)).first().id
    _callback(c, f"lanc:{pid}:despesa")
    _callback(c, f"cancel:{pid}")
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None
        assert s.exec(select(LancamentoPendente)).first() is None


def test_faltando_dados_pergunta_antes_de_confirmar(client, monkeypatch):
    """#397 — se faltar fornecedor/valor/data de emissão, o robô pergunta se
    quer lançar mesmo assim antes de mostrar os botões normais."""
    c, engine, enviados = client
    monkeypatch.setattr(telegram, "_ler_documento_pendente", lambda pend: {
        "tipo_documento": "recibo", "fornecedor_cliente": None, "numero_documento": None,
        "data_emissao": None, "data_pagamento": None, "valor_total": 500.0,
        "conta_bancaria": None, "itens": [], "observacao": None,
    })
    _enviar_documento(c)
    with Session(engine) as s:
        pid = s.exec(select(TelegramPendente)).first().id
    _callback(c, f"lanc:{pid}:despesa")
    ultima = enviados[-1]
    assert "faltam dados" in ultima["text"].lower()
    assert "fornecedor" in ultima["text"].lower()
    assert "lançar mesmo assim" in ultima["text"].lower()

    _callback(c, f"confirmarlanc:{pid}")
    with Session(engine) as s:
        pendente = s.exec(select(LancamentoPendente)).first()
        assert pendente is not None
        assert json.loads(pendente.payload)["valor_total"] == 500.0


def test_boleto_isolado_pergunta_avulso_ou_manual(client, monkeypatch):
    """#398 — boleto sem indicação de parcelamento pergunta se é avulso ou se
    o usuário prefere informar manualmente (ex.: novo parcelamento)."""
    c, engine, enviados = client
    monkeypatch.setattr(telegram, "_ler_documento_pendente", lambda pend: {
        "tipo_documento": "boleto", "fornecedor_cliente": "Cooperativa Agro", "numero_documento": "00001-2",
        "data_emissao": None, "data_pagamento": None, "valor_total": 850.0, "conta_bancaria": None,
        "itens": [], "observacao": None, "parcela_num": None, "parcela_total": None,
        "linha_digitavel": "12345", "data_vencimento": "2026-08-10",
    })
    _enviar_documento(c)
    with Session(engine) as s:
        pid = s.exec(select(TelegramPendente)).first().id
    _callback(c, f"lanc:{pid}:despesa")
    ultima = enviados[-1]
    assert "avulso" in ultima["text"].lower()
    assert "manualmente" in ultima["text"].lower()
    with Session(engine) as s:
        assert s.exec(select(LancamentoPendente)).first() is None  # ainda não decidiu

    # Escolhe "informar manualmente" → não lança nada, só orienta a usar o site.
    _callback(c, f"boletomanual:{pid}")
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None
        assert s.exec(select(LancamentoPendente)).first() is None
    assert "financeiro" in enviados[-1]["text"].lower()


def test_boleto_avulso_confirma_normalmente(client, monkeypatch):
    """#398 — escolhendo "avulso", segue para a confirmação normal (#397) e o
    Confirmar cria o LancamentoPendente."""
    c, engine, enviados = client
    monkeypatch.setattr(telegram, "_ler_documento_pendente", lambda pend: {
        "tipo_documento": "boleto", "fornecedor_cliente": "Cooperativa Agro", "numero_documento": "00001-2",
        "data_emissao": "2026-07-10", "data_pagamento": None, "valor_total": 850.0, "conta_bancaria": None,
        "itens": [], "observacao": None, "parcela_num": None, "parcela_total": None,
        "linha_digitavel": "12345", "data_vencimento": "2026-08-10",
    })
    _enviar_documento(c)
    with Session(engine) as s:
        pid = s.exec(select(TelegramPendente)).first().id
    _callback(c, f"lanc:{pid}:despesa")
    _callback(c, f"boletoavulso:{pid}")
    ultima = enviados[-1]
    assert "confirmar" in ultima["text"].lower() or any(
        "confirmar" in b["text"].lower() for linha in ultima.get("reply_markup", {}).get("inline_keyboard", []) for b in linha
    )
    _callback(c, f"confirmarlanc:{pid}")
    with Session(engine) as s:
        pendente = s.exec(select(LancamentoPendente)).first()
        assert pendente is not None
        assert json.loads(pendente.payload)["tipo_documento"] == "boleto"


def test_boleto_parcelado_nao_pergunta_avulso(client, monkeypatch):
    """#398 — quando o documento já indica a parcela (ex.: "2/6"), não faz
    sentido perguntar se é avulso — já sabemos que faz parte de um plano."""
    c, engine, enviados = client
    monkeypatch.setattr(telegram, "_ler_documento_pendente", lambda pend: {
        "tipo_documento": "boleto", "fornecedor_cliente": "Cooperativa Agro", "numero_documento": "00001-2",
        "data_emissao": "2026-07-10", "data_pagamento": None, "valor_total": 850.0, "conta_bancaria": None,
        "itens": [], "observacao": None, "parcela_num": 2, "parcela_total": 6,
        "linha_digitavel": "12345", "data_vencimento": "2026-08-10",
    })
    _enviar_documento(c)
    with Session(engine) as s:
        pid = s.exec(select(TelegramPendente)).first().id
    _callback(c, f"lanc:{pid}:despesa")
    ultima = enviados[-1]
    assert "avulso" not in ultima["text"].lower()
    assert "2/6" in ultima["text"]


def test_falha_na_leitura_do_documento_avisa_usuario_com_mensagem_clara(client, monkeypatch):
    """Regressão: os outros testes deste arquivo sempre trocam
    `_ler_documento_pendente` por um stub — o que significa que o caminho real
    (baixar o arquivo do Telegram e chamar `ler_documento`, que faz OCR via
    Tesseract) nunca era exercitado pela suíte, e uma falha do pipeline de OCR
    em produção (ex.: nixpacks.toml não instalou o binário `tesseract`) não
    seria pega pelo CI. Este teste usa a função de verdade (só a chamada de
    rede ao Telegram e o OCR em si são simulados — mockar `pytesseract` evita
    precisar do binário instalado neste ambiente de teste) e confirma que,
    quando a leitura falha, o usuário recebe um aviso claro (não trava, não
    vaza um erro genérico ilegível) e o pendente é descartado — igual ao
    caminho do Financeiro (ver
    test_leitura_documento.py::test_falha_do_binario_tesseract_vira_valueerror_nao_500)."""
    c, engine, enviados = client
    monkeypatch.setattr(telegram, "_ler_documento_pendente", _ler_documento_pendente_real)
    monkeypatch.setattr(telegram, "_baixar_arquivo", lambda file_id: b"%PDF-1.4")
    monkeypatch.setattr("pdf2image.convert_from_bytes", lambda conteudo: [object()])
    monkeypatch.setattr("pytesseract.image_to_string", lambda img, lang=None: (_ for _ in ()).throw(OSError("tesseract não encontrado")))

    _enviar_documento(c)
    with Session(engine) as s:
        pid = s.exec(select(TelegramPendente)).first().id
    _callback(c, f"lanc:{pid}:despesa")

    ultima = enviados[-1]
    assert "Não consegui ler o documento" in ultima["text"]
    with Session(engine) as s:
        assert s.exec(select(TelegramPendente)).first() is None
