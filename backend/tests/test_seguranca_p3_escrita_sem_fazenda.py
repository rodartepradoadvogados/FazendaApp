"""
Faixa P3 da auditoria (docs/security-audit/achados.json, severidade "baixa"):
CRIAÇÃO de registro resolvendo `fazenda_id` pela dependência TOLERANTE
`get_fazenda_atual_id` — a linha nasce com `fazenda_id` nulo.

Este arquivo cobre as duas metades do fechamento da faixa:

1. O ÚLTIMO PONTO QUE AINDA ESTAVA ABERTO — a fábrica
   `financeiro.py::_crud_nome_ativo_financeiro` (tipos-documento,
   formas-pagamento-cadastro, classificações). Ela sobreviveu às ondas P1/P2/P3
   inteiras porque as duas sentinelas de AST (tests/test_sentinela_*) só
   enxergam função DECORADA com `@router.post(...)`, e estas três rotas são
   registradas por chamada — `router.post("/tipos-documento")(_criar_tipo_doc)`
   —, com a função nascendo dentro de uma fábrica. Ficaram no ponto cego das
   duas redes; é este teste que passa a segurar.

2. A MENSAGEM DA RECUSA, para todo o grupo. A regra do dono, textual: "Fazenda
   chegar vazia, tem que dar erro e pedido de acionamento do suporte CowData.
   Isso só é resolvido se tiver uma fazenda cadastrada, a pessoa cadastrada e
   usuário atribuído a uma pessoa cadastrada dentro de uma fazenda." O texto
   mora em `fazenda.auth.ERRO_ESCRITA_SEM_FAZENDA` e é cobrado aqui pelo mesmo
   motivo que `routers/auth.py::ERRO_USUARIO_SEM_FAZENDA` é cobrado em
   test_usuario_sempre_com_fazenda.py: é a única explicação que a pessoa
   travada recebe, e um "não foi possível salvar" genérico a deixaria sem saber
   o que fazer. As demais rotas do grupo A já tinham sido convertidas em PRs
   anteriores — aqui elas ganham a trava de texto que ainda não tinham.

DUAS CAMADAS, DE PROPÓSITO. Em produção a trava de porta
(`auth.py::exigir_fazenda_selecionada`, uma linha por router em main.py) já
recusa o token sem "fid" antes de a rota rodar. Os testes conferem primeiro
essa camada e depois DESLIGAM-NA para conferir a segunda — a dependência da
própria rota. Defesa em profundidade: a guarda da rota não pode depender de uma
linha do main.py que um remonte de router apaga sem ninguém notar.

Token REAL (`criar_token`), nunca `dependency_overrides` de
`get_fazenda_atual_id` — mesmo espírito dos demais
test_seguranca_*_multitenant.py.
"""
from __future__ import annotations

