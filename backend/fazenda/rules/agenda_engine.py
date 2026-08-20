"""
Motor da Agenda — orquestra todas as regras e produz a lista de eventos do dia.

AgendaEngine.calcular(data_referencia) → AgendaResult com:
  - candidatas_iatf: lista com doses calculadas
  - checagem_hormonios: estoque × necessidade
  - bst_elegiveis / bst_excluidos
  - contas_a_pagar: próximos 10 dias
  - eventos: lista cronológica de todos os eventos
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from fazenda.api.routers.animais import _del_dias_ao_vivo
from fazenda.rules.bst import ResultadoBST, avaliar_bst
from fazenda.rules.dry_off import calcular_secagem
from fazenda.rules.gestation import calcular_parto_provavel
from fazenda.rules.iatf import (
    CandidataIATF,
    NecessidadeHormonios,
    calcular_necessidade_hormonios,
    selecionar_candidatas_iatf,
)
from fazenda.rules.parametros import (
    dias_contas_a_pagar_agenda as _dias_contas_a_pagar_padrao,
    dias_reinseminacao_referencia as _dias_reinseminacao_referencia,
    get_param,
    gestacao_dias_referencia,
    idade_apta_min_meses as _idade_apta_min_meses,
    idade_max_1a_cobertura_meses as _idade_max_1a_cobertura_meses,
    intervalo_bst as _intervalo_bst_padrao,
    intervalo_visita_reprodutiva as _intervalo_visita_reprodutiva_padrao,
    periodo_seco_dias,
    peso_apta_min as _peso_apta_min,
    pev_dias as _pev_dias,
    pre_parto_max,
)
from fazenda.rules.estado_reprodutivo import (
    GESTANTE as _E_GESTANTE,
    INSEMINADA as _E_INSEMINADA,
    estados_ao_vivo,
)
from fazenda.rules.perda_prenhez import retoque_esta_resolvido
from fazenda.rules.scratch_pev import calcular_pev, calcular_scratch


def _del_projetado_bst(del_atual: int | None, proxima_visita_bst: date | None, hoje: date) -> int | None:
    """DEL que o animal terá na data da PRÓXIMA aplicação de BST agendada
    (`proxima_visita_bst`) — mesma conta usada para 'DEL projetado' das
    candidatas IATF (ver `del_dias_projetado` em
    `api/routers/reproducao.py::candidatas_iatf_projetadas`): DEL de hoje +
    dias até a data de referência futura. None quando falta um dos dois dados
    (sem último parto → sem `del_atual`; sem aplicação de BST agendada ainda)."""
    if del_atual is None or proxima_visita_bst is None:
        return None
    return del_atual + (proxima_visita_bst - hoje).days


# Com quanta antecedência o descarte previsto entra na Agenda. Não reaproveita
# `dias_contas_a_pagar` (padrão 10) de propósito: aquele prazo é de fluxo de
# caixa, e descarte se organiza com semanas — comprador, transporte, lote de
# venda. Trinta dias dá tempo de arranjar isso sem encher a agenda de hoje com
# coisa de dois meses adiante.
DIAS_HORIZONTE_DESCARTE = 30


@dataclass
class AgendaItem:
    data: date
    categoria: str   # Reprodutivo / Sanidade / Produção / Gestão/Financeiro / Atividades
    descricao: str
    numero_animal: str | None = None
    observacao: str | None = None
    fonte: str = "auto"  # "auto" ou "manual"
    ref: str | None = None  # referência p/ agrupar (ex.: nº do lançamento financeiro)
    lote: str | None = None  # CSV de códigos de lote, quando o evento manual é vinculado a lote(s)
    tipo_evento: str | None = None  # Compra, Venda, Serviço, Outro (só em eventos manuais)
    apenas_admin: bool = False  # evento visível somente para o administrador
    link: str | None = None  # rota interna de instruções/ação

    @property
    def chave(self) -> str:
        """Hash estável do evento — identidade usada para marcar 'realizado'."""
        bruto = f"{self.data.isoformat()}|{self.categoria}|{self.descricao}|{self.numero_animal or ''}"
        return hashlib.sha1(bruto.encode()).hexdigest()[:16]

    @property
    def cor(self) -> str:
        cores = {
            "Reprodutivo": "#D4EDDA",
            "Sanidade": "#FFF3CD",
            "Produção": "#D1ECF1",
            "Gestão/Financeiro": "#F8D7DA",
            "Atividades": "#E2E3E5",
        }
        return cores.get(self.categoria, "#FFFFFF")


@dataclass
class CheckHormonio:
    nome: str
    estoque_atual: float
    necessidade: float
    unidade: str
    suficiente: bool
    falta: float


@dataclass
class AgendaResult:
    data_referencia: date
    candidatas_iatf: list[CandidataIATF] = field(default_factory=list)
    necessidade_iatf: NecessidadeHormonios | None = None
    hormonios_check: list[CheckHormonio] = field(default_factory=list)
    bst_elegiveis: list[ResultadoBST] = field(default_factory=list)
    bst_excluidos: list[ResultadoBST] = field(default_factory=list)
    # Excluídas manualmente (Animal.excluir_bst) — não contam como aptas nem
    # como "excluídas por critério automático"; ficam à parte para reanálise
    # na próxima aplicação (indicador amarelo no front).
    bst_reanalise: list[ResultadoBST] = field(default_factory=list)
    contas_a_pagar: list[dict] = field(default_factory=list)
    eventos: list[AgendaItem] = field(default_factory=list)
    # Próxima visita reprodutiva/BST — ancorada no serviço mais recente do
    # rebanho (não por animal): último serviço em 03/07 -> visita em 24/07 (21 dias).
    proxima_visita_iatf: date | None = None
    proxima_visita_bst: date | None = None


class AgendaEngine:
    """
    Motor de cálculo da agenda preditiva.
    Recebe os dados do banco (já carregados) e aplica todas as regras da Seção 5.
    """

    def calcular(
        self,
        data_referencia: date,
        animais: list[dict],
        servicos: list[dict],
        partos: list[dict],
        estoque: list[dict],
        contas: list[dict],
        eventos_manuais: list[dict],
        dias_contas_a_pagar: int | None = None,
        proxima_visita_bst_real: date | None = None,
        lotes: list[dict] | None = None,
        secagens: list[dict] | None = None,
        pedidos_documentos_vencendo: list[dict] | None = None,
        pessoas_documentos_vencendo: list[dict] | None = None,
        inducoes_cio: list[dict] | None = None,
        # Entram para o estado reprodutivo AO VIVO decidir candidatas a IATF e
        # "PEV encerra" — antes os dois liam `sit_rep`, o texto congelado do
        # GERAL.csv. Sem `aplicacoes_iatf` o estado EM_PROTOCOLO nunca sai e a
        # vaca com D0 implantado hoje volta a ser oferecida; sem
        # `peso_por_animal` a novilha nulípara nunca é apta por peso. Ambos com
        # default vazio para não quebrar chamador nenhum.
        aplicacoes_iatf: list[dict] | None = None,
        peso_por_animal: dict[str, float] | None = None,
        # Histórico COMPLETO de serviços, só para a classificação ao vivo.
        # `servicos` continua sendo o recorte `ult_ocorrencia == 1`, porque o
        # alerta de retoque varre essa lista e dispararia para serviços antigos
        # se ela virasse o histórico. `classificar_animal` faz o próprio
        # recorte "posterior ao último parto"; com só o registro marcado, o
        # vigente correto pode ficar de fora quando a marcação está velha.
        servicos_historico: list[dict] | None = None,
    ) -> AgendaResult:
        """
        Calcula toda a agenda para uma data de referência.

        Args:
            data_referencia: Data de referência (geralmente hoje).
            animais: Lista de dicts com campos do modelo Animal.
            servicos: Lista de dicts com campos do modelo Servico (ÚLT_OCORR filtrado).
            partos: Lista de dicts com campos do modelo Parto.
            estoque: Lista de dicts com campos do modelo Estoque.
            contas: Lista de dicts com campos do modelo ContaGerencial.
            eventos_manuais: Lista de dicts com campos do modelo AgendaManual.
            proxima_visita_bst_real: Data da próxima aplicação de BST calculada
                a partir da ÚLTIMA APLICAÇÃO REAL lançada (Sanidade), já com o
                ciclo de 12 em 12 dias avançado até cair no futuro. Quando
                informada, substitui a estimativa por analogia ao serviço
                reprodutivo — o motor usa essa data para projetar o DEL de
                cada animal na próxima aplicação (bst_elegiveis/nunca aplicadas).
            secagens: Lista de dicts com campos do modelo Secagem — usada para
                calcular o DEL de cada animal AO VIVO (ver `_del_dias_ao_vivo`),
                em vez do `Animal.del_dias` congelado no último GERAL.csv.
            pedidos_documentos_vencendo: Anexos de Pedido (orçamento/ordem de
                serviço) com `data_validade`, já filtrados em agenda.py para
                pedidos "aberto"/"parcialmente_atendido" — dispara alerta 2
                dias antes do vencimento (ver PedidoAnexo/PUT /pedidos/{id}/anexos).
            pessoas_documentos_vencendo: Anexos de Pessoa da categoria
                "Contrato de trabalho por prazo determinado" com
                `data_validade`, já filtrados em agenda.py para pessoa ativa —
                dispara alerta 15 dias antes do vencimento (mais antecedência
                que Pedido: decidir renovar/encerrar um vínculo de trabalho
                precisa de mais prazo do que aprovar um orçamento — ver
                PessoaAnexo/POST /cadastro/pessoas/{id}/anexos).
            inducoes_cio: Aplicações de indução de cio (Sanidade com
                atividade=ATIVIDADE_INDUCAO_CIO) dos últimos dias — dispara
                "observar cio" na janela de 2 a 5 dias após a aplicação,
                enquanto o cio ainda não foi aproveitado (ver reproducao.py).

        Returns:
            AgendaResult com todos os blocos da agenda calculados.
        """
        result = AgendaResult(data_referencia=data_referencia)
        eventos: list[AgendaItem] = []
        dias_contas_a_pagar = dias_contas_a_pagar if dias_contas_a_pagar is not None else _dias_contas_a_pagar_padrao()
        intervalo_visita_reprodutiva = _intervalo_visita_reprodutiva_padrao()
        intervalo_bst = _intervalo_bst_padrao()
        dias_reinseminacao = _dias_reinseminacao_referencia()

        # Grupos (Lote.codigo + " - " + Lote.nome, mesmo formato de
        # Animal.grupo_primario) cujo cadastro já marca `pre_parto=True` —
        # animal cujo grupo atual já é um desses não recebe o alerta "entrando
        # no pré-parto" de novo (já foi movido manualmente/pela sugestão de
        # movimentação; ver lote_criterios.py).
        grupos_ja_pre_parto = {
            f"{l['codigo']} - {l['nome']}" for l in (lotes or []) if l.get("pre_parto")
        }

        # Índices auxiliares
        servico_por_animal: dict[str, dict] = {
            s["numero_matriz"]: s for s in servicos if s.get("ult_ocorrencia") == 1
        }
        parto_por_animal: dict[str, dict] = {}
        partos_por_animal: dict[str, list[dict]] = {}
        for p in sorted(partos, key=lambda x: x.get("ordem_parto") or 0, reverse=True):
            n = p["numero_matriz"]
            if n not in parto_por_animal:
                parto_por_animal[n] = p
            partos_por_animal.setdefault(n, []).append(p)

        # Secagem mais recente por animal — junto com o parto mais recente
        # acima, alimenta o DEL AO VIVO (ver _del_dias_ao_vivo, importado do
        # topo do arquivo) usado logo abaixo no loop por animal.
        ult_secagem_por_animal: dict[str, date] = {}
        ult_secagem_rotina_por_animal: dict[str, date] = {}
        for s in secagens or []:
            n = s.get("numero_matriz")
            d = s.get("data_secagem")
            if n and d and (n not in ult_secagem_por_animal or d > ult_secagem_por_animal[n]):
                ult_secagem_por_animal[n] = d
            if n and d and s.get("motivo") == "rotina" and (n not in ult_secagem_rotina_por_animal or d > ult_secagem_rotina_por_animal[n]):
                ult_secagem_rotina_por_animal[n] = d

        # ── ESTADO REPRODUTIVO AO VIVO
        # Recalculado dos registros, é o que decide as candidatas a IATF e o
        # aviso "PEV encerra" mais abaixo. Antes os dois liam `Animal.sit_rep`,
        # congelado no último GERAL.csv: vaca que engravidasse pelo app seguia
        # sendo oferecida para protocolo até o próximo upload.
        no_programa = [
            a for a in animais
            if a.get("ativo", True)
            and not a.get("a_descartar")
            and not (a.get("data_baixa") and a["data_baixa"] <= data_referencia)
        ]
        estados_vivos = estados_ao_vivo(
            no_programa,
            hoje=data_referencia,
            partos=partos,
            servicos=servicos_historico if servicos_historico is not None else servicos,
            aplicacoes_iatf=aplicacoes_iatf or [],
            pev_dias=_pev_dias(),
            del_max_1o_servico=int(get_param("meta_del_max_1o_servico", 100) or 100),
            peso_por_animal=peso_por_animal or {},
            idade_apta_dias=int(_idade_apta_min_meses() * 30.44),
            idade_atraso_dias=int(_idade_max_1a_cobertura_meses() * 30.44),
            peso_apta_kg=_peso_apta_min(),
        )

        # 1. CANDIDATAS IATF
        # `no_programa` já aplicou a regra R1 (a_descartar e baixa datada), que
        # `classificar_animal` não consulta sozinho.
        iatf_input = [
            {
                "numero_matriz": a["numero"],
                "sit_rep": a.get("sit_rep"),
                "diagnostico_ultimo": servico_por_animal.get(a["numero"], {}).get("diagnostico"),
            }
            for a in no_programa
        ]
        candidatas = selecionar_candidatas_iatf(iatf_input, estados_vivos)
        result.candidatas_iatf = candidatas
        if candidatas:
            result.necessidade_iatf = calcular_necessidade_hormonios(len(candidatas))

        # Próxima visita reprodutiva/BST — ancorada no serviço mais recente do
        # rebanho inteiro (não por animal individual). Intervalo em 0/vazio
        # (Configurações > Parâmetros) desliga o agendamento automático da
        # visita reprodutiva — ele simplesmente não aparece (ver Agenda
        # Reprodutiva, que então oferece configurar via janela suspensa).
        datas_servico = [s["data_servico"] for s in servicos if s.get("data_servico")]
        if datas_servico:
            ultimo_servico = max(datas_servico)
            if intervalo_visita_reprodutiva > 0:
                result.proxima_visita_iatf = ultimo_servico + timedelta(days=intervalo_visita_reprodutiva)
            result.proxima_visita_bst = ultimo_servico + timedelta(days=intervalo_bst)
        # A data real (última aplicação de BST + 12 dias, avançada até cair no
        # futuro) sempre tem prioridade sobre a estimativa acima — que é só um
        # chute por analogia ao serviço reprodutivo, usado apenas quando a
        # fazenda nunca lançou nenhuma aplicação de BST ainda.
        if proxima_visita_bst_real is not None:
            result.proxima_visita_bst = proxima_visita_bst_real

        # 1b. RETOQUE — diagnóstico positivo marcado para reconfirmar entra na
        # agenda no dia da próxima visita reprodutiva (data do diagnóstico + meta de
        # reinseminação; sem diagnóstico registrado, usa a data do serviço).
        # A cobrança para assim que um evento mais definitivo já tiver
        # resolvido a gestação sozinho — parto, secagem de rotina ou entrada
        # na janela de pré-parto (ver perda_prenhez.retoque_esta_resolvido);
        # sem isso, uma vaca que já pariu ou já está no pré-parto continuava
        # recebendo o alerta de retoque para sempre, já que só a
        # reconfirmação manual desligava o flag `retoque` do serviço.
        gestacao_dias_ref = gestacao_dias_referencia()
        pre_parto_max_dias = pre_parto_max()
        grupo_por_animal = {a["numero"]: a.get("grupo_primario") or "" for a in animais}
        for s in servicos:
            if not s.get("retoque"):
                continue
            numero_s = s["numero_matriz"]
            # Já está fisicamente no lote de pré-parto (grupo_primario aponta
            # pra um Lote com pre_parto=True) — mesmo sinal que já suspende o
            # alerta "Pré-parto" abaixo (grupos_ja_pre_parto). Verificação à
            # parte de `retoque_esta_resolvido`: o critério do lote é
            # race-aware (fazenda.rules.lote_criterios.dias_para_parto usa
            # dias_gestacao(raca)), enquanto o cálculo abaixo usa a média
            # configurável — as duas janelas podem divergir alguns dias para
            # raças fora do Holandês.
            if grupo_por_animal.get(numero_s) in grupos_ja_pre_parto:
                continue
            if retoque_esta_resolvido(
                data_servico=s.get("data_servico"),
                hoje=data_referencia,
                ultimo_parto=parto_por_animal.get(numero_s, {}).get("data_parto"),
                ultima_secagem_rotina=ult_secagem_rotina_por_animal.get(numero_s),
                dias_gestacao_referencia=gestacao_dias_ref,
                pre_parto_max_dias=pre_parto_max_dias,
            ):
                continue
            ancora = s.get("data_diagnostico") or s.get("data_servico")
            if not ancora:
                continue
            eventos.append(AgendaItem(
                data=ancora + timedelta(days=dias_reinseminacao),
                categoria="Reprodutivo",
                descricao=f"Retoque — reconfirmar diagnóstico de {s['numero_matriz']}",
                numero_animal=s["numero_matriz"],
            ))

        # 2. CHECAGEM DE HORMÔNIOS
        if result.necessidade_iatf:
            nec = result.necessidade_iatf
            estoque_map: dict[str, float] = {}
            for item in estoque:
                nome_lower = item["nome"].lower()
                for chave in ("sincrogest", "cidr", "sincrodiol", "sincroforte", "estron", "sincrocp", "lactotropin"):
                    if chave in nome_lower:
                        estoque_map[chave] = estoque_map.get(chave, 0) + (item.get("quantidade") or 0)

            checks = [
                CheckHormonio(
                    nome="Implante (Sincrogest/CIDR)",
                    estoque_atual=estoque_map.get("sincrogest", 0) + estoque_map.get("cidr", 0),
                    necessidade=nec.implantes,
                    unidade="unidade",
                    suficiente=(estoque_map.get("sincrogest", 0) + estoque_map.get("cidr", 0)) >= nec.implantes,
                    falta=max(0, nec.implantes - estoque_map.get("sincrogest", 0) - estoque_map.get("cidr", 0)),
                ),
                CheckHormonio(
                    nome="Sincrodiol (Benzoato)",
                    estoque_atual=estoque_map.get("sincrodiol", 0),
                    necessidade=nec.sincrodiol_ml,
                    unidade="ml",
                    suficiente=estoque_map.get("sincrodiol", 0) >= nec.sincrodiol_ml,
                    falta=max(0, nec.sincrodiol_ml - estoque_map.get("sincrodiol", 0)),
                ),
                CheckHormonio(
                    nome="Sincroforte (Buserelina)",
                    estoque_atual=estoque_map.get("sincroforte", 0),
                    necessidade=nec.sincroforte_ml,
                    unidade="ml",
                    suficiente=estoque_map.get("sincroforte", 0) >= nec.sincroforte_ml,
                    falta=max(0, nec.sincroforte_ml - estoque_map.get("sincroforte", 0)),
                ),
                CheckHormonio(
                    nome="Estron (Cloprostenol)",
                    estoque_atual=estoque_map.get("estron", 0),
                    necessidade=nec.estron_ml,
                    unidade="ml",
                    suficiente=estoque_map.get("estron", 0) >= nec.estron_ml,
                    falta=max(0, nec.estron_ml - estoque_map.get("estron", 0)),
                ),
                CheckHormonio(
                    nome="SincroCP (Cipionato)",
                    estoque_atual=estoque_map.get("sincrocp", 0),
                    necessidade=nec.sincrocp_ml,
                    unidade="ml",
                    suficiente=estoque_map.get("sincrocp", 0) >= nec.sincrocp_ml,
                    falta=max(0, nec.sincrocp_ml - estoque_map.get("sincrocp", 0)),
                ),
            ]
            result.hormonios_check = checks

        # 3. EVENTOS POR ANIMAL (gestação, secagem, scratch, PEV, BST, desmama)
        bst_elegiveis: list[ResultadoBST] = []
        bst_excluidos: list[ResultadoBST] = []
        bst_reanalise: list[ResultadoBST] = []

        for animal in animais:
            if not animal.get("ativo", True):
                continue

            numero = animal["numero"]
            raca = animal.get("raca")
            sit_rep = animal.get("sit_rep") or ""
            grupo = animal.get("grupo_primario") or ""

            servico = servico_por_animal.get(numero, {})
            parto = parto_por_animal.get(numero, {})

            data_parto_real = parto.get("data_parto")
            data_servico = servico.get("data_servico")
            diagnostico = (servico.get("diagnostico") or "").upper()
            ordem_parto = parto.get("ordem_parto") or servico.get("ordem_parto") or 0
            # Perda de prenhez registrada neste serviço (manual ou automática
            # por reinseminação, ver fazenda.rules.perda_prenhez) — mesmo
            # diagnóstico ainda marcado POSITIVO, a gestação não é mais
            # vigente: não gera Parto provável/Pré-parto/Secagem (senão a vaca
            # continuava recebendo pendência de mudar para o pré-parto mesmo
            # depois de perder a prenhez, o pedido do produtor que este bloco
            # existe para fechar).
            perdeu_prenhez = bool(servico.get("data_perda_prenhez"))
            gestante_vigente = diagnostico == "POSITIVO" and not perdeu_prenhez

            # DEL (dias em lactação) AO VIVO — `Animal.del_dias` é zerado no
            # instante do parto lançado no app (ver registrar_parto) mas fica
            # congelado dali em diante, só voltando a bater com a realidade
            # no próximo GERAL.csv (Ideagri); nunca reflete uma Secagem
            # lançada no app depois. Sem isso, tanto a decisão "está em
            # lactação, deve secar" (logo abaixo) quanto o DEL usado no BST
            # (atual e projetado, mais abaixo no loop) ficavam presos ao
            # valor congelado — um animal recém-parido pelo app nunca entrava
            # para secar, e um animal recém-seco pelo app nunca saía da lista
            # (ver auditoria ago/2026).
            del_dias = _del_dias_ao_vivo(
                animal.get("del_dias"), data_parto_real, ult_secagem_por_animal.get(numero), data_referencia,
            )

            # ── PARTO PROVÁVEL (só para prenhes com serviço positivo)
            # Se já houve um parto após este serviço, a prenhez já se resolveu
            # (a vaca pariu) — não gerar parto provável nem pré-parto/secagem,
            # senão vira uma pendência falsa de um parto que já ocorreu.
            ja_pariu_deste_servico = data_servico is not None and any(
                p.get("data_parto") and p["data_parto"] >= data_servico
                for p in partos_por_animal.get(numero, [])
            )
            data_parto_provavel = None
            if gestante_vigente and data_servico and not ja_pariu_deste_servico:
                res_gest = calcular_parto_provavel(data_servico, raca)
                data_parto_provavel = res_gest.data_parto_provavel
                eventos.append(AgendaItem(
                    data=data_parto_provavel,
                    categoria="Reprodutivo",
                    descricao=f"Parto provável ({raca or 'raça?'})",
                    numero_animal=numero,
                ))

                # ── PRÉ-PARTO (pre_parto_max dias antes, padrão 30 — TODA
                # gestante, novilha de 1ª cria inclusive: é só uma separação/
                # movimentação de manejo, não depende de lactação nenhuma).
                # Vem DEPOIS da Secagem (ver abaixo) — pre_parto_max é sempre
                # menor que periodo_seco_dias, então esta data cai depois.
                # Sem piso de data: um pré-parto vencido precisa continuar
                # aparecendo (e cair em "Atrasados" no front) até o animal
                # ser realmente movido — antes, a data passar simplesmente
                # apagava o alerta da Agenda, como se tivesse sido resolvido.
                data_pre_parto = data_parto_provavel - timedelta(days=pre_parto_max())
                if grupo not in grupos_ja_pre_parto:
                    eventos.append(AgendaItem(
                        data=data_pre_parto,
                        categoria="Reprodutivo",
                        descricao="Pré-parto",
                        numero_animal=numero,
                    ))

                # ── SECAGEM (periodo_seco_dias antes, padrão 60 — só quem já
                # pariu e está em lactação: novilha de 1ª cria nunca seca, e
                # quem não está em lactação não tem o que secar; ver dry_off.py).
                em_lactacao = bool(del_dias and del_dias > 0)
                res_sec = calcular_secagem(numero, data_parto_provavel, ordem_parto, em_lactacao)
                # Sem piso de data (mesmo racional do Pré-parto acima) — uma
                # secagem vencida precisa continuar aparecendo até ser feita.
                if res_sec.deve_secar:
                    eventos.append(AgendaItem(
                        data=res_sec.data_secagem,
                        categoria="Produção",
                        descricao=f"Secagem ({periodo_seco_dias()} dias antes do parto)",
                        numero_animal=numero,
                    ))

            # ── SCRATCH (14 dias após último serviço) — também dispara quando
            # a prenhez deste serviço já se perdeu (perdeu_prenhez): a vaca
            # volta a precisar de detector de cio, mesmo com o diagnóstico
            # antigo ainda marcado POSITIVO no registro.
            if data_servico and not gestante_vigente:
                res_scratch = calcular_scratch(numero, data_servico, servico.get("diagnostico"))
                if res_scratch.ativo and res_scratch.data_scratch >= data_referencia:
                    eventos.append(AgendaItem(
                        data=res_scratch.data_scratch,
                        categoria="Reprodutivo",
                        descricao="Aplicar Scratch (0,5) — detector de cio, 14 dias pós-IA",
                        numero_animal=numero,
                    ))

            # ── PEV (45 dias após parto)
            # A exclusão de gestante/inseminada sai do estado AO VIVO. Com o
            # `sit_rep` congelado, a vaca que engravidasse pelo app continuava
            # recebendo "PEV encerra — liberar p/ inseminar" até o próximo CSV.
            estado_vivo = (estados_vivos.get(numero) or {}).get("estado")
            if data_parto_real and estado_vivo not in (_E_GESTANTE, _E_INSEMINADA):
                res_pev = calcular_pev(numero, data_parto_real, data_referencia)
                if not res_pev.liberado:
                    eventos.append(AgendaItem(
                        data=res_pev.data_pev,
                        categoria="Reprodutivo",
                        descricao=f"PEV encerra — liberar p/ inseminar (faltam {res_pev.dias_restantes}d)",
                        numero_animal=numero,
                    ))

            # ── DESMAMA (90 dias) — bezerros, com destaque para o lote BEZ 3 (08).
            grupo_num = grupo.strip().split(" ")[0] if grupo else ""
            if grupo_num in ("06", "07", "08", "09"):
                data_nasc = animal.get("data_nasc")
                if data_nasc:
                    data_desmama = data_nasc + timedelta(days=90)
                    if data_desmama >= data_referencia:
                        dias_rest = (data_desmama - data_referencia).days
                        obs = "faltam 5 dias ou menos" if dias_rest <= 5 else None
                        eventos.append(AgendaItem(
                            data=data_desmama,
                            categoria="Produção",
                            descricao=f"Desmama aos 90 dias (faltam {dias_rest}d)",
                            numero_animal=numero,
                            observacao=obs,
                        ))

            # ── BST — marcada para excluir manualmente OU revertida (aguardando
            # nova aplicação para voltar a apta): não é "apta" nem "excluída
            # por critério automático" — vai para uma lista à parte, de
            # reanálise na próxima aplicação (indicador amarelo no front).
            if animal.get("excluir_bst") or animal.get("aguardando_nova_aplicacao_bst"):
                cod = (grupo or "").strip()[:2]
                if cod in ("01", "02", "03"):
                    res_bst = avaliar_bst(
                        numero_matriz=numero,
                        grupo_primario=grupo,
                        del_dias=del_dias,
                        data_secagem=data_parto_provavel - timedelta(days=60) if data_parto_provavel else None,
                        data_referencia=data_referencia,
                        del_atual=del_dias,
                        del_projetado=_del_projetado_bst(del_dias, result.proxima_visita_bst, data_referencia),
                    )
                    res_bst.motivo_exclusao = (
                        "Excluída manualmente do BST — revisar na próxima aplicação"
                        if animal.get("excluir_bst")
                        else "Revertida do BST — aguardando nova aplicação para voltar a apta"
                    )
                    bst_reanalise.append(res_bst)
            else:
                # DEL projetado para a data da PRÓXIMA aplicação de BST (não o DEL de
                # hoje) — uma vaca com DEL 55 hoje mas cuja próxima aplicação é daqui
                # a 6 dias já entra como candidata (chegará aos 60 dias na hora certa).
                del_dias_bst = del_dias
                if del_dias is not None and result.proxima_visita_bst and result.proxima_visita_bst > data_referencia:
                    del_dias_bst = del_dias + (result.proxima_visita_bst - data_referencia).days

                res_bst = avaliar_bst(
                    numero_matriz=numero,
                    grupo_primario=grupo,
                    del_dias=del_dias_bst,
                    data_secagem=data_parto_provavel - timedelta(days=60) if data_parto_provavel else None,
                    data_referencia=data_referencia,
                    del_atual=del_dias,
                    del_projetado=_del_projetado_bst(del_dias, result.proxima_visita_bst, data_referencia),
                )
                if res_bst.elegivel:
                    bst_elegiveis.append(res_bst)
                else:
                    # Excluídos do BST: apenas lactantes (01/02/03) que não cumprem os
                    # requisitos — não faz sentido listar a fazenda inteira.
                    cod = (grupo or "").strip()[:2]
                    if cod in ("01", "02", "03"):
                        bst_excluidos.append(res_bst)

        result.bst_elegiveis = bst_elegiveis
        result.bst_excluidos = bst_excluidos
        result.bst_reanalise = bst_reanalise

        # 3b. INDUÇÃO DE CIO (PGF2α/Cloprostenol) — aplicada nos últimos dias
        # do PEV pra estimular o cio (não é IATF nem diagnóstico, ver
        # fazenda/api/routers/reproducao.py::ATIVIDADE_INDUCAO_CIO). Observar
        # cio na janela de 2 a 5 dias após a aplicação — pára de avisar assim
        # que o cio já foi aproveitado (serviço mais recente do animal em
        # data >= aplicação).
        for inducao in (inducoes_cio or []):
            numero = inducao.get("numero_matriz")
            data_aplicacao = inducao.get("data_aplicacao")
            if not numero or not data_aplicacao:
                continue
            data_servico_recente = servico_por_animal.get(numero, {}).get("data_servico")
            if data_servico_recente and data_servico_recente >= data_aplicacao:
                continue
            janela_ini = data_aplicacao + timedelta(days=2)
            janela_fim = data_aplicacao + timedelta(days=5)
            if not (janela_ini <= data_referencia <= janela_fim):
                continue
            eventos.append(AgendaItem(
                data=data_referencia,
                categoria="Reprodutivo",
                descricao=f"Observar cio — indução aplicada em {data_aplicacao.strftime('%d/%m/%Y')} ({inducao.get('produto', 'PGF2α')}), esperado em 2 a 5 dias",
                numero_animal=numero,
            ))

        # 4. PESAGENS RECORRENTES
        # Terça mais próxima (bezerros, a cada 15 dias)
        # Quinta mais próxima (leite, toda quinta)
        dias_ate_quinta = (3 - data_referencia.weekday()) % 7 or 7
        proxima_quinta = data_referencia + timedelta(days=dias_ate_quinta)
        eventos.append(AgendaItem(
            data=proxima_quinta,
            categoria="Produção",
            descricao="Pesagem de leite (controle leiteiro)",
        ))

        dias_ate_terca = (1 - data_referencia.weekday()) % 7 or 7
        proxima_terca = data_referencia + timedelta(days=dias_ate_terca)
        eventos.append(AgendaItem(
            data=proxima_terca,
            categoria="Produção",
            descricao="Pesagem de bezerros / recria",
        ))

        # 5. CONTAS A PAGAR (próximos N dias — padrão 10, ou o período pedido pelo front)
        limite_contas = data_referencia + timedelta(days=dias_contas_a_pagar)
        contas_proximas = [
            c for c in contas
            if c.get("data_vencimento")
            and data_referencia <= c["data_vencimento"] <= limite_contas
            and (c.get("valor_pago") or 0) < (c.get("valor_total") or 0)
        ]
        result.contas_a_pagar = sorted(contas_proximas, key=lambda c: c["data_vencimento"])
        for conta in result.contas_a_pagar:
            eventos.append(AgendaItem(
                data=conta["data_vencimento"],
                categoria="Gestão/Financeiro",
                descricao=f"Conta a pagar: {conta.get('descricao', '')} — R$ {conta.get('valor_total', 0):,.2f}",
                observacao=conta.get("fornecedor_cliente"),
                ref=conta.get("numero_lancamento") or conta.get("numero_nota"),
            ))

        # 5b. NECESSIDADE DE COMPRA — só para itens marcados no cadastro
        # ("Exibir necessidade de compra na agenda") e abaixo do estoque mínimo.
        for item in estoque:
            if not item.get("exibir_necessidade_compra_agenda"):
                continue
            minimo = item.get("estoque_minimo")
            qtd = item.get("quantidade")
            if minimo is None or qtd is None or qtd >= minimo:
                continue
            eventos.append(AgendaItem(
                data=data_referencia,
                categoria="Gestão/Financeiro",
                descricao=f"Comprar {item['nome']} — estoque abaixo do mínimo ({qtd} de {minimo} {item.get('unidade') or ''})",
            ))

        # 5c. PEDIDOS — orçamento/ordem de serviço vencendo (2 dias antes),
        # enquanto o pedido segue aberto/parcialmente atendido (já filtrado
        # em agenda.py, ver PedidoAnexo).
        for doc in (pedidos_documentos_vencendo or []):
            validade = doc.get("data_validade")
            if not validade:
                continue
            alerta_em = validade - timedelta(days=2)
            if not (data_referencia <= alerta_em <= limite_contas):
                continue
            eventos.append(AgendaItem(
                data=alerta_em,
                categoria="Gestão/Financeiro",
                descricao=f"{doc.get('categoria', 'Documento')} do pedido {doc.get('numero_pedido', '')} vence em {validade.strftime('%d/%m/%Y')} — pedido ainda {doc.get('status_label', 'em aberto')}",
                observacao=doc.get("fornecedor_cliente"),
                ref=doc.get("numero_pedido"),
                link=f"/pedidos?id={doc.get('pedido_id')}" if doc.get("pedido_id") else None,
            ))

        # 5d. PESSOAS — contrato de trabalho por prazo determinado vencendo
        # (15 dias antes — mais antecedência que Pedido: decidir renovar ou
        # encerrar um vínculo de trabalho precisa de mais prazo do que
        # aprovar um orçamento), pessoa ainda ativa (já filtrado em
        # agenda.py, ver PessoaAnexo).
        for doc in (pessoas_documentos_vencendo or []):
            validade = doc.get("data_validade")
            if not validade:
                continue
            alerta_em = validade - timedelta(days=15)
            if not (data_referencia <= alerta_em <= limite_contas):
                continue
            eventos.append(AgendaItem(
                data=alerta_em,
                categoria="Gestão/Financeiro",
                descricao=f"{doc.get('categoria', 'Documento')} de {doc.get('pessoa_nome', '')} vence em {validade.strftime('%d/%m/%Y')}",
                ref=str(doc.get("pessoa_id")) if doc.get("pessoa_id") else None,
                link="/configuracoes?aba=cadastro&sub=pessoas",
            ))

        # 5e. DESCARTE PREVISTO — animal marcado "a descartar" com data de
        # saída planejada (Animal.descarte_previsto_em, opcional). Sem este
        # evento a data ficava só guardada no cadastro: ninguém era lembrado
        # quando ela chegava, e o animal seguia comendo.
        #
        # Duas âncoras, de propósito:
        #   - previsão FUTURA -> evento na própria data prevista;
        #   - previsão VENCIDA -> evento reancorado em HOJE, e continua
        #     aparecendo todo dia até a baixa ser lançada.
        #
        # A segunda âncora existe porque `AgendaItem.cor` é por CATEGORIA, não
        # por atraso — a Agenda não tem mecanismo de "vencido". Deixar o evento
        # na data original faria ele sumir da lista exatamente quando passa a
        # importar, que é o oposto de um lembrete. Quando a baixa é lançada o
        # animal deixa de ser `ativo` e o evento some sozinho, sem estado extra.
        for a_ in animais:
            if not a_.get("ativo") or not a_.get("a_descartar"):
                continue
            previsto = a_.get("descarte_previsto_em")
            if not previsto:
                continue  # sem previsão é estado legítimo, não pendência
            numero = a_.get("numero")
            if previsto >= data_referencia:
                if previsto > data_referencia + timedelta(days=DIAS_HORIZONTE_DESCARTE):
                    continue
                eventos.append(AgendaItem(
                    data=previsto,
                    categoria="Gestão/Financeiro",
                    descricao=f"Descarte previsto — {numero}",
                    numero_animal=numero,
                    link="/rebanho",
                ))
            else:
                eventos.append(AgendaItem(
                    data=data_referencia,
                    categoria="Gestão/Financeiro",
                    descricao=(
                        f"Descarte VENCIDO — {numero} "
                        f"(previsto para {previsto.strftime('%d/%m/%Y')}, ainda no rebanho)"
                    ),
                    numero_animal=numero,
                    link="/rebanho",
                ))

        # 6. EVENTOS MANUAIS
        for ev in eventos_manuais:
            data_ev = ev.get("data_evento")
            if data_ev and data_ev >= data_referencia:
                eventos.append(AgendaItem(
                    data=data_ev,
                    categoria=ev.get("categoria", "Gestão/Financeiro"),
                    descricao=ev.get("descricao", ""),
                    numero_animal=ev.get("numero_animal"),
                    observacao=ev.get("observacao"),
                    fonte="manual",
                    lote=ev.get("lotes"),
                    tipo_evento=ev.get("tipo_evento"),
                    apenas_admin=bool(ev.get("apenas_admin")),
                    link=ev.get("link"),
                ))

        # Ordena todos os eventos por data
        result.eventos = sorted(eventos, key=lambda e: e.data)
        return result
