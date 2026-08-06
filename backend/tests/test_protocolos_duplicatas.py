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

2. ATUALIZAÇÃO — as outras 4 famílias de protocolo (IATF em reproducao.py,
   sanitário em sanidade.py, customizado em protocolos_customizados.py, lida
   em lida.py) tinham o MESMO buraco de idempotência — nenhuma verificava se
   já existia um lançamento equivalente antes de criar um novo. Isto ERA
   documentado como bug de arquitetura fora do escopo (item xfail abaixo);
   nesta rodada seguinte, as 4 ganharam a MESMA proteção da indução —
   `TestIdempotenciaIatf`, `TestIdempotenciaCustomizado`, `TestIdempotenciaLida`
   e `TestIdempotenciaSanitario` abaixo. Duas particularidades por família:
   - IATF sem molde (`protocolo_id is None`, hormônios digitados na hora): a
     equivalência usa data_d0 + animais + o CONJUNTO DE HORMÔNIOS aplicados
     (não só data_d0 + animais), porque dois lançamentos ad-hoc distintos
     podem legitimamente coincidir em animal/data com um hormônio diferente
     — ver comentário em `lancar_protocolo_iatf`.
   - Sanitário é estruturalmente diferente: `ProtocoloSanitarioLancamento` é
     POR ANIMAL (sem cabeçalho de lote) e não tem `ativo`/`encerrado_em` (a
     Central de Protocolos nem oferece cancelar/encerrar essa origem). A
     proteção aqui é PARCIAL, não tudo-ou-nada: pula, animal a animal, quem
     já tem (protocolo_id, data_inicio, numero_matriz) idêntico e cria
     normalmente o resto, informando quantos foram pulados em `pulados` — ver
     comentário em `lancar_protocolo` (sanidade.py).

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

    # /producao, /reproducao, /sanidade e /cadastro exigem contrato ativo (+
    # módulo comercial específico — "produtivo"/"reprodutivo"/"sanitario",
    # ver main.py) — sem isso todo POST cai em 403 antes mesmo de chegar na
    # lógica que este arquivo testa (mesmo padrão de test_inducao_fazenda_id.
    # py). /protocolos-customizados e /lida só exigem contrato ativo (sem
    # módulo comercial próprio), mas conceder os três módulos aqui não
    # atrapalha esses testes.
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in ("produtivo", "reprodutivo", "sanitario"):
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, ativo=True))
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


