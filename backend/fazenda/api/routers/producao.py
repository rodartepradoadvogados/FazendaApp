"""
Router de produção — indicadores do histórico de controle leiteiro e
lançamento de pesagens (por vaca ou por lote inteiro, de uma vez).
"""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.lotes import _codigo_do_grupo, _mesmo_codigo, coletar_dados_criterios
from fazenda.auth import exigir_admin, get_current_user
from fazenda.database import get_session
from fazenda.models import (
    Animal, AplicacaoAgendada, ContaGerencial, ControleLeiteiro, Dieta, DietaLancamento, EntregaLeiteMensal, Estoque,
    FaixaBonificacaoQualidade, LancamentoItem, Lote, ParametroFazenda,
    Parto, PesagemCorporal, ProtocoloInducaoAplicacao, ProtocoloInducaoLactacao, ProtocoloInducaoLactacaoEtapa,
    ProtocoloInducaoLancamento, ProtocoloInducaoMedicamento, QualidadeLeite, Sanidade, Secagem, Servico, Usuario,
)
from fazenda.ordenacao import chave_numero
from fazenda.parsers.utils import iter_planilha_rows, normalizar_cabecalho, parse_date, parse_float, valor_por_apelido
from fazenda.rules.alimentacao import calcular_consumo
from fazenda.rules.auditoria import mapa_usuarios
from fazenda.rules.bonificacao_qualidade import INDICADORES_BONIFICAVEIS, calcular_bonificacao
from fazenda.rules.dry_off import calcular_secagem
from fazenda.rules.gestation import calcular_parto_provavel
from fazenda.rules.lote_criterios import animal_atende_criterios, lote_tem_criterio
from fazenda.rules.planilha_modelo import gerar_modelo_xlsx
from fazenda.rules.producao import calcular_producao
from fazenda.rules.unidades import pode_dar_baixa_direta, unidades_compativeis

router = APIRouter(prefix="/producao", tags=["producao"])

MOTIVOS_SECAGEM = ["doente", "baixa_producao", "comportamento", "mastite", "casco", "rotina", "outros"]


def _usuario_id_seguro(user: Usuario) -> int | None:
    """Resolve o id do usuário logado para o carimbo de auditoria.

    Estas funções de criação também são chamadas diretamente (fora do ciclo
    de requisição do FastAPI) pela importação de CSV (importar.py) e pelos
    fluxos do bot do Telegram (telegram_fluxos.py), passando só `dados` e
    `session` — nesses casos `user` fica com o valor padrão não resolvido
    (`Depends(...)`), não uma instância real de `Usuario`. Sem usuário real,
    não há quem carimbar.
    """
    return user.id if isinstance(user, Usuario) else None


class OrdenhaIn(BaseModel):
    numero_matriz: str
    # Cada posição é a ordenha correspondente (1ª/2ª/3ª); `None` significa
    # "não ordenhou"/"não lançou" nessa posição — distinto de `0` (ordenhou e
    # deu zero) — para não puxar as médias de ordenha para baixo com um valor
    # que não foi realmente medido.
    ordenhas: list[float | None] = []
    # Se preenchido, grava só o total do dia (sem quebrar em ordenha1/2/3) —
    # usado quando a planilha/lançamento só informa o total, sem detalhar por
    # ordenha; nesse caso `ordenhas` fica vazio e os relatórios que abrem por
    # ordenha simplesmente não têm o que mostrar para esse registro.
    total_kg: float | None = None


class ControlesIn(BaseModel):
    data_controle: date
    entradas: list[OrdenhaIn]


@router.get("/")
def obter_producao(session: Session = Depends(get_session)) -> dict:
    """Série temporal, curva de lactação e ranking por vaca do controle leiteiro."""
    controles = [c.model_dump() for c in session.exec(select(ControleLeiteiro)).all()]
    return calcular_producao(controles)


@router.get("/controles")
def listar_controles(session: Session = Depends(get_session)) -> dict:
    """Registros de controle leiteiro achatados para o dashboard interativo."""
    animais_cadastro = session.exec(select(Animal)).all()
    grupo_por_numero = {a.numero: a.grupo_primario for a in animais_cadastro}
    # Raça sempre a do cadastro do animal (nunca a copiada/congelada no controle
    # leiteiro, que pode estar desatualizada ou vir de texto livre de CSV antigo).
    raca_por_numero = {a.numero: a.raca for a in animais_cadastro}
    # Ordem de parto por animal derivada do nº de partos, para preencher os
    # controles cuja ordem veio vazia (o primeiro parto é sempre "1").
    partos_por_numero: dict[str, int] = {}
    for p in session.exec(select(Parto)).all():
        partos_por_numero[p.numero_matriz] = partos_por_numero.get(p.numero_matriz, 0) + 1
    controles = session.exec(select(ControleLeiteiro)).all()
    nomes = mapa_usuarios(session, {c.usuario_id for c in controles})
    registros = []
    for c in controles:
        d = c.data_controle
        ordem = c.ordem_parto or partos_por_numero.get(c.numero_matriz) or None
        registros.append({
            "numero": c.numero_matriz,
            "raca": raca_por_numero.get(c.numero_matriz) or "",
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "producao_kg": c.producao_kg,
            "del": c.del_no_controle,
            "ordem_parto": ordem,
            "data_ult_parto": c.data_ult_parto.isoformat() if c.data_ult_parto else None,
            "ordenha1_kg": c.ordenha1_kg,
            "ordenha2_kg": c.ordenha2_kg,
            "ordenha3_kg": c.ordenha3_kg,
            "grupo_primario": grupo_por_numero.get(c.numero_matriz),  # lote atual do animal (não histórico)
            "usuario_nome": nomes.get(c.usuario_id),
        })
    return {"controles": registros, "total": len(registros)}


