"""
Bloco das MÉDIAS da auditoria (docs/security-audit/achados.json): as rotas que
ainda gravavam com a dependência TOLERANTE (`get_fazenda_atual_id` +
`fazenda_id_seguro`) e as duas leituras que ficaram sem filtro de fazenda.

Achados cobertos aqui — numeração 1-based do relatório impresso:

  4  POST /producao/pesagens ................ gravava PesagemCorporal órfã
  5  POST /producao/qualidade-leite ......... gravava QualidadeLeite órfã
  6  POST /producao/entrega-leite ........... upsert atravessava a fazenda
  31 POST /sanidade/cronogramas ............. gravava CronogramaSanitario órfão
  33 POST /cadastro/protocolos-sanitarios/dose-migrar . sem gate de papel
  54 GET  /indicadores/ ..................... select(Lote) sem fazenda_id
  58 POST /baixas/a-descartar ............... marcava o animal de outra fazenda
  65 PUT  /reproducao/servicos/{id} ......... diagnóstico sem allow-list

Dois cenários de ataque, sempre os dois:

  (a) FAZENDA 2 AGE SOBRE O DADO DA FAZENDA 1 — normalmente pelo `numero` do
      animal ou pela `competencia`, que são texto e colidem entre tenants de
      propósito (a vaca "500" existe nas duas fazendas desde a migração
      c24befa94c1b, e todo mundo fecha o mesmo mês "2026-06").

  (b) TOKEN SEM `fid` — o que a auditoria chama de padrão tolerante. Com
      fazenda cadastrada no banco, esse token não pode gravar nada: se a
      dependência de escrita deixar passar, o registro nasce com
      `fazenda_id = NULL`, invisível a toda consulta filtrada por fazenda
      (é a causa raiz documentada do "D6 sumindo da Agenda", e a migração
      029227481e9e mostra que esses órfãos existem de verdade em produção).

E sempre um CONTROLE POSITIVO: a própria fazenda continua conseguindo. Um
teste que só prova bloqueio pode estar bloqueando tudo.

TOKEN DE VERDADE (`criar_token`), nunca `dependency_overrides` de
`get_fazenda_atual_id`: é justamente o caminho token -> get_fazenda_atual_id
-> get_fazenda_id_escrita -> consulta que está em julgamento. Mesmo espírito
de tests/test_trava_fazenda_selecionada.py e dos demais
test_seguranca_*_multitenant.py.
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
    Animal, CalendarioSanitario, ContratoFazenda, ContratoFazendaModulo, EntregaLeiteMensal,
    EventoSanitario, Fazenda, Lote, PesagemCorporal, ProtocoloSanitario, ProtocoloSanitarioEtapa,
    QualidadeLeite, Servico, Usuario, UsuarioFazenda,
)
from fazenda.models.planos import MODULOS_COMERCIAIS

# A vaca que existe NAS DUAS fazendas. Desde c24befa94c1b `animal.numero` só é
# único dentro da fazenda, e toda rota que casa por número precisa provar isso.
MATRIZ_COLIDIDA = "500"
COMPETENCIA = "2026-06"
DATA = date(2026, 6, 15)


@pytest.fixture
def ambiente(monkeypatch):
    """Duas fazendas-clientes, um admin em cada, a mesma vaca "500" nas duas,
    e o dado atacável da fazenda 1 para cada rota sob teste."""
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
            s.add(Animal(
                numero=MATRIZ_COLIDIDA, ativo=True, sexo="F", categoria_abrev="Novilha",
                data_nasc=date(2023, 1, 10), grupo_primario="01 - Lactação", fazenda_id=fid,
            ))

        # Admin com acesso às DUAS fazendas. É ELE que produz o token sem
        # `fid` que interessa: `resolver_fazenda_id_escrita` resolve sozinha a
        # fazenda de quem tem vínculo ÚNICO (caso 2 do docstring dela, e está
        # certo — o token legado do cliente único não deve forçar relogin),
        # então um usuário de uma fazenda só nunca chega no caminho de recusa.
        # Com dois vínculos não há o que adivinhar: ou o token diz qual
        # fazenda, ou a escrita não acontece.
        s.add(Usuario(
            id=9, username="admin_duplo", senha_hash=hash_senha("x"), papel="admin", ativo=True,
        ))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=1))
        s.add(UsuarioFazenda(usuario_id=9, fazenda_id=2))

        # --- Achado 6: a entrega da fazenda 1 na competência disputada -----
        entrega_v = EntregaLeiteMensal(
            competencia=COMPETENCIA, quantidade_litros=90000.0, unidade="kg", fazenda_id=1,
        )
        s.add(entrega_v)

        # --- Achado 54: o lote da fazenda 1, com janela de DEL própria -----
        # Mesmo `grupo_primario` ("01 - Lactação") nas duas fazendas — é o
        # vocabulário padrão do sistema, então a colisão é o caso normal.
        lote_v = Lote(codigo="01", nome="Lactação", del_min=0, del_max=305, fazenda_id=1)
        lote_atacante = Lote(codigo="01", nome="Lactação", del_min=0, del_max=100, fazenda_id=2)
        s.add(lote_v)
        s.add(lote_atacante)

        # --- Achado 31: regra de calendário da fazenda 1 -------------------
        evento_v = EventoSanitario(nome="Vermífugo", ativo=True, fazenda_id=1)
        s.add(evento_v)
        s.commit()
        s.refresh(evento_v)
        calendario_v = CalendarioSanitario(
            evento_sanitario_id=evento_v.id, frequencia_valor=4, frequencia_unidade="meses",
            data_evento=DATA, usa_cronograma=True, ativo=True, fazenda_id=1,
        )
        s.add(calendario_v)

        # --- Achado 33: etapa de protocolo com dose de peso vivo no texto --
        # Uma em cada fazenda: a varredura em massa não pode atravessar.
        protocolo_v = ProtocoloSanitario(nome="Pneumonia — Protocolo A", fazenda_id=1)
        protocolo_atacante = ProtocoloSanitario(nome="Pneumonia — Protocolo A", fazenda_id=2)
        s.add(protocolo_v)
        s.add(protocolo_atacante)
        s.commit()
        s.refresh(protocolo_v)
        s.refresh(protocolo_atacante)
        etapa_v = ProtocoloSanitarioEtapa(
            protocolo_id=protocolo_v.id, dia=0, produto="Banamine", modo_dose="fixa",
            dosagem=2.0, unidade="ml / 15kg PV", fazenda_id=1,
        )
        etapa_atacante = ProtocoloSanitarioEtapa(
            protocolo_id=protocolo_atacante.id, dia=0, produto="Banamine", modo_dose="fixa",
            dosagem=2.0, unidade="ml / 15kg PV", fazenda_id=2,
        )
        s.add(etapa_v)
        s.add(etapa_atacante)

        # --- Achado 65: serviço da fazenda 2, para editar o próprio --------
        servico_atacante = Servico(
            numero_matriz=MATRIZ_COLIDIDA, data_servico=date(2026, 5, 1), tipo_servico="IA",
            fazenda_id=2,
        )
        s.add(servico_atacante)
        s.commit()
        s.refresh(entrega_v)
        s.refresh(calendario_v)
        s.refresh(servico_atacante)

        ids.update(
            entrega_vitima=entrega_v.id,
            calendario_vitima=calendario_v.id,
            etapa_vitima=etapa_v.id,
            etapa_atacante=etapa_atacante.id,
            servico_atacante=servico_atacante.id,
        )

    def _get_session_override():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = _get_session_override
    with TestClient(main.app) as c:
        yield c, engine, ids
    main.app.dependency_overrides.clear()


def _cab(fazenda_id: int):
    """Token REAL do admin daquela fazenda, com a claim "fid" carimbada."""
    return {"Authorization": f"Bearer {criar_token(f'admin{fazenda_id}', fazenda_id=fazenda_id)}"}


def _cab_sem_fazenda():
    """Token REAL sem a claim "fid", de um usuário com acesso a DUAS fazendas
    — o caso 3 de `resolver_fazenda_id_escrita`. É o token que o padrão
    tolerante deixava passar: sem `fid`, o `if fazenda_id is not None` de toda
    consulta some e o `session.add(Modelo(fazenda_id=None))` grava órfão.

    Acontece de verdade em três situações (ver auth.py::login): usuário com
    2+ fazendas que não chamou /auth/selecionar-fazenda, membro da Equipe
    CowData, e token legado "manter conectado" de até 90 dias."""
    return {"Authorization": f"Bearer {criar_token('admin_duplo')}"}


def _desligar_trava_de_porta():
    """Desliga SÓ `exigir_fazenda_selecionada` — a trava de porta montada nos
    `include_router` de main.py —, mantendo o token real e todo o resto.

    Existe por um motivo específico. Hoje essa trava recusa o token sem `fid`
    na ENTRADA, antes de qualquer rota rodar. Isso é ótimo, mas esconde a
    camada de dentro: com ela ligada, uma rota que grava pela dependência
    TOLERANTE (`get_fazenda_atual_id`) parece tão segura quanto uma que grava
    pela ESTRITA (`get_fazenda_id_escrita`) — as duas devolvem 403 e o teste
    fica verde sem provar nada. Foi assim que os furos passaram antes.

    A trava de porta é UMA linha por router em main.py. Ela some no dia em que
    alguém montar um router novo, ou remontar um existente, sem repeti-la — e
    é exatamente esse o risco que o docstring de portal.py já nomeia ao
    repetir a checagem dentro da própria função. Desligando aqui, o teste
    passa a medir a segunda camada: sem a trava, a rota AINDA recusa?

    NÃO é um override de `get_fazenda_atual_id` — esse continua proibido (é o
    caminho em julgamento). O que se desliga é a camada de fora, para poder
    ver a de dentro."""
    import main

    main.app.dependency_overrides[main._fazenda_selecionada[0].dependency] = lambda: None


def _assert_trava_de_porta_recusa(resposta):
    """Camada 1 — a trava de porta barra o token sem `fid` na entrada, com o
    mesmo 409 que a camada de dentro usa (é o código que o front lê para
    mandar reescolher a fazenda). Quem responde aqui é
    `exigir_fazenda_selecionada`, montada no include_router: a requisição nem
    chega na função da rota."""
    assert resposta.status_code == 409, (
        "a trava de porta (exigir_fazenda_selecionada) deixou entrar uma requisição sem "
        f"fazenda selecionada. Resposta: {resposta.status_code} {resposta.text[:200]}"
    )


def _assert_recusa_sem_fazenda(resposta):
    """Camada 2 — mesmo SEM a trava de porta, a rota recusa em vez de gravar.

    409 é a resposta desenhada por `resolver_fazenda_id_escrita`, com o
    cabeçalho X-Fazenda-Nao-Selecionada que o front lê para mandar reescolher
    a fazenda. O que não pode é 2xx: aí o registro nasce com
    `fazenda_id = NULL` e some de todas as telas."""
    assert resposta.status_code == 409, (
        "com a trava de porta desligada, a rota GRAVOU com token sem fazenda — é o padrão "
        "tolerante da auditoria: o registro nasce órfão e nenhuma consulta por fazenda o "
        f"enxerga de novo. Resposta: {resposta.status_code} {resposta.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Achado 4 — POST /producao/pesagens
# ---------------------------------------------------------------------------
def test_pesagem_com_token_sem_fazenda_e_recusada(ambiente):
    c, engine, _ids = ambiente
    _assert_trava_de_porta_recusa(c.post(
        "/producao/pesagens",
        json={"data_pesagem": DATA.isoformat(), "entradas": [{"numero_matriz": MATRIZ_COLIDIDA, "peso_kg": 420.0}]},
        headers=_cab_sem_fazenda(),
    ))
    _desligar_trava_de_porta()
    r = c.post(
        "/producao/pesagens",
        json={"data_pesagem": DATA.isoformat(), "entradas": [{"numero_matriz": MATRIZ_COLIDIDA, "peso_kg": 420.0}]},
        headers=_cab_sem_fazenda(),
    )
    _assert_recusa_sem_fazenda(r)
    with Session(engine) as s:
        orfas = s.exec(select(PesagemCorporal).where(PesagemCorporal.fazenda_id.is_(None))).all()
        assert not orfas, (
            "nasceu PesagemCorporal com fazenda_id=NULL. O peso é o que decide novilha "
            "apta/inapta e agora não pertence a ninguém."
        )


def test_pesagem_da_propria_fazenda_continua_funcionando(ambiente):
    c, engine, _ids = ambiente
    r = c.post(
        "/producao/pesagens",
        json={"data_pesagem": DATA.isoformat(), "entradas": [{"numero_matriz": MATRIZ_COLIDIDA, "peso_kg": 415.0}]},
        headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        pesagens = s.exec(select(PesagemCorporal)).all()
        assert [p.fazenda_id for p in pesagens] == [2], "a pesagem tem que nascer carimbada na fazenda 2"


def test_pesagem_nao_atravessa_para_a_vaca_de_mesmo_numero_da_outra_fazenda(ambiente):
    """Controle do casamento por número: a fazenda 2 pesa a SUA vaca "500" e
    isso não pode mexer em nada da fazenda 1."""
    c, engine, _ids = ambiente
    c.post(
        "/producao/pesagens",
        json={"data_pesagem": DATA.isoformat(), "entradas": [{"numero_matriz": MATRIZ_COLIDIDA, "peso_kg": 415.0}]},
        headers=_cab(2),
    )
    with Session(engine) as s:
        da_fazenda_1 = s.exec(select(PesagemCorporal).where(PesagemCorporal.fazenda_id == 1)).all()
        assert not da_fazenda_1, "a pesagem da fazenda 2 caiu na fazenda 1 pelo número da vaca"


# ---------------------------------------------------------------------------
# Achado 5 — POST /producao/qualidade-leite
# ---------------------------------------------------------------------------
def test_qualidade_leite_com_token_sem_fazenda_e_recusada(ambiente):
    c, engine, _ids = ambiente
    _assert_trava_de_porta_recusa(c.post(
        "/producao/qualidade-leite",
        json={"data_coleta": DATA.isoformat(), "ccs": 250.0},
        headers=_cab_sem_fazenda(),
    ))
    _desligar_trava_de_porta()
    r = c.post(
        "/producao/qualidade-leite",
        json={"data_coleta": DATA.isoformat(), "ccs": 250.0, "cbt": 40.0},
        headers=_cab_sem_fazenda(),
    )
    _assert_recusa_sem_fazenda(r)
    with Session(engine) as s:
        orfas = s.exec(select(QualidadeLeite).where(QualidadeLeite.fazenda_id.is_(None))).all()
        assert not orfas, (
            "nasceu QualidadeLeite com fazenda_id=NULL — é a tabela onde este bug JÁ deixou "
            "órfãos em produção, depois da migração que deveria tê-los zerado."
        )


def test_qualidade_leite_da_propria_fazenda_continua_funcionando(ambiente):
    c, engine, _ids = ambiente
    r = c.post(
        "/producao/qualidade-leite",
        json={"data_coleta": DATA.isoformat(), "ccs": 250.0},
        headers=_cab(2),
    )
    assert r.status_code == 201, r.text
    assert r.json()["fazenda_id"] == 2


# ---------------------------------------------------------------------------
# Achado 6 — POST /producao/entrega-leite
# ---------------------------------------------------------------------------
def test_entrega_leite_com_token_sem_fazenda_nao_sobrescreve_a_entrega_alheia(ambiente):
    """O pior caso do achado 6: o upsert busca por `competencia`, e sem o
    filtro de fazenda ele ENCONTRA a entrega da outra fazenda no mesmo mês e
    reescreve o volume dela — não é só criar um órfão, é apagar um dado."""
    c, engine, ids = ambiente
    corpo = {"competencia": COMPETENCIA, "quantidade_litros": 1.0, "unidade": "kg"}
    _assert_trava_de_porta_recusa(
        c.post("/producao/entrega-leite", json=corpo, headers=_cab_sem_fazenda())
    )
    _desligar_trava_de_porta()
    r = c.post("/producao/entrega-leite", json=corpo, headers=_cab_sem_fazenda())
    _assert_recusa_sem_fazenda(r)
    with Session(engine) as s:
        assert s.get(EntregaLeiteMensal, ids["entrega_vitima"]).quantidade_litros == 90000.0, (
            "o volume entregue pela fazenda 1 no mês foi reescrito por um token sem fazenda"
        )
        orfas = s.exec(select(EntregaLeiteMensal).where(EntregaLeiteMensal.fazenda_id.is_(None))).all()
        assert not orfas


def test_entrega_leite_da_propria_fazenda_na_mesma_competencia_continua_funcionando(ambiente):
    """Controle positivo E prova de isolamento: a fazenda 2 lança a MESMA
    competência que a fazenda 1 já tem. Tem que criar a entrega dela, não
    encostar na da vizinha."""
    c, engine, ids = ambiente
    r = c.post(
        "/producao/entrega-leite",
        json={"competencia": COMPETENCIA, "quantidade_litros": 12000.0, "unidade": "kg"},
        headers=_cab(2),
    )
    assert r.status_code == 201, r.text
    assert r.json()["fazenda_id"] == 2
    with Session(engine) as s:
        assert s.get(EntregaLeiteMensal, ids["entrega_vitima"]).quantidade_litros == 90000.0


# ---------------------------------------------------------------------------
# Achado 31 — POST /sanidade/cronogramas
# ---------------------------------------------------------------------------
def test_cronograma_com_token_sem_fazenda_e_recusado(ambiente):
    c, _engine, ids = ambiente
    _assert_trava_de_porta_recusa(c.post(
        "/sanidade/cronogramas",
        json={"calendario_sanitario_id": ids["calendario_vitima"]},
        headers=_cab_sem_fazenda(),
    ))
    _desligar_trava_de_porta()
    r = c.post(
        "/sanidade/cronogramas",
        json={"calendario_sanitario_id": ids["calendario_vitima"]},
        headers=_cab_sem_fazenda(),
    )
    _assert_recusa_sem_fazenda(r)


def test_cronograma_sobre_regra_de_outra_fazenda_e_recusado(ambiente):
    c, _engine, ids = ambiente
    r = c.post(
        "/sanidade/cronogramas",
        json={"calendario_sanitario_id": ids["calendario_vitima"]},
        headers=_cab(2),
    )
    assert r.status_code == 404, (
        "404, nunca 403 — um 403 já confirma que o id existe. "
        f"Resposta: {r.status_code} {r.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Achado 33 — POST /cadastro/protocolos-sanitarios/dose-migrar
# ---------------------------------------------------------------------------
def test_dose_migrar_exige_papel(ambiente):
    """Reescreve posologia (a dose que vai na vaca) de forma irreversível — não
    pode ser disparável por qualquer usuário com o módulo liberado.

    O operador aqui recebe `permissoes="parametros"` DE PROPÓSITO: é o módulo
    que o router de cadastro exige em main.py. Sem isso o 403 viria de
    `exigir_modulo`, e o teste ficaria verde sem nunca ter chegado no gate de
    papel — que é o que está em julgamento."""
    c, engine, ids = ambiente
    with Session(engine) as s:
        operador = Usuario(
            id=3, username="operador2", senha_hash=hash_senha("x"), papel="operador",
            permissoes="parametros", ativo=True,
        )
        s.add(operador)
        s.add(UsuarioFazenda(usuario_id=3, fazenda_id=2))
        s.commit()
    cab = {"Authorization": f"Bearer {criar_token('operador2', fazenda_id=2)}"}
    # Controle: o operador CHEGA no router — outra rota dele responde 200.
    # Sem isto, um 403 vindo de `exigir_modulo` passaria por prova do gate.
    assert c.get("/cadastro/protocolos-sanitarios", headers=cab).status_code == 200
    r = c.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true", headers=cab)
    assert r.status_code == 403, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(ProtocoloSanitarioEtapa, ids["etapa_atacante"]).modo_dose == "fixa"


def test_dose_migrar_com_token_sem_fazenda_e_recusado(ambiente):
    """O caso grave do achado 33: `confirmar=true` com `fazenda_id` resolvendo
    None derrubava o `where` inteiro e reescrevia a etapa de TODAS as
    fazendas de uma vez."""
    c, engine, ids = ambiente
    _assert_trava_de_porta_recusa(
        c.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true", headers=_cab_sem_fazenda())
    )
    _desligar_trava_de_porta()
    r = c.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true", headers=_cab_sem_fazenda())
    _assert_recusa_sem_fazenda(r)
    with Session(engine) as s:
        for chave in ("etapa_vitima", "etapa_atacante"):
            assert s.get(ProtocoloSanitarioEtapa, ids[chave]).modo_dose == "fixa", (
                "uma varredura em massa sem fazenda reescreveu a posologia de todos os tenants"
            )


def test_dose_migrar_da_propria_fazenda_continua_funcionando(ambiente):
    """Controle positivo: o admin da fazenda 2 migra a etapa DELA — e só a
    dela. Se este teste falhar junto com os de bloqueio, a correção só quebrou
    a rota em vez de isolá-la."""
    c, engine, ids = ambiente
    r = c.post("/cadastro/protocolos-sanitarios/dose-migrar?confirmar=true", headers=_cab(2))
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        assert s.get(ProtocoloSanitarioEtapa, ids["etapa_atacante"]).modo_dose == "por_peso"
        assert s.get(ProtocoloSanitarioEtapa, ids["etapa_vitima"]).modo_dose == "fixa", (
            "a migração da fazenda 2 alcançou a etapa da fazenda 1"
        )


# ---------------------------------------------------------------------------
# Achado 54 — GET /indicadores/ (select(Lote) sem filtro)
# ---------------------------------------------------------------------------
def test_indicadores_nao_carregam_lote_de_outra_fazenda(ambiente):
    """Prova direta na função de carga: `_coletar_*` devolvia TODOS os lotes.
    Como o animal casa com o lote por `grupo_primario` (texto livre, e "01 -
    Lactação" é o vocabulário padrão), a janela de DEL da vizinha
    reclassificava o rebanho daqui."""
    import fazenda.database as database
    import main

    from fazenda.api.routers.indicadores import _contexto_calculo

    c, engine, _ids = ambiente
    assert c is not None and main is not None and database is not None
    with Session(engine) as s:
        _peso, lotes, _iatf = _contexto_calculo(s, 2)
    assert [l["fazenda_id"] for l in lotes] == [2], (
        f"a carga de indicadores da fazenda 2 trouxe lote de outra fazenda: {lotes}"
    )


def test_indicadores_enxergam_exatamente_o_lote_da_propria_fazenda(ambiente):
    from fazenda.api.routers.indicadores import _contexto_calculo

    _c, engine, _ids = ambiente
    with Session(engine) as s:
        _peso, lotes, _iatf = _contexto_calculo(s, 1)
    assert len(lotes) == 1 and lotes[0]["del_max"] == 305, (
        "o filtro cortou também o lote da própria fazenda — bloquear tudo não é isolar"
    )


# ---------------------------------------------------------------------------
# Achado 58 — POST /baixas/a-descartar
# ---------------------------------------------------------------------------
def test_a_descartar_com_token_sem_fazenda_e_recusado(ambiente):
    """O furo aqui não é gravar órfão, é escrever NO ANIMAL ERRADO: sem o
    filtro sobra `Animal.numero == "500"`, que casa nas duas fazendas."""
    c, engine, _ids = ambiente
    corpo = {"animais": [MATRIZ_COLIDIDA], "descartar": True}
    _assert_trava_de_porta_recusa(c.post("/baixas/a-descartar", json=corpo, headers=_cab_sem_fazenda()))
    _desligar_trava_de_porta()
    r = c.post("/baixas/a-descartar", json=corpo, headers=_cab_sem_fazenda())
    _assert_recusa_sem_fazenda(r)
    with Session(engine) as s:
        marcados = s.exec(select(Animal).where(Animal.a_descartar == True)).all()  # noqa: E712
        assert not marcados, "um token sem fazenda tirou vaca da reprodução"


def test_a_descartar_marca_so_a_vaca_da_propria_fazenda(ambiente):
    c, engine, _ids = ambiente
    r = c.post(
        "/baixas/a-descartar",
        json={"animais": [MATRIZ_COLIDIDA], "descartar": True},
        headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    assert r.json()["afetados"] == 1
    with Session(engine) as s:
        marcados = s.exec(select(Animal).where(Animal.a_descartar == True)).all()  # noqa: E712
        assert [a.fazenda_id for a in marcados] == [2], (
            "a vaca '500' da fazenda 1 foi marcada para descarte pela fazenda 2"
        )


# ---------------------------------------------------------------------------
# Achado 65 — PUT /reproducao/servicos/{id}: allow-list de diagnóstico
# ---------------------------------------------------------------------------
def test_diagnostico_fora_do_vocabulario_e_recusado(ambiente):
    """`diagnostico` é lido como enum ("POSITIVO"/"NEGATIVO") por
    estado_reprodutivo, agenda_engine, perda_prenhez e reproducao_analise.
    Texto livre ali não dá erro em lugar nenhum — a vaca só some das listas.
    E era esse valor que ia cru para o corpo do e-mail de diagnóstico."""
    c, engine, ids = ambiente
    r = c.put(
        f"/reproducao/servicos/{ids['servico_atacante']}",
        json={"diagnostico": "<img src=x onerror=alert(1)>"}, headers=_cab(2),
    )
    assert r.status_code == 400, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(Servico, ids["servico_atacante"]).diagnostico is None


def test_metodo_diagnostico_fora_do_vocabulario_e_recusado(ambiente):
    c, engine, ids = ambiente
    r = c.put(
        f"/reproducao/servicos/{ids['servico_atacante']}",
        json={"metodo_diagnostico": "<b>Palpação</b>"}, headers=_cab(2),
    )
    assert r.status_code == 400, f"Resposta: {r.status_code} {r.text[:200]}"
    with Session(engine) as s:
        assert s.get(Servico, ids["servico_atacante"]).metodo_diagnostico is None


def test_diagnostico_canonico_continua_passando(ambiente):
    """Controle positivo puro — vale antes e depois da correção. Se este
    quebrar junto com os de bloqueio, a allow-list fechou a rota em vez de
    filtrá-la."""
    c, engine, ids = ambiente
    r = c.put(
        f"/reproducao/servicos/{ids['servico_atacante']}",
        json={"diagnostico": "POSITIVO", "metodo_diagnostico": "Palpação"}, headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        servico = s.get(Servico, ids["servico_atacante"])
        assert servico.diagnostico == "POSITIVO"
        assert servico.metodo_diagnostico == "Palpação"


def test_diagnostico_em_caixa_baixa_e_sem_acento_e_normalizado(ambiente):
    """As telas antigas mandam "positivo" e "palpacao". Recusar isso quebraria
    o lançamento sem fechar furo nenhum, então a allow-list normaliza: aceita
    a variação e GRAVA a forma canônica, que é a que estado_reprodutivo,
    agenda_engine e perda_prenhez comparam."""
    c, engine, ids = ambiente
    r = c.put(
        f"/reproducao/servicos/{ids['servico_atacante']}",
        json={"diagnostico": "positivo", "metodo_diagnostico": "palpacao"}, headers=_cab(2),
    )
    assert r.status_code == 200, r.text
    with Session(engine) as s:
        servico = s.get(Servico, ids["servico_atacante"])
        assert servico.diagnostico == "POSITIVO"
        assert servico.metodo_diagnostico == "Palpação"


def test_lancamento_de_diagnostico_tambem_valida_o_metodo(ambiente):
    """A allow-list não pode existir só no PUT: POST /reproducao/diagnostico
    grava no MESMO campo, a partir de `metodo`, que também é texto livre."""
    c, _engine, _ids = ambiente
    r = c.post(
        "/reproducao/diagnostico",
        json={
            "numero_matriz": MATRIZ_COLIDIDA, "data_diagnostico": DATA.isoformat(),
            "resultado": "reconfirmada", "metodo": "<script>alert(1)</script>",
        },
        headers=_cab(2),
    )
    assert r.status_code == 400, f"Resposta: {r.status_code} {r.text[:200]}"