def _criar_molde_iatf(c, nome="Protocolo IATF padrão"):
    r = c.post("/cadastro/protocolos-iatf", json={
        "nome": nome,
        "etapas": [{"dia": 0, "produto": "Sincrodiol", "dose": 2.0, "unidade": "ml", "via": "Intramuscular"}],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _lancar_iatf(c, animais, data_d0="2026-08-04", protocolo_id=None, hormonios=None):
    return c.post("/reproducao/protocolo-iatf", json={
        "protocolo_id": protocolo_id, "animais": animais, "data_d0": data_d0,
        "hormonios": hormonios or [],
    })


class TestIdempotenciaIatf:
    """IATF ganhou a MESMA proteção que a indução de lactação (ver
    lancar_protocolo_iatf em reproducao.py) — este teste antes documentava o
    buraco (`xfail`, "test_iatf_tem_o_mesmo_buraco_de_idempotencia_que_a_
    inducao_tinha"); agora que reproducao.py está corrigido, vira teste
    normal do comportamento esperado."""

    def test_chamada_repetida_nao_duplica_o_lancamento(self, client):
        c, engine, estado = client
        pid = _criar_molde_iatf(c)

        # A rota nunca teve status_code=201 (sempre devolveu 200, criado ou
        # não) — diferente de indução/customizado/lida/sanitário, que ganharam
        # 201 na criação quando esta auditoria criou aquelas rotas do zero ou
        # as tocou. Mudar o status agora quebraria os testes existentes desta
        # rota (test_protocolos_ciclo_vida.py, test_central_protocolos.py)
        # que já esperam 200; por isso aqui a distinção "criado" é só pelo
        # campo `criado` do corpo, não pelo HTTP status.
        r1 = _lancar_iatf(c, ["422"], protocolo_id=pid)
        assert r1.status_code == 200, r1.text
        corpo1 = r1.json()
        assert corpo1["criado"] is True

        r2 = _lancar_iatf(c, ["422"], protocolo_id=pid)
        assert r2.status_code == 200, r2.text
        corpo2 = r2.json()
        assert corpo2["criado"] is False
        assert corpo2["lancamento_id"] == corpo1["lancamento_id"]
        assert corpo2["eventos_criados"] == 0
        assert "aviso" in corpo2

        from fazenda.models import ProtocoloIatfLancamento
        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloIatfLancamento)).all()) == 1

    def test_animais_diferentes_nao_sao_bloqueados(self, client):
        c, engine, estado = client
        pid = _criar_molde_iatf(c)

        r1 = _lancar_iatf(c, ["422"], protocolo_id=pid)
        r2 = _lancar_iatf(c, ["500"], protocolo_id=pid)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["criado"] is True and r2.json()["criado"] is True
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]

        from fazenda.models import ProtocoloIatfLancamento
        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloIatfLancamento)).all()) == 2

    def test_data_d0_diferente_nao_e_bloqueada(self, client):
        c, engine, estado = client
        pid = _criar_molde_iatf(c)

        r1 = _lancar_iatf(c, ["422"], data_d0="2026-08-04", protocolo_id=pid)
        r2 = _lancar_iatf(c, ["422"], data_d0="2026-08-05", protocolo_id=pid)
        assert r1.json()["criado"] is True and r2.json()["criado"] is True
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]

    def test_lancamento_cancelado_nao_bloqueia_um_novo_igual(self, client):
        c, engine, estado = client
        pid = _criar_molde_iatf(c)

        r1 = _lancar_iatf(c, ["422"], protocolo_id=pid)
        lancamento_id = r1.json()["lancamento_id"]
        from fazenda.models import ProtocoloIatfLancamento
        with Session(engine) as s:
            lanc = s.get(ProtocoloIatfLancamento, lancamento_id)
            lanc.ativo = False
            s.add(lanc)
            s.commit()

        r2 = _lancar_iatf(c, ["422"], protocolo_id=pid)
        assert r2.status_code == 200, r2.text
        assert r2.json()["criado"] is True
        assert r2.json()["lancamento_id"] != lancamento_id

    def test_lancamento_encerrado_nao_bloqueia_um_novo_igual(self, client):
        c, engine, estado = client
        pid = _criar_molde_iatf(c)

        r1 = _lancar_iatf(c, ["422"], protocolo_id=pid)
        lancamento_id = r1.json()["lancamento_id"]
        r_encerrar = c.post(f"/central-protocolos/iatf/{lancamento_id}/encerrar", json={"motivo": "teste"})
        assert r_encerrar.status_code == 200, r_encerrar.text

        r2 = _lancar_iatf(c, ["422"], protocolo_id=pid)
        assert r2.status_code == 200, r2.text
        assert r2.json()["criado"] is True

    def test_ad_hoc_sem_molde_chamada_repetida_nao_duplica(self, client):
        """Lançamento sem `protocolo_id` (hormônios digitados na hora, sem
        molde cadastrado) — a equivalência aqui usa data_d0 + animais +
        hormônios (ver comentário em lancar_protocolo_iatf)."""
        c, engine, estado = client
        hormonios = [{"dia": 0, "produto": "SincroCP", "dose": 1.0, "unidade": "ml", "via": "Intramuscular"}]

        r1 = _lancar_iatf(c, ["422"], hormonios=hormonios)
        assert r1.status_code == 200, r1.text
        corpo1 = r1.json()
        assert corpo1["criado"] is True

        r2 = _lancar_iatf(c, ["422"], hormonios=hormonios)
        assert r2.status_code == 200, r2.text
        corpo2 = r2.json()
        assert corpo2["criado"] is False
        assert corpo2["lancamento_id"] == corpo1["lancamento_id"]

        from fazenda.models import ProtocoloIatfLancamento
        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloIatfLancamento)).all()) == 1

    def test_ad_hoc_hormonios_diferentes_nao_sao_bloqueados(self, client):
        """Dois lançamentos ad-hoc LEGÍTIMOS e distintos (mesmo animal/data,
        hormônio diferente) não se confundem com um retry."""
        c, engine, estado = client
        h1 = [{"dia": 0, "produto": "SincroCP", "dose": 1.0, "unidade": "ml", "via": "Intramuscular"}]
        h2 = [{"dia": 0, "produto": "Estron", "dose": 2.0, "unidade": "ml", "via": "Intramuscular"}]

        r1 = _lancar_iatf(c, ["422"], hormonios=h1)
        r2 = _lancar_iatf(c, ["422"], hormonios=h2)
        assert r1.json()["criado"] is True and r2.json()["criado"] is True
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]


