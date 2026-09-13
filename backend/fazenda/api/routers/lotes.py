"""
Router de lotes — cadastro de lotes de manejo, seus parâmetros (faixa de DEL,
produção etc.) e os critérios de seleção de animais (cumulativos), usados hoje
pela tela de Configurações > Cadastro e, no futuro, pelo motor de sugestão
automática de movimentação.
"""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.api.routers.recria import _parametros_estado_vivo
from fazenda.auth import get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import Animal, CategoriaManejo, Lote, Parto, PesagemCorporal, Sanidade, Secagem, Servico
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.lote_criterios import animal_atende_criterios

router = APIRouter(prefix="/lotes", tags=["lotes"])


def _rotulo(codigo: str, nome: str) -> str:
    return f"{codigo} - {nome}"


def _normalizar_codigo(codigo: str) -> str:
    """Códigos numéricos sempre com 2 dígitos (ex.: '5' -> '05') — o resto do
    sistema (indicadores, alimentação, Fêmeas por grupo) extrai o código de um
    grupo pelos 2 primeiros caracteres; um código de 1 dígito faz esse animal
    "sumir" de todo lugar que conta por código."""
    codigo = codigo.strip()
    return codigo.zfill(2) if codigo.isdigit() else codigo


def _codigo_do_grupo(grupo: str | None) -> str | None:
    """Extrai o código do início de um grupo_primario ('04 - Secas' -> '04'),
    pelo separador " - " (não por posição fixa) — robusto a códigos com
    quantidade de dígitos diferente do padrão de 2."""
    if not grupo:
        return None
    return grupo.split(" - ", 1)[0].strip() or None


def _mesmo_codigo(a: str | None, b: str | None) -> bool:
    """Compara códigos de lote tolerando zero à esquerda ('5' == '05') — cobre
    o caso de um lote antigo com código não normalizado sendo comparado com o
    valor já normalizado."""
    if not a or not b:
        return False
    if a == b:
        return True
    try:
        return int(a) == int(b)
    except ValueError:
        return False


class LoteIn(BaseModel):
    codigo: str
    nome: str
    del_min: int | None = None
    del_max: int | None = None
    producao_min: float | None = None
    producao_max: float | None = None
    # Critérios de seleção (cumulativos) — ver fazenda.rules.lote_criterios.
    status_lactacao: str | None = None
    situacao_reprodutiva: str | None = None
    categorias: str | None = None
    pre_parto: bool | None = None
    peso_min: float | None = None
    peso_max: float | None = None
    dias_para_parto_min: int | None = None
    dias_para_parto_max: int | None = None
    dias_gestacao_min: int | None = None
    dias_gestacao_max: int | None = None
    dias_desde_servico_min: int | None = None
    dias_desde_servico_max: int | None = None
    em_tratamento: bool | None = None
    idade_dias_min: int | None = None
    idade_dias_max: int | None = None
    novilhas_inseminadas: bool | None = None
    novilhas_gestantes: bool | None = None
    categoria_manejo_ids: str | None = None
    excluir_da_sugestao: bool = False
    ativo: bool = True
    # Permissões do lançamento de consumo de alimento. Nascem False (o padrão
    # restritivo é o seguro), mas PRECISAM ser editáveis por aqui: sem isto o
    # lote fica preso no padrão para sempre, porque não há outro caminho na
    # aplicação para ligá-las — só editando o banco à mão.
    permitir_fora_da_dieta: bool = False
    permitir_sem_estoque: bool = False
    # Como a dieta deste lote afeta o Estoque — "automatica" (baixa dia a dia
    # pelo plano), "consumo_real" (só baixa quando alguém lança o consumo de
    # verdade) ou "sem_baixa" (a dieta é só plano/receita). Nasce
    # "consumo_real" (padrão restritivo/compatível — ver Lote.modo_baixa_estoque)
    # e, como as duas flags acima, precisa ser editável por aqui.
    modo_baixa_estoque: str = "consumo_real"


