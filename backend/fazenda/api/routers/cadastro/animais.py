"""
Cadastro > Animais — ficha do animal (grava na tabela Animal usada em todo o
site), motivo de baixa, motivo de venda, raça e grau de sangue.
Extraído do antigo `cadastro.py` monolítico.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_fazenda_atual_id
from fazenda.database import get_session
from fazenda.models import (
    AgendaManual, Animal, AplicacaoAgendada, BaixaAnimal, ColostragemBezerra, CompraAnimal, ControleLeiteiro,
    CronogramaSanitarioAnimal, ExameResultado, GrauSangue, Lactacao, LidaAplicacao, MotivoBaixa, MotivoVenda,
    MovimentoLote, OcorrenciaClinica, Parto, PesagemCorporal, ProtocoloCustomizadoAplicacao, ProtocoloIatfAplicacao,
    ProtocoloInducaoAplicacao, ProtocoloSanitarioAplicacao, ProtocoloSanitarioLancamento, QualidadeLeite, Raca,
    Sanidade, Secagem, SeedFlag, Servico, Usuario, VendaAnimal,
)
from fazenda.rules.auditoria import fazenda_id_seguro

from ._comum import _crud_nome_ativo

router = APIRouter()

# ---------------------------------------------------------------------------
# Ficha do animal — grava direto na tabela Animal usada em todo o site.
# ---------------------------------------------------------------------------
class AnimalFichaIn(BaseModel):
    numero: str
    nome: str | None = None
    sisbov: str | None = None
    sexo: str | None = None  # "F" | "M"
    raca: str | None = None
    grau_sangue: str | None = None
    categoria_abrev: str | None = None
    grupo_primario: str | None = None
    data_nasc: date | None = None
    data_entrada: date | None = None
    proprietario: str | None = None
    valor: float | None = None
    motivo_baixa: str | None = None
    data_baixa: date | None = None
    mae_numero: str | None = None
    mae_nome: str | None = None
    pai_nome: str | None = None
    pai_naab: str | None = None
    avo_paterno_nome: str | None = None
    avo_paterno_naab: str | None = None
    bisavo_paterno_nome: str | None = None
    bisavo_paterno_naab: str | None = None
    observacoes: str | None = None
    excluir_bst: bool = False


def _completar_genealogia_paterna(session: Session, animal: Animal) -> None:
    """Se o pai foi informado mas a genealogia paterna (avô/bisavô) não foi
    preenchida manualmente, tenta buscá-la no cadastro do animal — o pai pode
    também estar cadastrado como Animal (touro da fazenda) com sua própria
    genealogia já registrada; o avô, idem, uma geração acima. Sem essa cadeia
    cadastrada não há como derivar automaticamente — quem chama decide se
    deixa em aberto para seleção manual."""
    if animal.pai_nome and not animal.avo_paterno_nome:
        pai_animal = session.exec(
            select(Animal).where(func.lower(Animal.nome) == animal.pai_nome.strip().lower())
        ).first()
        if pai_animal and pai_animal.pai_nome:
            animal.avo_paterno_nome = pai_animal.pai_nome
            animal.avo_paterno_naab = pai_animal.pai_naab
    if animal.avo_paterno_nome and not animal.bisavo_paterno_nome:
        avo_animal = session.exec(
            select(Animal).where(func.lower(Animal.nome) == animal.avo_paterno_nome.strip().lower())
        ).first()
        if avo_animal and avo_animal.pai_nome:
            animal.bisavo_paterno_nome = avo_animal.pai_nome
            animal.bisavo_paterno_naab = avo_animal.pai_naab


def _partos_da_matriz(session: Session, fazenda_id: int | None, mae_numero: str) -> list[Parto]:
    query = select(Parto).where(Parto.numero_matriz == mae_numero)
    if fazenda_id is not None:
        query = query.where(Parto.fazenda_id == fazenda_id)
    return list(session.exec(query.order_by(Parto.ordem_parto, Parto.id)).all())


def _desvincular_cria_de_outros_partos(
    session: Session, fazenda_id: int | None, numero_animal: str, manter_parto_id: int | None = None,
) -> None:
    """Remove o vínculo deste animal (como cria) de qualquer parto que hoje
    aponte para ele, exceto o `manter_parto_id` informado — evita deixar o
    mesmo animal "duplicado" como cria de dois partos diferentes quando a mãe
    informada na ficha é trocada (ou removida)."""
    query = select(Parto).where(
        (Parto.numero_cria_1 == numero_animal) | (Parto.numero_cria_2 == numero_animal)
    )
    if fazenda_id is not None:
        query = query.where(Parto.fazenda_id == fazenda_id)
    for p in session.exec(query).all():
        if manter_parto_id is not None and p.id == manter_parto_id:
            continue
        if p.numero_cria_1 == numero_animal:
            p.numero_cria_1 = None
        if p.numero_cria_2 == numero_animal:
            p.numero_cria_2 = None
        session.add(p)


def validar_e_vincular_mae(session: Session, fazenda_id: int | None, mae_numero: str | None, numero_animal: str) -> None:
    """Cruza a mãe informada manualmente na ficha do animal (fora do
    lançamento de Parto) com o histórico reprodutivo JÁ LANÇADO dela, e só
    permite gravar se sobrar pelo menos 1 parto da mãe ainda sem cria
    vinculada (ou já vinculado a este mesmo animal, no caso de reeditar a
    mesma ficha sem trocar a mãe) — vincula automaticamente a esse parto
    livre (Parto.numero_cria_1/2), o mesmo campo usado pelo lançamento normal
    de parto (ver `registrar_parto` em fazenda/api/routers/reproducao.py).

    Sem essa validação, cadastrar/editar a mãe de qualquer jeito (inclusive
    direto pela API, sem passar pela Ficha) deixaria o número da mãe como
    texto solto, sem nenhum parto de fato vinculado a ela — e duas crias
    diferentes poderiam "roubar" o mesmo parto uma da outra sem aviso.

    Fonte da verdade no backend: chamada tanto por `criar_animal` quanto por
    `atualizar_ficha_animal`, então nenhuma chamada direta à API contorna a
    checagem (só a Ficha do Animal reforça isso no front, com um popup)."""
    if not mae_numero:
        # Mãe removida/vazia — desfaz qualquer vínculo anterior deste animal
        # como cria de algum parto, para não deixar um parto "grudado" numa
        # ficha que já não referencia mais aquela mãe.
        _desvincular_cria_de_outros_partos(session, fazenda_id, numero_animal)
        return

    partos = _partos_da_matriz(session, fazenda_id, mae_numero)
    if not partos:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Não é possível lançar essa mãe para esse animal, pois ela não possui nenhum parto "
                f"registrado. Se quiser realizar esse lançamento, lance o histórico reprodutivo dessa "
                f"vaca, inclusive o parto, e então cadastre esse animal."
            ),
        )

    livre: Parto | None = None
    ocupantes: list[str] = []
    for p in partos:
        outros = [n for n in (p.numero_cria_1, p.numero_cria_2) if n and n != numero_animal]
        if outros:
            ocupantes.extend(outros)
        elif livre is None:
            livre = p

    if livre is None:
        nomes = ", ".join(sorted(set(ocupantes)))
        raise HTTPException(
            status_code=409,
            detail=(
                f"Não é possível lançar essa mãe para esse animal, pois ela possui {len(partos)} "
                f"parto(s) (dos animais {nomes}). Se quiser realizar esse lançamento, lance o "
                f"histórico reprodutivo dessa vaca, inclusive o parto, e então cadastre esse animal."
            ),
        )

    _desvincular_cria_de_outros_partos(session, fazenda_id, numero_animal, manter_parto_id=livre.id)
    if livre.numero_cria_1 in (None, numero_animal):
        livre.numero_cria_1 = numero_animal
    elif livre.numero_cria_2 in (None, numero_animal):
        livre.numero_cria_2 = numero_animal
    session.add(livre)


def _validar_raca_grau_sangue(session: Session, fazenda_id: int | None, animal_atual: Animal | None, dados: "AnimalFichaIn") -> None:
    """Trava Raça/Grau de sangue na lista fechada de Configurações > Cadastro
    — sem isso, o `<input list=…>` de texto livre do formulário (ou uma
    chamada direta à API) continua aceitando qualquer string, que era
    exatamente o bug relatado pelo usuário (31/08/2026).

    Cláusula do avô ("grandfather clause"): só barra um valor que está
    MUDANDO para algo fora da lista ativa. Um valor que já estava gravado no
    animal (histórico, CSV importado, ficha antiga de antes da lista
    fechada) sempre pode ser regravado sem mudança, mesmo que hoje não
    exista mais no cadastro — `AnimalFichaIn` é um PUT que reenvia a ficha
    inteira a cada edição, então travar também o valor já existente
    quebraria a edição de qualquer animal legado.

    Segunda salvaguarda: só entra em vigor se a fazenda já tem pelo menos 1
    raça/grau de sangue ATIVO cadastrado. Uma fazenda cujo cadastro está
    vazio (nunca rodou o seed — caso do banco isolado de cada teste, que roda
    com `FAZENDA_TESTING` e pula os ~50 seeds de produção por custo, ver
    `lifespan` em main.py) ainda não tem lista fechada nenhuma para vender:
    travar igual deixaria esses lançamentos permanentemente impossíveis."""
    for campo, modelo, rotulo in ((dados.raca, Raca, "raça"), (dados.grau_sangue, GrauSangue, "grau de sangue")):
        valor = (campo or "").strip()
        if not valor:
            continue
        valor_atual = getattr(animal_atual, "raca" if modelo is Raca else "grau_sangue", None) if animal_atual else None
        if valor == valor_atual:
            continue
        query_ativos = select(modelo).where(modelo.ativo == True)  # noqa: E712
        if fazenda_id is not None:
            query_ativos = query_ativos.where(modelo.fazenda_id == fazenda_id)
        ativos = session.exec(query_ativos).all()
        if not ativos:
            continue
        if not any(item.nome == valor for item in ativos):
            raise HTTPException(
                status_code=400,
                detail=f"'{valor}' não é uma opção válida de {rotulo}. Selecione uma opção da lista em Configurações > Cadastro.",
            )


@router.get("/animais/matrizes")
def listar_matrizes_com_parto(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Fêmeas da fazenda que já tiveram pelo menos 1 parto registrado —
    matrizes possíveis para a sugestão/autocomplete do campo "Número da mãe"
    na ficha de cadastro do animal (Configurações > Cadastro > Animal)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Parto)
    if fazenda_id is not None:
        query = query.where(Parto.fazenda_id == fazenda_id)
    numeros = sorted({p.numero_matriz for p in session.exec(query).all() if p.numero_matriz})
    if not numeros:
        return []
    query_animais = select(Animal).where(Animal.numero.in_(numeros))
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    nomes = {a.numero: a.nome for a in session.exec(query_animais).all()}
    return [{"numero": n, "nome": nomes.get(n)} for n in numeros]


@router.post("/animais")
def criar_animal(
    dados: AnimalFichaIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session)
) -> dict:
    numero = dados.numero.strip()
    if not numero:
        raise HTTPException(status_code=400, detail="Número/brinco é obrigatório")
    query_existente = select(Animal).where(Animal.numero == numero)
    if fazenda_id is not None:
        query_existente = query_existente.where(Animal.fazenda_id == fazenda_id)
    existente = session.exec(query_existente).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"Já existe um animal com o número {numero}")
    _validar_raca_grau_sangue(session, fazenda_id, None, dados)

    animal = Animal(numero=numero, ativo=dados.data_baixa is None, fazenda_id=fazenda_id)
    for campo, valor in dados.model_dump(exclude={"numero"}).items():
        setattr(animal, campo, valor)
    _completar_genealogia_paterna(session, animal)
    mae_numero = (animal.mae_numero or "").strip() or None
    validar_e_vincular_mae(session, fazenda_id, mae_numero, numero)
    session.add(animal)
    session.commit()
    session.refresh(animal)
    return animal.model_dump()


@router.put("/animais/{numero}")
def atualizar_ficha_animal(
    numero: str, dados: AnimalFichaIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_animal = select(Animal).where(Animal.numero == numero)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    _validar_raca_grau_sangue(session, fazenda_id, animal, dados)
    for campo, valor in dados.model_dump(exclude={"numero"}).items():
        setattr(animal, campo, valor)
    if dados.data_baixa is not None:
        animal.ativo = False
    _completar_genealogia_paterna(session, animal)
    mae_numero = (animal.mae_numero or "").strip() or None
    validar_e_vincular_mae(session, fazenda_id, mae_numero, numero)
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    session.commit()
    session.refresh(animal)
    return animal.model_dump()


# ---------------------------------------------------------------------------
# Renumerar animal — pedido do usuário (01/09/2026): "número/brinco digitado
# errado" acontece (erro de digitação no cadastro, ou animal comprado com um
# número que já tinha dono na fazenda) e hoje não existe correção nenhuma —
# `AnimalFichaIn.numero` é ignorado de propósito em `atualizar_ficha_animal`
# acima (`exclude={"numero"}`) porque `Animal.numero` é usado como CHAVE DE
# TEXTO (não FK) em dezenas de tabelas de histórico (produção, reprodução,
# sanidade...) sem constraint nenhuma amarrando — trocar sem cascatear
# deixaria todo esse histórico "órfão", apontando pro número antigo que
# deixou de existir.
#
# Por isso esta é uma ferramenta À PARTE, não um campo a mais no formulário
# de edição normal: só administrador do tenant (`Depends(exigir_admin)`,
# reforçado pelo cadeado da Ficha do Animal no frontend — ver
# FichaAnimal.tsx), e propaga em cascata pra TODA referência por
# numero_matriz/numero_animal conhecida, na mesma transação da troca de
# `Animal.numero`.
# ---------------------------------------------------------------------------

# (modelo, campo) — toda tabela que guarda o número do animal por TEXTO
# (sem FK pra Animal.id). `Animal.numero` é único globalmente (não só por
# fazenda, ver `Animal.numero: ... unique=True`), então não precisa filtrar
# por fazenda_id aqui: o valor antigo só pode pertencer a ESTE animal.
_TABELAS_NUMERO_ANIMAL: list[tuple[type, str]] = [
    (MovimentoLote, "numero_matriz"), (BaixaAnimal, "numero_animal"), (CompraAnimal, "numero_animal"),
    (VendaAnimal, "numero_animal"), (ControleLeiteiro, "numero_matriz"), (PesagemCorporal, "numero_matriz"),
    (QualidadeLeite, "numero_matriz"), (Secagem, "numero_matriz"), (Lactacao, "numero_matriz"),
    (Servico, "numero_matriz"), (ProtocoloIatfAplicacao, "numero_matriz"), (Parto, "numero_matriz"),
    (ColostragemBezerra, "numero_animal"), (Sanidade, "numero_matriz"), (AplicacaoAgendada, "numero_matriz"),
    (ExameResultado, "numero_matriz"), (CronogramaSanitarioAnimal, "numero_matriz"),
    (ProtocoloSanitarioLancamento, "numero_matriz"), (ProtocoloSanitarioAplicacao, "numero_matriz"),
    (ProtocoloInducaoAplicacao, "numero_matriz"), (OcorrenciaClinica, "numero_matriz"),
    (ProtocoloCustomizadoAplicacao, "numero_matriz"), (LidaAplicacao, "numero_matriz"),
    # Genealogia — mãe/cria referenciados em texto livre por OUTRO animal.
    (Animal, "mae_numero"), (Parto, "numero_cria_1"), (Parto, "numero_cria_2"),
]


def _renumerar_em_cascata(session: Session, numero_antigo: str, numero_novo: str) -> list[str]:
    """Troca `numero_antigo` -> `numero_novo` em toda tabela que o referencia
    por texto — ver `_TABELAS_NUMERO_ANIMAL`. Devolve os nomes das tabelas
    que de fato tinham alguma linha pra trocar (só informativo)."""
    tabelas_afetadas: list[str] = []
    for modelo, campo in _TABELAS_NUMERO_ANIMAL:
        linhas = session.exec(select(modelo).where(getattr(modelo, campo) == numero_antigo)).all()
        for linha in linhas:
            setattr(linha, campo, numero_novo)
            session.add(linha)
        if linhas:
            tabelas_afetadas.append(f"{modelo.__name__}.{campo}")

    # AgendaManual.numero_animal é uma lista CSV de números (evento pode
    # estar vinculado a mais de um animal) — não dá pra trocar com um
    # UPDATE de texto direto (um "12" dentro de "112,120" bateria errado);
    # reescreve token a token.
    for evento in session.exec(select(AgendaManual).where(AgendaManual.numero_animal.is_not(None))).all():
        tokens = [t.strip() for t in (evento.numero_animal or "").split(",")]
        if numero_antigo in tokens:
            evento.numero_animal = ",".join(numero_novo if t == numero_antigo else t for t in tokens)
            session.add(evento)
            tabelas_afetadas.append("AgendaManual.numero_animal")

    return sorted(set(tabelas_afetadas))


class RenumerarAnimalIn(BaseModel):
    novo_numero: str


@router.post("/animais/{numero}/renumerar")
def renumerar_animal(
    numero: str, dados: RenumerarAnimalIn, fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session), _admin: Usuario = Depends(exigir_admin),
) -> dict:
    """Corrige o número/brinco de um animal já cadastrado — só admin do
    tenant, com cascata completa (ver `_renumerar_em_cascata`). Ação rara e
    sensível: sem ela, um número digitado errado no cadastro nunca poderia
    ser corrigido, só recadastrado do zero (perdendo o vínculo com todo o
    histórico já lançado)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    numero_novo = dados.novo_numero.strip()
    if not numero_novo:
        raise HTTPException(status_code=400, detail="Informe o novo número/brinco")
    if numero_novo == numero:
        raise HTTPException(status_code=400, detail="O novo número é igual ao atual")

    query_animal = select(Animal).where(Animal.numero == numero)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")

    query_conflito = select(Animal).where(Animal.numero == numero_novo)
    if fazenda_id is not None:
        query_conflito = query_conflito.where(Animal.fazenda_id == fazenda_id)
    if session.exec(query_conflito).first():
        raise HTTPException(status_code=400, detail=f"Já existe um animal com o número {numero_novo}")

    tabelas_afetadas = _renumerar_em_cascata(session, numero, numero_novo)
    animal.numero = numero_novo
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Não foi possível renumerar: \"{numero_novo}\" colide com um registro histórico existente.",
        )
    session.refresh(animal)
    return {"numero_antigo": numero, "numero_novo": numero_novo, "tabelas_afetadas": tabelas_afetadas}


