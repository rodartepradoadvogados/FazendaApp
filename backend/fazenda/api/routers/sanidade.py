"""
Router de sanidade — histórico de medicamentos aplicados nos animais e
lançamento de aplicação (um ou mais produtos, por animal ou por lote).
Endpoint: GET /sanidade/aplicacoes, POST /sanidade/aplicacoes
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.ordenacao import chave_numero
from fazenda.models import (
    Animal, AplicacaoAgendada, ColostragemBezerra,
    Doenca, Estoque, IndicacaoTerapeutica, MedicamentoComercial, MovimentoEstoque,
    Parto, ProtocoloSanitario, ProtocoloSanitarioAplicacao, ProtocoloSanitarioEtapa,
    ProtocoloSanitarioLancamento, ProtocoloSanitarioLote, QualidadeLeite, Sanidade, Usuario,
)
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios, usuario_id_seguro
from fazenda.rules.cura_protocolo import protocolo_terminado
from fazenda.rules.estoque_baixa import (
    baixar as _estoque_baixar, carencia_para_item, devolver as _estoque_devolver,
    resolver_item as _resolver_item_estoque, resolver_marca_comercial,
)
from fazenda.rules.farmacia import resumo_principios
from fazenda.rules.historico_sanitario import (
    TIPO_PREVENTIVO, TIPOS_HISTORICO, doencas_dos_curativos, linhas_preventivo,
)
from fazenda.rules.lote_historico import (
    MapaLotes, erro_periodo, lote_casa, lote_na_data, no_periodo, normalizar_lista,
)
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento
from fazenda.rules.parto import eh_parto_produtivo
from fazenda.rules.unidades import unidades_compativeis
from fazenda.rules.visibilidade import visivel

TETOS_VALIDOS = ["AE", "AD", "PD", "PE"]
CLASSIFICACOES_MASTITE = ["clinica", "subclinica", "ambiental"]
GRAUS_MASTITE = [1, 2, 3]
RESULTADOS_CMT = ["-", "+", "++", "+++"]
# Agentes (patógenos) de mastite mais comuns — lista padrão sugerida; o usuário
# pode informar outro no lançamento.
AGENTES_MASTITE = [
    "Staphylococcus aureus", "Streptococcus agalactiae", "Mycoplasma bovis", "Negativo",
    "Coliformes", "Streptococcus uberis", "Streptococcus dysgalactiae", "Escherichia coli",
    "Klebsiella pneumoniae", "Enterobacter aerogenes", "Serratia spp.", "Pseudomonas spp.",
    "Proteus spp.", "Arcanobacterium pyogenes", "Nocardia spp.", "Bacillus spp.",
    "Fungos", "Leveduras", "Algas",
]
# Intervalo abaixo do qual um novo caso no mesmo teto é considerado recidiva
# (indica trocar para o próximo tratamento).
DIAS_RECIDIVA_MASTITE = 20

router = APIRouter(prefix="/sanidade", tags=["sanidade"])


def _data_br(iso: str) -> str:
    """`"2026-08-10"` -> `"10/08/2026"` — formato que o operador lê no campo,
    não o ISO que só serve pra máquina."""
    return date.fromisoformat(iso).strftime("%d/%m/%Y")

STATUS_ESTOQUE_RANK = {"ok": 0, "low": 1, "out": 2}


def _bulas_por_principio(session: Session, fazenda_id: int | None, principio_ids: set[int]) -> dict[int, list[dict]]:
    """Dose, via e carência do CADASTRO das marcas de cada princípio (é na
    marca que moram — ver MedicamentoComercial). Catálogo global + o da
    fazenda; a cópia personalizada pela fazenda esconde o padrão de origem."""
    if not principio_ids:
        return {}
    marcas = session.exec(visivel(
        select(MedicamentoComercial).where(
            MedicamentoComercial.principio_ativo_id.in_(principio_ids), MedicamentoComercial.ativo == True,  # noqa: E712
        ), MedicamentoComercial, fazenda_id,
    )).all()
    personalizadas = {m.origem_id for m in marcas if m.origem_id and m.fazenda_id is not None}
    saida: dict[int, list[dict]] = {}
    for m in marcas:
        if m.id in personalizadas:
            continue
        dose = (m.dose_texto or "").strip() or None
        if dose is None and m.dose_padrao is not None:
            num = f"{m.dose_padrao:g}".replace(".", ",")
            dose = f"{num} {m.unidade_dose or ''}".strip()
            if m.dose_base == "por_kg_pv" and m.dose_referencia_kg:
                dose += f" a cada {m.dose_referencia_kg:g} kg"
        tem_carencia = m.carencia_leite_dias is not None or m.carencia_carne_dias is not None or bool(m.proibido_lactacao)
        if not (dose or m.via_padrao or tem_carencia):
            continue
        saida.setdefault(m.principio_ativo_id, []).append({
            "id": m.id, "marca": m.nome_comercial, "laboratorio": m.laboratorio, "dose": dose, "via": m.via_padrao,
            "carencia": carencia_para_item(None, m)["texto"] if tem_carencia else None,
        })
    return saida


@router.get("/indicacoes-doenca/{doenca_id}")
def indicacoes_por_doenca(
    doenca_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Ranking de medicamentos indicados para uma doença (prioridade clínica) com
    estoque ao vivo — alimenta a consulta "Remédios por doença" e o banner de
    substituto no lançamento (quando o 1º colocado está sem estoque)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    # Doença do CATÁLOGO GLOBAL tem fazenda_id nulo — o `!=` estrito dava 404
    # em toda doença semeada assim que a fazenda passou a ter `fid` no token.
    # Tolera nulo (é de todo mundo), rejeita a de OUTRA fazenda.
    doenca = session.get(Doenca, doenca_id)
    if not doenca or (fazenda_id is not None and doenca.fazenda_id not in (None, fazenda_id)):
        raise HTTPException(status_code=404, detail="Doença não encontrada")
    indicacoes = session.exec(
        visivel(
            select(IndicacaoTerapeutica).where(IndicacaoTerapeutica.doenca_id == doenca_id),
            IndicacaoTerapeutica, fazenda_id,
        ).order_by(IndicacaoTerapeutica.prioridade)
    ).all()
    resumo_por_pa = {r["id"]: r for r in resumo_principios(session, fazenda_id)}
    bulas_por_pa = _bulas_por_principio(session, fazenda_id, {i.principio_ativo_id for i in indicacoes})
    opcoes = []
    for ind in indicacoes:
        r = resumo_por_pa.get(ind.principio_ativo_id)
        if not r:
            continue
        status = "out" if not r["itens"] or (r["total_apresentacoes"] or 0) <= 0 else ("low" if r["abaixo_minimo"] else "ok")
        marcas = sorted({it["marca"] for it in r["itens"] if it["marca"]})
        # Bula das marcas: primeiro as que a fazenda TEM no estoque (é o que
        # vai ser aplicado), depois as demais do catálogo.
        em_estoque = {it["medicamento_comercial_id"] for it in r["itens"] if it["medicamento_comercial_id"]}
        bulas = sorted(bulas_por_pa.get(ind.principio_ativo_id, []), key=lambda b: (b["id"] not in em_estoque, b["marca"]))
        opcoes.append({
            "principio_ativo_id": ind.principio_ativo_id,
            "nome": r["nome"],
            "classificacao": r["categoria_software"],
            "prioridade": ind.prioridade,
            "status_estoque": status,
            "total_apresentacoes": r["total_apresentacoes"],
            "unidade_apresentacao": r["unidade_apresentacao"],
            "marcas": marcas,
            # Observação clínica da indicação ("só com corpo lúteo"...) — o
            # campo existia no cadastro e nunca saía na consulta.
            "nota": (ind.nota or "").strip() or None,
            # Nenhum item de estoque ligado ao princípio: a tela diz "Sem
            # apresentações cadastradas" em vez de "0 frasco em estoque".
            "apresentacoes_cadastradas": len(r["itens"]),
            "bulas": [{k: v for k, v in b.items() if k != "id"} | {"em_estoque": b["id"] in em_estoque} for b in bulas[:4]],
        })
    opcoes.sort(key=lambda o: (o["prioridade"], STATUS_ESTOQUE_RANK.get(o["status_estoque"], 9)))
    return {"doenca_id": doenca_id, "doenca": doenca.nome, "opcoes": opcoes}


@router.get("/aplicacoes")
def listar_aplicacoes(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
    data_inicio: date | None = None,
    data_fim: date | None = None,
    numeros: Annotated[list[str] | None, Query()] = None,
    lotes: Annotated[list[str] | None, Query()] = None,
    tipo: str | None = None,
    doencas: Annotated[list[int] | None, Query()] = None,
) -> dict:
    """Aplicações achatadas para o dashboard interativo (filtra no cliente).

    Filtros OPCIONAIS (Menu › Sanidade › Histórico de tratamentos e vacinas do
    app, espec aprovada pelo dono em out/2026) — sem nenhum, a resposta é a
    mesma de antes (o site depende disso):
      * `data_inicio`/`data_fim` (invertido = 400, como em Produção);
      * `numeros` — número EXATO do animal (repetível ou "1,2");
      * `lotes` — o lote do animal NA DATA da aplicação (gravado em
        `lote_no_dia` ou reconstruído pelo MovimentoLote — rules/lote_historico);
      * `tipo` = todos | curativo | preventivo — com ele a lista vira o
        histórico do app: o curativo (sem o BST/indução, que é manejo) junto
        com as vacinas/exames do preventivo novo (`sanitario_registro`), cada
        linha com `tipo_historico`. Sem `tipo`, só `Sanidade`, como sempre;
      * `doencas` — ids de doença do protocolo aplicado (curativo).
    Toda linha ganha `chave` (única entre as duas tabelas), `tipo_historico`,
    `lote_na_data`/`lote_fonte`, `doenca_id`/`doenca` e `curada`."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    msg_periodo = erro_periodo(data_inicio, data_fim)
    if msg_periodo:
        raise HTTPException(status_code=400, detail=msg_periodo)
    if tipo is not None and tipo not in TIPOS_HISTORICO:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: use {', '.join(TIPOS_HISTORICO)}.")
    filtro_numeros = normalizar_lista(numeros)
    filtro_lotes = normalizar_lista(lotes)
    filtro_doencas = set(doencas or [])
    # Aborto não conta como parto na ordem exibida (ver fazenda/rules/parto.py).
    # Escopado pela fazenda: antes `select(Parto)` contava os partos de TODAS
    # as fazendas com o mesmo número de brinco (ordem de parto misturada).
    query_partos = select(Parto)
    if fazenda_id is not None:
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
    partos_por_numero: dict[str, int] = {}
    for p in session.exec(query_partos).all():
        if not eh_parto_produtivo(p):
            continue
        partos_por_numero[p.numero_matriz] = partos_por_numero.get(p.numero_matriz, 0) + 1
    # Lote/categoria ATUAIS do animal em `lote`/`categoria_animal` (campo de
    # sempre, o site usa); o lote NA DATA vai em `lote_na_data`.
    query_animais = select(Animal)
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    animais_por_numero = {a.numero: a for a in session.exec(query_animais).all()}
    query_sanidades = select(Sanidade)
    if fazenda_id is not None:
        query_sanidades = query_sanidades.where(Sanidade.fazenda_id == fazenda_id)
    if data_inicio is not None:
        query_sanidades = query_sanidades.where(Sanidade.data_aplicacao >= data_inicio)
    if data_fim is not None:
        query_sanidades = query_sanidades.where(Sanidade.data_aplicacao <= data_fim)
    if filtro_numeros:
        query_sanidades = query_sanidades.where(Sanidade.numero_matriz.in_(filtro_numeros))
    sanidades = [] if tipo == TIPO_PREVENTIVO else session.exec(query_sanidades).all()
    if tipo is not None:
        # Histórico do app: BST e indução de cio (natureza="preventivo" em
        # Sanidade) são manejo, não tratamento nem vacina — ficam de fora.
        sanidades = [s for s in sanidades if (s.natureza or "curativo") != "preventivo"]
    nomes = mapa_usuarios(session, {s.usuario_id for s in sanidades})
    doenca_por_lancamento = doencas_dos_curativos(
        session, fazenda_id, {s.protocolo_sanitario_lancamento_id for s in sanidades},
    )

    # Item de Estoque por nome do produto (mesma fazenda) — usado para casar
    # cada aplicação com a marca comercial que carrega a carência. Cacheado
    # por nome (memoizado abaixo) porque o mesmo produto se repete em muitas
    # linhas e não vale a pena resolver a marca de novo a cada uma.
    query_estoque_prod = select(Estoque)
    if fazenda_id is not None:
        query_estoque_prod = query_estoque_prod.where(Estoque.fazenda_id == fazenda_id)
    estoque_por_nome = {(e.nome or "").strip().lower(): e for e in session.exec(query_estoque_prod).all()}
    resolvido_por_produto: dict[str, tuple[Estoque | None, MedicamentoComercial | None]] = {}

    def _item_e_marca(produto: str | None) -> tuple[Estoque | None, MedicamentoComercial | None]:
        chave = (produto or "").strip().lower()
        if chave not in resolvido_por_produto:
            item = estoque_por_nome.get(chave)
            marca = resolver_marca_comercial(
                session, item=item, nome=produto,
                principio_ativo_id=item.principio_ativo_id if item else None,
            )
            resolvido_por_produto[chave] = (item, marca)
        return resolvido_por_produto[chave]

    registros = []
    for s in sanidades:
        d = s.data_aplicacao
        animal = animais_por_numero.get(s.numero_matriz)
        item_produto, marca_produto = _item_e_marca(s.produto)
        doenca = doenca_por_lancamento.get(s.protocolo_sanitario_lancamento_id)
        registros.append({
            "id": s.id,
            "chave": f"c{s.id}",
            "tipo_historico": s.natureza or "curativo",
            "numero": s.numero_matriz,
            "raca": s.raca or "(sem raça)",
            "produto": s.produto,
            "categoria": s.categoria or "Outros",
            "dose": s.dose,
            "unidade": s.unidade,
            "via": s.via,
            "responsavel": s.responsavel,
            "atividade": s.atividade,
            "obs": s.obs,
            "ordem_parto": partos_por_numero.get(s.numero_matriz) or None,
            "lote": s.lote or (animal.grupo_primario if animal else None),
            "categoria_animal": animal.categoria_abrev or animal.categoria_completa if animal else None,
            "natureza": s.natureza or "curativo",
            "data": d.isoformat() if d else None,
            "ano": d.year if d else None,
            "mes": f"{d.year}-{d.month:02d}" if d else None,
            "usuario_nome": nomes.get(s.usuario_id),
            "carencia": carencia_para_item(item_produto, marca_produto, data_aplicacao=d),
            "doenca_id": doenca[0] if doenca else None,
            "doenca": doenca[1] if doenca else None,
            "curada": s.curada,
            "lote_gravado": s.lote_no_dia,
        })
    if tipo in ("todos", TIPO_PREVENTIVO) and fazenda_id is not None:
        for r in linhas_preventivo(session, fazenda_id, inicio=data_inicio, fim=data_fim, numeros=filtro_numeros):
            animal = animais_por_numero.get(r["numero"])
            r.update({
                "raca": (animal.raca if animal else None) or "(sem raça)", "atividade": None,
                "ordem_parto": partos_por_numero.get(r["numero"]) or None,
                "lote": animal.grupo_primario if animal else None,
                "categoria_animal": animal.categoria_abrev or animal.categoria_completa if animal else None,
            })
            registros.append(r)

    # Lote NA DATA (uma carga só do histórico de movimentação, escopada).
    mapa_lotes = MapaLotes(session, fazenda_id, {r["numero"] for r in registros if r["numero"]})
    saida = []
    for r in registros:
        dia = date.fromisoformat(r["data"]) if r["data"] else None
        lote, fonte = mapa_lotes.na_data(r["numero"], dia, gravado=r.pop("lote_gravado"))
        if filtro_lotes and not lote_casa(lote, filtro_lotes):
            continue
        if filtro_doencas and r["doenca_id"] not in filtro_doencas:
            continue
        if (data_inicio or data_fim) and not no_periodo(dia, data_inicio, data_fim):
            continue
        r["lote_na_data"] = lote
        r["lote_fonte"] = fonte
        saida.append(r)
    if tipo is not None:
        saida.sort(key=lambda r: (r["data"] or "", r["chave"]), reverse=True)
    return {"aplicacoes": saida, "total": len(saida)}