def _criar_molde_customizado(c, nome="Vacina Rebanho"):
    r = c.post("/cadastro/protocolos-customizados", json={
        "nome": nome, "categoria": "Rebanho", "dia_inicial": 0,
        "etapas": [
            {"dia": 0, "descricao_evento": "Aplicar vacina", "insumo_padrao": "Vacina X", "dose": 2, "unidade": "ml"},
            {"dia": 21, "descricao_evento": "Reforço"},
        ],
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _lancar_customizado(c, pid, animais, data_inicio="2026-08-04", lote=None):
    return c.post("/protocolos-customizados/lancar", json={
        "protocolo_id": pid, "animais": animais, "lote": lote, "data_inicio": data_inicio,
    })


class TestIdempotenciaCustomizado:
    """Mesma proteção replicada em protocolos_customizados.lancar_protocolo_
    customizado — ver o comentário "Idempotência:" lá."""

    def test_chamada_repetida_nao_duplica_o_lancamento(self, client):
        c, engine, estado = client
        pid = _criar_molde_customizado(c)

        r1 = _lancar_customizado(c, pid, ["422"])
        assert r1.status_code == 201, r1.text
        corpo1 = r1.json()
        assert corpo1["criado"] is True

        r2 = _lancar_customizado(c, pid, ["422"])
        assert r2.status_code == 200, r2.text
        corpo2 = r2.json()
        assert corpo2["criado"] is False
        assert corpo2["lancamento_id"] == corpo1["lancamento_id"]
        assert corpo2["eventos_criados"] == 0
        assert "aviso" in corpo2

        from fazenda.models import ProtocoloCustomizadoLancamento
        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloCustomizadoLancamento)).all()) == 1

    def test_animais_diferentes_nao_sao_bloqueados(self, client):
        c, engine, estado = client
        pid = _criar_molde_customizado(c)

        r1 = _lancar_customizado(c, pid, ["422"])
        r2 = _lancar_customizado(c, pid, ["500"])
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]

    def test_data_diferente_nao_e_bloqueada(self, client):
        c, engine, estado = client
        pid = _criar_molde_customizado(c)

        r1 = _lancar_customizado(c, pid, ["422"], data_inicio="2026-08-04")
        r2 = _lancar_customizado(c, pid, ["422"], data_inicio="2026-08-05")
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]

    def test_lancamento_cancelado_nao_bloqueia_um_novo_igual(self, client):
        c, engine, estado = client
        pid = _criar_molde_customizado(c)

        r1 = _lancar_customizado(c, pid, ["422"])
        lancamento_id = r1.json()["lancamento_id"]
        r_cancelar = c.post(f"/protocolos-customizados/{lancamento_id}/cancelar")
        assert r_cancelar.status_code == 200, r_cancelar.text

        r2 = _lancar_customizado(c, pid, ["422"])
        assert r2.status_code == 201, r2.text
        assert r2.json()["criado"] is True

    def test_lancamento_encerrado_nao_bloqueia_um_novo_igual(self, client):
        c, engine, estado = client
        pid = _criar_molde_customizado(c)

        r1 = _lancar_customizado(c, pid, ["422"])
        lancamento_id = r1.json()["lancamento_id"]
        r_encerrar = c.post(f"/central-protocolos/customizado/{lancamento_id}/encerrar", json={"motivo": "teste"})
        assert r_encerrar.status_code == 200, r_encerrar.text

        r2 = _lancar_customizado(c, pid, ["422"])
        assert r2.status_code == 201, r2.text
        assert r2.json()["criado"] is True

    def test_tarefa_da_fazenda_sem_animal_chamada_repetida_nao_duplica(self, client):
        """`animais=[]` (tarefa da fazenda, sem animal específico) também é
        protegida — o conjunto vazio compara certo com outro vazio."""
        c, engine, estado = client
        pid = _criar_molde_customizado(c)

        r1 = _lancar_customizado(c, pid, [])
        assert r1.status_code == 201, r1.text
        r2 = _lancar_customizado(c, pid, [])
        assert r2.status_code == 200, r2.text
        assert r2.json()["criado"] is False
        assert r2.json()["lancamento_id"] == r1.json()["lancamento_id"]