# ---------------------------------------------------------------------------
# Motivo de baixa (Rebanho > Baixar animal) — causa específica da baixa (usada
# quando o motivo geral é "doença", mas também cobre outras causas comuns:
# acidente, roubo, idade avançada etc.). Cadastrável em Configurações, para
# não ficar limitado à lista fixa que havia antes só no código.
# ---------------------------------------------------------------------------
SEED_MOTIVOS_BAIXA = [
    "Botulismo", "Brucelose", "Tuberculose", "Babesia", "Casco", "Choque anafilático",
    "Afogada", "Complicações pós-parto", "Clostridiose", "Descarga elétrica", "Descarte",
    "Deslocamento de abomaso", "Desconhecido", "Diarréia", "Doação", "Doenças a vírus",
    "Doenças bacterianas", "Doenças", "Fratura", "Hemorragia interna", "Hipocalcemia",
    "Idade avançada", "Infarto", "Ingestão de corpo estranho", "Intoxicação", "Leptospirose",
    "Má formação", "Mastite", "Metrite", "Morte natural", "Nascimento prematuro", "Natimorto",
    "Pneumonia", "Retenção de placenta", "Roubo", "Tripanossoma", "Trombose",
]


def seed_motivos_baixa(session: Session, fazenda_id: int | None = None) -> None:
    """Cria os motivos de baixa padrão uma única vez por fazenda (idempotente via SeedFlag)."""
    chave = f"motivos_baixa_v1_fazenda_{fazenda_id}" if fazenda_id is not None else "motivos_baixa_v1"
    if session.get(SeedFlag, chave):
        return
    for nome in SEED_MOTIVOS_BAIXA:
        query = select(MotivoBaixa).where(MotivoBaixa.nome == nome)
        if fazenda_id is not None:
            query = query.where(MotivoBaixa.fazenda_id == fazenda_id)
        if not session.exec(query).first():
            session.add(MotivoBaixa(nome=nome, fazenda_id=fazenda_id))
    session.add(SeedFlag(chave=chave))
    session.commit()