@router.post("/controles")
def criar_controles(
    dados: ControlesIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    """
    Registra a pesagem do dia para uma ou várias vacas de uma vez (lançamento
    individual ou em lote — o front manda uma entrada por vaca do lote).
    """
    usuario_id = _usuario_id_seguro(user)
    criados = []
    for entrada in dados.entradas:
        if entrada.total_kg is not None:
            producao_kg = round(entrada.total_kg, 2)
            o1 = o2 = o3 = None
        elif entrada.ordenhas and any(v for v in entrada.ordenhas if v is not None):
            ordenhas = entrada.ordenhas
            producao_kg = round(sum(v for v in ordenhas if v is not None), 2)
            o1 = ordenhas[0] if len(ordenhas) > 0 else None
            o2 = ordenhas[1] if len(ordenhas) > 1 else None
            o3 = ordenhas[2] if len(ordenhas) > 2 else None
        else:
            continue
        animal = session.exec(select(Animal).where(Animal.numero == entrada.numero_matriz)).first()
        registro = ControleLeiteiro(
            animal_id=animal.id if animal else None,
            numero_matriz=entrada.numero_matriz,
            raca=animal.raca if animal else None,
            data_controle=dados.data_controle,
            producao_kg=producao_kg,
            del_no_controle=animal.del_dias if animal else None,
            ordenha1_kg=o1,
            ordenha2_kg=o2,
            ordenha3_kg=o3,
            usuario_id=usuario_id,
        )
        session.add(registro)
        criados.append(registro)
    session.commit()
    return {"criados": len(criados)}


# ---------------------------------------------------------------------------
# Importação de planilha (Excel ou CSV) de controle leiteiro — usada direto na
# tela de Lançamentos (não é a mesma coisa da CSV genérica de Configurações >
# Importar dados). O sistema identifica sozinho, pelo cabeçalho, se a planilha
# é "por animal" (coluna número) ou "por lote" (coluna lote, sem número
# individual — a pesagem do lote é distribuída igualmente entre os animais
# hoje naquele lote e grava um ControleLeiteiro por vaca, igual ao lançamento
# manual "em lote" já existente — nenhuma tabela/relatório precisa mudar).
# ---------------------------------------------------------------------------
CONTROLE_LEITEIRO_APELIDOS = {
    "numero_matriz": ["numero", "numero matriz", "no", "n", "vaca", "animal", "brinco", "id"],
    "lote": ["lote", "grupo", "pen", "curral"],
    "data_controle": ["data", "data controle", "data do controle"],
    "ordenha1_kg": ["primeira ordenha kg", "1 ordenha kg", "ordenha1 kg", "ordenha1"],
    "ordenha2_kg": ["segunda ordenha kg", "2 ordenha kg", "ordenha2 kg", "ordenha2"],
    "ordenha3_kg": ["terceira ordenha kg", "3 ordenha kg", "ordenha3 kg", "ordenha3"],
    # Fallback: se nenhuma ordenha individual vier preenchida, usa o total do
    # dia — grava só a soma, sem quebrar por ordenha (relatórios que abrem por
    # ordenha não têm o que mostrar para essa linha, e é isso mesmo).
    "total_kg": ["total", "total kg", "total do dia", "producao total", "producao total kg"],
}
MODELO_CONTROLE_LEITEIRO_ANIMAL = {
    "colunas": ["Número", "Data", "Primeira ordenha (kg)", "Segunda ordenha (kg)", "Terceira ordenha (kg)", "Total"],
    "exemplo": ["464", "05/07/2026", "14,5", "13,0", "", "27,5"],
}
MODELO_CONTROLE_LEITEIRO_LOTE = {
    "colunas": ["Lote", "Data", "Primeira ordenha (kg)", "Segunda ordenha (kg)", "Terceira ordenha (kg)", "Total"],
    "exemplo": ["01 - Lactação Alta", "05/07/2026", "320,0", "290,0", "", "610,0"],
}


def _xlsx_response(colunas: list[str], exemplo: list[str], aba: str, nome_arquivo: str) -> Response:
    conteudo = gerar_modelo_xlsx(colunas, exemplo, aba=aba)
    return Response(
        content=conteudo,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome_arquivo}"'},
    )


@router.get("/controle-leiteiro/modelo-excel")
def modelo_excel_controle_leiteiro(modo: str = "animal") -> Response:
    modelo = MODELO_CONTROLE_LEITEIRO_LOTE if modo == "lote" else MODELO_CONTROLE_LEITEIRO_ANIMAL
    nome = "modelo_controle_leiteiro_lote.xlsx" if modo == "lote" else "modelo_controle_leiteiro_animal.xlsx"
    return _xlsx_response(modelo["colunas"], modelo["exemplo"], "Controle leiteiro", nome)


def _resolver_lote(session: Session, valor: str) -> Lote | None:
    valor = (valor or "").strip()
    if not valor:
        return None
    codigo_extraido = _codigo_do_grupo(valor) or valor
    lotes = session.exec(select(Lote)).all()
    for l in lotes:
        if _mesmo_codigo(l.codigo, codigo_extraido):
            return l
    valor_norm = valor.lower()
    for l in lotes:
        if l.nome.lower() == valor_norm:
            return l
    return None