def _validar_faixas(dados: LoteIn) -> None:
    pares = [
        (dados.del_min, dados.del_max, "DEL"),
        (dados.producao_min, dados.producao_max, "Produção"),
        (dados.peso_min, dados.peso_max, "Peso"),
        (dados.dias_para_parto_min, dados.dias_para_parto_max, "Dias para o parto"),
        (dados.idade_dias_min, dados.idade_dias_max, "Idade em dias"),
        (dados.dias_gestacao_min, dados.dias_gestacao_max, "Dias de gestação"),
        (dados.dias_desde_servico_min, dados.dias_desde_servico_max, "Dias desde o último serviço"),
    ]
    for minimo, maximo, nome in pares:
        if minimo is not None and maximo is not None and minimo > maximo:
            raise HTTPException(status_code=400, detail=f"{nome} mínimo não pode ser maior que o máximo")
    # "Pré-parto" e "Secas" (status_lactacao="seca") são identidades
    # exclusivas — o mesmo lote não pode ser as duas coisas ao mesmo tempo
    # (ver _lote_das_secas em producao.py e lote_pre_parto em
    # cadastro/sanitario.py, que buscam UM lote por flag). Sem essa checagem,
    # um cadastro errado (ex.: marcar as duas caixas no mesmo lote) fica
    # silencioso até aparecer como "nome errado" numa sugestão de secagem.
    if dados.pre_parto and dados.status_lactacao == "seca":
        raise HTTPException(
            status_code=400,
            detail="Um lote não pode ser 'Pré-parto' e 'Secas' (status de lactação = seca) ao mesmo tempo — são identidades exclusivas.",
        )


def _validar_flags_unicos(session: Session, dados: LoteIn, lote_id: int | None, fazenda_id: int | None) -> None:
    """Só pode haver UM lote com pre_parto=True e UM com status_lactacao="seca"
    — várias regras (secagem, calendário sanitário) buscam "o" lote por essa
    flag com `.first()`; um segundo lote com a mesma flag faria a sugestão
    virar silenciosamente para o lote errado, sem erro nenhum. Escopo por
    fazenda: cada fazenda tem seu próprio "o lote pré-parto"/"o lote seco"."""
    query = select(Lote)
    if fazenda_id is not None:
        query = query.where(Lote.fazenda_id == fazenda_id)
    outros = session.exec(query).all()
    for outro in outros:
        if outro.id == lote_id:
            continue
        if dados.pre_parto and outro.pre_parto:
            raise HTTPException(
                status_code=400,
                detail=f"Já existe um lote marcado como Pré-parto ({_rotulo(outro.codigo, outro.nome)}) — desmarque-o antes de marcar este.",
            )
        if dados.status_lactacao == "seca" and outro.status_lactacao == "seca":
            raise HTTPException(
                status_code=400,
                detail=f"Já existe um lote com status de lactação = Seca ({_rotulo(outro.codigo, outro.nome)}) — altere-o antes de marcar este.",
            )


def _aplicar_campos(lote: Lote, dados: LoteIn) -> None:
    lote.del_min = dados.del_min
    lote.del_max = dados.del_max
    lote.producao_min = dados.producao_min
    lote.producao_max = dados.producao_max
    lote.status_lactacao = dados.status_lactacao
    lote.situacao_reprodutiva = dados.situacao_reprodutiva
    lote.categorias = dados.categorias
    lote.pre_parto = dados.pre_parto
    lote.peso_min = dados.peso_min
    lote.peso_max = dados.peso_max
    lote.dias_para_parto_min = dados.dias_para_parto_min
    lote.dias_para_parto_max = dados.dias_para_parto_max
    lote.dias_gestacao_min = dados.dias_gestacao_min
    lote.dias_gestacao_max = dados.dias_gestacao_max
    lote.dias_desde_servico_min = dados.dias_desde_servico_min
    lote.dias_desde_servico_max = dados.dias_desde_servico_max
    lote.em_tratamento = dados.em_tratamento
    lote.idade_dias_min = dados.idade_dias_min
    lote.idade_dias_max = dados.idade_dias_max
    lote.novilhas_inseminadas = dados.novilhas_inseminadas
    lote.novilhas_gestantes = dados.novilhas_gestantes
    lote.categoria_manejo_ids = dados.categoria_manejo_ids
    lote.excluir_da_sugestao = dados.excluir_da_sugestao
    lote.ativo = dados.ativo
    lote.permitir_fora_da_dieta = dados.permitir_fora_da_dieta
    lote.permitir_sem_estoque = dados.permitir_sem_estoque
    lote.modo_baixa_estoque = dados.modo_baixa_estoque