# ---------------------------------------------------------------------------
# Motivos de venda de animal (Lançamentos > Compra/Venda > Vender animal) —
# lista padrão razoável, editável depois em Configurações > Parâmetros >
# Parâmetros gerais.
# ---------------------------------------------------------------------------
SEED_MOTIVOS_VENDA = [
    "Descarte (baixa produção)", "Problema reprodutivo", "Problema sanitário/mastite crônica",
    "Excedente de rebanho", "Venda de touro/reprodutor", "Venda de recria/leite para outra propriedade",
    "Idade avançada", "Seleção genética", "Comportamento/temperamento", "Ajuste de fluxo de caixa",
]


def seed_motivos_venda(session: Session, fazenda_id: int | None = None) -> None:
    """Cria os motivos de venda padrão uma única vez por fazenda (idempotente via SeedFlag)."""
    chave = f"motivos_venda_v1_fazenda_{fazenda_id}" if fazenda_id is not None else "motivos_venda_v1"
    if session.get(SeedFlag, chave):
        return
    for nome in SEED_MOTIVOS_VENDA:
        query = select(MotivoVenda).where(MotivoVenda.nome == nome)
        if fazenda_id is not None:
            query = query.where(MotivoVenda.fazenda_id == fazenda_id)
        if not session.exec(query).first():
            session.add(MotivoVenda(nome=nome, fazenda_id=fazenda_id))
    session.add(SeedFlag(chave=chave))
    session.commit()


