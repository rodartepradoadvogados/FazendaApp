"""
Central de Documentos (Administração) — busca unificada, só leitura, sobre
os dois arquivos de documento que já existem no sistema:

  - `DocumentoArquivado` (fazenda/models/documentos.py, ver
    fazenda/api/routers/documentos.py) — arquivo fiscal-contábil da fazenda
    como um todo (nota fiscal avulsa, CCIR, IRPF/IRPJ, inscrição estadual,
    matrícula, contratos...). Acesso EXCLUSIVO de administrador da fazenda.
  - `LancamentoAnexo` (fazenda/models/financeiro.py, ver endpoints de anexo
    em fazenda/api/routers/financeiro.py) — documento anexado a um
    lançamento financeiro específico (fatura, boleto, ordem de serviço,
    comprovante, orçamento/pedido...). Acesso de quem tem o módulo
    financeiro (funcionário + fazenda com o módulo contratado).

Não cria tabela nova nem migra nada — só junta os dois num único endpoint
filtrável (categoria, período, número do documento), cada linha carimbada
com a "origem" (fiscal | financeiro) e, quando vier de um lançamento, o
número dele — é o que permite achar, por exemplo, "o boleto número X" sem
saber de antemão a qual lançamento ele pertence, ou ver de uma vez o pacote
inteiro (orçamento + pedido + nota fiscal + boleto + comprovante) que um
mesmo lançamento reuniu.

Isolamento multi-tenant: as duas consultas são SEMPRE filtradas por
fazenda_id (fazenda_id_seguro) — nunca devolve linha de outra fazenda. Um
usuário sem nenhum dos dois acessos recebe lista vazia, não 403 — a tela só
mostra "nada aqui" em vez de quebrar; o filtro de acesso é decidido aqui
dentro, nunca no frontend.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from fazenda.auth import fazenda_tem_modulo_contratado, get_current_user, get_fazenda_atual_id, tem_modulo
from fazenda.database import get_session
from fazenda.models import ContaGerencial, DocumentoArquivado, LancamentoAnexo, Usuario
from fazenda.rules.auditoria import fazenda_id_seguro

router = APIRouter(prefix="/documentos-central", tags=["documentos-central"])


@router.get("")
def listar_central_documentos(
    categoria: str | None = None,
    numero_documento: str | None = None,
    data_de: date | None = None,
    data_ate: date | None = None,
    session: Session = Depends(get_session),
    user: Usuario = Depends(get_current_user),
    fazenda_id: int | None = Depends(get_fazenda_atual_id),
) -> list[dict]:
    fazenda_id = fazenda_id_seguro(fazenda_id)
    linhas: list[dict] = []

    # Tier fiscal — só administrador da fazenda. `DocumentoArquivado` não tem
    # um campo "número do documento" próprio (nasceu pra CCIR/IRPF/matrícula,
    # onde isso não se aplica igual) — a busca por número aqui cai no nome do
    # arquivo e no número de lançamento vinculado (quando "inserir no
    # balanço" foi marcado no upload).
    if user.papel == "admin":
        query = select(DocumentoArquivado)
        if fazenda_id is not None:
            query = query.where(DocumentoArquivado.fazenda_id == fazenda_id)
        if categoria:
            query = query.where(DocumentoArquivado.categoria == categoria)
        if data_de:
            query = query.where(DocumentoArquivado.data_documento >= data_de)
        if data_ate:
            query = query.where(DocumentoArquivado.data_documento <= data_ate)
        alvo = (numero_documento or "").strip().lower()
        for d in session.exec(query).all():
            if alvo and alvo not in (d.numero_lancamento or "").lower() and alvo not in d.nome_original.lower():
                continue
            linhas.append({
                "origem": "fiscal", "id": d.id, "categoria": d.categoria, "nome_arquivo": d.nome_original,
                "numero_documento": None,
                "data_documento": d.data_documento.isoformat() if d.data_documento else None,
                "criado_em": d.data_upload.isoformat(), "numero_lancamento": d.numero_lancamento,
                "fornecedor_cliente": None, "descricao": d.descricao,
                "url": f"/documentos/{d.id}/download",
            })

    # Tier financeiro — quem tem o módulo (permissão do funcionário + módulo
    # contratado pela fazenda), igual ao gate do resto do Financeiro.
    if tem_modulo(user, "financeiro") and fazenda_tem_modulo_contratado(session, fazenda_id, "financeiro"):
        query = select(LancamentoAnexo)
        if fazenda_id is not None:
            query = query.where(LancamentoAnexo.fazenda_id == fazenda_id)
        if categoria:
            query = query.where(LancamentoAnexo.categoria == categoria)
        if numero_documento:
            query = query.where(LancamentoAnexo.numero_documento.ilike(f"%{numero_documento}%"))
        if data_de:
            query = query.where(LancamentoAnexo.data_documento >= data_de)
        if data_ate:
            query = query.where(LancamentoAnexo.data_documento <= data_ate)
        anexos = session.exec(query).all()

        # Contexto (fornecedor/descrição) do lançamento de cada anexo — busca
        # em lote pelos números distintos, não uma query por anexo.
        numeros = {a.numero_lancamento for a in anexos}
        contas_por_numero: dict[str, ContaGerencial] = {}
        if numeros:
            q_contas = select(ContaGerencial).where(ContaGerencial.numero_lancamento.in_(numeros))
            if fazenda_id is not None:
                q_contas = q_contas.where(ContaGerencial.fazenda_id == fazenda_id)
            for c in session.exec(q_contas).all():
                contas_por_numero.setdefault(c.numero_lancamento, c)

        for a in anexos:
            conta = contas_por_numero.get(a.numero_lancamento)
            linhas.append({
                "origem": "financeiro", "id": a.id, "categoria": a.categoria, "nome_arquivo": a.nome_arquivo,
                "numero_documento": a.numero_documento,
                "data_documento": a.data_documento.isoformat() if a.data_documento else None,
                "criado_em": a.criado_em.isoformat(), "numero_lancamento": a.numero_lancamento,
                "fornecedor_cliente": conta.fornecedor_cliente if conta else None,
                "descricao": conta.descricao if conta else None,
                "url": f"/financeiro/anexos/{a.id}",
            })

    linhas.sort(key=lambda l: l["criado_em"], reverse=True)
    return linhas