@router.post("/controle-leiteiro/importar")
async def importar_controle_leiteiro(
    file: UploadFile, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    content = await file.read()
    linhas = list(iter_planilha_rows(file.filename or "", content))
    if not linhas:
        return {"criados": 0, "erros": ["Planilha vazia ou em formato não reconhecido."]}

    linhas_norm = [{normalizar_cabecalho(k): v for k, v in row.items()} for row in linhas]
    cabecalho_norm = set(linhas_norm[0].keys())
    tem_numero = any(a in cabecalho_norm for a in CONTROLE_LEITEIRO_APELIDOS["numero_matriz"])
    tem_lote = any(a in cabecalho_norm for a in CONTROLE_LEITEIRO_APELIDOS["lote"])
    if not tem_numero and not tem_lote:
        raise HTTPException(
            status_code=400,
            detail='Não identifiquei o tipo da planilha — inclua uma coluna "Número" (lançamento por animal) '
                   'ou "Lote" (lançamento por lote).',
        )

    erros: list[str] = []
    por_data: dict[date, list[OrdenhaIn]] = {}

    def _ordenhas_ou_total(row_norm: dict) -> tuple[list[float | None], float | None] | None:
        o1 = parse_float(valor_por_apelido(row_norm, CONTROLE_LEITEIRO_APELIDOS["ordenha1_kg"]))
        o2 = parse_float(valor_por_apelido(row_norm, CONTROLE_LEITEIRO_APELIDOS["ordenha2_kg"]))
        o3 = parse_float(valor_por_apelido(row_norm, CONTROLE_LEITEIRO_APELIDOS["ordenha3_kg"]))
        if o1 is not None or o2 is not None or o3 is not None:
            return ([o1, o2, o3] if o3 is not None else [o1, o2]), None
        total = parse_float(valor_por_apelido(row_norm, CONTROLE_LEITEIRO_APELIDOS["total_kg"]))
        return ([], total) if total is not None else None

    if tem_numero:
        for i, row_norm in enumerate(linhas_norm, start=2):
            numero = valor_por_apelido(row_norm, CONTROLE_LEITEIRO_APELIDOS["numero_matriz"]).strip()
            data_linha = parse_date(valor_por_apelido(row_norm, CONTROLE_LEITEIRO_APELIDOS["data_controle"]))
            resultado = _ordenhas_ou_total(row_norm)
            if not numero or not data_linha or resultado is None:
                erros.append(f"Linha {i}: número, data e ao menos uma ordenha (ou o total) são obrigatórios.")
                continue
            ordenhas, total = resultado
            por_data.setdefault(data_linha, []).append(OrdenhaIn(numero_matriz=numero, ordenhas=ordenhas, total_kg=total))
    else:
        for i, row_norm in enumerate(linhas_norm, start=2):
            lote_valor = valor_por_apelido(row_norm, CONTROLE_LEITEIRO_APELIDOS["lote"]).strip()
            data_linha = parse_date(valor_por_apelido(row_norm, CONTROLE_LEITEIRO_APELIDOS["data_controle"]))
            resultado = _ordenhas_ou_total(row_norm)
            if not lote_valor or not data_linha or resultado is None:
                erros.append(f"Linha {i}: lote, data e ao menos uma ordenha (ou o total) são obrigatórios.")
                continue
            ordenhas, total = resultado
            lote = _resolver_lote(session, lote_valor)
            if not lote:
                erros.append(f'Linha {i}: lote "{lote_valor}" não encontrado no cadastro.')
                continue
            rotulo = f"{lote.codigo} - {lote.nome}"
            animais_lote = session.exec(select(Animal).where(Animal.grupo_primario == rotulo)).all()
            if not animais_lote:
                erros.append(f'Linha {i}: lote "{lote_valor}" não tem nenhum animal no momento — pesagem não distribuída.')
                continue
            n = len(animais_lote)
            if total is not None:
                total_por_vaca = round(total / n, 2)
                for a in animais_lote:
                    por_data.setdefault(data_linha, []).append(OrdenhaIn(numero_matriz=a.numero, total_kg=total_por_vaca))
            else:
                ordenhas_por_vaca = [round(v / n, 2) if v is not None else None for v in ordenhas]
                for a in animais_lote:
                    por_data.setdefault(data_linha, []).append(OrdenhaIn(numero_matriz=a.numero, ordenhas=ordenhas_por_vaca))

    criados = 0
    for dia, entradas in por_data.items():
        resultado = criar_controles(ControlesIn(data_controle=dia, entradas=entradas), session, user)
        criados += resultado["criados"]
    return {"criados": criados, "erros": erros, "modo": "animal" if tem_numero else "lote"}


class PesoIn(BaseModel):
    numero_matriz: str
    peso_kg: float


class PesagensIn(BaseModel):
    data_pesagem: date
    entradas: list[PesoIn]


def _fase_transicao(session: Session, animal: "Animal | None", data_pesagem: date) -> str | None:
    """Classifica a vaca na data da pesagem para os pesos de transição:
    pré-parto (<=30 dias do parto previsto), vaca seca (31-60 dias antes) ou
    pós-parto (recém-parida). Fora disso (ou recria), retorna None."""
    if not animal:
        return None
    from fazenda.models import Servico
    from fazenda.rules.gestation import calcular_parto_provavel
    # Recém-parida: DEL pequeno na data da pesagem → pós-parto.
    if animal.del_dias is not None and 0 <= animal.del_dias <= 30:
        return "pos_parto"
    ultimo_pos = session.exec(
        select(Servico).where(
            Servico.numero_matriz == animal.numero, Servico.diagnostico == "POSITIVO"
        ).order_by(Servico.data_servico.desc())
    ).first()
    if ultimo_pos and ultimo_pos.data_servico:
        parto_provavel = calcular_parto_provavel(ultimo_pos.data_servico, animal.raca).data_parto_provavel
        dias_para_parto = (parto_provavel - data_pesagem).days
        if 0 <= dias_para_parto <= 30:
            return "pre_parto"
        if 31 <= dias_para_parto <= 60:
            return "vaca_seca"
    return None


@router.post("/pesagens")
def criar_pesagens(
    dados: PesagensIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    """Registra a pesagem corporal do dia para uma ou várias vacas de uma vez."""
    usuario_id = _usuario_id_seguro(user)
    criados = []
    for entrada in dados.entradas:
        if not entrada.peso_kg:
            continue
        animal = session.exec(select(Animal).where(Animal.numero == entrada.numero_matriz)).first()
        registro = PesagemCorporal(
            numero_matriz=entrada.numero_matriz,
            data_pesagem=dados.data_pesagem,
            peso_kg=entrada.peso_kg,
            del_dias=animal.del_dias if animal else None,
            idade_meses=animal.idade_meses if animal else None,
            grupo_primario=animal.grupo_primario if animal else None,
            fase=_fase_transicao(session, animal, dados.data_pesagem),
            usuario_id=usuario_id,
        )
        session.add(registro)
        criados.append(registro)
    session.commit()
    return {"criados": len(criados)}


@router.get("/pesagens/relatorio")
def relatorio_pesagens(
    numero_matriz: str | None = None,
    grupo: str | None = None,
    data_inicio: date | None = None,
    data_fim: date | None = None,
    session: Session = Depends(get_session),
) -> dict:
    """
    Primeira/última pesagem, GMD (ganho médio diário — peso final vs inicial no
    período) e GPD (ganho de peso diário entre pesagens — média dos ganhos
    diários de cada intervalo consecutivo) por animal, lote ou todo o rebanho.
    """
    query = select(PesagemCorporal)
    if numero_matriz:
        query = query.where(PesagemCorporal.numero_matriz == numero_matriz)
    if data_inicio:
        query = query.where(PesagemCorporal.data_pesagem >= data_inicio)
    if data_fim:
        query = query.where(PesagemCorporal.data_pesagem <= data_fim)
    pesagens = session.exec(query).all()
    if grupo:
        pesagens = [p for p in pesagens if p.grupo_primario == grupo]

    por_animal: dict[str, list[PesagemCorporal]] = {}
    for p in pesagens:
        por_animal.setdefault(p.numero_matriz, []).append(p)

    linhas = []
    for numero, lista in por_animal.items():
        lista.sort(key=lambda p: p.data_pesagem)
        primeira, ultima = lista[0], lista[-1]
        dias_totais = (ultima.data_pesagem - primeira.data_pesagem).days
        gmd = round((ultima.peso_kg - primeira.peso_kg) / dias_totais, 3) if dias_totais > 0 else None

        taxas = []
        for anterior, atual in zip(lista, lista[1:]):
            dias = (atual.data_pesagem - anterior.data_pesagem).days
            if dias > 0:
                taxas.append((atual.peso_kg - anterior.peso_kg) / dias)
        gpd = round(sum(taxas) / len(taxas), 3) if taxas else None

        linhas.append({
            "numero_matriz": numero,
            "grupo_primario": ultima.grupo_primario,
            "primeira_data": primeira.data_pesagem.isoformat(),
            "primeira_peso": primeira.peso_kg,
            "ultima_data": ultima.data_pesagem.isoformat(),
            "ultima_peso": ultima.peso_kg,
            "gmd_kg_dia": gmd,
            "gpd_kg_dia": gpd,
            "num_pesagens": len(lista),
        })

    linhas.sort(key=lambda l: chave_numero(l["numero_matriz"]))
    return {"linhas": linhas, "total": len(linhas)}


# ---------------------------------------------------------------------------
# Importação de planilha (Excel ou CSV) de pesagem corporal — mesmo padrão do
# controle leiteiro/qualidade do leite acima: atalho direto na tela de
# Lançamentos, distinto do CSV genérico de Configurações > Importar dados.
# ---------------------------------------------------------------------------
PESAGEM_CORPORAL_APELIDOS = {
    "numero_matriz": ["numero do animal", "numero animal", "numero", "numero matriz", "no", "n", "vaca", "animal", "brinco", "id"],
    "data_pesagem": ["data", "data pesagem", "data da pesagem"],
    "peso_kg": ["peso kg", "peso", "peso vivo", "peso vivo kg"],
}
MODELO_PESAGEM_CORPORAL = {
    "colunas": ["Número do animal", "Data", "Peso (kg)"],
    "exemplo": ["464", "05/07/2026", "420,5"],
}


@router.get("/pesagens/modelo-excel")
def modelo_excel_pesagem_corporal() -> Response:
    return _xlsx_response(
        MODELO_PESAGEM_CORPORAL["colunas"], MODELO_PESAGEM_CORPORAL["exemplo"],
        "Pesagem corporal", "modelo_pesagem_corporal.xlsx",
    )


@router.post("/pesagens/importar")
async def importar_pesagem_corporal_planilha(
    file: UploadFile, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    content = await file.read()
    linhas = list(iter_planilha_rows(file.filename or "", content))
    if not linhas:
        return {"criados": 0, "erros": ["Planilha vazia ou em formato não reconhecido."]}

    erros: list[str] = []
    por_data: dict[date, list[PesoIn]] = {}
    for i, row in enumerate(linhas, start=2):
        row_norm = {normalizar_cabecalho(k): v for k, v in row.items()}
        numero = valor_por_apelido(row_norm, PESAGEM_CORPORAL_APELIDOS["numero_matriz"]).strip()
        data_linha = parse_date(valor_por_apelido(row_norm, PESAGEM_CORPORAL_APELIDOS["data_pesagem"]))
        peso = parse_float(valor_por_apelido(row_norm, PESAGEM_CORPORAL_APELIDOS["peso_kg"]))
        if not numero or not data_linha or not peso:
            erros.append(f"Linha {i}: número do animal, data e peso são obrigatórios.")
            continue
        por_data.setdefault(data_linha, []).append(PesoIn(numero_matriz=numero, peso_kg=peso))

    criados = 0
    for dia, entradas in por_data.items():
        resultado = criar_pesagens(PesagensIn(data_pesagem=dia, entradas=entradas), session, user)
        criados += resultado["criados"]
    return {"criados": criados, "erros": erros}


class QualidadeLeiteIn(BaseModel):
    numero_matriz: str | None = None  # vazio = leitura do tanque (todas as vacas em lactação)
    data_coleta: date
    ccs: float | None = None
    cbt: float | None = None
    gordura_pct: float | None = None
    proteina_pct: float | None = None
    solidos_totais_pct: float | None = None
    esd_pct: float | None = None
    lactose_pct: float | None = None
    nul: float | None = None
    observacao: str | None = None


@router.get("/qualidade-leite")
def listar_qualidade_leite(session: Session = Depends(get_session)) -> dict:
    registros = session.exec(select(QualidadeLeite).order_by(QualidadeLeite.data_coleta)).all()
    nomes = mapa_usuarios(session, {r.usuario_id for r in registros})
    faixas = session.exec(select(FaixaBonificacaoQualidade)).all()
    tem_faixas_bonificacao = any(f.ativo for f in faixas)
    linhas = []
    for r in registros:
        linha = r.model_dump()
        linha["usuario_nome"] = nomes.get(linha.pop("usuario_id"))
        bonificacao = calcular_bonificacao(linha, faixas)
        linha["bonificacao_por_litro"] = bonificacao["total_por_litro"]
        linha["bonificacao_detalhe"] = bonificacao["detalhe"]
        linhas.append(linha)
    return {"registros": linhas, "total": len(registros), "tem_faixas_bonificacao": tem_faixas_bonificacao}


# ---------------------------------------------------------------------------
# Faixas de bonificação/penalização por qualidade do leite (#548) — tabela
# configurável em Configurações > Parâmetros, já que cada laticínio define a
# própria tabela de faixas de CCS/CBT/gordura/proteína (não existe padrão
# nacional único). Ver fazenda/rules/bonificacao_qualidade.py para o cálculo.
# ---------------------------------------------------------------------------
class FaixaBonificacaoQualidadeIn(BaseModel):
    indicador: str
    valor_min: float | None = None
    valor_max: float | None = None
    ajuste_por_litro: float
    ativo: bool = True
    observacao: str | None = None


def _validar_faixa_bonificacao(dados: FaixaBonificacaoQualidadeIn) -> None:
    if dados.indicador not in INDICADORES_BONIFICAVEIS:
        raise HTTPException(
            status_code=400,
            detail=f"Indicador inválido. Use um de: {', '.join(INDICADORES_BONIFICAVEIS)}",
        )
    if dados.valor_min is not None and dados.valor_max is not None and dados.valor_min > dados.valor_max:
        raise HTTPException(status_code=400, detail="Valor mínimo não pode ser maior que o valor máximo")


@router.get("/faixas-bonificacao-qualidade")
def listar_faixas_bonificacao_qualidade(session: Session = Depends(get_session)) -> dict:
    faixas = session.exec(
        select(FaixaBonificacaoQualidade).order_by(FaixaBonificacaoQualidade.indicador, FaixaBonificacaoQualidade.valor_min)
    ).all()
    return {"faixas": [f.model_dump() for f in faixas]}


@router.post("/faixas-bonificacao-qualidade", status_code=201)
def criar_faixa_bonificacao_qualidade(
    dados: FaixaBonificacaoQualidadeIn, session: Session = Depends(get_session), _: Usuario = Depends(exigir_admin),
) -> dict:
    _validar_faixa_bonificacao(dados)
    faixa = FaixaBonificacaoQualidade(**dados.model_dump())
    session.add(faixa)
    session.commit()
    session.refresh(faixa)
    return faixa.model_dump()


@router.put("/faixas-bonificacao-qualidade/{faixa_id}")
def atualizar_faixa_bonificacao_qualidade(
    faixa_id: int, dados: FaixaBonificacaoQualidadeIn,
    session: Session = Depends(get_session), _: Usuario = Depends(exigir_admin),
) -> dict:
    faixa = session.get(FaixaBonificacaoQualidade, faixa_id)
    if not faixa:
        raise HTTPException(status_code=404, detail="Faixa de bonificação não encontrada")
    _validar_faixa_bonificacao(dados)
    for campo, valor in dados.model_dump().items():
        setattr(faixa, campo, valor)
    session.add(faixa)
    session.commit()
    session.refresh(faixa)
    return faixa.model_dump()


@router.delete("/faixas-bonificacao-qualidade/{faixa_id}")
def excluir_faixa_bonificacao_qualidade(
    faixa_id: int, session: Session = Depends(get_session), _: Usuario = Depends(exigir_admin),
) -> dict:
    faixa = session.get(FaixaBonificacaoQualidade, faixa_id)
    if not faixa:
        raise HTTPException(status_code=404, detail="Faixa de bonificação não encontrada")
    session.delete(faixa)
    session.commit()
    return {"ok": True}


@router.post("/qualidade-leite", status_code=201)
def criar_qualidade_leite(
    dados: QualidadeLeiteIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    registro = QualidadeLeite(**dados.model_dump(), usuario_id=_usuario_id_seguro(user))
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


# ---------------------------------------------------------------------------
# Importação de planilha (Excel ou CSV) de qualidade do leite — atalho direto
# na tela de Lançamentos (distinto do CSV genérico de Configurações > Importar
# dados). Tolera cabeçalhos variados (mesmos apelidos usados lá).
# ---------------------------------------------------------------------------
QUALIDADE_LEITE_APELIDOS = {
    "numero_matriz": ["numero matriz", "numero", "vaca", "animal", "id", "brinco"],
    "data_coleta": ["data coleta", "data", "data da coleta", "coleta"],
    "ccs": ["ccs", "ccs mil ml", "ccs x1000", "celulas somaticas"],
    "cbt": ["cbt", "cpp", "cbt mil ufc ml", "contagem bacteriana", "ufc"],
    "gordura_pct": ["gordura pct", "gordura", "gordura g", "teor de gordura"],
    "proteina_pct": ["proteina pct", "proteina", "proteina g", "teor de proteina"],
    "solidos_totais_pct": ["solidos totais pct", "solidos totais", "est", "extrato seco total"],
    "esd_pct": ["esd pct", "esd", "extrato seco desengordurado"],
    "lactose_pct": ["lactose pct", "lactose"],
    "nul": ["nul", "ureia", "mun", "num", "nitrogenio ureico", "nitrogenio ureico no leite"],
}
MODELO_QUALIDADE_LEITE = {
    "colunas": [
        "Número (vazio = tanque)", "Data da coleta", "CCS", "CBT", "Gordura (%)", "Proteína (%)",
        "Sólidos totais (%)", "ESD (%)", "Lactose (%)", "NUL/ureia",
    ],
    "exemplo": ["", "05/07/2026", "181", "11", "3,69", "3,42", "12,69", "9,00", "4,69", "14,0"],
}


@router.get("/qualidade-leite/modelo-excel")
def modelo_excel_qualidade_leite() -> Response:
    return _xlsx_response(
        MODELO_QUALIDADE_LEITE["colunas"], MODELO_QUALIDADE_LEITE["exemplo"],
        "Qualidade do leite", "modelo_qualidade_leite.xlsx",
    )


@router.post("/qualidade-leite/importar")
async def importar_qualidade_leite_planilha(
    file: UploadFile, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    content = await file.read()
    criados = 0
    erros: list[str] = []
    for i, row in enumerate(iter_planilha_rows(file.filename or "", content), start=2):
        row_norm = {normalizar_cabecalho(k): v for k, v in row.items()}
        data_coleta = parse_date(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["data_coleta"]))
        if not data_coleta:
            erros.append(f"Linha {i}: data da coleta é obrigatória.")
            continue
        dados = QualidadeLeiteIn(
            numero_matriz=valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["numero_matriz"]).strip() or None,
            data_coleta=data_coleta,
            ccs=parse_float(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["ccs"])),
            cbt=parse_float(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["cbt"])),
            gordura_pct=parse_float(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["gordura_pct"])),
            proteina_pct=parse_float(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["proteina_pct"])),
            solidos_totais_pct=parse_float(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["solidos_totais_pct"])),
            esd_pct=parse_float(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["esd_pct"])),
            lactose_pct=parse_float(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["lactose_pct"])),
            nul=parse_float(valor_por_apelido(row_norm, QUALIDADE_LEITE_APELIDOS["nul"])),
        )
        criar_qualidade_leite(dados, session, user)
        criados += 1
    return {"criados": criados, "erros": erros}


