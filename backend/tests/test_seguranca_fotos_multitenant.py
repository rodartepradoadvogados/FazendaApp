"""
Isolamento por fazenda no router de Fotos do campo.

Três furos, todos do mesmo padrão tolerante que a auditoria vem fechando:

  POST /fotos/upload
      Gravava com `get_fazenda_atual_id`. Token sem "fid" → foto nasce com
      `fazenda_id` NULO, e órfã passa por qualquer fazenda no
      `if fazenda_id is not None` espalhado pelo sistema. Mesmo defeito que o
      PR #703 fechou em cartao_credito.py::criar_cartao.

      No mesmo caminho, a busca do animal por `identificacao_animal` filtrava
      dentro de um `if`. `animal.numero` deixou de ser único globalmente na
      migração c24befa94c1b — "0042" existe em várias fazendas ao mesmo tempo
      —, então sem a cláusula a foto era vinculada ao animal de OUTRA fazenda.

  GET /fotos/{id}/arquivo  e  DELETE /fotos/{id}
      Checagem de posse `if fazenda_id is not None and foto.fazenda_id !=
      fazenda_id`, feita sobre o objeto já carregado por `session.get()`. Com
      `fazenda_id` nulo ela não comparava nada.

DUAS CAMADAS, MEDIDAS SEPARADAMENTE. A trava de porta
(`auth.py::exigir_fazenda_selecionada`, montada no router em main.py via
`_protegido`) já recusa o token sem "fid" antes de chegar na rota — então um
teste que só mande o token sem "fid" fica VERDE mesmo com a guarda da rota
revertida, porque nunca chega lá. É o falso verde que o PR #703 encontrou e
desarmou. Aqui cada camada tem o seu teste: os `test_trava_de_porta_*`
aferem a porta, e os `test_guarda_da_rota_*` desligam a porta de propósito
para aferir a rota por dentro.

Token real (`criar_token`), nunca `dependency_overrides` de
`get_fazenda_atual_id` — override testaria a rota contra uma dependência
falsa e não prova nada sobre o token de verdade.
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
    Animal, ContratoFazenda, ContratoFazendaModulo, Fazenda, FotoCampo, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

UMA_IMAGEM = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes com um admin cada; um animal com o MESMO número
    nas duas (o que a migração c24befa94c1b passou a permitir); uma foto da
    fazenda 1 (a vítima) e uma foto ÓRFÃ, sem fazenda nenhuma.

    `admin_duplo` tem vínculo com as DUAS fazendas de propósito: com vínculo
    único, `resolver_fazenda_id_escrita` resolve a fazenda sozinha e o teste
    de token-sem-"fid" não mediria o que pretende medir.
    """
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    ids: dict[str, int] = {}
    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Alvo"))
        s.add(Fazenda(id=2, nome="Fazenda Atacante"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(
                id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True,
            ))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))

        s.add(Usuario(
            id=9, username="admin_duplo", senha_hash=hash_senha("x"), papel="admin", ativo=True,
        ))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=2))

        # O MESMO número de animal nas duas fazendas.
        animal_1 = Animal(numero="0042", fazenda_id=1)
        animal_2 = Animal(numero="0042", fazenda_id=2)
        foto_vitima = FotoCampo(
            fazenda_id=1, caminho_storage="fazenda-1/2026-09-06-0001.png",
            mime_type="image/png", tamanho_bytes=len(UMA_IMAGEM), descricao="foto da fazenda 1",
        )
        foto_orfa = FotoCampo(
            fazenda_id=None, caminho_storage="geral/2026-09-06-0001.png",
            mime_type="image/png", tamanho_bytes=len(UMA_IMAGEM), descricao="foto sem dono",
        )
        s.add_all([animal_1, animal_2, foto_vitima, foto_orfa])
        s.commit()
        for obj, chave in (
            (animal_1, "animal_f1"), (animal_2, "animal_f2"),
            (foto_vitima, "foto_vitima"), (foto_orfa, "foto_orfa"),
        ):
            s.refresh(obj)
            ids[chave] = obj.id

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(username: str, fazenda_id: int | None = None):
    return {"Authorization": f"Bearer {criar_token(username, fazenda_id=fazenda_id)}"}


