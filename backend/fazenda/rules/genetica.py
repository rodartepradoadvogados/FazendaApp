"""
Cálculo automático de grau de sangue da cria no parto — composição genética
na escala de absorção Holandês x Gir (Girolando), usada na pecuária leiteira
brasileira. Cada grau de sangue cadastrado (Configurações > Cadastro > Raças
e grau de sangue) tem uma `fracao_holandes` (0 = PO Gir, 1 = PO Holandês);
a fração da cria é a média entre mãe e pai, arredondada para o grau
cadastrado mais próximo.

Só calcula quando dá para resolver a fração de sangue de AMBOS os pais —
caso contrário, mantém o comportamento anterior (raça da cria = raça da mãe,
grau de sangue em branco), sempre editável manualmente na ficha do animal.
"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from fazenda.models import Animal, EstoqueSemen, GrauSangue, Servico, Touro

_JANELA_GESTACAO_DIAS_MIN = 260
_JANELA_GESTACAO_DIAS_MAX = 295


def _fracao_por_texto(texto: str | None) -> float | None:
    """Heurística de fallback quando não há grau de sangue cadastrado casando
    exatamente: raça/nome contendo "Holandês" (e não "Gir") -> puro Holandês;
    contendo "Gir" (e não "Holandês") -> puro Gir. Caso ambíguo/vazio, None."""
    if not texto:
        return None
    t = texto.strip().lower()
    tem_holandes = "holand" in t
    tem_gir = "gir" in t and "girolando" not in t
    if tem_holandes and not tem_gir:
        return 1.0
    if tem_gir and not tem_holandes:
        return 0.0
    return None


def _fracao_grau_sangue(session: Session, grau_sangue: str | None, raca: str | None) -> float | None:
    """Fração de sangue Holandês de um animal, priorizando o grau de sangue
    cadastrado (exato) e caindo para a heurística por texto da raça/grau."""
    if grau_sangue:
        cadastro = session.exec(select(GrauSangue).where(GrauSangue.nome == grau_sangue.strip())).first()
        if cadastro and cadastro.fracao_holandes is not None:
            return cadastro.fracao_holandes
    fracao = _fracao_por_texto(grau_sangue)
    if fracao is not None:
        return fracao
    return _fracao_por_texto(raca)


def _touro_pai(session: Session, reprodutor: str | None) -> Touro | None:
    """Casa o touro/reprodutor do serviço com o catálogo NAAB — pelo NAAB do
    estoque de sêmen (se cadastrado) ou, na falta, pelo nome do touro."""
    if not reprodutor:
        return None
    nome_norm = reprodutor.strip().lower()
    semen = session.exec(select(EstoqueSemen).where(EstoqueSemen.touro_nome == reprodutor.strip())).first()
    if semen and semen.naab:
        touro = session.exec(select(Touro).where(Touro.naab == semen.naab.strip().upper())).first()
        if touro:
            return touro
    return next((t for t in session.exec(select(Touro)).all() if (t.nome or "").strip().lower() == nome_norm), None)


def _servico_concepcao(
    session: Session, numero_matriz: str, data_parto: date, fazenda_id: int | None = None,
) -> Servico | None:
    """Serviço mais provável a ter gerado a gestação — o último serviço com
    reprodutor informado dentro da janela de gestação bovina (~260-295 dias
    antes do parto). Mesma janela usada na ficha do animal (fazenda.api.routers.animais)."""
    # FURO DE MULTI-TENANT CORRIGIDO: sem o filtro de fazenda_id, uma
    # colisão de numero_matriz com outra fazenda podia puxar o serviço/touro
    # ALHEIO e calcular a raça/grau de sangue da cria com o pai errado.
    query_servico_concepcao = select(Servico).where(Servico.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        query_servico_concepcao = query_servico_concepcao.where(Servico.fazenda_id == fazenda_id)
    servicos = session.exec(query_servico_concepcao.order_by(Servico.data_servico)).all()
    candidatos = [
        s for s in servicos
        if s.data_servico and s.reprodutor
        and _JANELA_GESTACAO_DIAS_MIN <= (data_parto - s.data_servico).days <= _JANELA_GESTACAO_DIAS_MAX
    ]
    return candidatos[-1] if candidatos else None


def calcular_grau_sangue_cria(
    session: Session, mae: Animal, data_parto: date, fazenda_id: int | None = None,
) -> tuple[str | None, str | None]:
    """Retorna (raca, grau_sangue) sugeridos para a cria, ou (mae.raca, None)
    quando não é possível calcular (falta grau de sangue/raça da mãe ou do
    pai identificável)."""
    frac_mae = _fracao_grau_sangue(session, mae.grau_sangue, mae.raca)
    if frac_mae is None:
        return mae.raca, None

    servico = _servico_concepcao(session, mae.numero, data_parto, fazenda_id)
    if not servico or not servico.reprodutor:
        return mae.raca, None

    touro = _touro_pai(session, servico.reprodutor)
    frac_pai = _fracao_por_texto(touro.raca if touro else None) or _fracao_por_texto(servico.reprodutor)
    if frac_pai is None:
        return mae.raca, None

    media = (frac_mae + frac_pai) / 2

    # Catálogo de GrauSangue também é escopado por fazenda (cadastrável, ver
    # fazenda/models/animais.py::GrauSangue) — sem o filtro, o nome do grau
    # mais próximo podia vir do cadastro de OUTRA fazenda.
    query_graus = select(GrauSangue)
    if fazenda_id is not None:
        query_graus = query_graus.where(GrauSangue.fazenda_id == fazenda_id)
    graus_calculaveis = [g for g in session.exec(query_graus).all() if g.fracao_holandes is not None]
    if not graus_calculaveis:
        return mae.raca, None
    mais_proximo = min(graus_calculaveis, key=lambda g: abs(g.fracao_holandes - media))

    if media >= 0.999:
        raca = "Holandês"
    elif media <= 0.001:
        raca = "Gir"
    else:
        raca = "Girolando"
    return raca, mais_proximo.nome
