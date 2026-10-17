"""
Deteccao de cio de repasse configuravel por fazenda (fatia 10, item C):
regra pura, endpoints de configuracao (/agenda/repasse/*) e efeito no motor da
Agenda (GET /agenda). Fazenda sem configuracao segue o comportamento legado.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import date, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mktemp(suffix='.db')}"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

import fazenda.database as database
from fazenda.models import (
    Animal, ContratoFazenda, ContratoFazendaModulo, Estoque, Fazenda, RepasseConfig, Servico,
)
from fazenda.models.planos import MODULOS_COMERCIAIS
from fazenda.rules import repasse as R
from fazenda.rules.parametros import fazenda_atual

HOJE = date.today()
CAT = "Detecção de cio de repasse"


# ── regra pura ───────────────────────────────────────────────────────────────
class TestRegraPura:
    def test_padrao_e_o_comportamento_legado(self):
        p = R.padrao()
        assert p["usar"] and p["dias_apos_servico"] == 14 and p["quem_entra"] == "todas" and p["mostrar_na_agenda"]
        assert p["configurado"] is False

    def test_datas_sem_repeticao_e_com_repeticao(self):
        d = date(2026, 10, 1)
        assert R.datas_checagem(d, {"dias_apos_servico": 14, "repetir": False}) == [date(2026, 10, 15)]
        cfg = {"dias_apos_servico": 14, "repetir": True, "repetir_cada_dias": 21, "repeticoes": 2}
        assert R.datas_checagem(d, cfg) == [date(2026, 10, 15), date(2026, 11, 5), date(2026, 11, 26)]

    def test_quem_entra(self):
        iatf = {"tipo_servico": "IA", "protocolo": "IATF 3 manejos"}
        ia = {"tipo_servico": "IA", "protocolo": None}
        monta = {"tipo_servico": "Monta natural"}
        assert R.servico_entra(iatf, "iatf") and not R.servico_entra(ia, "iatf") and not R.servico_entra(monta, "iatf")
        assert R.servico_entra(monta, "monta_natural") and not R.servico_entra(iatf, "monta_natural")
        assert all(R.servico_entra(s, "todas") for s in (iatf, ia, monta))

    def test_categoria_ignora_acento_e_caixa(self):
        assert R.categoria_e_repasse("detecçao de CIO de repasse")
        assert R.categoria_e_repasse("Deteccao de cio de repasse")
        assert not R.categoria_e_repasse("Medicamentos e produtos veterinários")

    def test_descricao_legada_e_com_produto(self):
        assert R.descricao_checagem({"dias_apos_servico": 14, "repetir_cada_dias": 21}, None, 0) == \
            "Aplicar Scratch (0,5) — detector de cio, 14 dias pós-IA"
        assert "Adesivo X" in R.descricao_checagem({"dias_apos_servico": 20, "repetir_cada_dias": 21}, "Adesivo X", 0)
        assert "2ª checagem" in R.descricao_checagem({"dias_apos_servico": 14, "repetir_cada_dias": 21}, None, 1)


# ── endpoints e motor ────────────────────────────────────────────────────────
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
        s.commit()

    def _sess():
        with Session(engine) as session:
            yield session

    import main
    from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita

    class _User:
        id = 1
        papel = "admin"
        ativo = True
        username = "teste"
        email = "t@example.com"
        permissoes = ""

    usuario = _User()
    estado = {"fazenda": 1}
    main.app.dependency_overrides[database.get_session] = _sess
    main.app.dependency_overrides[get_current_user] = lambda: usuario
    main.app.dependency_overrides[get_fazenda_atual_id] = lambda: estado["fazenda"]
    main.app.dependency_overrides[get_fazenda_id_escrita] = lambda: estado["fazenda"]
    with TestClient(main.app) as c:
        c.estado, c.usuario = estado, usuario
        yield c, engine
    main.app.dependency_overrides.clear()
    fazenda_atual.set(None)


def _adesivo_param(engine, ligado: bool) -> None:
    """Parâmetro antigo `usa_adesivo_deteccao_cio` (a chave mestra de quem ainda não salvou a configuração de repasse)."""
    from fazenda.models import ParametroFazenda

    with Session(engine) as s:
        s.add(ParametroFazenda(chave="usa_adesivo_deteccao_cio", fazenda_id=None, grupo="reinseminacao_cio",
                               label="Utiliza adesivos para detecção de cio de repasse?", valor="true" if ligado else "false", tipo="bool"))
        s.commit()


def _item(s: Session, nome: str, categoria: str | None = CAT, fazenda_id: int = 1, **kw) -> int:
    e = Estoque(nome=nome, categoria=categoria, fazenda_id=fazenda_id, quantidade=kw.pop("quantidade", 10), unidade="un", **kw)
    s.add(e)
    s.commit()
    s.refresh(e)
    return e.id


def _vaca_servico(s: Session, numero: str, dias_atras: int = 4, fazenda_id: int = 1, **kw) -> None:
    s.add(Animal(numero=numero, sexo="F", ativo=True, fazenda_id=fazenda_id, grupo_primario="03 Lote 03"))
    s.add(Servico(numero_matriz=numero, data_servico=HOJE - timedelta(days=dias_atras), ult_ocorrencia=1,
                  tipo_servico=kw.pop("tipo_servico", "IA"), fazenda_id=fazenda_id, **kw))
    s.commit()


def _descricoes_repasse(c) -> list[tuple[str, str]]:
    r = c.get("/agenda/", params={"data": HOJE.isoformat()})
    assert r.status_code == 200, r.text
    return [(e["data"], e["descricao"]) for e in r.json()["eventos"]
            if "detector de cio" in e["descricao"].lower() or "scratch" in e["descricao"].lower() or "repasse" in e["descricao"].lower()]


class TestEndpointsConfig:
    def test_sem_configuracao_e_sem_o_parametro_antigo_o_adesivo_fica_desligado(self, ctx):
        c, _ = ctx
        r = c.get("/agenda/repasse/config")
        assert r.status_code == 200
        b = r.json()
        assert b["configurado"] is False and b["usar"] is False and b["avisar_apos_dias"] is None
        assert b["estoque_ids"] == [] and b["produtos"] == []

    def test_sem_configuracao_com_o_parametro_antigo_ligado_vale_o_padrao_de_14_dias(self, ctx):
        c, engine = ctx
        _adesivo_param(engine, True)
        r = c.get("/agenda/repasse/config")
        assert r.status_code == 200
        b = r.json()
        assert b["configurado"] is False and b["usar"] is True and b["dias_apos_servico"] == 14 and b["avisar_apos_dias"] == 14
        assert b["categoria_produto"] == CAT and b["ciclo_sugerido"] == [18, 24]
        assert {o["valor"] for o in b["quem_entra_opcoes"]} == {"todas", "iatf", "monta_natural"}

    def test_get_nao_grava(self, ctx):
        c, engine = ctx
        c.get("/agenda/repasse/config")
        with Session(engine) as s:
            assert s.exec(select(RepasseConfig)).all() == []

    def test_salvar_e_ler_de_volta(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            pid = _item(s, "Adesivo Estrus")
        corpo = {"usar": True, "estoque_id": pid, "dias_apos_servico": 20, "repetir": True, "repetir_cada_dias": 21,
                 "repeticoes": 2, "mostrar_na_agenda": False, "quem_entra": "iatf"}
        r = c.put("/agenda/repasse/config", json=corpo)
        assert r.status_code == 200, r.text
        assert r.json()["avisos"] == []
        b = c.get("/agenda/repasse/config").json()
        assert b["configurado"] is True and b["dias_apos_servico"] == 20 and b["quem_entra"] == "iatf"
        assert b["mostrar_na_agenda"] is False and b["produto"]["nome"] == "Adesivo Estrus"
        # regravar atualiza a mesma linha (uma por fazenda)
        c.put("/agenda/repasse/config", json={**corpo, "dias_apos_servico": 22})
        with Session(engine) as s:
            linhas = s.exec(select(RepasseConfig)).all()
            assert len(linhas) == 1 and linhas[0].dias_apos_servico == 22

    def test_validacoes(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            errado = _item(s, "Ivermectina", categoria="Medicamentos e produtos veterinários")
            de_outra = _item(s, "Adesivo alheio", fazenda_id=2)
        for corpo, trecho in [
            ({"dias_apos_servico": 0}, "Avisar na agenda após"),
            ({"dias_apos_servico": 61}, "Avisar na agenda após"),
            ({"avisar_apos_dias": 0}, "Avisar na agenda após"),
            ({"avisar_apos_dias": 90}, "Avisar na agenda após"),
            ({"repetir_cada_dias": 3}, "Repetir a cada"),
            ({"repeticoes": 9}, "repetições"),
            ({"quem_entra": "vacas_bonitas"}, "quem entra"),
            ({"estoque_id": de_outra}, "não encontrado"),
            ({"estoque_ids": [de_outra]}, "não encontrado"),
            ({"estoque_id": 99999}, "não encontrado"),
        ]:
            r = c.put("/agenda/repasse/config", json=corpo)
            assert r.status_code == 422, (corpo, r.text)
            assert trecho.lower() in r.json()["detail"].lower(), (corpo, r.json())

    def test_aviso_fora_do_ciclo_sugerido_e_sem_produto_nao_e_mais_aviso(self, ctx):
        c, _ = ctx
        r = c.put("/agenda/repasse/config", json={"repetir": True, "repetir_cada_dias": 30})
        avisos = " ".join(r.json()["avisos"])
        assert "18 a 24" in avisos
        assert "Sem produto vinculado" not in avisos  # sem produto vinculado = escolha livre no estoque, por decisão

    def test_isolamento_por_fazenda(self, ctx):
        c, engine = ctx
        c.put("/agenda/repasse/config", json={"dias_apos_servico": 25})
        c.estado["fazenda"] = 2
        assert c.get("/agenda/repasse/config").json()["configurado"] is False
        c.put("/agenda/repasse/config", json={"dias_apos_servico": 18})
        c.estado["fazenda"] = 1
        assert c.get("/agenda/repasse/config").json()["dias_apos_servico"] == 25

    def test_sem_permissao_nao_configura(self, ctx):
        c, _ = ctx
        c.usuario.papel = "funcionario"
        c.usuario.permissoes = "producao"
        assert c.put("/agenda/repasse/config", json={}).status_code == 403
        assert c.post("/agenda/repasse/produtos/1/classificar").status_code == 403
        c.usuario.permissoes = "sanidade"
        assert c.put("/agenda/repasse/config", json={}).status_code == 200


class TestProdutos:
    def test_lista_so_da_categoria_e_separa_os_outros(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _item(s, "Adesivo A")
            _item(s, "Adesivo inativo", ativo=False)
            _item(s, "Ivermectina", categoria="Medicamentos e produtos veterinários")
            _item(s, "Adesivo de outra fazenda", fazenda_id=2)
        b = c.get("/agenda/repasse/produtos").json()
        assert [p["nome"] for p in b["produtos"]] == ["Adesivo A"]
        assert [p["nome"] for p in b["outros_itens"]] == ["Ivermectina"]

    def test_classificar_muda_so_a_categoria(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            pid = _item(s, "Detector X", categoria="Outros", estoque_minimo=5, quantidade=7)
        r = c.post(f"/agenda/repasse/produtos/{pid}/classificar")
        assert r.status_code == 200 and r.json()["categoria"] == CAT
        with Session(engine) as s:
            e = s.get(Estoque, pid)
            assert e.categoria == CAT and e.estoque_minimo == 5 and e.quantidade == 7

    def test_classificar_item_de_outra_fazenda_da_404(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            pid = _item(s, "Alheio", categoria="Outros", fazenda_id=2)
        assert c.post(f"/agenda/repasse/produtos/{pid}/classificar").status_code == 404
        with Session(engine) as s:
            assert s.get(Estoque, pid).categoria == "Outros"


class TestMotorDaAgenda:
    def test_sem_configuracao_e_sem_adesivo_nao_cai_tarefa_na_agenda(self, ctx):
        """O relato do produtor: o aviso de aplicar adesivo caía sozinho aos 14 dias mesmo sem a fazenda usar adesivo."""
        c, engine = ctx
        with Session(engine) as s:
            _vaca_servico(s, "101", dias_atras=4)
        assert _descricoes_repasse(c) == []

    def test_sem_configuracao_mantem_o_texto_e_os_14_dias(self, ctx):
        c, engine = ctx
        _adesivo_param(engine, True)
        with Session(engine) as s:
            _vaca_servico(s, "101", dias_atras=4)
        assert _descricoes_repasse(c) == [
            ((HOJE + timedelta(days=10)).isoformat(), "Aplicar Scratch (0,5) — detector de cio, 14 dias pós-IA"),
        ]

    def test_dias_configurados_e_produto_no_texto(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _vaca_servico(s, "101", dias_atras=4)
            pid = _item(s, "Adesivo Estrus")
        c.put("/agenda/repasse/config", json={"dias_apos_servico": 20, "estoque_id": pid})
        (data, desc), = _descricoes_repasse(c)
        assert data == (HOJE + timedelta(days=16)).isoformat()
        assert "Adesivo Estrus" in desc and "20 dias" in desc

    def test_repeticao_gera_checagens_seguintes(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _vaca_servico(s, "101", dias_atras=4)
        c.put("/agenda/repasse/config", json={"repetir": True, "repetir_cada_dias": 21, "repeticoes": 2})
        datas = [d for d, _ in _descricoes_repasse(c)]
        assert datas == [(HOJE + timedelta(days=n)).isoformat() for n in (10, 31, 52)]

    def test_desligado_ou_sem_aviso_na_agenda_nao_gera_tarefa(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _vaca_servico(s, "101", dias_atras=4)
        c.put("/agenda/repasse/config", json={"usar": False})
        assert _descricoes_repasse(c) == []
        c.put("/agenda/repasse/config", json={"usar": True, "mostrar_na_agenda": False})
        assert _descricoes_repasse(c) == []
        c.put("/agenda/repasse/config", json={"usar": True, "mostrar_na_agenda": True})
        assert len(_descricoes_repasse(c)) == 1

    def test_quem_entra_filtra_por_tipo_de_servico(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _vaca_servico(s, "101", dias_atras=4, tipo_servico="IA", protocolo="IATF 3 manejos")
            _vaca_servico(s, "102", dias_atras=4, tipo_servico="Monta natural")
        c.put("/agenda/repasse/config", json={"quem_entra": "monta_natural"})
        assert len(_descricoes_repasse(c)) == 1
        c.put("/agenda/repasse/config", json={"quem_entra": "iatf"})
        assert len(_descricoes_repasse(c)) == 1
        c.put("/agenda/repasse/config", json={"quem_entra": "todas"})
        assert len(_descricoes_repasse(c)) == 2

    def test_config_de_uma_fazenda_nao_muda_a_outra(self, ctx):
        c, engine = ctx
        _adesivo_param(engine, True)  # parâmetro global ligado: a fazenda 2, sem configuração salva, segue no padrão
        with Session(engine) as s:
            _vaca_servico(s, "101", dias_atras=4, fazenda_id=1)
            _vaca_servico(s, "901", dias_atras=4, fazenda_id=2)
        c.put("/agenda/repasse/config", json={"usar": False})           # fazenda 1 desliga
        c.estado["fazenda"] = 2
        assert len(_descricoes_repasse(c)) == 1                          # fazenda 2 segue no padrão de 14 dias


class TestParametrosDoAdesivo:
    """Parâmetros › Reinseminação e observação de cio: chave mestra, avisar após X dias (vazio = não avisar) e vários produtos."""

    def test_avisar_apos_dias_vazio_desliga_so_o_aviso_e_numero_liga(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            _vaca_servico(s, "101", dias_atras=4)
        r = c.put("/agenda/repasse/config", json={"usar": True, "avisar_apos_dias": None})
        assert r.status_code == 200 and r.json()["avisar_apos_dias"] is None and r.json()["usar"] is True
        assert _descricoes_repasse(c) == []
        r = c.put("/agenda/repasse/config", json={"usar": True, "avisar_apos_dias": 20})
        assert r.json()["avisar_apos_dias"] == 20 and r.json()["dias_apos_servico"] == 20 and r.json()["mostrar_na_agenda"] is True
        (data, _), = _descricoes_repasse(c)
        assert data == (HOJE + timedelta(days=16)).isoformat()

    def test_vazio_guarda_os_dias_anteriores_para_quando_voltar_a_avisar(self, ctx):
        c, _ = ctx
        c.put("/agenda/repasse/config", json={"usar": True, "avisar_apos_dias": 21})
        c.put("/agenda/repasse/config", json={"usar": True, "avisar_apos_dias": None})
        b = c.get("/agenda/repasse/config").json()
        assert b["avisar_apos_dias"] is None and b["dias_apos_servico"] == 21 and b["mostrar_na_agenda"] is False

    def test_varios_produtos_ida_e_volta_qualquer_categoria_e_texto_com_todos(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            a = _item(s, "Scratch Heatmark")
            b = _item(s, "Detector Kamar", categoria="Outros")  # sem a categoria de repasse: vale mesmo assim
            _vaca_servico(s, "101", dias_atras=4)
        r = c.put("/agenda/repasse/config", json={"usar": True, "estoque_ids": [a, b, a]})  # repetido é ignorado
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["estoque_ids"] == [a, b] and corpo["estoque_id"] == a
        assert [p["nome"] for p in corpo["produtos"]] == ["Scratch Heatmark", "Detector Kamar"]
        lido = c.get("/agenda/repasse/config").json()
        assert lido["estoque_ids"] == [a, b] and [p["nome"] for p in lido["produtos"]] == ["Scratch Heatmark", "Detector Kamar"]
        (_, desc), = _descricoes_repasse(c)
        assert "Scratch Heatmark ou Detector Kamar" in desc

    def test_produto_apagado_ou_inativo_sai_da_selecao_sem_travar_nada(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            a = _item(s, "Scratch Heatmark")
            b = _item(s, "Detector Kamar")
        c.put("/agenda/repasse/config", json={"usar": True, "estoque_ids": [a, b]})
        with Session(engine) as s:
            item = s.get(Estoque, b)
            item.ativo = False
            s.add(item)
            s.commit()
        lido = c.get("/agenda/repasse/config")
        assert lido.status_code == 200
        assert [p["nome"] for p in lido.json()["produtos"]] == ["Scratch Heatmark"]
        with Session(engine) as s:
            s.delete(s.get(Estoque, a))
            s.commit()
        assert c.get("/agenda/repasse/config").json()["produtos"] == []

    def test_corpo_antigo_com_um_produto_continua_valendo(self, ctx):
        c, engine = ctx
        with Session(engine) as s:
            pid = _item(s, "Adesivo Estrus")
        r = c.put("/agenda/repasse/config", json={"usar": True, "estoque_id": pid, "dias_apos_servico": 18})
        assert r.json()["estoque_ids"] == [pid] and r.json()["avisar_apos_dias"] == 18
        r = c.put("/agenda/repasse/config", json={"usar": True, "estoque_id": None, "estoque_ids": []})
        assert r.json()["estoque_ids"] == [] and r.json()["estoque_id"] is None

    def test_a_configuracao_salva_manda_na_chave_mestra_e_o_parametro_antigo_so_vale_sem_ela(self, ctx):
        from fazenda.rules.parametros import usa_adesivo_deteccao_cio

        c, engine = ctx
        assert usa_adesivo_deteccao_cio() is False
        _adesivo_param(engine, True)
        fazenda_atual.set(1)
        assert usa_adesivo_deteccao_cio() is True          # sem configuração: vale o parâmetro
        c.put("/agenda/repasse/config", json={"usar": False})
        assert usa_adesivo_deteccao_cio() is False         # configuração salva manda, mesmo com o parâmetro ligado
        c.put("/agenda/repasse/config", json={"usar": True})
        assert usa_adesivo_deteccao_cio() is True
        fazenda_atual.set(2)
        assert usa_adesivo_deteccao_cio() is True          # a fazenda 2 não salvou nada: segue o parâmetro

    def test_chave_mestra_desligada_esconde_a_lista_observacao_de_cio(self, ctx):
        from fazenda.rules.parametros import usa_adesivo_deteccao_cio

        c, engine = ctx
        c.put("/agenda/repasse/config", json={"usar": False})
        fazenda_atual.set(1)
        assert usa_adesivo_deteccao_cio() is False  # a lista só é montada quando isto é True (agenda_veterinario)