import os
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from fazenda.auth import ERRO_ESCRITA_SEM_FAZENDA, criar_token, hash_senha
from fazenda.models import (
    AlertaIndicador, CentroCusto, ClassificacaoLancamento, ContaCorrente, ContratoFazenda,
    ContratoFazendaModulo, EstoqueSemen, Fazenda, FormaPagamentoCadastro, GrauSangue, Lote,
    MetodoServicoReprodutivo, MotivoMovimentacao, Raca, Safra, TipoDocumento,
    TipoServicoReprodutivo, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

# Sufixo em todos os nomes criados pelos testes: nenhum deles pode colidir com
# o que o startup semeia (seed_tipos_documento_formas_pagamento e amigos), senão
# a recusa viria do 409 de duplicata e o teste passaria pelo motivo errado.
MARCA = "P3 Sentinela"


# (rota, corpo, modelo, campo, valor) — as rotas de CRIAÇÃO citadas nos seis
# achados do grupo A. As três de `_crud_nome_ativo_financeiro` vêm por último
# porque são as que este PR corrige; as demais já estavam convertidas e entram
# aqui para a trava de TEXTO, que nenhuma delas tinha.
ROTAS_DE_CRIACAO = [
    ("/cadastro/racas", {"nome": f"Raça {MARCA}"}, Raca, "nome", f"Raça {MARCA}"),
    ("/cadastro/graus-sangue", {"nome": f"Grau {MARCA}"}, GrauSangue, "nome", f"Grau {MARCA}"),
    (
        "/cadastro/metodos-servico",
        {"nome": f"Método {MARCA}", "tipo_servico_id": 1},
        MetodoServicoReprodutivo, "nome", f"Método {MARCA}",
    ),
    (
        "/cadastro/estoque-semen",
        {"touro_nome": f"Touro {MARCA}"},
        EstoqueSemen, "touro_nome", f"Touro {MARCA}",
    ),
    ("/movimentacoes/motivos", {"nome": f"Motivo {MARCA}"}, MotivoMovimentacao, "nome", f"Motivo {MARCA}"),
    ("/lotes", {"codigo": "P3S", "nome": f"Lote {MARCA}"}, Lote, "codigo", "P3S"),
    (
        "/safras",
        {
            "nome": f"Safra {MARCA}", "data_inicio": "2026-01-01", "data_fim": "2026-06-30",
            "hectares": 10.0, "toneladas_produzidas": 5.0,
        },
        Safra, "nome", f"Safra {MARCA}",
    ),
    (
        "/alertas-indicador",
        {"indicador_chave": "taxa_prenhez_pct", "operador": ">", "valor_limite": 10.0},
        AlertaIndicador, "indicador_chave", "taxa_prenhez_pct",
    ),
    (
        "/financeiro/contas-correntes",
        {"banco": "001", "agencia": "0001", "numero_conta": "P3S-0"},
        ContaCorrente, "numero_conta", "P3S-0",
    ),
    ("/financeiro/centros-custo", {"nome": f"Centro {MARCA}"}, CentroCusto, "nome", f"Centro {MARCA}"),
    (
        "/financeiro/tipos-documento",
        {"nome": f"Tipo {MARCA}"}, TipoDocumento, "nome", f"Tipo {MARCA}",
    ),
    (
        "/financeiro/formas-pagamento-cadastro",
        {"nome": f"Forma {MARCA}"}, FormaPagamentoCadastro, "nome", f"Forma {MARCA}",
    ),
    (
        "/financeiro/classificacoes",
        {"nome": f"Classificação {MARCA}"}, ClassificacaoLancamento, "nome", f"Classificação {MARCA}",
    ),
]

# As três que esta correção converteu — usadas também na contraprova, para o
# caminho legítimo não ficar só implícito.
ROTAS_DA_FABRICA_FINANCEIRA = [
    ("/financeiro/tipos-documento", TipoDocumento),
    ("/financeiro/formas-pagamento-cadastro", FormaPagamentoCadastro),
    ("/financeiro/classificacoes", ClassificacaoLancamento),
]


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes provisionadas (é a tabela `fazenda` NÃO vazia que
    liga a recusa — ver `auth.py::multifazenda_provisionado`), um admin
    vinculado a cada uma, e um terceiro usuário SEM vínculo nenhum: é ele que
    representa o caso da regra do dono ("usuário atribuído a uma pessoa
    cadastrada dentro de uma fazenda" que nunca aconteceu)."""
    engine = create_engine(
        f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    import fazenda.database as database
    import main

    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)

    with Session(engine) as s:
        s.add(Fazenda(id=1, nome="Fazenda Um"))
        s.add(Fazenda(id=2, nome="Fazenda Dois"))
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
            s.add(Usuario(
                id=fid, username=f"admin{fid}", senha_hash=hash_senha("x"), papel="admin", ativo=True,
            ))
            s.add(UsuarioFazenda(usuario_id=fid, fazenda_id=fid))
            # Tipo de serviço reprodutivo por fazenda: o POST /cadastro/
            # metodos-servico exige um, e sem ele a contraprova positiva
            # morreria no 400 de "Tipo de serviço não encontrado" em vez de
            # provar que o caminho legítimo continua de pé.
            s.add(TipoServicoReprodutivo(id=fid, nome=f"IA {fid}", fazenda_id=fid))

        # O usuário travado: existe, é admin, tem tudo liberado — e não está
        # vinculado a fazenda nenhuma. Nenhuma tela do lado do cliente conserta
        # isso, que é por que a mensagem manda acionar o suporte CowData.
        s.add(Usuario(
            id=9, username="sem_fazenda", senha_hash=hash_senha("x"), papel="admin", ativo=True,
        ))
        s.commit()

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()


def _cab(username: str, fazenda_id: int | None = None) -> dict:
    """Token REAL. `fazenda_id=None` é o token sem a claim "fid" — o que o
    login emite para quem não tem fazenda vinculada (ver routers/auth.py)."""
    return {"Authorization": f"Bearer {criar_token(username, fazenda_id=fazenda_id)}"}


def _desligar_trava_de_porta() -> None:
    """Desliga `exigir_fazenda_selecionada` para expor a SEGUNDA camada.

    A trava de porta é uma linha por router no main.py (`_fazenda_selecionada`);
    se ela fosse a única defesa, remontar um router sem ela reabriria a faixa
    inteira em silêncio. Aqui ela sai justamente para o teste comprovar que a
    rota se defende sozinha."""
    import main

    main.app.dependency_overrides[main._fazenda_selecionada[0].dependency] = lambda: None


@pytest.mark.parametrize("rota,corpo,modelo,campo,valor", ROTAS_DE_CRIACAO, ids=[r[0] for r in ROTAS_DE_CRIACAO])
def test_criacao_sem_fazenda_recusa_e_manda_acionar_o_suporte(ambiente, rota, corpo, modelo, campo, valor):
    """O achado inteiro, rota por rota: token sem fazenda + usuário sem vínculo
    não pode gravar linha órfã. Confere as duas camadas, o TEXTO da recusa e
    que nada foi para o banco."""
    c, engine = ambiente

    # Camada 1 — a trava de porta recusa na entrada. `/alertas-indicador` e as
    # demais compartilham o mesmo objeto de dependência, então o 409 é o mesmo.
    primeira = c.post(rota, json=corpo, headers=_cab("sem_fazenda"))
    assert primeira.status_code == 409, (
        f"{rota}: a trava de porta deixou passar um token sem fazenda. "
        f"Resposta: {primeira.status_code} {primeira.text[:200]}"
    )

    # Camada 2 — sem a porta, a própria rota.
    _desligar_trava_de_porta()
    r = c.post(rota, json=corpo, headers=_cab("sem_fazenda"))
    assert r.status_code == 409, (
        f"{rota}: criou (ou tentou criar) registro com fazenda_id nulo em vez de recusar. "
        f"Resposta: {r.status_code} {r.text[:300]}"
    )
    assert r.json()["detail"] == ERRO_ESCRITA_SEM_FAZENDA, (
        f"{rota}: a recusa veio com outro texto. Esta mensagem é a única instrução que a pessoa "
        "travada recebe — a regra do dono é que ela mande acionar o suporte CowData. "
        f"Veio: {r.json().get('detail')!r}"
    )

    with Session(engine) as s:
        gravadas = s.exec(select(modelo).where(getattr(modelo, campo) == valor)).all()
        assert not gravadas, (
            f"{rota}: a recusa respondeu 409 mas a linha foi gravada assim mesmo "
            f"(fazenda_id={[g.fazenda_id for g in gravadas]})"
        )


@pytest.mark.parametrize("rota,modelo", ROTAS_DA_FABRICA_FINANCEIRA, ids=[r[0] for r in ROTAS_DA_FABRICA_FINANCEIRA])
def test_catalogo_financeiro_da_propria_fazenda_continua_funcionando(ambiente, rota, modelo):
    """Contraprova das três rotas corrigidas: com a fazenda no token, o cadastro
    continua nascendo — e nasce CARIMBADO. Sem isto, trocar a dependência por
    uma que recusa sempre também passaria no teste de cima."""
    c, engine = ambiente
    nome = f"Catálogo {MARCA}"

    r = c.post(rota, json={"nome": nome}, headers=_cab("admin1", 1))
    assert r.status_code == 200, r.text
    assert r.json()["fazenda_id"] == 1, (
        f"{rota}: o cadastro nasceu com fazenda_id={r.json().get('fazenda_id')!r}. "
        "A listagem filtra por igualdade exata, então uma linha nula some do seletor de todas "
        "as fazendas — inclusive da de quem acabou de criá-la."
    )

    with Session(engine) as s:
        criadas = s.exec(select(modelo).where(modelo.nome == nome)).all()
        assert [x.fazenda_id for x in criadas] == [1]

    # E o carimbo tem efeito prático: a fazenda 2 não enxerga o cadastro da 1.
    listagem_vizinha = c.get(rota, headers=_cab("admin2", 2))
    assert listagem_vizinha.status_code == 200, listagem_vizinha.text
    assert nome not in [item["nome"] for item in listagem_vizinha.json()], (
        f"{rota}: o cadastro da fazenda 1 apareceu na listagem da fazenda 2"
    )

    # O mesmo nome nas duas fazendas não colide: a checagem de duplicata é por
    # fazenda, e só continua sendo enquanto o carimbo existir.
    r2 = c.post(rota, json={"nome": nome}, headers=_cab("admin2", 2))
    assert r2.status_code == 200, (
        f"{rota}: a fazenda 2 não conseguiu usar um nome que só existe na fazenda 1. "
        f"Resposta: {r2.status_code} {r2.text[:200]}"
    )
    assert r2.json()["fazenda_id"] == 2


def test_usuario_com_duas_fazendas_recebe_a_outra_instrucao(ambiente):
    """A recusa de "acione o suporte" é só para quem não tem vínculo NENHUM.
    Quem tem duas fazendas e não escolheu uma resolve sozinho, saindo e
    entrando de novo — mandá-lo ao suporte seria ruído, e é por isso que
    `resolver_fazenda_id_escrita` tem dois textos e não um."""
    c, engine = ambiente
    with Session(engine) as s:
        s.add(Usuario(id=10, username="admin_duplo", senha_hash=hash_senha("x"), papel="admin", ativo=True))
        s.add(UsuarioFazenda(usuario_id=10, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=10, fazenda_id=2))
        s.commit()

    _desligar_trava_de_porta()
    r = c.post("/financeiro/tipos-documento", json={"nome": f"Duplo {MARCA}"}, headers=_cab("admin_duplo"))
    assert r.status_code == 409, r.text
    detalhe = r.json()["detail"]
    assert detalhe != ERRO_ESCRITA_SEM_FAZENDA
    assert "sair e entrar novamente" in detalhe.lower() or "entre novamente" in detalhe.lower(), detalhe

    with Session(engine) as s:
        assert not s.exec(select(TipoDocumento).where(TipoDocumento.nome == f"Duplo {MARCA}")).all()


def test_usuario_de_fazenda_unica_sem_fid_continua_lancando(ambiente):
    """O caminho legítimo que a recusa NÃO pode atrapalhar: token legado (sem
    "fid", ex.: sessão "manter conectado" de antes do multi-fazenda) de quem
    tem vínculo com UMA fazenda só. `resolver_fazenda_id_escrita` resolve por
    ela em vez de recusar — a maioria esmagadora da base real. Se este teste
    quebrar, a correção deixou de ser uma trava e virou uma parede."""
    c, engine = ambiente
    _desligar_trava_de_porta()

    nome = f"Legado {MARCA}"
    r = c.post("/financeiro/tipos-documento", json={"nome": nome}, headers=_cab("admin1"))
    assert r.status_code == 200, (
        "token legado de usuário com fazenda única deixou de conseguir cadastrar. "
        f"Resposta: {r.status_code} {r.text[:200]}"
    )
    assert r.json()["fazenda_id"] == 1
    with Session(engine) as s:
        assert [t.fazenda_id for t in s.exec(select(TipoDocumento).where(TipoDocumento.nome == nome)).all()] == [1]
