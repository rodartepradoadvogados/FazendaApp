"""
Comprovante de pagamento de vale (RH > Folha) — o MESMO defeito de colisão de
caminho no Storage que travou a exclusão de documento em Cadastro > Pessoas
(relato do dono, 06/09/2026), corrigido depois em pedidos.py e financeiro.py
e ainda intacto aqui, em cópia literal: `seq = 1 + len(existentes)` mais a
exclusão que virava 400 no RuntimeError do Storage antes de apagar a linha.

O fluxo real que quebra é o de sempre: "anexei o comprovante errado, apago e
anexo o certo" — o segundo envio costuma trazer o MESMO nome de arquivo
(comprovante.pdf, pix.pdf, o nome que o banco gera), e é aí que o caminho
sai idêntico ao de um comprovante que ainda existe.

Cada teste nasceu ANTES da correção, reproduzindo a falha contra o código de
então. TOKEN DE VERDADE (`criar_token`), nunca
`dependency_overrides[get_fazenda_atual_id]`: o isolamento entre fazendas
depende da claim do token e das próprias consultas.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, Fazenda, LancamentoAnexo, Pessoa, Usuario,
    UsuarioFazenda, ValeFuncionario,
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
            s.add(Pessoa(id=fid, nome=f"Funcionário {fid}", tipo="Funcionário", salario_base=3000.0, fazenda_id=fid))
            s.add(Usuario(
                id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True,
            ))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
            s.add(ValeFuncionario(
                id=fid, pessoa_id=fid, valor_total=500.0, forma_pagamento="pix",
                data_pagamento=date(2026, 8, 1), parcelas=1, competencia_inicio="2026-08",
                fazenda_id=fid,
            ))
        s.commit()

    # Supabase Storage falso — o `balde` é o disco, e apagar um caminho que
    # não está lá levanta RuntimeError EXATAMENTE como `excluir_arquivo`
    # levanta quando o Supabase responde 404 (ver rules/supabase_storage.py).
    # É esse 404 que travava a exclusão do comprovante.
    import fazenda.api.routers.cadastro.rh_folha as rh_folha_mod
    balde: dict[str, bytes] = {}

    def _baixar(caminho, *a, **k):
        if caminho not in balde:
            raise RuntimeError("Falha ao baixar arquivo do Supabase Storage: 404 {'error':'not_found'}")
        return balde[caminho]

    def _excluir(caminho, *a, **k):
        if caminho not in balde:
            raise RuntimeError("Falha ao excluir arquivo do Supabase Storage: 404 {'error':'not_found'}")
        balde.pop(caminho)

    monkeypatch.setattr(rh_folha_mod, "enviar_arquivo", lambda caminho, conteudo, *a, **k: balde.__setitem__(caminho, conteudo))
    monkeypatch.setattr(rh_folha_mod, "baixar_arquivo", _baixar)
    monkeypatch.setattr(rh_folha_mod, "excluir_arquivo", _excluir)

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


def _anexar(c, nome: str, conteudo: bytes = b"%PDF-1.4 comprovante", *, vale_id: int = 1, fazenda_id: int = 1) -> int:
    r = c.post(
        f"/cadastro/vales/funcionario/{vale_id}/comprovante",
        files={"file": (nome, conteudo, "application/pdf")},
        headers=_cab(fazenda_id),
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _listar(c, vale_id: int = 1, fazenda_id: int = 1) -> list[dict]:
    r = c.get(f"/cadastro/vales/funcionario/{vale_id}/comprovante", headers=_cab(fazenda_id))
    assert r.status_code == 200, r.text
    return r.json()


def _caminho(engine, anexo_id: int) -> str:
    with Session(engine) as s:
        return s.get(LancamentoAnexo, anexo_id).caminho_storage


class TestExcluirComprovanteDeVale:
    def test_exclui_comprovante_mesmo_com_o_arquivo_ausente_no_storage(self, ambiente):
        """FALHA REPRODUZIDA: o arquivo não está mais no bucket (apagado à mão
        no painel do Supabase, upload interrompido, ou caminho duplicado — ver
        o teste seguinte), o Supabase responde 404 e `excluir_arquivo` levanta
        RuntimeError. O endpoint devolvia 400 e ABORTAVA antes de apagar a
        linha, então o comprovante ficava preso na tela para sempre: toda
        nova tentativa repetia o mesmo 400."""
        c, _, balde = ambiente
        anexo_id = _anexar(c, "comprovante.pdf")
        balde.clear()
        r = c.delete(f"/cadastro/vales/comprovante/{anexo_id}", headers=_cab())
        assert r.status_code == 200, r.text
        assert _listar(c) == []

    def test_dois_comprovantes_vivos_nunca_dividem_o_mesmo_caminho(self, ambiente):
        """FALHA REPRODUZIDA (a CAUSA do 400 acima, no fluxo real): o caminho
        vinha de `1 + len(existentes)`. Excluir um comprovante derruba a
        contagem, o upload seguinte reaproveita o número e — com o mesmo nome
        de arquivo, que é o normal em "anexei o comprovante errado, apago e
        anexo o certo" — gera um caminho IDÊNTICO ao de um comprovante vivo.
        O `x-upsert` sobrescreve calado e as duas linhas passam a apontar
        para o mesmo objeto."""
        c, engine, balde = ambiente
        primeiro = _anexar(c, "comprovante.pdf", b"o-errado")
        segundo = _anexar(c, "pix.pdf", b"o-certo")
        caminho_segundo = _caminho(engine, segundo)
        assert c.delete(f"/cadastro/vales/comprovante/{primeiro}", headers=_cab()).status_code == 200

        terceiro = _anexar(c, "pix.pdf", b"o-terceiro")  # mesmo nome do que ficou
        assert _caminho(engine, terceiro) != caminho_segundo, (
            "o terceiro envio reaproveitou o caminho de um comprovante vivo"
        )
        r = c.get(f"/cadastro/vales/comprovante/{segundo}", headers=_cab())
        assert r.status_code == 200, r.text
        assert r.content == b"o-certo"
        assert balde[caminho_segundo] == b"o-certo"

        with Session(engine) as s:
            caminhos = [a.caminho_storage for a in s.exec(
                select(LancamentoAnexo).where(LancamentoAnexo.vale_funcionario_id == 1)
            ).all()]
        assert len(caminhos) == len(set(caminhos)), caminhos

        # E, consequência do que travava o usuário: os dois seguem excluíveis.
        for anexo in _listar(c):
            assert c.delete(f"/cadastro/vales/comprovante/{anexo['id']}", headers=_cab()).status_code == 200
        assert _listar(c) == []

    def test_comprovante_antigo_que_divide_caminho_sai_sem_derrubar_o_irmao(self, ambiente):
        """Os comprovantes gravados ANTES da correção acima já estão
        duplicados no banco de produção. Excluir um deles não pode apagar o
        arquivo que o outro ainda usa."""
        c, engine, balde = ambiente
        a1 = _anexar(c, "comprovante.pdf")
        a2 = _anexar(c, "pix.pdf")
        with Session(engine) as s:  # simula o estado legado: mesmo caminho nos dois
            anexo1 = s.get(LancamentoAnexo, a1)
            anexo2 = s.get(LancamentoAnexo, a2)
            anexo1.caminho_storage = anexo2.caminho_storage
            s.add(anexo1)
            s.commit()
            caminho = anexo2.caminho_storage

        assert c.delete(f"/cadastro/vales/comprovante/{a1}", headers=_cab()).status_code == 200
        assert caminho in balde, "o arquivo do irmão que ficou não pode ter sido apagado"
        assert c.get(f"/cadastro/vales/comprovante/{a2}", headers=_cab()).status_code == 200

    def test_exclusao_normal_continua_apagando_o_arquivo_do_bucket(self, ambiente):
        """Caracterização: tolerar a falha do Storage não pode virar "nunca
        apaga o arquivo" — sem nenhum irmão apontando para o caminho, o objeto
        sai do bucket como sempre saiu."""
        c, _, balde = ambiente
        anexo_id = _anexar(c, "comprovante.pdf")
        assert len(balde) == 1
        assert c.delete(f"/cadastro/vales/comprovante/{anexo_id}", headers=_cab()).status_code == 200
        assert balde == {}

    def test_comprovante_de_outra_fazenda_continua_dando_404(self, ambiente):
        """A tolerância acima é sobre o Storage, não sobre o tenant:
        comprovante de outra fazenda continua sendo 404 (nunca 403), e o
        arquivo dele continua no bucket."""
        c, engine, balde = ambiente
        anexo_id = _anexar(c, "comprovante.pdf", vale_id=1, fazenda_id=1)
        caminho = _caminho(engine, anexo_id)
        assert c.delete(f"/cadastro/vales/comprovante/{anexo_id}", headers=_cab(2)).status_code == 404
        assert caminho in balde