@router.get("/")
def listar_lotes(
    incluir_inativos: bool = Query(False, description="True mostra também lotes inativos (só o cadastro precisa disso; seletores de destino não)."),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Lote).order_by(Lote.codigo)
    query_animal = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(Lote.fazenda_id == fazenda_id)
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    if not incluir_inativos:
        query = query.where(Lote.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query = query.where(Lote.fazenda_id == fazenda_id)
    lotes = session.exec(query).all()
    animais = session.exec(query_animal).all()
    contagem: dict[str, int] = {}
    for a in animais:
        if a.eh_semen or a.sexo == "M" or not a.grupo_primario:
            continue
        codigo = _codigo_do_grupo(a.grupo_primario)
        if codigo:
            contagem[codigo] = contagem.get(codigo, 0) + 1

    saida = []
    for lote in lotes:
        d = lote.model_dump()
        d["rotulo"] = _rotulo(lote.codigo, lote.nome)
        # Tolera código gravado sem zero à esquerda (ver _mesmo_codigo).
        d["qtd_animais"] = sum(n for cod, n in contagem.items() if _mesmo_codigo(cod, lote.codigo))
        saida.append(d)
    return saida


@router.post("/")
def criar_lote(
    dados: LoteIn, fazenda_id: int = Depends(get_fazenda_id_escrita), session: Session = Depends(get_session),
) -> dict:
    _validar_faixas(dados)
    _validar_flags_unicos(session, dados, lote_id=None, fazenda_id=fazenda_id)
    codigo = _normalizar_codigo(dados.codigo)
    if not codigo or not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Código e nome são obrigatórios")
    query_existente = select(Lote).where(Lote.codigo == codigo)
    if fazenda_id is not None:
        query_existente = query_existente.where(Lote.fazenda_id == fazenda_id)
    existente = session.exec(query_existente).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"Já existe um lote com o código {codigo}")

    lote = Lote(codigo=codigo, nome=dados.nome.strip(), fazenda_id=fazenda_id)
    _aplicar_campos(lote, dados)
    session.add(lote)
    session.commit()
    session.refresh(lote)
    return lote.model_dump()


