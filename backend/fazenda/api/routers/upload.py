"""
Router de upload de CSV — recebe arquivos do Ideagri e faz upsert no banco.
Endpoint: POST /upload/{tipo}

ISOLAMENTO POR FAZENDA (Fase 0): quase todo tipo de upload aqui é
"apaga tudo e reimporta" — o Ideagri sempre reenvia o histórico completo.
Sem filtro de fazenda, subir o CSV de UMA fazenda apagava os dados de TODAS
as outras (Servico, Sanidade, Estoque, Dieta, ControleLeiteiro,
ContaGerencial, CurvaABC, PlanoContaGerencial). Agora todo delete é
escopado pela fazenda atual e toda linha inserida é carimbada com ela — ver
`_escopo` e `_carimbar` abaixo.

Patrimônio é a ÚNICA exceção ao "apaga tudo e reimporta": vira upsert real
(ver `_upsert_patrimonio`) porque o item carrega dado que só existe no app
(depreciavel corrigido à mão, valor de mercado, plano de manutenção) e pode
estar referenciado por `ContaGerencial.patrimonio_id` — apagar e reinserir
destruía os dois.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.auth import get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    Animal,
    ContaGerencial,
    ControleLeiteiro,
    CurvaABC,
    Dieta,
    Estoque,
    Patrimonio,
    PlanoContaGerencial,
    Sanidade,
    Servico,
    Parto,
)
from fazenda.parsers.conta_gerencial import parse_conta_gerencial
from fazenda.parsers.controle_leiteiro import parse_controle_leiteiro
from fazenda.parsers.curva_abc import parse_curva_abc
from fazenda.parsers.dieta import parse_dieta
from fazenda.parsers.estoque import parse_estoque
from fazenda.parsers.geral import parse_geral
from fazenda.parsers.patrimonio import parse_patrimonio
from fazenda.parsers.plano_conta_gerencial import parse_plano_conta_gerencial
from fazenda.parsers.reprodutivo import parse_reprodutivo
from fazenda.parsers.sanidade import parse_sanidade
from fazenda.rules import lactacao as regras_lactacao

router = APIRouter(prefix="/upload", tags=["upload"])

TIPOS_VALIDOS = (
    "geral", "reprodutivo", "conta_gerencial", "estoque", "dieta", "controle_leiteiro",
    "sanidade", "curva_abc", "plano_conta_gerencial", "patrimonio",
)


def _escopo(query, modelo, fazenda_id: int | None):
    """Restringe a varredura de "apaga tudo antes de reimportar" à fazenda
    atual. `fazenda_id is None` = token legado sem fazenda selecionada: mantém
    o comportamento global de antes (não quebra instalação de fazenda única).

    Inclui as linhas com `fazenda_id IS NULL` (dados anteriores ao retrofit
    multi-fazenda) — senão cada upload deixaria para trás um histórico órfão
    que nunca mais seria substituído, duplicando tudo na tela.
    """
    if fazenda_id is None:
        return query
    return query.where(modelo.fazenda_id.in_((fazenda_id, None)))


def _carimbar(linhas, fazenda_id: int | None):
    """Carimba a fazenda atual em cada linha recém-parseada do CSV — sem isso
    a reimportação seguinte não acharia (nem substituiria) o que acabou de
    entrar, e o dado ficaria visível para as outras fazendas."""
    if fazenda_id is not None:
        for linha in linhas:
            linha.fazenda_id = fazenda_id
    return linhas


@router.post("/{tipo}")
async def upload_csv(
    tipo: str,
    file: UploadFile,
    session: Session = Depends(get_session),
    # Resolvedor único de escrita (nunca devolve fazenda_id nulo em silêncio,
    # ver fazenda.auth::resolver_fazenda_id_escrita) — antes usava o
    # tolerante get_fazenda_atual_id + fazenda_id_seguro: um token legado
    # (ou sessão "manter conectado" sem "fid") caía direto no ramo
    # `fazenda_id is None` de `_carimbar`, e o upload inteiro do Ideagri
    # (que reimporta o histórico completo de Animal/Servico/Parto/
    # ContaGerencial/Estoque/Dieta/Sanidade/ControleLeiteiro/CurvaABC/
    # PlanoContaGerencial/Patrimonio) nascia sem fazenda_id — exatamente o
    # padrão de "chamador fora do ciclo HTTP normal" citado no PR
    # claude/fazenda-id-raiz (aqui o ciclo HTTP existe, mas o token é que
    # não carrega a fazenda).
    fazenda_id: int = Depends(get_fazenda_id_escrita),
):
    """
    Recebe um arquivo CSV do Ideagri e realiza o upsert no banco.

    Tipos suportados:
    - geral: GERAL.csv
    - reprodutivo: Consulta_SQL_Dados_Reprodutivos_e_Produtivos_Versao_8.csv
    - conta_gerencial: CONTA_GERENCIAL.csv
    - estoque: ESTOQUE.csv
    """
    if tipo not in TIPOS_VALIDOS:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo '{tipo}' inválido. Use: {', '.join(TIPOS_VALIDOS)}",
        )

    content = await file.read()

    try:
        if tipo == "geral":
            return await _upsert_geral(content, session, fazenda_id)
        elif tipo == "reprodutivo":
            return await _upsert_reprodutivo(content, session, fazenda_id)
        elif tipo == "conta_gerencial":
            return await _upsert_conta_gerencial(content, session, fazenda_id)
        elif tipo == "estoque":
            return await _upsert_estoque(content, session, fazenda_id)
        elif tipo == "dieta":
            return await _upsert_dieta(content, session, fazenda_id)
        elif tipo == "controle_leiteiro":
            return await _upsert_controle_leiteiro(content, session, fazenda_id)
        elif tipo == "sanidade":
            return await _upsert_sanidade(content, session, fazenda_id)
        elif tipo == "curva_abc":
            return await _upsert_curva_abc(content, session, fazenda_id)
        elif tipo == "plano_conta_gerencial":
            return await _upsert_plano_conta_gerencial(content, session, fazenda_id)
        elif tipo == "patrimonio":
            return await _upsert_patrimonio(content, session, fazenda_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


async def _upsert_curva_abc(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    linhas = parse_curva_abc(content)
    for antigo in session.exec(_escopo(select(CurvaABC), CurvaABC, fazenda_id)).all():
        session.delete(antigo)
    for linha in _carimbar(linhas, fazenda_id):
        session.add(linha)
    session.commit()
    return {"tipo": "curva_abc", "registros": len(linhas)}


async def _upsert_plano_conta_gerencial(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    contas = parse_plano_conta_gerencial(content)
    for antigo in session.exec(_escopo(select(PlanoContaGerencial), PlanoContaGerencial, fazenda_id)).all():
        session.delete(antigo)
    session.commit()
    for conta in _carimbar(contas, fazenda_id):
        session.add(conta)
    session.commit()
    return {"tipo": "plano_conta_gerencial", "registros": len(contas)}


# Campos que o CSV do Ideagri realmente carrega — é só isto que uma
# reimportação pode atualizar num item já existente. Todo o resto
# (`depreciavel`, valor de mercado, plano de manutenção, `valor_por_unidade`)
# só existe no app: o CSV não tem essas colunas, então sobrescrever com o
# que "viria" de lá era sempre None/default, apagando o que o usuário já
# tinha corrigido/cadastrado na tela — ver ADR abaixo.
_CAMPOS_CSV_PATRIMONIO = (
    "tipo", "nome", "numero", "atividade_cultura", "data_imobilizacao",
    "metodo_depreciacao", "vida_util", "valor_residual", "quantidade",
    "unidade", "valor_total", "data_baixa",
)


async def _upsert_patrimonio(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    """Upsert (não mais "apaga tudo e reimporta" — ver histórico do módulo):
    o Ideagri reenvia o LISTA_DE_PATRIMONIO.csv completo a cada exportação,
    mas apagar tudo antes de reinserir destruía:
    - a marcação `depreciavel` corrigida à mão (o CSV não traz essa coluna,
      então ela nasce de novo do zero — errada — em todo item reimportado);
    - `valor_mercado_atual`/plano de manutenção, cadastrados só no app;
    - qualquer item cadastrado direto pelo app (sem número/linha no Ideagri
      ainda) — reimportar o Ideagri não pode apagar o que o app criou;
    - linhas referenciadas por `ContaGerencial.patrimonio_id`
      (fk sem ON DELETE, ver alembic c6d7e8f9a0b1) — o DELETE quebrava esse
      vínculo silenciosamente.

    Casamento: por `numero` quando o CSV traz número (é o identificador mais
    estável — mesmo bem, mesmo número, mesmo com nome reescrito); por
    (`nome`, `tipo`) quando não há número. Item batido é atualizado só nos
    campos que vêm do CSV (`_CAMPOS_CSV_PATRIMONIO`); item que existe no
    banco e não veio nesta rodada do CSV NÃO é apagado."""
    itens = _carimbar(parse_patrimonio(content), fazenda_id)

    existentes = session.exec(_escopo(select(Patrimonio), Patrimonio, fazenda_id)).all()
    por_numero = {e.numero: e for e in existentes if e.numero}
    por_nome_tipo = {(e.nome, e.tipo): e for e in existentes}

    inseridos, atualizados = 0, 0
    for novo in itens:
        existente = por_numero.get(novo.numero) if novo.numero else por_nome_tipo.get((novo.nome, novo.tipo))
        if existente:
            for campo in _CAMPOS_CSV_PATRIMONIO:
                setattr(existente, campo, getattr(novo, campo))
            session.add(existente)
            atualizados += 1
        else:
            session.add(novo)
            inseridos += 1

    session.commit()
    return {"tipo": "patrimonio", "registros": len(itens), "inseridos": inseridos, "atualizados": atualizados}


async def _upsert_geral(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    animais = _carimbar(parse_geral(content), fazenda_id)
    inserted, updated = 0, 0

    for animal_novo in animais:
        # `numero` NÃO é único entre fazendas — a vaca "18" existe em várias.
        # Sem o escopo, o upload de uma fazenda sobrescrevia a ficha da vaca
        # de mesmo número de outra.
        existing = session.exec(
            _escopo(select(Animal).where(Animal.numero == animal_novo.numero), Animal, fazenda_id)
        ).first()

        if existing:
            # Atualiza campos — exceto o lote, se ele já foi definido manualmente
            # (ver Animal.grupo_manual): uma movimentação feita no site não pode
            # ser silenciosamente revertida pelo próximo upload do GERAL.csv.
            for field in animal_novo.model_fields_set:
                if field in ("grupo_primario", "grupo_raw") and existing.grupo_manual:
                    continue
                setattr(existing, field, getattr(animal_novo, field))
            session.add(existing)
            updated += 1
        else:
            session.add(animal_novo)
            inserted += 1

    session.commit()
    return {"tipo": "geral", "inseridos": inserted, "atualizados": updated, "total": len(animais)}


async def _upsert_reprodutivo(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    servicos, partos = parse_reprodutivo(content)
    _carimbar(servicos, fazenda_id)
    _carimbar(partos, fazenda_id)

    # Serviços: limpa e reinsere (o CSV do Ideagri não tem chave natural
    # estável nos serviços), MAS preservando o que só o app produz.
    #
    # O bug que este bloco fecha: o apaga-tudo levava junto tudo que foi
    # lançado no app e não existe na planilha — a perda de prenhez lançada
    # pelo produtor (data E motivo), o retoque/reconfirmação marcados pelo
    # veterinário, o tipo de sêmen e o inseminador gravados na inseminação, e
    # o carimbo de quem lançou. Um upload de CSV bastava para apagar em
    # silêncio o aborto que alguém tinha acabado de registrar — e a matriz
    # voltava a constar como gestante.
    #
    # A chave de casamento é (matriz, data do serviço): é o que identifica a
    # mesma inseminação nos dois lados. Mesmo padrão dos `Parto` logo abaixo
    # (ver `preservados` lá).
    CAMPOS_SO_DO_APP = (
        "data_perda_prenhez", "motivo_perda_prenhez", "origem_perda_prenhez",
        "retoque", "data_reconfirmacao", "diagnostico_reconfirmacao",
        "tipo_semen", "inseminador", "usuario_id",
    )
    preservados_servico: dict[tuple[str, object], dict] = {}
    for s in session.exec(_escopo(select(Servico), Servico, fazenda_id)).all():
        guardado = {campo: getattr(s, campo, None) for campo in CAMPOS_SO_DO_APP}
        if any(v is not None for v in guardado.values()):
            preservados_servico[(s.numero_matriz, s.data_servico)] = guardado
        session.delete(s)
    session.commit()

    for servico in servicos:
        # Vincula ao animal se existir — dentro da fazenda, senão pegaria o
        # animal de mesmo número de outra fazenda.
        animal = session.exec(
            _escopo(select(Animal).where(Animal.numero == servico.numero_matriz), Animal, fazenda_id)
        ).first()
        if animal:
            servico.animal_id = animal.id
        salvo = preservados_servico.get((servico.numero_matriz, servico.data_servico))
        if salvo:
            for campo, valor in salvo.items():
                # `or` na direção certa: o que o CSV traz preenchido vence (a
                # planilha É a fonte para o que ela cobre — ex.: a coluna
                # "DATA DA PERDA DE PRENHEZ" do Ideagri); o guardado só
                # preenche o que veio vazio do CSV.
                if getattr(servico, campo, None) is None:
                    setattr(servico, campo, valor)
        session.add(servico)

    # Partos: reimporta sem DUPLICAR. Antes só inseria — cada reenvio do CSV
    # empilhava os mesmos partos (uma vaca com 10 uploads ficava com 10 partos
    # iguais). Agora, para cada (matriz, data) que vem no CSV, apagamos os
    # partos já existentes daquela data antes de reinserir. Partos lançados à
    # mão em OUTRAS datas (pelo app/site) são preservados.
    datas_csv = {(p.numero_matriz, p.data_parto) for p in partos}
    # O CSV do reprodutivo não traz o número da cria nem o sexo do gemelar
    # (só sexo_cria_1/2, gemelar e retenção) — preserva o que já estava
    # lançado à mão ou preenchido pelo backfill (ver backfill_numero_cria_
    # partos em reproducao.py) para o reenvio do CSV não apagar esse vínculo.
    preservados: dict[tuple[str, object], dict] = {}
    if datas_csv:
        for antigo in session.exec(_escopo(select(Parto), Parto, fazenda_id)).all():
            chave_antigo = (antigo.numero_matriz, antigo.data_parto)
            if chave_antigo in datas_csv:
                if antigo.numero_cria_1 or antigo.numero_cria_2 or antigo.gemelar_sexo:
                    preservados[chave_antigo] = {
                        "numero_cria_1": antigo.numero_cria_1, "numero_cria_2": antigo.numero_cria_2,
                        "gemelar_sexo": antigo.gemelar_sexo,
                    }
                session.delete(antigo)
        session.commit()

    for parto in partos:
        animal = session.exec(
            _escopo(select(Animal).where(Animal.numero == parto.numero_matriz), Animal, fazenda_id)
        ).first()
        if animal:
            parto.animal_id = animal.id
        salvo = preservados.get((parto.numero_matriz, parto.data_parto))
        if salvo:
            parto.numero_cria_1 = parto.numero_cria_1 or salvo["numero_cria_1"]
            parto.numero_cria_2 = parto.numero_cria_2 or salvo["numero_cria_2"]
            parto.gemelar_sexo = parto.gemelar_sexo or salvo["gemelar_sexo"]
        session.add(parto)

    session.commit()
    # Todo parto importado também precisa existir como LACTAÇÃO — senão o
    # controle leiteiro dessas vacas passa a ser recusado (ver
    # POST /producao/controles) por uma lactação que só falta materializar.
    # Reaproveita a MESMA reconstrução da migração de dados; idempotente
    # (ver rules/lactacao.py::backfill_lactacoes).
    if partos:
        from fazenda.rules.lactacao import backfill_lactacoes
        backfill_lactacoes(session, fazenda_id=fazenda_id)
        session.commit()
    return {
        "tipo": "reprodutivo",
        "servicos": len(servicos),
        "partos": len(partos),
    }


async def _upsert_conta_gerencial(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    contas = parse_conta_gerencial(content)

    # Limpa e reinserere (dados financeiros são sempre re-importados com janela completa)
    for c in session.exec(_escopo(select(ContaGerencial), ContaGerencial, fazenda_id)).all():
        session.delete(c)
    session.commit()

    for conta in _carimbar(contas, fazenda_id):
        session.add(conta)

    session.commit()
    return {"tipo": "conta_gerencial", "registros": len(contas)}


async def _upsert_estoque(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    items = parse_estoque(content)

    for c in session.exec(_escopo(select(Estoque), Estoque, fazenda_id)).all():
        session.delete(c)
    session.commit()

    for item in _carimbar(items, fazenda_id):
        session.add(item)

    session.commit()
    return {"tipo": "estoque", "registros": len(items)}


async def _upsert_dieta(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    itens = parse_dieta(content)

    for d in session.exec(_escopo(select(Dieta), Dieta, fazenda_id)).all():
        session.delete(d)
    session.commit()

    for item in _carimbar(itens, fazenda_id):
        session.add(item)

    session.commit()
    lotes = len({i.lote for i in itens if i.lote is not None})
    return {"tipo": "dieta", "registros": len(itens), "lotes": lotes}


async def _upsert_sanidade(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    registros = parse_sanidade(content)

    # Re-importação completa (histórico é sempre reenviado atualizado do Ideagri).
    for s in session.exec(_escopo(select(Sanidade), Sanidade, fazenda_id)).all():
        session.delete(s)
    session.commit()

    for reg in _carimbar(registros, fazenda_id):
        session.add(reg)

    session.commit()
    animais = len({r.numero_matriz for r in registros})
    return {"tipo": "sanidade", "registros": len(registros), "animais": animais}


async def _upsert_controle_leiteiro(content: bytes, session: Session, fazenda_id: int | None) -> dict:
    registros = parse_controle_leiteiro(content)

    # Re-importação completa (histórico é sempre reenviado com a janela escolhida).
    for r in session.exec(_escopo(select(ControleLeiteiro), ControleLeiteiro, fazenda_id)).all():
        session.delete(r)
    session.commit()

    # Mesma trava de `_gravar_controles(estrito=False)` (POST
    # /producao/controles) — sem lactação aberta na data, a linha é PULADA em
    # vez de gravada. Antes deste conserto, este era o ÚNICO dos 5 pontos de
    # entrada de ControleLeiteiro sem checagem nenhuma: uma novilha sem
    # `Parto`/`Lactacao` (caso relatado: "14") passava direto por aqui a cada
    # reimportação do CSV, mesmo com a trava já valendo pros outros 4
    # caminhos (lançamento manual, planilha de confirmação, app, Telegram).
    ignorados = 0
    gravados: list = []
    for reg in registros:
        if regras_lactacao.lactacao_aberta(
            session, numero_matriz=reg.numero_matriz, data=reg.data_controle, fazenda_id=fazenda_id,
        ) is None:
            ignorados += 1
            continue
        gravados.append(reg)

    for reg in _carimbar(gravados, fazenda_id):
        animal = session.exec(
            _escopo(select(Animal).where(Animal.numero == reg.numero_matriz), Animal, fazenda_id)
        ).first()
        if animal:
            reg.animal_id = animal.id
        session.add(reg)

    session.commit()
    vacas = len({r.numero_matriz for r in gravados})
    return {"tipo": "controle_leiteiro", "registros": len(gravados), "ignorados": ignorados, "vacas": vacas}
