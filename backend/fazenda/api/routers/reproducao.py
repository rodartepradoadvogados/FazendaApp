"""
Router de reprodução — dados achatados para o dashboard interativo de análise
e lançamento de diagnóstico de gestação.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user
from fazenda.database import get_session
from fazenda.models import (
    Animal, ControleLeiteiro, EstoqueSemen, Parto, PesagemCorporal, ProtocoloIatfAplicacao, ProtocoloIatfHormonio, ProtocoloIatfLancamento,
    SeedFlag, Secagem, Servico, Usuario,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules.agenda_veterinario import classificar_rebanho
from fazenda.rules.auditoria import mapa_usuarios, usuario_id_seguro
from fazenda.rules.genetica import calcular_grau_sangue_cria
from fazenda.rules.reproducao_analise import agregar_mensal, analisar_servicos

router = APIRouter(prefix="/reproducao", tags=["reproducao"])


def deduplicar_partos(session: Session) -> None:
    """Remove partos duplicados que sobraram de reimportações antigas do CSV
    reprodutivo (o import só inseria e nunca limpava — uma vaca com N uploads
    ficava com N partos iguais). Roda UMA vez (guardada por SeedFlag): para
    cada (matriz, data), mantém só o registro mais antigo. Uma vaca não pode
    parir duas vezes no mesmo dia, então colapsar por (matriz, data) é seguro.
    """
    chave = "partos_dedup_v1"
    if session.get(SeedFlag, chave):
        return
    vistos: set[tuple[str, object]] = set()
    for p in session.exec(select(Parto).order_by(Parto.id)).all():
        k = (p.numero_matriz, p.data_parto)
        if k in vistos:
            session.delete(p)
        else:
            vistos.add(k)
    session.add(SeedFlag(chave=chave))
    session.commit()

# Passos do protocolo IATF — mesmo cronograma já usado no rascunho do front
# (D0/D7/D9/D11); aqui viram eventos reais na Agenda em vez de só um desenho.
PASSOS_PROTOCOLO_IATF = [
    (0, "Implante de progesterona + Benzoato de estradiol + Acetato de buserelina (D0)"),
    (7, "Cloprostenol (D7)"),
    (9, "Retirar implante + Cipionato de estradiol + Cloprostenol (D9)"),
    (11, "Inseminação (IATF) — D11"),
]


@router.get("/agenda-veterinario")
def agenda_veterinario(session: Session = Depends(get_session)) -> dict:
    """
    Roteiro do veterinário do serviço: classifica o rebanho fêmea em 9 listas
    (ver fazenda.rules.agenda_veterinario para os critérios de cada uma).
    """
    hoje = date.today()
    animais = [
        a.model_dump() for a in session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
    ]

    servico_por_animal: dict[str, dict] = {}
    for s in session.exec(select(Servico)).all():
        atual = servico_por_animal.get(s.numero_matriz)
        if not atual or (s.data_servico and (not atual.get("data_servico") or s.data_servico > atual["data_servico"])):
            servico_por_animal[s.numero_matriz] = s.model_dump()

    peso_por_animal: dict[str, float] = {}
    ultima_data: dict[str, date] = {}
    for p in session.exec(select(PesagemCorporal)).all():
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg

    listas = classificar_rebanho(animais, servico_por_animal, peso_por_animal, hoje)
    return {"data_referencia": hoje.isoformat(), "listas": listas, "totais": {k: len(v) for k, v in listas.items()}}


@router.get("/servicos")
def listar_servicos_analise(session: Session = Depends(get_session)) -> dict:
    """
    Todos os serviços achatados com as dimensões da análise reprodutiva
    (concepção/perda por categoria, raça, ordem de parto/tentativa, condição
    de IA, inseminador, mês, DEL). O front filtra/agrega no cliente.
    """
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    registros = analisar_servicos(servicos)
    nomes = mapa_usuarios(session, {r["usuario_id"] for r in registros})
    for r in registros:
        r["usuario_nome"] = nomes.get(r.pop("usuario_id"))
    return {"servicos": registros, "total": len(registros)}


@router.get("/indicadores-mensais")
def indicadores_mensais_analise(session: Session = Depends(get_session)) -> dict:
    """
    Série mensal cruzando métricas reprodutivas (serviços, métodos, concepção,
    perdas) e produtivas (secagens, produção de leite, DEL) — alimenta o
    gráfico interativo configurável de Análise reprodutiva (escolha de
    métricas e eixo ano/mês).
    """
    servicos = [s.model_dump() for s in session.exec(select(Servico)).all()]
    registros = analisar_servicos(servicos)
    secagens = [s.model_dump() for s in session.exec(select(Secagem)).all()]
    controles = [c.model_dump() for c in session.exec(select(ControleLeiteiro)).all()]
    return agregar_mensal(registros, secagens, controles)


class DiagnosticoIn(BaseModel):
    numero_matriz: str
    data_diagnostico: date
    resultado: str  # "retoque" | "reconfirmada" | "negativo" | "indefinido"
    metodo: str | None = None  # Palpação | Ultrassom | Cio de repasse


@router.post("/diagnostico")
def registrar_diagnostico(dados: DiagnosticoIn, session: Session = Depends(get_session)) -> dict:
    """
    Registra o resultado do diagnóstico de gestação no serviço mais recente da
    matriz. Se marcado "retoque", o lembrete de reconfirmação entra na agenda
    na data do próximo serviço (agenda_engine.py). "Indefinido" (inconclusivo)
    é distinto de "negativo" — a matriz não vira vazia, segue para reavaliar.
    """
    if dados.resultado not in ("retoque", "reconfirmada", "negativo", "indefinido"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    servico = session.exec(
        select(Servico)
        .where(Servico.numero_matriz == dados.numero_matriz)
        .order_by(Servico.data_servico.desc())
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_diagnostico = dados.data_diagnostico
    servico.metodo_diagnostico = dados.metodo
    if dados.resultado == "retoque":
        servico.diagnostico = "POSITIVO"
        servico.retoque = True
    elif dados.resultado == "reconfirmada":
        servico.diagnostico = "POSITIVO"
        servico.retoque = False
    elif dados.resultado == "indefinido":
        servico.diagnostico = "INDEFINIDO"
        servico.retoque = False
    else:
        servico.diagnostico = "NEGATIVO"
        servico.retoque = False

    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


class ReconfirmacaoIn(BaseModel):
    numero_matriz: str
    data_reconfirmacao: date
    resultado: str  # "positivo" | "negativo"


@router.post("/reconfirmacao")
def registrar_reconfirmacao(dados: ReconfirmacaoIn, session: Session = Depends(get_session)) -> dict:
    """
    Segundo exame (reconfirmação, ~60 dias do serviço) — distinto do primeiro
    toque. Usado pela agenda do veterinário para tirar o animal de "atrasada
    para reconfirmação" e classificá-lo como gestante confirmada.
    """
    if dados.resultado not in ("positivo", "negativo"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    servico = session.exec(
        select(Servico)
        .where(Servico.numero_matriz == dados.numero_matriz)
        .order_by(Servico.data_servico.desc())
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_reconfirmacao = dados.data_reconfirmacao
    servico.diagnostico_reconfirmacao = "POSITIVO" if dados.resultado == "positivo" else "NEGATIVO"
    servico.retoque = False

    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


class CriaIn(BaseModel):
    numero: str = ""      # vazio = cria sem número → baixa automática (natimorto/não entra no rebanho)
    sexo: str  # "F" | "M"
    nasceu_viva: bool = True


class PartoIn(BaseModel):
    numero_matriz: str
    data_parto: date
    tipo_parto: str | None = None
    crias: list[CriaIn] = []
    retencao_placenta: bool | None = None
    gemelar: bool | None = None
    gemelar_sexo: str | None = None  # "FF" | "FM" | "MM" (informado ou derivado dos sexos das crias)
    observacao: str | None = None


@router.post("/parto")
def registrar_parto(dados: PartoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    """
    Registra o parto e cria a ficha de cada cria nascida viva ainda não
    cadastrada. Não move ninguém de lote sozinho — o front sugere o lote via
    /producao/sugestao-lote-evento e só move (POST /movimentacoes/mover) com
    confirmação explícita do usuário.
    """
    mae = session.exec(select(Animal).where(Animal.numero == dados.numero_matriz)).first()
    if not mae:
        raise HTTPException(status_code=404, detail="Matriz não encontrada")

    ultimo_parto = session.exec(
        select(Parto).where(Parto.numero_matriz == dados.numero_matriz).order_by(Parto.ordem_parto.desc())
    ).first()
    ordem_parto = (ultimo_parto.ordem_parto or 0) + 1 if ultimo_parto else 1

    # Sexo do parto gemelar: usa o informado ou deriva dos sexos das crias.
    gemelar_sexo = dados.gemelar_sexo
    if not gemelar_sexo and len(dados.crias) >= 2:
        combo = "".join(sorted((dados.crias[0].sexo or "").upper() + (dados.crias[1].sexo or "").upper()))
        gemelar_sexo = {"FF": "FF", "FM": "FM", "MM": "MM"}.get(combo)

    parto = Parto(
        animal_id=mae.id,
        numero_matriz=dados.numero_matriz,
        data_parto=dados.data_parto,
        ordem_parto=ordem_parto,
        tipo_parto=dados.tipo_parto,
        sexo_cria_1=dados.crias[0].sexo if len(dados.crias) > 0 else None,
        sexo_cria_2=dados.crias[1].sexo if len(dados.crias) > 1 else None,
        numero_cria_1=(dados.crias[0].numero or None) if len(dados.crias) > 0 else None,
        numero_cria_2=(dados.crias[1].numero or None) if len(dados.crias) > 1 else None,
        gemelar=dados.gemelar if dados.gemelar is not None else len(dados.crias) > 1,
        gemelar_sexo=gemelar_sexo,
        retencao_placenta=dados.retencao_placenta,
        usuario_id=usuario_id_seguro(user),
    )
    session.add(parto)

    crias_criadas = []
    crias_baixadas = []
    for cria in dados.crias:
        # Sem número OU marcada como não-viva → baixa automática (natimorto/não
        # entra no rebanho). Fica registrada no parto (sexo), mas sem ficha.
        if not (cria.numero or "").strip() or not cria.nasceu_viva:
            crias_baixadas.append(cria.sexo or "?")
            continue
        if session.exec(select(Animal).where(Animal.numero == cria.numero)).first():
            continue  # já cadastrada — não sobrescreve
        raca_cria, grau_sangue_cria = calcular_grau_sangue_cria(session, mae, dados.data_parto)
        session.add(Animal(
            numero=cria.numero, sexo=cria.sexo, raca=raca_cria, grau_sangue=grau_sangue_cria, data_nasc=dados.data_parto,
            mae_numero=mae.numero, mae_nome=mae.nome, ativo=True,
        ))
        crias_criadas.append(cria.numero)

    # Retenção de placenta → gera um item na Agenda (avaliação/tratamento) no
    # dia do parto, para não passar despercebido.
    if dados.retencao_placenta:
        from fazenda.models import AgendaManual
        session.add(AgendaManual(
            data_evento=dados.data_parto,
            descricao=f"Retenção de placenta — vaca {mae.numero}: avaliar/tratar",
            categoria="Sanidade",
            numero_animal=mae.numero,
            tipo_evento="Outro",
            observacao="Gerado automaticamente pelo lançamento de parto com retenção de placenta.",
            usuario_id=usuario_id_seguro(user),
        ))

    # DEL reseta ao parir — o resto da ficha (categoria, produção etc.) só é
    # atualizado de fato no próximo upload do GERAL.csv.
    mae.del_dias = 0
    mae.atualizado_em = datetime.utcnow()
    session.add(mae)

    session.commit()
    return {"criado": True, "ordem_parto": ordem_parto, "crias_criadas": crias_criadas, "crias_baixadas": crias_baixadas}


class HormonioIatfIn(BaseModel):
    dia: int  # 0, 7 ou 9 (D11 é inseminação, sem hormônio)
    produto: str
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None


class ProtocoloIatfIn(BaseModel):
    animais: list[str]
    data_d0: date
    protocolo: str = "Protocolo IATF"
    # Medicamentos por dia (ex.: D0 = 1ml SincroCP + 2ml Estron). Opcional —
    # sem eles, o protocolo funciona como antes (sem baixa de estoque).
    hormonios: list[HormonioIatfIn] = []


@router.post("/protocolo-iatf")
def lancar_protocolo_iatf(dados: ProtocoloIatfIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    """
    Agenda só o PROTOCOLO hormonal (D0/D7/D9/D11) — não cria o serviço em si.
    A inseminação de fato (D11) é lançada à parte em POST /reproducao/servico,
    para separar "marcar o protocolo" de "a vaca foi inseminada". Cada etapa de
    cada animal vira uma ProtocoloIatfAplicacao rastreável — a Agenda agrupa
    por (lançamento, dia) em vez de mostrar uma linha por animal.
    """
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    lancamento = ProtocoloIatfLancamento(nome_protocolo=dados.protocolo, data_d0=dados.data_d0, usuario_id=usuario_id_seguro(user))
    session.add(lancamento)
    session.flush()  # garante lancamento.id antes de criar as aplicações

    # Medicamentos por dia (aplicados a todas as vacas do passo). Se o usuário
    # informou hormônios, a descrição de cada dia passa a listá-los.
    hormonios_por_dia: dict[int, list[HormonioIatfIn]] = {}
    for h in dados.hormonios:
        if (h.produto or "").strip():
            hormonios_por_dia.setdefault(h.dia, []).append(h)
            session.add(ProtocoloIatfHormonio(
                lancamento_id=lancamento.id, dia=h.dia, produto=h.produto.strip(),
                dose=h.dose, unidade=h.unidade, via=h.via,
            ))

    def _descricao_dia(dias: int, padrao: str) -> str:
        hs = hormonios_por_dia.get(dias)
        if not hs:
            return padrao
        return " + ".join(f"{h.dose or ''}{(' ' + h.unidade) if h.unidade else ''} {h.produto}".strip() for h in hs)

    eventos_criados = 0
    for numero in dados.animais:
        for dias, descricao in PASSOS_PROTOCOLO_IATF:
            session.add(ProtocoloIatfAplicacao(
                lancamento_id=lancamento.id,
                numero_matriz=numero,
                dia=dias,
                descricao=_descricao_dia(dias, descricao),
                data_prevista=dados.data_d0 + timedelta(days=dias),
            ))
            eventos_criados += 1

    session.commit()
    return {"criado": True, "lancamento_id": lancamento.id, "eventos_criados": eventos_criados, "animais": len(dados.animais)}


@router.get("/protocolo-iatf/ativos")
def listar_protocolos_iatf_ativos(session: Session = Depends(get_session)) -> list[dict]:
    """
    Protocolos IATF com pelo menos uma etapa ainda não realizada — para ver de
    relance em qual dia (D0/D7/D9/D11) está cada animal em andamento.

    Um protocolo com TODAS as etapas concluídas (D11/inseminação já com
    baixa) some da lista principal, mas continua aparecendo por mais um
    ciclo (intervalo_visita_reprodutiva dias, editável em Configurações >
    Parâmetros) como "concluido": True, mostrando a data do próximo serviço
    (D11 + intervalo) e as candidatas herd-wide ao próximo repasse (mesmo
    critério de `selecionar_candidatas_iatf`, usado na Agenda) — ver #369.
    """
    from fazenda.rules.iatf import selecionar_candidatas_iatf
    from fazenda.rules.parametros import intervalo_visita_reprodutiva

    hoje = date.today()
    intervalo = intervalo_visita_reprodutiva()
    lancamentos = session.exec(select(ProtocoloIatfLancamento).order_by(ProtocoloIatfLancamento.data_d0.desc())).all()
    aplicacoes = session.exec(select(ProtocoloIatfAplicacao)).all()
    por_lancamento: dict[int, list[ProtocoloIatfAplicacao]] = {}
    for ap in aplicacoes:
        por_lancamento.setdefault(ap.lancamento_id, []).append(ap)

    _candidatas_cache: list | None = None

    def candidatas_herd() -> list[dict]:
        nonlocal _candidatas_cache
        if _candidatas_cache is None:
            animais = session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
            servicos = session.exec(select(Servico).where(Servico.ult_ocorrencia == 1)).all()
            diag_por_animal = {s.numero_matriz: s.diagnostico for s in servicos}
            iatf_input = [
                {
                    "numero_matriz": a.numero, "sit_rep": a.sit_rep, "del_dias": a.del_dias,
                    "diagnostico_ultimo": diag_por_animal.get(a.numero),
                }
                for a in animais
            ]
            candidatas = selecionar_candidatas_iatf(iatf_input)
            _candidatas_cache = [
                {"numero_matriz": c.numero_matriz, "sit_rep": c.sit_rep, "del_dias": c.del_dias, "motivo": c.motivo}
                for c in candidatas
            ]
        return _candidatas_cache

    ativos = []
    for lanc in lancamentos:
        aps = por_lancamento.get(lanc.id, [])
        pendentes = [a for a in aps if not a.realizada]
        d11s = [a for a in aps if a.dia == 11]

        if not pendentes:
            if not d11s:
                continue  # protocolo sem etapa D11 cadastrada — nada a projetar
            data_d11 = max((a.data_realizacao or a.data_prevista) for a in d11s)
            proxima_visita = data_d11 + timedelta(days=intervalo)
            if hoje > proxima_visita + timedelta(days=7):
                continue  # já passou da janela útil — não mostra mais
            ativos.append({
                "lancamento_id": lanc.id,
                "nome_protocolo": lanc.nome_protocolo,
                "data_d0": lanc.data_d0.isoformat(),
                "animais": [],
                "concluido": True,
                "data_d11": data_d11.isoformat(),
                "proxima_visita": proxima_visita.isoformat(),
                "candidatas_proxima_visita": candidatas_herd(),
            })
            continue

        por_animal: dict[str, list[ProtocoloIatfAplicacao]] = {}
        for ap in aps:
            por_animal.setdefault(ap.numero_matriz, []).append(ap)
        animais_status = []
        for numero, aps_animal in sorted(por_animal.items(), key=lambda item: chave_numero(item[0])):
            proxima = min((a for a in aps_animal if not a.realizada), key=lambda a: a.dia, default=None)
            animais_status.append({
                "numero_matriz": numero,
                "etapa_atual": f"D{proxima.dia}" if proxima else "Concluído",
                "data_etapa_atual": proxima.data_prevista.isoformat() if proxima else None,
            })
        ativos.append({
            "lancamento_id": lanc.id,
            "nome_protocolo": lanc.nome_protocolo,
            "data_d0": lanc.data_d0.isoformat(),
            "animais": animais_status,
            "concluido": False,
        })
    return ativos


@router.get("/protocolo-iatf/lancamentos")
def listar_lancamentos_iatf(session: Session = Depends(get_session)) -> list[dict]:
    """
    Todos os lançamentos de protocolo IATF (para adicionar animais a um
    protocolo já existente — mesmo D0 e mesmo nome). Mais recentes primeiro.
    """
    lancamentos = session.exec(
        select(ProtocoloIatfLancamento).order_by(ProtocoloIatfLancamento.data_d0.desc(), ProtocoloIatfLancamento.id.desc())
    ).all()
    aplicacoes = session.exec(select(ProtocoloIatfAplicacao)).all()
    animais_por_lanc: dict[int, set[str]] = {}
    for ap in aplicacoes:
        animais_por_lanc.setdefault(ap.lancamento_id, set()).add(ap.numero_matriz)
    return [
        {
            "lancamento_id": l.id,
            "nome_protocolo": l.nome_protocolo,
            "data_d0": l.data_d0.isoformat(),
            "qtd_animais": len(animais_por_lanc.get(l.id, set())),
        }
        for l in lancamentos
    ]


class AdicionarAnimaisIatfIn(BaseModel):
    animais: list[str]


@router.post("/protocolo-iatf/{lancamento_id}/animais")
def adicionar_animais_iatf(lancamento_id: int, dados: AdicionarAnimaisIatfIn, session: Session = Depends(get_session)) -> dict:
    """
    Adiciona animais a um protocolo IATF já lançado (esqueci de incluí-los na
    hora). Reaproveita a MESMA data de D0 e os mesmos hormônios por dia; ignora
    animais que já estão no protocolo.
    """
    lancamento = session.get(ProtocoloIatfLancamento, lancamento_id)
    if not lancamento:
        raise HTTPException(status_code=404, detail="Protocolo IATF não encontrado")
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    ja_no_protocolo = {
        a.numero_matriz for a in session.exec(
            select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lancamento_id)
        ).all()
    }
    # Hormônios por dia deste lançamento → mesma descrição das etapas.
    hormonios = session.exec(
        select(ProtocoloIatfHormonio).where(ProtocoloIatfHormonio.lancamento_id == lancamento_id)
    ).all()
    hormonios_por_dia: dict[int, list[ProtocoloIatfHormonio]] = {}
    for h in hormonios:
        hormonios_por_dia.setdefault(h.dia, []).append(h)

    def _descricao_dia(dias: int, padrao: str) -> str:
        hs = hormonios_por_dia.get(dias)
        if not hs:
            return padrao
        return " + ".join(f"{h.dose or ''}{(' ' + h.unidade) if h.unidade else ''} {h.produto}".strip() for h in hs)

    novos = 0
    for numero in dados.animais:
        if numero in ja_no_protocolo:
            continue
        for dias, descricao in PASSOS_PROTOCOLO_IATF:
            session.add(ProtocoloIatfAplicacao(
                lancamento_id=lancamento_id,
                numero_matriz=numero,
                dia=dias,
                descricao=_descricao_dia(dias, descricao),
                data_prevista=lancamento.data_d0 + timedelta(days=dias),
            ))
        novos += 1

    session.commit()
    return {"adicionados": novos, "lancamento_id": lancamento_id, "nome_protocolo": lancamento.nome_protocolo}


class ServicoIn(BaseModel):
    numero_matriz: str
    data_servico: date
    tipo_servico: str = "IA"  # "IA" | "Monta natural"
    protocolo: str | None = None  # preenchido = veio de um protocolo IATF; vazio = cio natural
    reprodutor: str | None = None
    responsavel: str | None = None


@router.post("/servico")
def registrar_servico(dados: ServicoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    """
    Registra a inseminação/cobertura em si — cio natural (sem protocolo) ou a
    inseminação de um protocolo IATF já agendado (protocolo preenchido).
    """
    animal = session.exec(select(Animal).where(Animal.numero == dados.numero_matriz)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Matriz não encontrada")

    anteriores = session.exec(select(Servico).where(Servico.numero_matriz == dados.numero_matriz)).all()
    for s in anteriores:
        if s.ult_ocorrencia == 1:
            s.ult_ocorrencia = 0
            session.add(s)

    ultimo = max(anteriores, key=lambda s: s.data_servico or date.min, default=None)
    ordem_tentativa = (ultimo.ordem_tentativa or 0) + 1 if ultimo else 1
    intervalo = (dados.data_servico - ultimo.data_servico).days if ultimo and ultimo.data_servico else None

    servico = Servico(
        animal_id=animal.id,
        numero_matriz=dados.numero_matriz,
        raca_matriz=animal.raca,
        data_nasc_matriz=animal.data_nasc,
        data_servico=dados.data_servico,
        tipo_servico=dados.tipo_servico,
        protocolo=dados.protocolo,
        reprodutor=dados.reprodutor,
        inseminador=dados.responsavel,
        ordem_tentativa=ordem_tentativa,
        intervalo_tentativas=intervalo,
        del_servico=animal.del_dias,
        ult_ocorrencia=1,
        usuario_id=usuario_id_seguro(user),
    )
    session.add(servico)

    # Veio de um protocolo IATF: resolve automaticamente a aplicação D11 em
    # aberto correspondente — a Agenda para de lembrar essa etapa sozinha,
    # sem exigir um segundo clique de "marcar realizado" separado.
    if dados.protocolo:
        aplicacao_d11 = session.exec(
            select(ProtocoloIatfAplicacao)
            .join(ProtocoloIatfLancamento, ProtocoloIatfAplicacao.lancamento_id == ProtocoloIatfLancamento.id)
            .where(
                ProtocoloIatfAplicacao.numero_matriz == dados.numero_matriz,
                ProtocoloIatfAplicacao.dia == 11,
                ProtocoloIatfAplicacao.realizada == False,  # noqa: E712
                ProtocoloIatfLancamento.nome_protocolo == dados.protocolo,
            )
        ).first()
        if aplicacao_d11:
            aplicacao_d11.realizada = True
            aplicacao_d11.data_realizacao = dados.data_servico
            session.add(aplicacao_d11)

    session.commit()
    session.refresh(servico)
    return servico.model_dump()


def _nome_auto_iatf(d0: date) -> str:
    """Nome padrão do protocolo IATF: 'IATF <D0> A <D11>' (datas dd/mm/aa)."""
    d11 = d0 + timedelta(days=11)
    return f"IATF {d0.strftime('%d/%m/%y')} A {d11.strftime('%d/%m/%y')}"


def _registrar_um_servico(session: Session, numero_matriz: str, data_servico: date,
                          tipo_servico: str, protocolo: str | None, reprodutor: str | None,
                          inseminador: str | None = None, usuario_id: int | None = None) -> Servico | None:
    """Cria um Servico para uma matriz (mesma lógica de registrar_servico, sem
    commit) — resolve o D11 do protocolo IATF vinculado, se houver."""
    animal = session.exec(select(Animal).where(Animal.numero == numero_matriz)).first()
    if not animal:
        return None
    anteriores = session.exec(select(Servico).where(Servico.numero_matriz == numero_matriz)).all()
    for s in anteriores:
        if s.ult_ocorrencia == 1:
            s.ult_ocorrencia = 0
            session.add(s)
    ultimo = max(anteriores, key=lambda s: s.data_servico or date.min, default=None)
    ordem_tentativa = (ultimo.ordem_tentativa or 0) + 1 if ultimo else 1
    intervalo = (data_servico - ultimo.data_servico).days if ultimo and ultimo.data_servico else None
    servico = Servico(
        animal_id=animal.id, numero_matriz=numero_matriz, raca_matriz=animal.raca,
        data_nasc_matriz=animal.data_nasc, data_servico=data_servico, tipo_servico=tipo_servico,
        protocolo=protocolo, reprodutor=reprodutor, inseminador=inseminador, ordem_tentativa=ordem_tentativa,
        intervalo_tentativas=intervalo, del_servico=animal.del_dias, ult_ocorrencia=1, usuario_id=usuario_id,
    )
    session.add(servico)
    if protocolo:
        ap_d11 = session.exec(
            select(ProtocoloIatfAplicacao)
            .join(ProtocoloIatfLancamento, ProtocoloIatfAplicacao.lancamento_id == ProtocoloIatfLancamento.id)
            .where(
                ProtocoloIatfAplicacao.numero_matriz == numero_matriz,
                ProtocoloIatfAplicacao.dia == 11,
                ProtocoloIatfAplicacao.realizada == False,  # noqa: E712
                ProtocoloIatfLancamento.nome_protocolo == protocolo,
            )
        ).first()
        if ap_d11:
            ap_d11.realizada = True
            ap_d11.data_realizacao = data_servico
            session.add(ap_d11)
    return servico


def _animal_tem_protocolo_pendente(session: Session, numero_matriz: str) -> ProtocoloIatfLancamento | None:
    """Retorna o lançamento IATF com etapa pendente do animal (o mais recente)."""
    ap = session.exec(
        select(ProtocoloIatfAplicacao)
        .where(ProtocoloIatfAplicacao.numero_matriz == numero_matriz, ProtocoloIatfAplicacao.realizada == False)  # noqa: E712
    ).all()
    if not ap:
        return None
    lanc_ids = {a.lancamento_id for a in ap}
    lancs = [l for l in (session.get(ProtocoloIatfLancamento, lid) for lid in lanc_ids) if l]
    return max(lancs, key=lambda l: l.data_d0, default=None) if lancs else None


class ServicoLoteIn(BaseModel):
    animais: list[str]
    data_servico: date
    tipo: str  # "cio_natural" | "iatf" | "monta_natural"
    reprodutor: str | None = None
    responsavel: str | None = None
    protocolo_lancamento_id: int | None = None  # IATF: vincular a este lançamento
    auto_lancar_iatf: bool = False  # IATF: se não há protocolo, cria um retroativo (D0 = serviço − 11)


@router.post("/servico-lote")
def registrar_servico_lote(dados: ServicoLoteIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user)) -> dict:
    """
    Inseminação de vários animais de uma vez. `tipo` = cio_natural (IA sem
    protocolo), iatf (IA vinculada a protocolo) ou monta_natural. No IATF, se o
    animal não estiver em protocolo e `auto_lancar_iatf`, cria um protocolo
    retroativo (D0 = data do serviço − 11) só para registrar/vincular — sem
    hormônio. Animais IATF sem protocolo e sem auto-lançar entram em
    `incompativeis` (a UI pergunta o que fazer).
    """
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")
    if dados.tipo not in ("cio_natural", "iatf", "monta_natural"):
        raise HTTPException(status_code=400, detail="Tipo inválido")

    tipo_servico = "Monta natural" if dados.tipo == "monta_natural" else "IA"
    lanc_escolhido = session.get(ProtocoloIatfLancamento, dados.protocolo_lancamento_id) if dados.protocolo_lancamento_id else None

    criados, incompativeis = 0, []
    for numero in dados.animais:
        protocolo_name: str | None = None
        if dados.tipo == "iatf":
            alvo = lanc_escolhido or _animal_tem_protocolo_pendente(session, numero)
            if alvo is None and dados.auto_lancar_iatf:
                d0 = dados.data_servico - timedelta(days=11)
                alvo = ProtocoloIatfLancamento(nome_protocolo=_nome_auto_iatf(d0), data_d0=d0, retroativo=True, usuario_id=usuario_id_seguro(user))
                session.add(alvo)
                session.flush()
                for dias, descricao in PASSOS_PROTOCOLO_IATF:
                    session.add(ProtocoloIatfAplicacao(
                        lancamento_id=alvo.id, numero_matriz=numero, dia=dias,
                        descricao=descricao, data_prevista=d0 + timedelta(days=dias),
                    ))
            elif alvo is not None:
                ja = session.exec(
                    select(ProtocoloIatfAplicacao).where(
                        ProtocoloIatfAplicacao.lancamento_id == alvo.id,
                        ProtocoloIatfAplicacao.numero_matriz == numero,
                    )
                ).first()
                if not ja:
                    for dias, descricao in PASSOS_PROTOCOLO_IATF:
                        session.add(ProtocoloIatfAplicacao(
                            lancamento_id=alvo.id, numero_matriz=numero, dia=dias,
                            descricao=descricao, data_prevista=alvo.data_d0 + timedelta(days=dias),
                        ))
            if alvo is None:
                incompativeis.append(numero)
                continue
            session.flush()
            protocolo_name = alvo.nome_protocolo

        s = _registrar_um_servico(session, numero, dados.data_servico, tipo_servico, protocolo_name, dados.reprodutor, dados.responsavel, usuario_id=usuario_id_seguro(user))
        if s is None:
            incompativeis.append(numero)
        else:
            criados += 1

    # Desconta 1 dose por inseminação realizada (IA — cio natural ou IATF; não
    # se aplica à monta natural, que não usa sêmen estocado) do touro
    # informado, casando por nome, NAAB ou código — mantém o Estoque de Sêmen
    # em dia com o uso real sem exigir baixa manual a cada inseminação.
    if criados and dados.tipo != "monta_natural" and dados.reprodutor:
        alvo = dados.reprodutor.strip().lower()
        touro = next(
            (t for t in session.exec(select(EstoqueSemen)).all()
             if (t.touro_nome or "").strip().lower() == alvo
             or (t.naab or "").strip().lower() == alvo
             or (t.codigo or "").strip().lower() == alvo),
            None,
        )
        if touro:
            touro.doses = touro.doses - criados
            touro.atualizado_em = datetime.utcnow()
            session.add(touro)

    session.commit()
    return {"criados": criados, "incompativeis": incompativeis, "tipo": dados.tipo}