class EntregaLeiteMensalIn(BaseModel):
    competencia: str  # "YYYY-MM"
    quantidade_litros: float
    observacao: str | None = None


@router.get("/entrega-leite")
def listar_entrega_leite(session: Session = Depends(get_session)) -> dict:
    registros = session.exec(select(EntregaLeiteMensal).order_by(EntregaLeiteMensal.competencia)).all()
    nomes = mapa_usuarios(session, {r.usuario_id for r in registros})
    linhas = []
    for r in registros:
        linha = r.model_dump()
        linha["usuario_nome"] = nomes.get(linha.pop("usuario_id"))
        linhas.append(linha)
    return {"registros": linhas, "total": len(registros)}


@router.post("/entrega-leite", status_code=201)
def criar_entrega_leite(
    dados: EntregaLeiteMensalIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    existente = session.exec(select(EntregaLeiteMensal).where(EntregaLeiteMensal.competencia == dados.competencia)).first()
    if existente:
        existente.quantidade_litros = dados.quantidade_litros
        existente.observacao = dados.observacao
        session.add(existente)
        session.commit()
        session.refresh(existente)
        return existente.model_dump()
    registro = EntregaLeiteMensal(**dados.model_dump(), usuario_id=_usuario_id_seguro(user))
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


def _competencia(d: date | None) -> str | None:
    return f"{d.year:04d}-{d.month:02d}" if d else None


def _parse_iso(s: str) -> date | None:
    try:
        return date.fromisoformat(s) if s else None
    except ValueError:
        return None


def _dias_por_mes_no_periodo(ini: date, fim: date) -> dict[tuple[int, int], int]:
    """Quantos dias do período caem em cada mês (para projeção proporcional)."""
    out: dict[tuple[int, int], int] = {}
    d = ini
    while d <= fim:
        chave = (d.year, d.month)
        out[chave] = out.get(chave, 0) + 1
        d += timedelta(days=1)
    return out


@router.get("/relatorio-controle-entrega")
def relatorio_controle_entrega(
    data_inicio: str = "", data_fim: str = "", session: Session = Depends(get_session),
) -> dict:
    """
    Controle × Entregue no PERÍODO filtrado, tudo em quilos de leite.

    - Controle (projetado): média da produção diária do rebanho no período
      (soma dos controles de cada dia ÷ nº de dias com controle) × dias do período.
    - Entregue (projetado): a entrega é lançada por mês; para cada mês tocado
      pelo período usa entrega_do_mês ÷ dias daquele mês (28/29/30/31) × dias do
      período naquele mês.
    - Receita média: mesma projeção proporcional, a partir da receita do laticínio.
    - Não entregue = Controle − Entregue.
    - Bezerros = leite/dia da dieta lançada × dias do período.
    - Equipe/família = Não entregue − Bezerros (residual).
    - Desvio padrão %: coeficiente de variação da produção diária do controle no
      período (mede se a média projeta bem; tolerância de 5%).
    """
    hoje = date.today()
    ini = _parse_iso(data_inicio) or hoje.replace(day=1)
    fim = _parse_iso(data_fim) or hoje
    if fim < ini:
        ini, fim = fim, ini
    dias_periodo = (fim - ini).days + 1

    # ── Controle: soma diária do rebanho, média diária, projeção e desvio ──
    kg_por_dia: dict[date, float] = {}
    for c in session.exec(select(ControleLeiteiro)).all():
        if c.data_controle and ini <= c.data_controle <= fim and c.producao_kg is not None:
            kg_por_dia[c.data_controle] = kg_por_dia.get(c.data_controle, 0.0) + c.producao_kg
    totais_diarios = list(kg_por_dia.values())
    dias_com_controle = len(totais_diarios)
    media_diaria = (sum(totais_diarios) / dias_com_controle) if dias_com_controle else 0.0
    controle_projetado = round(media_diaria * dias_periodo, 1) if dias_com_controle else None
    if dias_com_controle >= 2 and media_diaria:
        variancia = sum((x - media_diaria) ** 2 for x in totais_diarios) / dias_com_controle
        desvio_pct = round((variancia ** 0.5) / media_diaria * 100, 1)
    else:
        desvio_pct = None

    # ── Entrega e receita: projeção proporcional por mês ──
    entregas = {e.competencia: e.quantidade_litros for e in session.exec(select(EntregaLeiteMensal)).all()}
    receita_por_mes: dict[str, float] = {}
    for c in session.exec(select(ContaGerencial).where(ContaGerencial.tipo == "receita")).all():
        if "italac" not in (c.fornecedor_cliente or "").lower():
            continue
        comp = _competencia(c.data_competencia)
        if comp:
            receita_por_mes[comp] = receita_por_mes.get(comp, 0.0) + (c.valor_total or 0.0)

    entrega_projetada = 0.0
    receita_projetada = 0.0
    tem_entrega = tem_receita = False
    for (ano, mes), dias_no_mes_periodo in _dias_por_mes_no_periodo(ini, fim).items():
        comp = f"{ano:04d}-{mes:02d}"
        dias_do_mes = calendar.monthrange(ano, mes)[1]
        if comp in entregas:
            tem_entrega = True
            entrega_projetada += entregas[comp] / dias_do_mes * dias_no_mes_periodo
        if comp in receita_por_mes:
            tem_receita = True
            receita_projetada += receita_por_mes[comp] / dias_do_mes * dias_no_mes_periodo
    entrega_kg = round(entrega_projetada, 1) if tem_entrega else None
    receita = round(receita_projetada, 2) if tem_receita else None
    preco_medio_kg = round(receita / entrega_kg, 4) if (receita and entrega_kg) else None

    # ── Bezerros: leite/dia da dieta lançada (fallback: dieta CSV) × dias ──
    leite_dia_bezerros = sum(
        d.leite_bezerros_kg_dia or 0.0
        for d in session.exec(select(DietaLancamento).where(DietaLancamento.data_efetivo_encerramento == None)).all()  # noqa: E711
    )
    fonte_bezerros = "dieta_lancada"
    if leite_dia_bezerros <= 0:
        dietas = [d.model_dump() for d in session.exec(select(Dieta)).all()]
        animais = [
            a.model_dump() for a in session.exec(select(Animal).where(Animal.ativo == True)).all()  # noqa: E712
            if not a.eh_semen
        ]
        consumo = calcular_consumo(dietas, animais)
        for lote_info in consumo["por_lote"]:
            if "bezerr" not in (lote_info.get("categoria") or "").lower():
                continue
            for item in lote_info["itens"]:
                if "leite" in (item["ingrediente"] or "").lower():
                    leite_dia_bezerros += item["consumo_dia"]
        fonte_bezerros = "dieta_csv"
    bezerros_kg = round(leite_dia_bezerros * dias_periodo, 1)

    # ── Balanço ──
    nao_entregue = round(controle_projetado - entrega_kg, 1) if (controle_projetado is not None and entrega_kg is not None) else None
    equipe_kg = round(nao_entregue - bezerros_kg, 1) if nao_entregue is not None else None

    return {
        "data_inicio": ini.isoformat(), "data_fim": fim.isoformat(), "dias_periodo": dias_periodo,
        "dias_com_controle": dias_com_controle,
        "media_diaria_controle_kg": round(media_diaria, 1) if dias_com_controle else None,
        "controle_projetado_kg": controle_projetado,
        "desvio_padrao_pct": desvio_pct,
        "entrega_projetada_kg": entrega_kg,
        "receita_projetada": receita,
        "preco_medio_kg": preco_medio_kg,
        "nao_entregue_kg": nao_entregue,
        "leite_bezerros_kg_dia": round(leite_dia_bezerros, 1),
        "bezerros_kg": bezerros_kg,
        "bezerros_fonte": fonte_bezerros,
        "equipe_kg": equipe_kg,
    }


def _rotulo_lote(codigo: str, nome: str) -> str:
    return f"{codigo} - {nome}"


def _lote_das_secas(session: Session) -> dict | None:
    """
    O lote de vacas secas é o único configurado com status_lactacao="seca" —
    não dá pra usar o motor geral de critérios aqui porque a categoria/status
    do animal na ficha só é atualizada no próximo upload do GERAL.csv, não na
    hora do lançamento manual de secagem.
    """
    lote = session.exec(select(Lote).where(Lote.status_lactacao == "seca")).first()
    if not lote:
        return None
    return {"codigo": lote.codigo, "nome": lote.nome, "rotulo": _rotulo_lote(lote.codigo, lote.nome)}


@router.get("/secagem-info")
def info_secagem(numero_matriz: str, session: Session = Depends(get_session)) -> dict:
    """DEL atual, data prevista de secagem e o lote sugerido para a vaca secar."""
    animal = session.exec(select(Animal).where(Animal.numero == numero_matriz)).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")

    ultimo_servico = session.exec(
        select(Servico)
        .where(Servico.numero_matriz == numero_matriz, Servico.diagnostico == "POSITIVO")
        .order_by(Servico.data_servico.desc())
    ).first()

    data_prevista = None
    deve_secar = None
    motivo_exclusao = None
    dias_gestacao = None
    if ultimo_servico and ultimo_servico.data_servico:
        res_gest = calcular_parto_provavel(ultimo_servico.data_servico, animal.raca)
        em_lactacao = bool(animal.del_dias and animal.del_dias > 0)
        res_sec = calcular_secagem(numero_matriz, res_gest.data_parto_provavel, ultimo_servico.ordem_parto, em_lactacao)
        data_prevista = res_sec.data_secagem.isoformat()
        deve_secar = res_sec.deve_secar
        motivo_exclusao = res_sec.motivo_exclusao
        # Dias de gestação já decorridos (do serviço positivo até hoje).
        dias_gestacao = max(0, (date.today() - ultimo_servico.data_servico).days)

    # DEL ao vivo — o campo animal.del_dias só é atualizado no próximo upload
    # do GERAL.csv (fica parado entre uploads); aqui calculamos a partir do
    # último parto, igual à lógica já usada no relatório de Controle leiteiro.
    ultimo_parto = session.exec(
        select(Parto).where(Parto.numero_matriz == numero_matriz).order_by(Parto.data_parto.desc())
    ).first()
    del_atual = (date.today() - ultimo_parto.data_parto).days if ultimo_parto else animal.del_dias

    return {
        "numero_matriz": numero_matriz,
        "del_atual": del_atual,
        "lote_atual": animal.grupo_primario,
        "data_prevista_secagem": data_prevista,
        "deve_secar": deve_secar,
        "motivo_exclusao": motivo_exclusao,
        "dias_gestacao": dias_gestacao,
        "lote_sugerido": _lote_das_secas(session),
    }


class ItemSecagemIn(BaseModel):
    produto: str
    via: str | None = None
    quantidade: float
    unidade: str


class SecagemIn(BaseModel):
    numero_matriz: str
    data_secagem: date
    motivo: str
    escore_condicao_corporal: float | None = None
    observacao: str | None = None
    responsavel: str | None = None
    produtos: list[ItemSecagemIn] = []
    # Igual à Aplicação de Sanidade: se o produto de secagem ainda não foi
    # aplicado (ou a data é futura), não baixa estoque agora — vira uma
    # aplicação programada na Agenda, que baixa ao confirmar.
    aplicado: bool = True
    # Vacina(s) pré-parto escolhidas (sim/não + quais). Por padrão viram
    # pendência na Agenda para o dia seguinte à secagem; se o funcionário já
    # aplicou na hora (vacina_pre_parto_aplicada_agora=True), gera Sanidade +
    # baixa de estoque direto, sem duplicar a pendência na Agenda.
    vacinas_pre_parto: list[str] = []
    vacina_pre_parto_aplicada_agora: bool = False


@router.post("/secagem")
def registrar_secagem(
    dados: SecagemIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    if dados.motivo not in MOTIVOS_SECAGEM:
        raise HTTPException(status_code=400, detail=f"Motivo inválido (aceitos: {', '.join(MOTIVOS_SECAGEM)})")
    if dados.escore_condicao_corporal is not None and not (1 <= dados.escore_condicao_corporal <= 5):
        raise HTTPException(status_code=400, detail="Escore de condição corporal deve ser entre 1 e 5")

    session.add(Secagem(
        numero_matriz=dados.numero_matriz,
        data_secagem=dados.data_secagem,
        motivo=dados.motivo,
        escore_condicao_corporal=dados.escore_condicao_corporal,
        observacao=dados.observacao,
        usuario_id=_usuario_id_seguro(user),
    ))

    # Data futura ou "ainda não apliquei" → os produtos de secagem não baixam
    # estoque agora; viram aplicações programadas (Agenda/pendências).
    materializar = dados.aplicado and dados.data_secagem <= date.today()

    avisos: list[str] = []
    for item in dados.produtos:
        estoque_item = session.exec(select(Estoque).where(Estoque.nome == item.produto)).first()
        compativeis = unidades_compativeis(estoque_item.unidade if estoque_item else None)
        if item.unidade not in compativeis:
            raise HTTPException(
                status_code=400,
                detail=f'Unidade "{item.unidade}" não é compatível com o produto "{item.produto}" (aceitas: {", ".join(compativeis)})',
            )
        if not materializar:
            session.add(AplicacaoAgendada(
                numero_matriz=dados.numero_matriz, data=dados.data_secagem, produto=item.produto,
                dose=item.quantidade, unidade=item.unidade, via=item.via, responsavel=dados.responsavel,
                observacao="Secagem", aplicado=False,
            ))
            continue
        session.add(Sanidade(
            numero_matriz=dados.numero_matriz,
            data_aplicacao=dados.data_secagem,
            produto=item.produto,
            dose=item.quantidade,
            unidade=item.unidade,
            via=item.via,
            responsavel=dados.responsavel,
            atividade="Secagem",
        ))
        if estoque_item and estoque_item.estocavel is not False and pode_dar_baixa_direta(item.unidade, estoque_item.unidade):
            estoque_item.quantidade = (estoque_item.quantidade or 0) - item.quantidade
            if estoque_item.estoque_minimo is not None:
                estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
            estoque_item.atualizado_em = datetime.utcnow()
            session.add(estoque_item)
        elif estoque_item and estoque_item.unidade and estoque_item.unidade != item.unidade:
            avisos.append(
                f'Baixa de estoque de "{item.produto}" não aplicada — cadastre a equivalência entre '
                f'"{item.unidade}" e "{estoque_item.unidade}" (unidade de estoque do produto).'
            )

    if dados.produtos and not materializar:
        avisos.append("Produto(s) de secagem programado(s) na Agenda — o estoque baixa quando você confirmar a aplicação.")

    # Vacina(s) pré-parto: por padrão vira pendência na Agenda para o dia
    # seguinte à secagem. Se já foi aplicada na hora (mesmo lançamento), grava
    # direto em Sanidade e dá baixa de estoque — sem duplicar na Agenda.
    if dados.vacinas_pre_parto and dados.vacina_pre_parto_aplicada_agora:
        for vacina in dados.vacinas_pre_parto:
            session.add(Sanidade(
                numero_matriz=dados.numero_matriz, data_aplicacao=dados.data_secagem, produto=vacina,
                dose=1, unidade="dose", responsavel=dados.responsavel, atividade="Vacina pré-parto",
            ))
            estoque_item = session.exec(select(Estoque).where(Estoque.nome == vacina)).first()
            if estoque_item and estoque_item.estocavel is not False and pode_dar_baixa_direta("dose", estoque_item.unidade):
                estoque_item.quantidade = (estoque_item.quantidade or 0) - 1
                if estoque_item.estoque_minimo is not None:
                    estoque_item.abaixo_minimo = estoque_item.quantidade < estoque_item.estoque_minimo
                estoque_item.atualizado_em = datetime.utcnow()
                session.add(estoque_item)
        avisos.append("Vacina(s) pré-parto registrada(s) em Sanidade e baixada(s) do estoque.")
    elif dados.vacinas_pre_parto:
        data_vacina = dados.data_secagem + timedelta(days=1)
        for vacina in dados.vacinas_pre_parto:
            session.add(AplicacaoAgendada(
                numero_matriz=dados.numero_matriz, data=data_vacina, produto=vacina,
                responsavel=dados.responsavel, observacao="Vacina pré-parto", aplicado=False,
            ))
        avisos.append(f"Vacina(s) pré-parto programada(s) na Agenda para {data_vacina.strftime('%d/%m/%Y')}.")

    session.commit()
    return {"criado": True, "avisos": avisos, "programado": not materializar, "lote_sugerido": _lote_das_secas(session)}


class SugestaoLoteEventoIn(BaseModel):
    numero_matriz: str
    categoria_abrev: str  # "Vaca" | "Novilha" | "Bezerra" | "Bezerro"
    del_dias: int | None = None
    data_nasc: date | None = None


@router.post("/sugestao-lote-evento")
def sugestao_lote_evento(dados: SugestaoLoteEventoIn, session: Session = Depends(get_session)) -> dict:
    """
    Sugere um lote para um animal num evento de vida (nascimento ou parto),
    aplicando os critérios já cadastrados (Configurações > Cadastro > Lotes)
    ao estado REAL do animal nesse momento (idade 0 ao nascer, DEL 0 ao parir),
    mesmo que a ficha ainda não tenha sido atualizada pelo próximo GERAL.csv.
    """
    lotes = [l for l in session.exec(select(Lote)).all() if lote_tem_criterio(l)]
    _, servicos_por_animal, sanidades_por_animal, peso_por_animal = coletar_dados_criterios(session)

    hoje = date.today()
    animal_dict = {
        "numero": dados.numero_matriz,
        "categoria_abrev": dados.categoria_abrev,
        "categoria_completa": dados.categoria_abrev,
        "del_dias": dados.del_dias,
        "data_nasc": dados.data_nasc or hoje,
        "sit_rep": None,
        "diagnostico": None,
        "ult_cl_kg": None,
    }
    for lote in lotes:
        if animal_atende_criterios(lote, animal_dict, hoje, peso_por_animal, servicos_por_animal, sanidades_por_animal):
            return {"lote_sugerido": {"codigo": lote.codigo, "nome": lote.nome, "rotulo": _rotulo_lote(lote.codigo, lote.nome)}}
    return {"lote_sugerido": None}


# ---------------------------------------------------------------------------
# Protocolo de indução de lactação — lançamento em lote (protocolo cadastrado
# em Configurações > Cadastro, ver fazenda.api.routers.cadastro) para um ou
# vários animais de uma vez. Cada dia de cada animal vira uma aplicação
# rastreável (aparece agrupada na Agenda, marcada como realizada
# individualmente) — mesmo padrão do protocolo IATF (reproducao.py).
# ---------------------------------------------------------------------------
def _descricao_medicamentos_dia(etapas: list[ProtocoloInducaoLactacaoEtapa]) -> str:
    partes = []
    for e in etapas:
        if e.dose:
            dose_txt = f"{e.dose:g}".rstrip("0").rstrip(".") if isinstance(e.dose, float) else str(e.dose)
            partes.append(f"{dose_txt} {e.unidade or ''} {e.produto}".strip())
        else:
            partes.append(e.produto)
    return " + ".join(partes) if partes else "-"


def _observacao_manejo_dia(etapas: list[ProtocoloInducaoLactacaoEtapa]) -> str | None:
    textos = []
    for e in etapas:
        if e.tipo == "dispositivo":
            textos.append("Colocar Implante de Progesterona" if e.acao_dispositivo == "colocar" else "Retirar o Implante de Progesterona")
        elif e.tipo == "manejo":
            textos.append(e.produto)
    return " + ".join(textos) if textos else None


@router.get("/protocolos-inducao-lactacao")
def listar_protocolos_inducao_producao(session: Session = Depends(get_session)) -> list[dict]:
    """Protocolos ativos disponíveis para lançamento (o cadastro/edição vive em
    Configurações > Cadastro > Protocolo de indução de lactação)."""
    protocolos = session.exec(
        select(ProtocoloInducaoLactacao).where(ProtocoloInducaoLactacao.ativo == True).order_by(ProtocoloInducaoLactacao.nome)  # noqa: E712
    ).all()
    out = []
    for p in protocolos:
        etapas = session.exec(
            select(ProtocoloInducaoLactacaoEtapa)
            .where(ProtocoloInducaoLactacaoEtapa.protocolo_id == p.id)
            .order_by(ProtocoloInducaoLactacaoEtapa.dia)
        ).all()
        ultimo_dia = max((e.dia for e in etapas), default=p.dia_inicial)
        out.append({**p.model_dump(), "etapas": [e.model_dump() for e in etapas], "duracao_dias": ultimo_dia - p.dia_inicial})
    return out


class LancarInducaoLactacaoIn(BaseModel):
    protocolo_id: int
    animais: list[str]
    data_d0: date  # data do dia_inicial do protocolo (D0 ou D1)
    responsavel: str | None = None
    observacao: str | None = None


@router.post("/inducao-lactacao", status_code=201)
def lancar_inducao_lactacao(
    dados: LancarInducaoLactacaoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
) -> dict:
    protocolo = session.get(ProtocoloInducaoLactacao, dados.protocolo_id)
    if not protocolo:
        raise HTTPException(status_code=404, detail="Protocolo de indução de lactação não encontrado")
    etapas = session.exec(
        select(ProtocoloInducaoLactacaoEtapa)
        .where(ProtocoloInducaoLactacaoEtapa.protocolo_id == dados.protocolo_id)
        .order_by(ProtocoloInducaoLactacaoEtapa.dia)
    ).all()
    if not etapas:
        raise HTTPException(status_code=400, detail="Este protocolo não tem etapas cadastradas")
    animais = [n.strip() for n in dados.animais if n.strip()]
    if not animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    etapas_por_dia: dict[int, list[ProtocoloInducaoLactacaoEtapa]] = {}
    for e in etapas:
        etapas_por_dia.setdefault(e.dia, []).append(e)

    lancamento = ProtocoloInducaoLancamento(
        protocolo_id=protocolo.id, nome_protocolo=protocolo.nome, data_d0=dados.data_d0,
        responsavel=dados.responsavel, observacao=dados.observacao, usuario_id=_usuario_id_seguro(user),
    )
    session.add(lancamento)
    session.commit()
    session.refresh(lancamento)

    for dia, etapas_dia in etapas_por_dia.items():
        for e in etapas_dia:
            if e.tipo == "medicamento":
                session.add(ProtocoloInducaoMedicamento(
                    lancamento_id=lancamento.id, dia=dia, produto=e.produto, dose=e.dose, unidade=e.unidade, via=e.via,
                ))

    eventos_criados = 0
    for numero in animais:
        for dia, etapas_dia in etapas_por_dia.items():
            data_prevista = dados.data_d0 + timedelta(days=dia - protocolo.dia_inicial)
            session.add(ProtocoloInducaoAplicacao(
                lancamento_id=lancamento.id, numero_matriz=numero, dia=dia,
                descricao=_descricao_medicamentos_dia([e for e in etapas_dia if e.tipo == "medicamento"]),
                observacao_manejo=_observacao_manejo_dia(etapas_dia),
                data_prevista=data_prevista,
            ))
            eventos_criados += 1

    session.commit()
    return {"criado": True, "lancamento_id": lancamento.id, "eventos_criados": eventos_criados, "animais": len(animais)}


@router.get("/inducao-lactacao/ativos")
def listar_inducao_lactacao_ativos(session: Session = Depends(get_session)) -> list[dict]:
    """Lançamentos com pelo menos uma etapa ainda não realizada — para ver de
    relance em qual dia está cada animal em indução."""
    lancamentos = session.exec(select(ProtocoloInducaoLancamento).order_by(ProtocoloInducaoLancamento.data_d0.desc())).all()
    aplicacoes = session.exec(select(ProtocoloInducaoAplicacao)).all()
    por_lancamento: dict[int, list[ProtocoloInducaoAplicacao]] = {}
    for ap in aplicacoes:
        por_lancamento.setdefault(ap.lancamento_id, []).append(ap)

    ativos = []
    for lanc in lancamentos:
        aps = por_lancamento.get(lanc.id, [])
        pendentes = [a for a in aps if not a.realizada]
        if not pendentes:
            continue
        por_animal: dict[str, list[ProtocoloInducaoAplicacao]] = {}
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
        })
    return ativos


