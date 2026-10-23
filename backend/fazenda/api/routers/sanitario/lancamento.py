"""
/sanitario — Lançamentos › Preventivo (simples/retroativo, "à moda antiga"),
lançamento a partir da ficha vazia e importação de planilha.

  - Caixa cadastrada OU "outro" (texto livre): "outro" SÓ REGISTRA no
    histórico (nunca oferece criar no catálogo — §13).
  - Data no passado = retroativo; o motivo é pulável.
  - Planilha importada entra como SÓ REGISTRO: aparece no histórico, não conta
    para cobertura nem tira o animal da caixa; nunca apaga nada lançado.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlmodel import Session, select

from fazenda.api.routers.sanitario._comum import da_fazenda, exigir_fazenda, traduzir_erros
from fazenda.api.routers.sanitario.schemas import LancamentoSimplesIn
from fazenda.auth import get_current_user, get_fazenda_id_escrita
from fazenda.database import get_session
from fazenda.models import SanitarioCaixa, Usuario
from fazenda.parsers.utils import iter_planilha_rows, normalizar_cabecalho, parse_date, parse_float, valor_por_apelido
from fazenda.rules.sanitario import registro as regras_reg
from fazenda.rules.sanitario.definicao import normalizar
from fazenda.rules.sanitario.permissoes import eh_admin_fazenda

router = APIRouter(tags=["sanitario-lancamento"])

APELIDOS = {
    "numero": ["numero", "brinco", "animal", "n", "no", "numero animal", "vaca"],
    "data": ["data", "data aplicacao", "data da aplicacao", "dt"],
    "vacina": ["vacina", "exame", "o que", "produto", "vacina exame", "protocolo", "caixa"],
    "dose": ["dose", "dose ml", "quantidade"],
    "unidade": ["unidade", "un"],
    "aplicador": ["aplicador", "responsavel", "quem aplicou"],
    "resultado": ["resultado"],
    "obs": ["obs", "observacao"],
}
MODELO_COLUNAS = ["Brinco", "Data", "Vacina/exame", "Dose", "Unidade", "Aplicador", "Resultado", "Obs"]


@router.post("/lancamento-simples")
def lancamento_simples(dados: LancamentoSimplesIn, session: Session = Depends(get_session),
                       user: Usuario = Depends(get_current_user),
                       fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    if dados.caixa_id is None and not (dados.outro_texto or "").strip():
        raise HTTPException(status_code=400, detail="Escolha a vacina/exame ou escreva o que foi feito.")
    if dados.caixa_id is not None:
        da_fazenda(session, SanitarioCaixa, dados.caixa_id, fid, "Vacina/exame")
    if not dados.animal_ids and not dados.numeros:
        raise HTTPException(status_code=400, detail="Escolha ao menos um animal.")
    cons = {(c.animal_id, c.caixa_id): c for c in dados.consentimentos if c.aceito}
    base = {
        "caixa_id": dados.caixa_id, "outro_texto": (dados.outro_texto or "").strip() or None, "data": dados.data,
        "retroativo_motivo": dados.retroativo_motivo,
        "produto": dados.produto.model_dump(exclude_unset=True) if dados.produto else None,
        "aplicador_pessoa_id": dados.aplicador_pessoa_id, "aplicador_texto": dados.aplicador_texto,
        "veterinario_pessoa_id": dados.veterinario_pessoa_id, "veterinario_texto": dados.veterinario_texto,
        "crmv_texto": dados.crmv_texto,
        "atestado_numero": dados.atestado.numero if dados.atestado else None,
        "atestado_destinatario": dados.atestado.destinatario if dados.atestado else None,
        "carencia": dados.carencia.model_dump() if dados.carencia else None,
    }
    itens = []
    for aid in dict.fromkeys(dados.animal_ids):
        c = cons.get((aid, dados.caixa_id)) or cons.get((aid, None))
        itens.append({**base, "animal_id": aid, "peso_kg": dados.peso_kg.get(aid),
                      "resultado": dados.resultados.get(aid),
                      "consentimento": c.model_dump(exclude={"animal_id", "caixa_id"}) if c else None,
                      "chave_idempotencia": f"{dados.chave_lote}:{aid}" if dados.chave_lote else None})
    for numero in dict.fromkeys(n.strip() for n in dados.numeros if n.strip()):
        itens.append({**base, "numero_animal": numero,
                      "chave_idempotencia": f"{dados.chave_lote}:n{numero}" if dados.chave_lote else None})
    with traduzir_erros(session):
        res = regras_reg.registrar(session, fid, itens, origem=dados.origem, canal="site", usuario_id=user.id,
                                   eh_admin=eh_admin_fazenda(session, user, fid))
        session.commit()
    return res


@router.get("/importar-planilha/modelo")
def modelo_planilha() -> dict:
    return {"colunas": MODELO_COLUNAS,
            "exemplo": ["2401", "14/03/2026", "Brucelose B19", "2", "mL", "Zé", "", ""],
            "nota": "Entra como SÓ REGISTRO: aparece no histórico, não conta para cobertura nem tira o "
                    "animal da caixa. Nada lançado no CowData é apagado."}


@router.post("/importar-planilha")
async def importar_planilha(file: UploadFile, session: Session = Depends(get_session),
                            user: Usuario = Depends(get_current_user),
                            fazenda_id: int = Depends(get_fazenda_id_escrita)) -> dict:
    fid = exigir_fazenda(fazenda_id)
    content = await file.read()
    caixas = {normalizar(c.nome): c for c in session.exec(select(SanitarioCaixa).where(
        SanitarioCaixa.fazenda_id == fid, SanitarioCaixa.estado != "arquivada")).all()}
    caixas.update({normalizar(c.nome_curto): c for c in caixas.values() if c.nome_curto})
    itens, erros = [], []
    for n, row in enumerate(iter_planilha_rows(file.filename or "", content), start=2):
        r = {normalizar_cabecalho(k): (v or "") for k, v in row.items()}
        numero = valor_por_apelido(r, APELIDOS["numero"]).strip()
        try:
            data = parse_date(valor_por_apelido(r, APELIDOS["data"]))
        except Exception:
            data = None
        oque = valor_por_apelido(r, APELIDOS["vacina"]).strip()
        if not numero or data is None or not oque:
            erros.append(f"Linha {n}: precisa de brinco, data e vacina/exame.")
            continue
        cx = caixas.get(normalizar(oque))
        dose = parse_float(valor_por_apelido(r, APELIDOS["dose"]))
        resultado = normalizar(valor_por_apelido(r, APELIDOS["resultado"])) or None
        if resultado and resultado not in regras_reg.RESULTADOS:
            resultado = None
        itens.append({
            "numero_animal": numero, "data": data, "caixa_id": cx.id if cx else None,
            "outro_texto": None if cx else oque,
            "produto": {"modo": "sem_estoque", "texto": oque, "dose_valor": dose,
                        "dose_unidade": "mL" if dose is not None else None},
            "aplicador_texto": valor_por_apelido(r, APELIDOS["aplicador"]).strip() or None,
            "resultado": resultado,
            "chave_idempotencia": f"planilha:{normalizar(numero)}:{data.isoformat()}:{normalizar(oque)}",
        })
    with traduzir_erros(session):
        res = regras_reg.registrar(session, fid, itens, origem="importado", canal="importacao", usuario_id=user.id,
                                   eh_admin=False, so_registro=True)
        session.commit()
    return {**res, "erros_planilha": erros, "linhas": len(itens) + len(erros)}