# ---------------------------------------------------------------------------
# Raça e Grau de sangue — cadastráveis em Configurações, substituindo o select
# fixo (Girolando/Holandês/Gir/Outra) e o datalist de grau de sangue que
# existiam hardcoded em CadastroAnimalForm. `fracao_holandes` de cada grau de
# sangue é a posição na escala de absorção Holandês x Gir (0 = PO Gir, 1 = PO
# Holandês) — usada para calcular automaticamente o grau de sangue da cria no
# parto (ver calcular_grau_sangue_cria em fazenda.rules.genetica).
#
# Cada item tem uma `nota` didática curta — mostrada como subtítulo no
# seletor de busca da ficha do animal (ListaFechadaPicker), pesquisada nas
# fontes oficiais (Girolando/ABCGIL, Embrapa, ABCZ) pedido explícito do
# usuário, 31/08/2026: "coloque em forma de nota uma pequena nota para cada
# raça, cruzamento... da forma mais didática possível".
# ---------------------------------------------------------------------------
SEED_RACAS: list[tuple[str, str]] = [
    ("Holandês", "Raça leiteira por excelência — maior produção de leite por vaca do mundo. Pelagem preta e branca (ou vermelha e branca, a variante Red Holstein)."),
    ("Jersey", "Pequena, precoce e rústica, com o leite mais rico em gordura e proteína entre as raças leiteiras — ótima em cruzamentos para melhorar sólidos do leite."),
    ("Pardo Suíço", "Raça leiteira europeia (Brown Swiss), rústica e de boa longevidade — segundo leite mais rico em proteína/gordura depois da Jersey."),
    ("Gir", "Zebuína indiana (Gir Leiteiro), a base leiteira do Girolando — resistente ao calor e a carrapatos, com boa habilidade materna."),
    ("Guzerá", "Zebuína de dupla aptidão (leite e corte), rústica, usada em cruzamento com Holandês (Guzolando) em regiões mais quentes."),
    ("Sindi", "Zebuína (Vermelho Sindi) pequena e muito rústica, com excelente adaptação ao calor — usada sobretudo no Nordeste."),
    ("Simental", "Raça europeia de dupla aptidão (leite e corte), porte grande, usada em cruzamento industrial."),
    ("Normando", "Raça francesa de dupla aptidão (leite e carne), tradicional no Sul do Brasil."),
    ("Caracu", "Raça bovina brasileira (origem ibérica) de dupla aptidão, rústica e adaptada ao clima tropical."),
    ("Girolando", "Cruzamento consolidado Holandês x Gir — a raça leiteira mais criada no Brasil, responsável por cerca de 80% do leite nacional. Ver o grau de sangue para a fração exata de cada componente."),
    ("Guzolando", "Cruzamento consolidado Guzerá x Holandês — alternativa ao Girolando em regiões de calor mais intenso."),
    ("Jersolando", "Cruzamento consolidado Jersey x Holandês — busca aumentar o teor de sólidos (gordura/proteína) do leite."),
    ("SRD (Sem Raça Definida)", "Animal de composição genética não identificada ou irrelevante para o manejo — use quando não há como precisar a raça."),
]

