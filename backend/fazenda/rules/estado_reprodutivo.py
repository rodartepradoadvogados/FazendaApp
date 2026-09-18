"""
Estado reprodutivo AO VIVO — fonte única de verdade para as listas de Rebanho
(app de campo e site).

## Por que este módulo existe

Até aqui, TODA lista de Rebanho (Gestantes, Inseminadas, PEV, Aptas,
Atrasadas) era filtrada por `Animal.sit_rep` — um TEXTO congelado, importado
do GERAL.csv do Ideagri. Consequência: a lista só mudava no próximo upload de
CSV, nunca ao lançar um parto/serviço/diagnóstico no próprio sistema. Isso
produziu erros de classificação reais e perigosos, ex.:

  - novilha que pariu continuava listada como "gestante" (o parto não voltava
    para a lista de PEV);
  - vaca que já passou do PEV continuava em "PEV";
  - novilha recém-inseminada aparecia em "atrasadas";
  - vaca em protocolo de IATF aparecia em "aptas".

Aqui a classificação é recalculada a partir dos REGISTROS (Parto, Servico,
ProtocoloIatfAplicacao) toda vez que a lista é pedida. `sit_rep` e `del_dias`
não são mais consultados para decidir categoria.

## Matriz de exclusão (a ordem É a regra)

Cada animal recebe UM e apenas um estado. A primeira regra que casar vence —
por isso a ordem abaixo importa mais que qualquer condição individual:

  1. GESTANTE     diagnóstico POSITIVO no serviço vigente, sem perda de
                  prenhez e sem parto posterior.
  2. INSEMINADA   tem serviço vigente aguardando diagnóstico. Exclui
                  ATRASADA por definição: quem foi inseminada não está
                  atrasada, só espera o dia do toque.
  3. EM_PROTOCOLO dentro da janela D0–D11 de IATF e ainda SEM serviço neste
                  ciclo. Exclui APTA: quem está em protocolo já está sendo
                  trabalhada, não é candidata a novo serviço.
  4. PEV          pariu há menos de `pev_dias`. Descanso obrigatório.
  5. APTA         passou do PEV (vaca), ou teve diagnóstico negativo/perda
                  sem serviço depois, ou é novilha que atingiu idade e peso
                  de aptidão. É a definição dada pelo produtor.
  6. ATRASADA     seria APTA, mas passou do prazo — subconjunto de "deveria
                  ter sido inseminada e não foi". Um prazo para a VACA: DEL
                  máximo para o 1º serviço (conta a partir do parto, o evento
                  que a habilitou). Dois prazos EM PARALELO para a NOVILHA
                  nulípara — o que vier primeiro marca ATRASADA: a idade
                  máxima para a 1ª cobertura (conta a partir do NASCIMENTO,
                  um teto populacional fixo) e os dias após aptidão (conta a
                  partir da data em que ELA ficou apta — idade E peso, ver
                  `data_em_que_ficou_apta` — o evento individual, análogo ao
                  parto da vaca). Sem histórico de pesagem que confirme o
                  peso mínimo, só o teto de idade se aplica.
  7. NAO_APTA     novilha que ainda não atingiu idade/peso.
  8. VAZIA        DECLARADO, MAS NUNCA PRODUZIDO hoje. O docstring dizia que
                  era o fallback de "sem dados suficientes para classificar";
                  o fallback real de `classificar_animal` é NAO_APTA, e não há
                  nenhum `return` de VAZIA na função. Para a vaca, "vazia" é
                  descrita por APTA ou ATRASADA conforme o DEL; para a
                  nulípara, por APTA/ATRASADA/NAO_APTA conforme idade e peso —
                  ou seja, o conceito está coberto, o rótulo é que sobrou.
                  A constante fica porque é lida em três lugares (ROTULOS
                  aqui, o mapa de rótulos do frontend e ESTADOS_APTOS do motor
                  de ciclos); removê-la é mudança de vocabulário em três
                  arquivos sem nenhum ganho de comportamento. Mas quem for
                  acrescentar um estado novo precisa saber: ESTADOS_APTOS tem
                  um membro morto, e devolver VAZIA daqui hoje seria devolver
                  um estado que nenhuma tela jamais exercitou.

"Serviço vigente" = último serviço com data POSTERIOR ao último parto. É esse
recorte que faz o parto zerar o ciclo — a correção central do bug da novilha
que pariu e continuava gestante.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fazenda.rules.gestation import dias_gestacao_da_raca

# Estados possíveis — mutuamente exclusivos (ver matriz no topo do módulo).
GESTANTE = "gestante"
INSEMINADA = "inseminada"
EM_PROTOCOLO = "em_protocolo"
PEV = "pev"
APTA = "apta"
ATRASADA = "atrasada"
NAO_APTA = "nao_apta"
VAZIA = "vazia"

ROTULOS = {
    GESTANTE: "Gestante",
    INSEMINADA: "Inseminada",
    EM_PROTOCOLO: "Em protocolo (IA atual)",
    PEV: "PEV",
    APTA: "Apta",
    ATRASADA: "Atrasada",
    NAO_APTA: "Não apta",
    VAZIA: "Vazia",
}

# Gestação média de bovino leiteiro — fallback de quando a raça do animal não
# é informada. Com a raça em mãos, use `dias_gestacao(raca)` (Holandês 280,
# Girolando 287, Gir/Zebu 295): fixar 280 para todo mundo previa o parto de
# um Gir 15 dias antes do real, adiantando secagem e pré-parto na mesma medida.
DIAS_GESTACAO = 280
# Janela do protocolo IATF: D0 (implante) até D11 (inseminação).
DIA_FINAL_PROTOCOLO = 11

_POSITIVO = "POSITIVO"
_NEGATIVO = "NEGATIVO"


def _d(valor: Any) -> date | None:
    """Aceita date ou 'AAAA-MM-DD' (os dicts vêm de model_dump em alguns
    chamadores) e devolve date."""
    if valor is None or isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except ValueError:
        return None


def _get(obj: Any, campo: str) -> Any:
    """Lê tanto de objeto SQLModel quanto de dict — os dois formatos circulam
    no projeto (routers passam models; regras já achatadas passam dicts)."""
    if isinstance(obj, dict):
        return obj.get(campo)
    return getattr(obj, campo, None)


def data_em_que_ficou_apta(
    *,
    data_nasc: date | None,
    idade_apta_dias: int | None,
    pesagens: list[tuple[date, float]],
    peso_apta_kg: float | None,
) -> date | None:
    """Data em que a novilha passou a satisfazer idade E peso de aptidão —
    o evento individual que ancora `dias_atraso_apos_aptidao_novilha`, do
    mesmo jeito que o parto ancora `meta_del_max_1o_servico` para a vaca.

    É o MAIOR dos dois marcos: a data em que completou a idade mínima, e a
    primeira pesagem (ordenada por data) que bateu o peso mínimo. Antes dos
    dois marcos ela não está apta; o mais tardio dos dois é quando passou a
    estar, de fato.

    Devolve `None` quando não dá para saber — nascimento ausente, ou nenhuma
    pesagem no histórico bateu o peso mínimo. `None` aqui não é "nunca vai
    ficar atrasada por este critério": é "não afirme nada", a mesma
    disciplina de `peso_kg` ausente em `classificar_animal` — o chamador cai
    de volta no teto de idade (`idade_atraso_dias`) como única rede de
    segurança para quem nunca foi pesada."""
    if data_nasc is None or idade_apta_dias is None or peso_apta_kg is None:
        return None
    data_idade_ok = data_nasc + timedelta(days=idade_apta_dias)

    data_peso_ok = None
    for d, peso in sorted(pesagens, key=lambda item: item[0]):
        if peso is not None and peso >= peso_apta_kg:
            data_peso_ok = d
            break
    if data_peso_ok is None:
        return None
    return max(data_idade_ok, data_peso_ok)


def classificar_animal(
    numero: str,
    *,
    hoje: date,
    partos: list[Any],
    servicos: list[Any],
    aplicacoes_iatf: list[Any],
    pev_dias: int,
    del_max_1o_servico: int | None,
    eh_vaca: bool,
    idade_dias: int | None = None,
    peso_kg: float | None = None,
    idade_apta_dias: int | None = None,
    idade_atraso_dias: int | None = None,
    peso_apta_kg: float | None = None,
    raca: str | None = None,
    dias_atraso_apos_aptidao: int | None = None,
    data_ficou_apta: date | None = None,
    data_inicio_lactacao: date | None = None,
) -> dict:
    """Estado reprodutivo de UM animal, recalculado dos registros.

    `partos`/`servicos`/`aplicacoes_iatf` são só os registros DESTE animal.
    Devolve o estado + os dados derivados que as telas mostram (dias de
    gestação, parto previsto, DEL, dados da inseminação), para a tela não ter
    que recalcular nada nem voltar ao banco.
    """
    datas_parto = sorted([d for d in (_d(_get(p, "data_parto")) for p in partos) if d])
    ultimo_parto = datas_parto[-1] if datas_parto else None
    # Lactação sem parto (indução, aborto com abertura): a data de início da
    # lactação é o "parto virtual" para efeito de DEL e PEV — a matriz entrou
    # em ordenha, produziu leite e merece os mesmos pev_dias de descanso.
    ancora = ultimo_parto or data_inicio_lactacao
    del_dias = (hoje - ancora).days if ancora else None

    # Só o que veio DEPOIS do último parto conta para o ciclo atual — é isso
    # que faz um parto lançado hoje derrubar a gestação anterior.
    vigentes = [
        s for s in servicos
        if (ds := _d(_get(s, "data_servico"))) is not None
        and ds <= hoje
        and (ancora is None or ds > ancora)
    ]
    vigentes.sort(key=lambda s: _d(_get(s, "data_servico")))
    ultimo_servico = vigentes[-1] if vigentes else None

    base = {
        "numero": numero,
        "del_dias": del_dias,
        "data_ultimo_parto": ultimo_parto.isoformat() if ultimo_parto else None,
        "dias_gestacao": None,
        "parto_previsto": None,
        "data_servico": None,
        "tipo_servico": None,
        "protocolo": None,
        "dias_desde_servico": None,
    }

    if ultimo_servico is not None:
        ds = _d(_get(ultimo_servico, "data_servico"))
        base["data_servico"] = ds.isoformat() if ds else None
        base["tipo_servico"] = _get(ultimo_servico, "tipo_servico")
        base["protocolo"] = _get(ultimo_servico, "protocolo")
        base["dias_desde_servico"] = (hoje - ds).days if ds else None

        diagnostico = (_get(ultimo_servico, "diagnostico") or "").strip().upper()
        perdeu = _d(_get(ultimo_servico, "data_perda_prenhez")) is not None

        # 1. GESTANTE — prenhez confirmada e ainda de pé.
        if diagnostico == _POSITIVO and not perdeu:
            base["dias_gestacao"] = (hoje - ds).days if ds else None
            base["parto_previsto"] = (
                (ds + timedelta(days=dias_gestacao_da_raca(raca, DIAS_GESTACAO))).isoformat() if ds else None
            )
            return {**base, "estado": GESTANTE}

        # 2. INSEMINADA — serviço feito, resultado ainda em aberto. Vence
        #    ATRASADA: não há o que fazer com ela além de esperar o toque.
        if diagnostico not in (_POSITIVO, _NEGATIVO) and not perdeu:
            return {**base, "estado": INSEMINADA}

    # 3. EM_PROTOCOLO — dentro de D0–D11 e sem serviço neste ciclo.
    d0 = _d0_protocolo_ativo(aplicacoes_iatf, hoje)
    if d0 is not None:
        servico_no_ciclo = any(
            (ds := _d(_get(s, "data_servico"))) is not None and ds >= d0 for s in vigentes
        )
        if not servico_no_ciclo:
            return {
                **base,
                "estado": EM_PROTOCOLO,
                "protocolo_d0": d0.isoformat(),
                "protocolo_dia_atual": (hoje - d0).days,
            }

    # 4. PEV — descanso pós-parto obrigatório.
    if del_dias is not None and del_dias < pev_dias:
        return {**base, "estado": PEV}

    # 5/6. APTA x ATRASADA (vaca) — passou do PEV e está livre para servir.
    if eh_vaca or ultimo_parto is not None:
        if del_max_1o_servico is not None and del_dias is not None and del_dias > del_max_1o_servico:
            return {**base, "estado": ATRASADA}
        return {**base, "estado": APTA}

    # 7. Novilha nulípara: aptidão por idade E peso — mas peso AUSENTE não
    # desqualifica.
    #
    # Por quê: `peso_kg` vem exclusivamente da tabela PesagemCorporal, e nenhum
    # importador a escreve — só lançamento manual. Com a regra estrita, a
    # fazenda que não pesa tinha TODA novilha nulípara em NAO_APTA todos os
    # dias, o que a tira do BR ELIG de todo ciclo e faz as três taxas do painel
    # voltarem None. Numa fazenda de recria pesada isso apagava a maior parte
    # do rebanho da medição: 74 novilhas contra 37 vacas, com 59 prenhezes
    # invisíveis. Pior, "Todas" virava cópia de "Vacas" (é derivado por soma) e
    # passava por número do rebanho inteiro.
    #
    # A distinção que o código faz agora: peso LANÇADO abaixo do mínimo
    # desqualifica (o dado existe e diz que ela não está pronta); peso NUNCA
    # LANÇADO não afirma nada, e a idade decide sozinha. Quem pesa continua com
    # o critério completo. `aptidao_por_idade` marca o caso para a tela poder
    # avisar que aquela classificação foi feita sem pesagem.
    #
    # A guarda final continua: sem data de nascimento E sem peso não há dado
    # nenhum, e aí NAO_APTA é a resposta honesta.
    tem_idade = idade_dias is not None
    tem_peso = peso_kg is not None
    atingiu_idade = idade_apta_dias is None or (tem_idade and idade_dias >= idade_apta_dias)
    atingiu_peso = peso_apta_kg is None or not tem_peso or peso_kg >= peso_apta_kg
    if atingiu_idade and atingiu_peso and (tem_idade or tem_peso):
        # ATRASADA para nulípara — o análogo exato do teste da vaca logo acima.
        # A vaca fica atrasada quando passa N dias do evento que a habilitou (o
        # parto); a novilha, quando passa da idade-teto para a 1ª cobertura.
        #
        # Sem isto, ATRASADA era sintaticamente inalcançável para quem nunca
        # pariu (o único `return ATRASADA` está dentro do ramo
        # `eh_vaca or ultimo_parto is not None`), e o sistema perdia uma
        # informação que o GERAL.csv do Ideagri já entregava: nesta fazenda,
        # 11 das 74 novilhas são "Novilha vazia em atraso" — e não existe uma
        # única "Novilha vazia apta", porque lá o teto coincide com o piso.
        #
        # Note que isto só SUBDIVIDE o balde das aptas: ATRASADA já está em
        # ESTADOS_APTOS e em ESTADOS_CANDIDATA, então nenhum animal entra ou
        # sai de conjunto nenhum, e nenhuma taxa muda de valor.
        atrasada_por_idade = idade_atraso_dias is not None and tem_idade and idade_dias > idade_atraso_dias
        # Segundo gatilho, em paralelo (decisão do usuário: o que vier
        # primeiro marca ATRASADA — o teto de idade continua valendo como
        # rede de segurança para quem nunca foi pesada, já que sem pesagem
        # `data_ficou_apta` vem None e este segundo gatilho não dispara).
        atrasada_por_aptidao = (
            data_ficou_apta is not None
            and dias_atraso_apos_aptidao is not None
            and (hoje - data_ficou_apta).days > dias_atraso_apos_aptidao
        )
        if atrasada_por_idade or atrasada_por_aptidao:
            return {**base, "estado": ATRASADA, "aptidao_por_idade": not tem_peso}
        return {**base, "estado": APTA, "aptidao_por_idade": not tem_peso}
    return {**base, "estado": NAO_APTA, "aptidao_por_idade": False}


def _d0_protocolo_ativo(aplicacoes_iatf: list[Any], hoje: date) -> date | None:
    """D0 do protocolo IATF em andamento (janela D0..D11 contendo hoje), ou
    None. Agrupa por lançamento: as 4 linhas D0/D7/D9/D11 são UM protocolo,
    não quatro (ver também a ficha do animal, que contava 4 IATFs)."""
    por_lancamento: dict[Any, list[Any]] = {}
    for ap in aplicacoes_iatf:
        por_lancamento.setdefault(_get(ap, "lancamento_id"), []).append(ap)

    d0_ativo: date | None = None
    for aplicacoes in por_lancamento.values():
        datas_d0 = [
            d for ap in aplicacoes
            if _get(ap, "dia") == 0 and (d := _d(_get(ap, "data_prevista"))) is not None
        ]
        if not datas_d0:
            continue
        d0 = min(datas_d0)
        if d0 <= hoje <= d0 + timedelta(days=DIA_FINAL_PROTOCOLO):
            # Mais de um protocolo aberto (não deveria) → vale o mais recente.
            if d0_ativo is None or d0 > d0_ativo:
                d0_ativo = d0
    return d0_ativo


def descrever_servico(servico: Any) -> str:
    """Texto curto do tipo de serviço para as listas: distingue monta natural
    de IA e, sendo IA, cio natural de IATF (pedido do produtor na lista de
    Inseminadas)."""
    tipo = (_get(servico, "tipo_servico") or "").strip()
    protocolo = (_get(servico, "protocolo") or "").strip()
    tipo_l = tipo.lower()
    if "monta" in tipo_l or "natural" in tipo_l and "cio" not in tipo_l:
        return "Monta natural"
    if protocolo and protocolo.lower() not in ("cio natural", "cio", "-", "—"):
        return f"IA — IATF ({protocolo})"
    return "IA — cio natural"


def estados_ao_vivo(
    animais: list[Any],
    *,
    hoje: date,
    partos: list[Any],
    servicos: list[Any],
    aplicacoes_iatf: list[Any],
    pev_dias: int,
    del_max_1o_servico: int | None,
    peso_por_animal: dict[str, float] | None = None,
    idade_apta_dias: int | None = None,
    idade_atraso_dias: int | None = None,
    peso_apta_kg: float | None = None,
    dias_atraso_apos_aptidao: int | None = None,
    datas_ficou_apta_por_animal: dict[str, date] | None = None,
    inicio_lactacao_por_animal: dict[str, date] | None = None,
) -> dict[str, dict]:
    """`classificar_animal` em lote: devolve {numero -> dict completo}.

    Existe porque três lugares (Agenda, candidatas a IATF, protocolos ativos)
    montavam o mesmo agrupamento na mão e depois decidiam por `sit_rep`.

    Devolve o dict INTEIRO de `classificar_animal`, não só o estado — quem
    chama precisa de `del_dias` e `data_servico` junto. (`indicadores.py`
    tem uma variante que guarda só a string; esta é a versão rica.)

    `eh_vaca` sai de ter parto registrado, de "vaca" na categoria, OU de ter
    lactação aberta por indução/aborto (`inicio_lactacao_por_animal`) — mesma
    convenção de `programa_reprodutivo.montar_perfil`.

    ATENÇÃO: `classificar_animal` NÃO consulta `a_descartar` nem `data_baixa`.
    Quem precisa da regra R1 do programa reprodutivo tem que aplicá-la por
    cima — ou usar `programa_reprodutivo.estado_no_dia`, que já faz isso.
    """
    peso_por_animal = peso_por_animal or {}
    datas_ficou_apta_por_animal = datas_ficou_apta_por_animal or {}
    inicio_lactacao_por_animal = inicio_lactacao_por_animal or {}

    servicos_por: dict[str, list] = {}
    for s in servicos:
        servicos_por.setdefault(_get(s, "numero_matriz"), []).append(s)
    partos_por: dict[str, list] = {}
    for p in partos:
        partos_por.setdefault(_get(p, "numero_matriz"), []).append(p)
    iatf_por: dict[str, list] = {}
    for ap in aplicacoes_iatf:
        iatf_por.setdefault(_get(ap, "numero_matriz"), []).append(ap)

    resultado: dict[str, dict] = {}
    for a in animais:
        numero = _get(a, "numero")
        if not numero:
            continue
        partos_do_animal = partos_por.get(numero, [])
        categoria_txt = (
            _get(a, "categoria_abrev") or _get(a, "categoria_completa") or ""
        ).lower()
        nasc = _d(_get(a, "data_nasc"))
        resultado[numero] = classificar_animal(
            numero,
            hoje=hoje,
            partos=partos_do_animal,
            servicos=servicos_por.get(numero, []),
            aplicacoes_iatf=iatf_por.get(numero, []),
            pev_dias=pev_dias,
            del_max_1o_servico=del_max_1o_servico,
            eh_vaca=bool(partos_do_animal) or "vaca" in categoria_txt or numero in inicio_lactacao_por_animal,
            idade_dias=(hoje - nasc).days if nasc else None,
            peso_kg=peso_por_animal.get(numero) or _get(a, "peso_kg"),
            idade_apta_dias=idade_apta_dias,
            idade_atraso_dias=idade_atraso_dias,
            peso_apta_kg=peso_apta_kg,
            raca=_get(a, "raca"),
            dias_atraso_apos_aptidao=dias_atraso_apos_aptidao,
            data_ficou_apta=datas_ficou_apta_por_animal.get(numero),
            data_inicio_lactacao=inicio_lactacao_por_animal.get(numero),
        )
    return resultado
