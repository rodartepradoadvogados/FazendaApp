"""
Rotina automatica da lista de espera (docs/agents/auditoria-preventivo-agenda/
planejamento/11-rotina-lista-de-espera.md).

So atua com (1) rotina ativada nos Parametros da fazenda (padrao desligada),
(2) regras de vacina/exame cadastradas, (3) o resto vem da regra. Nunca aplica,
baixa estoque, lanca Sanidade nem cria agendamento; so cria/atualiza lista de
espera ("sugerido"), idempotente, R8, sem baixados/ja vacinados, e nunca vira
tarefa do Dia a dia.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, CalendarioSanitario, CategoriaManejo, ContratoFazenda, ContratoFazendaModulo, CronogramaSanitario,
    CronogramaSanitarioAnimal, CronogramaSanitarioLog, EventoSanitario, Fazenda, ParametroFazenda,
    RotinaListaEsperaEstado, Sanidade,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import rotina_lista_espera as rotina
from fazenda.rules.parametros import fazenda_atual

HOJE = date.today()


@pytest.fixture
def ctx(monkeypatch):
    engine = create_engine(f"sqlite:///{tempfile.mktemp(suffix='.db')}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(database, "engine", engine)
    with Session(engine) as s:
        for fid in (1, 2):
            s.add(Fazenda(id=fid, nome=f"Fazenda {fid}"))
            s.add(ContratoFazenda(fazenda_id=fid, status="ativo"))
            for modulo in MODULOS_COMERCIAIS:
                s.add(ContratoFazendaModulo(fazenda_id=fid, modulo=modulo, preco=0.0, ativo=True))
        s.add(CategoriaManejo(nome="Novilha", dia_min=91, dia_max=730, ordem=1))
        s.commit()

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id

    class _FakeUser:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "teste@example.com"
        permissoes = ""

    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: _FakeUser()
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: 1
    with TestClient(main.app) as c:
        yield c, engine
    main.app.dependency_overrides.clear()
    fazenda_atual.set(None)


def _param(s: Session, chave: str, valor: str, fazenda_id: int | None = 1) -> None:
    linha = s.exec(select(ParametroFazenda).where(ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == fazenda_id)).first()
    if linha is None:
        linha = ParametroFazenda(chave=chave, fazenda_id=fazenda_id, grupo="lista_espera", label=chave, valor=valor, tipo="texto")
    linha.valor = valor
    s.add(linha)
    s.commit()


def _ligar(s: Session, *, dias: int | None = None, aviso: bool = False, fazenda_id: int = 1) -> None:
    _param(s, rotina.CHAVE_ATIVA, "true", fazenda_id)
    if dias is not None:
        _param(s, rotina.CHAVE_DIAS, str(dias), fazenda_id)
    if aviso:
        _param(s, rotina.CHAVE_AVISO, "true", fazenda_id)


def _animais(s: Session, *numeros: str, fazenda_id: int = 1, **extra) -> None:
    for n in numeros:
        s.add(Animal(numero=n, data_nasc=HOJE - timedelta(days=100), ativo=True, sexo="F", fazenda_id=fazenda_id, **extra))
    s.commit()


def _regra(s: Session, *, data_evento: date, fazenda_id: int = 1, categoria_preventiva: str | None = "vacina",
           produto: str = "Vacina X", antecedencia: int | None = None, tipo: str = "epoca") -> int:
    n = len(s.exec(select(EventoSanitario)).all())
    ev = EventoSanitario(nome=f"Vacina X {n}", tipo_agendamento=tipo, fazenda_id=fazenda_id, categoria_preventiva=categoria_preventiva)
    s.add(ev)
    s.commit()
    s.refresh(ev)
    cal = CalendarioSanitario(
        evento_sanitario_id=ev.id, categoria_alvo="Novilha", produto=produto, frequencia_valor=6, frequencia_unidade="meses",
        data_evento=data_evento, usa_cronograma=True, fazenda_id=fazenda_id, dias_antecedencia_lista_espera=antecedencia,
    )
    s.add(cal)
    s.commit()
    s.refresh(cal)
    return cal.id


def _sugeridos(engine, fazenda_id: int = 1) -> list[str]:
    with Session(engine) as s:
        return sorted(
            l.numero_matriz for l in s.exec(select(CronogramaSanitarioAnimal).where(CronogramaSanitarioAnimal.fazenda_id == fazenda_id)).all()
            if l.status == "sugerido"
        )


def _rodar(engine, origem="diaria", fazenda_id=1, **kw) -> dict:
    with Session(engine) as s:
        return rotina.executar_fazenda(s, fazenda_id, origem, **kw)


# ---------------------------------------------------------------------------
class TestCondicionantes:
    def test_desligada_por_padrao_nao_faz_nada(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _regra(s, data_evento=HOJE + timedelta(days=5))
        r = _rodar(engine)
        assert r["executou"] is False and r["motivo"] == "desligada"
        assert _sugeridos(engine) == []
        with Session(engine) as s:
            assert s.exec(select(CronogramaSanitario)).all() == []
            assert s.exec(select(RotinaListaEsperaEstado)).all() == []

    def test_ligada_sem_regras_nao_faz_nada(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
        r = _rodar(engine)
        assert r["executou"] and r["motivo"] == "sem_regras" and r["entraram"] == 0
        assert _sugeridos(engine) == []
        with Session(engine) as s:
            assert s.exec(select(CronogramaSanitario)).all() == []

    def test_tratamento_nao_e_vacina_nem_exame(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=5), categoria_preventiva="tratamento")
        r = _rodar(engine)
        assert r["motivo"] == "sem_regras" and _sugeridos(engine) == []

    def test_ligada_com_regra_na_janela_cria_a_lista_de_espera(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55", "56")
            _ligar(s, dias=15)
            _regra(s, data_evento=HOJE + timedelta(days=10))
        r = _rodar(engine)
        assert r["executou"] and r["motivo"] == "ok" and r["entraram"] == 2 and r["regras_na_janela"] == 1
        assert _sugeridos(engine) == ["55", "56"]

    def test_exame_tambem_entra(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s, dias=15)
            _regra(s, data_evento=HOJE + timedelta(days=10), categoria_preventiva="exame")
        assert _rodar(engine)["entraram"] == 1

    def test_regra_fora_da_janela_de_antecedencia_nao_entra(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s, dias=15)
            _regra(s, data_evento=HOJE + timedelta(days=40))
        r = _rodar(engine)
        assert r["entraram"] == 0 and r["regras_na_janela"] == 0
        assert _sugeridos(engine) == []

    def test_antecedencia_da_regra_sobrescreve_a_da_fazenda(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s, dias=5)
            _regra(s, data_evento=HOJE + timedelta(days=30), antecedencia=45)
        assert _rodar(engine)["entraram"] == 1

    def test_regra_por_evento_de_vida_fica_de_fora(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s, dias=15)
            _regra(s, data_evento=HOJE + timedelta(days=2), tipo="evento")
        assert _rodar(engine)["entraram"] == 0


class TestNuncaAplicaNemAgenda:
    def test_so_cria_lista_de_espera(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))
        _rodar(engine)
        with Session(engine) as s:
            crons = s.exec(select(CronogramaSanitario)).all()
            assert [c.status for c in crons] == ["aberto"]           # nenhum agendamento
            assert s.exec(select(Sanidade)).all() == []               # nada aplicado
            logs = s.exec(select(CronogramaSanitarioLog)).all()
            assert [l.acao for l in logs] == ["Lista de espera (rotina)"] and logs[0].canal == "rotina"

    def test_idempotente(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55", "56")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))
        assert _rodar(engine, "manual")["entraram"] == 2
        assert _rodar(engine, "manual")["entraram"] == 0
        assert _sugeridos(engine) == ["55", "56"]
        with Session(engine) as s:
            assert len(s.exec(select(CronogramaSanitario)).all()) == 1
            assert len(s.exec(select(CronogramaSanitarioLog)).all()) == 1   # 2a rodada nao entrou ninguem: sem log

    def test_animal_ja_em_agendamento_nao_entra_de_novo_r8(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55", "56")
            _ligar(s)
            cal = _regra(s, data_evento=HOJE + timedelta(days=3))
            agendado = CronogramaSanitario(calendario_sanitario_id=cal, data_evento=HOJE + timedelta(days=3), status="agendado",
                                           modo_execucao="propria", fazenda_id=1)
            s.add(agendado)
            s.commit()
            s.refresh(agendado)
            s.add(CronogramaSanitarioAnimal(cronograma_id=agendado.id, numero_matriz="55", status="incluido",
                                            data_sugestao=HOJE, fazenda_id=1))
            s.commit()
        _rodar(engine)
        assert _sugeridos(engine) == ["56"]

    def test_vendido_baixado_e_ja_vacinado_no_ciclo_ficam_de_fora(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55", "56", "57", "58")
            s.exec(select(Animal).where(Animal.numero == "56")).one().ativo = False
            s.exec(select(Animal).where(Animal.numero == "57")).one().data_baixa = HOJE - timedelta(days=3)
            s.add(Sanidade(numero_matriz="58", produto="Vacina X", data_aplicacao=HOJE - timedelta(days=20),
                           natureza="preventivo", fazenda_id=1))
            s.commit()
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))
        _rodar(engine)
        assert _sugeridos(engine) == ["55"]

    def test_macho_nunca_entra(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            s.add(Animal(numero="M1", data_nasc=HOJE - timedelta(days=100), ativo=True, sexo="M", fazenda_id=1))
            s.commit()
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3), produto="Brucelose B19")
        _rodar(engine)
        assert _sugeridos(engine) == ["55"]

    def test_isolamento_entre_fazendas(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _animais(s, "77", fazenda_id=2)
            _ligar(s, fazenda_id=1)
            _regra(s, data_evento=HOJE + timedelta(days=3), fazenda_id=1)
            _regra(s, data_evento=HOJE + timedelta(days=3), fazenda_id=2)   # fazenda 2 NAO ligou a rotina
        resumo = rotina.executar_todas_as_fazendas(Session(engine))
        assert resumo["processadas"] == 1
        assert _sugeridos(engine, 1) == ["55"]
        assert _sugeridos(engine, 2) == []


class TestConcorrenciaEAviso:
    def test_diaria_roda_uma_vez_por_dia(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))
        assert _rodar(engine)["executou"] is True
        r2 = _rodar(engine)
        assert r2["executou"] is False and r2["motivo"] == "ja_executou_hoje"
        amanha = _rodar(engine, hoje=HOJE + timedelta(days=1), agora=datetime.now() + timedelta(days=1))
        assert amanha["executou"] is True

    def test_lock_impede_execucao_simultanea(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))
            rotina._estado(s, 1)
            estado = s.exec(select(RotinaListaEsperaEstado)).one()
            estado.em_execucao_ate = datetime.now() + timedelta(minutes=10)   # outra instancia esta rodando
            s.add(estado)
            s.commit()
        r = _rodar(engine, "manual")
        assert r["executou"] is False and r["motivo"] == "em_execucao"
        assert _sugeridos(engine) == []

    def test_lock_vencido_e_retomado(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))
            rotina._estado(s, 1)
            estado = s.exec(select(RotinaListaEsperaEstado)).one()
            estado.em_execucao_ate = datetime.now() - timedelta(minutes=1)   # instancia morta
            s.add(estado)
            s.commit()
        assert _rodar(engine, "manual")["executou"] is True

    def test_lock_e_liberado_ao_final(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))
        _rodar(engine, "manual")
        with Session(engine) as s:
            assert s.exec(select(RotinaListaEsperaEstado)).one().em_execucao_ate is None

    def test_aviso_diario_no_maximo_uma_vez_por_dia(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s, aviso=True)
            _regra(s, data_evento=HOJE + timedelta(days=3))
        r1 = _rodar(engine, "manual")
        r2 = _rodar(engine, "manual")
        assert r1["aviso_emitido"] is True and r2["aviso_emitido"] is False
        with Session(engine) as s:
            assert s.exec(select(RotinaListaEsperaEstado)).one().ultimo_aviso_em == HOJE

    def test_sem_aviso_ligado_nao_registra_aviso(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s, aviso=False)
            _regra(s, data_evento=HOJE + timedelta(days=3))
        assert _rodar(engine)["aviso_emitido"] is False
        with Session(engine) as s:
            assert s.exec(select(RotinaListaEsperaEstado)).one().ultimo_aviso_em is None

    def test_erro_de_uma_fazenda_nao_derruba_o_estado(self, ctx, monkeypatch):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))

        def _boom(*a, **k):
            raise RuntimeError("falhou")

        monkeypatch.setattr(rotina, "_processar", _boom)
        r = _rodar(engine)
        assert r["executou"] and r["motivo"] == "erro"
        with Session(engine) as s:
            estado = s.exec(select(RotinaListaEsperaEstado)).one()
            assert estado.ultima_execucao_status == "erro" and "falhou" in estado.ultimo_erro
            assert estado.ultima_diaria_em is None and estado.em_execucao_ate is None   # tenta de novo


class TestEndpoints:
    def _montar(self, engine, *, aviso: bool):
        with Session(engine) as s:
            _animais(s, "55", "56")
            _ligar(s, aviso=aviso)
            _regra(s, data_evento=HOJE + timedelta(days=3))

    def test_status_e_executar_agora(self, ctx):
        c, engine = ctx
        st = c.get("/agenda/lista-espera-rotina/status").json()
        assert st["ativa"] is False and st["ultima_execucao_em"] is None and st["dias_antecedencia"] == 15
        r = c.post("/agenda/lista-espera-rotina/executar")
        assert r.status_code == 400   # desligada
        self._montar(engine, aviso=False)
        r = c.post("/agenda/lista-espera-rotina/executar")
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["resultado"]["entraram"] == 2
        assert corpo["status"]["entraram"] == 2 and corpo["status"]["na_lista_de_espera"] == 2
        assert corpo["status"]["ultima_execucao_origem"] == "manual" and corpo["status"]["tem_regras"] is True

    def test_salvar_parametro_ativa_e_executa_na_hora(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _regra(s, data_evento=HOJE + timedelta(days=3))
            for chave, valor, tipo in ((rotina.CHAVE_ATIVA, "false", "bool"), (rotina.CHAVE_DIAS, "15", "int"), (rotina.CHAVE_AVISO, "false", "bool")):
                s.add(ParametroFazenda(chave=chave, fazenda_id=None, grupo="lista_espera", label=chave, valor=valor, tipo=tipo))
            s.commit()
        r = c.put(f"/parametros/{rotina.CHAVE_DIAS}", json={"valor": 20})
        assert r.status_code == 200 and r.json()["rotina_lista_espera"]["motivo"] == "desligada"
        assert _sugeridos(engine) == []
        r = c.put(f"/parametros/{rotina.CHAVE_ATIVA}", json={"valor": True})
        assert r.status_code == 200 and r.json()["rotina_lista_espera"]["entraram"] == 1
        assert _sugeridos(engine) == ["55"]
        st = c.get("/agenda/lista-espera-rotina/status").json()
        assert st["ativa"] is True and st["dias_antecedencia"] == 20 and st["ultima_execucao_origem"] == "parametros"

    def test_card_no_painel_so_com_aviso_ligado_e_nunca_no_dia_a_dia(self, ctx):
        c, engine = ctx
        self._montar(engine, aviso=False)
        _rodar(engine, "manual")
        painel = c.get("/agenda/painel").json()
        assert painel["lista_espera_total"] == 2 and painel["rotina_lista_espera"]["mostrar_card"] is False
        with Session(engine) as s:
            _param(s, rotina.CHAVE_AVISO, "true")
        assert c.get("/agenda/painel").json()["rotina_lista_espera"]["mostrar_card"] is True
        with Session(engine) as s:
            _param(s, rotina.CHAVE_ATIVA, "false")
        assert c.get("/agenda/painel").json()["rotina_lista_espera"]["mostrar_card"] is False
        with Session(engine) as s:
            _param(s, rotina.CHAVE_ATIVA, "true")
        dia = c.get("/agenda/dia").json()
        assert "espera" not in str(dia).lower()   # a rotina nunca vira item do Dia a dia

    def test_resumo_global_do_painel_cowdata(self, ctx):
        _, engine = ctx
        with Session(engine) as s:
            _animais(s, "55")
            _ligar(s)
            _regra(s, data_evento=HOJE + timedelta(days=3))
            resumo = rotina.resumo_global(s)
            assert resumo["fazendas_ativas"] == 1 and resumo["fazendas_processadas_hoje"] == 0
        rotina.executar_todas_as_fazendas(Session(engine))
        with Session(engine) as s:
            resumo = rotina.resumo_global(s)
        assert resumo["fazendas_processadas_hoje"] == 1 and resumo["entraram_ultima_passada"] == 1
        assert resumo["erros"] == [] and resumo["ultima_execucao_em"]
