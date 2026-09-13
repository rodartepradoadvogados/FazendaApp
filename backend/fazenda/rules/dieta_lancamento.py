"""
Lançamento de dieta (DietaLancamento + DietaItemProgramado) — extraído de
fazenda/api/routers/alimentacao.py para ser reaproveitado também por
Formulação de Dietas (POST /formulacao/simulacoes/{id}/aplicar), que precisa
criar exatamente o mesmo tipo de lançamento a partir de uma simulação
calculada, com a mesma validação de matéria seca e a mesma regra de "dieta
ativa" por lote. Sem mudança de comportamento em relação ao endpoint
original — ver backend/tests/test_alimentacao.py.
"""
from __future__ import annotations

from datetime import date

from fastapi import HTTPException
from sqlmodel import Session, select

from fazenda.models import (
    Alimento, DietaItemProgramado, DietaLancamento, Estoque, IngredienteMS, Lote,
)


def criar_lancamento_programado(
    session: Session,
    fazenda_id: int | None,
    usuario_id: int | None,
    *,
    lote: int,
    responsavel: str | None,
    data_abertura: date,
    data_prevista_encerramento: date | None,
    observacao: str | None,
    base_quantidade: str | None,
    leite_bezerros_kg_dia: float | None,
    itens: list[dict],
    encerrar_anterior: bool,
    dieta_simulacao_id: int | None = None,
) -> DietaLancamento:
    """Cria uma DietaLancamento + seus DietaItemProgramado, com a mesma
    validação de % de matéria seca (obrigatório quando `base="MS"`) e a mesma
    regra de dieta ativa por lote (409 sem `encerrar_anterior`, encerra a
    anterior na data de abertura desta quando True) do endpoint original de
    Alimentação. `itens` é uma lista de dicts com as chaves `alimento`,
    `quantidade`, `unidade`, `base`, `ms_pct`, `base_quantidade` (mesmo shape
    de ItemProgramadoIn) — `base_quantidade` é opcional e, quando ausente ou
    None, o item herda a base da dieta (`base_quantidade` do parâmetro
    abaixo), exatamente como antes deste campo existir. Sem validação de
    valor (igual ao `base_quantidade` da própria dieta, hoje também livre) —
    qualquer coisa que não seja exatamente "animal" já cai no ramo "total"
    em `_base_efetiva`/`_por_cabeca`."""
    if not itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um alimento do plano programado")

    query_ms = select(IngredienteMS)
    if fazenda_id is not None:
        query_ms = query_ms.where(IngredienteMS.fazenda_id == fazenda_id)
    ms_por_nome = {i.nome: i.ms_pct for i in session.exec(query_ms).all()}
    for item in itens:
        if item.get("ms_pct") is None:
            item["ms_pct"] = ms_por_nome.get(item["alimento"])
        if item.get("base") == "MS" and not item.get("ms_pct"):
            raise HTTPException(
                status_code=400,
                detail=f'Informe o % de matéria seca de "{item["alimento"]}" em Configurações > Cadastro > '
                       f'Alimentação > Matéria seca antes de lançar em base MS.',
            )
        ms_pct = item.get("ms_pct")
        if ms_pct is not None and not (0 < ms_pct <= 100):
            raise HTTPException(status_code=400, detail=f'% de matéria seca inválido para "{item["alimento"]}" — deve ser entre 0 e 100.')

    query_ativa = select(DietaLancamento).where(
        DietaLancamento.lote == lote, DietaLancamento.data_efetivo_encerramento == None  # noqa: E711
    )
    if fazenda_id is not None:
        query_ativa = query_ativa.where(DietaLancamento.fazenda_id == fazenda_id)
    ativa_existente = session.exec(query_ativa).first()
    if ativa_existente:
        if encerrar_anterior:
            ativa_existente.data_efetivo_encerramento = data_abertura
            session.add(ativa_existente)
            session.commit()
        else:
            raise HTTPException(
                status_code=409,
                detail=f"Já existe uma dieta ativa para o lote {lote} — encerre-a antes de lançar uma nova",
            )

    dieta = DietaLancamento(
        lote=lote, responsavel=responsavel, data_abertura=data_abertura,
        data_prevista_encerramento=data_prevista_encerramento, observacao=observacao,
        base_quantidade=base_quantidade or "total",
        leite_bezerros_kg_dia=leite_bezerros_kg_dia,
        usuario_id=usuario_id, fazenda_id=fazenda_id,
        dieta_simulacao_id=dieta_simulacao_id,
    )
    session.add(dieta)
    session.commit()
    session.refresh(dieta)

    # Resolve o alimento_id automaticamente pelo nome do item de Estoque
    # escolhido (ou já vindo preenchido, no caso de Formulação de Dietas) —
    # sem exigir nenhuma mudança na tela de lançamento manual: se existir um
    # Alimento com esse mesmo nome (ou um item de Estoque já vinculado a um
    # Alimento), o vínculo entra sozinho.
    query_estoque = select(Estoque)
    query_alimento = select(Alimento)
    if fazenda_id is not None:
        query_estoque = query_estoque.where(Estoque.fazenda_id == fazenda_id)
        query_alimento = query_alimento.where(Alimento.fazenda_id == fazenda_id)
    estoque_por_nome = {e.nome: e for e in session.exec(query_estoque).all()}
    alimento_por_nome = {a.nome: a.id for a in session.exec(query_alimento).all()}
    for item in itens:
        alimento_id_informado = item.pop("alimento_id", None)
        estoque_item = estoque_por_nome.get(item["alimento"])
        alimento_id = alimento_id_informado or (estoque_item.alimento_id if estoque_item else None) or alimento_por_nome.get(item["alimento"])
        session.add(DietaItemProgramado(
            dieta_lancamento_id=dieta.id, alimento_id=alimento_id, fazenda_id=fazenda_id,
            alimento=item["alimento"], quantidade=item["quantidade"], unidade=item["unidade"],
            base=item.get("base"), ms_pct=item.get("ms_pct"),
            base_quantidade=item.get("base_quantidade"),
        ))
    session.commit()
    return dieta


