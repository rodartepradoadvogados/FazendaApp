"""Visita reprodutiva — UMA regra para a data da próxima visita, lida por todos.

Antes a data da próxima visita era só calculada (último serviço do rebanho + `intervalo_visita_reprodutiva`).
Agora o usuário também pode DEFINIR a data (parâmetro `proxima_visita_reprodutiva_data`, grupo "manejo" de
Configurações > Parâmetros — mesmo padrão do ajuste manual do BST). Quem define é a Agenda ("Definir nova data da
visita") e a Agenda Reprodutiva do Insights (nota "Cenário projetado"); quem lê é a Agenda (comunicado e item), a
projeção da Agenda Reprodutiva, as candidatas projetadas de IATF e a tela de Parâmetros.

Regra de prioridade (`proxima_visita`):
  1. data definida pelo usuário, enquanto ainda não passou (>= hoje);
  2. senão, último serviço do rebanho + intervalo (intervalo 0/vazio desliga o cálculo automático);
  3. senão, nenhuma visita.
Passada a data definida, ela deixa de valer sozinha e o cálculo automático retoma — o usuário define a próxima
quando quiser, sem precisar limpar nada.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlmodel import Session, select

CHAVE_DATA = "proxima_visita_reprodutiva_data"


def data_definida(hoje: date | None = None) -> date | None:
    """Data definida pelo usuário que ainda vale (>= hoje); None se não há ou já passou."""
    from fazenda.rules.parametros import get_param_date

    hoje = hoje or date.today()
    d = get_param_date(CHAVE_DATA, None)
    return d if d is not None and d >= hoje else None


def proxima_visita(
    ultimo_servico: date | None, intervalo: int, hoje: date, definida: date | None = None,
) -> tuple[date | None, str | None]:
    """(data, origem) da próxima visita reprodutiva; origem = "definida" | "calculada" | None."""
    if definida is not None and definida >= hoje:
        return definida, "definida"
    if ultimo_servico is not None and intervalo and intervalo > 0:
        return ultimo_servico + timedelta(days=intervalo), "calculada"
    return None, None


def gravar_data_definida(session: Session, fazenda_id: int | None, nova_data: date | None) -> None:
    """Grava (ou limpa, com None) a data definida na linha DA FAZENDA — clone-on-write do padrão global, como em
    `parametros.atualizar_parametro`: nunca altera o padrão visto pelas outras fazendas. Não comita."""
    from fazenda.models import ParametroFazenda

    linha = None
    if fazenda_id is not None:
        linha = session.exec(select(ParametroFazenda).where(
            ParametroFazenda.chave == CHAVE_DATA, ParametroFazenda.fazenda_id == fazenda_id)).first()
    if linha is None:
        base = session.exec(select(ParametroFazenda).where(
            ParametroFazenda.chave == CHAVE_DATA, ParametroFazenda.fazenda_id.is_(None))).first()
        if fazenda_id is None and base is not None:
            linha = base  # sem fazenda (ex.: Painel CowData fora de modo suporte): edita o padrão global, nunca duplica a linha
    if linha is None:
        linha = ParametroFazenda(
            chave=CHAVE_DATA, fazenda_id=fazenda_id, grupo=base.grupo if base else "manejo",
            label=base.label if base else "Data da próxima visita reprodutiva (definida por você)",
            valor="", tipo="date", unidade=None,
        )
    linha.valor = nova_data.isoformat() if nova_data else ""
    linha.atualizado_em = datetime.utcnow()
    session.add(linha)