@router.get("/unidades-compativeis")
def obter_unidades_compativeis(
    produto: str, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[str]:
    """Unidades que fazem sentido escolher para este produto, dada sua unidade de estoque."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Estoque).where(Estoque.nome == produto)
    if fazenda_id is not None:
        query = query.where(Estoque.fazenda_id == fazenda_id)
    item = session.exec(query).first()
    return unidades_compativeis(item.unidade if item else None)


class ItemAplicacaoIn(BaseModel):
    produto: str
    via: str | None = None
    quantidade: float
    unidade: str
    # "Qual frasco/apresentação você está usando?" — quando há mais de uma
    # apresentação (marca/tamanho) do mesmo princípio no estoque, o front manda
    # o id do item escolhido para abater do recipiente certo.
    estoque_id: int | None = None
    # "Qual lote/frasco de compra?" (Fase G, 01/09/2026) — dentro do MESMO
    # item de estoque escolhido acima, quando há mais de um lote em aberto.
    # Sem isso, a baixa cai em FIFO automático (lote mais antigo primeiro).
    lote_id: int | None = None


class AplicacaoIn(BaseModel):
    data_aplicacao: date
    animais: list[str]
    itens: list[ItemAplicacaoIn]
    responsavel: str | None = None
    observacao: str | None = None
    # "Já foi aplicado?" — quando False (ou a data é futura) NADA é baixado do
    # estoque: a aplicação fica programada na Agenda até ser confirmada.
    aplicado: bool = True
    # Só "curativo": vacinas e exames preventivos saíram deste lançamento em
    # 2026 (módulo novo sanitario_*). BST e Indução de cio gravam
    # natureza="preventivo" pelos próprios fluxos (agenda/reprodução), não aqui.
    natureza: Literal["curativo"] = "curativo"


@router.post("/aplicacoes")
def registrar_aplicacao(
    dados: AplicacaoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal ou lote")
    if not dados.itens:
        raise HTTPException(status_code=400, detail="Adicione ao menos um produto")

    # Regra de data: aplicação no futuro NUNCA baixa estoque (não aconteceu
    # ainda). Só materializa quando marcada como aplicada E a data não é futura.
    materializar = dados.aplicado and dados.data_aplicacao <= date.today()

    if not materializar:
        agendadas = 0
        for item in dados.itens:
            for numero in dados.animais:
                session.add(AplicacaoAgendada(
                    numero_matriz=numero, data=dados.data_aplicacao, produto=item.produto,
                    dose=item.quantidade, unidade=item.unidade, via=item.via,
                    responsavel=dados.responsavel, observacao=dados.observacao,
                    usuario_id=usuario_id_seguro(user), natureza=dados.natureza,
                    fazenda_id=fazenda_id,
                ))
                agendadas += 1
        session.commit()
        return {"criados": 0, "agendadas": agendadas, "avisos": [], "programado": True}

    criados = 0
    sanidade_ids: list[int] = []
    avisos: list[str] = []
    for item in dados.itens:
        # Se o usuário escolheu o frasco/apresentação específico ("qual frasco?"),
        # abate dele; senão, cai no item pelo nome do produto (comportamento antigo).
        estoque_item = _resolver_item_estoque(session, fazenda_id=fazenda_id, produto=item.produto, estoque_id=item.estoque_id)
        compativeis = unidades_compativeis(estoque_item.unidade if estoque_item else None)
        if item.unidade not in compativeis:
            raise HTTPException(
                status_code=400,
                detail=f'Unidade "{item.unidade}" não é compatível com o produto "{item.produto}" (aceitas: {", ".join(compativeis)})',
            )

        # Aviso de carência — uma vez por produto lançado (não por animal: é a
        # mesma informação repetida). O que o ordenhador/tratador precisa não é
        # o número de dias, é ATÉ QUANDO descartar — por isso o aviso carrega a
        # data de liberação já calculada a partir de `data_aplicacao`, não só o
        # prazo cru. Sem carência informada, NENHUM aviso é emitido: inventar
        # "sem carência" seria pior que não avisar nada (ver rules/carencia.py).
        marca_item = resolver_marca_comercial(
            session, item=estoque_item, nome=item.produto,
            principio_ativo_id=estoque_item.principio_ativo_id if estoque_item else None,
        )
        carencia = carencia_para_item(estoque_item, marca_item, data_aplicacao=dados.data_aplicacao)
        if carencia["leite_dias"] is not None or carencia["carne_dias"] is not None or carencia["proibido_lactacao"]:
            frase = carencia["texto"]
            complementos = []
            if carencia["proibido_lactacao"]:
                complementos.append(
                    "Produto NÃO PODE ser usado em vaca em lactação — não aplique em animal em produção."
                )
            if carencia.get("liberacao_leite"):
                complementos.append(f'Descarte o leite até {_data_br(carencia["liberacao_leite"])}.')
            if carencia.get("liberacao_carne"):
                complementos.append(f'Aguarde até {_data_br(carencia["liberacao_carne"])} para abater.')
            if complementos:
                frase = frase + " " + " ".join(complementos)
            avisos.append(f'{item.produto}: {frase}')

        for numero in dados.animais:
            sanidade = Sanidade(
                numero_matriz=numero,
                data_aplicacao=dados.data_aplicacao,
                produto=item.produto,
                dose=item.quantidade,
                unidade=item.unidade,
                via=item.via,
                responsavel=dados.responsavel,
                obs=dados.observacao,
                usuario_id=usuario_id_seguro(user),
                natureza=dados.natureza,
                fazenda_id=fazenda_id,
                # Lote do animal no dia da aplicação — o relatório de BST
                # inclui o curativo com produto BST, filtrado pelo lote do dia.
                lote_no_dia=lote_na_data(
                    session, numero_matriz=numero, data=dados.data_aplicacao, fazenda_id=fazenda_id,
                ),
            )
            session.add(sanidade)
            session.flush()
            sanidade_ids.append(sanidade.id)
            criados += 1

            # Baixa POR ANIMAL, não uma só agregada pro lote inteiro — cada
            # MovimentoEstoque fica com origem_id=sanidade.id (a linha DESTE
            # animal). Antes, um lote de N animais baixava tudo numa
            # movimentação só, presa ao id do último animal — excluir a
            # aplicação de qualquer um dos outros N-1 não achava o que
            # estornar (o estorno genérico de exclusoes.py busca por
            # origem_id, não recalcula a dose). Mesmo saldo final de estoque,
            # só que rastreável e reversível linha a linha.
            avisos.extend(_estoque_baixar(
                session, item=estoque_item, quantidade=item.quantidade, unidade=item.unidade, data=dados.data_aplicacao,
                fazenda_id=fazenda_id, observacao=f"Aplicação em {numero} — Sanidade",
                usuario_id=usuario_id_seguro(user), origem_tipo="sanidade", origem_id=sanidade.id,
                produto=item.produto, lote_id=item.lote_id,
            ))

    session.commit()
    return {"criados": criados, "agendadas": 0, "avisos": avisos, "programado": False, "sanidade_ids": sanidade_ids}


def _ajustar_estoque_por_aplicacao(
    session: Session, produto: str | None, dose: float | None, unidade: str | None,
    fazenda_id: int | None, sinal: int, observacao: str, origem_id: int | None = None,
    estoque_id: int | None = None, lote_id: int | None = None,
) -> list[str]:
    """Devolve (sinal=+1) ou baixa (sinal=-1) `dose` de `produto` no estoque —
    usado para estornar/reaplicar a baixa quando uma aplicação é editada ou
    excluída (ver PUT/DELETE /sanidade/aplicacoes/{id}). Delega os mesmos
    portões da baixa original (ver fazenda.rules.estoque_baixa.movimentar) —
    sem isso um estorno criaria estoque fantasma para uma baixa que nunca
    aconteceu. Devolve os avisos gerados (lista vazia se nada precisou avisar).

    `estoque_id`, quando informado, força o MESMO frasco que a baixa original
    usou — sem ele, `_resolver_item_estoque` cai no fallback por nome e, se
    houver mais de um frasco cadastrado com o mesmo produto (comum em
    Farmácia — lotes/validades diferentes), pode devolver/rebaixar num frasco
    diferente do que a aplicação de fato consumiu. `lote_id` (Fase G,
    01/09/2026) é o mesmo princípio, um nível abaixo: o lote/frasco de compra
    específico que a baixa original consumiu dentro desse item."""
    if not produto or dose is None or not unidade:
        return []
    estoque_item = _resolver_item_estoque(session, fazenda_id=fazenda_id, produto=produto, estoque_id=estoque_id)
    fn = _estoque_devolver if sinal > 0 else _estoque_baixar
    return fn(
        session, item=estoque_item, quantidade=dose, unidade=unidade, data=date.today(),
        fazenda_id=fazenda_id, observacao=observacao, origem_tipo="sanidade", origem_id=origem_id,
        produto=produto, lote_id=lote_id,
    )


def _frasco_da_ultima_aplicacao(session: Session, sanidade_id: int) -> tuple[int | None, int | None]:
    """(`estoque_id`, `lote_id`) que a baixa mais recente desta Sanidade de
    fato usou (lido do próprio rastro em MovimentoEstoque, que `estoque_baixa.
    movimentar` grava — ver a nota em `_ajustar_estoque_por_aplicacao`).
    "Mais recente" porque uma aplicação pode já ter sido editada antes: cada
    edição grava um novo par estorno/rebaixa com o mesmo origem_id."""
    mov = session.exec(
        select(MovimentoEstoque).where(
            MovimentoEstoque.origem_tipo == "sanidade", MovimentoEstoque.origem_id == sanidade_id,
            MovimentoEstoque.movimento == "Aplicação",
        ).order_by(MovimentoEstoque.id.desc())
    ).first()
    return (mov.estoque_id, mov.lote_id) if mov else (None, None)


class EditarAplicacaoIn(BaseModel):
    """Edição de UMA aplicação já lançada, direto na lista de Sanidade.
    Todos os campos são opcionais — só o que vier é alterado."""
    data_aplicacao: date | None = None
    produto: str | None = None
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None
    responsavel: str | None = None
    obs: str | None = None


@router.put("/aplicacoes/{aplicacao_id}", dependencies=[Depends(exigir_admin)])
def editar_aplicacao(
    aplicacao_id: int, dados: EditarAplicacaoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Corrige uma aplicação diretamente na lista (produto, dose, unidade, via,
    responsável, data, observação). Se produto, dose ou unidade mudarem, o
    estoque é ajustado: estorna a baixa antiga (valores atuais do registro) e
    aplica a baixa com os valores novos — ver _ajustar_estoque_por_aplicacao.

    Restrito a admin — o front já só mostra "Editar" pra admin; a trava aqui
    fecha o desvio óbvio de chamar o endpoint direto sem passar pela tela."""
    s = session.get(Sanidade, aplicacao_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not s or (s.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")

    campos = dados.model_dump(exclude_unset=True)
    if "unidade" in campos and campos["unidade"]:
        produto = campos.get("produto", s.produto)
        query_item = select(Estoque).where(Estoque.nome == produto)
        if fazenda_id is not None:
            query_item = query_item.where(Estoque.fazenda_id == fazenda_id)
        estoque_item = session.exec(query_item).first()
        compativeis = unidades_compativeis(estoque_item.unidade if estoque_item else None)
        if campos["unidade"] not in compativeis:
            raise HTTPException(
                status_code=400,
                detail=f'Unidade "{campos["unidade"]}" não é compatível com o produto "{produto}" (aceitas: {", ".join(compativeis)})',
            )

    avisos: list[str] = []
    # Cada linha de Sanidade é UM animal — a quantidade do ajuste de estoque é
    # a própria dose (não multiplica por nº de animais, ao contrário da baixa
    # em lote de registrar_aplicacao).
    mexe_estoque = any(c in campos for c in ("produto", "dose", "unidade"))
    if mexe_estoque:
        produto_antigo = s.produto
        estoque_id_antigo, lote_id_antigo = _frasco_da_ultima_aplicacao(session, s.id)
        _ajustar_estoque_por_aplicacao(
            session, produto_antigo, s.dose, s.unidade, fazenda_id, +1,
            f"Estorno por edição da aplicação #{s.id} — Sanidade", origem_id=s.id, estoque_id=estoque_id_antigo,
            lote_id=lote_id_antigo,
        )

    for campo, valor in campos.items():
        setattr(s, campo, valor)
    s.atualizado_em = datetime.utcnow()
    session.add(s)

    if mexe_estoque:
        # Produto não mudou: continua no MESMO frasco que a baixa original
        # usava — não deixa a rebaixa "escolher" outro frasco do mesmo
        # produto por conta própria. Produto mudou: não há frasco antigo
        # válido pro produto novo, resolve por nome mesmo (comportamento de
        # sempre).
        estoque_id_novo = estoque_id_antigo if s.produto == produto_antigo else None
        lote_id_novo = lote_id_antigo if s.produto == produto_antigo else None
        avisos.extend(_ajustar_estoque_por_aplicacao(
            session, s.produto, s.dose, s.unidade, fazenda_id, -1,
            f"Aplicação editada #{s.id} — Sanidade", origem_id=s.id, estoque_id=estoque_id_novo,
            lote_id=lote_id_novo,
        ))

    session.commit()
    session.refresh(s)
    return {
        "id": s.id, "numero": s.numero_matriz, "produto": s.produto, "dose": s.dose, "unidade": s.unidade,
        "avisos": avisos,
    }


@router.delete("/aplicacoes/{aplicacao_id}", dependencies=[Depends(exigir_admin)])
def excluir_aplicacao(
    aplicacao_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Exclusão direta (hard delete), restrita a admin. O site não chama mais
    este endpoint — usa o fluxo central e auditado (POST /exclusoes/confirmar,
    tipo="sanidade"), que admin também exclui na hora mas operador só solicita
    (ver exclusoes.py). Mantido para chamadas diretas à API.

    Devolve a dose ao estoque nas mesmas condições da baixa original — ver
    _ajustar_estoque_por_aplicacao."""
    s = session.get(Sanidade, aplicacao_id)
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not s or (s.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")
    estoque_id_excluida, lote_id_excluida = _frasco_da_ultima_aplicacao(session, s.id)
    _ajustar_estoque_por_aplicacao(
        session, s.produto, s.dose, s.unidade, fazenda_id, +1,
        f"Estorno por exclusão da aplicação #{s.id} — Sanidade", origem_id=s.id,
        estoque_id=estoque_id_excluida, lote_id=lote_id_excluida,
    )
    session.delete(s)
    session.commit()
    return {"excluido": True, "id": aplicacao_id}


class MarcarCuraAplicacaoIn(BaseModel):
    curada: bool


@router.post("/aplicacoes/{aplicacao_id}/cura")
def marcar_cura_aplicacao(
    aplicacao_id: int, dados: MarcarCuraAplicacaoIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Marca, no dia seguinte a uma aplicação curativa avulsa, se o animal foi
    curado ou não — mesma ideia do /mastite/cura, mas para aplicação avulsa
    (não um protocolo multi-dia). Alimenta o relatório Taxa de cura."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    s = session.get(Sanidade, aplicacao_id)
    if not s or (s.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Aplicação não encontrada")
    s.curada = dados.curada
    session.add(s)
    session.commit()
    return {"id": s.id, "curada": s.curada}


# Categoria simplificada do animal (mesmo padrão usado em lote_criterios.py e
# agenda_veterinario.py — sem helper compartilhado hoje, ver dívida técnica
# anotada nesses arquivos) — usada só para os filtros do relatório abaixo.
def _categoria_animal(animal: Animal | None) -> str:
    if not animal:
        return ""
    texto = (animal.categoria_abrev or animal.categoria_completa or "").strip().lower()
    if "bezerr" in texto:
        return "bezerra"
    if "novilh" in texto:
        return "novilha"
    if "vaca" in texto:
        return "vaca"
    return ""


def _status_lactacao(animal: Animal | None) -> str:
    if not animal:
        return ""
    texto = (animal.categoria_completa or "").strip().lower()
    if "seca" in texto:
        return "seca"
    if "lact" in texto:
        return "lactacao"
    return ""


@router.get("/taxa-cura")
def relatorio_taxa_cura(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Casos de cura (aplicação avulsa curativa + protocolo sanitário),
    achatados para o dashboard interativo — filtra no cliente por período,
    lote, lactação/seca e categoria, e permite comparar o mesmo animal ao
    longo da vida (vários casos por número).

    Traz tanto os casos JÁ AVALIADOS (`avaliado=True`, `curada` true/false)
    quanto os que já poderiam ter sido avaliados mas ninguém respondeu
    (`avaliado=False`, `curada=None`) — um protocolo só vira "não avaliado"
    quando já TERMINOU (todas as aplicações do último dia realizadas, mesma
    regra de `agenda.py`); protocolo em andamento não é pendência, ainda não
    chegou a hora de perguntar. Sem isso, quem nunca responde "curado?" fica
    invisível no relatório e a taxa de cura mostrada fica artificialmente
    boa — daí a taxa (`taxa_cura_pct`) ser calculada só sobre os avaliados, e
    o campo `cobertura_avaliacao_pct` existir para denunciar se ela é
    confiável (poucos casos avaliados = número pouco confiável mesmo que
    bonito).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)

    query_animais = select(Animal)
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    animais_por_numero = {a.numero: a for a in session.exec(query_animais).all()}
    protocolos_nomes = {p.id: p.nome for p in session.exec(select(ProtocoloSanitario)).all()}

    casos = []

    query_sanidade = select(Sanidade).where(Sanidade.curada != None)  # noqa: E711
    if fazenda_id is not None:
        query_sanidade = query_sanidade.where(Sanidade.fazenda_id == fazenda_id)
    for s in session.exec(query_sanidade).all():
        animal = animais_por_numero.get(s.numero_matriz)
        casos.append({
            "origem": "aplicacao",
            "id": s.id,
            "numero": s.numero_matriz,
            "tratamento": s.produto,
            "data": s.data_aplicacao.isoformat() if s.data_aplicacao else None,
            "curada": s.curada,
            "avaliado": True,
            "lote": s.lote or (animal.grupo_primario if animal else None),
            "categoria": _categoria_animal(animal),
            "status_lactacao": _status_lactacao(animal),
        })

    query_lancamentos = select(ProtocoloSanitarioLancamento)
    if fazenda_id is not None:
        query_lancamentos = query_lancamentos.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query_lancamentos).all()

    query_aplicacoes_protocolo = select(ProtocoloSanitarioAplicacao)
    if fazenda_id is not None:
        query_aplicacoes_protocolo = query_aplicacoes_protocolo.where(ProtocoloSanitarioAplicacao.fazenda_id == fazenda_id)
    aplicacoes_por_lancamento: dict[int, list] = {}
    for a in session.exec(query_aplicacoes_protocolo).all():
        aplicacoes_por_lancamento.setdefault(a.lancamento_id, []).append(a)

    for lanc in lancamentos:
        if lanc.curada is not None:
            avaliado = True
        else:
            terminou, _ = protocolo_terminado(aplicacoes_por_lancamento.get(lanc.id, []))
            if not terminou:
                continue  # protocolo em andamento — ainda não é caso pendente de avaliação
            avaliado = False
        animal = animais_por_numero.get(lanc.numero_matriz)
        casos.append({
            "origem": "protocolo",
            "id": lanc.id,
            "numero": lanc.numero_matriz,
            "tratamento": protocolos_nomes.get(lanc.protocolo_id, "—"),
            "data": lanc.data_inicio.isoformat() if lanc.data_inicio else None,
            "curada": lanc.curada,
            "avaliado": avaliado,
            "lote": animal.grupo_primario if animal else None,
            "categoria": _categoria_animal(animal),
            "status_lactacao": _status_lactacao(animal),
        })

    casos.sort(key=lambda c: (c["numero"], c["data"] or ""))
    total_avaliados = sum(1 for c in casos if c["avaliado"])
    total_nao_avaliados = len(casos) - total_avaliados
    curados = sum(1 for c in casos if c["avaliado"] and c["curada"])
    nao_curados = total_avaliados - curados
    return {
        "casos": casos,
        "total": total_avaliados,  # retrocompatibilidade (era o total de avaliados antes do defeito 3)
        "total_avaliados": total_avaliados,
        "curados": curados,
        "nao_curados": nao_curados,
        "total_nao_avaliados": total_nao_avaliados,
        "taxa_cura_pct": round(100 * curados / total_avaliados, 1) if total_avaliados else None,
        "cobertura_avaliacao_pct": (
            round(100 * total_avaliados / len(casos), 1) if casos else None
        ),
    }


# ---------------------------------------------------------------------------
# Protocolo sanitário — lançamento (aplicar um protocolo cadastrado a um
# animal). Gera uma aplicação (evento de Agenda) por etapa/dia do protocolo;
# a baixa de estoque só acontece quando o evento é marcado "realizado" na
# Agenda (ver POST /agenda/realizados).
# ---------------------------------------------------------------------------
class ProtocoloLancamentoIn(BaseModel):
    protocolo_id: int
    numeros_matriz: list[str]  # um ou mais animais (protocolo de mastite aceita só um)
    data_inicio: date
    responsavel: str | None = None
    observacao: str | None = None
    classificacao_mastite: str | None = None  # "clinica" | "subclinica" | "ambiental"
    grau_mastite: int | None = None  # 1, 2 ou 3
    agente: str | None = None
    resultado_cmt: str | None = None  # "-", "+", "++" ou "+++"
    tetos_afetados: list[str] = []  # subconjunto de AE/AD/PD/PE
    # Medicamento escolhido por etapa (etapa_id -> nome do medicamento), quando
    # a etapa foi cadastrada por princípio ativo/classificação.
    escolhas_medicamento: dict[str, str] = {}


def _status_lancamento_protocolo(lote: ProtocoloSanitarioLote | None, aplicacoes: list) -> str:
    """Mesma regra de central_protocolos._linha: cancelado > encerrado >
    concluido > ativo. O estado de cancelar/encerrar mora no LOTE — sem
    ele, um protocolo cancelado (aplicações desfeitas) parecia 'em andamento'."""
    if lote is not None and not lote.ativo:
        return "cancelado"
    if lote is not None and lote.encerrado_em is not None:
        return "encerrado"
    if aplicacoes and all(a.realizada for a in aplicacoes):
        return "concluido"
    return "ativo"


def _serializar_lancamento_protocolo(
    session: Session, lanc: ProtocoloSanitarioLancamento, protocolos: dict[int, ProtocoloSanitario], nomes: dict[int, str] | None = None,
    lotes: dict[int, ProtocoloSanitarioLote] | None = None,
) -> dict:
    aplicacoes = session.exec(
        select(ProtocoloSanitarioAplicacao)
        .where(ProtocoloSanitarioAplicacao.lancamento_id == lanc.id)
        .order_by(ProtocoloSanitarioAplicacao.data_prevista)
    ).all()
    etapas = {e.id: e for e in session.exec(select(ProtocoloSanitarioEtapa)).all()}
    nomes = nomes if nomes is not None else mapa_usuarios(session, {lanc.usuario_id})
    protocolo = protocolos.get(lanc.protocolo_id)
    lote = (lotes or {}).get(lanc.lote_id) if lanc.lote_id else None
    return {
        **lanc.model_dump(),
        "status": _status_lancamento_protocolo(lote, aplicacoes),
        "encerrado_em": lote.encerrado_em if lote else None,
        "encerrado_motivo": lote.encerrado_motivo if lote else None,
        "protocolo_nome": protocolo.nome if protocolo else "—",
        # Rótulo D exibido = etapa.dia - protocolo_dia_inicial (mesma convenção
        # de CadastroSanitario.tsx) — sem isso, a listagem de lançamentos
        # sempre mostraria o dia bruto (D1, D2...) mesmo para protocolos já
        # cadastrados em base D0.
        "protocolo_dia_inicial": protocolo.dia_inicial if protocolo else 1,
        "usuario_nome": nomes.get(lanc.usuario_id),
        "aplicacoes": [
            {**a.model_dump(), "etapa": etapas[a.etapa_id].model_dump() if a.etapa_id in etapas else None}
            for a in aplicacoes
        ],
    }


@router.get("/protocolos/lancamentos")
def listar_lancamentos_protocolo(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    protocolos = {p.id: p for p in session.exec(select(ProtocoloSanitario)).all()}
    query = select(ProtocoloSanitarioLancamento).order_by(ProtocoloSanitarioLancamento.data_inicio.desc())
    if fazenda_id is not None:
        query = query.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query).all()
    nomes = mapa_usuarios(session, {l.usuario_id for l in lancamentos})
    lotes = {lo.id: lo for lo in session.exec(select(ProtocoloSanitarioLote)).all()}
    return [_serializar_lancamento_protocolo(session, l, protocolos, nomes, lotes) for l in lancamentos]


@router.post("/protocolos/lancamentos", status_code=201)
def lancar_protocolo(
    dados: ProtocoloLancamentoIn, response: Response, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    # BUG DE SEGURANÇA CORRIGIDO: ProtocoloSanitario é per-tenant (uq (nome,
    # fazenda_id)) e o id é sequencial — sem comparar posse, um cliente lançava
    # (e via aplicado/baixado) o molde terapêutico de outro cliente (produtos,
    # doses), com o nome dele denormalizado no lançamento e ecoado na resposta.
    protocolo = session.get(ProtocoloSanitario, dados.protocolo_id)
    if not protocolo or protocolo.fazenda_id != fazenda_id:
        raise HTTPException(status_code=404, detail="Protocolo não encontrado")
    etapas = session.exec(
        select(ProtocoloSanitarioEtapa).where(ProtocoloSanitarioEtapa.protocolo_id == dados.protocolo_id).order_by(ProtocoloSanitarioEtapa.dia)
    ).all()
    if not etapas:
        raise HTTPException(status_code=400, detail="Este protocolo não tem etapas cadastradas")
    numeros = [n.strip() for n in dados.numeros_matriz if n.strip()]
    if not numeros:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal, lote ou categoria")

    if protocolo.eh_mastite and not dados.classificacao_mastite:
        raise HTTPException(status_code=400, detail="Informe a classificação da mastite (clínica, subclínica ou ambiental)")
    if protocolo.eh_mastite and len(numeros) > 1:
        raise HTTPException(status_code=400, detail="Protocolo de mastite: lance um animal por vez (classificação/CMT/tetos são específicos de cada caso)")
    if dados.classificacao_mastite and dados.classificacao_mastite not in CLASSIFICACOES_MASTITE:
        raise HTTPException(status_code=400, detail=f"Classificação de mastite inválida (aceitas: {', '.join(CLASSIFICACOES_MASTITE)})")
    for teto in dados.tetos_afetados:
        if teto not in TETOS_VALIDOS:
            raise HTTPException(status_code=400, detail=f"Teto inválido: {teto} (aceitos: {', '.join(TETOS_VALIDOS)})")

    # Etapas cadastradas por princípio ativo/classificação exigem escolher o
    # medicamento real no lançamento (guardado por etapa em cada aplicação).
    # Etapas de produto FIXO também podem vir com uma escolha — é o medicamento
    # SUBSTITUTO que o front oferece quando o item cadastrado no protocolo está
    # zerado/negativo/no mínimo; nesse caso, o substituto vale por cima do fixo.
    produto_por_etapa: dict[int, str | None] = {}
    for etapa in etapas:
        escolhido = (dados.escolhas_medicamento.get(str(etapa.id)) or "").strip()
        if getattr(etapa, "criterio_tipo", "medicamento") != "medicamento":
            if not escolhido:
                raise HTTPException(status_code=400, detail=f"Escolha o medicamento da etapa D{etapa.dia - protocolo.dia_inicial} ({etapa.produto}).")
            produto_por_etapa[etapa.id] = escolhido
        else:
            produto_por_etapa[etapa.id] = escolhido or None

    if dados.grau_mastite is not None and dados.grau_mastite not in GRAUS_MASTITE:
        raise HTTPException(status_code=400, detail="Grau de mastite inválido (aceitos: 1, 2 ou 3)")

    # Idempotência (mesmo padrão de producao.lancar_inducao_lactacao — ver o
    # comentário "Idempotência:" lá): duplo clique ou retry da fila offline
    # não pode duplicar. Mas ProtocoloSanitarioLancamento é POR ANIMAL, não
    # tem "cabeçalho" de lote como as outras 4 famílias — e, diferente
    # delas, também não tem `ativo`/`encerrado_em` (a Central de Protocolos
    # nem oferece cancelar/encerrar sanitário, "se resolve pela Agenda", ver
    # `_lancamento_ou_404`). Por isso a proteção aqui é diferente das outras:
    # em vez de recusar a chamada inteira quando encontra QUALQUER lançamento
    # igual, ela é PARCIAL — passa animal por animal e pula só quem já tem
    # (protocolo_id, data_inicio, numero_matriz) idêntico, criando
    # normalmente os que faltam. Isso cobre tanto o duplo clique puro (todos
    # os animais já existem, nada é criado) quanto o caso comum de "relançar
    # os mesmos N + 1 animal novo" (ex.: usuário lembrou de incluir mais uma
    # vaca no mesmo lote) — sem essa proteção parcial, os N repetidos
    # duplicariam de novo, mesmo a chamada sendo "quase" um retry.
    existentes_query = (
        select(ProtocoloSanitarioLancamento.numero_matriz)
        .where(ProtocoloSanitarioLancamento.protocolo_id == dados.protocolo_id)
        .where(ProtocoloSanitarioLancamento.data_inicio == dados.data_inicio)
        .where(ProtocoloSanitarioLancamento.numero_matriz.in_(numeros))
    )
    if fazenda_id is not None:
        # Estrito (== , não tolera fazenda_id nulo do candidato) — mesmo
        # motivo do bloco equivalente em producao.lancar_inducao_lactacao:
        # pular um animal como "já lançado" com base num registro órfão de
        # outra fazenda cruzaria tenant, contra o filtro do PR #488.
        existentes_query = existentes_query.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
    numeros_existentes = set(session.exec(existentes_query).all())

    protocolos = {protocolo.id: protocolo}
    lancamentos_criados = []
    avisos: list[str] = []
    pulados: list[str] = []
    # Cabeçalho do lote (ProtocoloSanitarioLote) — criado uma única vez para
    # esta chamada, na hora do primeiro animal de fato novo (uma chamada só
    # com animais já lançados — puro retry — não deve deixar um lote vazio
    # para trás). É o que dá ao Sanitário a mesma grade dia×animal com
    # marcar/desfazer/cancelar/encerrar que as outras 4 famílias já têm na
    # Central de Protocolos (ver ProtocoloSanitarioLote e central_protocolos.py).
    lote: ProtocoloSanitarioLote | None = None
    dia_final_etapas = max(e.dia for e in etapas)
    for numero in numeros:
        if numero in numeros_existentes:
            pulados.append(numero)
            continue
        if lote is None:
            lote = ProtocoloSanitarioLote(
                protocolo_id=dados.protocolo_id,
                nome_protocolo=gerar_nome_lancamento(
                    protocolo.nome, dados.data_inicio, protocolo.dia_inicial, dia_final_etapas,
                ),
                data_inicio=dados.data_inicio, responsavel=dados.responsavel, observacao=dados.observacao,
                usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
            )
            session.add(lote)
            session.commit()
            session.refresh(lote)
        del_no_caso = None
        ccs_ultima = None
        recidiva = None
        if protocolo.eh_mastite:
            # FURO DE MULTI-TENANT CORRIGIDO: sem o filtro de fazenda_id, uma
            # colisão de numero com outra fazenda (numero deixou de ser único
            # globalmente — ver Animal.numero) gravava o DEL de um animal
            # ALHEIO como snapshot do caso de mastite deste lançamento.
            query_animal_mastite = select(Animal).where(Animal.numero == numero)
            if fazenda_id is not None:
                query_animal_mastite = query_animal_mastite.where(Animal.fazenda_id == fazenda_id)
            animal = session.exec(query_animal_mastite).first()
            del_no_caso = animal.del_dias if animal else None
            # Última CCS do animal (ou do tanque, na falta) — snapshot do caso.
            query_ccs = select(QualidadeLeite).where(QualidadeLeite.numero_matriz == numero, QualidadeLeite.ccs != None)  # noqa: E711
            if fazenda_id is not None:
                query_ccs = query_ccs.where(QualidadeLeite.fazenda_id == fazenda_id)
            ult_ccs = session.exec(query_ccs.order_by(QualidadeLeite.data_coleta.desc())).first()
            ccs_ultima = ult_ccs.ccs if ult_ccs else None
            # Recidiva: caso de mastite anterior no MESMO teto com intervalo < 20 dias.
            tetos_novos = set(dados.tetos_afetados)
            if tetos_novos:
                limite = dados.data_inicio - timedelta(days=DIAS_RECIDIVA_MASTITE)
                # BUG DE SEGURANÇA CORRIGIDO: sem o filtro de fazenda_id, uma
                # colisão de numero_matriz com outra fazenda vazava data e
                # tetos de um caso de mastite ALHEIO no aviso de recidiva.
                query_anteriores = select(ProtocoloSanitarioLancamento).where(
                    ProtocoloSanitarioLancamento.numero_matriz == numero,
                    ProtocoloSanitarioLancamento.data_inicio >= limite,
                    ProtocoloSanitarioLancamento.data_inicio < dados.data_inicio,
                )
                if fazenda_id is not None:
                    query_anteriores = query_anteriores.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
                anteriores = session.exec(query_anteriores).all()
                for ant in anteriores:
                    tetos_ant = set((ant.tetos_afetados or "").split(",")) if ant.tetos_afetados else set()
                    if tetos_novos & tetos_ant:
                        recidiva = True
                        avisos.append(
                            f"Recidiva no(s) teto(s) {', '.join(sorted(tetos_novos & tetos_ant))} do animal {numero} "
                            f"(caso em {ant.data_inicio.strftime('%d/%m/%Y')}, menos de {DIAS_RECIDIVA_MASTITE} dias) — "
                            f"troque para o próximo tratamento."
                        )
                        break
        lancamento = ProtocoloSanitarioLancamento(
            protocolo_id=dados.protocolo_id, numero_matriz=numero, data_inicio=dados.data_inicio,
            lote_id=lote.id,
            responsavel=dados.responsavel, observacao=dados.observacao,
            classificacao_mastite=dados.classificacao_mastite,
            grau_mastite=dados.grau_mastite, agente=dados.agente,
            resultado_cmt=dados.resultado_cmt,
            tetos_afetados=",".join(dados.tetos_afetados) if dados.tetos_afetados else None,
            del_no_caso=del_no_caso, ccs_ultima=ccs_ultima, recidiva=recidiva,
            usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
        )
        session.add(lancamento)
        session.commit()
        session.refresh(lancamento)

        for etapa in etapas:
            data_prevista = dados.data_inicio + timedelta(days=etapa.dia - protocolo.dia_inicial)
            session.add(ProtocoloSanitarioAplicacao(
                lancamento_id=lancamento.id, etapa_id=etapa.id, data_prevista=data_prevista,
                dia=etapa.dia, numero_matriz=numero,
                produto=produto_por_etapa.get(etapa.id), fazenda_id=fazenda_id,
            ))
        session.commit()
        lancamentos_criados.append(_serializar_lancamento_protocolo(session, lancamento, protocolos))

    if pulados:
        avisos.append(
            f"{len(pulados)} animal(is) já tinha(m) este protocolo lançado nesta data e "
            f"foi(ram) ignorado(s) para não duplicar: {', '.join(sorted(pulados, key=chave_numero))}."
        )
    if not lancamentos_criados and numeros:
        # Nada novo foi criado (todo mundo já existia) — mesma convenção de
        # status das outras famílias: 200 em vez do 201 padrão da rota.
        response.status_code = 200
    return {
        "criados": len(lancamentos_criados), "pulados": len(pulados), "lancamentos": lancamentos_criados,
        "avisos": avisos,
    }


@router.get("/mastite/opcoes")
def opcoes_mastite() -> dict:
    """Listas padrão do lançamento de mastite (agentes, graus, tetos, CMT)."""
    return {
        "agentes": AGENTES_MASTITE, "graus": GRAUS_MASTITE, "tetos": TETOS_VALIDOS,
        "resultados_cmt": RESULTADOS_CMT, "classificacoes": CLASSIFICACOES_MASTITE,
    }


@router.get("/mastite/contexto")
def contexto_mastite(
    numero: str, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """DEL atual, última CCS e último CMT do animal — preenchidos automaticamente
    ao abrir um caso de mastite."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_animal = select(Animal).where(Animal.numero == numero)
    query_ccs = select(QualidadeLeite).where(QualidadeLeite.numero_matriz == numero, QualidadeLeite.ccs != None)  # noqa: E711
    query_caso = select(ProtocoloSanitarioLancamento).where(
        ProtocoloSanitarioLancamento.numero_matriz == numero, ProtocoloSanitarioLancamento.resultado_cmt != None  # noqa: E711
    )
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
        query_ccs = query_ccs.where(QualidadeLeite.fazenda_id == fazenda_id)
        query_caso = query_caso.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    ult_ccs = session.exec(query_ccs.order_by(QualidadeLeite.data_coleta.desc())).first()
    ult_caso = session.exec(query_caso.order_by(ProtocoloSanitarioLancamento.data_inicio.desc())).first()
    return {
        "numero": numero,
        "del_atual": animal.del_dias if animal else None,
        "ccs_ultima": ult_ccs.ccs if ult_ccs else None,
        "data_ccs": ult_ccs.data_coleta.isoformat() if ult_ccs else None,
        "cmt_ultimo": ult_caso.resultado_cmt if ult_caso else None,
    }


class MarcarCuraIn(BaseModel):
    lancamento_id: int
    curada: bool


def _marcar_cura_protocolo(lancamento_id: int, curada: bool, session: Session, fazenda_id: int | None) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lanc = session.get(ProtocoloSanitarioLancamento, lancamento_id)
    if not lanc or (lanc.fazenda_id != fazenda_id):
        raise HTTPException(status_code=404, detail="Lançamento de protocolo sanitário não encontrado")
    lanc.curada = curada
    session.add(lanc)
    session.commit()
    proximo = None if curada else "Caso não curado — inicie o próximo tratamento (protocolo seguinte)."
    return {"lancamento_id": lanc.id, "curada": lanc.curada, "proximo_tratamento": proximo}


@router.post("/protocolos/lancamentos/{lancamento_id}/cura")
def marcar_cura_protocolo(
    lancamento_id: int, dados: MarcarCuraIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Marca, no último dia do protocolo, se o caso foi curado ou não — para
    QUALQUER protocolo sanitário (mastite, vermifugação, etc.), não só
    mastite. Se não curado, sinaliza a necessidade do próximo tratamento."""
    if dados.lancamento_id != lancamento_id:
        raise HTTPException(status_code=400, detail="lancamento_id do corpo diverge da URL")
    return _marcar_cura_protocolo(lancamento_id, dados.curada, session, fazenda_id)


@router.post("/mastite/cura")
def marcar_cura_mastite(
    dados: MarcarCuraIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """RETROCOMPATIBILIDADE — o app em produção ainda chama esta rota. Apesar
    do nome ("mastite"), sempre serviu para marcar a cura de QUALQUER
    protocolo sanitário lançado, não só mastite. Mantida funcionando com a
    mesma lógica de `POST /protocolos/lancamentos/{id}/cura` (a rota nova,
    com nome correto, para a qual o frontend atual já aponta) — não remova
    sem migrar quem ainda chama esta."""
    return _marcar_cura_protocolo(dados.lancamento_id, dados.curada, session, fazenda_id)


# ---------------------------------------------------------------------------
# Colostragem e teste de sangue (IgG) — gravado a partir da calculadora em
# Lançamentos > Parto/nascimento, consumido pelo relatório sanitário de
# bezerras abaixo.
# ---------------------------------------------------------------------------
def _classe_colostro(brix: float | None) -> str | None:
    if brix is None:
        return None
    if brix > 25:
        return "ouro"
    if brix >= 18:
        return "prata"
    return "bronze"


def _classe_soro(brix: float | None) -> str | None:
    if brix is None:
        return None
    if brix >= 8.4:
        return "sucesso"
    if brix >= 8.1:
        return "alerta"
    return "falha"


def _classe_colostragem(brix: float | None, proteina: float | None) -> str | None:
    """Eficiência de transferência de imunidade passiva, em 4 níveis, por Brix
    sérico (%) OU proteína sérica total (g/dL) — o que estiver disponível
    (Brix tem prioridade). Faixas (Lombard et al.):
      excelente  Brix >9,4  · proteína >6,2   (meta: >50% das bezerras)
      boa        Brix 8,9-9,3 · proteína 5,8-6,1 (meta: 30%)
      aceitavel  Brix 8,1-8,8 · proteína 5,1-5,7 (meta: 15%)
      ruim       Brix <8,1  · proteína <5,1    (meta: <5%)
    """
    if brix is not None:
        if brix > 9.4:
            return "excelente"
        if brix >= 8.9:
            return "boa"
        if brix >= 8.1:
            return "aceitavel"
        return "ruim"
    if proteina is not None:
        if proteina > 6.2:
            return "excelente"
        if proteina >= 5.8:
            return "boa"
        if proteina >= 5.1:
            return "aceitavel"
        return "ruim"
    return None


class ColostragemIn(BaseModel):
    numero_animal: str
    tomou_colostro: bool | None = None
    litros_colostro: float | None = None
    brix_colostro: float | None = None
    data_colostro: date | None = None
    hora_parto: str | None = None
    hora_colostro: str | None = None
    peso_nascer_kg: float | None = None
    brix_soro: float | None = None
    proteina_serica: float | None = None
    apenas_colostro_po: bool | None = None
    data_teste_sangue: date | None = None
    observacao: str | None = None


@router.post("/colostragem")
def registrar_colostragem(
    dados: ColostragemIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """Grava (ou atualiza) o registro de colostragem/teste de sangue de uma
    cria — uma linha por animal, chamada pela calculadora de Parto/nascimento."""
    query_animal = select(Animal).where(Animal.numero == dados.numero_animal)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")

    query_registro = select(ColostragemBezerra).where(ColostragemBezerra.numero_animal == dados.numero_animal)
    if fazenda_id is not None:
        query_registro = query_registro.where(ColostragemBezerra.fazenda_id == fazenda_id)
    registro = session.exec(query_registro).first()
    if not registro:
        registro = ColostragemBezerra(
            animal_id=animal.id, numero_animal=dados.numero_animal, usuario_id=usuario_id_seguro(user),
            fazenda_id=fazenda_id,
        )
    for campo, valor in dados.model_dump(exclude={"numero_animal"}).items():
        setattr(registro, campo, valor)
    registro.atualizado_em = datetime.utcnow()
    session.add(registro)
    session.commit()
    session.refresh(registro)
    return registro.model_dump()


@router.get("/relatorio-bezerras")
def relatorio_sanitario_bezerras(
    faixa_etaria: str | None = Query(None, description="ate_12 | acima_12"),
    numero: str | None = None,
    lote: str | None = None,
    numeros: list[str] | None = Query(None),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Indicadores de colostragem e teste de sangue por animal, para identificar
    na fase adulta problemas que vieram de má colostragem. Filtra por faixa
    etária (bezerra <=12 meses / animal >12 meses, calculada por data_nasc),
    por animal, por lote atual (grupo_primario) ou por seleção de vários animais.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_animais = select(Animal).where(Animal.eh_semen == False)  # noqa: E712
    query_registros = select(ColostragemBezerra)
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
        query_registros = query_registros.where(ColostragemBezerra.fazenda_id == fazenda_id)
    animais = session.exec(query_animais).all()
    todos_registros = session.exec(query_registros).all()
    registros = {r.numero_animal: r for r in todos_registros}
    nomes = mapa_usuarios(session, {r.usuario_id for r in todos_registros})
    hoje = date.today()

    numeros_selecionados = {n.strip() for n in numeros} if numeros else None
    saida = []
    for a in animais:
        if numero and a.numero != numero:
            continue
        if lote and (a.grupo_primario or "") != lote:
            continue
        if numeros_selecionados and a.numero not in numeros_selecionados:
            continue

        idade_meses = round((hoje - a.data_nasc).days / 30.44, 1) if a.data_nasc else a.idade_meses
        if faixa_etaria == "ate_12" and (idade_meses is None or idade_meses > 12):
            continue
        if faixa_etaria == "acima_12" and (idade_meses is None or idade_meses <= 12):
            continue

        r = registros.get(a.numero)
        saida.append({
            "numero": a.numero, "nome": a.nome, "sexo": a.sexo, "categoria_abrev": a.categoria_abrev,
            "grupo_primario": a.grupo_primario, "data_nasc": a.data_nasc, "idade_meses": idade_meses,
            "ativo": a.ativo,
            "tomou_colostro": r.tomou_colostro if r else None,
            "litros_colostro": r.litros_colostro if r else None,
            "brix_colostro": r.brix_colostro if r else None,
            "classe_colostro": _classe_colostro(r.brix_colostro if r else None),
            "data_colostro": r.data_colostro if r else None,
            "hora_parto": r.hora_parto if r else None,
            "hora_colostro": r.hora_colostro if r else None,
            "peso_nascer_kg": r.peso_nascer_kg if r else None,
            "brix_soro": r.brix_soro if r else None,
            "proteina_serica": r.proteina_serica if r else None,
            "classe_soro": _classe_soro(r.brix_soro if r else None),
            "classe_colostragem": _classe_colostragem(r.brix_soro if r else None, r.proteina_serica if r else None),
            "apenas_colostro_po": (r.apenas_colostro_po if r else None) or False,
            # Sem mensuração = tem registro mas nenhum Brix/proteína sérica medido.
            "sem_mensuracao": bool(r) and (r.brix_soro is None and r.proteina_serica is None),
            "data_teste_sangue": r.data_teste_sangue if r else None,
            "usuario_nome": nomes.get(r.usuario_id) if r else None,
        })
    saida.sort(key=lambda x: x["numero"])
    return saida
