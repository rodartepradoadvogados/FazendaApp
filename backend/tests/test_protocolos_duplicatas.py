"""
Auditoria — Central de Protocolos > Acompanhamento mostrando DUAS linhas de
Indução de Lactação praticamente idênticas (mesmo protocolo, mesmo período
04/08/2026 a 22/08/2026, 1 animal cada, ambas "Ativo"), uma com nome "cru" do
molde ("Protocolo de Indução de Lactação — 18 dias (Ativos 2)") e 2/12 etapas
(já com baixas), outra com o nome longo padronizado ("PROTOCOLO DE INDUÇÃO DE
LACTAÇÃO — 18 DIAS (ATIVOS 2) - 04/08/26 A 22/08/26 (D0 A D18 - 19 DIAS)") e
0/12 etapas (nenhuma baixa).

ACHADOS (evidência em código, ver resumo passado ao orquestrador):

1. `producao.lancar_inducao_lactacao` (POST /producao/inducao-lactacao) é o
   ÚNICO caminho do backend que cria um `ProtocoloInducaoLancamento` — não há
   seed/backfill/migração que grave um segundo lançamento renomeado. Mas essa
   rota, do jeito que estava, não tinha NENHUMA proteção contra a MESMA
   chamada acontecendo duas vezes: duplo clique no botão "Lançar" no
   navegador, ou o retry da fila offline do app móvel reenviando um POST cuja
   confirmação 2xx nunca voltou ao aparelho (sem chave de idempotência, cada
   retry é, para o servidor, um lançamento novo). Duas chamadas idênticas
   (mesmo `protocolo_id` + `data_d0` + mesmo conjunto de `animais`) criavam
   DOIS `ProtocoloInducaoLancamento` "Ativos" — exatamente o padrão do print
   (mesmo período, mesmo total de etapas, 1 animal, ambos ativos).
   CORRIGIDO nesta rodada, só em `producao.py`: a segunda chamada agora
   reaproveita o lançamento já ativo (mesmo protocolo + data_d0 + animais,
   ainda não encerrado) e devolve `{"criado": False, "aviso": "..."}`
   (HTTP 200) em vez de duplicar. Ver `TestIdempotenciaInducaoLactacao`
   abaixo.

2. As outras famílias de protocolo (IATF em reproducao.py, sanitário via
   agenda.py/protocolos_sanitarios.py, customizado em
   protocolos_customizados.py, lida em lida.py) têm o MESMO buraco de
   idempotência — nenhuma delas verifica se já existe um lançamento
   equivalente antes de criar um novo. É bug de ARQUITETURA, não específico
   da indução de lactação. Fora do escopo desta rodada (só `producao.py` e
   `nomenclatura_protocolo.py` podiam ser corrigidos aqui) — documentado
   abaixo com `xfail` em vez de corrigido.

3. O nome "cru" do molde (sem o sufixo "- {D0} A {fim} (D.. A D.. - N DIAS)")
   que aparece numa das duas linhas do print NÃO é produzido por nenhum
   caminho de CRIAÇÃO atual: a única rota de criação sempre grava
   `nome_protocolo` via `gerar_nome_lancamento()` (maiúsculo, com o sufixo de
   datas — ver `TestNomeGravadoNaCriacao` abaixo). É compatível com (a) um
   lançamento antigo, de antes desta nomenclatura automática existir, ou
   (b) uma renomeação manual via `PATCH
   /central-protocolos/{origem}/{id}/renomear` (central_protocolos.py, fora
   do escopo desta rodada) — essa rota grava `lancamento.nome_protocolo`
   livremente, sem chamar `gerar_nome_lancamento`, então um lançamento pode
   ficar com QUALQUER nome, inclusive igual ao nome cru do molde, sem que
   isso indique nada sobre COMO ele foi criado. `gerar_nome_lancamento()` é
   chamado uma única vez, na hora de lançar, e o nome fica gravado para
   sempre — nunca é recalculado depois (comentário adicionado no módulo).
   Por isso não reescrevemos nomes de lançamentos existentes: o teste
   `TestConvivenciaDeNomesAntigoENovo` reproduz a convivência dos dois
   formatos (como no print) só para provar que a Central continua exibindo
   os dois corretamente, sem mexer no dado histórico.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    ContratoFazenda, ContratoFazendaModulo,
    ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento,
)
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento, nome_curto


@pytest.fixture
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)

    def _get_session_override():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"

    # /producao e /cadastro exigem contrato ativo (+ módulo "produtivo" no
    # caso de /producao) — sem isso todo POST cai em 403 antes mesmo de
    # chegar na lógica que este arquivo testa (mesmo padrão de
    # test_inducao_fazenda_id.py).
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            s.add(ContratoFazendaModulo(fazenda_id=fid, modulo="produtivo", ativo=True))
        s.commit()

    estado = {"fazenda_id": 1}
    main.app.dependency_overrides[database.get_session] = _get_session_override
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: estado["fazenda_id"]

    with TestClient(main.app) as c:
        yield c, engine, estado

    main.app.dependency_overrides.clear()


def _criar_molde(c, nome="Indução de Lactação — 18 dias (Ativos 2)"):
    """Molde pequeno (2 etapas, D0 e D3) — suficiente para exercitar o
    lançamento sem reproduzir as 12 etapas reais do print."""
    r = c.post("/cadastro/protocolos-inducao-lactacao", json={
        "nome": nome,
        "etapas": [
            {"dia": 0, "tipo": "medicamento", "produto": "Benzoato de estradiol", "dose": 1, "unidade": "ml"},
            {"dia": 3, "tipo": "manejo", "produto": "Iniciar ordenha"},
        ],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _lancar(c, protocolo_id, animais, data_d0="2026-08-04"):
    return c.post("/producao/inducao-lactacao", json={
        "protocolo_id": protocolo_id, "animais": animais, "data_d0": data_d0,
    })


class TestIdempotenciaInducaoLactacao:
    """Reproduz o caminho de duplicação: a MESMA chamada (duplo clique /
    retry de fila offline) repetida para o mesmo protocolo + data_d0 + mesmo
    conjunto de animais."""

    def test_chamada_repetida_nao_duplica_o_lancamento(self, client):
        c, engine, estado = client
        pid = _criar_molde(c)

        r1 = _lancar(c, pid, ["422"])
        assert r1.status_code == 201, r1.text
        corpo1 = r1.json()
        assert corpo1["criado"] is True
        assert corpo1["eventos_criados"] == 2  # D0 + D3, 1 animal

        # Mesmíssima chamada de novo — sem nenhuma mudança no payload. Antes
        # da correção, isto criava um SEGUNDO ProtocoloInducaoLancamento
        # "Ativo" com o mesmo protocolo/período/animal — o par de linhas do
        # print.
        r2 = _lancar(c, pid, ["422"])
        assert r2.status_code == 200, r2.text
        corpo2 = r2.json()
        assert corpo2["criado"] is False
        assert corpo2["lancamento_id"] == corpo1["lancamento_id"]
        assert corpo2["eventos_criados"] == 0
        assert "aviso" in corpo2

        # Só existe UM ProtocoloInducaoLancamento no banco...
        with Session(engine) as s:
            todos = s.exec(select(ProtocoloInducaoLancamento)).all()
            assert len(todos) == 1

        # ...e a Central de Protocolos > Acompanhamento mostra UMA linha, não
        # duas — este é o sintoma do print, agora ausente.
        linhas = c.get("/central-protocolos/acompanhamento").json()
        linhas_inducao = [l for l in linhas if l["origem"] == "inducao"]
        assert len(linhas_inducao) == 1

    def test_animais_diferentes_nao_sao_bloqueados(self, client):
        """Duas chamadas LEGÍTIMAS e distintas (mesmo protocolo/data, animais
        diferentes) continuam criando dois lançamentos — a proteção é contra
        REPETIÇÃO exata, não contra lançar o mesmo molde para vacas
        diferentes no mesmo dia."""
        c, engine, estado = client
        pid = _criar_molde(c)

        r1 = _lancar(c, pid, ["422"])
        r2 = _lancar(c, pid, ["500"])
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]

        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloInducaoLancamento)).all()) == 2

    def test_data_d0_diferente_nao_e_bloqueada(self, client):
        c, engine, estado = client
        pid = _criar_molde(c)

        r1 = _lancar(c, pid, ["422"], data_d0="2026-08-04")
        r2 = _lancar(c, pid, ["422"], data_d0="2026-08-05")
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]

    def test_lancamento_encerrado_nao_bloqueia_um_novo_igual(self, client):
        """Um lançamento idêntico mas já ENCERRADO não deve impedir um novo —
        encerrar é dizer "isto acabou", não "isto nunca existiu"; se o
        usuário quiser lançar de novo o mesmo protocolo/data/animal depois de
        encerrar o anterior, isso é uma decisão válida, não um duplo clique."""
        c, engine, estado = client
        pid = _criar_molde(c)

        r1 = _lancar(c, pid, ["422"])
        assert r1.status_code == 201, r1.text
        lancamento_id = r1.json()["lancamento_id"]

        r_encerrar = c.post(f"/central-protocolos/inducao/{lancamento_id}/encerrar", json={"motivo": "teste"})
        assert r_encerrar.status_code == 200, r_encerrar.text

        r2 = _lancar(c, pid, ["422"])
        assert r2.status_code == 201, r2.text
        assert r2.json()["criado"] is True
        assert r2.json()["lancamento_id"] != lancamento_id

    def test_lancamento_inativo_nao_bloqueia_um_novo_igual(self, client):
        """Mesma lógica para `ativo=False` (ex.: cancelado) — não deve
        contar como lançamento "equivalente" para fins de idempotência."""
        c, engine, estado = client
        pid = _criar_molde(c)

        r1 = _lancar(c, pid, ["422"])
        lancamento_id = r1.json()["lancamento_id"]
        with Session(engine) as s:
            lanc = s.get(ProtocoloInducaoLancamento, lancamento_id)
            lanc.ativo = False
            s.add(lanc)
            s.commit()

        r2 = _lancar(c, pid, ["422"])
        assert r2.status_code == 201, r2.text
        assert r2.json()["criado"] is True


@pytest.mark.xfail(
    reason=(
        "Bug de arquitetura confirmado também em IATF (reproducao.py "
        "lancar_protocolo_iatf) — mesma falta de proteção contra chamada "
        "repetida. Fora do escopo desta auditoria (só producao.py e "
        "nomenclatura_protocolo.py podiam ser corrigidos aqui); descrito no "
        "resumo para o orquestrador. Este teste documenta o comportamento "
        "ATUAL (duplica) e falhará sozinho quando reproducao.py ganhar a "
        "mesma proteção — nesse momento é só remover o xfail."
    ),
    strict=False,
)
def test_iatf_tem_o_mesmo_buraco_de_idempotencia_que_a_inducao_tinha(client):
    c, engine, estado = client
    r_molde = c.post("/cadastro/protocolos-iatf", json={
        "nome": "Protocolo IATF padrão",
        "etapas": [{"dia": 0, "produto": "Sincrodiol", "dose": 2.0, "unidade": "ml", "via": "Intramuscular"}],
    })
    assert r_molde.status_code == 200, r_molde.text
    pid = r_molde.json()["id"]

    payload = {"protocolo_id": pid, "animais": ["422"], "data_d0": "2026-08-04", "hormonios": []}
    r1 = c.post("/reproducao/protocolo-iatf", json=payload)
    r2 = c.post("/reproducao/protocolo-iatf", json=payload)
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text

    from fazenda.models import ProtocoloIatfLancamento
    with Session(engine) as s:
        total = len(s.exec(select(ProtocoloIatfLancamento)).all())
    # Comportamento hoje: 2 chamadas idênticas -> 2 lançamentos. Esperamos
    # que um dia isso vire 1 (mesma proteção que ganhamos em indução).
    assert total == 1, f"esperado 1 lançamento (idempotente), encontrado {total} — mesmo bug da indução, sem correção em reproducao.py"


class TestNomeGravadoNaCriacao:
    """`nome_protocolo` é sempre o nome LONGO e padronizado (gerar_nome_
    lancamento) no momento da criação — nunca o nome cru do molde. Se um
    lançamento aparece com o nome cru, não foi criado por esta rota hoje."""

    def test_nome_gravado_e_o_longo_padronizado_maiusculo_com_sufixo(self, client):
        c, engine, estado = client
        nome_molde = "Indução de Lactação — 18 dias (Ativos 2)"
        pid = _criar_molde(c, nome=nome_molde)

        r = _lancar(c, pid, ["422"], data_d0="2026-08-04")
        assert r.status_code == 201, r.text
        lancamento_id = r.json()["lancamento_id"]

        with Session(engine) as s:
            lanc = s.get(ProtocoloInducaoLancamento, lancamento_id)
            esperado = gerar_nome_lancamento(nome_molde, date(2026, 8, 4), 0, 3)
            assert lanc.nome_protocolo == esperado
            # Não é, e nunca é, o nome cru do molde.
            assert lanc.nome_protocolo != nome_molde
            assert lanc.nome_protocolo == lanc.nome_protocolo.upper()


class TestConvivenciaDeNomesAntigoENovo:
    """Reproduz a CONVIVÊNCIA dos dois formatos de nome vista no print — um
    lançamento "antigo" com o nome cru do molde (pré-nomenclatura automática,
    ou renomeado manualmente via /central-protocolos/.../renomear — fora do
    escopo) e um lançamento novo com o nome longo padronizado — inserindo o
    antigo DIRETO no banco (não existe rota atual que produza esse formato).
    Não reescrevemos o nome do lançamento antigo: o objetivo aqui é só
    confirmar que a Central convive bem com os dois formatos ao mesmo tempo,
    sem confundi-los."""

    def test_central_mostra_os_dois_formatos_sem_misturar(self, client):
        c, engine, estado = client
        pid = _criar_molde(c, nome="Indução de Lactação — 18 dias (Ativos 2)")

        # Simula o lançamento "antigo" com o nome cru do molde, como uma
        # migração anterior à nomenclatura automática (ou uma renomeação
        # manual) teria deixado — inserido direto, fora da rota de lançar.
        with Session(engine) as s:
            antigo = ProtocoloInducaoLancamento(
                protocolo_id=pid, nome_protocolo="Indução de Lactação — 18 dias (Ativos 2)",
                data_d0=date(2026, 8, 4), fazenda_id=1,
            )
            s.add(antigo)
            s.commit()
            s.refresh(antigo)
            s.add(ProtocoloInducaoAplicacao(
                lancamento_id=antigo.id, numero_matriz="900", dia=0, descricao="D0",
                data_prevista=date(2026, 8, 4), fazenda_id=1,
            ))
            s.commit()

        # E o lançamento novo, para um animal DIFERENTE — nome longo, gerado
        # pela rota normal.
        r = _lancar(c, pid, ["901"], data_d0="2026-08-04")
        assert r.status_code == 201, r.text

        linhas = c.get("/central-protocolos/acompanhamento").json()
        nomes = {l["nome"] for l in linhas if l["origem"] == "inducao"}
        assert "Indução de Lactação — 18 dias (Ativos 2)" in nomes
        assert any(n.startswith("INDUÇÃO DE LACTAÇÃO — 18 DIAS (ATIVOS 2) - 04/08/26") for n in nomes)
        # Os dois são o MESMO molde/período mas continuam sendo duas linhas
        # DIFERENTES (animais diferentes) — não é o bug, é o esperado.
        assert len(nomes) == 2


class TestNomeCurtoNaoAmbiguoDentroDoProprioCartao:
    """`nome_curto()` só remove o sufixo que `gerar_nome_lancamento()` mesmo
    monta; nome antigo (sem sufixo) passa batido. Dois lançamentos do MESMO
    molde em datas diferentes colapsam para o mesmo nome_curto — isso é
    esperado (o cartão da Agenda já mostra a data ao lado, ver docstring de
    nome_curto), não uma ambiguidade nova introduzida aqui."""

    def test_nome_curto_remove_so_o_sufixo_proprio(self):
        completo = gerar_nome_lancamento("Indução de Lactação — 18 dias (Ativos 2)", date(2026, 8, 4), 0, 18)
        assert nome_curto(completo) == "INDUÇÃO DE LACTAÇÃO — 18 DIAS (ATIVOS 2)"

    def test_nome_curto_de_nome_antigo_sem_sufixo_fica_intacto(self):
        antigo = "Indução de Lactação — 18 dias (Ativos 2)"
        assert nome_curto(antigo) == antigo

    def test_dois_lancamentos_do_mesmo_molde_em_datas_diferentes_colapsam_no_nome_curto(self):
        # Documenta o comportamento — não é bug: a Agenda mostra a data do
        # cartão ao lado do nome_curto, então dois cartões com o mesmo
        # nome_curto em dias diferentes não se confundem na tela.
        c1 = gerar_nome_lancamento("Indução de Lactação — 18 dias (Ativos 2)", date(2026, 8, 4), 0, 18)
        c2 = gerar_nome_lancamento("Indução de Lactação — 18 dias (Ativos 2)", date(2026, 9, 1), 0, 18)
        assert c1 != c2
        assert nome_curto(c1) == nome_curto(c2)