def _codigo_grupo_lote(grupo_primario: str | None) -> str | None:
    if not grupo_primario:
        return None
    return grupo_primario.split(" - ")[0].strip() or None


def contexto_lote(session: Session, fazenda_id: int | None, lote: int) -> dict:
    """Contexto de um lote para pré-preencher a Etapa 2 de Formulação de
    Dietas: nome do lote, nº de animais ativos, DEL médio, produção média e
    dias de gestação médios (para lote de vaca seca). Mesma resolução de
    animais-do-lote do contexto de Alimentação (por `Lote.codigo` batendo
    com o prefixo de `Animal.grupo_primario`)."""
    from fazenda.models import Animal, Parto, Servico
    from fazenda.rules.perda_prenhez import servicos_positivos_vigentes
    from fazenda.rules.producao_leiteira import com_fallback_animal, ultimo_controle_por_animal

    query_lote = select(Lote).where(Lote.codigo == f"{lote:02d}")
    if fazenda_id is not None:
        query_lote = query_lote.where(Lote.fazenda_id == fazenda_id)
    lote_cad = session.exec(query_lote).first()

    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    ativos = session.exec(query_animais).all()
    animais = [
        a for a in ativos
        if not a.eh_semen and a.sexo != "M" and _codigo_grupo_lote(a.grupo_primario) == f"{lote:02d}"
    ]
    n = len(animais)
    dels = [a.del_dias for a in animais if a.del_dias is not None]
    # Último controle leiteiro AO VIVO — mesmo motivo/fix do contexto de
    # Alimentação (ver rules/producao_leiteira.py): Animal.ult_cl_kg sozinho
    # fica congelado na data do último CSV importado.
    numeros_do_lote = {a.numero for a in animais}
    controles_ao_vivo = ultimo_controle_por_animal(session, numeros_do_lote, fazenda_id)
    cls = [
        p for a in animais
        if (p := com_fallback_animal(a.numero, controles_ao_vivo, a)[0]) is not None
    ]
    gestacoes: list[int] = []
    if numeros_do_lote:
        query_servicos = select(Servico).where(Servico.numero_matriz.in_(numeros_do_lote))
        query_partos = select(Parto).where(Parto.numero_matriz.in_(numeros_do_lote))
        if fazenda_id is not None:
            query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
            query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
        servicos = session.exec(query_servicos).all()
        partos = session.exec(query_partos).all()
        hoje = date.today()
        for servico in servicos_positivos_vigentes(servicos, partos).values():
            gestacoes.append((hoje - servico.data_servico).days)

    return {
        "lote": lote,
        "nome": lote_cad.nome if lote_cad else None,
        "qtd_animais": n,
        "del_medio": round(sum(dels) / len(dels)) if dels else None,
        "media_cl": round(sum(cls) / len(cls), 1) if cls else None,
        "dias_gestacao_medio": round(sum(gestacoes) / len(gestacoes)) if gestacoes else None,
    }
