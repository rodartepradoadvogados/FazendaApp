"""
Router de reprodução — dados achatados para o dashboard interativo de análise
e lançamento de diagnóstico de gestação.
"""
from __future__ import annotations

import html
import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import (
    Animal, ControleLeiteiro, EstoqueSemen, Lactacao, Lote, Parto, PesagemCorporal, ProtocoloIatf, ProtocoloIatfAplicacao,
    ProtocoloIatfEtapa, ProtocoloIatfHormonio, ProtocoloIatfLancamento,
    Sanidade, SeedFlag, Secagem, Servico, Usuario,
)
from fazenda.ordenacao import chave_numero
from fazenda.rules.agenda_reprodutiva_configuravel import SITUACOES, avaliar_card
from fazenda.rules.agenda_veterinario import classificar_rebanho
from fazenda.rules.aptidao import AptidaoResultado, avaliar_aptidao_no_banco, parametros_aptidao
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usuarios, usuario_id_seguro
from fazenda.rules import estoque_baixa
from fazenda.rules.email import enviar_email
from fazenda.rules.estado_reprodutivo import data_em_que_ficou_apta, estados_ao_vivo
from fazenda.rules.genetica import calcular_grau_sangue_cria
from fazenda.rules import lactacao as regras_lactacao
from fazenda.rules.nomenclatura_protocolo import gerar_nome_lancamento
from fazenda.rules.parto import (
    TIPO_PARTO_ABORTO, TIPO_PARTO_NATIMORTO, TIPO_PARTO_NORMAL, eh_parto_produtivo, proxima_ordem_parto,
)
from fazenda.rules.parametros import (
    dias_atraso_apos_aptidao_novilha, get_param, idade_apta_min_meses, idade_max_1a_cobertura_meses, peso_apta_min,
    pev_dias as pev_dias_param,
)
from fazenda.rules.perda_prenhez import (
    MOTIVOS_PERDA_PRENHEZ,
    MOTIVOS_PERDA_PRENHEZ_VALIDOS,
    ORIGEM_REINSEMINACAO,
    detectar_e_registrar_perda_por_reinseminacao,
    fechar_servicos_abertos_por_reinseminacao,
    servico_esta_em_aberto,
    servico_esta_positivo_vigente,
)
from fazenda.rules.programa_reprodutivo import (
    calcular_series,
    ciclos_21_dias,
    montar_perfil,
)
from fazenda.rules.protocolo_iatf import (
    PASSOS_PROTOCOLO_IATF_PADRAO as PASSOS_PROTOCOLO_IATF,
    DIA_INSEMINACAO_PADRAO,
    dia_inseminacao,
)
from fazenda.rules.reproducao_analise import agregar_mensal, analisar_servicos

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reproducao", tags=["reproducao"])


def _buscar_da_fazenda(session: Session, modelo, registro_id: int | None, fazenda_id: int | None):
    """Carrega UM registro por id JÁ FILTRANDO por fazenda na própria consulta,
    em vez de `session.get()` seguido de um `if` sobre o objeto carregado.

    A diferença não é estética. O `if` que estava em quase todas as rotas
    daqui era `registro.fazenda_id not in (None, fazenda_id)`, que TOLERAVA
    `fazenda_id=NULL` no registro. `servico`, `parto`, `secagem`, `sanidade` e
    `protocolo_iatf_lancamento` sobrevivem nulos justamente em instalação com
    2+ fazendas — é o que o relatório da migração
    029227481e9e_backfill_fazenda_id_nulo imprime como pendente quando não há
    pai de onde derivar nem fazenda única para atribuir. Enquanto a tolerância
    existia, um Servico órfão tinha diagnóstico/perda de prenhez editáveis por
    QUALQUER fazenda-cliente, só enumerando o id. Filtrando na consulta, "de
    outra fazenda" e "sem fazenda" caem os dois no mesmo lugar: não
    encontrado. 404, nunca 403 — responder 403 já confirmaria que o id existe.

    `fazenda_id is None` só acontece em ambiente onde o multi-fazenda NÃO está
    provisionado (tabela `fazenda` vazia — suíte de testes e instalação
    anterior à migração f1a2b3c4d5e6). Havendo qualquer fazenda cadastrada, a
    trava de porta (fazenda/auth.py::exigir_fazenda_selecionada, montada no
    router de Reprodução em main.py) recusa a requisição antes de chegar aqui.
    O caso está tratado explicitamente, não por omissão: sem tenant cadastrado
    não há tenant a isolar.

    Cópia deliberada de api/routers/agenda.py::_buscar_da_fazenda — o mesmo
    desenho, aplicado aos registros deste router (o helper ainda não tem um
    módulo compartilhado; quando tiver, os dois saem daqui juntos).
    """
    if registro_id is None:
        return None
    query = select(modelo).where(modelo.id == registro_id)
    if fazenda_id is not None:
        query = query.where(modelo.fazenda_id == fazenda_id)
    return session.exec(query).first()


# ---------------------------------------------------------------------------
# Trava de aptidão para serviço reprodutivo (ver fazenda/rules/aptidao.py)
#
# Antes desta trava, nenhum dos três pontos de entrada de serviço/IA validava
# nada além de "o animal existe": dava para inseminar bezerra, macho, animal
# baixado ou vaca prenhe — e reinseminar uma matriz gestante fazia o sistema
# INVENTAR sozinho uma perda de prenhez no serviço anterior. Agora esse caso
# exige uma confirmação explícita (`forcar: true`) de uma pessoa.
# ---------------------------------------------------------------------------
def _detalhe_aptidao(resultado: AptidaoResultado, numeros: list[str] | None = None) -> dict:
    """Corpo do 409. `msg` é a chave que o tratamento genérico de erro do
    frontend já lê (`mensagemErroApi`); `motivo`/`confirmavel` existem para a
    tela decidir se oferece o botão "confirmar mesmo assim" sem precisar
    interpretar o texto da mensagem."""
    return {
        "erro": "aptidao",
        "msg": resultado.mensagem,
        "motivo": resultado.motivo,
        "confirmavel": resultado.confirmavel,
        "animais": numeros or [],
    }


def _exigir_aptidao(
    session: Session, animal: Animal, *, data: date, fazenda_id: int | None, forcar: bool,
) -> AptidaoResultado:
    """Avalia a aptidão e levanta 409 quando o serviço não pode ser gravado.

    Devolve o resultado mesmo quando passa — o chamador usa isso para
    registrar no log que houve uma confirmação manual (`forcar`)."""
    resultado = avaliar_aptidao_no_banco(session, animal, data=data, fazenda_id=fazenda_id)
    if resultado.bloqueia(forcar):
        raise HTTPException(status_code=409, detail=_detalhe_aptidao(resultado, [animal.numero]))
    if not resultado.apta and forcar:
        # Auditoria completa da confirmação manual fica para a rodada da
        # trilha de eventos (Peça de auditoria de transição de estado); por
        # ora o registro é este log, que já distingue "o sistema decidiu" de
        # "uma pessoa confirmou".
        logger.info(
            "Aptidão forçada manualmente: matriz=%s motivo=%s data=%s", animal.numero, resultado.motivo, data,
        )
    return resultado


def carregar_perfis_reprodutivos(
    session: Session, fazenda_id: int | None, *, categoria: str = "todas",
) -> list:
    """Monta os `PerfilAnimal` de todas as fêmeas do rebanho, com os registros
    já indexados por número.

    Mesmo padrão de carregamento de `api/routers/indicadores.py` (indexa uma
    vez por número em vez de varrer as listas por animal — o rebanho tem
    milhares de serviços/partos).

    `categoria`: "todas" | "vaca" | "novilha". Vaca = já pariu alguma vez.
    """
    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    query_servicos = select(Servico)
    query_partos = select(Parto)
    query_iatf = select(ProtocoloIatfAplicacao)
    query_pesagem = select(PesagemCorporal)
    query_lactacao = select(Lactacao)
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
        query_iatf = query_iatf.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
        query_pesagem = query_pesagem.where(PesagemCorporal.fazenda_id == fazenda_id)
        query_lactacao = query_lactacao.where(Lactacao.fazenda_id == fazenda_id)

    femeas = [a for a in session.exec(query_animais).all() if not a.eh_semen and a.sexo != "M"]

    servicos_por: dict[str, list] = {}
    for s in session.exec(query_servicos).all():
        servicos_por.setdefault(s.numero_matriz, []).append(s)
    partos_por: dict[str, list] = {}
    for p in session.exec(query_partos).all():
        partos_por.setdefault(p.numero_matriz, []).append(p)
    iatf_por: dict[str, list] = {}
    for ap in session.exec(query_iatf).all():
        iatf_por.setdefault(ap.numero_matriz, []).append(ap)
    # Lactações abertas sem Parto (indução, aborto) — "parto virtual" pro DEL
    # e pro `eh_vaca` de `montar_perfil` (ver docstring lá). Mesma lógica de
    # agenda.py/indicadores.py — quem tem parto real sempre vence.
    inicio_lactacao_por: dict[str, date] = {}
    for lact in session.exec(query_lactacao).all():
        if lact.data_fim is not None:
            continue
        if lact.data_inicio is None:
            continue
        inicio_lactacao_por[lact.numero_matriz] = lact.data_inicio

    # Peso mais recente de cada animal — entra na aptidão da novilha nulípara.
    peso_por: dict[str, float] = {}
    ultima: dict[str, date] = {}
    for pes in session.exec(query_pesagem).all():
        if pes.numero_matriz not in ultima or pes.data_pesagem > ultima[pes.numero_matriz]:
            ultima[pes.numero_matriz] = pes.data_pesagem
            peso_por[pes.numero_matriz] = pes.peso_kg

    perfis = []
    for a in femeas:
        dados = a.model_dump()
        dados["peso_kg"] = peso_por.get(a.numero)
        perfil = montar_perfil(
            dados,
            partos=partos_por.get(a.numero, []),
            servicos=servicos_por.get(a.numero, []),
            aplicacoes_iatf=iatf_por.get(a.numero, []),
            data_inicio_lactacao=inicio_lactacao_por.get(a.numero),
        )
        if categoria != "todas" and perfil.categoria != categoria:
            continue
        perfis.append(perfil)
    return perfis