SEED_GRAUS_SANGUE: list[tuple[str, float | None, str]] = [
    ("PO Holandês", 1.0, "Puro de Origem — animal Holandês registrado, nacional ou importado, sem cruzamento."),
    ("PO Gir", 0.0, "Puro de Origem — animal Gir registrado, sem cruzamento."),
    ("PO Jersey", None, "Puro de Origem — animal Jersey registrado, sem cruzamento."),
    ("PO Pardo Suíço", None, "Puro de Origem — animal Pardo Suíço registrado, sem cruzamento."),
    ("PO Guzerá", None, "Puro de Origem — animal Guzerá registrado, sem cruzamento."),
    ("PC Holandês", 1.0, "Puro por Cruza — atingiu a pureza Holandês por cruzamento sucessivo (absorção), não por ascendência 100% registrada desde a origem."),
    ("PC Gir", 0.0, "Puro por Cruza — atingiu a pureza Gir por cruzamento sucessivo (absorção), não por ascendência 100% registrada desde a origem."),
    ("PCOC Holandês", 1.0, "Puro por Cruza de Origem Conhecida — absorção para Holandês com todos os ascendentes do cruzamento identificados."),
    ("PCOC Gir", 0.0, "Puro por Cruza de Origem Conhecida — absorção para Gir com todos os ascendentes do cruzamento identificados."),
    ("PCOD Holandês", 1.0, "Puro por Cruza de Origem Desconhecida — absorção para Holandês sem registro de quais raças entraram no cruzamento original."),
    ("PCOD Gir", 0.0, "Puro por Cruza de Origem Desconhecida — absorção para Gir sem registro de quais raças entraram no cruzamento original."),
    ("1/4 Holandês x Gir", 0.25, "25% de sangue Holandês e 75% Gir — grau inicial de absorção rumo ao Girolando."),
    ("3/8 Holandês x Gir", 0.375, "37,5% de sangue Holandês e 62,5% Gir."),
    ("1/2 Holandês x Gir", 0.5, "50% Holandês e 50% Gir — a primeira geração (F1) do cruzamento Girolando."),
    ("5/8 Holandês x Gir", 0.625, "62,5% Holandês e 37,5% Gir — o padrão oficial do Girolando definido pela ABCGIL, o ponto de equilíbrio entre produção de leite e rusticidade."),
    ("3/4 Holandês x Gir", 0.75, "75% de sangue Holandês e 25% Gir."),
    ("7/8 Holandês x Gir", 0.875, "87,5% de sangue Holandês e 12,5% Gir."),
    ("15/16 Holandês x Gir", 0.9375, "93,75% de sangue Holandês — bem próximo do Holandês puro."),
    ("31/32 Holandês x Gir", 0.96875, "96,875% de sangue Holandês — o limiar em que o animal passa a ser considerado Puro por Cruza (PC Holandês)."),
    ("PS Girolando", 0.625, "Puro Sintético — geração final do Girolando já fixada geneticamente no padrão 5/8 Holandês x 3/8 Gir, reproduzindo-se \"dentro da raça\" sem precisar de novo cruzamento."),
    ("1/2 Jersey x Holandês", None, "50% Jersey e 50% Holandês — primeira geração (F1) do cruzamento Jersolando."),
    ("1/2 Guzerá x Holandês", None, "50% Guzerá e 50% Holandês — primeira geração (F1) do cruzamento Guzolando."),
    ("SRD (Sem Raça Definida)", None, "Composição genética não identificada ou irrelevante para o manejo."),
]


