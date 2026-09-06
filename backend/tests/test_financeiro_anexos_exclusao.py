"""
Anexos de lançamento (boleto, nota fiscal, comprovante) — o MESMO defeito que
travou a exclusão de documento em Cadastro > Pessoas (relato do dono,
06/09/2026; ver test_pessoas_exclusao.py), que existia copiado aqui.

Cada teste nasceu ANTES da correção, reproduzindo a falha contra o código de
então. O fixture monta o cenário de PRODUÇÃO, não o da suíte: fazenda de
verdade com contrato ativo, para que a trava de porta
(exigir_fazenda_selecionada) e o `fazenda_id_seguro` das rotas sejam
exercidos como no ar.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
import fazenda.models  # noqa: F401 — registra as tabelas antes do create_all
from fazenda.models import (
    ContaGerencial, ContratoFazenda, ContratoFazendaModulo, Fazenda, LancamentoAnexo,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Jairo Nasser"))
        s.add(ContratoFazenda(fazenda_id=1, status="ativo"))
        for modulo in MODULOS_COMERCIAIS:
            s.add(ContratoFazendaModulo(fazenda_id=1, modulo=modulo, preco=0.0, ativo=True))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(database, "engine", engine)
    main.app.dependency_overrides[database.get_session] = _get_session_override

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "dono@example.com"
        permissoes = ""

    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1

    # Supabase Storage falso — o `bucket` é o disco, e apagar um caminho que
    # não está lá levanta RuntimeError EXATAMENTE como `excluir_arquivo`
    # levanta quando o Supabase responde 404 (ver rules/supabase_storage.py).
    # É esse 404 que travava a exclusão do anexo.
    import fazenda.api.routers.financeiro as financeiro_mod
    bucket: dict[str, bytes] = {}
    monkeypatch.setattr(financeiro_mod, "enviar_arquivo", lambda c, conteudo, *a, **k: bucket.__setitem__(c, conteudo))
    monkeypatch.setattr(financeiro_mod, "baixar_arquivo", lambda c, *a, **k: bucket[c])

    def _excluir_arquivo(caminho, *a, **k):
        if caminho not in bucket:
            raise RuntimeError("Falha ao excluir arquivo do Supabase Storage: 404 {'error':'not_found'}")
        bucket.pop(caminho)

    monkeypatch.setattr(financeiro_mod, "excluir_arquivo", _excluir_arquivo)

    with TestClient(main.app) as c:
        yield c, engine, bucket

    main.app.dependency_overrides.clear()


def _lancamento(engine, numero="LAN-2026-0001") -> str:
    with Session(engine) as s:
        s.add(ContaGerencial(
            numero_lancamento=numero,
            codigo_conta="3.01.01.01",
            descricao="Compra de ração",
            data_vencimento=date(2026, 7, 10),
            data_competencia=date(2026, 7, 1),
            fornecedor_cliente="Fornecedor Teste",
            valor_total=1000.0,
            tipo="despesa",
            fazenda_id=1,
        ))
        s.commit()
    return numero


def _anexar(c, numero: str, nome_arquivo: str) -> int:
    r = c.post(
        f"/financeiro/lancamentos/{numero}/anexos",
        files={"file": (nome_arquivo, b"%PDF-1.4 documento", "application/pdf")},
        data={"categoria": "Boleto"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


class TestExcluirAnexoDeLancamento:
    def test_exclui_anexo_mesmo_com_o_arquivo_ausente_no_storage(self, client):
        """FALHA REPRODUZIDA: o arquivo não está mais no bucket (apagado à mão,
        upload interrompido, ou caminho duplicado — ver o teste seguinte), o
        Supabase responde 404 e `excluir_arquivo` levanta RuntimeError. O
        endpoint devolvia 400 e ABORTAVA antes de apagar a linha, então o
        anexo ficava preso na tela para sempre: toda nova tentativa repetia o
        mesmo 400. Antes da correção: 400 e o anexo ainda listado."""
        c, engine, bucket = client
        numero = _lancamento(engine)
        anexo_id = _anexar(c, numero, "boleto.pdf")
        bucket.clear()
        r = c.delete(f"/financeiro/anexos/{anexo_id}")
        assert r.status_code == 200, r.text
        assert c.get(f"/financeiro/lancamentos/{numero}/anexos").json() == []

    def test_dois_anexos_vivos_nunca_dividem_o_mesmo_caminho_no_storage(self, client):
        """FALHA REPRODUZIDA (a CAUSA do 400 acima, no fluxo real): o caminho
        vinha de `1 + len(existentes)`. Excluir um anexo derruba a contagem, o
        upload seguinte reaproveita o número e — com o mesmo nome de arquivo,
        que é o normal em "anexei o boleto errado, apago e anexo o certo" —
        gera um caminho IDÊNTICO ao de um anexo vivo. O `x-upsert` sobrescreve
        calado e as duas linhas passam a apontar para o mesmo objeto."""
        c, engine, bucket = client
        numero = _lancamento(engine)
        primeiro = _anexar(c, numero, "boleto.pdf")
        _anexar(c, numero, "nota.pdf")
        assert c.delete(f"/financeiro/anexos/{primeiro}").status_code == 200
        _anexar(c, numero, "nota.pdf")  # mesmo nome do que ficou

        with Session(engine) as s:
            caminhos = [a.caminho_storage for a in s.exec(
                select(LancamentoAnexo).where(LancamentoAnexo.numero_lancamento == numero)
            ).all()]
        assert len(caminhos) == len(set(caminhos)), caminhos
        assert len(bucket) == len(caminhos), (sorted(bucket), caminhos)

        # E, consequência do que travava o usuário: os dois seguem excluíveis.
        for anexo in c.get(f"/financeiro/lancamentos/{numero}/anexos").json():
            assert c.delete(f"/financeiro/anexos/{anexo['id']}").status_code == 200
        assert c.get(f"/financeiro/lancamentos/{numero}/anexos").json() == []

    def test_anexo_antigo_que_divide_caminho_sai_sem_derrubar_o_irmao(self, client):
        """Os anexos gravados ANTES da correção acima podem estar duplicados no
        banco de produção — e o comprovante em lote (ver
        anexar_comprovante_em_lote) divide caminho de propósito. Excluir uma
        das linhas não pode apagar o arquivo que a outra ainda usa."""
        c, engine, bucket = client
        numero = _lancamento(engine)
        a1 = _anexar(c, numero, "boleto.pdf")
        a2 = _anexar(c, numero, "nota.pdf")
        with Session(engine) as s:  # simula o estado legado: mesmo caminho nos dois
            anexo1 = s.get(LancamentoAnexo, a1)
            anexo2 = s.get(LancamentoAnexo, a2)
            anexo1.caminho_storage = anexo2.caminho_storage
            s.add(anexo1)
            s.commit()
            caminho = anexo2.caminho_storage

        assert c.delete(f"/financeiro/anexos/{a1}").status_code == 200
        assert caminho in bucket, "o arquivo do irmão que ficou não pode ter sido apagado"
        assert c.get(f"/financeiro/anexos/{a2}").status_code == 200

    def test_exclusao_normal_continua_apagando_o_arquivo_do_bucket(self, client):
        """Caracterização: tolerar a falha do Storage não pode virar "nunca
        apaga o arquivo" — sem nenhum irmão apontando para o caminho, o objeto
        sai do bucket como sempre saiu."""
        c, engine, bucket = client
        numero = _lancamento(engine)
        anexo_id = _anexar(c, numero, "boleto.pdf")
        assert len(bucket) == 1
        assert c.delete(f"/financeiro/anexos/{anexo_id}").status_code == 200
        assert bucket == {}

    def test_anexo_de_outra_fazenda_continua_dando_404(self, client):
        """A tolerância acima é sobre o Storage, não sobre o tenant: anexo de
        outra fazenda continua sendo 404 (nunca 403), como o resto do módulo."""
        c, engine, _ = client
        numero = _lancamento(engine)
        anexo_id = _anexar(c, numero, "boleto.pdf")
        with Session(engine) as s:
            anexo = s.get(LancamentoAnexo, anexo_id)
            anexo.fazenda_id = 2
            s.add(anexo)
            s.commit()
        assert c.delete(f"/financeiro/anexos/{anexo_id}").status_code == 404