@router.get("/ciclos-21-dias")
def ciclos_de_21_dias(
    ancora: date = Query(..., description="Data de referência do ciclo"),
    modo: str = Query("fim", description='"inicio" (conta para frente) ou "fim" (conta para trás)'),
    n_ciclos: int = Query(6, ge=1, le=26, description="Quantos ciclos de 21 dias"),
    categoria: str = Query("todas", description='"todas" | "vaca" | "novilha"'),
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Risco de prenhez em ciclos de 21 dias — o BREDSUM\\E do DairyComp.

    Devolve, por ciclo: BR ELIG (elegíveis para inseminação) → BRED (servidas)
    → PG ELIG (elegíveis para prenhez) → PREG (prenhes), com as três taxas e a
    lista nominal de animais em cada balde, para o usuário conferir na tela
    exatamente quem entrou e quem saiu de cada denominador.

    A âncora é livre: `modo="inicio"` conta 21 dias para frente a partir dela;
    `modo="fim"` conta para trás. Substitui a ancoragem fechada anterior, presa
    ao D11 do protocolo IATF ou à data da inseminação.

    Ver `fazenda.rules.programa_reprodutivo` para o modelo lógico completo
    (regras R1–R9) que define cada um desses conjuntos.
    """
    from fazenda.rules.parametros import (
        dias_minimos_no_ciclo, dias_reinseminacao_min, dias_resultado_conhecido, get_param,
        idade_apta_min_meses,
        idade_max_1a_cobertura_meses, meta_taxa_concepcao, meta_taxa_prenhez,
        meta_taxa_servico, pev_dias, peso_apta_min,
    )

    if modo not in ("inicio", "fim"):
        raise HTTPException(status_code=400, detail='modo deve ser "inicio" ou "fim"')
    if categoria not in ("todas", "vaca", "novilha"):
        raise HTTPException(status_code=400, detail='categoria deve ser "todas", "vaca" ou "novilha"')

    fazenda_id = fazenda_id_seguro(fazenda_id)
    perfis = carregar_perfis_reprodutivos(session, fazenda_id, categoria=categoria)
    ciclos = ciclos_21_dias(ancora, modo=modo, n_ciclos=n_ciclos)

    resultados = calcular_series(
        perfis, ciclos, date.today(),
        pev_dias=pev_dias(),
        dias_minimos=dias_minimos_no_ciclo(),
        dias_resultado=dias_resultado_conhecido(),
        # Janela mínima de cio de repasse — a mesma que a tela de Reprodução
        # já usa. Sem passar aqui, o motor cairia no piso embutido e o campo
        # editável em Configurações não faria efeito nenhum (foi por ser um
        # campo assim, editável e inerte, que `idade_maturidade_novilha` foi
        # aposentado).
        dias_minimos_repasse=dias_reinseminacao_min(),
        del_max_1o_servico=int(get_param("meta_del_max_1o_servico", 100) or 100),
        idade_apta_dias=int(idade_apta_min_meses() * 30.44),
        idade_atraso_dias=int(idade_max_1a_cobertura_meses() * 30.44),
        peso_apta_kg=peso_apta_min(),
    )

    linhas = [r.para_dict() for r in resultados]
    # Média ponderada pelo denominador de cada ciclo — a média simples das
    # porcentagens daria peso igual a um ciclo de 3 vacas e a um de 300.
    def _ponderada(campo: str, denominador: str) -> float | None:
        total_den = sum(l[denominador] for l in linhas)
        if not total_den:
            return None
        soma = sum((l[campo] or 0) * l[denominador] for l in linhas)
        return round(soma / total_den, 1)

    # `animais_avaliados` já se chamou assim sem merecer: media quantos perfis
    # foram CARREGADOS do banco para o cálculo, não quantos de fato passaram
    # por algum crivo do BREDSUM\E. Uma vaca gestante o período todo, ou uma
    # baixada antes do primeiro ciclo, entrava nessa contagem do mesmo jeito
    # que uma que foi de fato avaliada — nome prometendo mais do que a conta
    # entregava. A união de br_elig/bred/pg_elig/preg de todos os ciclos já
    # responde "quem passou por pelo menos um balde", sem inventar cálculo
    # novo: cada `ResultadoCiclo` já carrega essas listas. O valor antigo (o
    # tamanho do rebanho carregado) não desaparece — seria informação querida
    # por quem calibra o carregamento em si — só passa a ter nome que não
    # mente: `animais_carregados`. Mesmo princípio de `ultimo_por_animal` em
    # rules/indicadores.py, que preservou um acumulado ao ser destronado do
    # card.
    animais_avaliados: set[str] = set()
    for r in resultados:
        animais_avaliados.update(r.br_elig, r.bred, r.pg_elig, r.preg)

    return {
        "ancora": ancora.isoformat(),
        "modo": modo,
        "categoria": categoria,
        "periodo": {"inicio": ciclos[0].inicio.isoformat(), "fim": ciclos[-1].fim.isoformat()},
        "ciclos": linhas,
        "resumo": {
            "taxa_servico": _ponderada("taxa_servico", "br_elig"),
            "taxa_prenhez": _ponderada("taxa_prenhez", "pg_elig"),
            "taxa_concepcao": _ponderada("taxa_concepcao", "servicos_com_resultado"),
            "animais_avaliados": len(animais_avaliados),
            "animais_carregados": len(perfis),
        },
        "metas": {
            "taxa_servico": meta_taxa_servico(),
            "taxa_prenhez": meta_taxa_prenhez(),
            "taxa_concepcao": meta_taxa_concepcao(),
        },
        "parametros": {
            "pev_dias": pev_dias(),
            "dias_minimos_no_ciclo": dias_minimos_no_ciclo(),
            "dias_resultado_conhecido": dias_resultado_conhecido(),
        },
        # Aviso do rodapé da tela. Ficou desatualizado quando `a_descartar_em`
        # passou a existir (ver `descartada_em` em rules/programa_reprodutivo.py):
        # dizia ao usuário que a marcação NUNCA tem data, o que virou meia
        # verdade — passou a valer só para quem foi marcado antes da coluna.
        # Texto que engana é pior que aviso nenhum, ainda mais um que serve
        # justamente para o usuário calibrar quanta fé ter na série histórica.
        "ressalva_historica": (
            "A marcação \"a descartar\" passou a ser datada: quem for marcado de agora "
            "em diante sai do cálculo só a partir da data da marcação. Quem já estava "
            "marcado antes disso não tem data registrada e segue valendo para todo o "
            "período. Baixas sempre foram datadas e são reconstruídas corretamente."
        ),
    }


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


def backfill_fechar_servicos_abertos(session: Session) -> None:
    """Aplica ao histórico a mesma regra que passou a valer nos lançamentos
    novos: serviço em aberto que já foi sucedido por outro na mesma lactação
    fecha como NEGATIVO (ver rules/perda_prenhez.fechar_servicos_abertos_por_reinseminacao).

    Sem isto, a taxa de concepção só melhora dos lançamentos novos em diante e
    o histórico continua mostrando ABERTO em serviços de meses atrás — que foi
    exatamente a reclamação que originou a correção. A base do produtor tem 21
    registros vindos do CSV do Ideagri com o texto "ABERTO".

    Roda UMA vez (SeedFlag) e é conservador: só toca serviço que a regra dos
    lançamentos novos também tocaria, e carimba `origem_diagnostico` para que
    dê para distinguir (e desfazer) o que foi inferido do que foi lançado por
    gente."""
    chave = "backfill_fechar_servicos_abertos_v1"
    if session.get(SeedFlag, chave):
        return

    servicos = session.exec(select(Servico).order_by(Servico.data_servico)).all()
    partos = session.exec(select(Parto)).all()

    ultimo_parto: dict[tuple[object, str], date] = {}
    for p in partos:
        if not p.numero_matriz or not p.data_parto:
            continue
        k = (p.fazenda_id, p.numero_matriz)
        if k not in ultimo_parto or p.data_parto > ultimo_parto[k]:
            ultimo_parto[k] = p.data_parto

    # Data do serviço MAIS RECENTE de cada matriz — só o que vier antes dele
    # (e depois do último parto) pode ter sido superado por uma nova tentativa.
    mais_recente: dict[tuple[object, str], date] = {}
    for s in servicos:
        if not s.numero_matriz or not s.data_servico:
            continue
        k = (s.fazenda_id, s.numero_matriz)
        if k not in mais_recente or s.data_servico > mais_recente[k]:
            mais_recente[k] = s.data_servico

    for s in servicos:
        if not s.numero_matriz or not s.data_servico:
            continue
        k = (s.fazenda_id, s.numero_matriz)
        if s.data_servico >= mais_recente.get(k, s.data_servico):
            continue  # é o último da matriz — pode legitimamente estar aguardando toque
        parto = ultimo_parto.get(k)
        if parto is not None and s.data_servico <= parto:
            continue  # lactação anterior
        if not servico_esta_em_aberto(s):
            continue
        s.diagnostico = "NEGATIVO"
        s.origem_diagnostico = ORIGEM_REINSEMINACAO
        session.add(s)

    session.add(SeedFlag(chave=chave))
    session.commit()


def backfill_categoria_crias(session: Session) -> None:
    """Corrige crias já cadastradas via /parto que ficaram sem categoria (o
    registro só define categoria a partir de agora — ver registrar_parto).
    Roda UMA vez (guardada por SeedFlag): qualquer Animal com mãe registrada
    (mae_numero preenchido, ou seja, veio de um parto) e sem categoria
    completa ainda entra em "Bezerra/o Mamando"; o próximo upload do
    GERAL.csv (Ideagri) segue tendo prioridade e substitui esse valor."""
    chave = "backfill_categoria_crias_v1"
    if session.get(SeedFlag, chave):
        return
    crias = session.exec(
        select(Animal).where(Animal.mae_numero.is_not(None), Animal.categoria_completa.is_(None))
    ).all()
    for a in crias:
        a.categoria_completa = "Bezerra Mamando" if a.sexo == "F" else "Bezerro Mamando"
        a.categoria_abrev = "Bezerra" if a.sexo == "F" else "Bezerro"
        session.add(a)
    session.add(SeedFlag(chave=chave))
    session.commit()


def backfill_numero_cria_partos(session: Session) -> None:
    """Associa retroativamente numero_cria_1/2 (e gemelar_sexo) aos partos que
    vieram do upload do CSV reprodutivo — esse CSV não traz o número da cria
    nem o sexo do gemelar, só quem é registrado via /reproducao/parto tem
    isso hoje. Casa pela mãe (Animal.mae_numero == Parto.numero_matriz) e
    pela data de nascimento próxima da data do parto (± 2 dias, cobre
    diferenças de fuso/lançamento tardio). Roda UMA vez (SeedFlag); só
    preenche quando a combinação é inequívoca — deixa de fora (para revisão
    manual) qualquer parto com mais candidatos do que o esperado."""
    chave = "backfill_numero_cria_partos_v1"
    if session.get(SeedFlag, chave):
        return
    por_mae: dict[str, list[Animal]] = {}
    for a in session.exec(select(Animal).where(Animal.mae_numero.is_not(None))).all():
        por_mae.setdefault(a.mae_numero, []).append(a)

    partos = session.exec(
        select(Parto).where(Parto.numero_cria_1.is_(None), Parto.numero_cria_2.is_(None))
    ).all()
    for p in partos:
        if not p.data_parto:
            continue
        candidatos = [
            a for a in por_mae.get(p.numero_matriz, [])
            if a.data_nasc and abs((a.data_nasc - p.data_parto).days) <= 2
        ]
        if not candidatos:
            continue
        esperado = 2 if p.gemelar else 1
        if len(candidatos) > esperado:
            continue  # ambíguo — mais crias batendo do que o parto indica, não arrisca
        # Prioriza o candidato cujo sexo bate com sexo_cria_1 (já vindo do CSV),
        # depois ordena por número para ficar determinístico.
        candidatos.sort(key=lambda a: (0 if (p.sexo_cria_1 and a.sexo == p.sexo_cria_1) else 1, a.numero))
        p.numero_cria_1 = candidatos[0].numero
        if len(candidatos) > 1:
            p.numero_cria_2 = candidatos[1].numero
            if not p.gemelar_sexo and candidatos[0].sexo and candidatos[1].sexo:
                combo = "".join(sorted(candidatos[0].sexo + candidatos[1].sexo))
                p.gemelar_sexo = {"FF": "FF", "FM": "FM", "MM": "MM"}.get(combo)
        session.add(p)
    session.add(SeedFlag(chave=chave))
    session.commit()

# Cronograma padrão (D0/D7/D9 de hormônio + D11 de inseminação) — importado de
# fazenda.rules.protocolo_iatf, que também sabe calcular o cronograma de um
# molde com dias livres (ver _passos_do_lancamento abaixo). Usado quando o
# lançamento NÃO referencia um molde (hormônios digitados na hora) e no
# retroativo automático da inseminação avulsa — os dois únicos casos sem
# etapas de molde das quais derivar os dias.


def _passos_do_lancamento(session: Session, protocolo_id: int | None) -> list[tuple[int, str]]:
    """Os passos (dia, descrição-padrão) deste lançamento: do MOLDE cadastrado,
    se um foi escolhido — respeitando os dias livres que o usuário definiu —,
    ou o cronograma clássico D0/D7/D9/D11, se o lançamento for ad-hoc (sem
    molde, hormônios digitados na hora)."""
    if protocolo_id is None:
        return PASSOS_PROTOCOLO_IATF
    etapas = session.exec(
        select(ProtocoloIatfEtapa).where(ProtocoloIatfEtapa.protocolo_id == protocolo_id)
    ).all()
    if not etapas:
        return PASSOS_PROTOCOLO_IATF
    dias_hormonio = sorted({e.dia for e in etapas})
    passos = [(d, f"Hormônio(s) do dia D{d}") for d in dias_hormonio]
    passos.append((dia_inseminacao(dias_hormonio), "Inseminação (IATF)"))
    return passos


@router.get("/agenda-veterinario")
def agenda_veterinario(
    data: date | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Roteiro do veterinário do serviço: classifica o rebanho fêmea em 9 listas
    (ver fazenda.rules.agenda_veterinario para os critérios de cada uma).

    Aceita uma data de referência opcional (`?data=AAAA-MM-DD`, #490) para um
    cenário projetado: quando a visita do veterinário será numa data futura
    (a próxima visita reprodutiva), os dias inseminada/dias para parto são recalculados
    como se aquela fosse "hoje" — com os dados já lançados, sem prever novos
    lançamentos que ainda vão acontecer até lá.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje_real = date.today()
    hoje = data or hoje_real
    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    animais = [a.model_dump() for a in session.exec(query_animais).all()]

    query_servicos = select(Servico)
    if fazenda_id is not None:
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
    servico_por_animal: dict[str, dict] = {}
    for s in session.exec(query_servicos).all():
        atual = servico_por_animal.get(s.numero_matriz)
        if not atual or (s.data_servico and (not atual.get("data_servico") or s.data_servico > atual["data_servico"])):
            servico_por_animal[s.numero_matriz] = s.model_dump()

    # A pesagem era a ÚNICA subconsulta do roteiro sem filtro de fazenda
    # (achado 9 da auditoria). `numero_matriz` é texto livre sem FK e
    # `animal.numero` não é mais único entre fazendas (migração c24befa94c1b):
    # a vaca "500" da outra fazenda entregava o peso dela para o roteiro
    # daqui — e o peso é o que decide novilha apta/inapta.
    query_pesagens = select(PesagemCorporal)
    if fazenda_id is not None:
        query_pesagens = query_pesagens.where(PesagemCorporal.fazenda_id == fazenda_id)
    peso_por_animal: dict[str, float] = {}
    ultima_data: dict[str, date] = {}
    for p in session.exec(query_pesagens).all():
        atual = ultima_data.get(p.numero_matriz)
        if not atual or p.data_pesagem > atual:
            ultima_data[p.numero_matriz] = p.data_pesagem
            peso_por_animal[p.numero_matriz] = p.peso_kg

    # Parto e secagem de rotina desligam a cobrança de reconfirmação sozinhos
    # — ver fazenda.rules.perda_prenhez.retoque_esta_resolvido e o critério
    # completo em fazenda.rules.agenda_veterinario.
    query_partos = select(Parto)
    if fazenda_id is not None:
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
    ultimo_parto_por_animal: dict[str, date] = {}
    for p in session.exec(query_partos).all():
        if p.data_parto and (p.numero_matriz not in ultimo_parto_por_animal or p.data_parto > ultimo_parto_por_animal[p.numero_matriz]):
            ultimo_parto_por_animal[p.numero_matriz] = p.data_parto

    query_secagens = select(Secagem).where(Secagem.motivo == "rotina")
    if fazenda_id is not None:
        query_secagens = query_secagens.where(Secagem.fazenda_id == fazenda_id)
    ultima_secagem_rotina_por_animal: dict[str, date] = {}
    for s in session.exec(query_secagens).all():
        if s.data_secagem and (
            s.numero_matriz not in ultima_secagem_rotina_por_animal
            or s.data_secagem > ultima_secagem_rotina_por_animal[s.numero_matriz]
        ):
            ultima_secagem_rotina_por_animal[s.numero_matriz] = s.data_secagem

    query_lotes_pre_parto = select(Lote).where(Lote.pre_parto == True)  # noqa: E712
    if fazenda_id is not None:
        query_lotes_pre_parto = query_lotes_pre_parto.where(Lote.fazenda_id == fazenda_id)
    grupos_pre_parto = {f"{l.codigo} - {l.nome}" for l in session.exec(query_lotes_pre_parto).all()}

    listas = classificar_rebanho(
        animais, servico_por_animal, peso_por_animal, hoje,
        ultimo_parto_por_animal=ultimo_parto_por_animal,
        ultima_secagem_rotina_por_animal=ultima_secagem_rotina_por_animal,
        grupos_pre_parto=grupos_pre_parto,
    )

    # Próxima visita reprodutiva sugerida (#571): último serviço do rebanho +
    # intervalo configurado em Parâmetros. Intervalo 0/vazio => nenhuma data
    # é sugerida (agendamento automático "desligado") — o front então oferece
    # a janela suspensa para o usuário configurar o intervalo.
    from fazenda.rules.parametros import intervalo_visita_reprodutiva as _intervalo_visita_reprodutiva

    datas_servico = [s["data_servico"] for s in servico_por_animal.values() if s.get("data_servico")]
    ultimo_servico = max(datas_servico) if datas_servico else None
    intervalo = _intervalo_visita_reprodutiva()
    proxima_visita_reprodutiva = (
        ultimo_servico + timedelta(days=intervalo) if (ultimo_servico and intervalo > 0) else None
    )

    return {
        "data_referencia": hoje.isoformat(),
        "projetado": hoje != hoje_real,
        "listas": listas,
        "totais": {k: len(v) for k, v in listas.items()},
        "ultimo_servico": ultimo_servico.isoformat() if ultimo_servico else None,
        "proxima_visita_reprodutiva": proxima_visita_reprodutiva.isoformat() if proxima_visita_reprodutiva else None,
        "intervalo_visita_reprodutiva": intervalo,
    }


class CardAgendaReprodutivaIn(BaseModel):
    """Definição de um card configurável da Agenda Reprodutiva — os 4 eixos
    (ver fazenda.rules.agenda_reprodutiva_configuravel). `periodos` é uma
    lista de (de, ate) em dias; o eixo do dia depende de `situacao` (PEV/
    vazia: dias desde o parto; inseminada: dias desde o serviço; gestante:
    dias de gestação). Vazia = sem restrição de período."""

    categoria: str = "todas"  # "vaca" | "novilha" | "todas"
    lotes: list[str] = []
    situacao: str  # "pev" | "inseminada" | "gestante" | "vazia" | "vazia_atrasada" | "a_descartar"
    periodos: list[tuple[int, int]] = []
    somente_atrasadas: bool = False
    exceto_atrasadas: bool = False


@router.post("/agenda-reprodutiva/card")
def agenda_reprodutiva_card(
    config: CardAgendaReprodutivaIn,
    data: date | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Resultado de UM card configurável da Agenda Reprodutiva (ver proposta:
    substitui os cards fixos de `/agenda-veterinario`, exceto "Vazias por
    diagnóstico" e "Pendentes de classificação", que não são situação
    reprodutiva e continuam só naquele endpoint).

    Mesmo padrão de coleta de dados de `/agenda-veterinario` acima —
    `aplicacoes_iatf=[]` porque este endpoint não carrega
    ProtocoloIatfAplicacao: um animal em protocolo aparece como PEV/APTA/
    ATRASADA conforme o resto dos dados, mesma limitação aceita de
    `recria._contexto_categoria` (ver o comentário lá)."""
    if config.situacao not in SITUACOES:
        raise HTTPException(status_code=422, detail=f"situacao inválida: {config.situacao}")
    if config.categoria not in ("todas", "vaca", "novilha"):
        raise HTTPException(status_code=422, detail=f"categoria inválida: {config.categoria}")
    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje = data or date.today()

    query_animais = select(Animal).where(Animal.ativo == True)  # noqa: E712
    if fazenda_id is not None:
        query_animais = query_animais.where(Animal.fazenda_id == fazenda_id)
    animais = [a.model_dump() for a in session.exec(query_animais).all() if not a.eh_semen and a.sexo != "M"]

    query_servicos = select(Servico)
    query_partos = select(Parto)
    query_pesagens = select(PesagemCorporal)
    if fazenda_id is not None:
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
        query_pesagens = query_pesagens.where(PesagemCorporal.fazenda_id == fazenda_id)
    servicos = session.exec(query_servicos).all()
    partos = session.exec(query_partos).all()

    query_lactacao = select(Lactacao)
    if fazenda_id is not None:
        query_lactacao = query_lactacao.where(Lactacao.fazenda_id == fazenda_id)
    # Lactações abertas sem parto produtivo (indução, aborto com abertura): a
    # data_inicio é o "parto virtual" para DEL/PEV em classificar_animal, mesma
    # lógica de /agenda/ e /indicadores/estados-reprodutivos.
    inicio_lactacao_por_animal: dict[str, date] = {}
    for lact in session.exec(query_lactacao).all():
        if lact.data_fim is not None and lact.data_fim <= hoje:
            continue
        if lact.data_inicio is None:
            continue
        inicio_lactacao_por_animal[lact.numero_matriz] = lact.data_inicio

    peso_por_animal: dict[str, float] = {}
    pesagens_por_animal: dict[str, list[tuple[date, float]]] = {}
    for p in session.exec(query_pesagens).all():
        if not p.peso_kg or not p.data_pesagem:
            continue
        pesagens_por_animal.setdefault(p.numero_matriz, []).append((p.data_pesagem, p.peso_kg))
    for numero, lista in pesagens_por_animal.items():
        lista.sort(key=lambda item: item[0])
        peso_por_animal[numero] = lista[-1][1]

    pev = pev_dias_param()
    del_max = int(get_param("meta_del_max_1o_servico", 100) or 100)
    idade_apta_dias = round(idade_apta_min_meses() * 30.44)
    idade_atraso_dias = round(idade_max_1a_cobertura_meses() * 30.44)
    peso_apta_kg = peso_apta_min()
    dias_atraso_apos_aptidao = dias_atraso_apos_aptidao_novilha()

    datas_ficou_apta: dict[str, date] = {}
    for a in animais:
        numero = a["numero"]
        d = data_em_que_ficou_apta(
            data_nasc=a.get("data_nasc"), idade_apta_dias=idade_apta_dias,
            pesagens=pesagens_por_animal.get(numero, []), peso_apta_kg=peso_apta_kg,
        )
        if d is not None:
            datas_ficou_apta[numero] = d

    estados = estados_ao_vivo(
        animais, hoje=hoje, partos=partos, servicos=servicos, aplicacoes_iatf=[],
        pev_dias=pev, del_max_1o_servico=del_max, peso_por_animal=peso_por_animal,
        idade_apta_dias=idade_apta_dias, idade_atraso_dias=idade_atraso_dias, peso_apta_kg=peso_apta_kg,
        dias_atraso_apos_aptidao=dias_atraso_apos_aptidao, datas_ficou_apta_por_animal=datas_ficou_apta,
        inicio_lactacao_por_animal=inicio_lactacao_por_animal,
    )

    itens = avaliar_card(
        categoria=config.categoria, lotes=config.lotes, situacao=config.situacao,
        periodos=[tuple(p) for p in config.periodos],
        somente_atrasadas=config.somente_atrasadas, exceto_atrasadas=config.exceto_atrasadas,
        animais=animais, estados=estados,
    )
    itens.sort(key=lambda it: chave_numero(it.get("numero")))

    return {
        "data_referencia": hoje.isoformat(),
        "total": len(itens),
        "itens": [
            {
                "numero_matriz": it.get("numero"),
                "categoria": it.get("categoria_normalizada"),
                "lote_atual": it.get("grupo_primario"),
                "estado": it.get("estado"),
                "del_dias": it.get("del_dias"),
                "dias_gestacao": it.get("dias_gestacao"),
                "dias_desde_servico": it.get("dias_desde_servico"),
                "data_servico": it.get("data_servico"),
                "parto_previsto": it.get("parto_previsto"),
            }
            for it in itens
        ],
    }


def _ultimo_servico(session: Session, numero_matriz: str, fazenda_id: int | None = None) -> Servico | None:
    query = select(Servico).where(Servico.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    return session.exec(query.order_by(Servico.data_servico.desc())).first()


@router.get("/animais/{numero_matriz}/ultimo-diagnostico")
def ultimo_diagnostico(
    numero_matriz: str,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict | None:
    """Último serviço/IA da matriz (com diagnóstico, se já lançado) — usado
    tanto na Agenda do veterinário quanto na ficha do animal para montar o
    e-mail de "enviar último DG" (ver enviar_ultimo_diagnostico abaixo)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    servico = _ultimo_servico(session, numero_matriz, fazenda_id=fazenda_id)
    return servico.model_dump() if servico else None


class EnviarDiagnosticoIn(BaseModel):
    destinatario: str


@router.post("/animais/{numero_matriz}/diagnostico/enviar")
def enviar_ultimo_diagnostico(
    numero_matriz: str,
    dados: EnviarDiagnosticoIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Envia por e-mail um resumo do último diagnóstico de gestação da
    matriz — mesmo mecanismo de e-mail do recibo financeiro (#505), mas sem
    PDF anexado (o corpo do e-mail já traz os dados do diagnóstico)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if not (dados.destinatario or "").strip():
        raise HTTPException(status_code=400, detail="Informe o e-mail do destinatário")
    servico = _ultimo_servico(session, numero_matriz, fazenda_id=fazenda_id)
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {numero_matriz}")
    if not servico.data_diagnostico:
        raise HTTPException(status_code=400, detail=f"A matriz {numero_matriz} ainda não tem diagnóstico de gestação registrado")

    fmt = lambda d: d.strftime("%d/%m/%Y") if d else "—"  # noqa: E731
    # BUG DE SEGURANÇA CORRIGIDO: numero_matriz/diagnostico/metodo_diagnostico
    # não têm validação de valores fechados no backend — sem escape, um
    # cliente de e-mail que renderiza HTML executaria markup injetado.
    linhas = [
        f"<p><b>Matriz:</b> {html.escape(numero_matriz)}</p>",
        f"<p><b>Data do serviço:</b> {fmt(servico.data_servico)}</p>",
        f"<p><b>Data do diagnóstico:</b> {fmt(servico.data_diagnostico)}</p>",
        f"<p><b>Resultado:</b> {html.escape(servico.diagnostico or '—')}</p>",
    ]
    if servico.metodo_diagnostico:
        linhas.append(f"<p><b>Método:</b> {html.escape(servico.metodo_diagnostico)}</p>")
    if servico.data_reconfirmacao:
        linhas.append(f"<p><b>Reconfirmação ({fmt(servico.data_reconfirmacao)}):</b> {html.escape(servico.diagnostico_reconfirmacao or '—')}</p>")
    corpo_html = "".join(linhas) + "<p>Fazenda Estreito Ponte de Pedra</p>"

    try:
        enviar_email(dados.destinatario.strip(), f"Diagnóstico de gestação — matriz {numero_matriz}", corpo_html)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"enviado": True}


@router.post("/animais/{numero_matriz}/abrir-lactacao")
def abrir_lactacao(
    numero_matriz: str,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Abre lactação de um animal sem um parto associado — usado no popup de
    aborto (perda de prenhez tardia), quando a vaca segue produzindo leite
    mesmo sem ter parido. Mesmo efeito colateral que um parto normal já causa
    na mãe (del_dias = 0, ver registrar_parto), só que sem Parto nem cria.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Animal).where(Animal.numero == numero_matriz)
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal não encontrado")
    animal.del_dias = 0
    animal.atualizado_em = datetime.utcnow()
    session.add(animal)
    session.commit()
    return {"aberto": True, "numero": numero_matriz}


@router.get("/servicos")
def listar_servicos_analise(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Todos os serviços achatados com as dimensões da análise reprodutiva
    (concepção/perda por categoria, raça, ordem de parto/tentativa, condição
    de IA, inseminador, mês, DEL). O front filtra/agrega no cliente.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Servico)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    servicos = [s.model_dump() for s in session.exec(query).all()]
    registros = analisar_servicos(servicos)
    nomes = mapa_usuarios(session, {r["usuario_id"] for r in registros})
    tipo_por_touro = _mapa_tipo_semen_por_touro(session, fazenda_id)
    data_d0_por_servico = _mapa_data_d0_por_servico(session, fazenda_id)
    for r in registros:
        r["usuario_nome"] = nomes.get(r.pop("usuario_id"))
        # Serviços antigos (lançados antes de o tipo ser perguntado) não têm
        # tipo_semen gravado — completa casando o nome do touro com o Estoque
        # de Sêmen atual, mesma regra usada na baixa de dose.
        if not r.get("tipo_semen") and r.get("touro") and r["touro"] != "(sem touro)":
            r["tipo_semen"] = tipo_por_touro.get(r["touro"].strip().lower())
        # D0 real do protocolo IATF (se o serviço veio de um) — usado pela tela
        # para agrupar por "ciclo" de verdade, em vez de uma janela de calendário
        # ancorada na data do serviço mais recente do filtro (ver data_d0_por_servico).
        # analisar_servicos já renomeou/serializou os campos: "numero" (não
        # numero_matriz) e "data" como string ISO (não data_servico/date).
        r["data_d0"] = data_d0_por_servico.get((r["numero"], r["data"]))
    return {"servicos": registros, "total": len(registros)}


def _mapa_data_d0_por_servico(session: Session, fazenda_id: int | None) -> dict[tuple[str, str], str]:
    """(numero_matriz, data_servico ISO) -> data_d0 (ISO) do protocolo IATF que
    originou aquele serviço — mesma chave que registrar_servico usa para
    resolver a ProtocoloIatfAplicacao da INSEMINAÇÃO na hora de registrar
    (numero_matriz + data_realizacao == data_servico), então funciona igual
    para qualquer serviço já lançado, não só os novos. Sem isso a tela
    agrupava "ciclo" numa janela de calendário arbitrária, sem nenhuma relação
    com o D0 real de cada protocolo (bug relatado — datas de ciclo não
    batiam com os D0 verdadeiros).

    A etapa de inseminação é a de MAIOR dia dentro de cada lançamento — não
    necessariamente D11 (molde com dias livres desloca esse número, ver
    fazenda.rules.protocolo_iatf) —, por isso o maior dia é calculado por
    lançamento em Python em vez de filtrar por um número fixo em SQL.
    """
    query = (
        select(
            ProtocoloIatfAplicacao.lancamento_id, ProtocoloIatfAplicacao.numero_matriz,
            ProtocoloIatfAplicacao.dia, ProtocoloIatfAplicacao.data_realizacao,
            ProtocoloIatfLancamento.data_d0,
        )
        .join(ProtocoloIatfLancamento, ProtocoloIatfAplicacao.lancamento_id == ProtocoloIatfLancamento.id)
        .where(ProtocoloIatfAplicacao.realizada == True)  # noqa: E712
    )
    if fazenda_id is not None:
        query = query.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)

    maior_dia_por_lancamento: dict[int, int] = {}
    linhas = session.exec(query).all()
    for lancamento_id, _numero, dia, _realizacao, _d0 in linhas:
        if dia > maior_dia_por_lancamento.get(lancamento_id, -1):
            maior_dia_por_lancamento[lancamento_id] = dia

    return {
        (numero, realizacao.isoformat()): d0.isoformat()
        for lancamento_id, numero, dia, realizacao, d0 in linhas
        if realizacao is not None and dia == maior_dia_por_lancamento.get(lancamento_id)
    }


class ServicoEditIn(BaseModel):
    """Edição de um serviço/IA já lançado — todos os campos são opcionais,
    só o que for enviado é alterado (usado pelas sub-abas Serviços, IAs,
    Diagnósticos e Perda de prenhez do histórico de Reprodução, que editam
    o mesmo registro Servico com recortes de campos diferentes)."""
    data_servico: date | None = None
    tipo_servico: str | None = None
    reprodutor: str | None = None
    tipo_semen: str | None = None
    inseminador: str | None = None
    data_diagnostico: date | None = None
    diagnostico: str | None = None
    metodo_diagnostico: str | None = None
    data_perda_prenhez: date | None = None
    motivo_perda_prenhez: str | None = None


# Vocabulário fechado do diagnóstico de gestação. Ele SEMPRE existiu, mas só
# como comentário em models/reprodutivo.py ("POSITIVO | NEGATIVO | INDEFINIDO"
# e "Palpação | Ultrassom | Cio de repasse") — nunca como validação (achado 65
# da auditoria): o PUT /servicos/{id} faz `setattr` genérico sobre tudo que
# chega e só `motivo_perda_prenhez` tinha allow-list.
#
# O corpo do e-mail de diagnóstico já escapa o valor (`html.escape`, mais
# acima), então o XSS está fechado no SINK; isto fecha a ORIGEM. E o dano
# maior nem era o e-mail: `diagnostico` é lido como enum por
# rules/estado_reprodutivo.py, agenda_engine.py, perda_prenhez.py,
# reproducao_analise.py e iatf.py, todos comparando com "POSITIVO"/"NEGATIVO"
# em caixa alta. Qualquer outro texto gravado aqui não é rejeitado por
# ninguém: a vaca simplesmente deixa de casar com qualquer estado e some das
# listas de reprodução sem erro nenhum na tela.
DIAGNOSTICOS_VALIDOS = ("POSITIVO", "NEGATIVO", "INDEFINIDO")
METODOS_DIAGNOSTICO_VALIDOS = ("Palpação", "Ultrassom", "Cio de repasse")


def _normalizar_escolha(valor: str, opcoes: tuple[str, ...]) -> str | None:
    """Casa `valor` com uma das `opcoes` ignorando caixa, acento e espaço em
    volta, e devolve a opção NA FORMA CANÔNICA (ou None se não casar).

    Normaliza em vez de comparar cru porque as telas antigas mandam
    "positivo", "Palpacao" e "ULTRASSOM" — recusar isso quebraria o
    lançamento sem fechar furo nenhum. Gravar a forma canônica é o que
    importa: as regras de reprodução comparam com "POSITIVO" em caixa alta."""
    import unicodedata

    def chave(t: str) -> str:
        sem_acento = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
        return sem_acento.strip().casefold()

    procurado = chave(valor)
    for opcao in opcoes:
        if chave(opcao) == procurado:
            return opcao
    return None


def _exigir_metodo_diagnostico(metodo: str | None) -> str | None:
    """Método na forma canônica, ou 400. `None`/vazio segue válido — o método
    é opcional no lançamento (nem todo diagnóstico registra como foi feito)."""
    if not (metodo or "").strip():
        return None
    canonico = _normalizar_escolha(metodo, METODOS_DIAGNOSTICO_VALIDOS)
    if canonico is None:
        raise HTTPException(
            status_code=400,
            detail=f"Método de diagnóstico inválido — use um de: {', '.join(METODOS_DIAGNOSTICO_VALIDOS)}",
        )
    return canonico


@router.put("/servicos/{servico_id}")
def atualizar_servico(
    servico_id: int,
    dados: ServicoEditIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    # Carga filtrada na consulta (ver _buscar_da_fazenda): a checagem antiga
    # tolerava `servico.fazenda_id is None`, e o Servico órfão continua
    # existindo em instalação com 2+ fazendas ('servico' está em
    # _TABELAS_SEM_PAI na migração de backfill).
    servico = _buscar_da_fazenda(session, Servico, servico_id, fazenda_id)
    if not servico:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    campos = dados.model_dump(exclude_unset=True)
    # "nao_informado" só entra aqui (não em MOTIVOS_PERDA_PRENHEZ, a lista de
    # escolha) — é o sentinela gravado pelo botão "Descartar" da pendência da
    # Agenda (ver fazenda.rules.perda_prenhez): a perda continua registrada,
    # só o motivo que o usuário optou por não informar.
    if "motivo_perda_prenhez" in campos and campos["motivo_perda_prenhez"] is not None \
            and campos["motivo_perda_prenhez"] not in MOTIVOS_PERDA_PRENHEZ_VALIDOS:
        raise HTTPException(status_code=400, detail="Motivo de perda de prenhez inválido")
    # Allow-list de diagnóstico/método (achado 65 — ver DIAGNOSTICOS_VALIDOS).
    # `None` continua passando: apagar o diagnóstico é uma edição legítima
    # (reabrir o serviço), o que não pode é gravar texto que ninguém lê.
    for campo, opcoes, rotulo in (
        ("diagnostico", DIAGNOSTICOS_VALIDOS, "Diagnóstico"),
        ("metodo_diagnostico", METODOS_DIAGNOSTICO_VALIDOS, "Método de diagnóstico"),
    ):
        if campos.get(campo) is None:
            continue
        canonico = _normalizar_escolha(campos[campo], opcoes)
        if canonico is None:
            raise HTTPException(
                status_code=400,
                detail=f"{rotulo} inválido — use um de: {', '.join(opcoes)}",
            )
        campos[campo] = canonico
    for campo, valor in campos.items():
        setattr(servico, campo, valor)
    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


@router.get("/indicadores-mensais")
def indicadores_mensais_analise(
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    ini: str | None = None,
    fim: str | None = None,
    tipo_servico: list[str] | None = Query(None),
    metodo_ia: list[str] | None = Query(None),
    touro: list[str] | None = Query(None),
    inseminador: list[str] | None = Query(None),
    ordem_parto: list[str] | None = Query(None),
    ordem_tentativa: list[str] | None = Query(None),
) -> dict:
    """
    Série mensal cruzando métricas reprodutivas (serviços, métodos, concepção,
    perdas) e produtivas (secagens, produção de leite, DEL) — alimenta o
    gráfico interativo configurável de Análise reprodutiva (escolha de
    métricas e eixo ano/mês).

    Aceita os mesmos filtros (período e dimensões) usados na tela de Análise
    reprodutiva, para que o gráfico reflita exatamente o recorte que o
    usuário escolheu — em vez de sempre olhar o histórico inteiro.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Servico)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    servicos = [s.model_dump() for s in session.exec(query).all()]
    registros = analisar_servicos(servicos)

    filtros_dimensao = {
        "tipo_servico": tipo_servico,
        "metodo_ia": metodo_ia,
        "touro": touro,
        "inseminador": inseminador,
        "ordem_parto": ordem_parto,
        "ordem_tentativa": ordem_tentativa,
    }

    def passa(r: dict) -> bool:
        if ini and (not r["data"] or r["data"] < ini):
            return False
        if fim and (not r["data"] or r["data"] > fim):
            return False
        for chave, valores in filtros_dimensao.items():
            if valores and str(r.get(chave)) not in valores:
                return False
        return True

    registros = [r for r in registros if passa(r)]

    secagens_query = select(Secagem)
    controles_query = select(ControleLeiteiro)
    if fazenda_id is not None:
        secagens_query = secagens_query.where(Secagem.fazenda_id == fazenda_id)
        controles_query = controles_query.where(ControleLeiteiro.fazenda_id == fazenda_id)
    secagens = [s.model_dump() for s in session.exec(secagens_query).all()]
    controles = [c.model_dump() for c in session.exec(controles_query).all()]

    if ini or fim:
        def no_periodo(d: object) -> bool:
            if not isinstance(d, date):
                return False
            iso = d.isoformat()
            if ini and iso < ini:
                return False
            if fim and iso > fim:
                return False
            return True

        secagens = [s for s in secagens if no_periodo(s.get("data_secagem"))]
        controles = [c for c in controles if no_periodo(c.get("data_controle"))]

    from fazenda.rules.parametros import dias_resultado_conhecido

    return agregar_mensal(registros, secagens, controles, dias_resultado=dias_resultado_conhecido())


class DiagnosticoIn(BaseModel):
    numero_matriz: str
    data_diagnostico: date
    resultado: str  # "retoque" | "reconfirmada" | "negativo" | "indefinido"
    metodo: str | None = None  # Palpação | Ultrassom | Cio de repasse


@router.post("/diagnostico")
def registrar_diagnostico(
    dados: DiagnosticoIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Registra o resultado do diagnóstico de gestação no serviço mais recente da
    matriz. Se marcado "retoque", o lembrete de reconfirmação entra na agenda
    na data da próxima visita reprodutiva (agenda_engine.py). "Indefinido" (inconclusivo)
    é distinto de "negativo" — a matriz não vira vazia, segue para reavaliar.

    "reconfirmada"/"negativo" sobre um serviço que JÁ teve o 1º toque
    resolvido (ver `eh_2o_exame` abaixo) é o 2º exame, não um novo toque —
    grava em `data_reconfirmacao`/`diagnostico_reconfirmacao` (os mesmos
    campos de POST /reconfirmacao), preservando a data/resultado do 1º
    toque. Sem essa distinção, selecionar "reconfirmada" nesta tela (ex.:
    Lançamentos > Diagnóstico de gestação > Agenda do veterinário >
    Inseminadas 60+ dias) sobrescrevia `data_diagnostico` com a data da
    reconfirmação e nunca preenchia `data_reconfirmacao`/
    `diagnostico_reconfirmacao` — a matriz nunca saía da lista de
    reconfirmação pendente nem aparecia como reconfirmada em lugar nenhum
    (Agenda, roteiro do veterinário, histórico), mesmo com o lançamento
    "bem-sucedido" (relato do produtor, ago/2026).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if dados.resultado not in ("retoque", "reconfirmada", "negativo", "indefinido"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    # Prioriza o serviço ainda em aberto (sem diagnóstico) — evita gravar por
    # engano num serviço antigo já diagnosticado quando a matriz tem mais de
    # um serviço na tabela. Sem serviço em aberto, cai no mais recente (mantém
    # o fluxo de reeditar o diagnóstico já lançado, ex.: retoque -> reconfirmada).
    query_aberto = select(Servico).where(Servico.numero_matriz == dados.numero_matriz, Servico.diagnostico.is_(None))
    query_recente = select(Servico).where(Servico.numero_matriz == dados.numero_matriz)
    if fazenda_id is not None:
        query_aberto = query_aberto.where(Servico.fazenda_id == fazenda_id)
        query_recente = query_recente.where(Servico.fazenda_id == fazenda_id)
    servico = session.exec(query_aberto.order_by(Servico.data_servico.desc())).first() or session.exec(
        query_recente.order_by(Servico.data_servico.desc())
    ).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    # 3º lançamento sobre a mesma prenhez: toque (data_diagnostico) e retoque
    # (data_reconfirmacao) já confirmados POSITIVO, sem perda registrada ainda.
    # Não sobra slot de diagnóstico livre — é interpretado como aborto (perda
    # de prenhez), não como um novo toque sobrescrevendo o anterior.
    if servico.diagnostico_reconfirmacao is not None and servico.data_perda_prenhez is None:
        servico.data_perda_prenhez = dados.data_diagnostico
        servico.motivo_perda_prenhez = "aborto"
        session.add(servico)
        session.commit()
        session.refresh(servico)
        resultado = servico.model_dump()
        resultado["aborto_detectado"] = True
        return resultado

    # 1º toque já resolvido (POSITIVO/NEGATIVO/INDEFINIDO) e ainda sem
    # reconfirmação — "reconfirmada"/"negativo" aqui são o 2º exame, não um
    # novo toque. "retoque"/"indefinido" continuam sempre gravando no toque
    # (marcar/manter para reconfirmar), mesmo re-selecionados sobre um
    # serviço já retoque=True — idempotente, não perde dado nenhum.
    eh_2o_exame = (
        dados.resultado in ("reconfirmada", "negativo")
        and (servico.diagnostico or "").strip().upper() in {"POSITIVO", "NEGATIVO", "INDEFINIDO"}
    )

    if eh_2o_exame:
        servico.data_reconfirmacao = dados.data_diagnostico
        servico.diagnostico_reconfirmacao = "POSITIVO" if dados.resultado == "reconfirmada" else "NEGATIVO"
        servico.retoque = False
    else:
        servico.data_diagnostico = dados.data_diagnostico
        # Mesma allow-list do PUT /servicos/{id} (achado 65): `dados.metodo` é
        # texto livre e cai no mesmo campo, então validar só lá deixaria a
        # porta da frente aberta. O `resultado` logo abaixo já era fechado.
        servico.metodo_diagnostico = _exigir_metodo_diagnostico(dados.metodo)
        if dados.resultado == "retoque":
            servico.diagnostico = "POSITIVO"
            servico.retoque = True
        elif dados.resultado == "reconfirmada":
            # Fluxo legado: reconfirmar direto, sem 1º toque lançado antes
            # (servico ainda em aberto) — mesmo caso já suportado por
            # POST /reconfirmacao.
            servico.diagnostico = "POSITIVO"
            servico.retoque = False
        elif dados.resultado == "indefinido":
            # Inconclusivo NÃO é positivo, negativo nem "em aberto" — é um estado
            # próprio, e a única saída dele é examinar de novo. Por isso já entra
            # marcado para retoque: o lembrete de reconfirmação cai na agenda
            # sozinho (agenda_engine.py só olha o flag, não o diagnóstico), em vez
            # de depender de alguém lembrar de voltar nessa vaca.
            servico.diagnostico = "INDEFINIDO"
            servico.retoque = True
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
def registrar_reconfirmacao(
    dados: ReconfirmacaoIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Segundo exame (reconfirmação, ~60 dias do serviço) — distinto do primeiro
    toque. Usado pela agenda do veterinário para tirar o animal de "atrasada
    para reconfirmação" e classificá-lo como gestante confirmada.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if dados.resultado not in ("positivo", "negativo"):
        raise HTTPException(status_code=400, detail="Resultado inválido")

    # Mesma lógica de preferência do diagnóstico acima: prioriza o serviço
    # positivo ainda sem reconfirmação; sem um assim, cai no mais recente
    # (mantém o fluxo legado de reconfirmar direto um serviço sem 1º toque).
    query_aberto = select(Servico).where(
        Servico.numero_matriz == dados.numero_matriz,
        Servico.diagnostico == "POSITIVO",
        Servico.data_reconfirmacao.is_(None),
    )
    query_recente = select(Servico).where(Servico.numero_matriz == dados.numero_matriz)
    if fazenda_id is not None:
        query_aberto = query_aberto.where(Servico.fazenda_id == fazenda_id)
        query_recente = query_recente.where(Servico.fazenda_id == fazenda_id)
    servico = session.exec(query_aberto.order_by(Servico.data_servico.desc())).first() or session.exec(
        query_recente.order_by(Servico.data_servico.desc())
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


class PerdaPrenhezIn(BaseModel):
    numero_matriz: str
    data_perda_prenhez: date
    motivo: str  # aborto | natimorto | outros


@router.post("/perda-prenhez")
def registrar_perda_prenhez(
    dados: PerdaPrenhezIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Registra a perda de prenhez (com motivo) no serviço mais recente da
    matriz — sem isso, `data_perda_prenhez` só era populado pela importação de
    CSV, sem nenhuma classificação nem forma manual de lançar. Alimenta o
    histórico de perda de prenhezes (filtro aborto/natimorto/outros).
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if dados.motivo not in MOTIVOS_PERDA_PRENHEZ:
        raise HTTPException(status_code=400, detail="Motivo inválido")

    query = select(Servico).where(Servico.numero_matriz == dados.numero_matriz)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    servico = session.exec(query.order_by(Servico.data_servico.desc())).first()
    if not servico:
        raise HTTPException(status_code=404, detail=f"Nenhum serviço encontrado para a matriz {dados.numero_matriz}")

    servico.data_perda_prenhez = dados.data_perda_prenhez
    servico.motivo_perda_prenhez = dados.motivo
    session.add(servico)
    session.commit()
    session.refresh(servico)
    return servico.model_dump()


@router.get("/partos")
def listar_partos_historico(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Todos os partos, achatados — histórico de partos (Reprodução), com os
    mesmos filtros de animal/data/ciclo/ordem de parto da sub-aba Reprodução."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Parto).order_by(Parto.data_parto.desc())
    if fazenda_id is not None:
        query = query.where(Parto.fazenda_id == fazenda_id)
    partos = session.exec(query).all()
    nomes = mapa_usuarios(session, {p.usuario_id for p in partos})
    registros = []
    for p in partos:
        d = p.model_dump()
        d["numero"] = d.pop("numero_matriz")
        ds = d.get("data_parto")
        d["ano"] = ds.year if isinstance(ds, date) else None
        d["mes"] = f"{ds.year}-{ds.month:02d}" if isinstance(ds, date) else None
        d["data"] = ds.isoformat() if isinstance(ds, date) else None
        d["usuario_nome"] = nomes.get(d.pop("usuario_id"))
        registros.append(d)
    return {"partos": registros, "total": len(registros)}


class PartoEditIn(BaseModel):
    data_parto: date | None = None
    tipo_parto: str | None = None
    retencao_placenta: bool | None = None
    numero_cria_1: str | None = None
    numero_cria_2: str | None = None
    sexo_cria_1: str | None = None
    sexo_cria_2: str | None = None
    gemelar: bool | None = None
    gemelar_sexo: str | None = None


@router.put("/partos/{parto_id}")
def atualizar_parto(
    parto_id: int,
    dados: PartoEditIn,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Edita os campos do parto (data, tipo, retenção de placenta, número/sexo
    das crias). Editar o número da cria aqui só corrige o REGISTRO DO PARTO —
    não renomeia nem cria a ficha do animal da cria; isso continua sendo feito
    pela Ficha do Animal (ver /animais/{numero} e verificar_mae_parto abaixo,
    que cruza a mãe informada na ficha com os partos dela)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    # Mesmo caso do atualizar_servico — 'parto' também está em
    # _TABELAS_SEM_PAI na migração de backfill (ver _buscar_da_fazenda).
    parto = _buscar_da_fazenda(session, Parto, parto_id, fazenda_id)
    if not parto:
        raise HTTPException(status_code=404, detail="Parto não encontrado")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(parto, campo, valor)
    session.add(parto)
    session.commit()
    session.refresh(parto)
    return parto.model_dump()


@router.get("/verificar-mae")
def verificar_mae_parto(
    mae_numero: str,
    animal_numero: str | None = None,
    session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Chamado ao editar a Ficha do Animal e mudar o campo "mãe" — cruza a mãe
    informada com os partos DELA já registrados (Histórico > Reprodução >
    Partos), para o front mostrar um popup de confirmação com data/ordem do
    parto e apontar inconsistências (mãe sem parto registrado, nenhum parto
    perto da data de nascimento, ou parto já com outra cria vinculada) antes
    de salvar. Não bloqueia nada sozinho — só informa, quem decide é o usuário."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_mae = select(Animal).where(Animal.numero == mae_numero)
    if fazenda_id is not None:
        query_mae = query_mae.where(Animal.fazenda_id == fazenda_id)
    mae = session.exec(query_mae).first()

    query_animal = select(Animal).where(Animal.numero == animal_numero) if animal_numero else None
    if query_animal is not None and fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first() if query_animal is not None else None
    nascimento = animal.data_nasc if animal else None

    query_partos = select(Parto).where(Parto.numero_matriz == mae_numero)
    if fazenda_id is not None:
        query_partos = query_partos.where(Parto.fazenda_id == fazenda_id)
    partos_da_mae = session.exec(query_partos.order_by(Parto.data_parto.desc())).all()

    inconsistencias: list[str] = []
    parto_correspondente = None
    if not mae:
        inconsistencias.append(f"Não existe animal cadastrado com o número {mae_numero}.")
    elif not partos_da_mae:
        inconsistencias.append(f"A mãe {mae_numero} não tem nenhum parto registrado no Histórico.")
    elif nascimento:
        # Parto mais próximo da data de nascimento informada, dentro de 15 dias
        # (cobre desvio entre data do parto e data de nascimento lançada).
        candidatos = [p for p in partos_da_mae if p.data_parto and abs((p.data_parto - nascimento).days) <= 15]
        parto_correspondente = min(candidatos, key=lambda p: abs((p.data_parto - nascimento).days)) if candidatos else None
        if not parto_correspondente:
            inconsistencias.append(
                f"Nenhum parto da mãe {mae_numero} está próximo da data de nascimento informada "
                f"({nascimento.strftime('%d/%m/%Y')}) — o parto mais próximo é "
                f"{partos_da_mae[0].data_parto.strftime('%d/%m/%Y') if partos_da_mae[0].data_parto else 'sem data'}."
            )
        else:
            outra_cria = None
            if parto_correspondente.numero_cria_1 and parto_correspondente.numero_cria_1 != animal_numero:
                outra_cria = parto_correspondente.numero_cria_1
            elif parto_correspondente.numero_cria_2 and parto_correspondente.numero_cria_2 != animal_numero:
                outra_cria = parto_correspondente.numero_cria_2
            if outra_cria and (parto_correspondente.numero_cria_1 != animal_numero and parto_correspondente.numero_cria_2 != animal_numero):
                inconsistencias.append(f"O parto de {parto_correspondente.data_parto.strftime('%d/%m/%Y')} da mãe {mae_numero} já tem outra cria vinculada (nº {outra_cria}).")
    else:
        inconsistencias.append("O animal não tem data de nascimento cadastrada — não é possível cruzar com a data do parto.")

    return {
        "mae_encontrada": mae is not None,
        "parto_correspondente": parto_correspondente.model_dump() if parto_correspondente else None,
        "partos_da_mae": [p.model_dump() for p in partos_da_mae[:5]],
        "inconsistencias": inconsistencias,
    }


@router.get("/secagens")
def listar_secagens_historico(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Todas as secagens, achatadas — histórico de secagens (Reprodução), com
    os mesmos filtros de animal/data/ciclo da sub-aba Reprodução.

    Correção (fechamento dos 17 gaps de editar/excluir, G5): esta rota não
    filtrava por fazenda — vazamento entre fazendas, secagens de uma fazenda
    apareciam no histórico de outra."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Secagem)
    if fazenda_id is not None:
        query = query.where(Secagem.fazenda_id == fazenda_id)
    secagens = session.exec(query.order_by(Secagem.data_secagem.desc())).all()
    registros = []
    for s in secagens:
        d = s.model_dump()
        d["numero"] = d.pop("numero_matriz")
        ds = d.get("data_secagem")
        d["ano"] = ds.year if isinstance(ds, date) else None
        d["mes"] = f"{ds.year}-{ds.month:02d}" if isinstance(ds, date) else None
        d["data"] = ds.isoformat() if isinstance(ds, date) else None
        registros.append(d)
    return {"secagens": registros, "total": len(registros)}


class SecagemEditIn(BaseModel):
    data_secagem: date | None = None
    motivo: str | None = None
    escore_condicao_corporal: float | None = None
    observacao: str | None = None


@router.put("/secagens/{secagem_id}")
def atualizar_secagem(
    secagem_id: int, dados: SecagemEditIn, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    secagem = _buscar_da_fazenda(session, Secagem, secagem_id, fazenda_id)
    if not secagem:
        raise HTTPException(status_code=404, detail="Secagem não encontrada")
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(secagem, campo, valor)
    session.add(secagem)
    session.commit()
    session.refresh(secagem)
    return secagem.model_dump()


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


def _partos_da_matriz(session: Session, numero_matriz: str, fazenda_id: int | None) -> list[Parto]:
    """Todos os partos gravados da matriz — inclusive os abortos, que também
    são `Parto` desde o endpoint único de encerramento de gestação. Quem
    precisa só dos produtivos filtra com `rules.parto.eh_parto_produtivo`."""
    query = select(Parto).where(Parto.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        query = query.where(Parto.fazenda_id == fazenda_id)
    return list(session.exec(query).all())


def _buscar_matriz(session: Session, numero_matriz: str, fazenda_id: int | None) -> Animal:
    query = select(Animal).where(Animal.numero == numero_matriz)
    if fazenda_id is not None:
        query = query.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Matriz não encontrada")
    return animal


def _gravar_parto_e_crias(
    session: Session, mae: Animal, *, data_parto: date, tipo_parto: str | None,
    crias: list[CriaIn], retencao_placenta: bool | None, gemelar: bool | None,
    gemelar_sexo: str | None, ordem_parto: int | None, usuario_id: int | None,
    fazenda_id: int | None, abriu_lactacao: bool = False,
) -> tuple[Parto, list[str], list[str]]:
    """Cria o `Parto`, cadastra as crias nascidas vivas e agenda a avaliação
    de retenção de placenta — SEM commit.

    Extraído de `registrar_parto` para ser o corpo comum dele e do endpoint
    único de encerramento de gestação: os dois precisam gravar exatamente o
    mesmo `Parto`, e ter duas cópias dessa gravação é como o aborto acabou
    sem `Parto` nenhum em primeiro lugar.

    `ordem_parto=None` marca um fim de gestação NÃO produtivo (aborto sem
    abertura de lactação) — ver `fazenda.rules.parto`. `abriu_lactacao=True`
    é o registro, no próprio `Parto`, de que este aborto específico abriu
    lactação (True só chega aqui vindo de `encerrar_gestacao`, nunca de
    `registrar_parto` — só o aborto pode ser não-produtivo).
    """
    if not gemelar_sexo and len(crias) >= 2:
        combo = "".join(sorted((crias[0].sexo or "").upper() + (crias[1].sexo or "").upper()))
        gemelar_sexo = {"FF": "FF", "FM": "FM", "MM": "MM"}.get(combo)

    parto = Parto(
        animal_id=mae.id,
        numero_matriz=mae.numero,
        data_parto=data_parto,
        ordem_parto=ordem_parto,
        tipo_parto=tipo_parto,
        sexo_cria_1=crias[0].sexo if len(crias) > 0 else None,
        sexo_cria_2=crias[1].sexo if len(crias) > 1 else None,
        numero_cria_1=(crias[0].numero or None) if len(crias) > 0 else None,
        numero_cria_2=(crias[1].numero or None) if len(crias) > 1 else None,
        gemelar=gemelar if gemelar is not None else len(crias) > 1,
        gemelar_sexo=gemelar_sexo,
        retencao_placenta=retencao_placenta,
        abriu_lactacao=abriu_lactacao,
        usuario_id=usuario_id,
        fazenda_id=fazenda_id,
    )
    session.add(parto)
    session.flush()  # precisa do parto.id para vincular a lactação

    crias_criadas: list[str] = []
    crias_baixadas: list[str] = []
    for cria in crias:
        # Sem número OU marcada como não-viva → baixa automática (natimorto/não
        # entra no rebanho). Fica registrada no parto (sexo), mas sem ficha.
        if not (cria.numero or "").strip() or not cria.nasceu_viva:
            crias_baixadas.append(cria.sexo or "?")
            continue
        query_cria_existente = select(Animal).where(Animal.numero == cria.numero)
        if fazenda_id is not None:
            query_cria_existente = query_cria_existente.where(Animal.fazenda_id == fazenda_id)
        if session.exec(query_cria_existente).first():
            continue  # já cadastrada — não sobrescreve
        raca_cria, grau_sangue_cria = calcular_grau_sangue_cria(session, mae, data_parto, fazenda_id)
        # Todo animal que nasce entra automaticamente na categoria "bezerra/o
        # mamando" — o próximo upload do GERAL.csv (Ideagri) pode atualizar
        # depois, mas a cria não deve ficar sem categoria até lá.
        categoria_completa_cria = "Bezerra Mamando" if cria.sexo == "F" else "Bezerro Mamando"
        categoria_abrev_cria = "Bezerra" if cria.sexo == "F" else "Bezerro"
        session.add(Animal(
            numero=cria.numero, sexo=cria.sexo, raca=raca_cria, grau_sangue=grau_sangue_cria, data_nasc=data_parto,
            mae_numero=mae.numero, mae_nome=mae.nome, ativo=True,
            categoria_completa=categoria_completa_cria, categoria_abrev=categoria_abrev_cria,
            fazenda_id=fazenda_id,
        ))
        crias_criadas.append(cria.numero)

    # Retenção de placenta → gera um item na Agenda (avaliação/tratamento) no
    # dia do parto, para não passar despercebido.
    if retencao_placenta:
        from fazenda.models import AgendaManual
        session.add(AgendaManual(
            data_evento=data_parto,
            descricao=f"Retenção de placenta — vaca {mae.numero}: avaliar/tratar",
            categoria="Sanidade",
            numero_animal=mae.numero,
            tipo_evento="Outro",
            observacao="Gerado automaticamente pelo lançamento de parto com retenção de placenta.",
            usuario_id=usuario_id,
            fazenda_id=fazenda_id,
        ))

    return parto, crias_criadas, crias_baixadas


@router.post("/parto")
def registrar_parto(
    dados: PartoIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Registra o parto e cria a ficha de cada cria nascida viva ainda não
    cadastrada. Não move ninguém de lote sozinho — o front sugere o lote via
    /producao/sugestao-lote-evento e só move (POST /movimentacoes/mover) com
    confirmação explícita do usuário.

    Continua existindo para não quebrar quem já o chama (app de campo, bot do
    Telegram, importações); o caminho novo e completo — que também resolve a
    perda de prenhez e cobre aborto/natimorto — é
    POST /reproducao/encerramento-gestacao.
    """
    mae = _buscar_matriz(session, dados.numero_matriz, fazenda_id)

    # A ordem sai de `rules.parto.proxima_ordem_parto` — não mais de
    # "`ordem_parto` do mais recente + 1" ordenado por essa mesma coluna.
    # Agora que o aborto também gera um `Parto` (com `ordem_parto` NULL, ver
    # fazenda/rules/parto.py), aquela consulta ficaria dependente de como o
    # banco ordena NULLs: em Postgres eles vêm PRIMEIRO no DESC, e toda matriz
    # com um aborto no histórico recomeçaria a contagem do 1.
    ordem_parto = proxima_ordem_parto(_partos_da_matriz(session, dados.numero_matriz, fazenda_id))

    parto, crias_criadas, crias_baixadas = _gravar_parto_e_crias(
        session, mae, data_parto=dados.data_parto, tipo_parto=dados.tipo_parto, crias=dados.crias,
        retencao_placenta=dados.retencao_placenta, gemelar=dados.gemelar, gemelar_sexo=dados.gemelar_sexo,
        ordem_parto=ordem_parto, usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
    )

    # Todo parto abre uma lactação (ver fazenda/rules/lactacao.py) — a
    # entidade que faltava e sem a qual "esta vaca está em lactação?" era
    # inferido de forma diferente em cada tela. `data_inicio` é a data REAL
    # do parto, inclusive retroativa: é dela que sai o DEL ao vivo gravado
    # em cada controle leiteiro.
    regras_lactacao.abrir_lactacao(
        session, numero_matriz=dados.numero_matriz, data_inicio=dados.data_parto,
        origem=regras_lactacao.ORIGEM_PARTO, parto_id=parto.id, animal_id=mae.id,
        fazenda_id=fazenda_id, usuario_id=usuario_id_seguro(user),
    )

    # `Animal.del_dias` é campo CONGELADO, mantido em dia aqui só por
    # compatibilidade com as telas que ainda o leem (a migração delas para
    # ler a Lactacao direto é a Peça 1). Note que agora sai do DEL AO VIVO
    # da lactação recém-aberta, não de um `0` cravado: num parto lançado
    # retroativamente, `0` era simplesmente falso.
    regras_lactacao.sincronizar_del_do_animal(
        session, numero_matriz=dados.numero_matriz, fazenda_id=fazenda_id,
    )

    session.commit()
    return {"criado": True, "ordem_parto": ordem_parto, "crias_criadas": crias_criadas, "crias_baixadas": crias_baixadas}


# ---------------------------------------------------------------------------
# Encerramento de gestação — o caminho ÚNICO de "esta gestação acabou"
#
# Antes existiam TRÊS caminhos incoerentes para a mesma coisa:
#
#   1. `POST /reproducao/parto` — criava `Parto`, mas só servia para parto
#      normal e não tocava na perda de prenhez;
#   2. `POST /reproducao/perda-prenhez` (o que o botão "Aborto" do FormParto
#      chamava) — NÃO criava `Parto` nenhum, só carimbava dois campos no
#      serviço MAIS RECENTE POR DATA da matriz, que nem sempre é o serviço
#      que originou a gestação perdida;
#   3. `POST /reproducao/animais/{n}/abrir-lactacao` — gravava `del_dias = 0`
#      e nada mais, sem nem receber a data do evento.
#
# O resultado era o bug que originou esta correção: a matriz que abortou
# ficava sem `Parto` (logo, "novilha gestante, sem parto" na Ficha para
# sempre), com a perda possivelmente carimbada no serviço errado, e com uma
# "lactação" que existia só como um zero num campo congelado.
#
# Este endpoint faz as quatro coisas numa transação só, para os três tipos de
# fim de gestação. Os endpoints antigos continuam existindo (há outros
# chamadores), mas o fluxo de aborto do FormParto passa por aqui.
# ---------------------------------------------------------------------------
TIPOS_ENCERRAMENTO = ("parto", "aborto", "natimorto")

# Rótulo gravado em `Parto.tipo_parto` por tipo de encerramento. O do aborto é
# o mesmo texto que a importação do CSV do Ideagri já traz, de propósito (ver
# fazenda/rules/parto.py).
ROTULO_TIPO_PARTO = {
    "parto": TIPO_PARTO_NORMAL,
    "aborto": TIPO_PARTO_ABORTO,
    "natimorto": TIPO_PARTO_NATIMORTO,
}

# Motivo de perda de prenhez implícito em cada tipo, quando o usuário não
# informa um. Parto normal não gera perda nenhuma — ver o comentário no corpo.
MOTIVO_PADRAO_POR_TIPO = {"aborto": "aborto", "natimorto": "natimorto"}


class EncerramentoGestacaoIn(BaseModel):
    numero_matriz: str
    data: date                      # data REAL do evento — aceita retroativa
    tipo: str                       # "parto" | "aborto" | "natimorto"
    abrir_lactacao: bool = False    # resposta do popup "deseja abrir lactação?"
    motivo: str | None = None       # perda de prenhez: aborto | natimorto | outros
    crias: list[CriaIn] = []
    retencao_placenta: bool | None = None
    gemelar: bool | None = None
    gemelar_sexo: str | None = None
    tipo_parto: str | None = None   # rótulo livre do parto (distocia etc.); vazio = o padrão do tipo
    observacao: str | None = None
    forcar: bool = False            # reservado: confirmação manual de situações limítrofes


@router.post("/encerramento-gestacao")
def encerrar_gestacao(
    dados: EncerramentoGestacaoIn, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Encerra a gestação de uma matriz — parto, aborto ou natimorto — numa
    única transação:

    1. cria o `Parto` (nos TRÊS casos; no aborto SEM abertura de lactação,
       `ordem_parto` fica NULL, que é o que o mantém fora do IEP/ordem de
       parto — ver rules/parto.py). Aborto COM abertura de lactação
       (`abrir_lactacao=True`) é produtivo — recebe `ordem_parto` e grava
       `Parto.abriu_lactacao=True`, a mesma exceção de `eh_parto_produtivo`;
    2. carimba a perda de prenhez no serviço VIGENTE POSITIVO certo (aborto e
       natimorto), usando `rules.perda_prenhez.servico_esta_positivo_vigente`
       em vez de "o serviço mais recente por data", que podia carimbar a
       perda numa inseminação posterior à gestação perdida;
    3. abre a `Lactacao` com `data_inicio` = a data REAL do evento, se
       `abrir_lactacao`;
    4. sincroniza `Animal.del_dias` com o DEL ao vivo recém-calculado, para
       as telas que ainda leem o campo congelado.

    Não move ninguém de lote: devolve `sugerir_lote` para o front pedir a
    sugestão em /producao/sugestao-lote-evento e confirmar com o usuário —
    exatamente o que o parto normal já faz, e que o caminho de aborto pulava
    inteiro.
    """
    if dados.tipo not in TIPOS_ENCERRAMENTO:
        raise HTTPException(status_code=400, detail=f"Tipo inválido: {dados.tipo}")
    if dados.motivo is not None and dados.motivo not in MOTIVOS_PERDA_PRENHEZ:
        raise HTTPException(status_code=400, detail="Motivo de perda de prenhez inválido")

    mae = _buscar_matriz(session, dados.numero_matriz, fazenda_id)
    usuario_id = usuario_id_seguro(user)
    partos_anteriores = _partos_da_matriz(session, dados.numero_matriz, fazenda_id)

    # (1) O Parto. Aborto -> ordem_parto NULL: a gestação acabou (e todo o
    # motor ao vivo que pergunta "existe parto?" passa a enxergar isso), mas
    # não houve cria e a ordem de parto da matriz não avança. EXCEÇÃO: aborto
    # que abre lactação (`dados.abrir_lactacao=True`) é produtivo — a vaca
    # entrou em lactação de verdade, funcionalmente equivalente a uma cria
    # para fins de contagem de ordem de parto (pedido explícito do usuário).
    abriu_lactacao_no_aborto = dados.tipo == "aborto" and dados.abrir_lactacao
    produtivo = dados.tipo != "aborto" or dados.abrir_lactacao
    ordem_parto = proxima_ordem_parto(partos_anteriores) if produtivo else None
    parto, crias_criadas, crias_baixadas = _gravar_parto_e_crias(
        session, mae, data_parto=dados.data, tipo_parto=dados.tipo_parto or ROTULO_TIPO_PARTO[dados.tipo],
        crias=dados.crias, retencao_placenta=dados.retencao_placenta, gemelar=dados.gemelar,
        gemelar_sexo=dados.gemelar_sexo, ordem_parto=ordem_parto, usuario_id=usuario_id, fazenda_id=fazenda_id,
        abriu_lactacao=abriu_lactacao_no_aborto,
    )

    # (2) A perda de prenhez — só quando de fato houve perda. Um parto normal
    # NÃO carimba `data_perda_prenhez`: a gestação se resolveu do jeito certo,
    # e marcar perda ali corromperia as taxas de perda de prenhez do rebanho.
    servico_perda = None
    if dados.tipo in MOTIVO_PADRAO_POR_TIPO:
        servico_perda = _carimbar_perda_no_servico_vigente(
            session, numero_matriz=dados.numero_matriz, data_perda=dados.data,
            motivo=dados.motivo or MOTIVO_PADRAO_POR_TIPO[dados.tipo],
            partos_anteriores=partos_anteriores, fazenda_id=fazenda_id,
        )

    # (3) A lactação, com a data REAL do evento (retroativa quando for o
    # caso). É daqui que sai o DEL — não mais de um `del_dias = 0` cravado
    # no dia do lançamento, que dava DEL 0 a uma vaca que abortou há 40 dias.
    lactacao = None
    if dados.abrir_lactacao:
        lactacao = regras_lactacao.abrir_lactacao(
            session, numero_matriz=dados.numero_matriz, data_inicio=dados.data,
            origem=regras_lactacao.ORIGEM_ABORTO if dados.tipo == "aborto" else regras_lactacao.ORIGEM_PARTO,
            parto_id=parto.id, animal_id=mae.id, fazenda_id=fazenda_id, usuario_id=usuario_id,
            observacao=dados.observacao,
        )

    # (4) Compatibilidade com quem ainda lê o campo congelado.
    del_atual = regras_lactacao.sincronizar_del_do_animal(
        session, numero_matriz=dados.numero_matriz, fazenda_id=fazenda_id,
    )
    # A gestação acabou — "gestante" no texto congelado deixou de ser
    # verdade, seja lá qual for o tipo (parto, aborto ou natimorto). Sem
    # isso, `Animal.categoria_completa/categoria_abrev` continuam dizendo
    # "gestante" até o próximo upload do GERAL.csv, que pode nunca vir (caso
    # relatado: novilha "14", abortou, categoria seguiu "Novilha gestante").
    regras_lactacao.sincronizar_categoria_do_animal(
        session, numero_matriz=dados.numero_matriz, fazenda_id=fazenda_id,
    )

    session.commit()
    if lactacao is not None:
        session.refresh(lactacao)
    return {
        "criado": True,
        "tipo": dados.tipo,
        "parto_id": parto.id,
        "ordem_parto": ordem_parto,
        "crias_criadas": crias_criadas,
        "crias_baixadas": crias_baixadas,
        "perda_prenhez_servico_id": servico_perda.id if servico_perda else None,
        "lactacao_id": lactacao.id if lactacao else None,
        "lactacao_aberta": lactacao is not None,
        "del_dias": del_atual,
        # O front usa isto para rodar o MESMO bloco de sugestão de lote do
        # parto normal (ver prepararPendenciaLote/alocarSemConfirmar em
        # FormParto.tsx), que o caminho antigo de aborto pulava.
        "sugerir_lote": lactacao is not None,
    }


def _carimbar_perda_no_servico_vigente(
    session: Session, *, numero_matriz: str, data_perda: date, motivo: str,
    partos_anteriores: list[Parto], fazenda_id: int | None,
) -> Servico | None:
    """Grava a perda de prenhez no serviço que ORIGINOU a gestação perdida.

    O caminho antigo (`POST /reproducao/perda-prenhez`) pegava simplesmente o
    serviço de data mais recente da matriz. Isso carimba no serviço errado
    sempre que existe uma inseminação POSTERIOR à gestação perdida — e a
    matriz passa a constar com uma perda numa tentativa que ainda nem foi
    diagnosticada, enquanto a gestação que realmente se perdeu continua
    contando como vigente.

    Aqui o alvo é o serviço vigente que ainda vale como prenhez, pelo mesmo
    critério de `rules.perda_prenhez.servico_esta_positivo_vigente`: o mais
    recente ATÉ a data do evento, posterior ao último parto anterior, com
    diagnóstico POSITIVO e sem perda já registrada.

    Devolve `None` (sem erro) quando não há serviço assim — é o caso legítimo
    da matriz que abortou sem que ninguém tivesse lançado o diagnóstico
    positivo. O `Parto` do aborto continua sendo criado, que é o que conserta
    o estado dela.
    """
    ultimo_parto = max(
        (p.data_parto for p in partos_anteriores if p.data_parto and p.data_parto < data_perda), default=None,
    )
    query = select(Servico).where(Servico.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        query = query.where(Servico.fazenda_id == fazenda_id)
    candidatos = [
        s for s in session.exec(query).all()
        if s.data_servico and s.data_servico <= data_perda
        and (ultimo_parto is None or s.data_servico > ultimo_parto)
    ]
    vigente = max(candidatos, key=lambda s: s.data_servico, default=None)
    if vigente is None or not servico_esta_positivo_vigente(vigente):
        return None
    vigente.data_perda_prenhez = data_perda
    vigente.motivo_perda_prenhez = motivo
    session.add(vigente)
    return vigente


class HormonioIatfIn(BaseModel):
    dia: int  # 0, 7 ou 9 (D11 é inseminação, sem hormônio)
    produto: str
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None


class ProtocoloIatfIn(BaseModel):
    animais: list[str]
    data_d0: date
    # Molde cadastrado (Central de Protocolos > Cadastro), opcional — só para
    # rastreabilidade/nome; os hormônios efetivamente aplicados continuam
    # vindo de `hormonios` (o frontend pré-preenche a partir do molde, mas
    # sempre resolvendo o item de estoque concreto antes de enviar).
    protocolo_id: int | None = None
    # Medicamentos por dia (ex.: D0 = 1ml SincroCP + 2ml Estron). Opcional —
    # sem eles, o protocolo funciona como antes (sem baixa de estoque).
    hormonios: list[HormonioIatfIn] = []
    forcar: bool = False  # confirmação manual dos bloqueios confirmáveis de aptidão (ver rules/aptidao.py)


@router.post("/protocolo-iatf")
def lancar_protocolo_iatf(
    dados: ProtocoloIatfIn, response: Response, session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user), fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Agenda só o PROTOCOLO hormonal (D0/D7/D9/D11 clássico, ou os dias livres
    do molde escolhido — ver `_passos_do_lancamento`) — não cria o serviço em
    si. A inseminação de fato é lançada à parte em POST /reproducao/servico,
    para separar "marcar o protocolo" de "a vaca foi inseminada". Cada etapa de
    cada animal vira uma ProtocoloIatfAplicacao rastreável — a Agenda agrupa
    por (lançamento, dia) em vez de mostrar uma linha por animal.
    """
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    # Colocar a matriz num protocolo hormonal é decidir que ela vai ser
    # inseminada — a mesma trava de aptidão da inseminação vale aqui, e vale
    # AQUI PRIMEIRO: entre o D0 e a IA passam ~11 dias de hormônio aplicado
    # em bicho que nunca deveria ter entrado no protocolo. Valida contra a
    # data do D0 (a idade do animal HOJE, não daqui a 11 dias).
    _exigir_aptidao_do_lote(
        session, dados.animais, data=dados.data_d0, fazenda_id=fazenda_id, forcar=dados.forcar,
    )

    nome_base = "Protocolo IATF"
    if dados.protocolo_id is not None:
        molde = _buscar_da_fazenda(session, ProtocoloIatf, dados.protocolo_id, fazenda_id)
        if not molde:
            raise HTTPException(status_code=404, detail="Protocolo IATF cadastrado não encontrado")
        nome_base = molde.nome

    # Idempotência (mesmo padrão de producao.lancar_inducao_lactacao — ver o
    # comentário "Idempotência:" lá): duplo clique ou retry da fila offline
    # reenviando este POST não pode criar um segundo ProtocoloIatfLancamento
    # "Ativo" com o mesmo molde/data/animais.
    #
    # Com molde (`protocolo_id` informado): mesmo protocolo_id + mesma data_d0
    # + mesmo conjunto de animais + ainda ativo e não encerrado — igual à
    # indução de lactação.
    #
    # Sem molde (lançamento ad-hoc, `protocolo_id is None`, hormônios
    # digitados na hora): não dá para usar só data_d0 + animais, porque dois
    # lançamentos ad-hoc LEGÍTIMOS e distintos podem coincidir nisso (mesma
    # vaca, mesmo D0, mas um protocolo hormonal diferente do outro — ex.:
    # usuário lança errado, cancela, relança com outra dose no mesmo dia).
    # Por isso a equivalência ad-hoc inclui também o conjunto de hormônios
    # (dia+produto+dose+unidade+via): um retry de verdade reenvia o MESMO
    # payload, hormônios inclusive, então continua batendo; já dois
    # lançamentos ad-hoc com hormônios diferentes não se confundem mais.
    animais_set = set(dados.animais)
    hormonios_set = {
        (h.dia, h.produto.strip(), h.dose, h.unidade, h.via)
        for h in dados.hormonios if (h.produto or "").strip()
    }
    candidatos = session.exec(
        select(ProtocoloIatfLancamento)
        .where(ProtocoloIatfLancamento.protocolo_id == dados.protocolo_id)
        .where(ProtocoloIatfLancamento.data_d0 == dados.data_d0)
        .where(ProtocoloIatfLancamento.ativo == True)  # noqa: E712
        .where(ProtocoloIatfLancamento.encerrado_em.is_(None))
    ).all()
    for candidato in candidatos:
        # Estrito (== , não tolera fazenda_id nulo do candidato) — mesmo
        # motivo do bloco equivalente em producao.lancar_inducao_lactacao:
        # reaproveitar um lançamento órfão de outra fazenda por coincidência
        # de data/molde/animais cruzaria tenant, contra o filtro do PR #488.
        if fazenda_id is not None and candidato.fazenda_id != fazenda_id:
            continue
        animais_candidato = set(session.exec(
            select(ProtocoloIatfAplicacao.numero_matriz)
            .where(ProtocoloIatfAplicacao.lancamento_id == candidato.id)
        ).all())
        if animais_candidato != animais_set:
            continue
        if dados.protocolo_id is None:
            hormonios_candidato = {
                (h.dia, h.produto, h.dose, h.unidade, h.via)
                for h in session.exec(
                    select(ProtocoloIatfHormonio)
                    .where(ProtocoloIatfHormonio.lancamento_id == candidato.id)
                ).all()
            }
            if hormonios_candidato != hormonios_set:
                continue
        response.status_code = 200
        return {
            "criado": False, "lancamento_id": candidato.id, "eventos_criados": 0,
            "animais": len(animais_set),
            "aviso": (
                "Já existe um lançamento ativo idêntico deste protocolo (mesma data D0 "
                "e mesmo(s) animal(is)) — reaproveitado em vez de criar um duplicado."
            ),
        }

    # Os passos deste lançamento — dias do molde (livres, com dia de
    # inseminação calculado) quando um molde foi escolhido; D0/D7/D9/D11
    # clássico quando não (hormônios digitados na hora).
    passos = _passos_do_lancamento(session, dados.protocolo_id)
    dia_final = max(dias for dias, _ in passos)
    nome_protocolo = gerar_nome_lancamento(nome_base, dados.data_d0, 0, dia_final)
    lancamento = ProtocoloIatfLancamento(
        nome_protocolo=nome_protocolo, data_d0=dados.data_d0, protocolo_id=dados.protocolo_id,
        usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
    )
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
                dose=h.dose, unidade=h.unidade, via=h.via, fazenda_id=fazenda_id,
            ))

    def _descricao_dia(dias: int, padrao: str) -> str:
        hs = hormonios_por_dia.get(dias)
        if not hs:
            return padrao
        return " + ".join(f"{h.dose or ''}{(' ' + h.unidade) if h.unidade else ''} {h.produto}".strip() for h in hs)

    eventos_criados = 0
    for numero in dados.animais:
        # Colocar a matriz num protocolo novo é decidir que ela vai ser
        # inseminada de novo — logo, o serviço anterior que ainda estava sem
        # diagnóstico não pegou. Fecha como NEGATIVO aqui também, e não só no
        # lançamento da inseminação: entre o D0 e a IA passam ~11 dias, e
        # nesse intervalo o veterinário já precisa ver o histórico correto.
        fechar_servicos_abertos_por_reinseminacao(
            session, numero_matriz=numero, nova_data_servico=dados.data_d0, fazenda_id=fazenda_id,
        )
        for dias, descricao in passos:
            session.add(ProtocoloIatfAplicacao(
                lancamento_id=lancamento.id,
                numero_matriz=numero,
                dia=dias,
                descricao=_descricao_dia(dias, descricao),
                data_prevista=dados.data_d0 + timedelta(days=dias),
                fazenda_id=fazenda_id,
            ))
            eventos_criados += 1

    session.commit()
    return {"criado": True, "lancamento_id": lancamento.id, "eventos_criados": eventos_criados, "animais": len(dados.animais)}


# Grace period antes de considerar um protocolo IATF sem D11 confirmado como
# "abandonado" (vira concluido=True). Menor que o JANELA_ATRASO_DIAS (30) das
# outras famílias de propósito: aqui há um segundo teto mais apertado logo
# abaixo (proxima_visita + 7 dias, calculada a partir do intervalo entre
# visitas) que faz o protocolo sumir de vez da lista — uma janela de 30 dias
# nesta ponta não deixaria espaço nenhum para o card "concluído" aparecer.
# Sem NENHUMA janela (o bug original), 1-2 dias de atraso — o caso mais
# comum, ninguém deu baixa ainda — já escondia o protocolo bem na hora em
# que o usuário precisava achá-lo na tela de Inseminação para registrar o
# sêmen com atraso.
GRACA_D11_ATRASADO_DIAS = 7


@router.get("/protocolo-iatf/ativos")
def listar_protocolos_iatf_ativos(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Protocolos IATF com pelo menos uma etapa ainda não realizada — para ver de
    relance em qual dia (D0/D7/D9/D11) está cada animal em andamento.

    Um protocolo com TODAS as etapas concluídas (D11/inseminação já com
    baixa) some da lista principal, mas continua aparecendo por mais um
    ciclo (intervalo_visita_reprodutiva dias, editável em Configurações >
    Parâmetros) como "concluido": True, mostrando a data da próxima visita reprodutiva
    (D11 + intervalo) e as candidatas herd-wide ao próximo repasse (mesmo
    critério de `selecionar_candidatas_iatf`, usado na Agenda) — ver #369.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    from fazenda.rules.iatf import selecionar_candidatas_iatf
    from fazenda.rules.parametros import intervalo_visita_reprodutiva

    hoje = date.today()
    intervalo = intervalo_visita_reprodutiva()
    query_lancamentos = select(ProtocoloIatfLancamento).order_by(ProtocoloIatfLancamento.data_d0.desc())
    if fazenda_id is not None:
        query_lancamentos = query_lancamentos.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query_lancamentos).all()
    query_aplicacoes = select(ProtocoloIatfAplicacao)
    if fazenda_id is not None:
        query_aplicacoes = query_aplicacoes.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
    aplicacoes = session.exec(query_aplicacoes).all()
    por_lancamento: dict[int, list[ProtocoloIatfAplicacao]] = {}
    for ap in aplicacoes:
        por_lancamento.setdefault(ap.lancamento_id, []).append(ap)

    # Datas de serviço já registradas por animal — usado para decidir se o
    # protocolo "ainda está vigente" (nenhum serviço lançado depois do D0
    # deste lançamento) ou se já foi encerrado por uma inseminação. A
    # inseminação em si pode ser lançada bem depois de o hormônio ter sido
    # aplicado (a posteriori) — por isso "vigente" nunca depende de estar
    # exatamente na etapa D11 hoje, só de ainda não ter serviço no ciclo.
    query_servicos_datas = select(Servico.numero_matriz, Servico.data_servico)
    if fazenda_id is not None:
        query_servicos_datas = query_servicos_datas.where(Servico.fazenda_id == fazenda_id)
    datas_servico_por_animal: dict[str, list[date]] = {}
    for numero, data_servico in session.exec(query_servicos_datas).all():
        if data_servico is not None:
            datas_servico_por_animal.setdefault(numero, []).append(data_servico)

    def _vigente(numero: str, data_d0: date) -> bool:
        return not any(d >= data_d0 for d in datas_servico_por_animal.get(numero, []))

    _candidatas_cache: list | None = None

    def candidatas_herd() -> list[dict]:
        nonlocal _candidatas_cache
        if _candidatas_cache is None:
            from fazenda.rules.parametros import (
                get_param, idade_apta_min_meses, idade_max_1a_cobertura_meses, peso_apta_min, pev_dias,
            )
            from fazenda.rules.programa_reprodutivo import estado_no_dia

            hoje_ref = date.today()
            perfis = carregar_perfis_reprodutivos(session, fazenda_id)
            query_servicos = select(Servico).where(Servico.ult_ocorrencia == 1)
            if fazenda_id is not None:
                query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
            diag_por_animal = {
                s.numero_matriz: s.diagnostico for s in session.exec(query_servicos).all()
            }
            query_sit = select(Animal)
            if fazenda_id is not None:
                query_sit = query_sit.where(Animal.fazenda_id == fazenda_id)
            sit_por_animal = {a.numero: a.sit_rep for a in session.exec(query_sit).all()}

            kwargs_estado = {
                "pev_dias": pev_dias(),
                "del_max_1o_servico": int(get_param("meta_del_max_1o_servico", 100) or 100),
                "idade_apta_dias": int(idade_apta_min_meses() * 30.44), "idade_atraso_dias": int(idade_max_1a_cobertura_meses() * 30.44),
                "peso_apta_kg": peso_apta_min(),
            }
            # Mesmo critério da Agenda: quem está apta HOJE. `estado_no_dia` já
            # aplica R1 (a descartar / baixada), que `classificar_animal` não faz.
            estados = {
                perfil.numero: {
                    "estado": estado_no_dia(perfil, hoje_ref, **kwargs_estado).estado_reprodutivo,
                    "del_dias": _del_em(perfil, hoje_ref),
                }
                for perfil in perfis
            }
            entrada = [
                {"numero_matriz": perfil.numero, "sit_rep": sit_por_animal.get(perfil.numero),
                 "diagnostico_ultimo": diag_por_animal.get(perfil.numero)}
                for perfil in perfis
            ]
            candidatas = selecionar_candidatas_iatf(entrada, estados)
            _candidatas_cache = [
                {"numero_matriz": c.numero_matriz, "sit_rep": c.sit_rep, "del_dias": c.del_dias,
                 "motivo": c.motivo, "estado": c.estado, "estado_rotulo": c.estado_rotulo}
                for c in candidatas
            ]
        return _candidatas_cache

    ativos = []
    for lanc in lancamentos:
        aps = por_lancamento.get(lanc.id, [])
        pendentes = [a for a in aps if not a.realizada]
        # A etapa de inseminação é a de MAIOR dia deste lançamento — não
        # necessariamente D11 (molde com dias livres desloca esse número).
        maior_dia = max((a.dia for a in aps), default=None)
        d11s = [a for a in aps if a.dia == maior_dia] if maior_dia is not None else []

        # Concluído se todas as etapas já foram marcadas realizada OU se o
        # calendário já passou do D11 previsto por mais que GRACA_D11_ATRASADO_DIAS
        # — este segundo caso cobre o protocolo abandonado (ninguém marcou
        # "realizada" em cada etapa, e D0/D7/D9/D11 ficaram no passado por um
        # bom tempo). Só se aplica quando o D11 já está cadastrado — sem ele
        # não há data prevista pra comparar (protocolo ainda em
        # criação/incompleto).
        data_d11_prevista = max((a.data_prevista for a in d11s), default=None)
        concluido = not pendentes or (
            data_d11_prevista is not None
            and hoje > data_d11_prevista + timedelta(days=GRACA_D11_ATRASADO_DIAS)
        )
        if concluido:
            if not d11s:
                continue  # protocolo sem etapa D11 cadastrada — nada a projetar
            data_d11 = max((a.data_realizacao or a.data_prevista) for a in d11s)
            proxima_visita = data_d11 + timedelta(days=intervalo)
            if hoje > proxima_visita + timedelta(days=7):
                continue  # já passou da janela útil — não mostra mais
            aps_por_animal_concluido: dict[str, list[ProtocoloIatfAplicacao]] = {}
            for ap in aps:
                aps_por_animal_concluido.setdefault(ap.numero_matriz, []).append(ap)
            animais_concluidos = sorted(aps_por_animal_concluido.keys(), key=chave_numero)
            ativos.append({
                "lancamento_id": lanc.id,
                "nome_protocolo": lanc.nome_protocolo,
                "data_d0": lanc.data_d0.isoformat(),
                "animais": [
                    {
                        "numero_matriz": n, "etapa_atual": "Concluído", "data_etapa_atual": None,
                        # Se o D0 nunca foi marcado "realizado" para este animal,
                        # ela pode ter entrado no lançamento sem ter sido de fato
                        # implantada (ver diagnóstico "mais animais do que o
                        # implantado") — sinaliza para o usuário conferir.
                        "d0_confirmado": any(a.dia == 0 and a.realizada for a in aps_por_animal_concluido[n]),
                        # Protocolo "concluído" aqui só quer dizer que o hormônio
                        # já foi todo aplicado — é exatamente quando a
                        # inseminação está pronta pra ser lançada. Só deixa de
                        # estar "vigente" quando já existe um Serviço registrado
                        # depois do D0 deste lançamento (ver `_vigente`).
                        "pronta_para_inseminar": _vigente(n, lanc.data_d0),
                    }
                    for n in animais_concluidos
                ],
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
            pendentes_animal = [a for a in aps_animal if not a.realizada]
            if not pendentes_animal:
                animais_status.append({
                    "numero_matriz": numero, "etapa_atual": "Concluído", "data_etapa_atual": None, "d0_confirmado": True,
                    "pronta_para_inseminar": _vigente(numero, lanc.data_d0),
                })
                continue
            # Próxima etapa é sempre calculada pela DATA, não por qual etapa
            # foi marcada "realizada" — do contrário, uma etapa nunca
            # confirmada manualmente trava a exibição em "D0"/"D7" para
            # sempre, mesmo com o calendário já bem à frente (ver #reformular
            # relatório gerencial de IATF atual). Chega em D11 e fica lá até
            # ultrapassar data_d11_prevista, quando o grupo inteiro entra no
            # ramo "concluído" acima.
            by_dia = {a.dia: a for a in aps_animal}
            # Etapa de inseminação = a de MAIOR dia deste animal — não
            # necessariamente D11 (molde com dias livres desloca esse número).
            maior_dia_animal = max(a.dia for a in aps_animal)
            d0 = by_dia.get(0)
            d_insem = by_dia.get(maior_dia_animal)
            # Percorre as etapas pendentes anteriores à inseminação, em ordem
            # de dia — não mais só D0/D7/D9 fixos, pois um molde de dias
            # livres pode ter qualquer sequência (ex.: D0/D8/D10/D12). A
            # primeira ainda não vencida é a "próxima"; se todas já venceram,
            # cai na inseminação (ou na pendente mais antiga, se a
            # inseminação já foi confirmada mas sobrou alguma etapa anterior).
            pendentes_ordenados = sorted(pendentes_animal, key=lambda a: a.dia)
            proxima = next(
                (a for a in pendentes_ordenados if a.dia != maior_dia_animal and hoje <= a.data_prevista), None
            )
            if proxima is None:
                proxima = d_insem or pendentes_ordenados[0]
            animais_status.append({
                "numero_matriz": numero,
                "etapa_atual": f"D{proxima.dia}",
                "data_etapa_atual": proxima.data_prevista.isoformat(),
                "d0_confirmado": bool(d0 and d0.realizada),
                # Mantido por compatibilidade — indica só se a etapa de HOJE é a
                # de inseminação. Não pode comparar etapa_atual com a string
                # "D11", porque o dia de inseminação varia conforme o molde.
                "na_inseminacao": proxima.dia == maior_dia_animal,
                # A "sub-aba Inseminação" usa ESTE flag pra decidir se mostra a
                # matriz: o protocolo está vigente (ainda sem Serviço lançado
                # depois do D0), não importa em qual etapa do hormônio está
                # hoje — a inseminação pode ser lançada a posteriori.
                "pronta_para_inseminar": _vigente(numero, lanc.data_d0),
            })
        ativos.append({
            "lancamento_id": lanc.id,
            "nome_protocolo": lanc.nome_protocolo,
            "data_d0": lanc.data_d0.isoformat(),
            "animais": animais_status,
            "concluido": False,
        })
    return ativos


def _del_em(perfil, d: date) -> int | None:
    """DEL do animal NA DATA `d` — dias desde o último parto que já tinha
    acontecido até ali.

    Substitui a conta antiga de "DEL projetado" (`Animal.del_dias` congelado +
    dias até a visita), que herdava a defasagem do CSV e ainda somava dias a um
    número que podia estar errado desde o começo.

    Sem Parto (indução/aborto), `perfil.data_inicio_lactacao` serve de "parto
    virtual" — mesma âncora de `estado_reprodutivo.classificar_animal`. Entre
    os dois (quando existem ambos), vale o MAIS RECENTE — um parto antigo, de
    um ciclo de lactação já encerrado, não pode continuar ancorando o DEL
    depois de uma indução bem mais nova ter reaberto a lactação da matriz."""
    datas = []
    for p in perfil.partos:
        dp = p.get("data_parto") if isinstance(p, dict) else getattr(p, "data_parto", None)
        if isinstance(dp, str):
            try:
                dp = date.fromisoformat(dp[:10])
            except ValueError:
                dp = None
        if dp and dp <= d:
            datas.append(dp)
    dil = getattr(perfil, "data_inicio_lactacao", None)
    if dil and dil <= d:
        datas.append(dil)
    return (d - max(datas)).days if datas else None


@router.get("/protocolo-iatf/candidatas")
def candidatas_iatf_projetadas(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """Candidatas à próxima IATF (mesmo critério de `selecionar_candidatas_iatf`
    usado na Agenda), com projeção de aptidão na data da próxima visita reprodutiva —
    último serviço do rebanho + `intervalo_visita_reprodutiva` dias (Configurações
    > Parâmetros). Usado em Histórico > Reprodução > Ciclos de IATF."""
    from fazenda.rules.iatf import ESTADOS_CANDIDATA, selecionar_candidatas_iatf
    from fazenda.rules.parametros import (
        get_param, idade_apta_min_meses, idade_max_1a_cobertura_meses,
        intervalo_visita_reprodutiva, peso_apta_min,
    )
    from fazenda.rules.programa_reprodutivo import estado_no_dia

    fazenda_id = fazenda_id_seguro(fazenda_id)
    hoje = date.today()
    # `carregar_perfis_reprodutivos` traz as cinco cargas (Animal, Servico,
    # Parto, aplicações de IATF e pesagem) já indexadas, com escopo de fazenda e
    # sem machos nem sêmen — este endpoint antes não filtrava nem isso.
    perfis = carregar_perfis_reprodutivos(session, fazenda_id)

    query_servicos = select(Servico)
    if fazenda_id is not None:
        query_servicos = query_servicos.where(Servico.fazenda_id == fazenda_id)
    todos_servicos = session.exec(query_servicos).all()
    diag_por_animal = {s.numero_matriz: s.diagnostico for s in todos_servicos if s.ult_ocorrencia == 1}
    sit_rep_por_animal = {}
    query_sit = select(Animal)
    if fazenda_id is not None:
        query_sit = query_sit.where(Animal.fazenda_id == fazenda_id)
    for a in session.exec(query_sit).all():
        sit_rep_por_animal[a.numero] = a.sit_rep

    datas_servico = [s.data_servico for s in todos_servicos if s.data_servico]
    intervalo = intervalo_visita_reprodutiva()
    proxima_visita = (max(datas_servico) + timedelta(days=intervalo)) if (datas_servico and intervalo > 0) else None
    pev = int(get_param("pev_dias", 45) or 45)
    kwargs_estado = {
        "pev_dias": pev,
        "del_max_1o_servico": int(get_param("meta_del_max_1o_servico", 100) or 100),
        "idade_apta_dias": int(idade_apta_min_meses() * 30.44), "idade_atraso_dias": int(idade_max_1a_cobertura_meses() * 30.44),
        "peso_apta_kg": peso_apta_min(),
    }

    # A pergunta desta tela é "quem planejo para a VISITA", não "quem trabalho
    # hoje" — por isso o estado é avaliado na data da visita, e não somando dias
    # ao `Animal.del_dias` congelado como antes. Quem sai do PEV entre hoje e a
    # visita aparece; quem entra em protocolo ou é inseminada nesse meio-tempo,
    # não. A Agenda continua respondendo pelo dia de hoje.
    data_alvo = proxima_visita or hoje
    estados_hoje = {}
    estados_visita = {}
    for perfil in perfis:
        estados_hoje[perfil.numero] = estado_no_dia(perfil, hoje, **kwargs_estado)
        estados_visita[perfil.numero] = estado_no_dia(perfil, data_alvo, **kwargs_estado)

    entrada = [
        {"numero_matriz": p.numero, "sit_rep": sit_rep_por_animal.get(p.numero),
         "diagnostico_ultimo": diag_por_animal.get(p.numero)}
        for p in perfis
    ]
    # `estado_no_dia` já aplicou R1 (a descartar / baixada) na data da visita.
    mapa_visita = {
        n: {"estado": e.estado_reprodutivo, "del_dias": None}
        for n, e in estados_visita.items()
    }
    del_por_animal = {p.numero: _del_em(p, hoje) for p in perfis}
    del_visita = {p.numero: _del_em(p, data_alvo) for p in perfis}
    for n in mapa_visita:
        mapa_visita[n]["del_dias"] = del_por_animal.get(n)
    candidatas = selecionar_candidatas_iatf(entrada, mapa_visita)

    resultado = []
    for c in candidatas:
        estado_agora = estados_hoje.get(c.numero_matriz)
        resultado.append({
            "numero_matriz": c.numero_matriz, "sit_rep": c.sit_rep, "del_dias": c.del_dias,
            "motivo": c.motivo, "estado": c.estado, "estado_rotulo": c.estado_rotulo,
            "del_dias_projetado": del_visita.get(c.numero_matriz),
            # Ela É candidata na visita por construção — a lista já foi montada
            # com o estado daquela data. O campo sobrevive para a tela, e agora
            # significa o que o nome diz.
            "apta_na_proxima_visita": True,
            # Quem já está apta hoje pode ser trabalhada sem esperar a visita.
            "apta_hoje": bool(estado_agora and estado_agora.estado_reprodutivo in ESTADOS_CANDIDATA),
        })
    return {"candidatas": resultado, "proxima_visita_iatf": proxima_visita.isoformat() if proxima_visita else None}


@router.get("/protocolo-iatf/lancamentos")
def listar_lancamentos_iatf(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """
    Todos os lançamentos de protocolo IATF (para adicionar animais a um
    protocolo já existente — mesmo D0 e mesmo nome). Mais recentes primeiro.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query_lancamentos = select(ProtocoloIatfLancamento).order_by(
        ProtocoloIatfLancamento.data_d0.desc(), ProtocoloIatfLancamento.id.desc()
    )
    if fazenda_id is not None:
        query_lancamentos = query_lancamentos.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    lancamentos = session.exec(query_lancamentos).all()
    query_aplicacoes = select(ProtocoloIatfAplicacao)
    if fazenda_id is not None:
        query_aplicacoes = query_aplicacoes.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
    aplicacoes = session.exec(query_aplicacoes).all()
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
def adicionar_animais_iatf(
    lancamento_id: int,
    dados: AdicionarAnimaisIatfIn,
    session: Session = Depends(get_session),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Adiciona animais a um protocolo IATF já lançado (esqueci de incluí-los na
    hora). Reaproveita a MESMA data de D0 e os mesmos hormônios por dia; ignora
    animais que já estão no protocolo.
    """
    # Filtro na consulta (ver _buscar_da_fazenda): um lançamento IATF sem
    # molde (protocolo_id nulo) não tem pai de onde a migração de backfill
    # derive a fazenda, então ele continua órfão em instalação com 2+
    # fazendas — e a checagem tolerante deixava qualquer tenant despejar
    # animais dentro dele (fechando serviços em aberto das matrizes de
    # quebra, ver fechar_servicos_abertos_por_reinseminacao abaixo).
    lancamento = _buscar_da_fazenda(session, ProtocoloIatfLancamento, lancamento_id, fazenda_id)
    if not lancamento:
        raise HTTPException(status_code=404, detail="Protocolo IATF não encontrado")
    if not dados.animais:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")

    aplicacoes_existentes = session.exec(
        select(ProtocoloIatfAplicacao).where(ProtocoloIatfAplicacao.lancamento_id == lancamento_id)
    ).all()
    ja_no_protocolo = {a.numero_matriz for a in aplicacoes_existentes}
    # Os dias deste lançamento são os que ELE JÁ TEM — não o cronograma padrão
    # nem o molde reconsultado (que pode ter sido editado depois). Um animal
    # incluído depois entra exatamente nos mesmos dias que os que já estavam,
    # seja o lançamento clássico ou de um molde com dias livres (D0/D8/D10/D12).
    dias_do_lancamento = sorted({a.dia for a in aplicacoes_existentes})
    # Dia que bate com o cronograma clássico mantém a descrição de sempre
    # ("Implante de progesterona…"); dia livre de molde usa o rótulo genérico
    # — o mesmo comportamento de _passos_do_lancamento, para não regredir a
    # descrição do caso comum (D0/D7/D9/D11 sem molde).
    _padrao_classico = dict(PASSOS_PROTOCOLO_IATF)
    passos = [(d, _padrao_classico.get(d, f"Hormônio(s) do dia D{d}")) for d in dias_do_lancamento] or PASSOS_PROTOCOLO_IATF
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
        # Mesma regra do D0 (ver lancar_protocolo_iatf): entrar no protocolo
        # fecha o serviço anterior que ficou sem diagnóstico.
        fechar_servicos_abertos_por_reinseminacao(
            session, numero_matriz=numero, nova_data_servico=lancamento.data_d0, fazenda_id=fazenda_id,
        )
        for dias, descricao in passos:
            session.add(ProtocoloIatfAplicacao(
                lancamento_id=lancamento_id,
                numero_matriz=numero,
                dia=dias,
                descricao=_descricao_dia(dias, descricao),
                data_prevista=lancamento.data_d0 + timedelta(days=dias),
                fazenda_id=fazenda_id,
            ))
        novos += 1

    session.commit()
    return {"adicionados": novos, "lancamento_id": lancamento_id, "nome_protocolo": lancamento.nome_protocolo}


@router.delete("/protocolo-iatf/{lancamento_id}/animais/{numero_matriz}")
def remover_animal_iatf(
    lancamento_id: int, numero_matriz: str, session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    """
    Remove um animal de um lançamento IATF ativo — corrige uma inclusão por
    engano (seleção em lote na hora de lançar, ou vínculo indevido numa
    inseminação avulsa) sem precisar apagar o lançamento inteiro (a única
    ferramenta disponível até então). Só permite remover se NENHUMA etapa
    desse animal já foi confirmada — se já foi (e já gerou baixa de
    estoque/Sanidade), desmarque "Realizado" na Agenda primeiro.
    """
    fazenda_id = fazenda_id_seguro(fazenda_id)
    lancamento = _buscar_da_fazenda(session, ProtocoloIatfLancamento, lancamento_id, fazenda_id)
    if not lancamento:
        raise HTTPException(status_code=404, detail="Protocolo IATF não encontrado")

    aplicacoes = session.exec(
        select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.lancamento_id == lancamento_id,
            ProtocoloIatfAplicacao.numero_matriz == numero_matriz,
        )
    ).all()
    if not aplicacoes:
        raise HTTPException(status_code=404, detail="Este animal não está neste protocolo")
    if any(a.realizada for a in aplicacoes):
        raise HTTPException(
            status_code=409,
            detail="Este animal já tem etapa(s) confirmada(s) neste protocolo — desmarque \"Realizado\" na Agenda antes de remover.",
        )
    for a in aplicacoes:
        session.delete(a)
    session.commit()
    return {"removido": True, "lancamento_id": lancamento_id, "numero_matriz": numero_matriz}


def _mapa_tipo_semen_por_touro(session: Session, fazenda_id: int | None = None) -> dict[str, str]:
    """touro_nome (minúsculo) -> tipo (convencional/sexado/fazenda) do Estoque
    de Sêmen — usado para completar o tipo_semen de serviços antigos que não
    gravaram a modalidade no momento da inseminação.

    Filtrado por fazenda, igual à baixa de dose (_baixar_dose_semen): sem
    isso, o mapa era montado com o Estoque de Sêmen de TODAS as fazendas e a
    tela de análise completava o tipo do serviço com a modalidade cadastrada
    por outro tenant para um touro de mesmo nome."""
    mapa: dict[str, str] = {}
    query = select(EstoqueSemen)
    if fazenda_id is not None:
        query = query.where(EstoqueSemen.fazenda_id == fazenda_id)
    for e in session.exec(query).all():
        if e.touro_nome:
            mapa.setdefault(e.touro_nome.strip().lower(), e.tipo or "convencional")
    return mapa


def _baixar_dose_semen(
    session: Session, reprodutor: str | None, tipo_semen: str | None, quantidade: int,
    fazenda_id: int | None = None, usuario_id: int | None = None, data: date | None = None,
    origem_id: int | None = None,
) -> list[str]:
    """Desconta `quantidade` doses do Estoque de Sêmen do touro usado, casando
    por nome, NAAB ou código — filtrado pela fazenda atual, para nunca casar
    com o touro de outra fazenda com nome igual. Quando o tipo
    (sexado/convencional/fazenda) é conhecido, restringe o casamento a esse
    tipo primeiro — o mesmo touro pode ter linhas de estoque separadas por
    modalidade, e usar a errada bagunçaria o saldo de quem realmente tem
    doses. Sem casamento por tipo (ou tipo desconhecido), cai no casamento
    antigo por nome/NAAB/código, para não quebrar compras/lançamentos que
    ainda não informam o tipo.

    Diferente do comportamento antigo, agora grava um MovimentoEstoque (ver
    fazenda.rules.estoque_baixa.baixar_dose_semen) — a baixa deixava saldo
    cair sem rastro nenhum no histórico."""
    if not reprodutor:
        return []
    alvo = reprodutor.strip().lower()
    query = select(EstoqueSemen)
    if fazenda_id is not None:
        query = query.where(EstoqueSemen.fazenda_id == fazenda_id)
    candidatos = [
        t for t in session.exec(query).all()
        if (t.touro_nome or "").strip().lower() == alvo
        or (t.naab or "").strip().lower() == alvo
        or (t.codigo or "").strip().lower() == alvo
    ]
    if tipo_semen:
        por_tipo = [t for t in candidatos if t.tipo == tipo_semen]
        if por_tipo:
            candidatos = por_tipo
    touro = candidatos[0] if candidatos else None
    if not touro:
        return []
    return estoque_baixa.baixar_dose_semen(
        session, touro=touro, doses=quantidade, data=data or date.today(), fazenda_id=fazenda_id,
        usuario_id=usuario_id, observacao=f"Inseminação — {quantidade} dose(s) — {reprodutor}",
        origem_tipo="ia_semen", origem_id=origem_id,
    )


class ServicoIn(BaseModel):
    numero_matriz: str
    data_servico: date
    tipo_servico: str = "IA"  # "IA" | "Monta natural"
    protocolo: str | None = None  # preenchido = veio de um protocolo IATF; vazio = cio natural
    reprodutor: str | None = None
    responsavel: str | None = None
    tipo_semen: str | None = None  # convencional | sexado | fazenda
    # Confirmação explícita de quem lança para os bloqueios CONFIRMÁVEIS de
    # aptidão (novilha sem pesagem/abaixo do peso, matriz que consta como
    # gestante) — ver fazenda/rules/aptidao.py. Nunca destrava os bloqueios
    # duros (sexo, animal baixado, idade abaixo do mínimo).
    forcar: bool = False


@router.post("/servico")
def registrar_servico(
    dados: ServicoIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    """
    Registra a inseminação/cobertura em si — cio natural (sem protocolo) ou a
    inseminação de um protocolo IATF já agendado (protocolo preenchido).
    """
    query_animal = select(Animal).where(Animal.numero == dados.numero_matriz)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Matriz não encontrada")

    # Trava de aptidão (ver fazenda/rules/aptidao.py) — antes daqui não havia
    # nenhuma, e a checagem "≥ 13 meses" que existia só no frontend divergia
    # do parâmetro real da fazenda e não valia para o app de campo nem para o
    # bot do Telegram, que chamam esta rota direto.
    _exigir_aptidao(
        session, animal, data=dados.data_servico, fazenda_id=fazenda_id, forcar=dados.forcar,
    )

    query_anteriores = select(Servico).where(Servico.numero_matriz == dados.numero_matriz)
    if fazenda_id is not None:
        query_anteriores = query_anteriores.where(Servico.fazenda_id == fazenda_id)
    anteriores = session.exec(query_anteriores).all()
    for s in anteriores:
        if s.ult_ocorrencia == 1:
            s.ult_ocorrencia = 0
            session.add(s)

    ultimo = max(anteriores, key=lambda s: s.data_servico or date.min, default=None)
    ordem_tentativa = (ultimo.ordem_tentativa or 0) + 1 if ultimo else 1
    intervalo = (dados.data_servico - ultimo.data_servico).days if ultimo and ultimo.data_servico else None

    # Pedido do produtor: reinseminar uma vaca cujo serviço vigente ainda está
    # POSITIVO (sem perda registrada) só pode significar que a prenhez se
    # perdeu e ninguém contou pro sistema — grava a perda automaticamente no
    # serviço anterior (dia anterior a esta IA), motivo em aberto (vira
    # pendência "Cadastrar motivo da perda de prenhez" na Agenda). Sem efeito
    # quando não há prenhez vigente, quando a perda já foi registrada
    # (idempotente) ou quando um parto real já resolveu a gestação.
    perda_registrada = detectar_e_registrar_perda_por_reinseminacao(
        session, numero_matriz=dados.numero_matriz, nova_data_servico=dados.data_servico, fazenda_id=fazenda_id,
    )
    # E o caso irmão: serviço anterior que ficou SEM diagnóstico. A nova
    # inseminação prova que aquele não pegou, então ele fecha como NEGATIVO —
    # senão fica em aberto para sempre, sai do denominador da taxa de
    # concepção e polui o histórico da matriz.
    fechar_servicos_abertos_por_reinseminacao(
        session, numero_matriz=dados.numero_matriz, nova_data_servico=dados.data_servico, fazenda_id=fazenda_id,
    )

    servico = Servico(
        animal_id=animal.id,
        numero_matriz=dados.numero_matriz,
        raca_matriz=animal.raca,
        data_nasc_matriz=animal.data_nasc,
        data_servico=dados.data_servico,
        tipo_servico=dados.tipo_servico,
        protocolo=dados.protocolo,
        reprodutor=dados.reprodutor,
        tipo_semen=dados.tipo_semen,
        inseminador=dados.responsavel,
        ordem_tentativa=ordem_tentativa,
        intervalo_tentativas=intervalo,
        del_servico=animal.del_dias,
        ult_ocorrencia=1,
        usuario_id=usuario_id_seguro(user),
        fazenda_id=fazenda_id,
    )
    session.add(servico)
    session.flush()
    if perda_registrada is not None:
        # Guarda quem causou a perda automática — sem isso, excluir esta
        # inseminação depois não tinha como desfazer a perda que ela mesma
        # disparou no serviço anterior (ver exclusoes.py).
        perda_registrada.perda_causada_por_servico_id = servico.id
        session.add(perda_registrada)
    # Desconta 1 dose do Estoque de Sêmen (mesma regra do lançamento em lote,
    # ver registrar_servico_lote) — não se aplica a monta natural, que não usa
    # sêmen estocado.
    if dados.tipo_servico != "Monta natural":
        _baixar_dose_semen(
            session, dados.reprodutor, dados.tipo_semen, 1, fazenda_id=fazenda_id,
            usuario_id=usuario_id_seguro(user), data=dados.data_servico, origem_id=servico.id,
        )

    # Veio de um protocolo IATF: resolve automaticamente a aplicação de
    # inseminação em aberto correspondente — a Agenda para de lembrar essa
    # etapa sozinha, sem exigir um segundo clique de "marcar realizado" separado.
    if dados.protocolo:
        aplicacao_insem = _aplicacao_inseminacao_pendente(session, dados.numero_matriz, dados.protocolo, fazenda_id)
        if aplicacao_insem:
            aplicacao_insem.realizada = True
            aplicacao_insem.data_realizacao = dados.data_servico
            session.add(aplicacao_insem)

    session.commit()
    session.refresh(servico)
    return servico.model_dump()


def _aplicacao_inseminacao_pendente(
    session: Session, numero_matriz: str, nome_protocolo: str, fazenda_id: int | None,
) -> ProtocoloIatfAplicacao | None:
    """A aplicação de inseminação ainda pendente de um protocolo IATF, pelo
    nome do lançamento — usado ao registrar o serviço para fechar
    automaticamente essa etapa. Não é necessariamente D11: um molde com dias
    livres desloca esse número (ver fazenda.rules.protocolo_iatf); por isso o
    dia de inseminação é resolvido como "o maior dia DESTE lançamento",
    olhando TODAS as aplicações dele (realizadas ou não) — e só então checa
    se essa etapa específica ainda está pendente. Filtrar direto por
    `realizada == False` e pegar a de maior dia entre as pendentes seria
    errado: se a inseminação já tiver sido confirmada e uma etapa anterior
    (ex.: D9) por algum motivo ainda estiver pendente, isso marcaria a etapa
    errada como feita."""
    query_lanc = select(ProtocoloIatfLancamento).where(ProtocoloIatfLancamento.nome_protocolo == nome_protocolo)
    if fazenda_id is not None:
        query_lanc = query_lanc.where(ProtocoloIatfLancamento.fazenda_id == fazenda_id)
    lancamento_ids = [l.id for l in session.exec(query_lanc).all()]
    if not lancamento_ids:
        return None
    aps = session.exec(
        select(ProtocoloIatfAplicacao).where(
            ProtocoloIatfAplicacao.lancamento_id.in_(lancamento_ids),
            ProtocoloIatfAplicacao.numero_matriz == numero_matriz,
        )
    ).all()
    por_lancamento: dict[int, list[ProtocoloIatfAplicacao]] = {}
    for a in aps:
        por_lancamento.setdefault(a.lancamento_id, []).append(a)
    for aps_lancamento in por_lancamento.values():
        dia_insem = max(a.dia for a in aps_lancamento)
        candidata = next((a for a in aps_lancamento if a.dia == dia_insem and not a.realizada), None)
        if candidata:
            return candidata
    return None


def _nome_auto_iatf(d0: date) -> str:
    """Nome padrão de um protocolo IATF lançado retroativamente (sem molde),
    mesma regra de nomenclatura da Central de Protocolos."""
    return gerar_nome_lancamento("Protocolo IATF", d0, 0, 11)


def _registrar_um_servico(session: Session, numero_matriz: str, data_servico: date,
                          tipo_servico: str, protocolo: str | None, reprodutor: str | None,
                          inseminador: str | None = None, usuario_id: int | None = None,
                          tipo_semen: str | None = None, fazenda_id: int | None = None,
                          forcar: bool = False) -> Servico | None:
    """Cria um Servico para uma matriz (mesma lógica de registrar_servico, sem
    commit) — resolve a inseminação do protocolo IATF vinculado, se houver.

    Aplica a MESMA trava de aptidão de `registrar_servico` (ver
    fazenda/rules/aptidao.py): este é o caminho do lançamento em lote e do
    protocolo IATF, e deixá-lo de fora seria manter a porta dos fundos
    aberta justamente no ponto em que se lançam dezenas de animais de uma
    vez sem olhar um por um."""
    query_animal = select(Animal).where(Animal.numero == numero_matriz)
    if fazenda_id is not None:
        query_animal = query_animal.where(Animal.fazenda_id == fazenda_id)
    animal = session.exec(query_animal).first()
    if not animal:
        return None
    _exigir_aptidao(session, animal, data=data_servico, fazenda_id=fazenda_id, forcar=forcar)
    query_anteriores = select(Servico).where(Servico.numero_matriz == numero_matriz)
    if fazenda_id is not None:
        query_anteriores = query_anteriores.where(Servico.fazenda_id == fazenda_id)
    anteriores = session.exec(query_anteriores).all()
    for s in anteriores:
        if s.ult_ocorrencia == 1:
            s.ult_ocorrencia = 0
            session.add(s)
    ultimo = max(anteriores, key=lambda s: s.data_servico or date.min, default=None)
    ordem_tentativa = (ultimo.ordem_tentativa or 0) + 1 if ultimo else 1
    intervalo = (data_servico - ultimo.data_servico).days if ultimo and ultimo.data_servico else None
    # Mesma detecção automática de perda por reinseminação de registrar_servico
    # (ver o comentário lá) — este é o caminho usado por lançamento em lote e
    # pelo protocolo IATF, então precisa da mesma regra.
    perda_registrada = detectar_e_registrar_perda_por_reinseminacao(
        session, numero_matriz=numero_matriz, nova_data_servico=data_servico, fazenda_id=fazenda_id,
    )
    fechar_servicos_abertos_por_reinseminacao(
        session, numero_matriz=numero_matriz, nova_data_servico=data_servico, fazenda_id=fazenda_id,
    )
    servico = Servico(
        animal_id=animal.id, numero_matriz=numero_matriz, raca_matriz=animal.raca,
        data_nasc_matriz=animal.data_nasc, data_servico=data_servico, tipo_servico=tipo_servico,
        protocolo=protocolo, reprodutor=reprodutor, tipo_semen=tipo_semen, inseminador=inseminador,
        ordem_tentativa=ordem_tentativa,
        intervalo_tentativas=intervalo, del_servico=animal.del_dias, ult_ocorrencia=1, usuario_id=usuario_id,
        fazenda_id=fazenda_id,
    )
    session.add(servico)
    if protocolo:
        aplicacao_insem = _aplicacao_inseminacao_pendente(session, numero_matriz, protocolo, fazenda_id)
        if aplicacao_insem:
            aplicacao_insem.realizada = True
            aplicacao_insem.data_realizacao = data_servico
            session.add(aplicacao_insem)
    if perda_registrada is not None:
        # `servico` só ganha id no flush do chamador (precisa dele pra gravar
        # o vínculo) — guarda a referência num atributo comum (não é coluna
        # do model) pro chamador ler depois desse flush.
        servico._perda_registrada = perda_registrada
    return servico


def _animal_tem_protocolo_pendente(
    session: Session, numero_matriz: str, fazenda_id: int | None = None
) -> ProtocoloIatfLancamento | None:
    """Retorna o lançamento IATF com etapa pendente do animal (o mais recente)."""
    query_ap = select(ProtocoloIatfAplicacao).where(
        ProtocoloIatfAplicacao.numero_matriz == numero_matriz, ProtocoloIatfAplicacao.realizada == False  # noqa: E712
    )
    if fazenda_id is not None:
        query_ap = query_ap.where(ProtocoloIatfAplicacao.fazenda_id == fazenda_id)
    ap = session.exec(query_ap).all()
    if not ap:
        return None
    lanc_ids = {a.lancamento_id for a in ap}
    # Os lançamentos também são carregados filtrando por fazenda: as
    # aplicações acima já são as da fazenda, mas uma delas apontando para um
    # lançamento órfão/alheio (resíduo do backfill) traria o nome do
    # protocolo de outro tenant para dentro dos serviços gravados aqui.
    lancs = [
        l for l in (_buscar_da_fazenda(session, ProtocoloIatfLancamento, lid, fazenda_id) for lid in lanc_ids) if l
    ]
    return max(lancs, key=lambda l: l.data_d0, default=None) if lancs else None


class ServicoLoteIn(BaseModel):
    animais: list[str]
    data_servico: date
    tipo: str  # "cio_natural" | "iatf" | "monta_natural"
    reprodutor: str | None = None
    responsavel: str | None = None
    protocolo_lancamento_id: int | None = None  # IATF: vincular a este lançamento
    auto_lancar_iatf: bool = False  # IATF: se não há protocolo, cria um retroativo (D0 = serviço − 11)
    tipo_semen: str | None = None  # convencional | sexado | fazenda
    forcar: bool = False  # confirmação manual dos bloqueios confirmáveis de aptidão (ver rules/aptidao.py)


def _exigir_aptidao_do_lote(
    session: Session, numeros: list[str], *, data: date, fazenda_id: int | None, forcar: bool,
) -> None:
    """Valida a aptidão de TODOS os animais do lote ANTES de gravar qualquer
    coisa, e recusa o lote inteiro se algum estiver bloqueado.

    Tudo ou nada, de propósito: o lançamento em lote cria protocolos IATF
    retroativos e baixa dose de sêmen ao longo do laço, e abortar no meio
    deixaria metade do lote gravada com a outra metade recusada — o pior dos
    dois mundos para quem está no curral. Animais desconhecidos NÃO entram
    aqui: eles já têm o caminho `incompativeis`, que a UI sabe tratar.
    """
    bloqueados: list[tuple[str, AptidaoResultado]] = []
    params = parametros_aptidao()
    for numero in numeros:
        query = select(Animal).where(Animal.numero == numero)
        if fazenda_id is not None:
            query = query.where(Animal.fazenda_id == fazenda_id)
        animal = session.exec(query).first()
        if animal is None:
            continue
        resultado = avaliar_aptidao_no_banco(session, animal, data=data, fazenda_id=fazenda_id, params=params)
        if resultado.bloqueia(forcar):
            bloqueados.append((numero, resultado))
        elif not resultado.apta and forcar:
            logger.info(
                "Aptidão forçada manualmente (lote): matriz=%s motivo=%s data=%s", numero, resultado.motivo, data,
            )
    if not bloqueados:
        return
    primeiro = bloqueados[0][1]
    confirmavel = all(r.confirmavel for _, r in bloqueados)
    detalhes = "; ".join(r.mensagem for _, r in bloqueados if r.mensagem)
    resumo = AptidaoResultado(
        apta=False,
        motivo=primeiro.motivo if len({r.motivo for _, r in bloqueados}) == 1 else "varios",
        mensagem=(
            f"{len(bloqueados)} animal(is) do lote não estão aptos a receber serviço: {detalhes}"
            if len(bloqueados) > 1 else detalhes
        ),
        severidade=primeiro.severidade if confirmavel else "duro",
    )
    raise HTTPException(status_code=409, detail=_detalhe_aptidao(resumo, [n for n, _ in bloqueados]))


@router.post("/servico-lote")
def registrar_servico_lote(
    dados: ServicoLoteIn,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
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

    _exigir_aptidao_do_lote(
        session, dados.animais, data=dados.data_servico, fazenda_id=fazenda_id, forcar=dados.forcar,
    )

    tipo_servico = "Monta natural" if dados.tipo == "monta_natural" else "IA"
    # `protocolo_lancamento_id` vem do corpo da requisição: carga filtrada por
    # fazenda (ver _buscar_da_fazenda), em vez do `session.get` + checagem
    # tolerante a NULL de antes — vincular o serviço a um lançamento alheio
    # ou órfão carimbava o nome do protocolo de outra fazenda nos serviços
    # gravados aqui e confirmava a etapa de inseminação lá.
    lanc_escolhido = _buscar_da_fazenda(
        session, ProtocoloIatfLancamento, dados.protocolo_lancamento_id, fazenda_id,
    )

    criados, incompativeis = 0, []
    servicos_criados: list[Servico] = []
    for numero in dados.animais:
        protocolo_name: str | None = None
        if dados.tipo == "iatf":
            alvo = lanc_escolhido or _animal_tem_protocolo_pendente(session, numero, fazenda_id=fazenda_id)
            if alvo is None and dados.auto_lancar_iatf:
                d0 = dados.data_servico - timedelta(days=11)
                alvo = ProtocoloIatfLancamento(
                    nome_protocolo=_nome_auto_iatf(d0), data_d0=d0, retroativo=True,
                    usuario_id=usuario_id_seguro(user), fazenda_id=fazenda_id,
                )
                session.add(alvo)
                session.flush()
                for dias, descricao in PASSOS_PROTOCOLO_IATF:
                    session.add(ProtocoloIatfAplicacao(
                        lancamento_id=alvo.id, numero_matriz=numero, dia=dias,
                        descricao=descricao, data_prevista=d0 + timedelta(days=dias),
                        fazenda_id=fazenda_id,
                    ))
            elif alvo is not None:
                ja = session.exec(
                    select(ProtocoloIatfAplicacao).where(
                        ProtocoloIatfAplicacao.lancamento_id == alvo.id,
                        ProtocoloIatfAplicacao.numero_matriz == numero,
                    )
                ).first()
                if not ja:
                    # O animal não foi de fato implantado neste lançamento —
                    # nunca fabrica um histórico D0-D11 retroativo por engano de
                    # seleção (ex.: "Inseminação avulsa" com um lote inteiro,
                    # tipo IATF, vinculado a um protocolo que não é dela). Sem
                    # isso, o lançamento ganhava animal(is) a mais na lista de
                    # "Protocolos IATF em andamento" sem nunca ter passado pelo
                    # D0 — a Agenda inteira do protocolo é inventada aqui.
                    # Cai em incompatíveis, igual a "nenhum protocolo encontrado".
                    alvo = None
            if alvo is None:
                incompativeis.append(numero)
                continue
            session.flush()
            protocolo_name = alvo.nome_protocolo

        s = _registrar_um_servico(
            session, numero, dados.data_servico, tipo_servico, protocolo_name, dados.reprodutor, dados.responsavel,
            usuario_id=usuario_id_seguro(user), tipo_semen=dados.tipo_semen, fazenda_id=fazenda_id,
            forcar=dados.forcar,
        )
        if s is None:
            incompativeis.append(numero)
        else:
            session.flush()  # precisa do id antes de usá-lo como origem_id da baixa, abaixo
            perda_registrada = getattr(s, "_perda_registrada", None)
            if perda_registrada is not None:
                perda_registrada.perda_causada_por_servico_id = s.id
                session.add(perda_registrada)
            servicos_criados.append(s)
            criados += 1

    # Desconta 1 dose por inseminação realizada (IA — cio natural ou IATF; não
    # se aplica à monta natural, que não usa sêmen estocado) do touro
    # informado — mantém o Estoque de Sêmen em dia com o uso real sem exigir
    # baixa manual a cada inseminação. Baixa POR ANIMAL, não uma única
    # agregada pro lote inteiro (mesmo motivo do padrão em sanidade.py
    # registrar_aplicacao): cada MovimentoEstoque fica com origem_id=servico.id
    # — sem isso, excluir o Serviço de UM animal do lote nunca achava o que
    # estornar (o estorno de exclusoes.py busca por origem_id) e a dose
    # daquele animal nunca voltava ao estoque.
    if dados.tipo != "monta_natural" and dados.reprodutor:
        for s in servicos_criados:
            _baixar_dose_semen(
                session, dados.reprodutor, dados.tipo_semen, 1, fazenda_id=fazenda_id,
                usuario_id=usuario_id_seguro(user), data=dados.data_servico, origem_id=s.id,
            )

    session.commit()
    return {"criados": criados, "incompativeis": incompativeis, "tipo": dados.tipo}


# ---------------------------------------------------------------------------
# Indução de cio (PGF2α/Cloprostenol) — estímulo hormonal aplicado geralmente
# nos últimos dias do PEV para a vaca entrar em cio em 2 a 5 dias. Guardado
# como Sanidade (mesmo padrão que BST já usa em agenda.py::aplicar_bst_lote)
# com `atividade` própria — gera histórico, mas de propósito NÃO é gravado em
# Servico (inseminação) nem em ProtocoloIatf*: não é IATF, não é diagnóstico,
# só um estímulo para o cio aparecer naturalmente (o cio observado depois vira
# um Serviço/IA normal, lançado à parte). A Agenda usa esta atividade para
# lembrar de observar o cio na janela de 2 a 5 dias (ver agenda_engine.py,
# bloco "3b").
# ---------------------------------------------------------------------------
ATIVIDADE_INDUCAO_CIO = "Indução de cio"


class InducaoCioIn(BaseModel):
    numeros_matriz: list[str]
    data_aplicacao: date
    produto: str = "Cloprostenol"
    dose: float | None = None
    unidade: str | None = None
    via: str | None = None
    responsavel: str | None = None
    observacao: str | None = None


@router.post("/inducao-cio", status_code=201)
def registrar_inducao_cio(
    dados: InducaoCioIn, session: Session = Depends(get_session), user: Usuario = Depends(get_current_user),
    fazenda_id: int = Depends(get_fazenda_id_escrita),
) -> dict:
    if not dados.numeros_matriz:
        raise HTTPException(status_code=400, detail="Selecione ao menos um animal")
    usuario_id = usuario_id_seguro(user)
    avisos: list[str] = []
    for numero in dados.numeros_matriz:
        sanidade = Sanidade(
            numero_matriz=numero, data_aplicacao=dados.data_aplicacao, produto=dados.produto,
            dose=dados.dose, unidade=dados.unidade, via=dados.via, responsavel=dados.responsavel,
            atividade=ATIVIDADE_INDUCAO_CIO, obs=dados.observacao, natureza="preventivo",
            usuario_id=usuario_id, fazenda_id=fazenda_id,
        )
        session.add(sanidade)
        session.flush()
        if dados.dose and dados.unidade:
            estoque_item = estoque_baixa.resolver_item(session, fazenda_id=fazenda_id, produto=dados.produto)
            avisos.extend(estoque_baixa.baixar(
                session, item=estoque_item, quantidade=dados.dose, unidade=dados.unidade, data=dados.data_aplicacao,
                fazenda_id=fazenda_id, observacao=f"Indução de cio — matriz {numero}", usuario_id=usuario_id,
                origem_tipo="inducao_cio", origem_id=sanidade.id, produto=dados.produto,
            ))
    session.commit()
    return {"aplicados": len(dados.numeros_matriz), "avisos": avisos}


@router.get("/inducao-cio")
def listar_inducoes_cio(
    session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    query = select(Sanidade).where(Sanidade.atividade == ATIVIDADE_INDUCAO_CIO)
    if fazenda_id is not None:
        query = query.where(Sanidade.fazenda_id == fazenda_id)
    lancamentos = session.exec(query.order_by(Sanidade.data_aplicacao.desc())).all()
    return [
        {
            "id": s.id, "numero_matriz": s.numero_matriz, "data_aplicacao": s.data_aplicacao.isoformat() if s.data_aplicacao else None,
            "produto": s.produto, "dose": s.dose, "unidade": s.unidade, "via": s.via,
            "responsavel": s.responsavel, "observacao": s.obs,
        }
        for s in lancamentos
    ]


@router.delete("/inducao-cio/{lancamento_id}")
def excluir_inducao_cio(
    lancamento_id: int, session: Session = Depends(get_session), fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    sanidade = _buscar_da_fazenda(session, Sanidade, lancamento_id, fazenda_id)
    if not sanidade or sanidade.atividade != ATIVIDADE_INDUCAO_CIO:
        raise HTTPException(status_code=404, detail="Lançamento de indução de cio não encontrado")
    session.delete(sanidade)
    session.commit()
    return {"excluido": True}
