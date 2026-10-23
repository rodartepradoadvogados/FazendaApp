"""
Sanitário v2 — motor contra o banco: estados, pré-parto previsto x real,
público por ID e histórico, chave única sem duplicata, leitura que não grava,
duas fazendas isoladas e simulação de outra data (riscos).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlmodel import select

from fazenda.models import (
    SanitarioCaixa, SanitarioLog, SanitarioNotaAgenda, SanitarioRegistro, SanitarioSituacao,
)
from fazenda.rules.sanitario import consulta
from fazenda.rules.sanitario.contexto import carregar_animais, carregar_caixas
from fazenda.rules.sanitario.motor import avaliar, motivo_inelegivel, recalcular, simular, situacao_atual
from tests.sanitario_cenario import (  # noqa: F401  (fixtures)
    F1, F2, HOJE, animal, caixa, categoria_id, def_b19, def_meses, def_pre_parto, engine, parto, servico, session,
)


def _sit(session, cx, a, ref=None):
    cxd = [c for c in carregar_caixas(session, cx.fazenda_id) if c.caixa_id == cx.id][0]
    ad = carregar_animais(session, cx.fazenda_id, animal_ids=[a.id], hoje=HOJE)[a.id]
    return situacao_atual(cxd, ad, ref or HOJE), cxd, ad


def _contar(session, modelo, **filtros):
    q = select(func.count()).select_from(modelo)
    for k, v in filtros.items():
        q = q.where(getattr(modelo, k) == v)
    return session.exec(q).one()


def _registrar(session, a, cx, ciclo, data=HOJE, dose=1, so_registro=False, estado="valido"):
    r = SanitarioRegistro(fazenda_id=a.fazenda_id, animal_id=a.id, caixa_id=cx.id, ciclo_chave=ciclo, dose_num=dose,
                          data=data, so_registro=so_registro, estado=estado)
    session.add(r)
    session.flush()
    return r


# ── estados ─────────────────────────────────────────────────────────────────
def test_b19_estados_por_idade_sexo_e_aplicacao(session):
    cx = caixa(session, def_b19())
    janela = animal(session, "2401", idade_dias=150)
    prevista = animal(session, "2409", idade_dias=70)
    macho = animal(session, "2413", sexo="M", idade_dias=150)
    passou = animal(session, "2412", idade_dias=259)
    assert _sit(session, cx, janela)[0].estado == "janela"
    assert _sit(session, cx, prevista)[0].estado == "prevista"
    s = _sit(session, cx, macho)[0]
    assert s.estado == "fora" and "Macho" in s.texto
    assert _sit(session, cx, passou)[0].estado == "perdida"  # ao fechar: perder
    _registrar(session, janela, cx, "U")
    assert _sit(session, cx, janela)[0].estado == "aplicada"


def test_ao_fechar_manter_e_descartar(session):
    a = animal(session, "2412", idade_dias=259)
    cm = caixa(session, def_b19(nome="B19 manter", ao_fechar="manter"))
    cd = caixa(session, def_b19(nome="B19 descartar", ao_fechar="descartar"))
    assert _sit(session, cm, a)[0].estado == "atrasada"
    assert _sit(session, cd, a)[0].estado == "descartada"


def test_periodo_manter_aberta_vira_atrasada_so_depois_de_ativada(session):
    a = animal(session, "0861", idade_dias=1500)
    antiga = caixa(session, def_meses("Lepto antiga", [[2], [8]]), ativada_em=date(2025, 1, 1))
    nova = caixa(session, def_meses("Lepto nova", [[2], [8]]), ativada_em=HOJE)
    assert _sit(session, antiga, a)[0].estado == "atrasada"   # setembro fechou sem receber
    assert _sit(session, nova, a)[0].estado == "prevista"     # ativada depois de setembro: só março


def test_aviso_antecedencia_do_periodo(session):
    a = animal(session, "0861", idade_dias=1500)
    cx = caixa(session, def_meses("Raiva", [[10]], aviso_antecedencia_dias=30), ativada_em=HOJE)
    assert _sit(session, cx, a)[0].estado == "aviso"  # data-base 15/11, aviso de 30 d


def test_categoria_por_id_e_historico_ja_nunca(session):
    b19 = caixa(session, def_b19())
    rb51 = caixa(session, dict(
        nome="RB51", tipo="vacina", pub_sexo="F", pub_hist_tipo="nunca", pub_hist_caixa_id=b19.id,
        categorias=[categoria_id(session, F1, "Novilha")], jan_usa_periodo=True, periodo_modo="continuo"))
    sem_b19 = animal(session, "3105", idade_dias=480)
    com_b19 = animal(session, "3101", idade_dias=470)
    bezerra = animal(session, "2401", idade_dias=150)
    # planilha importada ("só registro") também conta como histórico vacinal
    _registrar(session, com_b19, b19, "U", data=HOJE - timedelta(days=300), so_registro=True)
    assert _sit(session, rb51, sem_b19)[0].estado == "janela"
    s = _sit(session, rb51, com_b19)[0]
    assert s.estado == "fora" and "Já recebeu B19" in s.texto
    s = _sit(session, rb51, bezerra)[0]
    assert s.estado == "fora" and "Recria 1" in s.texto


def test_pre_parto_vai_do_previsto_menos_30_ate_o_parto_real(session):
    cx = caixa(session, def_pre_parto())
    vaca = animal(session, "0701", idade_dias=1700)
    sv = servico(session, vaca, HOJE - timedelta(days=270))  # parto previsto ~ HOJE+10 (Holandês 280)
    s, cxd, ad = _sit(session, cx, vaca)
    assert s.estado == "janela" and s.ciclo.chave == f"G:{sv.id}" and s.ciclo.aberta
    # parto previsto passou e ela não pariu: a janela continua aberta até o parto real
    depois = ad.gestacoes[-1].parto_previsto + timedelta(days=5)
    ad_depois = carregar_animais(session, F1, animal_ids=[vaca.id], hoje=depois)[vaca.id]
    s_tarde = situacao_atual(cxd, ad_depois, depois)
    assert s_tarde.estado == "janela"
    # pariu sem receber: a janela fecha no parto REAL e a vacina é perdida
    parto(session, vaca, HOJE + timedelta(days=2))
    s2, _cxd, _ad = _sit(session, cx, vaca, HOJE + timedelta(days=3))
    assert s2.ciclo.fim == HOJE + timedelta(days=1) and not s2.ciclo.aberta  # véspera do parto real
    assert s2.estado == "perdida"


def test_motivo_inelegivel_para_o_popup_de_consentimento(session):
    cx = caixa(session, def_b19())
    velha = animal(session, "2412", idade_dias=300)
    _s, cxd, ad = _sit(session, cx, velha)
    texto = motivo_inelegivel(cxd, ad, HOJE)
    assert texto and "fora da idade da B19" in texto


# ── chave única / sem duplicata ─────────────────────────────────────────────
def test_recalcular_duas_vezes_nao_duplica_e_remove_o_que_deixou_de_valer(session):
    cx = caixa(session, def_b19())
    a = animal(session, "2401", idade_dias=150)
    animal(session, "2402", idade_dias=100)
    c1 = recalcular(session, F1, hoje=HOJE)
    c2 = recalcular(session, F1, hoje=HOJE)
    assert c1["inseridas"] == 2 and c2["inseridas"] == 0 and c2["atualizadas"] == 0
    assert _contar(session, SanitarioSituacao, fazenda_id=F1) == 2
    _registrar(session, a, cx, "U")
    recalcular(session, F1, animal_ids=[a.id], hoje=HOJE)
    linhas = session.exec(select(SanitarioSituacao).where(SanitarioSituacao.animal_id == a.id)).all()
    assert [(r.ciclo_chave, r.estado) for r in linhas] == [("U", "aplicada")]


def test_registro_valido_tem_chave_unica_e_estorno_libera(session):
    import pytest
    from sqlalchemy.exc import IntegrityError

    cx = caixa(session, def_b19())
    a = animal(session, "2401", idade_dias=150)
    r = _registrar(session, a, cx, "U")
    _registrar(session, a, cx, "U", so_registro=True)  # "só registro" não conflita
    with pytest.raises(IntegrityError):
        with session.begin_nested():
            _registrar(session, a, cx, "U")
    r.estado = "estornado"
    session.add(r)
    session.flush()
    _registrar(session, a, cx, "U")  # estornado libera a chave
    assert _contar(session, SanitarioRegistro, animal_id=a.id, estado="valido") == 2


def test_venda_marca_saiu_sem_criar_linha(session):
    caixa(session, def_b19())
    a = animal(session, "2401", idade_dias=150)
    recalcular(session, F1, hoje=HOJE)
    a.ativo, a.motivo_baixa = False, "venda"
    session.add(a)
    session.flush()
    recalcular(session, F1, animal_ids=[a.id], hoje=HOJE)
    estados = session.exec(select(SanitarioSituacao.estado).where(SanitarioSituacao.animal_id == a.id)).all()
    assert estados == ["saiu"]


def test_caixa_inativada_perde_linhas_abertas(session):
    cx = caixa(session, def_b19())
    animal(session, "2401", idade_dias=150)
    recalcular(session, F1, hoje=HOJE)
    cx.estado = "inativa"
    session.add(cx)
    session.flush()
    recalcular(session, F1, hoje=HOJE)
    assert _contar(session, SanitarioSituacao, caixa_id=cx.id) == 0


# ── leitura não grava ───────────────────────────────────────────────────────
def test_leituras_e_simulacao_nao_gravam(session):
    cx = caixa(session, def_b19())
    a = animal(session, "2401", idade_dias=150)
    recalcular(session, F1, hoje=HOJE)
    session.commit()
    tabelas = (SanitarioSituacao, SanitarioRegistro, SanitarioNotaAgenda, SanitarioLog, SanitarioCaixa)
    antes = {m.__tablename__: _contar(session, m) for m in tabelas}
    consulta.resumo_30d(session, F1, hoje=HOJE)
    consulta.membros(session, F1, cx.id)
    consulta.situacao_do_animal(session, F1, a.id, hoje=HOJE)
    simular(session, F1, [cx.id], HOJE + timedelta(days=90), hoje=HOJE)
    assert not session.new and not session.dirty and not session.deleted
    session.rollback()
    depois = {m.__tablename__: _contar(session, m) for m in tabelas}
    assert antes == depois


def test_sentinela_modulos_de_leitura_nao_escrevem():
    """consulta.py (o que as telas/GETs vão usar) não chama add/delete/commit/flush."""
    import ast
    from pathlib import Path

    import fazenda.rules.sanitario.consulta as mod
    arvore = ast.parse(Path(mod.__file__).read_text())
    proibidos = {"add", "add_all", "delete", "commit", "flush", "merge"}
    chamadas = [n.func.attr for n in ast.walk(arvore)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in proibidos
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "session"]
    assert chamadas == []


# ── duas fazendas ───────────────────────────────────────────────────────────
def test_duas_fazendas_isoladas(session):
    cx1 = caixa(session, def_b19(), fazenda_id=F1)
    cx2 = caixa(session, def_b19(), fazenda_id=F2)  # mesmo nome, outra fazenda: permitido
    a1 = animal(session, "2401", idade_dias=150, fazenda_id=F1)
    a2 = animal(session, "2401", idade_dias=150, fazenda_id=F2)
    recalcular(session, F1, hoje=HOJE)
    linhas = session.exec(select(SanitarioSituacao)).all()
    assert {(r.fazenda_id, r.caixa_id, r.animal_id) for r in linhas} == {(F1, cx1.id, a1.id)}
    recalcular(session, F2, hoje=HOJE)
    linhas = session.exec(select(SanitarioSituacao).where(SanitarioSituacao.fazenda_id == F2)).all()
    assert {(r.caixa_id, r.animal_id) for r in linhas} == {(cx2.id, a2.id)}
    assert consulta.resumo_30d(session, F2, hoje=HOJE)["animais"] == 1
    assert [c.caixa_id for c in carregar_caixas(session, F2)] == [cx2.id]


# ── simulação de outra data ─────────────────────────────────────────────────
def test_simular_riscos_de_data_diferente(session):
    b19 = caixa(session, def_b19())
    pre = caixa(session, def_pre_parto())
    vaca = animal(session, "2208", idade_dias=735)
    servico(session, vaca, HOJE - timedelta(days=265))           # parto previsto ~ HOJE+15
    vai_passar = animal(session, "2410", idade_dias=230)         # passa de 240 d em 10 dias
    vai_entrar = animal(session, "2408", idade_dias=110)         # entra na janela em 10 dias
    nova = HOJE + timedelta(days=30)
    r = simular(session, F1, [b19.id, pre.id], nova, hoje=HOJE)
    kinds = {x["kind"]: x for x in r["riscos"]}
    assert "parto" in kinds and vaca.id in kinds["parto"]["animal_ids"]
    assert "terá parido antes de" in kinds["parto"]["texto"]
    assert "idade" in kinds and kinds["idade"]["animal_ids"] == [vai_passar.id]
    assert "fora da idade da B19" in kinds["idade"]["texto"]
    assert vai_entrar.id in {e["animal_id"] for e in r["entram"]}


def test_simular_mudou_de_categoria(session):
    novilha = categoria_id(session, F1, "Recria 1")
    cx = caixa(session, dict(nome="Vermífugo", tipo="vermifugo", categorias=[novilha], jan_usa_periodo=True,
                             periodo_modo="continuo"))
    a = animal(session, "2405", idade_dias=200)  # Recria 1 vai até 210 d
    r = simular(session, F1, [cx.id], HOJE + timedelta(days=30), hoje=HOJE)
    assert r["riscos"] and r["riscos"][0]["kind"] == "publico" and a.id in r["riscos"][0]["animal_ids"]
    assert "Recria 2" in r["riscos"][0]["texto"]


def test_avaliar_e_pura_sem_sessao():
    """avaliar() roda só com CaixaDef/AnimalCtx — sem banco."""
    from fazenda.rules.sanitario.tipos import AnimalCtx, CaixaDef
    cx = CaixaDef(caixa_id=1, versao_id=1, nome="B19", nome_curto="B19", pub_sexo="F", jan_usa_evento=True,
                  evento_tipo="idade", evento_de_dias=120, evento_ate_dias=240)
    a = AnimalCtx(id=1, numero="1", hoje=HOJE, sexo="F", nasc=HOJE - timedelta(days=130))
    assert avaliar(cx, a)[0].estado == "janela"
    assert datetime  # (import usado em outros testes)
