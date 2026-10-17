"""Visita reprodutiva — UMA regra para a data da próxima visita, lida por todos.

Antes a data da próxima visita era só calculada (último serviço do rebanho + `intervalo_visita_reprodutiva`).
Agora o usuário também pode DEFINIR a data (parâmetro `proxima_visita_reprodutiva_data`, grupo "manejo" de
Configurações > Parâmetros — mesmo padrão do ajuste manual do BST). Quem define é a Agenda ("Definir nova data da
visita") e a Agenda Reprodutiva do Insights (nota "Cenário projetado"); quem lê é a Agenda (comunicado e item), a
projeção da Agenda Reprodutiva, as candidatas projetadas de IATF e a tela de Parâmetros.

O usuário também pode informar a DATA DA ÚLTIMA VISITA (parâmetro `ultima_visita_reprodutiva_data`): ela é a âncora da
contagem dos dias entre visitas ("tive visita ontem" → próxima = ontem + intervalo de Parâmetros). Vale enquanto não
houver serviço lançado depois dela — um serviço mais novo prova que houve visita mais recente e volta a ser a âncora.

Regra de prioridade (`proxima_visita`):
  1. data definida pelo usuário, enquanto ainda não passou (>= hoje);
  2. senão, âncora + intervalo (intervalo 0/vazio desliga o cálculo automático), onde âncora = a mais recente entre a
     última visita informada e o último serviço do rebanho. Com a última visita informada como âncora, o ciclo é fixo
     (como o BST): se âncora + intervalo já passou, avança de intervalo em intervalo até a próxima data futura — assim
     o comunicado da véspera e do dia continua aparecendo mesmo que ninguém atualize a data;
  3. senão, nenhuma visita.
Passada a data definida, ela deixa de valer sozinha e o cálculo automático retoma — o usuário define a próxima
quando quiser, sem precisar limpar nada.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlmodel import Session, select

CHAVE_DATA = "proxima_visita_reprodutiva_data"
CHAVE_ULTIMA = "ultima_visita_reprodutiva_data"


def data_definida(hoje: date | None = None) -> date | None:
    """Data definida pelo usuário que ainda vale (>= hoje); None se não há ou já passou."""
    from fazenda.rules.parametros import get_param_date

    hoje = hoje or date.today()
    d = get_param_date(CHAVE_DATA, None)
    return d if d is not None and d >= hoje else None


def ultima_visita_informada(hoje: date | None = None) -> date | None:
    """Data da última visita informada pelo usuário; None se não há (ou se está no futuro — uma visita que ainda não
    aconteceu não ancora nada)."""
    from fazenda.rules.parametros import get_param_date

    hoje = hoje or date.today()
    d = get_param_date(CHAVE_ULTIMA, None)
    return d if d is not None and d <= hoje else None


def ultima_visita_vigente(ultimo_servico: date | None, ultima_informada: date | None) -> date | None:
    """Última visita que vale como âncora: a mais recente entre a informada e o último serviço do rebanho."""
    datas = [d for d in (ultimo_servico, ultima_informada) if d is not None]
    return max(datas) if datas else None


def proxima_visita(
    ultimo_servico: date | None, intervalo: int, hoje: date, definida: date | None = None,
    ultima_informada: date | None = None,
) -> tuple[date | None, str | None]:
    """(data, origem) da próxima visita reprodutiva; origem = "definida" | "calculada" | None."""
    if definida is not None and definida >= hoje:
        return definida, "definida"
    if not intervalo or intervalo <= 0:
        return None, None
    if ultima_informada is not None and (ultimo_servico is None or ultima_informada >= ultimo_servico):
        proxima = ultima_informada + timedelta(days=intervalo)
        if proxima < hoje:  # ciclo fixo: salta os ciclos já vencidos até o próximo que cai hoje ou no futuro
            ciclos_vencidos = -(-(hoje - proxima).days // intervalo)  # teto da divisão
            proxima += timedelta(days=ciclos_vencidos * intervalo)
        return proxima, "calculada"
    if ultimo_servico is not None:
        return ultimo_servico + timedelta(days=intervalo), "calculada"
    return None, None


def gravar_data_definida(session: Session, fazenda_id: int | None, nova_data: date | None, chave: str = CHAVE_DATA) -> None:
    """Grava (ou limpa, com None) a data definida (`chave`: próxima ou última visita) na linha DA FAZENDA — clone-on-write do padrão global, como em
    `parametros.atualizar_parametro`: nunca altera o padrão visto pelas outras fazendas. Não comita."""
    from fazenda.models import ParametroFazenda

    linha = None
    if fazenda_id is not None:
        linha = session.exec(select(ParametroFazenda).where(
            ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id == fazenda_id)).first()
    if linha is None:
        base = session.exec(select(ParametroFazenda).where(
            ParametroFazenda.chave == chave, ParametroFazenda.fazenda_id.is_(None))).first()
        if fazenda_id is None and base is not None:
            linha = base  # sem fazenda (ex.: Painel CowData fora de modo suporte): edita o padrão global, nunca duplica a linha
    if linha is None:
        linha = ParametroFazenda(
            chave=chave, fazenda_id=fazenda_id, grupo=base.grupo if base else "manejo",
            label=base.label if base else ("Data da última visita reprodutiva" if chave == CHAVE_ULTIMA
                                            else "Data da próxima visita reprodutiva (definida por você)"),
            valor="", tipo="date", unidade=None,
        )
    linha.valor = nova_data.isoformat() if nova_data else ""
    linha.atualizado_em = datetime.utcnow()
    session.add(linha)
