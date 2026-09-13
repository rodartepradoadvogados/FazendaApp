"""
Fotos do campo — o MESMO defeito de colisão de caminho no Storage que travou
a exclusão de documento em Cadastro > Pessoas (relato do dono, 06/09/2026),
corrigido depois em pedidos.py e financeiro.py e ainda intacto aqui.

AQUI ELE É PIOR, exatamente como em documentos.py: o nome gravado no Storage
é DETERMINÍSTICO ("2026-09-06_0001.jpg" — data e sequência, sem o nome do
arquivo enviado). Nos outros módulos a colisão dependia de o usuário repetir
o nome do arquivo; no app móvel ela é GARANTIDA: com 0001 e 0002 no mesmo
dia, excluir a 0001 faz a próxima foto nascer 0002 e sobrescrever, via
`x-upsert`, o arquivo da foto que continua viva na galeria — e o peão que
manda três fotos por dia da mesma cerca cai nisso na primeira exclusão.

Cada teste nasceu ANTES da correção, reproduzindo a falha contra o código de
então. TOKEN DE VERDADE (`criar_token`), nunca
`dependency_overrides[get_fazenda_atual_id]`: o isolamento entre fazendas
depende da claim do token e das próprias consultas.
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
    ContratoFazenda, ContratoFazendaModulo, Fazenda, FotoCampo, Usuario, UsuarioFazenda,
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
                id=fid, username=f"peao{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True,
            ))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
        s.commit()

    # Supabase Storage falso — o `balde` é o disco, e apagar um caminho que
    # não está lá levanta RuntimeError EXATAMENTE como `excluir_arquivo`
    # levanta quando o Supabase responde 404 (ver rules/supabase_storage.py).
    import fazenda.api.routers.fotos as fotos_mod
    balde: dict[str, bytes] = {}

    def _baixar(caminho, *a, **k):
        if caminho not in balde:
            raise RuntimeError("Falha ao baixar arquivo do Supabase Storage: 404 {'error':'not_found'}")
        return balde[caminho]

    def _excluir(caminho, *a, **k):
        if caminho not in balde:
            raise RuntimeError("Falha ao excluir arquivo do Supabase Storage: 404 {'error':'not_found'}")
        balde.pop(caminho)

    monkeypatch.setattr(fotos_mod, "enviar_arquivo", lambda caminho, conteudo, *a, **k: balde.__setitem__(caminho, conteudo))
    monkeypatch.setattr(fotos_mod, "baixar_arquivo", _baixar)
    monkeypatch.setattr(fotos_mod, "excluir_arquivo", _excluir)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, balde
    main.app.dependency_overrides.clear()


def _cab(fazenda_id: int = 1) -> dict:
    """Token REAL do peão daquela fazenda, com a claim "fid" carimbada."""
    return {"Authorization": f"Bearer {criar_token(f'peao{fazenda_id}', fazenda_id=fazenda_id)}"}


def _enviar(c, conteudo: bytes, *, descricao: str = "cerca do pasto 3", fazenda_id: int = 1) -> int:
    r = c.post(
        "/fotos/upload",
        files={"file": ("foto.jpg", conteudo, "image/jpeg")},
        data={"descricao": descricao},
        headers=_cab(fazenda_id),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _caminho(engine, foto_id: int) -> str:
    with Session(engine) as s:
        return s.get(FotoCampo, foto_id).caminho_storage


class TestExcluirFotoDoCampo:
    def test_exclui_foto_mesmo_com_o_arquivo_ausente_no_storage(self, ambiente):
        """FALHA REPRODUZIDA: o arquivo não está mais no bucket (apagado à mão
        no painel do Supabase, upload interrompido pela fila offline do app,
        ou caminho sobrescrito — ver o teste seguinte), o Supabase responde
        404 e `excluir_arquivo` levanta RuntimeError. O endpoint devolvia 400
        e ABORTAVA antes de apagar a linha, então a foto ficava presa na
        galeria para sempre."""
        c, _, balde = ambiente
        foto_id = _enviar(c, b"bytes-da-foto")
        balde.clear()
        r = c.delete(f"/fotos/{foto_id}", headers=_cab())
        assert r.status_code == 200, r.text
        assert c.get("/fotos", headers=_cab()).json() == []

    def test_upload_apos_exclusao_nao_sobrescreve_a_foto_viva(self, ambiente):
        """FALHA REPRODUZIDA — a CAUSA do 400 acima, e aqui ela é GARANTIDA,
        não eventual: o nome no Storage é determinístico ("2026-09-06_0001.jpg"),
        montado só com a data e a CONTAGEM de fotos vivas do dia. Com 0001 e
        0002 no mesmo dia, excluir a 0001 derruba a contagem para 1 e a foto
        seguinte nasce 0002 — o mesmo caminho da que continua na galeria. O
        `x-upsert` sobrescreve calado e as duas linhas passam a apontar para o
        mesmo objeto."""
        c, engine, balde = ambiente
        primeira = _enviar(c, b"bytes-da-primeira")
        segunda = _enviar(c, b"bytes-da-segunda")
        caminho_segunda = _caminho(engine, segunda)
        assert c.delete(f"/fotos/{primeira}", headers=_cab()).status_code == 200

        terceira = _enviar(c, b"bytes-da-terceira")
        assert _caminho(engine, terceira) != caminho_segunda, (
            "a terceira foto reaproveitou o caminho de uma foto viva"
        )
        # O que o peão enxerga: a segunda foto continua sendo ELA mesma.
        r = c.get(f"/fotos/{segunda}/arquivo", headers=_cab())
        assert r.status_code == 200, r.text
        assert r.content == b"bytes-da-segunda"
        assert balde[caminho_segunda] == b"bytes-da-segunda"

        with Session(engine) as s:
            caminhos = [f.caminho_storage for f in s.exec(select(FotoCampo)).all()]
        assert len(caminhos) == len(set(caminhos)), caminhos

        # E, consequência do que travava o usuário: as duas seguem excluíveis.
        for foto in c.get("/fotos", headers=_cab()).json():
            assert c.delete(f"/fotos/{foto['id']}", headers=_cab()).status_code == 200
        assert c.get("/fotos", headers=_cab()).json() == []

    def test_foto_antiga_que_divide_caminho_sai_sem_derrubar_a_irma(self, ambiente):
        """As fotos enviadas ANTES da correção acima já estão duplicadas no
        banco de produção. Excluir uma delas não pode apagar o arquivo que a
        outra ainda usa."""
        c, engine, balde = ambiente
        f1 = _enviar(c, b"bytes-da-primeira")
        f2 = _enviar(c, b"bytes-da-segunda")
        with Session(engine) as s:  # simula o estado legado: mesmo caminho nas duas
            foto1 = s.get(FotoCampo, f1)
            foto2 = s.get(FotoCampo, f2)
            foto1.caminho_storage = foto2.caminho_storage
            s.add(foto1)
            s.commit()
            caminho = foto2.caminho_storage

        assert c.delete(f"/fotos/{f1}", headers=_cab()).status_code == 200
        assert caminho in balde, "o arquivo da irmã que ficou não pode ter sido apagado"
        assert c.get(f"/fotos/{f2}/arquivo", headers=_cab()).status_code == 200

    def test_exclusao_normal_continua_apagando_o_arquivo_do_bucket(self, ambiente):
        """Caracterização: tolerar a falha do Storage não pode virar "nunca
        apaga o arquivo" — sem nenhuma irmã apontando para o caminho, o objeto
        sai do bucket como sempre saiu."""
        c, _, balde = ambiente
        foto_id = _enviar(c, b"bytes-da-foto")
        assert len(balde) == 1
        assert c.delete(f"/fotos/{foto_id}", headers=_cab()).status_code == 200
        assert balde == {}

    def test_foto_de_outra_fazenda_continua_dando_404(self, ambiente):
        """A tolerância acima é sobre o Storage, não sobre o tenant: foto de
        outra fazenda continua sendo 404 (nunca 403), e o arquivo dela
        continua no bucket."""
        c, engine, balde = ambiente
        foto_id = _enviar(c, b"bytes-da-foto", fazenda_id=1)
        caminho = _caminho(engine, foto_id)
        assert c.delete(f"/fotos/{foto_id}", headers=_cab(2)).status_code == 404
        assert caminho in balde

    def test_sequencia_nao_se_confunde_entre_fazendas(self, ambiente):
        """Controle positivo do recorte por fazenda dentro da consulta que
        monta o caminho: cada fazenda tem a sua própria pasta e a sua própria
        sequência do dia, e nenhuma enxerga a contagem da outra."""
        c, engine, _ = ambiente
        uma = _enviar(c, b"da-fazenda-1", fazenda_id=1)
        outra = _enviar(c, b"da-fazenda-2", fazenda_id=2)
        assert _caminho(engine, uma).startswith("fazenda-1/")
        assert _caminho(engine, outra).startswith("fazenda-2/")
        assert _caminho(engine, uma) != _caminho(engine, outra)
