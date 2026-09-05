"""
FURO DE MULTI-TENANT CORRIGIDO em `fazenda.rules.genetica`:
`calcular_grau_sangue_cria` (chamada por `registrar_parto`/`encerrar_gestacao`
para sugerir raça/grau de sangue da cria) resolvia o serviço de concepção
(`_servico_concepcao`) só por `numero_matriz`, sem filtrar fazenda_id — como
`animal.numero` deixou de ser único globalmente (migração c24befa94c1b),
podia puxar o touro/reprodutor de um Servico de OUTRA fazenda e calcular a
genética da cria com o pai errado.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, SQLModel, create_engine

from fazenda.models import Animal, GrauSangue, Servico
from fazenda.rules.genetica import calcular_grau_sangue_cria


def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return eng


def test_nao_usa_servico_de_outra_fazenda_para_calcular_genetica_da_cria():
    engine = _engine()
    with Session(engine) as s:
        # Mesma matriz "500" nas duas fazendas.
        mae_f1 = Animal(numero="500", fazenda_id=1, raca="Girolando", grau_sangue="1/2 Holandês x Gir")
        mae_f2 = Animal(numero="500", fazenda_id=2, raca="Girolando", grau_sangue="1/2 Holandês x Gir")
        s.add_all([mae_f1, mae_f2])
        s.add(GrauSangue(nome="1/2 Holandês x Gir", fracao_holandes=0.5, fazenda_id=1))
        s.add(GrauSangue(nome="PO Holandês", fracao_holandes=1.0, fazenda_id=1))
        s.add(GrauSangue(nome="1/2 Holandês x Gir", fracao_holandes=0.5, fazenda_id=2))
        s.add(GrauSangue(nome="PO Holandês", fracao_holandes=1.0, fazenda_id=2))
        # Serviço da FAZENDA 1: touro Holandês puro, ~280 dias antes do parto
        # que a fazenda 2 vai registrar (dentro da janela de gestação 260-295).
        s.add(Servico(
            numero_matriz="500", data_servico=date(2025, 3, 27), tipo="IA", tipo_servico="IA",
            reprodutor="Touro Holandês Puro", fazenda_id=1,
        ))
        # Fazenda 2 não tem NENHUM serviço para "500" — sem pai identificável,
        # o cálculo tem que cair no fallback (raça da mãe, sem grau de sangue).
        s.commit()

    with Session(engine) as s:
        from sqlmodel import select
        mae_f2_fresh = s.exec(select(Animal).where(Animal.fazenda_id == 2)).first()
        raca, grau = calcular_grau_sangue_cria(s, mae_f2_fresh, date(2026, 1, 1), fazenda_id=2)

    assert grau is None, (
        "sem serviço PRÓPRIO da fazenda 2 para a matriz '500', o cálculo não pode ter "
        "encontrado o touro Holandês da fazenda 1 e calculado um grau de sangue"
    )
    assert raca == "Girolando"  # fallback = raça da própria mãe
