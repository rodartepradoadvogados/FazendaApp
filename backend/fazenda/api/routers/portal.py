"""
Router do Portal (Administração > Portal) — comunicação interna entre
usuários: enviar mensagem (com pedido de retorno), enviar e-mail (livre ou
relatório gerencial) e delegar tarefa. Mensagens/tarefas pendentes alimentam
a central de alertas (ver fazenda.api.routers.notificacoes); tarefas também
geram um evento na Agenda (AgendaManual é um calendário único da fazenda —
"cai na agenda do destinatário" aqui significa um evento marcado com o nome
do destinatário, não uma agenda privada por usuário, que não existe hoje).
"""
from __future__ import annotations

import csv
import html
import io
import zipfile
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id, multifazenda_provisionado
from fazenda.database import engine, get_session
from fazenda.models import (
    AgendaManual, Animal, CompraAnimal, ContaGerencial, ControleLeiteiro, MovimentoEstoque, Estoque,
    Parto, Pessoa, PortalMensagem, Sanidade, Servico, Usuario, UsuarioFazenda, VendaAnimal,
)
from fazenda.rules.auditoria import fazenda_id_seguro
from fazenda.rules.email import enviar_email

router = APIRouter(prefix="/portal", tags=["portal"])

# Abas do site que podem ser referenciadas em uma mensagem/tarefa — só abas de
# 1º nível, nunca sub-abas (conforme pedido do usuário).
ABAS_VALIDAS = [
    "sanidade", "alimentacao", "estoque", "indicadores", "financeiro",
    "pedidos", "listas", "lancamentos", "agenda",
]

# Job-roles (Pessoa.tipo) que liberam "Delegar tarefa", além de Usuario.papel
# == "admin".
TIPOS_DELEGAM_TAREFA = {"Veterinário", "Zootecnista", "Geral"}


def _usuario_pode_delegar_tarefa(user: Usuario, session: Session) -> bool:
    if user.papel == "admin":
        return True
    if not user.pessoa_id:
        return False
    pessoa = session.get(Pessoa, user.pessoa_id)
    if not pessoa:
        return False
    tipos = {t.strip() for t in pessoa.tipo.split(",")}
    return bool(tipos & TIPOS_DELEGAM_TAREFA)


def usuarios_da_fazenda(session: Session, fazenda_id: int | None) -> list[Usuario]:
    """Usuários ativos vinculados a uma fazenda (via UsuarioFazenda), menos o
    robô-milknews. Compartilhado entre listar_destinatarios (Portal) e o
    fan-out de fotos do campo (fotos.py) — mesma regra de "quem pode ser
    destinatário nesta fazenda" nos dois lugares."""
    if fazenda_id is None:
        usuarios = session.exec(select(Usuario).where(Usuario.ativo == True)).all()  # noqa: E712
    else:
        usuarios = session.exec(
            select(Usuario)
            .join(UsuarioFazenda, UsuarioFazenda.usuario_id == Usuario.id)
            .where(Usuario.ativo == True, UsuarioFazenda.fazenda_id == fazenda_id)  # noqa: E712
            .distinct()
        ).all()
    return [u for u in usuarios if u.username != "robo-milknews"]