# ---------------------------------------------------------------------------
# Relatório de BST (Produção) — histórico de aplicações (Sanidade) achatado
# para os filtros/gestão. A elegibilidade do dia (aptas/excluídas/nunca
# aplicadas) já é calculada pela Agenda (GET /agenda/) — este endpoint cobre
# só o lado histórico/gerencial que falta: quem recebeu, quando e quanto.
# ---------------------------------------------------------------------------
MARCADORES_BST_PRODUCAO = re.compile(r"\b(lactotropin|boostin|bst|somatotropina)\b", re.IGNORECASE)


@router.get("/relatorio-bst")
def relatorio_bst(session: Session = Depends(get_session)) -> dict:
    """Histórico de aplicações de BST, achatado com lote/categoria do animal na hora."""
    animais_por_numero = {a.numero: a for a in session.exec(select(Animal)).all()}
    aplicacoes = [
        s for s in session.exec(select(Sanidade)).all()
        if s.atividade == "BST" or MARCADORES_BST_PRODUCAO.search(s.produto or "")
    ]
    registros = []
    for s in aplicacoes:
        a = animais_por_numero.get(s.numero_matriz)
        registros.append({
            "numero_matriz": s.numero_matriz,
            "data_aplicacao": s.data_aplicacao.isoformat() if s.data_aplicacao else None,
            "produto": s.produto, "dose": s.dose, "unidade": s.unidade, "responsavel": s.responsavel,
            "lote": a.grupo_primario if a else None,
            "categoria": (a.categoria_abrev or a.categoria_completa) if a else None,
        })
    registros.sort(key=lambda r: r["data_aplicacao"] or "", reverse=True)
    return {"aplicacoes": registros, "total": len(registros)}


