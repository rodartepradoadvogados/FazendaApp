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
import io
import zipfile
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import get_current_user, get_fazenda_atual_id
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
# == "admin". "Vet/Zootec." é um tipo combinado à parte e fica de fora — só os
# tipos exatos abaixo (mais admin) contam.
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
    if fazenda_id is None:
        usuarios = session.exec(select(Usuario).where(Usuario.ativo == True)).all()  # noqa: E712
    else:
        usuarios = session.exec(
            select(Usuario)
            .join(UsuarioFazenda, UsuarioFazenda.usuario_id == Usuario.id)
            .where(Usuario.ativo == True, UsuarioFazenda.fazenda_id == fazenda_id)  # noqa: E712
            .distinct()
        ).all()
    return [
        {"id": u.id, "nome": u.nome or u.username, "username": u.username}
        for u in usuarios
        if u.username != "robo-milknews"
    ]


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

    criadas = []
    for dest_id in dados.destinatarios_usuario_id:
        if not session.get(Usuario, dest_id):
            raise HTTPException(404, f"Usuário {dest_id} não encontrado")
        m = PortalMensagem(
            tipo="mensagem",
            remetente_usuario_id=user.id,
            destinatario_usuario_id=dest_id,
            aba=dados.aba,
            corpo=dados.corpo.strip(),
            pede_retorno=dados.pede_retorno,
            fazenda_id=fazenda_id_seguro(fazenda_id),
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
def enviar_email_portal(dados: EmailIn, user: Usuario = Depends(get_current_user), session: Session = Depends(get_session)) -> dict:
    if not dados.destinatarios_usuario_id:
        raise HTTPException(400, "Selecione ao menos um destinatário")
    if not dados.assunto.strip():
        raise HTTPException(400, "Assunto obrigatório")

    corpo_html = f"<p>{dados.corpo}</p>" if dados.corpo else "<p></p>"
    anexo_nome = None
    anexo_bytes = None

    if dados.relatorio:
        if dados.relatorio not in RELATORIOS_DISPONIVEIS:
            raise HTTPException(400, f"Relatório inválido: {dados.relatorio}")
        if not dados.data_inicio or not dados.data_fim:
            raise HTTPException(400, "Informe o período (de/até) do relatório")
        from fazenda.api.routers.financeiro import dre, rmca, custo_litro_leite

        if dados.relatorio == "dre":
            resultado = dre(data_inicio=dados.data_inicio, data_fim=dados.data_fim, centro_custo=None, regime="competencia", session=session)
        elif dados.relatorio == "rmca":
            resultado = rmca(data_inicio=dados.data_inicio, data_fim=dados.data_fim, session=session)
        else:
            resultado = custo_litro_leite(data_inicio=dados.data_inicio, data_fim=dados.data_fim, session=session)

        csv_texto = _dict_para_csv(resultado)
        anexo_nome = f"{dados.relatorio}_{dados.data_inicio.isoformat()}_{dados.data_fim.isoformat()}.csv"
        anexo_bytes = csv_texto.encode("utf-8-sig")
        corpo_html += f"<p>Relatório {RELATORIOS_DISPONIVEIS[dados.relatorio]} em anexo (período {dados.data_inicio.isoformat()} a {dados.data_fim.isoformat()}).</p>"

    enviados = 0
    for dest_id in dados.destinatarios_usuario_id:
        destinatario = session.get(Usuario, dest_id)
        if not destinatario:
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
    data_evento = dados.data_evento or date.today()
    criadas = []
    for dest_id in dados.destinatarios_usuario_id:
        destinatario = session.get(Usuario, dest_id)
        if not destinatario:
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


def _executar_exportacao(itens: list[dict], destinatario_email: str) -> None:
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
                    linhas = [row.model_dump(mode="json") for row in session.exec(query).all()]
                    zf.writestr(f"{chave}.csv", _linhas_para_csv(linhas).encode("utf-8-sig"))
                elif chave in RELATORIOS_DISPONIVEIS and item.get("data_inicio") and item.get("data_fim"):
                    from fazenda.api.routers.financeiro import custo_litro_leite, dre, rmca

                    if chave == "dre":
                        resultado = dre(data_inicio=item["data_inicio"], data_fim=item["data_fim"], centro_custo=None, regime="competencia", session=session)
                    elif chave == "rmca":
                        resultado = rmca(data_inicio=item["data_inicio"], data_fim=item["data_fim"], session=session)
                    else:
                        resultado = custo_litro_leite(data_inicio=item["data_inicio"], data_fim=item["data_fim"], session=session)
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
def solicitar_exportacao(dados: ExportarIn, background_tasks: BackgroundTasks, user: Usuario = Depends(get_current_user)) -> dict:
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

    itens = [item.model_dump() for item in dados.itens]
    background_tasks.add_task(_executar_exportacao, itens, user.email)
    return {"mensagem": f"Em breve o resultado será enviado para {user.email}."}