def _fazenda_obrigatoria(session: Session, fazenda_id: int | None) -> int | None:
    """A fazenda de quem está exportando/enviando relatório — ou 409.

    As duas rotas que usam isto (`POST /portal/exportar` e o anexo de
    `POST /portal/email`) são as únicas do sistema que despacham dado de
    fazenda para FORA dele, por e-mail, em lote. Por isso elas não confiam só
    no `exigir_fazenda_selecionada` do include_router (main.py): repetem a
    checagem aqui, na própria função, onde ela não some se alguém remontar o
    router amanhã. `_executar_exportacao` ainda por cima roda DEPOIS da
    resposta, numa BackgroundTask com sessão própria — quanto mais perto do
    ponto de leitura a trava estiver, melhor.

    A escape hatch é a mesma — e pela mesma razão — de
    `exigir_fazenda_selecionada`/`resolver_fazenda_id_escrita`: com a tabela
    `fazenda` VAZIA o multi-fazenda não está provisionado neste ambiente e não
    há tenant a isolar (instalação anterior à migração f1a2b3c4d5e6 e boa
    parte da suíte de testes). Havendo QUALQUER fazenda cadastrada — todo
    ambiente de produção — sem fazenda no token não se exporta nada."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    if fazenda_id is None and multifazenda_provisionado(session):
        raise HTTPException(
            status_code=409,
            detail="Sua sessão não tem uma fazenda selecionada. Saia e entre novamente para escolher "
                   "em qual fazenda deseja trabalhar antes de exportar ou enviar relatórios.",
            headers={"X-Fazenda-Nao-Selecionada": "1"},
        )
    return fazenda_id


def _serializar(m: PortalMensagem, session: Session) -> dict:
    remetente = session.get(Usuario, m.remetente_usuario_id)
    destinatario = session.get(Usuario, m.destinatario_usuario_id)
    return {
        "id": m.id,
        "tipo": m.tipo,
        "remetente": remetente.nome or remetente.username if remetente else None,
        "remetente_usuario_id": m.remetente_usuario_id,
        "destinatario": destinatario.nome or destinatario.username if destinatario else None,
        "destinatario_usuario_id": m.destinatario_usuario_id,
        "aba": m.aba,
        "corpo": m.corpo,
        "pede_retorno": m.pede_retorno,
        "lida": m.lida,
        "resolvida": m.resolvida,
        "resposta_de_id": m.resposta_de_id,
        "foto_campo_id": m.foto_campo_id,
        "criado_em": m.criado_em.isoformat(),
    }


@router.get("/permissoes")
def minhas_permissoes(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    return {"pode_delegar_tarefa": _usuario_pode_delegar_tarefa(user, session)}


@router.get("/destinatarios")
def listar_destinatarios(
    user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    """Lista para o "@" — usuários ativos vinculados à MESMA fazenda (via
    UsuarioFazenda), menos o robô-milknews. Antes trazia todo mundo ativo do
    sistema, de qualquer fazenda — vazamento real (um usuário podia mandar
    mensagem/tarefa pra alguém de outra fazenda, que nem aparece na tela dele)."""
    fazenda_id = fazenda_id_seguro(fazenda_id)
    usuarios = usuarios_da_fazenda(session, fazenda_id)
    return [{"id": u.id, "nome": u.nome or u.username, "username": u.username} for u in usuarios]


# ---------------------------------------------------------------------------
# Comunicação > Enviar mensagem
# ---------------------------------------------------------------------------
class MensagemIn(BaseModel):
    destinatarios_usuario_id: list[int]  # "marcar todos" já resolvido no front p/ a lista completa
    aba: Optional[str] = None
    corpo: str
    pede_retorno: bool = False


@router.post("/mensagens")
def enviar_mensagem(
    dados: MensagemIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if dados.aba and dados.aba not in ABAS_VALIDAS:
        raise HTTPException(400, f"Aba inválida: {dados.aba}")
    if not dados.corpo.strip():
        raise HTTPException(400, "Mensagem vazia")
    if not dados.destinatarios_usuario_id:
        raise HTTPException(400, "Selecione ao menos um destinatário")

    # BUG DE SEGURANÇA CORRIGIDO: só conferia que o usuário EXISTIA
    # (`session.get(Usuario, dest_id)`), não que ele era da MESMA fazenda de
    # quem está enviando — dava pra mandar mensagem (com pedido de retorno)
    # pra qualquer id de usuário de OUTRA fazenda, que caía direto na caixa
    # de entrada dele (`mensagens_pendentes` só olha destinatario_usuario_id,
    # sem fazenda_id). Mesma lista de `listar_destinatarios` acima (o "@" já
    # usa `usuarios_da_fazenda`) — só quem já aparece nesse seletor pode ser
    # destinatário de fato.
    fazenda_id = fazenda_id_seguro(fazenda_id)
    ids_validos = {u.id for u in usuarios_da_fazenda(session, fazenda_id)}
    criadas = []
    for dest_id in dados.destinatarios_usuario_id:
        if not session.get(Usuario, dest_id) or dest_id not in ids_validos:
            raise HTTPException(404, f"Usuário {dest_id} não encontrado")
        m = PortalMensagem(
            tipo="mensagem",
            remetente_usuario_id=user.id,
            destinatario_usuario_id=dest_id,
            aba=dados.aba,
            corpo=dados.corpo.strip(),
            pede_retorno=dados.pede_retorno,
            fazenda_id=fazenda_id,
        )
        session.add(m)
        criadas.append(m)
    session.commit()
    return {"criadas": len(criadas)}


@router.get("/mensagens/pendentes")
def mensagens_pendentes(user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> list[dict]:
    """O que ainda deve aparecer na central de alertas do usuário logado:
    tarefas/mensagens recebidas não lidas, e mensagens com pedido de retorno
    ainda não resolvidas (mesmo já lidas)."""
    pendentes = session.exec(
        select(PortalMensagem).where(
            PortalMensagem.destinatario_usuario_id == user.id,
            PortalMensagem.resolvida == False,  # noqa: E712
        )
    ).all()
    return [_serializar(m, session) for m in pendentes if not m.lida or m.pede_retorno]


@router.post("/mensagens/{mensagem_id}/marcar-lida")
def marcar_lida(mensagem_id: int, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    m = session.get(PortalMensagem, mensagem_id)
    if not m or m.destinatario_usuario_id != user.id:
        raise HTTPException(404, "Mensagem não encontrada")
    m.lida = True
    if not m.pede_retorno:
        m.resolvida = True
    session.add(m)
    session.commit()
    return {"ok": True}


@router.post("/mensagens/{mensagem_id}/resolver")
def resolver_mensagem(mensagem_id: int, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    m = session.get(PortalMensagem, mensagem_id)
    if not m or m.destinatario_usuario_id != user.id:
        raise HTTPException(404, "Mensagem não encontrada")
    m.lida = True
    m.resolvida = True
    session.add(m)
    session.commit()
    return {"ok": True}


class RespostaIn(BaseModel):
    corpo: str
    aba: Optional[str] = None


@router.post("/mensagens/{mensagem_id}/responder")
def responder_mensagem(mensagem_id: int, dados: RespostaIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    if dados.aba and dados.aba not in ABAS_VALIDAS:
        raise HTTPException(400, f"Aba inválida: {dados.aba}")
    original = session.get(PortalMensagem, mensagem_id)
    if not original or original.destinatario_usuario_id != user.id:
        raise HTTPException(404, "Mensagem não encontrada")
    if not dados.corpo.strip():
        raise HTTPException(400, "Resposta vazia")

    original.lida = True
    original.resolvida = True
    session.add(original)

    resposta = PortalMensagem(
        tipo="mensagem",
        remetente_usuario_id=user.id,
        destinatario_usuario_id=original.remetente_usuario_id,
        aba=dados.aba,
        corpo=dados.corpo.strip(),
        pede_retorno=False,
        resposta_de_id=original.id,
        fazenda_id=original.fazenda_id,
    )
    session.add(resposta)
    session.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Comunicação > Enviar e-mail
# ---------------------------------------------------------------------------
RELATORIOS_DISPONIVEIS = {
    "dre": "DRE",
    "rmca": "RMCA",
    "custo_litro_leite": "Custo por litro de leite",
}


@router.get("/relatorios-disponiveis")
def relatorios_disponiveis() -> dict:
    return RELATORIOS_DISPONIVEIS


def _dict_para_csv(dados: dict) -> str:
    """Achata um dict de relatório (campos escalares + no máx. 1 nível de dict
    aninhado, tipo {codigo: {...}}) em texto CSV — usado tanto no e-mail de
    "enviar relatório" quanto no carrinho de Exportar."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    tabelas_aninhadas: dict[str, dict] = {}
    for chave, valor in dados.items():
        if isinstance(valor, dict) and valor and all(isinstance(v, dict) for v in valor.values()):
            tabelas_aninhadas[chave] = valor
        elif isinstance(valor, dict):
            writer.writerow([chave, ""])
            for subchave, subvalor in valor.items():
                writer.writerow([f"  {subchave}", subvalor])
        elif isinstance(valor, list):
            writer.writerow([chave, "; ".join(str(v) for v in valor)])
        else:
            writer.writerow([chave, valor])

    for nome_tabela, linhas in tabelas_aninhadas.items():
        writer.writerow([])
        primeira = next(iter(linhas.values()))
        colunas = list(primeira.keys())
        writer.writerow([nome_tabela] + colunas)
        for identificador, linha in linhas.items():
            writer.writerow([identificador] + [linha.get(c, "") for c in colunas])

    return buffer.getvalue()