class AjustarProximaAplicacaoBstIn(BaseModel):
    nova_data: date
    modo: str  # "intervalo" | "referencia"


@router.post("/bst/ajustar-proxima-aplicacao")
def ajustar_proxima_aplicacao_bst(
    dados: AjustarProximaAplicacaoBstIn, session: Session = Depends(get_session), _: Usuario = Depends(exigir_admin),
) -> dict:
    """Corrige manualmente a data da próxima aplicação de BST (é uma decisão
    de rebanho inteiro, não por animal — mesma lógica de `proxima_visita_bst`
    em agenda.py).
    modo="intervalo": recalcula o "Intervalo de aplicação de BST" (Configurações
    > Parâmetros) a partir da última aplicação real até a nova data.
    modo="referencia": mantém o intervalo atual, passando a contar os
    próximos ciclos a partir da nova data (grava em `bst_ajuste_ancora_data`,
    lido por agenda.py)."""
    from fazenda.rules.parametros import intervalo_bst

    aplicacoes = [
        s for s in session.exec(select(Sanidade)).all()
        if s.atividade == "BST" or MARCADORES_BST_PRODUCAO.search(s.produto or "")
    ]
    datas_bst = [s.data_aplicacao for s in aplicacoes if s.data_aplicacao]
    intervalo_atual = intervalo_bst()
    hoje = date.today()

    if dados.modo == "intervalo":
        if not datas_bst:
            raise HTTPException(
                status_code=400,
                detail="Não há nenhuma aplicação de BST registrada ainda — não é possível calcular um novo intervalo.",
            )
        ancora = max(datas_bst)
        ciclos = 1
        marcador = ancora + timedelta(days=intervalo_atual)
        while marcador <= hoje:
            marcador += timedelta(days=intervalo_atual)
            ciclos += 1
        novo_intervalo = max(1, round((dados.nova_data - ancora).days / ciclos))
        linha_intervalo = session.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "intervalo_bst")).first()
        if not linha_intervalo:
            raise HTTPException(status_code=500, detail="Parâmetro 'intervalo_bst' não encontrado.")
        linha_intervalo.valor = str(novo_intervalo)
        linha_intervalo.atualizado_em = datetime.utcnow()
        session.add(linha_intervalo)
        # O novo intervalo já reproduz a data escolhida a partir da última
        # aplicação real — qualquer ajuste manual de referência anterior fica
        # obsoleto.
        linha_ancora = session.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "bst_ajuste_ancora_data")).first()
        if linha_ancora and linha_ancora.valor:
            linha_ancora.valor = ""
            linha_ancora.atualizado_em = datetime.utcnow()
            session.add(linha_ancora)
        session.commit()
        return {"ok": True, "novo_intervalo": novo_intervalo, "proxima_visita_bst": dados.nova_data.isoformat()}

    if dados.modo == "referencia":
        nova_ancora = dados.nova_data - timedelta(days=intervalo_atual)
        linha_ancora = session.exec(select(ParametroFazenda).where(ParametroFazenda.chave == "bst_ajuste_ancora_data")).first()
        if not linha_ancora:
            raise HTTPException(status_code=500, detail="Parâmetro 'bst_ajuste_ancora_data' não encontrado.")
        linha_ancora.valor = nova_ancora.isoformat()
        linha_ancora.atualizado_em = datetime.utcnow()
        session.add(linha_ancora)
        session.commit()
        return {"ok": True, "intervalo_bst": intervalo_atual, "proxima_visita_bst": dados.nova_data.isoformat()}

    raise HTTPException(status_code=400, detail="modo deve ser 'intervalo' ou 'referencia'")