def _criar_molde_lida(c, nome="Limpar cocho"):
    r = c.post("/cadastro/lidas", json={
        "nome": nome, "modo": "periodo", "dia_inicial": 0,
        "etapas": [{"dia_inicio": 0, "descricao_evento": "Limpar cocho"}],
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _lancar_lida(c, lida_id, animais, data_inicio="2026-08-04"):
    return c.post("/lida/lancar", json={
        "lida_id": lida_id, "animais": animais, "data_inicio": data_inicio,
    })


class TestIdempotenciaLida:
    """Mesma proteção replicada em lida.lancar_lida — ver o comentário
    "Idempotência:" lá."""

    def test_chamada_repetida_nao_duplica_o_lancamento(self, client):
        c, engine, estado = client
        lid = _criar_molde_lida(c)

        r1 = _lancar_lida(c, lid, ["422"])
        assert r1.status_code == 201, r1.text
        corpo1 = r1.json()
        assert corpo1["criado"] is True

        r2 = _lancar_lida(c, lid, ["422"])
        assert r2.status_code == 200, r2.text
        corpo2 = r2.json()
        assert corpo2["criado"] is False
        assert corpo2["lancamento_id"] == corpo1["lancamento_id"]
        assert corpo2["eventos_criados"] == 0
        assert "aviso" in corpo2

        from fazenda.models import LidaLancamento
        with Session(engine) as s:
            assert len(s.exec(select(LidaLancamento)).all()) == 1

    def test_animais_diferentes_nao_sao_bloqueados(self, client):
        c, engine, estado = client
        lid = _criar_molde_lida(c)

        r1 = _lancar_lida(c, lid, ["422"])
        r2 = _lancar_lida(c, lid, ["500"])
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]

    def test_data_diferente_nao_e_bloqueada(self, client):
        c, engine, estado = client
        lid = _criar_molde_lida(c)

        r1 = _lancar_lida(c, lid, ["422"], data_inicio="2026-08-04")
        r2 = _lancar_lida(c, lid, ["422"], data_inicio="2026-08-05")
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["lancamento_id"] != r2.json()["lancamento_id"]

    def test_lancamento_cancelado_nao_bloqueia_um_novo_igual(self, client):
        c, engine, estado = client
        lid = _criar_molde_lida(c)

        r1 = _lancar_lida(c, lid, ["422"])
        from fazenda.models import LidaLancamento
        with Session(engine) as s:
            lanc = s.get(LidaLancamento, r1.json()["lancamento_id"])
            lanc.ativo = False
            s.add(lanc)
            s.commit()

        r2 = _lancar_lida(c, lid, ["422"])
        assert r2.status_code == 201, r2.text
        assert r2.json()["criado"] is True

    def test_lancamento_encerrado_nao_bloqueia_um_novo_igual(self, client):
        c, engine, estado = client
        lid = _criar_molde_lida(c)

        r1 = _lancar_lida(c, lid, ["422"])
        lancamento_id = r1.json()["lancamento_id"]
        r_encerrar = c.post(f"/central-protocolos/lida/{lancamento_id}/encerrar", json={"motivo": "teste"})
        assert r_encerrar.status_code == 200, r_encerrar.text

        r2 = _lancar_lida(c, lid, ["422"])
        assert r2.status_code == 201, r2.text
        assert r2.json()["criado"] is True

    def test_tarefa_da_fazenda_sem_animal_chamada_repetida_nao_duplica(self, client):
        c, engine, estado = client
        lid = _criar_molde_lida(c)

        r1 = _lancar_lida(c, lid, [])
        assert r1.status_code == 201, r1.text
        r2 = _lancar_lida(c, lid, [])
        assert r2.status_code == 200, r2.text
        assert r2.json()["criado"] is False
        assert r2.json()["lancamento_id"] == r1.json()["lancamento_id"]


def _criar_molde_sanitario(c, nome="Protocolo Mastite Clínica"):
    r = c.post("/cadastro/protocolos-sanitarios", json={
        "nome": nome, "dia_inicial": 0,
        "etapas": [{"dia": 0, "produto": "Antibiótico X", "dosagem": 5.0, "unidade": "ml"}],
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _lancar_sanitario(c, pid, numeros, data_inicio="2026-08-04"):
    return c.post("/sanidade/protocolos/lancamentos", json={
        "protocolo_id": pid, "numeros_matriz": numeros, "data_inicio": data_inicio,
    })


class TestIdempotenciaSanitario:
    """`ProtocoloSanitarioLancamento` é POR ANIMAL (sem cabeçalho de lote) —
    a proteção replicada em sanidade.lancar_protocolo pula, animal a animal,
    quem já tem (protocolo_id, data_inicio, numero_matriz) idêntico, em vez
    de recusar a chamada inteira (ver comentário "Idempotência:" lá)."""

    def test_chamada_repetida_nao_duplica(self, client):
        c, engine, estado = client
        pid = _criar_molde_sanitario(c)

        r1 = _lancar_sanitario(c, pid, ["422"])
        assert r1.status_code == 201, r1.text
        assert r1.json()["criados"] == 1
        assert r1.json()["pulados"] == 0

        r2 = _lancar_sanitario(c, pid, ["422"])
        assert r2.status_code == 200, r2.text
        assert r2.json()["criados"] == 0
        assert r2.json()["pulados"] == 1

        from fazenda.models import ProtocoloSanitarioLancamento
        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloSanitarioLancamento)).all()) == 1

    def test_animais_diferentes_nao_sao_bloqueados(self, client):
        c, engine, estado = client
        pid = _criar_molde_sanitario(c)

        r1 = _lancar_sanitario(c, pid, ["422"])
        r2 = _lancar_sanitario(c, pid, ["500"])
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["criados"] == 1 and r2.json()["criados"] == 1

        from fazenda.models import ProtocoloSanitarioLancamento
        with Session(engine) as s:
            assert len(s.exec(select(ProtocoloSanitarioLancamento)).all()) == 2

    def test_data_diferente_nao_e_bloqueada(self, client):
        c, engine, estado = client
        pid = _criar_molde_sanitario(c)

        r1 = _lancar_sanitario(c, pid, ["422"], data_inicio="2026-08-04")
        r2 = _lancar_sanitario(c, pid, ["422"], data_inicio="2026-08-05")
        assert r1.status_code == 201 and r2.status_code == 201
        assert r1.json()["criados"] == 1 and r2.json()["criados"] == 1

    def test_relancar_mesmos_3_mais_1_novo_so_o_novo_e_criado(self, client):
        """3 animais lançados, depois relançados junto com um 4º novo — só o
        novo entra; os 3 repetidos são pulados, não duplicados."""
        c, engine, estado = client
        pid = _criar_molde_sanitario(c)

        r1 = _lancar_sanitario(c, pid, ["100", "200", "300"])
        assert r1.status_code == 201, r1.text
        assert r1.json()["criados"] == 3

        r2 = _lancar_sanitario(c, pid, ["100", "200", "300", "400"])
        assert r2.status_code == 201, r2.text  # ainda cria 1 novo -> 201
        assert r2.json()["criados"] == 1
        assert r2.json()["pulados"] == 3
        assert len(r2.json()["avisos"]) >= 1

        from fazenda.models import ProtocoloSanitarioLancamento
        with Session(engine) as s:
            todos = s.exec(select(ProtocoloSanitarioLancamento)).all()
            assert len(todos) == 4
            assert {l.numero_matriz for l in todos} == {"100", "200", "300", "400"}


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
