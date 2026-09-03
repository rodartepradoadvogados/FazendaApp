"""
Router de animais — listagem e consulta de animais.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    Animal, AgendaManual, BaixaAnimal, ColostragemBezerra, CompraAnimal, ControleLeiteiro, EstoqueSemen,
    EventoSanitario, ExameResultado, MovimentoLote, OcorrenciaClinica, Parto,
    PesagemCorporal, ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento,
    ProtocoloIatfAplicacao, ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento,
    ProtocoloSanitario, ProtocoloSanitarioLancamento, QualidadeLeite,
    Sanidade, Secagem, Servico, Touro, VendaAnimal,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.parametros import get_param, pre_parto_max
from fazenda.rules.parto_resumo import resumo_por_parto
from fazenda.rules.perda_prenhez import servicos_positivos_vigentes
from fazenda.rules.gestation import dias_gestacao_da_raca
from fazenda.rules.lactacao import em_lactacao_por_matriz as lactacoes_abertas_por_matriz
from fazenda.rules.parto import eh_parto_produtivo
from fazenda.rules.producao_leiteira import com_fallback_animal, del_dias_ao_vivo, ultimo_controle_por_animal
from fazenda.rules.relatorios_gerenciais import GESTACAO_DIAS, LIMITE_SECAGEM_RETROATIVA_DIAS

router = APIRouter(prefix="/animais", tags=["animais"])

# Alias local: a regra em si mora em `rules.producao_leiteira.del_dias_ao_vivo`
# (função pura, sem Session, reaproveitada também por
# `rules.indicadores.calcular_indicadores` para o card "DEL médio" da
# Produção) — mantido para não mexer nas chamadas já existentes neste arquivo.
_del_dias_ao_vivo = del_dias_ao_vivo


def _categoria_ao_vivo(categoria_completa: str | None, categoria_abrev: str | None, ult_parto: date | None, ult_secagem: date | None) -> tuple[str | None, str | None]:
    """Corrige "Novilha ..." para "Vaca ..." quando o app já tem um parto
    lançado para o animal — uma novilha que pariu vira vaca imediatamente, não
    só no próximo upload do GERAL.csv. Só mexe em categorias que ainda dizem
    "novilha" (texto do CSV congelado); categorias que já dizem "vaca" ficam
    intocadas para não perder nuances do texto original do Ideagri que não
    temos como reconstruir aqui (ex.: número da lactação)."""
    if ult_parto is None:
        return categoria_completa, categoria_abrev

    def _corrige(texto: str | None) -> str | None:
        if not texto or "novilha" not in texto.lower():
            return texto
        seca = bool(ult_secagem and ult_secagem >= ult_parto)
        return "Vaca seca" if seca else "Vaca em lactação"

    return _corrige(categoria_completa), _corrige(categoria_abrev)


@router.get("/")
def listar_animais(
    grupo: str | None = Query(None, description="Filtrar por grupo primário"),
    sit_rep: str | None = Query(None, description="Filtrar por situação reprodutiva"),
    ativo: bool = Query(True),
    incluir_machos: bool = Query(False, description="Incluir machos e sêmen (padrão: só fêmeas)"),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Animal).where(Animal.ativo == ativo)
    # Piloto conservador de multi-fazenda: só filtra quando o token carrega
    # uma fazenda selecionada (ver get_fazenda_atual_id) — token sem "fid"
    # (todo login de antes desta mudança) continua vendo tudo, como sempre.
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    if grupo:
        query = query.where(Animal.grupo_primario.contains(grupo))
    if sit_rep:
        query = query.where(Animal.sit_rep == sit_rep)

    animais = session.exec(query).all()
    if not incluir_machos:
        # Rebanho = só fêmeas. Exclui sêmen/reprodutores e machos. Registros
        # antigos (sem o campo) permanecem até o próximo upload do GERAL.
        animais = [a for a in animais if not a.eh_semen and a.sexo != "M"]

    # Datas reprodutivas por matriz: último serviço POSITIVO (concepção), último
    # parto e última secagem. Usadas no front para dias de gestação, dias para
    # o parto, PEV e para corrigir DEL/categoria congelados (ver funções AO
    # VIVO acima).
    query_servico = select(Servico)
    query_parto = select(Parto)
    query_secagem = select(Secagem)
    if fazenda_id is not None:
        query_servico = query_servico.where(Servico.fazenda_id == fazenda_id)
        query_parto = query_parto.where(Parto.fazenda_id == fazenda_id)
        query_secagem = query_secagem.where(Secagem.fazenda_id == fazenda_id)
    servicos_todos = session.exec(query_servico).all()
    partos_todos = session.exec(query_parto).all()
    # Serviço vigente positivo por matriz (não "o último diagnóstico positivo
    # do histórico" cru) — uma vaca reinseminada sem diagnóstico ainda, com a
    # prenhez já perdida, ou que já pariu depois daquele serviço não deve
    # continuar contando "dias de gestação" de uma prenhez que não existe
    # mais (ver fazenda.rules.perda_prenhez).
    ult_pos: dict[str, object] = {
        numero: s.data_servico for numero, s in servicos_positivos_vigentes(servicos_todos, partos_todos).items()
    }
    ult_parto: dict[str, object] = {}
    # Só para `data_ult_parto` (auditoria/histórico): a data do último `Parto`
    # da matriz, QUALQUER tipo — inclusive aborto sem abertura de lactação.
    # "Esta matriz encerrou uma gestação, foi quando?" é uma pergunta
    # diferente de "esta matriz pariu de verdade?" (ver `ult_parto_produtivo`
    # abaixo) — mistura-las aqui faria a data existir mas o resto da tela
    # (DEL/categoria) discordar dela sem motivo aparente para quem só olha
    # este campo isolado.
    ult_parto_produtivo: dict[str, object] = {}
    for p in partos_todos:
        d = p.data_parto
        if d and (p.numero_matriz not in ult_parto or d > ult_parto[p.numero_matriz]):
            ult_parto[p.numero_matriz] = d
        if d and eh_parto_produtivo(p) and (p.numero_matriz not in ult_parto_produtivo or d > ult_parto_produtivo[p.numero_matriz]):
            ult_parto_produtivo[p.numero_matriz] = d
    ult_secagem: dict[str, object] = {}
    for s in session.exec(query_secagem).all():
        d = s.data_secagem
        if d and (s.numero_matriz not in ult_secagem or d > ult_secagem[s.numero_matriz]):
            ult_secagem[s.numero_matriz] = d

    # Produção AO VIVO de cada animal — mesma dupla de funções que o contexto
    # de dieta já usa (ver docstring de `rules.producao_leiteira`): o
    # ControleLeiteiro lançado pelo app quando existe, senão o campo
    # congelado `ult_cl_kg` do CSV do Ideagri (aposentado). UMA consulta para
    # o rebanho inteiro — não uma por animal, que a listagem completa tornaria
    # proibitivo.
    numeros = {a.numero for a in animais}
    producao_ao_vivo = ultimo_controle_por_animal(session, numeros, fazenda_id)

    hoje = date.today()
    # FONTE ÚNICA de "está em lactação" para as telas de lançamento (ver
    # fazenda/rules/lactacao.py): a `Lactacao` aberta hoje. Substitui os dois
    # critérios divergentes que o frontend usava — "o código do lote é
    # 01/02/03" (FormControle) e "del_dias > 0" (campo congelado) —, sendo
    # que o app de campo não filtrava nada e deixava lançar leite de bezerra.
    lactacoes_abertas = lactacoes_abertas_por_matriz(session, numeros, data=hoje, fazenda_id=fazenda_id)

    saida = []
    for a in animais:
        d = a.model_dump()
        sp = ult_pos.get(a.numero)
        pp = ult_parto.get(a.numero)
        pp_produtivo = ult_parto_produtivo.get(a.numero)
        sec = ult_secagem.get(a.numero)
        lact = lactacoes_abertas.get(a.numero)
        d["data_ult_servico_pos"] = sp.isoformat() if sp else None
        d["data_ult_parto"] = pp.isoformat() if pp else None
        d["em_lactacao"] = lact is not None
        d["lactacao_inicio"] = lact.data_inicio.isoformat() if lact else None
        # DEL e categoria usam SÓ o parto produtivo (`pp_produtivo`), nunca o
        # `pp` bruto: um aborto sem abertura de lactação não deve dar DEL
        # nenhum nem virar novilha em vaca (matriz 108, relatado 30/05/2026).
        d["del_dias"] = _del_dias_ao_vivo(d["del_dias"], pp_produtivo, sec, hoje)
        if lact is not None:
            # Com lactação materializada, o DEL sai dela — inclusive nos
            # casos em que `_del_dias_ao_vivo` não tem o que responder
            # (lactação aberta por aborto ou indução, que não têm parto
            # produtivo por trás).
            d["del_dias"] = (hoje - lact.data_inicio).days
        d["categoria_completa"], d["categoria_abrev"] = _categoria_ao_vivo(d["categoria_completa"], d["categoria_abrev"], pp_produtivo, sec)
        producao_kg, producao_data = com_fallback_animal(a.numero, producao_ao_vivo, a)
        d["producao_kg"] = producao_kg
        d["producao_data"] = producao_data.isoformat() if producao_data else None
        if a.numero in producao_ao_vivo:
            d["producao_origem"] = "controle"
        elif producao_kg is not None:
            # `is not None` e não truthiness: uma vaca com `ult_cl_kg` 0,0
            # (registro do CSV de quem já estava seca) tem origem conhecida —
            # é o campo congelado. Dizer `None` ali seria afirmar que não se
            # sabe de onde veio o número, que é justamente o silêncio que
            # esta etapa remove.
            d["producao_origem"] = "congelado"
        else:
            d["producao_origem"] = None
        saida.append(d)
    saida.sort(key=lambda d: chave_numero(d["numero"]))
    return saida


# Lotes de lactação (convenção do sistema, mesma da Produção).
LOTES_LACTACAO = ("01", "02", "03")


def _codigo_lote(g: str | None) -> str | None:
    return g[:2] if g and len(g) >= 2 and g[:2].isdigit() else None


@router.get("/estratificacao")
def estratificacao_rebanho(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Composição do rebanho (fêmeas ativas) por faixa etária e, nas adultas,
    por situação (lactação / secas / pré-parto). Alimenta o gráfico do Rebanho."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje = date.today()
    query_parto = select(Parto)
    query_servico = select(Servico)
    query_animal = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_parto = query_parto.where(Parto.fazenda_id == fazenda_id)
        query_servico = query_servico.where(Servico.fazenda_id == fazenda_id)
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    partos_todos = session.exec(query_parto).all()
    servicos_todos = session.exec(query_servico).all()
    # Só o parto PRODUTIVO decide se a fêmea vira "vaca" no gráfico: uma
    # novilha cujo único `Parto` é um aborto sem abertura de lactação não
    # pariu de verdade (ver fazenda.rules.parto) e deve continuar nos
    # estratos de idade (aleitamento/recria/novilhas), não em vacas_*.
    ult_parto: dict[str, date] = {}
    for p in partos_todos:
        if p.data_parto and eh_parto_produtivo(p) and (p.numero_matriz not in ult_parto or p.data_parto > ult_parto[p.numero_matriz]):
            ult_parto[p.numero_matriz] = p.data_parto
    # Serviço vigente positivo por matriz — mesmo critério de listar_animais
    # acima (ver fazenda.rules.perda_prenhez): não conta uma prenhez já
    # perdida ou já substituída por uma reinseminação sem diagnóstico.
    ult_pos: dict[str, date] = {
        numero: s.data_servico for numero, s in servicos_positivos_vigentes(servicos_todos, partos_todos).items()
    }

    estratos = {
        "aleitamento_0_3m": 0, "recria_4_11m": 0, "recria_12_24m": 0,
        "novilhas_acima_24m": 0, "vacas_lactacao": 0, "vacas_secas": 0, "vacas_pre_parto": 0,
        "sem_data_nasc": 0,
    }
    # Números dos animais de cada estrato — usado pelo front para abrir a
    # janela suspensa de animais ao clicar numa fatia/card da composição.
    numeros: dict[str, list[str]] = {k: [] for k in estratos}
    total = 0
    for a in session.exec(query_animal).all():
        if a.eh_semen or a.sexo == "M":
            continue
        total += 1
        pariu = a.numero in ult_parto
        if pariu:
            # Vaca adulta: lactação (lote 01–03), pré-parto (últimos
            # pre_parto_max dias antes do parto previsto — padrão 30; ver
            # fazenda.rules.parametros e agenda_engine.py, mesma janela usada
            # na Agenda) ou seca (inclui o período seco/Secagem, 31-60 dias).
            gest = (hoje - ult_pos[a.numero]).days if a.numero in ult_pos else None
            limite_pre_parto = GESTACAO_DIAS - pre_parto_max()
            if _codigo_lote(a.grupo_primario) in LOTES_LACTACAO:
                estratos["vacas_lactacao"] += 1
                numeros["vacas_lactacao"].append(a.numero)
            elif gest is not None and gest >= limite_pre_parto:
                estratos["vacas_pre_parto"] += 1
                numeros["vacas_pre_parto"].append(a.numero)
            else:
                estratos["vacas_secas"] += 1
                numeros["vacas_secas"].append(a.numero)
            continue
        # Fêmea que ainda não pariu → classifica por idade.
        if not a.data_nasc:
            estratos["sem_data_nasc"] += 1
            numeros["sem_data_nasc"].append(a.numero)
            continue
        d = (hoje - a.data_nasc).days
        if d <= 90:
            estratos["aleitamento_0_3m"] += 1
            numeros["aleitamento_0_3m"].append(a.numero)
        elif d <= 364:
            estratos["recria_4_11m"] += 1
            numeros["recria_4_11m"].append(a.numero)
        elif d <= 730:
            estratos["recria_12_24m"] += 1
            numeros["recria_12_24m"].append(a.numero)
        else:
            estratos["novilhas_acima_24m"] += 1
            numeros["novilhas_acima_24m"].append(a.numero)

    def pct(n: int) -> float:
        return round(100 * n / total, 1) if total else 0.0

    vacas = estratos["vacas_lactacao"] + estratos["vacas_secas"] + estratos["vacas_pre_parto"]
    return {
        "total": total,
        "estratos": estratos,
        "numeros": numeros,
        "percentuais": {k: pct(v) for k, v in estratos.items()},
        "vacas_total": vacas,
        "numeros_vacas_total": numeros["vacas_lactacao"] + numeros["vacas_secas"] + numeros["vacas_pre_parto"],
        "pct_lactacao_sobre_total": pct(estratos["vacas_lactacao"]),
        "pct_lactacao_sobre_vacas": round(100 * estratos["vacas_lactacao"] / vacas, 1) if vacas else 0.0,
    }


@router.get("/{numero}")
def buscar_animal(
    numero: str, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Animal).where(Animal.numero == numero)
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query).first()
    if not animal:
        raise HTTPException(status_code=404, detail=f"Animal {numero} não encontrado")
    return animal.model_dump()


def _agrupar_protocolos_iatf(session: Session, aplicacoes: list) -> list[dict]:
    """Uma linha por PROTOCOLO (lancamento_id), não por aplicação: as linhas
    de um mesmo protocolo IATF (D0/D7/D9/D11 clássico, ou os dias livres de
    um molde) são um único protocolo. Antes a ficha do animal contava um IATF
    por etapa, distorcendo o histórico reprodutivo."""
    from fazenda.models import ProtocoloIatfLancamento

    por_lancamento: dict[int, list] = {}
    for ap in aplicacoes:
        por_lancamento.setdefault(ap.lancamento_id, []).append(ap)

    linhas: list[dict] = []
    for lancamento_id, aps in por_lancamento.items():
        aps = sorted(aps, key=lambda a: a.dia)
        lancamento = session.get(ProtocoloIatfLancamento, lancamento_id)
        d0 = next((a.data_prevista for a in aps if a.dia == 0), None)
        # Inseminação = etapa de MAIOR dia deste protocolo — não necessariamente
        # D11 (molde com dias livres desloca esse número).
        maior_dia = max((a.dia for a in aps), default=None)
        d11 = next((a.data_prevista for a in aps if a.dia == maior_dia), None) if maior_dia is not None else None
        linhas.append({
            "lancamento_id": lancamento_id,
            "nome_protocolo": lancamento.nome_protocolo if lancamento else "IATF",
            "data_d0": d0.isoformat() if d0 else None,
            "data_inseminacao": d11.isoformat() if d11 else None,
            "responsavel": lancamento.responsavel if lancamento else None,
            "concluido": all(a.realizada for a in aps),
            "etapas_realizadas": sum(1 for a in aps if a.realizada),
            "etapas_total": len(aps),
            # Detalhe dia a dia continua disponível para quem quiser abrir.
            "etapas": [
                {"dia": a.dia, "descricao": a.descricao,
                 "data_prevista": a.data_prevista.isoformat() if a.data_prevista else None,
                 "realizada": a.realizada,
                 "data_realizacao": a.data_realizacao.isoformat() if a.data_realizacao else None}
                for a in aps
            ],
        })
    linhas.sort(key=lambda p: p["data_d0"] or "")
    return linhas


@router.get("/{numero}/ficha")
def ficha_animal(
    numero: str, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Ficha única do animal: absolutamente todos os lançamentos já registrados
    para ele, reunidos em uma resposta — reprodução, parto, colostragem/IgG,
    produção, sanidade, movimentação de lote, compra/baixa e agenda. Serve
    tanto a tela de consulta quanto a exportação em PDF (por maior que fique).

    Isolamento por fazenda: a busca do animal e as tabelas que já têm
    `fazenda_id` (Servico, Parto, ColostragemBezerra, ProtocoloIatfAplicacao,
    Sanidade, ProtocoloSanitarioLancamento, ExameResultado) são filtradas
    abaixo. MovimentoLote, ControleLeiteiro, PesagemCorporal, QualidadeLeite,
    Secagem, AgendaManual, BaixaAnimal, CompraAnimal, VendaAnimal e
    OcorrenciaClinica AINDA NÃO têm a coluna — ficam sem filtro até os
    domínios Lote/Produção/Recria/Sistema serem migrados (ver proposta de
    separação fazenda/empresa, Parte 1.6) — não são um esquecimento, é uma
    lacuna conhecida e documentada.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_animal = select(Animal).where(Animal.numero == numero)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    if not animal:
        raise HTTPException(status_code=404, detail=f"Animal {numero} não encontrado")

    def _dump(rows) -> list[dict]:
        return [r.model_dump() for r in rows]

    query_partos = select(Parto).where(Parto.numero_matriz == numero)
    if fazenda_id is not None:
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
    partos = session.exec(query_partos.order_by(Parto.data_parto)).all()
    # Ordem de parto = SEMPRE a posição cronológica (1º, 2º, 3º…) dentro desta
    # lista, já ordenada por data_parto — nunca o `Parto.ordem_parto` gravado
    # no banco. Esse campo vem do import de CSV (ver parsers/reprodutivo.py) e
    # pode chegar errado ou duplicado (ex.: dois partos do mesmo animal ambos
    # com ordem_parto=1) — confiar nele aqui fazia a vaca aparecer com "1 de 2"
    # duas vezes em vez de "1 de 2" e "2 de 2" (bug relatado para o animal 403).
    # Exibida como "X de N" (N = total de partos do animal) para ficar claro
    # de cara quantos partos o animal já teve ao todo.
    # Abortos aparecem no histórico (são `Parto` desde o endpoint único de
    # encerramento de gestação — ver fazenda/rules/parto.py) mas NÃO entram na
    # contagem "X de N": não são cria. Sem esta separação, uma vaca de 3 crias
    # com um aborto no meio viraria "4 de 4".
    total_partos = sum(1 for p in partos if eh_parto_produtivo(p))
    partos_dump = []
    ordem_corrente = 0
    for p in partos:
        d = p.model_dump()
        # Coluna auxiliar da tabela de Partos da Ficha ("Considerar ordem de
        # parto/lactação?") — mesmo critério de `eh_parto_produtivo` usado
        # acima para "X de N", exposto explicitamente por linha para quem
        # olha o histórico bruto e quer saber, sem fazer conta, se ESTE
        # evento específico contou ou não.
        d["conta_ordem_parto_lactacao"] = eh_parto_produtivo(p)
        if eh_parto_produtivo(p):
            ordem_corrente += 1
            d["ordem_parto"] = f"{ordem_corrente} de {total_partos}"
        else:
            d["ordem_parto"] = "—"
        partos_dump.append(d)
    query_servicos = select(Servico).where(Servico.numero_matriz == numero)
    if fazenda_id is not None:
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
    servicos = session.exec(query_servicos.order_by(Servico.data_servico)).all()
    # Código NAAB do pai (touro/sêmen usado no serviço), buscado no catálogo de
    # sêmen pelo nome do reprodutor — anexado a cada serviço para exibir na ficha.
    estoque_semen_todos = session.exec(select(EstoqueSemen)).all()
    naab_por_touro = {
        s.touro_nome.strip().lower(): s.naab
        for s in estoque_semen_todos if s.naab
    }
    # Sexado/convencional/fazenda por nome do touro — usado como fallback para
    # serviços antigos que não gravaram o tipo_semen no momento da inseminação.
    tipo_semen_por_touro: dict[str, str] = {}
    for s in estoque_semen_todos:
        if s.touro_nome:
            tipo_semen_por_touro.setdefault(s.touro_nome.strip().lower(), s.tipo or "convencional")
    # Banco de touros (provas NAAB/CDCB) — para mostrar nome + provas do pai.
    touros = session.exec(select(Touro)).all()
    touro_por_naab = {(t.naab or "").strip().upper(): t for t in touros}
    touro_por_nome = {(t.nome or "").strip().lower(): t for t in touros if t.nome}
    servicos_dump = []
    for s in servicos:
        d = s.model_dump()
        naab = naab_por_touro.get((s.reprodutor or "").strip().lower())
        d["reprodutor_naab"] = naab
        d["tipo_semen"] = s.tipo_semen or tipo_semen_por_touro.get((s.reprodutor or "").strip().lower())
        # Casa o touro pelo NAAB (ou, na falta, pelo nome do reprodutor).
        touro = (touro_por_naab.get((naab or "").strip().upper())
                 or touro_por_nome.get((s.reprodutor or "").strip().lower()))
        d["touro"] = touro.model_dump() if touro else None
        # Chaves planas para a tabela genérica da ficha (provas do pai).
        d["touro_central"] = touro.central if touro else None
        d["touro_tpi"] = touro.tpi if touro else None
        d["touro_nm"] = touro.nm_dolar if touro else None
        # Ordem de parto ATUAL do animal no momento dessa IA — quantos partos já
        # tinha antes da data do serviço, +1 (ex.: já teve 2 partos → essa IA é
        # a tentativa para o 3º parto). Calculado aqui (não vem do campo
        # Servico.ordem_parto, que só é preenchido pelo import do CSV
        # REPRODUTIVO) para valer também para lançamentos manuais de IA.
        if s.data_servico:
            ordem_alvo = sum(1 for p in partos if p.data_parto and p.data_parto < s.data_servico) + 1
        else:
            ordem_alvo = None
        d["ordem_parto_na_ia"] = ordem_alvo
        # Parto que ESTE serviço deu origem, para a coluna "Parto" da tabela de
        # Serviço/IA e diagnóstico: não há FK Servico→Parto no modelo, então
        # usa a mesma ordem cronológica calculada acima — este serviço mira o
        # parto que ocupa a posição `ordem_alvo` na lista de partos do animal
        # (já ordenada por data). Só é preenchido quando o diagnóstico deste
        # serviço é POSITIVO (regra do card "Parto" na ficha) — None tanto
        # para diagnóstico não positivo quanto para o parto ainda não ter
        # acontecido (frontend distingue "vazio" de "—" pelo próprio
        # `diagnostico`, que já vai no dump).
        diagnostico_positivo = (s.diagnostico or "").strip().upper() == "POSITIVO"
        parto_alvo = (
            partos[ordem_alvo - 1] if diagnostico_positivo and ordem_alvo and ordem_alvo <= total_partos else None
        )
        d["parto_resultante_data"] = parto_alvo.data_parto.isoformat() if parto_alvo and parto_alvo.data_parto else None
        servicos_dump.append(d)

    # Pai deste animal (nome de guerra + NAAB). Prioridade 1: cadastrado
    # manualmente na ficha (Configurações > Cadastro > Animal) — necessário
    # para animais comprados ou anteriores ao uso do sistema, sem serviço/
    # parto da mãe registrados aqui. Prioridade 2 (fallback): não existe FK
    # direta — o animal é a cria de um Parto da mãe, e o pai é o reprodutor
    # do serviço da mãe que mais provavelmente gerou essa gestação (o mais
    # próximo antes do parto, dentro da janela de gestação bovina — ~260 a
    # 295 dias).
    pai = None
    if animal.pai_nome:
        naab = animal.pai_naab or naab_por_touro.get(animal.pai_nome.strip().lower())
        touro_pai = (touro_por_naab.get((naab or "").strip().upper())
                     or touro_por_nome.get(animal.pai_nome.strip().lower()))
        pai = {
            "nome": animal.pai_nome,
            "naab": naab or (touro_pai.naab if touro_pai else None),
            "central": touro_pai.central if touro_pai else None,
            "tpi": touro_pai.tpi if touro_pai else None,
            "nm_dolar": touro_pai.nm_dolar if touro_pai else None,
        }
    query_parto_cria = select(Parto).where((Parto.numero_cria_1 == numero) | (Parto.numero_cria_2 == numero))
    if fazenda_id is not None:
        query_parto_cria = query_parto_cria.where(Parto.fazenda_id == fazenda_id)
    parto_como_cria = session.exec(query_parto_cria).first()
    if pai is None and parto_como_cria and parto_como_cria.data_parto:
        query_servicos_mae = select(Servico).where(Servico.numero_matriz == parto_como_cria.numero_matriz)
        if fazenda_id is not None:
            query_servicos_mae = query_servicos_mae.where(Servico.fazenda_id == fazenda_id)
        servicos_mae = session.exec(query_servicos_mae.order_by(Servico.data_servico)).all()
        candidatos = [
            s for s in servicos_mae
            if s.data_servico and s.reprodutor and 260 <= (parto_como_cria.data_parto - s.data_servico).days <= 295
        ]
        servico_concepcao = candidatos[-1] if candidatos else None
        if servico_concepcao:
            naab = naab_por_touro.get((servico_concepcao.reprodutor or "").strip().lower())
            touro_pai = (touro_por_naab.get((naab or "").strip().upper())
                         or touro_por_nome.get((servico_concepcao.reprodutor or "").strip().lower()))
            pai = {
                "nome": servico_concepcao.reprodutor,
                "naab": naab or (touro_pai.naab if touro_pai else None),
                "central": touro_pai.central if touro_pai else None,
                "tpi": touro_pai.tpi if touro_pai else None,
                "nm_dolar": touro_pai.nm_dolar if touro_pai else None,
            }

    # IATF na ficha: UM protocolo = UMA linha. Antes devolvia as aplicações
    # cruas (D0/D7/D9/D11), então um único protocolo aparecia como 4 IATFs
    # na ficha do animal — inflando o histórico reprodutivo.
    query_protocolos_iatf = select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.numero_matriz == numero)
    if fazenda_id is not None:
        query_protocolos_iatf = query_protocolos_iatf.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
    aplicacoes_iatf = session.exec(query_protocolos_iatf.order_by(ProtocoloIatfAplicacao.data_prevista)).all()
    protocolos_iatf = _agrupar_protocolos_iatf(session, aplicacoes_iatf)

    # MovimentoLote ainda não tem fazenda_id — ver nota no docstring da função.
    movimentos_lote = session.exec(
        select(MovimentoLote).where(MovimentoLote.numero_matriz == numero).order_by(MovimentoLote.data_movimento)
    ).all()

    query_colostragem = select(ColostragemBezerra).where(ColostragemBezerra.numero_animal == numero)
    if fazenda_id is not None:
        query_colostragem = query_colostragem.where(ColostragemBezerra.fazenda_id == fazenda_id)
    colostragem = session.exec(query_colostragem).first()

    query_controles = select(ControleLeiteiro).where(ControleLeiteiro.numero_matriz == numero)
    if fazenda_id is not None:
        query_controles = query_controles.where(ControleLeiteiro.fazenda_id == fazenda_id)
    controles_leiteiros = session.exec(query_controles.order_by(ControleLeiteiro.data_controle)).all()

    query_pesagens = select(PesagemCorporal).where(PesagemCorporal.numero_matriz == numero)
    if fazenda_id is not None:
        query_pesagens = query_pesagens.where(PesagemCorporal.fazenda_id == fazenda_id)
    pesagens_corporais = session.exec(query_pesagens.order_by(PesagemCorporal.data_pesagem)).all()

    query_qualidade = select(QualidadeLeite).where(QualidadeLeite.numero_matriz == numero)
    if fazenda_id is not None:
        query_qualidade = query_qualidade.where(QualidadeLeite.fazenda_id == fazenda_id)
    qualidade_leite = session.exec(query_qualidade.order_by(QualidadeLeite.data_coleta)).all()

    query_sanidade = select(Sanidade).where(Sanidade.numero_matriz == numero)
    if fazenda_id is not None:
        query_sanidade = query_sanidade.where(Sanidade.fazenda_id == fazenda_id)
    aplicacoes_sanitarias = session.exec(query_sanidade.order_by(Sanidade.data_aplicacao)).all()

    query_protocolos_nomes = select(ProtocoloSanitario)
    if fazenda_id is not None:
        query_protocolos_nomes = query_protocolos_nomes.where(ProtocoloSanitario.fazenda_id == fazenda_id)
    protocolos_nomes = {p.id: p.nome for p in session.exec(query_protocolos_nomes).all()}
    query_protocolos_sanitarios = select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.numero_matriz == numero)
    if fazenda_id is not None:
        query_protocolos_sanitarios = query_protocolos_sanitarios.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
    protocolos_sanitarios_rows = session.exec(query_protocolos_sanitarios.order_by(ProtocoloSanitarioLancamento.data_inicio)).all()
    protocolos_sanitarios = [
        {**p.model_dump(), "protocolo_nome": protocolos_nomes.get(p.protocolo_id, "—")} for p in protocolos_sanitarios_rows
    ]

    # Indução de lactação e protocolo customizado — os dois protocolos que
    # nunca tinham entrado na ficha, apesar de já existirem no sistema (um
    # animal em indução ativa não mostrava nada aqui). Mesmo formato das
    # demais seções: uma linha por etapa/dia, com o que foi feito e quando.
    query_inducao = (
        select(ProtocoloInducaoAplicacao, ProtocoloInducaoLancamento)
        .join(ProtocoloInducaoLancamento, ProtocoloInducaoAplicacao.lancamento_id == ProtocoloInducaoLancamento.id)
        .where(ProtocoloInducaoAplicacao.numero_matriz == numero)
    )
    if fazenda_id is not None:
        query_inducao = query_inducao.where(ProtocoloInducaoAplicacao.fazenda_id == fazenda_id)
    inducao_lactacao = [
        {
            "nome_protocolo": lanc.nome_protocolo,
            "dia": ap.dia,
            "descricao": ap.descricao or ap.observacao_manejo or "—",
            "data_prevista": ap.data_prevista.isoformat() if ap.data_prevista else None,
            "realizada": "Sim" if ap.realizada else "Não",
            "data_realizacao": ap.data_realizacao.isoformat() if ap.data_realizacao else None,
        }
        for ap, lanc in sorted(
            session.exec(query_inducao).all(), key=lambda r: (r[0].data_prevista or date.min, r[0].dia)
        )
    ]

    query_custom = (
        select(ProtocoloCustomizadoAplicacao, ProtocoloCustomizadoLancamento)
        .join(ProtocoloCustomizadoLancamento, ProtocoloCustomizadoAplicacao.lancamento_id == ProtocoloCustomizadoLancamento.id)
        .where(ProtocoloCustomizadoAplicacao.numero_matriz == numero)
    )
    if fazenda_id is not None:
        query_custom = query_custom.where(ProtocoloCustomizadoAplicacao.fazenda_id == fazenda_id)
    protocolos_customizados = [
        {
            "nome_protocolo": lanc.nome_protocolo,
            "dia": ap.dia - (lanc.dia_inicial or 0),
            "descricao": ap.descricao or "—",
            "insumo": ap.insumo or "—",
            "data_prevista": ap.data_prevista.isoformat() if ap.data_prevista else None,
            "realizada": "Sim" if ap.realizada else "Não",
            "data_realizacao": ap.data_realizacao.isoformat() if ap.data_realizacao else None,
        }
        for ap, lanc in sorted(
            session.exec(query_custom).all(), key=lambda r: (r[0].data_prevista or date.min, r[0].dia)
        )
    ]

    query_secagens = select(Secagem).where(Secagem.numero_matriz == numero)
    if fazenda_id is not None:
        query_secagens = query_secagens.where(Secagem.fazenda_id == fazenda_id)
    secagens = session.exec(query_secagens.order_by(Secagem.data_secagem)).all()

    query_agenda = select(AgendaManual)
    if fazenda_id is not None:
        query_agenda = query_agenda.where(AgendaManual.fazenda_id.in_((fazenda_id, None)))
    eventos_agenda = [
        e for e in session.exec(query_agenda.order_by(AgendaManual.data_evento)).all()
        if e.numero_animal and numero in [n.strip() for n in e.numero_animal.split(",")]
    ]

    baixa = session.exec(select(BaixaAnimal).where(BaixaAnimal.numero_animal == numero)).first()
    # Rastreabilidade sanitária/GTA: TODAS as compras e vendas do animal (não só
    # a primeira) — um animal pode ter mais de uma GTA ao longo da vida (ex.:
    # comprado e, mais tarde, revendido). `compra` é mantido por compatibilidade
    # (primeira compra registrada); `compras`/`vendas` trazem a lista completa.
    compras = session.exec(select(CompraAnimal).where(CompraAnimal.numero_animal == numero).order_by(CompraAnimal.data_compra)).all()
    vendas = session.exec(select(VendaAnimal).where(VendaAnimal.numero_animal == numero).order_by(VendaAnimal.data_venda)).all()
    compra = compras[0] if compras else None
    gtas = sorted({c.gta for c in compras if c.gta} | {v.gta for v in vendas if v.gta})

    ocorrencias_clinicas = session.exec(
        select(OcorrenciaClinica).where(OcorrenciaClinica.numero_matriz == numero).order_by(OcorrenciaClinica.data_ocorrencia)
    ).all()

    query_eventos_sanitarios = select(EventoSanitario)
    if fazenda_id is not None:
        query_eventos_sanitarios = query_eventos_sanitarios.where(EventoSanitario.fazenda_id == fazenda_id)
    eventos_sanitarios_nomes = {e.id: e.nome for e in session.exec(query_eventos_sanitarios).all()}
    query_exames = select(ExameResultado).where(ExameResultado.numero_matriz == numero)
    if fazenda_id is not None:
        query_exames = query_exames.where(ExameResultado.fazenda_id == fazenda_id)
    exames_resultados_rows = session.exec(query_exames.order_by(ExameResultado.data_exame)).all()
    exames_resultados = [
        {**e.model_dump(), "evento_sanitario_nome": eventos_sanitarios_nomes.get(e.evento_sanitario_id)}
        for e in exames_resultados_rows
    ]

    # Linha do tempo de rastreabilidade sanitária: todos os eventos com
    # relevância sanitária/documental (GTA de compra/venda, aplicações,
    # protocolos, exames, doenças e baixa) numa única lista cronológica —
    # responde "esse animal, com essa GTA, teve qual histórico sanitário?"
    # sem precisar cruzar seção por seção.
    linha_tempo_sanitaria: list[dict] = []
    for c in compras:
        linha_tempo_sanitaria.append({
            "data": c.data_compra, "tipo_evento": "Compra", "descricao": f"Compra de {c.vendedor}",
            "gta": c.gta, "responsavel": c.responsavel,
        })
    for v in vendas:
        linha_tempo_sanitaria.append({
            "data": v.data_venda, "tipo_evento": "Venda", "descricao": f"Venda para {v.comprador}",
            "gta": v.gta, "responsavel": v.responsavel,
        })
    for s in aplicacoes_sanitarias:
        linha_tempo_sanitaria.append({
            "data": s.data_aplicacao, "tipo_evento": "Aplicação sanitária", "descricao": s.produto,
            "gta": None, "responsavel": s.responsavel,
        })
    for p in protocolos_sanitarios_rows:
        linha_tempo_sanitaria.append({
            "data": p.data_inicio, "tipo_evento": "Protocolo sanitário",
            "descricao": protocolos_nomes.get(p.protocolo_id, "—"), "gta": None, "responsavel": p.responsavel,
        })
    for e in exames_resultados:
        linha_tempo_sanitaria.append({
            "data": e["data_exame"], "tipo_evento": "Exame", "descricao": e.get("evento_sanitario_nome") or "—",
            "gta": None, "responsavel": e.get("veterinario"),
        })
    for o in ocorrencias_clinicas:
        linha_tempo_sanitaria.append({
            "data": o.data_ocorrencia, "tipo_evento": "Doença (ocorrência clínica)", "descricao": o.doenca,
            "gta": None, "responsavel": None,
        })
    if baixa:
        linha_tempo_sanitaria.append({
            "data": baixa.data_baixa, "tipo_evento": "Baixa", "descricao": f"{baixa.tipo_baixa} — {baixa.motivo}",
            "gta": None, "responsavel": baixa.responsavel,
        })
    linha_tempo_sanitaria.sort(key=lambda e: e["data"] or date.min)

    # DEL AO VIVO (ver _del_dias_ao_vivo no topo do arquivo) — precisa ser
    # calculado ANTES da previsão de secagem logo abaixo, que decide se o
    # animal "está em lactação" a partir dele. `Animal.del_dias` fica
    # congelado no valor do último GERAL.csv (zerado no instante do parto
    # lançado no app, mas nunca atualizado por uma Secagem lançada depois) —
    # usar o valor cru aqui fazia um animal recém-parido pelo app nunca
    # ganhar previsão de secagem, e um animal recém-secado pelo app nunca
    # perder a previsão (ver auditoria ago/2026).
    # `ultimo_parto_data` (QUALQUER `Parto`, inclusive aborto sem lactação) só
    # serve para decidir se uma gestação "acabou" — usado abaixo no filtro de
    # `servicos_positivos` ("gestação em curso" é o serviço positivo posterior
    # ao último fim de gestação, seja qual for o tipo). Já `del_dias_vivo` e a
    # categoria ao vivo (mais abaixo) precisam do parto PRODUTIVO: um aborto
    # sem abertura de lactação não é "esta matriz pariu", e não deve zerar/
    # mover o DEL nem virar novilha em vaca (matriz 108, relatado 30/05/2026 —
    # mesmo bug de `listar_animais`, ver `ult_parto_produtivo` lá).
    ultimo_parto_data = partos_dump[-1]["data_parto"] if partos_dump else None
    ultimo_parto_produtivo_data = next(
        (p["data_parto"] for p in reversed(partos_dump) if p["conta_ordem_parto_lactacao"]), None,
    )
    ultima_secagem_data = secagens[-1].data_secagem if secagens else None
    del_dias_vivo = _del_dias_ao_vivo(animal.del_dias, ultimo_parto_produtivo_data, ultima_secagem_data, date.today())

    # Previsão de parto / secagem: gestação em curso = último serviço positivo
    # (sem perda registrada) posterior ao último parto — mesma regra usada nas
    # Listas de manejo (relatorios_gerenciais), aqui aplicada a um único animal.
    previsao_parto = None
    previsao_secagem = None
    servicos_positivos = [
        s for s in servicos
        if (s.diagnostico or "").strip().upper() == "POSITIVO" and not s.data_perda_prenhez
        and s.data_servico and (not ultimo_parto_data or s.data_servico > ultimo_parto_data)
    ]
    if servicos_positivos:
        concepcao = servicos_positivos[-1].data_servico
        # Gestação da raça DESTE animal (Holandês 280, Girolando 287,
        # Gir/Zebu 295) — usar 280 para todos previa o parto de um Gir 15 dias
        # antes do real, e arrastava a secagem junto.
        gestacao_do_animal = dias_gestacao_da_raca(animal.raca, GESTACAO_DIAS)
        previsao_parto = concepcao + timedelta(days=gestacao_do_animal)
        if (del_dias_vivo or 0) > 0:
            seco = int(get_param("periodo_seco_dias", 60) or 60)
            previsao_secagem = concepcao + timedelta(days=gestacao_do_animal - seco)
            # Atraso implausível (parto/secagem que não foi lançado a tempo,
            # ver LIMITE_SECAGEM_RETROATIVA_DIAS) — mostra a data em que
            # deveria ter secado (60 dias antes do último parto PRODUTIVO,
            # que é quem abriu a lactação em aberto) em vez da projeção de
            # gestação, sem seguir cobrando retroativo.
            if (date.today() - previsao_secagem).days > LIMITE_SECAGEM_RETROATIVA_DIAS and ultimo_parto_produtivo_data:
                previsao_secagem = ultimo_parto_produtivo_data - timedelta(days=seco)

    # Card "Precisão de parto": só existe com gestação em aberto (mesma
    # condição de `servicos_positivos` acima — último serviço com diagnóstico
    # positivo, sem perda, posterior ao último parto). Reaproveita `concepcao`/
    # `previsao_parto` já calculados acima em vez de duplicar a lógica.
    precisao_parto = None
    if servicos_positivos:
        ultimo_positivo = servicos_positivos[-1]
        precisao_parto = {
            "data_ultima_ia_positiva": ultimo_positivo.data_servico,
            "data_confirmacao_prenhez": ultimo_positivo.data_diagnostico,
            "dias_gestacao": (date.today() - ultimo_positivo.data_servico).days,
            "data_parto_provavel": previsao_parto,
            "dias_para_parto": (previsao_parto - date.today()).days,
        }

    # Categoria AO VIVO (ver _categoria_ao_vivo no topo do arquivo) — mesma
    # ideia do del_dias_vivo calculado acima, para o texto de categoria.
    animal_dump = animal.model_dump()
    animal_dump["del_dias"] = del_dias_vivo
    animal_dump["categoria_completa"], animal_dump["categoria_abrev"] = _categoria_ao_vivo(
        animal_dump["categoria_completa"], animal_dump["categoria_abrev"], ultimo_parto_produtivo_data, ultima_secagem_data,
    )

    # Mãe: prioridade 1 é o cadastro manual (Animal.mae_numero, preenchido em
    # Configurações > Cadastro > Animal); fallback é o vínculo real de
    # parentesco — o Parto que lista este animal como cria (`parto_como_cria`,
    # já buscado acima para achar o pai) tem `numero_matriz`, que É a mãe. Sem
    # este fallback, um animal nascido de um Parto lançado no sistema (sem
    # ninguém preencher o cadastro manual depois) nunca mostrava a mãe na
    # ficha — nem na versão de mesa, nem no app de campo — apesar do vínculo
    # já existir nos dados.
    if not animal_dump.get("mae_numero") and parto_como_cria:
        animal_dump["mae_numero"] = parto_como_cria.numero_matriz
        if not animal_dump.get("mae_nome"):
            query_mae = select(Animal).where(Animal.numero == parto_como_cria.numero_matriz)
            if fazenda_id is not None:
                query_mae = query_mae.where(Animal.fazenda_id == fazenda_id)
            mae_animal = session.exec(query_mae).first()
            if mae_animal and mae_animal.nome:
                animal_dump["mae_nome"] = mae_animal.nome

    # Quadro "por parto" — o que se quer ver "se fosse comprar este animal":
    # produção, duração da lactação, tentativas de emprenhar e DEL de
    # concepção, por lactação (ver fazenda.rules.parto_resumo).
    # Só partos PRODUTIVOS: o quadro numera as lactações por posição na lista
    # (1ª, 2ª, 3ª…), então incluir um aborto deslocaria a numeração de todas
    # as lactações seguintes da matriz.
    resumo_partos = resumo_por_parto(
        [
            {
                "data_parto": p.data_parto,
                "tipo_parto": p.tipo_parto,
                "numero_cria_1": p.numero_cria_1,
                "numero_cria_2": p.numero_cria_2,
                "gemelar": p.gemelar,
            }
            for p in partos if eh_parto_produtivo(p)
        ],
        [{"data_controle": c.data_controle, "producao_kg": c.producao_kg} for c in controles_leiteiros],
        [{"data_secagem": s.data_secagem} for s in secagens],
        [{"data_servico": s.data_servico, "diagnostico": s.diagnostico, "ordem_tentativa": s.ordem_tentativa} for s in servicos],
    )
    # "Última cria" da Ficha (área de identificação) — o campo `cria` do
    # último parto produtivo, mesma regra do quadro (S/N sem número lançado,
    # vazio se natimorto). Derivado daqui em vez de recalculado no frontend
    # para não duplicar a lógica em dois lugares (desktop e mobile).
    ultima_cria = resumo_partos[-1]["cria"] if resumo_partos else ""

    return {
        "animal": animal_dump,
        "pai": pai,
        "previsao_parto": previsao_parto,
        "previsao_secagem": previsao_secagem,
        "precisao_parto": precisao_parto,
        "partos": partos_dump,
        "resumo_partos": resumo_partos,
        "ultima_cria": ultima_cria,
        "servicos": servicos_dump,
        # Já vem agrupado por protocolo (dicts prontos), não passa por _dump.
        "protocolos_iatf": protocolos_iatf,
        "movimentos_lote": _dump(movimentos_lote),
        "colostragem": colostragem.model_dump() if colostragem else None,
        "controles_leiteiros": _dump(controles_leiteiros),
        "pesagens_corporais": _dump(pesagens_corporais),
        "qualidade_leite": _dump(qualidade_leite),
        "aplicacoes_sanitarias": _dump(aplicacoes_sanitarias),
        "protocolos_sanitarios": protocolos_sanitarios,
        "inducao_lactacao": inducao_lactacao,
        "protocolos_customizados": protocolos_customizados,
        "secagens": _dump(secagens),
        "eventos_agenda": _dump(eventos_agenda),
        "baixa": baixa.model_dump() if baixa else None,
        "compra": compra.model_dump() if compra else None,
        "compras": _dump(compras),
        "vendas": _dump(vendas),
        "gtas": gtas,
        "ocorrencias_clinicas": _dump(ocorrencias_clinicas),
        "exames_resultados": exames_resultados,
        "linha_tempo_sanitaria": linha_tempo_sanitaria,
        # Curva média do rebanho por faixa de DEL — é a referência que a
        # "Curva de lactação" da ficha desenha por trás dos pontos do animal,
        # para responder "esta vaca está acima ou abaixo do padrão da casa?".
        # Reusa `rules.producao.calcular_producao`, o mesmo cálculo da tela de
        # Produção, em vez de inventar um modelo teórico à parte.
        "curva_referencia_rebanho": _curva_referencia_rebanho(session, fazenda_id),
        # Curva de Wood ajustada aos pontos REAIS deste animal (ver
        # fazenda.rules.curva_wood) — trajetória esperada da lactação DELE,
        # e projeção da cauda quando a lactação ainda está em aberto. None
        # quando não há controle leiteiro suficiente para um ajuste com
        # sentido (ver PONTOS_MINIMOS_AJUSTE no módulo).
        "curva_wood": _curva_wood_do_animal(controles_leiteiros),
        # Referência mais fina que `curva_referencia_rebanho`: só vacas na
        # MESMA ordem de parto do animal (ex.: só outras de 3ª cria), não o
        # rebanho inteiro. None quando o próprio animal nunca pariu ou não
        # há outras vacas no mesmo grupo com controle suficiente.
        "curva_referencia_grupo_ordem_parto": _curva_referencia_grupo_ordem_parto(
            session, fazenda_id, total_partos,
        ),
    }


def _curva_wood_do_animal(controles_leiteiros) -> list[dict] | None:
    """Extrai (DEL, kg) dos controles leiteiros do animal e ajusta a curva de
    Wood (ver fazenda.rules.curva_wood.ajustar_curva_wood). Devolve só a
    série de pontos prontos para desenhar — a/b/c ficam internos ao módulo de
    regras, não fazem parte do contrato da ficha."""
    from fazenda.rules.curva_wood import ajustar_curva_wood

    pontos = [
        (c.del_no_controle, c.producao_kg) for c in controles_leiteiros
        if c.del_no_controle is not None and c.producao_kg is not None
    ]
    ajuste = ajustar_curva_wood(pontos)
    return ajuste["pontos"] if ajuste else None


def _curva_referencia_grupo_ordem_parto(
    session: Session, fazenda_id: int | None, ordem_parto_animal: int,
) -> list[dict] | None:
    """Produção média por faixa de DEL, só de vacas na MESMA ordem de parto
    do animal em questão — recorte mais fino que `_curva_referencia_rebanho`,
    que mistura primípara com vaca de 5ª cria. Mesmo cálculo de
    `rules.producao.calcular_producao`, aplicado a um subconjunto de
    controles.

    A ordem de parto de CADA controle é a posição cronológica (1º, 2º, 3º…)
    do parto produtivo mais recente até a data daquele controle — mesmo
    critério de `total_partos`/`ordem_parto` usado no resto desta ficha (ver
    docstring de `ficha_animal`), não o campo `Parto.ordem_parto` gravado no
    banco (pode vir errado do CSV). Um controle anterior a qualquer parto do
    seu animal (ordem 0) fica sem ordem de parto conhecida e é EXCLUÍDO do
    agrupamento — não entra por engano no grupo de primípara.

    None quando o próprio animal nunca teve parto produtivo (sem ordem_parto
    para comparar) ou quando não sobra nenhum controle de outra vaca no
    mesmo grupo.
    """
    if not ordem_parto_animal:
        return None

    from fazenda.rules.parto import eh_parto_produtivo
    from fazenda.rules.producao import calcular_producao

    query_partos = select(Parto)
    query_controles = select(ControleLeiteiro)
    if fazenda_id is not None:
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
        query_controles = query_controles.where(ControleLeiteiro.fazenda_id == fazenda_id)

    partos_produtivos_por_matriz: dict[str, list[date]] = {}
    for p in session.exec(query_partos).all():
        if eh_parto_produtivo(p) and p.data_parto:
            partos_produtivos_por_matriz.setdefault(p.numero_matriz, []).append(p.data_parto)
    for datas in partos_produtivos_por_matriz.values():
        datas.sort()

    controles_do_grupo = []
    for c in session.exec(query_controles).all():
        if not c.data_controle:
            continue
        datas_parto = partos_produtivos_por_matriz.get(c.numero_matriz)
        if not datas_parto:
            continue  # animal sem ordem de parto conhecida — fora do agrupamento
        ordem_no_controle = sum(1 for d in datas_parto if d <= c.data_controle)
        if ordem_no_controle == 0 or ordem_no_controle != ordem_parto_animal:
            continue
        controles_do_grupo.append({
            "numero_matriz": c.numero_matriz,
            "data_controle": c.data_controle,
            "producao_kg": c.producao_kg,
            "del_no_controle": c.del_no_controle,
        })

    if not controles_do_grupo:
        return None
    curva = calcular_producao(controles_do_grupo)["curva_lactacao"]
    return curva or None


def _curva_referencia_rebanho(session: Session, fazenda_id: int | None) -> list[dict]:
    """Produção média do rebanho por faixa de DEL (0-30, 31-60, ...).

    Vazia quando ainda não há controle leiteiro suficiente — a ficha
    simplesmente não desenha a linha de referência nesse caso.
    """
    from fazenda.rules.producao import calcular_producao

    query = select(ControleLeiteiro)
    if fazenda_id is not None:
        query = query.where(ControleLeiteiro.fazenda_id == fazenda_id)
    controles = [
        {
            "numero_matriz": c.numero_matriz,
            "data_controle": c.data_controle,
            "producao_kg": c.producao_kg,
            "del_no_controle": c.del_no_controle,
        }
        for c in session.exec(query).all()
    ]
    return calcular_producao(controles)["curva_lactacao"]