def _desligar_trava_de_porta():
    """Desarma `exigir_fazenda_selecionada` para medir a guarda da ROTA.

    Sem isto, todo teste de token-sem-"fid" fica verde mesmo com a correção
    revertida — a porta barra antes e a rota nunca é exercida. Não é conforto
    de teste: é o que separa "a porta está fechada" de "a rota se defende".
    """
    import main
    main.app.dependency_overrides[main._fazenda_selecionada[0].dependency] = lambda: None


# ---------------------------------------------------------------------------
# Camada 1 — a trava de porta
# ---------------------------------------------------------------------------
def test_trava_de_porta_recusa_token_sem_fazenda(ambiente):
    """Com fazenda cadastrada no banco, token sem "fid" não entra no router
    de Fotos — em nenhum dos três verbos."""
    c, _engine, ids = ambiente
    cab = _cab("admin_duplo")
    assert c.get("/fotos").status_code in (401, 403, 409)
    assert c.get("/fotos", headers=cab).status_code == 409
    assert c.get(f"/fotos/{ids['foto_vitima']}/arquivo", headers=cab).status_code == 409
    assert c.delete(f"/fotos/{ids['foto_vitima']}", headers=cab).status_code == 409


# ---------------------------------------------------------------------------
# Camada 2 — a guarda da própria rota, com a porta desarmada
# ---------------------------------------------------------------------------
def test_guarda_da_rota_nao_baixa_foto_de_outra_fazenda(ambiente):
    """A fazenda 2 pede o arquivo da foto da fazenda 1 pelo id."""
    c, _engine, ids = ambiente
    r = c.get(f"/fotos/{ids['foto_vitima']}/arquivo", headers=_cab("admin2", 2))
    assert r.status_code == 404, (
        "a foto de outra fazenda foi baixada pelo id. "
        f"Resposta: {r.status_code} {r.text[:200]}"
    )


def test_guarda_da_rota_nao_baixa_foto_orfa(ambiente):
    """Foto com `fazenda_id` nulo não é de ninguém — e por isso mesmo não
    pode ser de qualquer um. Filtrando na consulta, "de outra fazenda" e "sem
    fazenda" caem no mesmo lugar: não encontrado."""
    c, _engine, ids = ambiente
    for fazenda in (1, 2):
        r = c.get(f"/fotos/{ids['foto_orfa']}/arquivo", headers=_cab(f"admin{fazenda}", fazenda))
        assert r.status_code == 404, f"fazenda {fazenda}: {r.status_code} {r.text[:200]}"


def test_guarda_da_rota_baixar_sem_fid_nao_alcanca_foto_alheia(ambiente):
    """O furo original: `if fazenda_id is not None and ...` não comparava
    nada com `fazenda_id` nulo, e qualquer foto era baixada pelo id."""
    c, _engine, ids = ambiente
    _desligar_trava_de_porta()
    r = c.get(f"/fotos/{ids['foto_vitima']}/arquivo", headers=_cab("admin_duplo"))
    assert r.status_code == 404, (
        "com token sem fazenda, a rota entregou a foto de outra fazenda. "
        f"Resposta: {r.status_code} {r.text[:200]}"
    )


def test_guarda_da_rota_nao_exclui_foto_de_outra_fazenda(ambiente):
    """404 e a linha continua no banco — não basta responder erro."""
    c, engine, ids = ambiente
    r = c.delete(f"/fotos/{ids['foto_vitima']}", headers=_cab("admin2", 2))
    assert r.status_code == 404, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(FotoCampo, ids["foto_vitima"]) is not None, "a foto da vítima foi excluída"


def test_guarda_da_rota_excluir_sem_fid_recusa_em_vez_de_nao_achar(ambiente):
    """Exclusão é escrita, e escrita usa o resolvedor ESTRITO.

    Exige 409 e não "404 ou 409" de propósito. A consulta filtrada de
    `_foto_da_fazenda` sozinha já devolveria 404 aqui (com `fazenda_id` nulo
    ela procura por `fazenda_id IS NULL`, e a foto da vítima é da fazenda 1)
    — então um teste que aceitasse 404 passaria mesmo com o resolvedor
    tolerante de volta, e não mediria nada. Aferido revertendo: com
    `get_fazenda_atual_id`, este teste fica vermelho.

    E 409 é a resposta certa, não um detalhe: o usuário tem duas fazendas e
    não disse em qual está. "Não encontrado" mentiria sobre a causa; o que
    falta é escolher a fazenda."""
    c, engine, ids = ambiente
    _desligar_trava_de_porta()
    r = c.delete(f"/fotos/{ids['foto_vitima']}", headers=_cab("admin_duplo"))
    assert r.status_code == 409, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(FotoCampo, ids["foto_vitima"]) is not None, "a foto da vítima foi excluída"