@router.put("/{lote_id}")
def atualizar_lote(
    lote_id: int, dados: LoteIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    _validar_faixas(dados)
    lote = session.get(Lote, lote_id)
    if not lote or (fazenda_id is not None and lote.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lote não encontrado")
    _validar_flags_unicos(session, dados, lote_id=lote_id, fazenda_id=fazenda_id)

    codigo_novo = _normalizar_codigo(dados.codigo) if dados.codigo.strip() else lote.codigo
    if codigo_novo != lote.codigo:
        query_existente = select(Lote).where(Lote.codigo == codigo_novo)
        if fazenda_id is not None:
            query_existente = query_existente.where(Lote.fazenda_id == fazenda_id)
        existente = session.exec(query_existente).first()
        if existente and existente.id != lote.id:
            raise HTTPException(status_code=400, detail=f"Já existe um lote com o código {codigo_novo}")

    # Rede de segurança para inativar: o front já orienta a transferir os
    # animais primeiro (janela suspensa), mas se algum ficou pra trás por
    # qualquer motivo, bloqueia aqui em vez de deixá-los "órfãos" — um lote
    # inativo some dos seletores de destino/movimentação.
    if lote.ativo and not dados.ativo:
        query_animais_no_lote = select(Animal).where(Animal.ativo == True)  # noqa: E712
        if fazenda_id is not None:
            query_animais_no_lote = query_animais_no_lote.where(Animal.fazenda_id == fazenda_id)
        animais_no_lote = session.exec(query_animais_no_lote).all()
        qtd = sum(
            1 for a in animais_no_lote
            if not a.eh_semen and a.sexo != "M" and _mesmo_codigo(_codigo_do_grupo(a.grupo_primario), lote.codigo)
        )
        if qtd:
            raise HTTPException(
                status_code=400,
                detail=f"Ainda há {qtd} animal(is) no lote {_rotulo(lote.codigo, lote.nome)} — transfira-os antes de inativar.",
            )

    codigo_antigo = lote.codigo
    nome_antigo = lote.nome

    lote.codigo = codigo_novo
    lote.nome = dados.nome.strip() or lote.nome
    _aplicar_campos(lote, dados)
    lote.atualizado_em = datetime.utcnow()
    session.add(lote)

    # Reconcilia o rótulo de todos os animais deste lote (pelo código ANTIGO
    # OU NOVO, tolerando zero à esquerda — ex.: um código gravado sem o zero
    # à esquerda antes de uma correção) com o nome/código atuais. Roda mesmo
    # sem mudança nesta chamada, para curar qualquer divergência que tenha
    # ficado de uma edição anterior (cadastro e Rebanho > Fêmeas por grupo não
    # podem exibir um rótulo diferente do cadastro).
    rotulo_novo = _rotulo(lote.codigo, lote.nome)
    query_animais_reconciliar = select(Animal).where(Animal.grupo_primario != None)  # noqa: E711
    if fazenda_id is not None:
        query_animais_reconciliar = query_animais_reconciliar.where(Animal.fazenda_id == fazenda_id)
    animais = session.exec(query_animais_reconciliar).all()
    for a in animais:
        cod_animal = _codigo_do_grupo(a.grupo_primario)
        if (_mesmo_codigo(cod_animal, codigo_antigo) or _mesmo_codigo(cod_animal, codigo_novo)) and a.grupo_primario != rotulo_novo:
            a.grupo_primario = rotulo_novo
            session.add(a)

    session.commit()
    session.refresh(lote)
    return lote.model_dump()


def coletar_dados_criterios(session: Session, fazenda_id: int | None = None) -> dict:
    """Reúne os dados usados pelos critérios de lote (prévia e sugestão de
    movimentação) — dict (não tupla posicional: cresceu demais pra isso) que
    `fazenda.rules.lote_criterios.animal_atende_criterios`/`sugerir_movimentacoes`
    recebem inteiro. `*_obj_por_animal` traz os objetos SQLModel (não dicts) —
    exigidos por `_contexto_categoria` (fazenda.api.routers.recria), reaproveitada
    para calcular situação produtiva/dias pós-parto/gestação AO VIVO.

    `CategoriaManejo` (Recria) ainda não tem `fazenda_id` — ver proposta de
    separação fazenda/empresa, Parte 1.6; fica sem filtro até esse domínio
    ser migrado."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_animal = select(Animal).where(Animal.ativo == True)  # noqa: E712
    query_servico = select(Servico)
    query_sanidade = select(Sanidade)
    query_parto = select(Parto)
    query_pesagem = select(PesagemCorporal)
    query_secagem = select(Secagem)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
        query_servico = query_servico.where(Servico.fazenda_id == fazenda_id)
        query_sanidade = query_sanidade.where(Sanidade.fazenda_id == fazenda_id)
        query_parto = query_parto.where(Parto.fazenda_id == fazenda_id)
        query_pesagem = query_pesagem.where(PesagemCorporal.fazenda_id == fazenda_id)
        query_secagem = query_secagem.where(Secagem.fazenda_id == fazenda_id)

    animais = [
        a.model_dump() for a in session.exec(query_animal).all()
        if not a.eh_semen and a.sexo != "M"
    ]

    servicos_obj = session.exec(query_servico).all()
    servicos_por_animal: dict[str, list[dict]] = {}
    servicos_obj_por_animal: dict[str, list] = {}
    for s in servicos_obj:
        servicos_por_animal.setdefault(s.numero_matriz, []).append(s.model_dump())
        servicos_obj_por_animal.setdefault(s.numero_matriz, []).append(s)

    sanidades_por_animal: dict[str, list[dict]] = {}
    for s in session.exec(query_sanidade).all():
        sanidades_por_animal.setdefault(s.numero_matriz, []).append(s.model_dump())

    peso_por_animal: dict[str, float] = {}
    ultima_data: dict[str, date] = {}
    pesagens_por_animal: dict[str, list[tuple[date, float]]] = {}
    for p in session.exec(query_pesagem).all():
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg
        if p.data_pesagem and p.peso_kg:
            pesagens_por_animal.setdefault(p.numero_matriz, []).append((p.data_pesagem, p.peso_kg))

    partos_obj_por_animal: dict[str, list] = {}
    for p in session.exec(query_parto).all():
        partos_obj_por_animal.setdefault(p.numero_matriz, []).append(p)

    secagens_obj_por_animal: dict[str, list] = {}
    for s in session.exec(query_secagem).all():
        secagens_obj_por_animal.setdefault(s.numero_matriz, []).append(s)

    categorias_ativas = list(session.exec(select(CategoriaManejo).where(CategoriaManejo.ativo == True)).all())  # noqa: E712

    # Os 4 parâmetros que o estado reprodutivo ao vivo precisa (ver
    # rules.estado_reprodutivo.classificar_animal, chamado dentro de
    # recria._contexto_categoria) — lidos uma vez aqui, não a cada animal:
    # `animal_atende_criterios`/`sugerir_movimentacoes` rodam em loop (às
    # vezes um por animal por lote), e cada leitura de parâmetro abre uma
    # sessão de banco própria (mesmo cuidado do calendário sanitário).
    pev_dias, del_max_1o_servico, idade_apta_dias, peso_apta_kg, idade_atraso_dias, dias_atraso_apos_aptidao = (
        _parametros_estado_vivo()
    )

    return {
        "animais": animais,
        "servicos_por_animal": servicos_por_animal,
        "sanidades_por_animal": sanidades_por_animal,
        "peso_por_animal": peso_por_animal,
        "pesagens_por_animal": pesagens_por_animal,
        "servicos_obj_por_animal": servicos_obj_por_animal,
        "partos_obj_por_animal": partos_obj_por_animal,
        "secagens_obj_por_animal": secagens_obj_por_animal,
        "categorias_ativas": categorias_ativas,
        "pev_dias": pev_dias, "del_max_1o_servico": del_max_1o_servico,
        "idade_apta_dias": idade_apta_dias, "peso_apta_kg": peso_apta_kg,
        "idade_atraso_dias": idade_atraso_dias,
        "dias_atraso_apos_aptidao": dias_atraso_apos_aptidao,
    }


@router.post("/preview")
def preview_criterios(
    dados: LoteIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    """
    Prévia de quantos e quais animais atendem aos critérios informados (sem
    precisar salvar o lote) — cumulativos, em E lógico.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    _validar_faixas(dados)
    lote_temp = Lote(codigo=dados.codigo or "?", nome=dados.nome or "?")
    _aplicar_campos(lote_temp, dados)

    hoje = date.today()
    dados_criterios = coletar_dados_criterios(session, fazenda_id)

    atendem = [
        a["numero"] for a in dados_criterios["animais"]
        if animal_atende_criterios(lote_temp, a, hoje, dados_criterios)
    ]
    return {"total": len(atendem), "animais": sorted(atendem)}
