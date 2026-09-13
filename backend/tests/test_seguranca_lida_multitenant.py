"""
Resíduo da Onda 1: `rules/lida.py` no padrão tolerante, e a rota que o
alimentava com `fazenda_id` nulo.

O módulo já tinha ganhado o filtro por fazenda ("BUG DE SEGURANÇA CORRIGIDO",
no comentário), mas dentro de `if fazenda_id is not None` — que com valor nulo
não restringe: DESLIGA o isolamento. E `lida` não é uma família qualquer:
`marcar_realizado` dá **baixa de estoque de verdade** quando a Lida tem
`dar_baixa_estoque` (o próprio módulo destaca isso na docstring), então
confirmar a lida alheia consome estoque alheio.

ONDE ESTAVA O FURO DE VERDADE, e não era no `lida.py`:

  • `POST /agenda/realizados` (marcar) já usava `get_fazenda_id_escrita` — o
    valor nunca chegava nulo ali, e o `if` era inofensivo na prática;
  • `DELETE /agenda/realizados/{id}` (desmarcar) usava
    `get_fazenda_atual_id`, o tolerante. Com token sem "fid" ele entregava
    `fazenda_id=None` às QUATRO famílias que a rota reverte (IATF, indução,
    protocolo personalizado e lida) — e as que filtravam dentro do `if`
    passavam a rodar sem recorte nenhum.

Desconfirmar a aplicação de outra fazenda não é dano abstrato: a tarefa volta
para a agenda dela como pendente que ninguém pediu, e alguém a executa de novo.

DUAS CAMADAS, MEDIDAS SEPARADAMENTE (mesma razão de
test_seguranca_encerrar_dieta_multitenant.py): a trava de porta recusa o token
sem "fid" antes da rota, então um teste que só mande esse token fica verde
mesmo com a correção revertida.

REGISTRO HONESTO DO ALCANCE, aferido revertendo cada metade em separado:

  • trocar a dependência da rota de volta para `get_fazenda_atual_id` deixa
    `test_sem_fid_a_rota_recusa_em_vez_de_rodar_sem_recorte` VERMELHO. Essa
    metade é a que carrega a correção.

  • devolver o `if fazenda_id is not None` ao `lida.py` NÃO quebra teste
    nenhum, e não tem como quebrar: com a dependência estrita na rota,
    `fazenda_id` nunca chega nulo, e aí o `if` volta a ser sempre verdadeiro.
    O filtro incondicional é defesa em profundidade sem cenário observável
    próprio — vale porque não depende de a rota continuar estrita amanhã, e
    porque `rules/lida.py` é chamado por quem quiser, não só por esta rota;
    não porque feche um furo hoje.

Escrever isto é preferível a inventar um teste que "cubra" o `lida.py` por
outra via: o cenário não existe enquanto a porta e o resolvedor estiverem no
lugar, e um teste que chamasse `rules/lida.py` direto, sem passar pela rota,
estaria medindo a minha própria montagem — não o sistema.
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
    ContratoFazenda, ContratoFazendaModulo, Fazenda, Lida, LidaAplicacao, LidaLancamento,
    Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

ROTA_DESMARCAR = "/agenda/realizados/{}"


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
        # `resolver_fazenda_id_escrita` resolveria a fazenda sozinha e o teste
        # de token-sem-"fid" não mediria o que pretende.
        s.add(Usuario(id=9, username="admin_duplo", senha_hash=hash_senha("x"), papel="admin", ativo=True))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=2))

        lida = Lida(nome="Limpeza do curral", fazenda_id=1)
        s.add(lida)
        s.commit()
        s.refresh(lida)

        lancamento = LidaLancamento(
            lida_id=lida.id, nome_protocolo="Limpeza do curral", modo="periodo",
            data_inicio=date(2026, 9, 1), dia_inicial=0, ativo=True, fazenda_id=1,
        )
        s.add(lancamento)
        s.commit()
        s.refresh(lancamento)

        # Aplicação da fazenda 1, JÁ REALIZADA — é ela que a fazenda 2 tentará
        # desconfirmar.
        aplicacao = LidaAplicacao(
            lancamento_id=lancamento.id, dia=0, data_prevista=date(2026, 9, 1),
            descricao="Lavar o curral", realizada=True, data_realizacao=date(2026, 9, 1),
            fazenda_id=1,
        )
        s.add(aplicacao)
        s.commit()
        s.refresh(aplicacao)
        ids["lancamento"] = lancamento.id
        ids["aplicacao"] = aplicacao.id

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


def _continua_realizada(engine, aplicacao_id: int) -> bool:
    with Session(engine) as s:
        return s.get(LidaAplicacao, aplicacao_id).realizada


def _evento(lancamento_id: int, dia: int = 0) -> str:
    return f"lida_{lancamento_id}_{dia}"


def test_trava_de_porta_recusa_token_sem_fazenda(ambiente):
    """A primeira camada, medida sozinha: com a porta armada, o token sem
    "fid" nem chega na rota."""
    c, _engine, ids = ambiente
    r = c.delete(ROTA_DESMARCAR.format(_evento(ids["lancamento"])), headers=_cab("admin_duplo"))
    assert r.status_code == 409, f"Resposta: {r.status_code} {r.text[:200]}"


def test_outra_fazenda_nao_desconfirma_a_lida_alheia(ambiente):
    """O cenário do achado: a fazenda 2 desconfirma a lida da fazenda 1.

    A rota responde 200 (ela é idempotente por natureza — desmarcar o que não
    existe não é erro), e é justamente por isso que o teste olha o BANCO: o
    que não pode acontecer é a aplicação da vítima voltar para pendente."""
    c, engine, ids = ambiente
    r = c.delete(ROTA_DESMARCAR.format(_evento(ids["lancamento"])), headers=_cab("admin2", 2))
    assert r.status_code == 200, f"Resposta: {r.status_code} {r.text[:200]}"
    assert _continua_realizada(engine, ids["aplicacao"]), (
        "a fazenda 2 desconfirmou a lida da fazenda 1 — ela volta para a agenda da vítima"
    )


def test_a_propria_fazenda_continua_desconfirmando(ambiente):
    """A guarda não pode ter fechado a porta para o dono do dado."""
    c, engine, ids = ambiente
    r = c.delete(ROTA_DESMARCAR.format(_evento(ids["lancamento"])), headers=_cab("admin1", 1))
    assert r.status_code == 200, f"Resposta: {r.status_code} {r.text[:200]}"
    assert not _continua_realizada(engine, ids["aplicacao"]), (
        "a fazenda 1 precisa continuar podendo desconfirmar a própria lida"
    )


def test_sem_fid_a_rota_recusa_em_vez_de_rodar_sem_recorte(ambiente):
    """A camada que carrega a correção, medida com a porta desarmada.

    Antes, a rota resolvia `fazenda_id=None` pelo dependente tolerante e
    entregava esse nulo às quatro famílias que ela reverte. Agora a
    dependência é a estrita, e ela recusa em vez de seguir sem recorte.

    Revertendo `get_fazenda_id_escrita` para `get_fazenda_atual_id` na rota,
    este teste fica VERMELHO — é ele que prende a correção."""
    c, engine, ids = ambiente
    _desligar_trava_de_porta()
    r = c.delete(ROTA_DESMARCAR.format(_evento(ids["lancamento"])), headers=_cab("admin_duplo"))
    assert r.status_code == 409, f"Resposta: {r.status_code} {r.text[:200]}"
    assert _continua_realizada(engine, ids["aplicacao"])
