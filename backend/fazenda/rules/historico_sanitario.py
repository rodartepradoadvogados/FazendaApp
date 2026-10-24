"""
Histórico de tratamentos e vacinas — junção do curativo (`Sanidade`) com o
preventivo novo (`SanitarioRegistro`), para Menu › Sanidade › Histórico do app.

## Por que existe

A tela "Histórico" do app só mostrava o curativo (`Sanidade`, aplicação avulsa
e protocolo). As vacinas e os exames gravados pelo dia de vacinação (módulo
`sanitario_*`, 2026) moram em OUTRA tabela e não apareciam em lugar nenhum do
app — o funcionário que vacinou o lote de manhã não achava a vacina no
histórico à tarde. Decisão do dono (espec de Sanidade, out/2026): uma lista
só, com etiqueta Curativo / Preventivo.

Fica fora do "Preventivo" o `Sanidade.natureza="preventivo"` (BST e indução
de cio): é manejo com relatório próprio (Produção › BST), não vacina/exame —
a tela do app já o escondia antes desta mudança.

Tudo aqui é leitura e sempre escopado por `fazenda_id`.
"""
from __future__ import annotations

from datetime import date
from typing import Iterable

from sqlmodel import Session, select

from fazenda.models import (
    Animal, Doenca, Estoque, Pessoa, ProtocoloSanitario, ProtocoloSanitarioLancamento, SanitarioCaixa,
    SanitarioRegistro,
)
from fazenda.rules.auditoria import mapa_usuarios

TIPO_CURATIVO = "curativo"
TIPO_PREVENTIVO = "preventivo"
TIPOS_HISTORICO = ("todos", TIPO_CURATIVO, TIPO_PREVENTIVO)

# Rótulo da "categoria" da linha preventiva, pelo tipo da caixa.
CATEGORIA_CAIXA = {"vacina": "Vacina", "exame": "Exame", "vermifugo": "Vermífugo", "outro": "Outro"}
RESULTADO_EXAME = {"positivo": "Positivo", "negativo": "Negativo", "inconclusivo": "Inconclusivo",
                   "nao_lido": "Não lido"}


def _br(d: date | None) -> str:
    return d.strftime("%d/%m/%Y") if d else ""


def doencas_dos_curativos(session: Session, fazenda_id: int | None, lancamento_ids: Iterable[int]) -> dict[int, tuple[int, str]]:
    """{protocolo_sanitario_lancamento_id: (doenca_id, nome)} — a doença do
    curativo vem do PROTOCOLO aplicado (a aplicação avulsa não guarda doença;
    nesse caso a linha fica sem doença e só entra no filtro "todas")."""
    ids = {i for i in lancamento_ids if i}
    if not ids:
        return {}
    q = select(ProtocoloSanitarioLancamento).where(ProtocoloSanitarioLancamento.id.in_(ids))
    if fazenda_id is not None:
        q = q.where(ProtocoloSanitarioLancamento.fazenda_id == fazenda_id)
    lancs = session.exec(q).all()
    protos = {p.id: p for p in session.exec(select(ProtocoloSanitario).where(
        ProtocoloSanitario.id.in_({l.protocolo_id for l in lancs} or {-1}))).all()}
    doencas = {d.id: d for d in session.exec(select(Doenca).where(
        Doenca.id.in_({p.doenca_id for p in protos.values() if p.doenca_id} or {-1}))).all()}
    saida: dict[int, tuple[int, str]] = {}
    for l in lancs:
        p = protos.get(l.protocolo_id)
        d = doencas.get(p.doenca_id) if p and p.doenca_id else None
        if d is not None:
            saida[l.id] = (d.id, d.nome)
    return saida


def _carencia_registro(r: SanitarioRegistro) -> dict | None:
    """Carência gravada no registro preventivo (datas de liberação, não dias).
    Sem nenhuma das duas datas: None — a tela não inventa "não informada" para
    vacina (a maioria não tem carência)."""
    if r.carencia_leite_ate is None and r.carencia_carne_ate is None:
        return None
    partes = []
    if r.carencia_leite_ate is not None:
        partes.append(f"leite até {_br(r.carencia_leite_ate)}")
    if r.carencia_carne_ate is not None:
        partes.append(f"carne até {_br(r.carencia_carne_ate)}")
    return {
        "leite_dias": (r.carencia_leite_ate - r.data).days if r.carencia_leite_ate else None,
        "carne_dias": (r.carencia_carne_ate - r.data).days if r.carencia_carne_ate else None,
        "proibido_lactacao": False,
        "texto": "Carência: " + " / ".join(partes),
        "liberacao_leite": r.carencia_leite_ate.isoformat() if r.carencia_leite_ate else None,
        "liberacao_carne": r.carencia_carne_ate.isoformat() if r.carencia_carne_ate else None,
    }


