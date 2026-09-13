"""
Achado 37 da auditoria (crítico): PUT /alimentacao/dietas/{id}/encerrar.

Qualquer usuário autenticado de qualquer fazenda encerrava a dieta ATIVA de
outro tenant só adivinhando o `dieta_id` — id inteiro pequeno e sequencial.
Encerrar a dieta da vítima interrompe a baixa automática de estoque e a
apuração dela; é um estrago silencioso, que só aparece no fechamento do mês.

A rota já tinha ganhado uma checagem de posse, mas no padrão TOLERANTE:
`if not dieta or (fazenda_id is not None and dieta.fazenda_id != fazenda_id)`
sobre o objeto carregado por `session.get()`. Com `fazenda_id` nulo — token
sem "fid" — a condição não compara nada. Agora o recorte entra na própria
consulta e a dependência de escrita é a estrita.

DUAS CAMADAS, MEDIDAS SEPARADAMENTE (mesma razão de
test_seguranca_fotos_multitenant.py): a trava de porta recusa o token sem
"fid" antes da rota, então um teste que só mande esse token fica verde mesmo
com a correção revertida.

REGISTRO HONESTO DO ALCANCE, aferido revertendo cada metade em separado:

  • trocar o resolvedor de volta para `get_fazenda_atual_id` deixa
    `test_guarda_da_rota_sem_fid_recusa_em_vez_de_encerrar` VERMELHO. Essa
    metade é a que carrega a correção.

  • devolver o recorte para o `if` sobre o objeto carregado NÃO quebra teste
    nenhum, e não tem como quebrar: com o resolvedor estrito, `fazenda_id`
    nunca é nulo, e aí `fazenda_id is not None and dieta.fazenda_id !=
    fazenda_id` volta a comparar de verdade — inclusive contra a dieta órfã
    (`None != 1`). Passar o recorte para dentro da consulta é defesa em
    profundidade sem cenário observável próprio: vale porque não depende do
    resolvedor continuar estrito amanhã, não porque feche um furo hoje.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from fazenda.auth import criar_token, hash_senha
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo, DietaLancamento, Fazenda, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

ROTA = "/alimentacao/dietas/{}/encerrar"
CORPO = {"data_efetivo_encerramento": date(2026, 9, 30).isoformat()}


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

        # Dois vínculos de propósito: com vínculo único,
        # `resolver_fazenda_id_escrita` resolveria a fazenda sozinha e o
        # teste de token-sem-"fid" não mediria o que pretende.
        s.add(Usuario(id=9, username="admin_duplo", senha_hash=hash_senha("x"), papel="admin", ativo=True))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=2))

        dieta_vitima = DietaLancamento(lote="Lote 1", data_abertura=date(2026, 1, 1), fazenda_id=1)
        dieta_orfa = DietaLancamento(lote="Lote sem dono", data_abertura=date(2026, 1, 1), fazenda_id=None)
        s.add_all([dieta_vitima, dieta_orfa])
        s.commit()
        for obj, chave in ((dieta_vitima, "vitima"), (dieta_orfa, "orfa")):
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
    import main
    main.app.dependency_overrides[main._fazenda_selecionada[0].dependency] = lambda: None


def _encerrada(engine, dieta_id: int) -> bool:
    with Session(engine) as s:
        return s.get(DietaLancamento, dieta_id).data_efetivo_encerramento is not None


def test_trava_de_porta_recusa_token_sem_fazenda(ambiente):
    c, _engine, ids = ambiente
    r = c.put(ROTA.format(ids["vitima"]), json=CORPO, headers=_cab("admin_duplo"))
    assert r.status_code == 409, f"Resposta: {r.status_code} {r.text[:200]}"


def test_guarda_da_rota_nao_encerra_dieta_de_outra_fazenda(ambiente):
    """O cenário do achado: a fazenda 2 encerra a dieta da fazenda 1."""
    c, engine, ids = ambiente
    r = c.put(ROTA.format(ids["vitima"]), json=CORPO, headers=_cab("admin2", 2))
    assert r.status_code == 404, f"Resposta: {r.status_code} {r.text[:200]}"
    assert not _encerrada(engine, ids["vitima"]), "a dieta da vítima foi encerrada"


def test_guarda_da_rota_nao_encerra_dieta_orfa(ambiente):
    """Dieta com `fazenda_id` nulo não é de ninguém — e por isso não pode ser
    de qualquer um. Filtrando na consulta, "de outra fazenda" e "sem fazenda"
    caem no mesmo lugar."""
    c, engine, ids = ambiente
    for fazenda in (1, 2):
        r = c.put(ROTA.format(ids["orfa"]), json=CORPO, headers=_cab(f"admin{fazenda}", fazenda))
        assert r.status_code == 404, f"fazenda {fazenda}: {r.status_code} {r.text[:200]}"
    assert not _encerrada(engine, ids["orfa"])


def test_guarda_da_rota_sem_fid_recusa_em_vez_de_encerrar(ambiente):
    """Com a porta desarmada, o resolvedor estrito recusa (409) em vez de
    devolver None em silêncio e deixar a checagem de posse sem efeito."""
    c, engine, ids = ambiente
    _desligar_trava_de_porta()
    r = c.put(ROTA.format(ids["vitima"]), json=CORPO, headers=_cab("admin_duplo"))
    assert r.status_code == 409, f"Resposta: {r.status_code} {r.text[:200]}"
    assert not _encerrada(engine, ids["vitima"]), "a dieta da vítima foi encerrada"


def test_a_dona_da_dieta_continua_encerrando(ambiente):
    """Controle positivo. Sem ele, uma rota que responde 404 para todo mundo
    passaria em todos os testes acima."""
    c, engine, ids = ambiente
    r = c.put(ROTA.format(ids["vitima"]), json=CORPO, headers=_cab("admin1", 1))
    assert r.status_code == 200, f"a dona não conseguiu encerrar: {r.status_code} {r.text[:200]}"
    assert _encerrada(engine, ids["vitima"])