def seed_racas_grau_sangue(session: Session, fazenda_id: int | None = None) -> None:
    """Cria/atualiza as raças e graus de sangue padrão para uma fazenda.

    Versão 2 (idempotente via SeedFlag próprio, não reaproveita a v1): a v1
    (jul/2026) só tinha 5 raças e 8 graus de sangue, sem nota nenhuma, e
    "Outra" como raça-curinga — o que, somado ao <input list=…> de texto
    livre que existia no formulário, é exatamente o que produziu o
    preenchimento livre relatado pelo usuário (31/08/2026). Roda de novo em
    fazendas que já tinham a v1: insere o que falta (idempotente por nome,
    como sempre) e BACKFILLA a nota de quem já existe e ainda não tinha uma
    — sem sobrescrever `fracao_holandes`/`ativo` de item já cadastrado."""
    chave = f"racas_grau_sangue_v2_fazenda_{fazenda_id}" if fazenda_id is not None else "racas_grau_sangue_v2"
    if session.get(SeedFlag, chave):
        return
    for nome, nota in SEED_RACAS:
        query = select(Raca).where(Raca.nome == nome)
        if fazenda_id is not None:
            query = query.where(Raca.fazenda_id == fazenda_id)
        existente = session.exec(query).first()
        if existente:
            if not existente.nota:
                existente.nota = nota
                session.add(existente)
        else:
            session.add(Raca(nome=nome, nota=nota, fazenda_id=fazenda_id))
    # "Outra" (v1) vira escape de texto livre — não existe mais espaço para
    # isso numa lista fechada; desativa em vez de excluir (preserva o
    # histórico de quem já tinha essa raça gravada).
    query_outra = select(Raca).where(Raca.nome == "Outra")
    if fazenda_id is not None:
        query_outra = query_outra.where(Raca.fazenda_id == fazenda_id)
    outra = session.exec(query_outra).first()
    if outra and outra.ativo:
        outra.ativo = False
        session.add(outra)
    for nome, fracao, nota in SEED_GRAUS_SANGUE:
        query = select(GrauSangue).where(GrauSangue.nome == nome)
        if fazenda_id is not None:
            query = query.where(GrauSangue.fazenda_id == fazenda_id)
        existente = session.exec(query).first()
        if existente:
            if not existente.nota:
                existente.nota = nota
                session.add(existente)
        else:
            session.add(GrauSangue(nome=nome, fracao_holandes=fracao, nota=nota, fazenda_id=fazenda_id))
    session.add(SeedFlag(chave=chave))
    session.commit()