class EmailIn(BaseModel):
    destinatarios_usuario_id: list[int]
    assunto: str
    corpo: Optional[str] = None
    relatorio: Optional[str] = None  # "dre" | "rmca" | "custo_litro_leite"
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None


@router.post("/email")
def enviar_email_portal(
    dados: EmailIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if not dados.destinatarios_usuario_id:
        raise HTTPException(400, "Selecione ao menos um destinatário")
    if not dados.assunto.strip():
        raise HTTPException(400, "Assunto obrigatório")

    corpo_html = f"<p>{html.escape(dados.corpo)}</p>" if dados.corpo else "<p></p>"
    anexo_nome = None
    anexo_bytes = None

    if dados.relatorio:
        if dados.relatorio not in RELATORIOS_DISPONIVEIS:
            raise HTTPException(400, f"Relatório inválido: {dados.relatorio}")
        if not dados.data_inicio or not dados.data_fim:
            raise HTTPException(400, "Informe o período (de/até) do relatório")
        from fazenda.api.routers.financeiro import dre, rmca, custo_litro_leite

        # BUG DE SEGURANÇA CORRIGIDO: dre/rmca/custo_litro_leite são rotas
        # FastAPI com `fazenda_id: int | None = Depends(get_fazenda_atual_id)`
        # — chamadas direto como função Python (sem passar fazenda_id), esse
        # parâmetro ficava com o próprio objeto Depends(...), que
        # fazenda_id_seguro() convertia para None, desligando todo filtro por
        # fazenda dentro delas. Passar fazenda_id explícito fecha o vazamento.
        #
        # Só que passar `None` explícito desliga o filtro do mesmo jeito (lá
        # dentro o padrão é o tolerante `if fazenda_id is not None`), e este
        # anexo sai do sistema por e-mail. Então aqui não existe caminho
        # "sem fazenda": ou a sessão diz qual é, ou não há relatório.
        fazenda_id = _fazenda_obrigatoria(session, fazenda_id)
        if dados.relatorio == "dre":
            resultado = dre(data_inicio=dados.data_inicio, data_fim=dados.data_fim, centro_custo=None, regime="competencia", session=session, fazenda_id=fazenda_id)
        elif dados.relatorio == "rmca":
            resultado = rmca(data_inicio=dados.data_inicio, data_fim=dados.data_fim, session=session, fazenda_id=fazenda_id)
        else:
            resultado = custo_litro_leite(data_inicio=dados.data_inicio, data_fim=dados.data_fim, session=session, fazenda_id=fazenda_id)

        csv_texto = _dict_para_csv(resultado)
        anexo_nome = f"{dados.relatorio}_{dados.data_inicio.isoformat()}_{dados.data_fim.isoformat()}.csv"
        anexo_bytes = csv_texto.encode("utf-8-sig")
        corpo_html += f"<p>Relatório {RELATORIOS_DISPONIVEIS[dados.relatorio]} em anexo (período {dados.data_inicio.isoformat()} a {dados.data_fim.isoformat()}).</p>"

    # BUG DE SEGURANÇA CORRIGIDO: mesmo furo que `enviar_mensagem` e
    # `delegar_tarefa` já tinham fechado, e que esta rota — a única das três
    # que manda o dado para FORA do sistema — continuava com aberto: só
    # conferia que o usuário EXISTIA, não que era da MESMA fazenda de quem
    # está enviando. Cenário concreto: o admin da fazenda 2 escolhe o id de um
    # funcionário da fazenda 1 e dispara para o e-mail pessoal dele a DRE da
    # fazenda 2 — o relatório sai do tenant — ou um texto livre qualquer, que
    # chega com a cara de comunicação oficial da plataforma. Mesma lista do
    # seletor "@" (`listar_destinatarios`): só quem já aparece lá pode receber.
    ids_validos = {u.id for u in usuarios_da_fazenda(session, fazenda_id_seguro(fazenda_id))}
    enviados = 0
    for dest_id in dados.destinatarios_usuario_id:
        destinatario = session.get(Usuario, dest_id)
        if not destinatario or dest_id not in ids_validos:
            raise HTTPException(404, f"Usuário {dest_id} não encontrado")
        if not destinatario.email:
            raise HTTPException(400, f"Usuário {destinatario.nome or destinatario.username} não tem e-mail cadastrado")
        enviar_email(destinatario.email, dados.assunto.strip(), corpo_html, anexo_nome, anexo_bytes)
        enviados += 1

    return {"enviados": enviados}


# ---------------------------------------------------------------------------
# Comunicação > Delegar tarefa
# ---------------------------------------------------------------------------
class TarefaIn(BaseModel):
    destinatarios_usuario_id: list[int]
    corpo: str
    data_evento: Optional[date] = None  # default: hoje


@router.post("/tarefas")
def delegar_tarefa(
    dados: TarefaIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> dict:
    if not _usuario_pode_delegar_tarefa(user, session):
        raise HTTPException(403, "Seu tipo de usuário não pode delegar tarefas")
    if not dados.corpo.strip():
        raise HTTPException(400, "Tarefa vazia")
    if not dados.destinatarios_usuario_id:
        raise HTTPException(400, "Selecione ao menos um destinatário")

    fazenda_id = fazenda_id_seguro(fazenda_id)
    # BUG DE SEGURANÇA CORRIGIDO: mesmo furo de `enviar_mensagem` acima — só
    # conferia existência do usuário, não a fazenda dele. Aqui era ainda mais
    # sensível: além da PortalMensagem cross-tenant, criava uma AgendaManual
    # "de graça" (com o nome real do delegante) na fazenda de quem delegou,
    # citando um destinatário de outra fazenda.
    ids_validos = {u.id for u in usuarios_da_fazenda(session, fazenda_id)}
    data_evento = dados.data_evento or date.today()
    criadas = []
    for dest_id in dados.destinatarios_usuario_id:
        destinatario = session.get(Usuario, dest_id)
        if not destinatario or dest_id not in ids_validos:
            raise HTTPException(404, f"Usuário {dest_id} não encontrado")

        evento = AgendaManual(
            data_evento=data_evento,
            descricao=f"Tarefa de {user.nome or user.username} para {destinatario.nome or destinatario.username}: {dados.corpo.strip()}",
            categoria="Gestão/Financeiro",
            tipo_evento="Serviço",
            usuario_id=user.id,
            fazenda_id=fazenda_id,
        )
        session.add(evento)
        session.flush()  # garante evento.id antes de vincular

        tarefa = PortalMensagem(
            tipo="tarefa",
            remetente_usuario_id=user.id,
            destinatario_usuario_id=dest_id,
            corpo=dados.corpo.strip(),
            agenda_manual_id=evento.id,
            fazenda_id=fazenda_id,
        )
        session.add(tarefa)
        criadas.append(tarefa)
    session.commit()
    return {"criadas": len(criadas)}


# ---------------------------------------------------------------------------
# Exportar (admin only) — carrinho de exportação de bancos completos por
# e-mail, funcionando como uma espécie de backup/migração. Cada item é uma
# tabela bruta (ficha do animal, reprodutivo, produção, estoque, aplicações,
# compra/venda de animal, lançamentos financeiros) ou um dos 3 relatórios
# financeiros indicadores já existentes (DRE, RMCA, custo por litro de leite)
# — os relatórios "Fluxo de caixa"/"Livro caixa"/"Extrato completo" do site
# são apenas visões sobre os mesmos lançamentos financeiros já cobertos pelo
# item "financeiro_lancamentos" (ContaGerencial), então não têm item próprio.
# Roda em segundo plano (BackgroundTasks) — a resposta ao clique é imediata,
# o e-mail com o ZIP chega depois, sem travar a tela do administrador.
# ---------------------------------------------------------------------------
EXPORT_CATALOG: dict[str, dict] = {
    "animal_ficha": {"label": "Ficha completa do animal", "model": Animal, "campo_data": None},
    "reprodutivo_servicos": {"label": "Reprodutivo — Serviços/IA/diagnósticos", "model": Servico, "campo_data": "data_servico"},
    "reprodutivo_partos": {"label": "Reprodutivo — Partos", "model": Parto, "campo_data": "data_parto"},
    "producao_controle_leiteiro": {"label": "Produção — Controle leiteiro", "model": ControleLeiteiro, "campo_data": "data_controle"},
    "estoque_itens": {"label": "Estoque — Itens cadastrados", "model": Estoque, "campo_data": None},
    "estoque_movimentos": {"label": "Estoque — Movimentações", "model": MovimentoEstoque, "campo_data": "data_movimento"},
    "sanidade_aplicacoes": {"label": "Aplicações sanitárias", "model": Sanidade, "campo_data": "data_aplicacao"},
    "compra_animal": {"label": "Compra de animais", "model": CompraAnimal, "campo_data": "data_compra"},
    "venda_animal": {"label": "Venda de animais", "model": VendaAnimal, "campo_data": "data_venda"},
    "financeiro_lancamentos": {"label": "Financeiro — todos os lançamentos (livro caixa/extrato/fluxo de caixa)", "model": ContaGerencial, "campo_data": "data_competencia"},
}


def _linhas_para_csv(linhas: list[dict]) -> str:
    if not linhas:
        return ""
    colunas = list(linhas[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=colunas, extrasaction="ignore")
    writer.writeheader()
    for linha in linhas:
        writer.writerow({c: linha.get(c, "") for c in colunas})
    return buffer.getvalue()


def _executar_exportacao(itens: list[dict], destinatario_email: str, fazenda_id: int | None) -> None:
    with Session(engine) as session:
        buffer_zip = io.BytesIO()
        with zipfile.ZipFile(buffer_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for item in itens:
                chave = item["chave"]
                if chave in EXPORT_CATALOG:
                    cfg = EXPORT_CATALOG[chave]
                    query = select(cfg["model"])
                    if cfg["campo_data"] and item.get("data_inicio") and item.get("data_fim"):
                        coluna = getattr(cfg["model"], cfg["campo_data"])
                        query = query.where(coluna >= item["data_inicio"], coluna <= item["data_fim"])
                    # BUG DE SEGURANÇA CORRIGIDO: nenhuma das 10 tabelas do
                    # catálogo era filtrada por fazenda_id — qualquer admin
                    # de qualquer fazenda-cliente exportava o banco inteiro
                    # (animais, produção, sanidade, compras/vendas,
                    # financeiro) de TODOS os outros clientes da plataforma.
                    #
                    # O filtro é INCONDICIONAL de propósito. O padrão tolerante
                    # (`if fazenda_id is not None: ...where(...)`) é o que criou
                    # o furo em primeiro lugar: com fazenda_id None ele não
                    # restringe, ele DESLIGA o isolamento — e aqui isso vira um
                    # ZIP com o banco de todos os clientes saindo por e-mail.
                    # Com fazenda_id None (ambiente sem multi-fazenda
                    # provisionado, ver `_fazenda_obrigatoria`) isto vira
                    # `fazenda_id IS NULL`, que é exatamente o conjunto de
                    # linhas desse ambiente — nunca as de outro tenant.
                    query = query.where(cfg["model"].fazenda_id == fazenda_id)
                    linhas = [row.model_dump(mode="json") for row in session.exec(query).all()]
                    zf.writestr(f"{chave}.csv", _linhas_para_csv(linhas).encode("utf-8-sig"))
                elif chave in RELATORIOS_DISPONIVEIS and item.get("data_inicio") and item.get("data_fim"):
                    from fazenda.api.routers.financeiro import custo_litro_leite, dre, rmca

                    # BUG DE SEGURANÇA CORRIGIDO: ver comentário equivalente
                    # em enviar_email_portal — sem fazenda_id explícito, estas
                    # chamadas diretas desligavam todo filtro por fazenda.
                    if chave == "dre":
                        resultado = dre(data_inicio=item["data_inicio"], data_fim=item["data_fim"], centro_custo=None, regime="competencia", session=session, fazenda_id=fazenda_id)
                    elif chave == "rmca":
                        resultado = rmca(data_inicio=item["data_inicio"], data_fim=item["data_fim"], session=session, fazenda_id=fazenda_id)
                    else:
                        resultado = custo_litro_leite(data_inicio=item["data_inicio"], data_fim=item["data_fim"], session=session, fazenda_id=fazenda_id)
                    zf.writestr(f"{chave}.csv", _dict_para_csv(resultado).encode("utf-8-sig"))

        enviar_email(
            destinatario_email,
            "Exportação de dados — Portal",
            "<p>Segue em anexo o arquivo ZIP com os dados exportados do sistema.</p>",
            "exportacao_portal.zip",
            buffer_zip.getvalue(),
        )


@router.get("/exportar/opcoes")
def opcoes_exportacao(user: Usuario = Depends(get_current_user)) -> list[dict]:
    if user.papel != "admin":
        raise HTTPException(403, "Só o administrador tem acesso à exportação")
    opcoes = [
        {"chave": chave, "rotulo": cfg["label"], "tem_periodo": cfg["campo_data"] is not None}
        for chave, cfg in EXPORT_CATALOG.items()
    ]
    opcoes += [
        {"chave": chave, "rotulo": rotulo, "tem_periodo": True}
        for chave, rotulo in RELATORIOS_DISPONIVEIS.items()
    ]
    return opcoes


class ItemExportacaoIn(BaseModel):
    chave: str
    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None


class ExportarIn(BaseModel):
    itens: list[ItemExportacaoIn]


@router.post("/exportar")
def solicitar_exportacao(
    dados: ExportarIn, background_tasks: BackgroundTasks, user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
    session: Session = Depends(get_session),
) -> dict:
    if user.papel != "admin":
        raise HTTPException(403, "Só o administrador tem acesso à exportação")
    if not user.email:
        raise HTTPException(400, "Cadastre um e-mail para o seu usuário antes de exportar")
    if not dados.itens:
        raise HTTPException(400, "Selecione ao menos um item para exportar")

    chaves_validas = set(EXPORT_CATALOG) | set(RELATORIOS_DISPONIVEIS)
    for item in dados.itens:
        if item.chave not in chaves_validas:
            raise HTTPException(400, f"Item inválido: {item.chave}")

    # A fazenda é resolvida (e exigida) AQUI, ainda dentro do request, e viaja
    # como argumento para a BackgroundTask — que roda depois da resposta, com
    # sessão própria e sem nenhum contexto de autenticação para consultar.
    fazenda_id = _fazenda_obrigatoria(session, fazenda_id)
    itens = [item.model_dump() for item in dados.itens]
    background_tasks.add_task(_executar_exportacao, itens, user.email, fazenda_id)
    return {"mensagem": f"Em breve o resultado será enviado para {user.email}."}