def test_dono_da_foto_continua_baixando_e_excluindo(ambiente, monkeypatch):
    """Controle positivo. Sem ele, uma rota que responde 404 para todo mundo
    passaria em todos os testes acima."""
    c, engine, ids = ambiente
    import fazenda.api.routers.fotos as fotos_mod
    monkeypatch.setattr(fotos_mod, "baixar_arquivo", lambda *a, **k: UMA_IMAGEM)
    monkeypatch.setattr(fotos_mod, "excluir_arquivo", lambda *a, **k: None)

    r = c.get(f"/fotos/{ids['foto_vitima']}/arquivo", headers=_cab("admin1", 1))
    assert r.status_code == 200, f"o dono não conseguiu baixar: {r.status_code} {r.text[:200]}"
    assert r.content == UMA_IMAGEM

    r = c.delete(f"/fotos/{ids['foto_vitima']}", headers=_cab("admin1", 1))
    assert r.status_code == 200, f"o dono não conseguiu excluir: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(FotoCampo, ids["foto_vitima"]) is None


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def test_upload_sem_fid_nao_grava_foto_orfa(ambiente, monkeypatch):
    """Com a porta desarmada, o upload não pode gravar `fazenda_id` nulo:
    órfã passa por qualquer fazenda no padrão tolerante do resto do sistema."""
    c, engine, _ids = ambiente
    import fazenda.api.routers.fotos as fotos_mod
    monkeypatch.setattr(fotos_mod, "enviar_arquivo", lambda *a, **k: None)
    _desligar_trava_de_porta()

    antes = _quantas_orfas(engine)
    r = c.post(
        "/fotos/upload",
        headers=_cab("admin_duplo"),
        files={"file": ("f.png", UMA_IMAGEM, "image/png")},
        data={"descricao": "sem fazenda"},
    )
    assert r.status_code != 201, f"a foto órfã foi criada. Resposta: {r.status_code} {r.text[:200]}"
    assert _quantas_orfas(engine) == antes, "nasceu foto com fazenda_id nulo"


def test_upload_vincula_o_animal_da_propria_fazenda(ambiente, monkeypatch):
    """As duas fazendas têm um animal "0042" (a migração c24befa94c1b tirou a
    unicidade global de `animal.numero`). A foto da fazenda 2 tem que apontar
    para o animal DELA.

    REGISTRO HONESTO DO ALCANCE: este teste passa igual com a consulta do
    animal revertida ao `if fazenda_id is not None` de antes — aferido. Com
    token que traz "fid", o `if` é verdadeiro e o filtro é aplicado do mesmo
    jeito; o único caminho que exploraria o `if` é o token sem "fid", e esse
    caminho o resolvedor estrito do upload já fechou (o teste acima). A
    troca por cláusula na consulta é defesa em profundidade, não uma correção
    com cenário observável próprio — o que este teste prova é o vínculo
    correto na presença de homônimo entre fazendas, que é o que ele diz."""
    c, engine, ids = ambiente
    import fazenda.api.routers.fotos as fotos_mod
    monkeypatch.setattr(fotos_mod, "enviar_arquivo", lambda *a, **k: None)

    r = c.post(
        "/fotos/upload",
        headers=_cab("admin2", 2),
        files={"file": ("f.png", UMA_IMAGEM, "image/png")},
        data={"identificacao_animal": "0042", "tipo_assunto": "animal"},
    )
    assert r.status_code == 201, f"Resposta: {r.status_code} {r.text[:200]}"
    assert r.json()["animal_id"] == ids["animal_f2"], (
        "a foto da fazenda 2 foi vinculada ao animal de outra fazenda com o mesmo número"
    )
    with Session(engine) as s:
        nova = s.get(FotoCampo, r.json()["id"])
        assert nova.fazenda_id == 2


def _quantas_orfas(engine) -> int:
    with Session(engine) as s:
        return len(s.exec(select(FotoCampo).where(FotoCampo.fazenda_id.is_(None))).all())
