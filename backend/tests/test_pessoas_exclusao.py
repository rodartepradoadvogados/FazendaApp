"""
Cadastro > Pessoas — as duas exclusões que o dono relatou travadas em
06/09/2026: "não estou conseguindo excluir cadastro de pessoas e nem excluir
documento quando edito cadastro de pessoas".

Cada teste aqui nasceu ANTES da correção, reproduzindo a falha contra o
código de então (ver o relato de cada um no docstring). O fixture monta o
cenário de PRODUÇÃO, não o da suíte: uma fazenda de verdade, contrato ativo
e token com `fid` — sem isso a trava de porta (exigir_fazenda_selecionada) e
o `fazenda_id_seguro` das rotas não são exercidos como no ar.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, DecimoTerceiro, Fazenda, FeriasFuncionario,
    PessoaAnexo, ValeParcela,
)
from fazenda.models.planos import MODULOS_COMERCIAIS


@pytest.fixture
def client(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    monkeypatch.setattr(database, "engine", engine)

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
    # É esse 404 que travava a exclusão do documento.
    import fazenda.api.routers.cadastro.pessoas as pessoas_mod
    bucket: dict[str, bytes] = {}
    monkeypatch.setattr(pessoas_mod, "enviar_arquivo", lambda c, conteudo, *a, **k: bucket.__setitem__(c, conteudo))
    monkeypatch.setattr(pessoas_mod, "baixar_arquivo", lambda c, *a, **k: bucket[c])

    def _excluir_arquivo(caminho, *a, **k):
        if caminho not in bucket:
            raise RuntimeError("Falha ao excluir arquivo do Supabase Storage: 404 {'error':'not_found'}")
        bucket.pop(caminho)

    monkeypatch.setattr(pessoas_mod, "excluir_arquivo", _excluir_arquivo)

    with TestClient(main.app) as c:
        yield c, engine, bucket

    main.app.dependency_overrides.clear()


def _pessoa(c, nome="Leomir Bonfim") -> int:
    r = c.post("/cadastro/pessoas", json={"nome": nome, "tipos": ["Funcionário"]})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _anexar(c, pessoa_id: int, nome_arquivo: str, categoria: str = "RG") -> int:
    r = c.post(
        f"/cadastro/pessoas/{pessoa_id}/anexos",
        files={"file": (nome_arquivo, b"%PDF-1.4 documento", "application/pdf")},
        data={"categoria": categoria},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ferias(pessoa_id: int, status: str) -> FeriasFuncionario:
    return FeriasFuncionario(
        pessoa_id=pessoa_id, fazenda_id=1,
        periodo_aquisitivo_inicio=date(2025, 1, 1), periodo_aquisitivo_fim=date(2025, 12, 31),
        dias_gozados=30, data_inicio_gozo=date(2026, 1, 1), data_fim_gozo=date(2026, 1, 30),
        valor_ferias=3000.0, valor_terco_constitucional=1000.0, valor_total=4000.0, status=status,
    )


def _decimo(pessoa_id: int, status: str) -> DecimoTerceiro:
    return DecimoTerceiro(
        pessoa_id=pessoa_id, fazenda_id=1, ano=2025, parcela="unica", meses_trabalhados=12,
        valor_bruto=3000.0, valor_liquido=2800.0, status=status,
    )


class TestExcluirPessoa:
    def test_exclui_pessoa_sem_vinculo(self, client):
        c, _, _ = client
        pessoa_id = _pessoa(c)
        assert c.delete(f"/cadastro/pessoas/{pessoa_id}").status_code == 200
        assert not any(p["id"] == pessoa_id for p in c.get("/cadastro/pessoas").json())

    def test_ferias_canceladas_pela_rescisao_nao_bloqueiam_a_exclusao(self, client):
        """FALHA REPRODUZIDA: férias absorvidas por uma rescisão nunca são
        apagadas — o servidor só carimba status="cancelado_rescisao", para o
        cancelamento ser rastreável (ver FeriasFuncionario.status). A
        varredura de vínculos contava esse registro morto como vínculo vivo,
        então bastava a pessoa ter tido férias canceladas para ela virar
        não-excluível para sempre. Antes da correção: 409 "1 férias"."""
        c, engine, _ = client
        pessoa_id = _pessoa(c)
        with Session(engine) as s:
            s.add(_ferias(pessoa_id, "cancelado_rescisao"))
            s.commit()
        r = c.delete(f"/cadastro/pessoas/{pessoa_id}")
        assert r.status_code == 200, r.text

    def test_decimo_terceiro_cancelado_pela_rescisao_nao_bloqueia_a_exclusao(self, client):
        """Mesmo caso das férias — o 13º proporcional já entrou nas verbas
        rescisórias e o lançamento fica só como histórico cancelado."""
        c, engine, _ = client
        pessoa_id = _pessoa(c)
        with Session(engine) as s:
            s.add(_decimo(pessoa_id, "cancelado_rescisao"))
            s.commit()
        assert c.delete(f"/cadastro/pessoas/{pessoa_id}").status_code == 200

    def test_ferias_e_decimo_pendentes_continuam_bloqueando(self, client):
        """Caracterização: a trava legítima não pode ter afrouxado junto —
        lançamento VIVO continua impedindo a exclusão."""
        c, engine, _ = client
        for status in ("pendente", "pago"):
            pessoa_id = _pessoa(c, f"Fulano {status}")
            with Session(engine) as s:
                s.add(_ferias(pessoa_id, status))
                s.commit()
            r = c.delete(f"/cadastro/pessoas/{pessoa_id}")
            assert r.status_code == 409, f"{status}: {r.text}"

    def test_mensagem_do_409_nomeia_cada_vinculo_em_portugues_legivel(self, client):
        """A mensagem é a única coisa que o usuário tem para decidir entre
        desativar a pessoa e desfazer o vínculo. Antes o plural era montado
        grudando um "s" no rótulo e chegava na tela como "2 fériass"."""
        c, engine, _ = client
        pessoa_id = _pessoa(c, "Valéria Bonfim")
        with Session(engine) as s:
            s.add(_ferias(pessoa_id, "pendente"))
            s.add(_ferias(pessoa_id, "pago"))
            s.add(_decimo(pessoa_id, "pendente"))
            s.commit()
        detalhe = c.delete(f"/cadastro/pessoas/{pessoa_id}").json()["detail"]
        assert "Valéria Bonfim" in detalhe
        assert "2 períodos de férias" in detalhe
        assert "1 lançamento de 13º salário" in detalhe
        assert "fériass" not in detalhe
        assert "desative" in detalhe.lower()

    def test_parcela_de_vale_orfa_recusa_com_mensagem_em_vez_de_estourar(self, client):
        """ValeParcela.pessoa_id é FK para pessoa.id e estava fora da lista de
        vínculos: no Postgres de produção o DELETE estourava
        ForeignKeyViolation (500 com texto de banco na tela). Agora é o mesmo
        409 explicado dos demais vínculos."""
        c, engine, _ = client
        pessoa_id = _pessoa(c)
        with Session(engine) as s:
            s.add(ValeParcela(vale_id=999, pessoa_id=pessoa_id, competencia="2026-01", valor=100.0, fazenda_id=1))
            s.commit()
        r = c.delete(f"/cadastro/pessoas/{pessoa_id}")
        assert r.status_code == 409
        assert "parcela de vale" in r.json()["detail"]

    def test_documento_anexado_nao_impede_a_exclusao_da_pessoa(self, client):
        c, engine, bucket = client
        pessoa_id = _pessoa(c)
        _anexar(c, pessoa_id, "rg.pdf")
        bucket.clear()  # arquivo já sumiu do Storage — a cascata tem que tolerar
        assert c.delete(f"/cadastro/pessoas/{pessoa_id}").status_code == 200
        with Session(engine) as s:
            assert s.exec(select(PessoaAnexo).where(PessoaAnexo.pessoa_id == pessoa_id)).all() == []


class TestExcluirDocumentoDaPessoa:
    def test_exclui_documento_mesmo_com_o_arquivo_ausente_no_storage(self, client):
        """FALHA REPRODUZIDA (a que travou o dono): o arquivo não está mais no
        bucket (apagado à mão, upload interrompido, ou caminho duplicado — ver
        o teste seguinte), o Supabase responde 404 e `excluir_arquivo` levanta
        RuntimeError. O endpoint devolvia 400 e ABORTAVA antes de apagar a
        linha, então o documento ficava preso na tela para sempre: toda nova
        tentativa repetia o mesmo 400. Antes da correção: 400 e o anexo ainda
        listado."""
        c, _, bucket = client
        pessoa_id = _pessoa(c)
        anexo_id = _anexar(c, pessoa_id, "rg.pdf")
        bucket.clear()
        r = c.delete(f"/cadastro/pessoas/anexos/{anexo_id}")
        assert r.status_code == 200, r.text
        assert c.get(f"/cadastro/pessoas/{pessoa_id}/anexos").json() == []

    def test_dois_documentos_vivos_nunca_dividem_o_mesmo_caminho_no_storage(self, client):
        """FALHA REPRODUZIDA (a CAUSA do 400 acima, no fluxo real): o caminho
        vinha de `1 + len(existentes)`. Excluir um documento derruba a
        contagem, o upload seguinte reaproveita o número e — com o mesmo nome
        de arquivo, que é o normal em "anexei o RG errado, apago e anexo o
        certo" — gera um caminho IDÊNTICO ao de um anexo vivo. O `x-upsert`
        sobrescreve calado e as duas linhas passam a apontar para o mesmo
        objeto."""
        c, engine, bucket = client
        pessoa_id = _pessoa(c)
        primeiro = _anexar(c, pessoa_id, "rg.pdf")
        _anexar(c, pessoa_id, "cpf.pdf", categoria="CPF")
        assert c.delete(f"/cadastro/pessoas/anexos/{primeiro}").status_code == 200
        _anexar(c, pessoa_id, "cpf.pdf", categoria="CPF")  # mesmo nome do que ficou

        with Session(engine) as s:
            caminhos = [a.caminho_storage for a in s.exec(
                select(PessoaAnexo).where(PessoaAnexo.pessoa_id == pessoa_id)
            ).all()]
        assert len(caminhos) == len(set(caminhos)), caminhos
        assert len(bucket) == len(caminhos), (sorted(bucket), caminhos)

        # E, consequência do que travava o dono: os dois continuam excluíveis.
        for anexo in c.get(f"/cadastro/pessoas/{pessoa_id}/anexos").json():
            assert c.delete(f"/cadastro/pessoas/anexos/{anexo['id']}").status_code == 200
        assert c.get(f"/cadastro/pessoas/{pessoa_id}/anexos").json() == []

    def test_anexo_antigo_que_divide_caminho_sai_sem_derrubar_o_irmao(self, client):
        """Os anexos gravados ANTES da correção acima podem estar duplicados
        no banco de produção. Excluir um deles não pode apagar o arquivo que o
        outro ainda usa."""
        c, engine, bucket = client
        pessoa_id = _pessoa(c)
        a1 = _anexar(c, pessoa_id, "rg.pdf")
        a2 = _anexar(c, pessoa_id, "cpf.pdf", categoria="CPF")
        with Session(engine) as s:  # simula o estado legado: mesmo caminho nos dois
            anexo1 = s.get(PessoaAnexo, a1)
            anexo2 = s.get(PessoaAnexo, a2)
            anexo1.caminho_storage = anexo2.caminho_storage
            s.add(anexo1)
            s.commit()
            caminho = anexo2.caminho_storage

        assert c.delete(f"/cadastro/pessoas/anexos/{a1}").status_code == 200
        assert caminho in bucket, "o arquivo do irmão que ficou não pode ter sido apagado"
        r = c.get(f"/cadastro/pessoas/anexos/{a2}")
        assert r.status_code == 200, r.text

    def test_exclusao_normal_continua_apagando_o_arquivo_do_bucket(self, client):
        """Caracterização: tolerar a falha do Storage não pode virar "nunca
        apaga o arquivo" — sem nenhum irmão apontando para o caminho, o objeto
        sai do bucket como sempre saiu."""
        c, _, bucket = client
        pessoa_id = _pessoa(c)
        anexo_id = _anexar(c, pessoa_id, "holerite.pdf", categoria="Holerite")
        assert len(bucket) == 1
        assert c.delete(f"/cadastro/pessoas/anexos/{anexo_id}").status_code == 200
        assert bucket == {}

    def test_anexo_de_outra_fazenda_continua_dando_404(self, client):
        """A tolerância acima é sobre o Storage, não sobre o tenant: anexo de
        outra fazenda continua sendo 404 (nunca 403), como o resto do módulo."""
        c, engine, _ = client
        pessoa_id = _pessoa(c)
        anexo_id = _anexar(c, pessoa_id, "rg.pdf")
        with Session(engine) as s:
            anexo = s.get(PessoaAnexo, anexo_id)
            anexo.fazenda_id = 2
            s.add(anexo)
            s.commit()
        assert c.delete(f"/cadastro/pessoas/anexos/{anexo_id}").status_code == 404