def linhas_preventivo(
    session: Session, fazenda_id: int, *, inicio: date | None, fim: date | None, numeros: list[str] | None,
) -> list[dict]:
    """Registros VÁLIDOS do preventivo (dia de vacinação, lançamento simples,
    ficha, importação) no MESMO formato das linhas de /sanidade/aplicacoes —
    mais `registro_id` e a etiqueta `tipo_historico="preventivo"`. Estornado
    não entra (é um registro desfeito, não uma aplicação)."""
    q = select(SanitarioRegistro).where(
        SanitarioRegistro.fazenda_id == fazenda_id, SanitarioRegistro.estado == "valido",
    )
    if inicio is not None:
        q = q.where(SanitarioRegistro.data >= inicio)
    if fim is not None:
        q = q.where(SanitarioRegistro.data <= fim)
    regs = session.exec(q).all()
    if not regs:
        return []
    animais = {a.id: a for a in session.exec(select(Animal).where(
        Animal.fazenda_id == fazenda_id, Animal.id.in_({r.animal_id for r in regs if r.animal_id} or {-1}))).all()}
    caixas = {c.id: c for c in session.exec(select(SanitarioCaixa).where(
        SanitarioCaixa.fazenda_id == fazenda_id, SanitarioCaixa.id.in_({r.caixa_id for r in regs if r.caixa_id} or {-1}))).all()}
    estoques = {e.id: e for e in session.exec(select(Estoque).where(
        Estoque.fazenda_id == fazenda_id, Estoque.id.in_({r.estoque_id for r in regs if r.estoque_id} or {-1}))).all()}
    pessoas = {p.id: p for p in session.exec(select(Pessoa).where(
        Pessoa.fazenda_id == fazenda_id,
        Pessoa.id.in_({r.aplicador_pessoa_id for r in regs if r.aplicador_pessoa_id}
                      | {r.veterinario_pessoa_id for r in regs if r.veterinario_pessoa_id} or {-1}))).all()}
    nomes = mapa_usuarios(session, {r.criado_por_usuario_id for r in regs})
    filtro = set(numeros) if numeros else None

    saida = []
    for r in regs:
        a = animais.get(r.animal_id) if r.animal_id else None
        numero = a.numero if a else (r.numero_animal_texto or "")
        if filtro is not None and numero not in filtro:
            continue
        cx = caixas.get(r.caixa_id) if r.caixa_id else None
        nome_caixa = (cx.nome_curto or cx.nome) if cx else (r.outro_texto or "Outro")
        est = estoques.get(r.estoque_id) if r.estoque_id else None
        produto_txt = r.produto_texto or (est.nome if est else None)
        aplicador = (pessoas[r.aplicador_pessoa_id].nome if r.aplicador_pessoa_id in pessoas else None) or r.aplicador_texto
        vet = (pessoas[r.veterinario_pessoa_id].nome if r.veterinario_pessoa_id in pessoas else None) or r.veterinario_texto
        obs = []
        if r.resultado:
            obs.append(f"Resultado: {RESULTADO_EXAME.get(r.resultado, r.resultado)}")
        if vet and vet != aplicador:
            obs.append(f"Veterinário: {vet}{f' ({r.crmv_texto})' if r.crmv_texto else ''}")
        if r.retroativo_motivo:
            obs.append(f"Lançado depois: {r.retroativo_motivo}")
        saida.append({
            "id": r.id,
            "registro_id": r.id,
            "chave": f"p{r.id}",
            "tipo_historico": TIPO_PREVENTIVO,
            "numero": numero,
            "animal_ativo": bool(a.ativo) if a else None,
            "produto": nome_caixa if not produto_txt else f"{nome_caixa} — {produto_txt}",
            "caixa": nome_caixa,
            "categoria": CATEGORIA_CAIXA.get(cx.tipo, "Outro") if cx else "Outro",
            "dose": r.dose_valor,
            "unidade": r.dose_unidade,
            "via": None,
            "responsavel": aplicador,
            "obs": " · ".join(obs) or None,
            "natureza": TIPO_PREVENTIVO,
            "data": r.data.isoformat(),
            "ano": r.data.year,
            "mes": f"{r.data.year}-{r.data.month:02d}",
            "usuario_nome": nomes.get(r.criado_por_usuario_id),
            "carencia": _carencia_registro(r),
            "doenca_id": None,
            "doenca": None,
            "curada": None,
            "lote_gravado": None,
        })
    return saida