_listar_motivos_baixa, _criar_motivo_baixa, _atualizar_motivo_baixa, _ = _crud_nome_ativo(MotivoBaixa, com_fazenda=True)
router.get("/motivos-baixa")(_listar_motivos_baixa)
router.post("/motivos-baixa")(_criar_motivo_baixa)
router.put("/motivos-baixa/{item_id}")(_atualizar_motivo_baixa)

_listar_motivos_venda, _criar_motivo_venda, _atualizar_motivo_venda, _ = _crud_nome_ativo(MotivoVenda, com_fazenda=True)
router.get("/motivos-venda")(_listar_motivos_venda)
router.post("/motivos-venda")(_criar_motivo_venda)
router.put("/motivos-venda/{item_id}")(_atualizar_motivo_venda)


class RacaIn(BaseModel):
    nome: str
    nota: Optional[str] = None
    ativo: bool = True


@router.get("/racas")
def listar_racas(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Raca)
    if fazenda_id is not None:
        query = query.where(Raca.fazenda_id == fazenda_id)
    return [r.model_dump() for r in session.exec(query.order_by(Raca.id)).all()]


@router.post("/racas")
def criar_raca(
    dados: RacaIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(Raca).where(Raca.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(Raca.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe uma raça com o nome '{nome}'")
    obj = Raca(nome=nome, nota=dados.nota, ativo=dados.ativo, fazenda_id=fazenda_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.put("/racas/{item_id}")
def atualizar_raca(
    item_id: int, dados: RacaIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    obj = session.get(Raca, item_id)
    if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Raça não encontrada")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    obj.nome = nome
    obj.nota = dados.nota
    obj.ativo = dados.ativo
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


class GrauSangueIn(BaseModel):
    nome: str
    fracao_holandes: Optional[float] = None
    nota: Optional[str] = None
    ativo: bool = True


@router.get("/graus-sangue")
def listar_graus_sangue(
    fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(GrauSangue)
    if fazenda_id is not None:
        query = query.where(GrauSangue.fazenda_id == fazenda_id)
    return [g.model_dump() for g in session.exec(query.order_by(GrauSangue.id)).all()]


@router.post("/graus-sangue")
def criar_grau_sangue(
    dados: GrauSangueIn, fazenda_id: int | None = Depends(get_fazenda_atual_id), session: Session = Depends(get_session),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    query_dup = select(GrauSangue).where(GrauSangue.nome == nome)
    if fazenda_id is not None:
        query_dup = query_dup.where(GrauSangue.fazenda_id == fazenda_id)
    if session.exec(query_dup).first():
        raise HTTPException(status_code=409, detail=f"Já existe um grau de sangue com o nome '{nome}'")
    obj = GrauSangue(nome=nome, fracao_holandes=dados.fracao_holandes, nota=dados.nota, ativo=dados.ativo, fazenda_id=fazenda_id)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()


@router.put("/graus-sangue/{item_id}")
def atualizar_grau_sangue(
    item_id: int, dados: GrauSangueIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    obj = session.get(GrauSangue, item_id)
    if not obj or (fazenda_id is not None and obj.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Grau de sangue não encontrado")
    nome = dados.nome.strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Nome é obrigatório")
    obj.nome = nome
    obj.fracao_holandes = dados.fracao_holandes
    obj.nota = dados.nota
    obj.ativo = dados.ativo
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj.model_dump()



