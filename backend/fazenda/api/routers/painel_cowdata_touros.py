"""
Painel CowData > Touros NAAB — MANUTENÇÃO do catálogo genético global de
touros (modelo `Touro`, ver fazenda/models/sanidade.py).

POR QUE ESTE ARQUIVO EXISTE (furo de segurança fechado, set/2026). O
catálogo de touros é GLOBAL: `Touro` não tem `fazenda_id`, é uma tabela só,
lida por todas as fazendas-cliente ao mesmo tempo. Mesmo assim as rotas de
escrita moravam em `cadastro/genetica.py`, montadas dentro do router de
fazenda e protegidas só por `exigir_admin` — o administrador de QUALQUER
fazenda-cliente podia reescrever ou apagar o catálogo que TODAS as outras
usavam. O `exigir_admin` de lá não era pouca proteção por acidente: ele
protege bem o dado de UMA fazenda, e o dado aqui não é de uma fazenda.

Mesmo furo, e pelo mesmo motivo, valia para `POST /importar/touros_naab`
(gated só por `exigir_modulo("upload")`): subir a planilha do fornecedor
reescreve o catálogo global inteiro por upsert. Ela também mudou de casa
para cá.

DECISÃO: as rotas de escrita foram REMOVIDAS do lado da fazenda, não
transformadas em 403. Uma rota que recusa continua montada, continua no
OpenAPI e volta a abrir sozinha se um dia alguém trocar a dependência dela
por engano; removida, a superfície simplesmente não existe mais e o
administrador de fazenda recebe 405/404 do próprio roteador. A leitura
continua exatamente onde estava (`GET /cadastro/touros`, em
`cadastro/genetica.py::router_touros_leitura`) — nenhuma tela de fazenda
perdeu consulta.

O QUE A FAZENDA CONTINUA PODENDO FAZER (palavras do dono): "consultar,
usar para prova genética simulada, estudo de touros, aplicar quando colocar
touro fora do estoque, selecionar para comprar... qualquer fazenda usa, mas
só se edita, exclui, cadastra, atualiza o banco de touros no painel
CowData". Tudo isso é leitura de `Touro` e não passa por aqui.

Permissão: LEITURA exige só a área "cadastros" do Painel CowData (o painel
inteiro é interno da CowData); ESCRITA exige a área MAIS a permissão
"editar touros NAAB" (`pode_editar_touros_naab`) do cadastro de equipe —
ver fazenda.auth.exigir_permissao_painel_cowdata. O dono-equivalente passa
em tudo, como em todo o painel.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session, select

from fazenda.auth import exigir_area_painel_cowdata, exigir_permissao_painel_cowdata
from fazenda.database import get_session
from fazenda.models import Touro, Usuario

router = APIRouter(prefix="/painel-cowdata/touros", tags=["painel-cowdata-touros"])

# Consulta: só a área do painel. Escrita: área + permissão de edição.
_dep_leitura = Depends(exigir_area_painel_cowdata("cadastros"))
_dep_edicao = Depends(exigir_permissao_painel_cowdata("cadastros", "pode_editar_touros_naab"))


class TouroIn(BaseModel):
    """Mesmo formato que a fazenda usava em POST/PUT /cadastro/touros — a
    tela é a mesma (components/CadastroTouros.tsx), só mudou de lado."""

    naab: str
    nome: str
    nome_completo: Optional[str] = None
    raca: Optional[str] = None
    central: Optional[str] = None
    leite_kg: Optional[float] = None
    gordura_kg: Optional[float] = None
    gordura_pct: Optional[float] = None
    proteina_kg: Optional[float] = None
    proteina_pct: Optional[float] = None
    tpi: Optional[float] = None
    nm_dolar: Optional[float] = None
    tipo_composto: Optional[float] = None
    ubere_composto: Optional[float] = None
    pernas_composto: Optional[float] = None
    ccs_score: Optional[float] = None
    fertilidade_filhas: Optional[float] = None
    facilidade_parto: Optional[float] = None
    fonte: Optional[str] = None
    rodada_prova: Optional[str] = None
    observacao: Optional[str] = None
    dados_extra: Optional[list[list[str]]] = None  # [[rótulo, valor], ...]


@router.get("")
def listar_touros_painel(session: Session = Depends(get_session), _: Usuario = _dep_leitura) -> list[dict]:
    """Mesma listagem de GET /cadastro/touros (ordenada por TPI e depois
    nome), só que servida sem fazenda selecionada — um membro da Equipe
    CowData nunca tem "fid" no token (ver fazenda.auth.
    exigir_fazenda_selecionada), então não conseguiria chamar a rota da
    fazenda nem para ler."""
    touros = session.exec(select(Touro)).all()
    touros.sort(key=lambda t: (-(t.tpi if t.tpi is not None else -1e9), (t.nome or t.naab)))
    return [t.model_dump() for t in touros]


@router.get("/campos-planilha")
def campos_planilha_touros_painel(_: Usuario = _dep_leitura) -> list[str]:
    """Rótulos originais das colunas do catálogo completo (Alta Genetics),
    para o cadastro manual oferecer "preencher com os campos da planilha"."""
    from fazenda.rules.touros import CURADOS_POR_CABECALHO

    return [cabecalho for _campo, cabecalho, _num in CURADOS_POR_CABECALHO if _campo != "naab"]


@router.post("")
def criar_touro_painel(dados: TouroIn, session: Session = Depends(get_session), _: Usuario = _dep_edicao) -> dict:
    """Cadastro manual de um touro. Só o código NAAB e o nome são
    obrigatórios — todo o resto (inclusive campos extras da planilha do
    fornecedor) é opcional."""
    naab = dados.naab.strip().upper()
    if not naab:
        raise HTTPException(status_code=400, detail="Informe o código NAAB")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do touro")
    if session.exec(select(Touro).where(Touro.naab == naab)).first():
        raise HTTPException(status_code=400, detail=f"Já existe um touro cadastrado com o NAAB {naab}")
    from fazenda.rules.naab import central_por_codigo_naab

    campos = dados.model_dump(exclude={"naab", "dados_extra"})
    touro = Touro(naab=naab, **campos)
    if not touro.central:
        touro.central = central_por_codigo_naab(naab)
    if dados.dados_extra:
        touro.dados_extra = json.dumps(dados.dados_extra, ensure_ascii=False)
    session.add(touro)
    session.commit()
    session.refresh(touro)
    return touro.model_dump()


@router.put("/{touro_id}")
def atualizar_touro_painel(
    touro_id: int, dados: TouroIn, session: Session = Depends(get_session), _: Usuario = _dep_edicao,
) -> dict:
    t = session.get(Touro, touro_id)
    if not t:
        raise HTTPException(status_code=404, detail="Touro não encontrado")
    naab = dados.naab.strip().upper()
    if not naab:
        raise HTTPException(status_code=400, detail="Informe o código NAAB")
    if not dados.nome.strip():
        raise HTTPException(status_code=400, detail="Informe o nome do touro")
    outro = session.exec(select(Touro).where(Touro.naab == naab)).first()
    if outro and outro.id != touro_id:
        raise HTTPException(status_code=400, detail=f"Já existe outro touro cadastrado com o NAAB {naab}")
    for campo, valor in dados.model_dump(exclude={"dados_extra"}).items():
        setattr(t, campo, valor)
    t.naab = naab
    if dados.dados_extra is not None:
        t.dados_extra = json.dumps(dados.dados_extra, ensure_ascii=False) if dados.dados_extra else None
    t.atualizado_em = datetime.utcnow()
    session.add(t)
    session.commit()
    session.refresh(t)
    return t.model_dump()


@router.delete("/{touro_id}")
def excluir_touro_painel(touro_id: int, session: Session = Depends(get_session), _: Usuario = _dep_edicao) -> dict:
    t = session.get(Touro, touro_id)
    if not t:
        raise HTTPException(status_code=404, detail="Touro não encontrado")
    session.delete(t)
    session.commit()
    return {"excluido": True}


@router.post("/recarregar-catalogo")
def recarregar_catalogo_touros_painel(session: Session = Depends(get_session), _: Usuario = _dep_edicao) -> dict:
    """Reimporta o catálogo NAAB completo empacotado no servidor (upsert por
    NAAB — nunca apaga touros existentes). Serve de botão de autoatendimento
    caso a carga automática na inicialização não tenha rodado por algum
    motivo (ex.: banco criado antes deste recurso existir)."""
    from fazenda.rules.touros import bootstrap_touros_naab

    antes = len(session.exec(select(Touro)).all())
    bootstrap_touros_naab(session, forcar=True)
    depois = len(session.exec(select(Touro)).all())
    return {"touros_antes": antes, "touros_depois": depois}


@router.post("/importar")
async def importar_touros_naab_painel(
    file: UploadFile,
    fonte: str = Form(""),
    rodada: str = Form(""),
    session: Session = Depends(get_session),
    _: Usuario = _dep_edicao,
) -> dict:
    """Catálogo genético de touros (provas do fornecedor / NAAB-CDCB).
    Aceita o Excel (.xlsx) ou CSV exportado do ABS BullSearch, Alta, Select
    Sires etc. Upsert por código NAAB; nunca apaga touros existentes.

    Era `POST /importar/touros_naab`, dentro do router de Importar dados da
    fazenda — a mesma escrita global protegida só por `exigir_modulo
    ("upload")`. Mudou de casa junto com o resto da manutenção do catálogo
    (ver docstring do módulo); o corpo da rota é o mesmo, linha por linha."""
    from fazenda.rules.touros import (
        eh_planilha_rica, importar_touros, importar_touros_planilha_rica, ler_planilha,
    )

    content = await file.read()
    nome = (file.filename or "").lower()
    try:
        if nome.endswith((".xlsx", ".xlsm")):
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            cabecalhos = next(wb.active.iter_rows(values_only=True), [])
            if eh_planilha_rica(list(cabecalhos)):
                resultado = importar_touros_planilha_rica(session, content, fonte.strip() or None, rodada.strip() or None)
                return {"categoria": "touros_naab", **resultado}
        linhas = ler_planilha(content, file.filename)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001 — arquivo ilegível vira erro amigável
        raise HTTPException(status_code=400, detail=f"Não consegui ler o arquivo: {e}")
    resultado = importar_touros(session, linhas, fonte.strip() or None, rodada.strip() or None)
    return {"categoria": "touros_naab", **resultado}
