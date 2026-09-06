"""
Arquivo fiscal-contábil (Central de Documentos) — o MESMO defeito de colisão
de caminho no Storage que travou a exclusão de documento em Cadastro >
Pessoas (relato do dono, 06/09/2026), corrigido depois em pedidos.py e
financeiro.py e ainda intacto aqui.

AQUI ELE É PIOR: o nome gravado no Storage é DETERMINÍSTICO
("2026-09-06_NF_0001.pdf" — data, abreviação da categoria e sequência, sem o
nome do arquivo enviado). Nos outros módulos a colisão dependia de o usuário
repetir o nome do arquivo; nesta tela ela é GARANTIDA: com 0001 e 0002 no
mesmo dia e na mesma categoria, excluir o 0001 faz o próximo upload nascer
0002 e sobrescrever, via `x-upsert`, o arquivo do documento que continua
vivo na tela.

Cada teste nasceu ANTES da correção, reproduzindo a falha contra o código de
então. O ambiente é o de PRODUÇÃO, não o da suíte: duas fazendas-clientes
com contrato ativo e TOKEN DE VERDADE (`criar_token`), nunca
`dependency_overrides[get_fazenda_atual_id]` — é o caminho token ->
get_fazenda_atual_id -> consulta que sustenta o isolamento, e falsificar o
meio dele tiraria do teste o que ele precisa provar.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, DocumentoArquivado, Fazenda, TipoDocumento, Usuario,
    UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def ambiente(monkeypatch):
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    with Session(engine) as s:
        for fid, nome in ((1, "Fazenda Alvo"), (2, "Fazenda Vizinha")):
            s.add(Fazenda(id=fid, nome=nome, ativa=True))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(
                id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True,
            ))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
            s.add(TipoDocumento(nome="Nota fiscal", ativo=True, fazenda_id=fid))
            s.add(TipoDocumento(nome="Contrato", ativo=True, fazenda_id=fid))
        s.commit()

    # Supabase Storage falso — o `balde` é o disco, e apagar um caminho que
    # não está lá levanta RuntimeError EXATAMENTE como `excluir_arquivo`
    # levanta quando o Supabase responde 404 (ver rules/supabase_storage.py).
    # É esse 404 que travava a exclusão do documento.
    import fazenda.api.routers.documentos as documentos_mod
    balde: dict[str, bytes] = {}

    def _baixar(caminho, *a, **k):
        if caminho not in balde:
            raise RuntimeError("Falha ao baixar arquivo do Supabase Storage: 404 {'error':'not_found'}")
        return balde[caminho]

    def _excluir(caminho, *a, **k):
        if caminho not in balde:
            raise RuntimeError("Falha ao excluir arquivo do Supabase Storage: 404 {'error':'not_found'}")
        balde.pop(caminho)

    monkeypatch.setattr(documentos_mod, "enviar_arquivo", lambda caminho, conteudo, *a, **k: balde.__setitem__(caminho, conteudo))
    monkeypatch.setattr(documentos_mod, "baixar_arquivo", _baixar)
    monkeypatch.setattr(documentos_mod, "excluir_arquivo", _excluir)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, balde
    main.app.dependency_overrides.clear()


def _cab(fazenda_id: int = 1) -> dict:
    """Token REAL do admin daquela fazenda, com a claim "fid" carimbada."""
    return {"Authorization": f"Bearer {criar_token(f'admin{fazenda_id}', fazenda_id=fazenda_id)}"}


def _enviar(c, conteudo: bytes, *, categoria: str = "Nota fiscal", nome: str = "nota.pdf", fazenda_id: int = 1) -> int:
    r = c.post(
        "/documentos/upload",
        files={"file": (nome, conteudo, "application/pdf")},
        data={"categoria": categoria},
        headers=_cab(fazenda_id),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _caminho(engine, documento_id: int) -> str:
    with Session(engine) as s:
        return s.get(DocumentoArquivado, documento_id).caminho_storage


class TestExcluirDocumentoArquivado:
    def test_exclui_documento_mesmo_com_o_arquivo_ausente_no_storage(self, ambiente):
        """FALHA REPRODUZIDA: o arquivo não está mais no bucket (apagado à mão
        no painel do Supabase, upload interrompido, ou caminho sobrescrito —
        ver o teste seguinte), o Supabase responde 404 e `excluir_arquivo`
        levanta RuntimeError. O endpoint devolvia 400 e ABORTAVA antes de
        apagar a linha, então o documento ficava preso na tela para sempre:
        toda nova tentativa repetia o mesmo 400."""
        c, _, balde = ambiente
        documento_id = _enviar(c, b"%PDF-1.4 nota")
        balde.clear()
        r = c.delete(f"/documentos/{documento_id}", headers=_cab())
        assert r.status_code == 200, r.text
        assert c.get("/documentos", headers=_cab()).json() == []

    def test_upload_apos_exclusao_nao_sobrescreve_o_documento_vivo(self, ambiente):
        """FALHA REPRODUZIDA — a CAUSA do 400 acima, e aqui ela é GARANTIDA,
        não eventual: o nome no Storage é determinístico
        ("2026-09-06_NF_0001.pdf"), montado só com data, categoria e a
        CONTAGEM de documentos vivos. Com 0001 e 0002 arquivados no mesmo dia
        e categoria, excluir o 0001 derruba a contagem para 1 e o upload
        seguinte nasce 0002 — o mesmo caminho do documento que continua na
        tela. O `x-upsert` sobrescreve calado e as duas linhas passam a
        apontar para o mesmo objeto."""
        c, engine, balde = ambiente
        primeiro = _enviar(c, b"conteudo-do-primeiro")
        segundo = _enviar(c, b"conteudo-do-segundo")
        caminho_segundo = _caminho(engine, segundo)
        assert c.delete(f"/documentos/{primeiro}", headers=_cab()).status_code == 200

        terceiro = _enviar(c, b"conteudo-do-terceiro")
        assert _caminho(engine, terceiro) != caminho_segundo, (
            "o terceiro upload reaproveitou o caminho de um documento vivo"
        )
        # O que o dono enxerga: o segundo documento continua sendo ELE mesmo.
        r = c.get(f"/documentos/{segundo}/download", headers=_cab())
        assert r.status_code == 200, r.text
        assert r.content == b"conteudo-do-segundo"
        assert balde[caminho_segundo] == b"conteudo-do-segundo"

        with Session(engine) as s:
            caminhos = [d.caminho_storage for d in s.exec(select(DocumentoArquivado)).all()]
        assert len(caminhos) == len(set(caminhos)), caminhos

        # E, consequência do que travava o usuário: os dois seguem excluíveis.
        for documento in c.get("/documentos", headers=_cab()).json():
            assert c.delete(f"/documentos/{documento['id']}", headers=_cab()).status_code == 200
        assert c.get("/documentos", headers=_cab()).json() == []

    def test_documento_antigo_que_divide_caminho_sai_sem_derrubar_o_irmao(self, ambiente):
        """Os documentos arquivados ANTES da correção acima já estão
        duplicados no banco de produção. Excluir um deles não pode apagar o
        arquivo que o outro ainda usa."""
        c, engine, balde = ambiente
        d1 = _enviar(c, b"conteudo-do-primeiro")
        d2 = _enviar(c, b"conteudo-do-segundo")
        with Session(engine) as s:  # simula o estado legado: mesmo caminho nos dois
            doc1 = s.get(DocumentoArquivado, d1)
            doc2 = s.get(DocumentoArquivado, d2)
            doc1.caminho_storage = doc2.caminho_storage
            s.add(doc1)
            s.commit()
            caminho = doc2.caminho_storage

        assert c.delete(f"/documentos/{d1}", headers=_cab()).status_code == 200
        assert caminho in balde, "o arquivo do irmão que ficou não pode ter sido apagado"
        assert c.get(f"/documentos/{d2}/download", headers=_cab()).status_code == 200

    def test_exclusao_normal_continua_apagando_o_arquivo_do_bucket(self, ambiente):
        """Caracterização: tolerar a falha do Storage não pode virar "nunca
        apaga o arquivo" — sem nenhum irmão apontando para o caminho, o objeto
        sai do bucket como sempre saiu."""
        c, _, balde = ambiente
        documento_id = _enviar(c, b"%PDF-1.4 nota")
        assert len(balde) == 1
        assert c.delete(f"/documentos/{documento_id}", headers=_cab()).status_code == 200
        assert balde == {}

    def test_documento_de_outra_fazenda_continua_dando_404(self, ambiente):
        """A tolerância acima é sobre o Storage, não sobre o tenant: documento
        de outra fazenda continua sendo 404 (nunca 403), e o arquivo dele
        continua no bucket."""
        c, engine, balde = ambiente
        documento_id = _enviar(c, b"%PDF-1.4 nota", fazenda_id=1)
        caminho = _caminho(engine, documento_id)
        assert c.delete(f"/documentos/{documento_id}", headers=_cab(2)).status_code == 404
        assert caminho in balde

    def test_sequencia_nao_se_confunde_entre_fazendas(self, ambiente):
        """Controle positivo do recorte por fazenda dentro da consulta que
        monta o caminho: cada fazenda tem a sua própria pasta e a sua própria
        sequência, e nenhuma enxerga a contagem da outra."""
        c, engine, _ = ambiente
        um = _enviar(c, b"da-fazenda-1", fazenda_id=1)
        dois = _enviar(c, b"da-fazenda-2", fazenda_id=2)
        assert _caminho(engine, um).startswith("fazenda-1/")
        assert _caminho(engine, dois).startswith("fazenda-2/")
        assert _caminho(engine, um) != _caminho(engine, dois)
