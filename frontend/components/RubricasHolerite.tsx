"use client";
import { useEffect, useState } from "react";
import { Minus, Plus, Search, Trash2 } from "lucide-react";
import {
  atualizarRubricaFolha, criarRubricaFolha, excluirRubricaFolha, fetchCatalogoRubricas,
  fetchComprasParaDesconto, fetchRubricasFolha, formatBRL, formatDate,
  type CatalogoRubricas, type CompraDoDesconto, type RubricaCatalogoItem, type RubricaFolha,
} from "@/lib/api";
import { Modal } from "@/components/Modal";

/*
 * Acrescentar VENCIMENTO e DESCONTO ao holerite — o painel de edição que
 * fica logo abaixo do documento, em Contas > Holerites e recibos.
 *
 * POR QUE O PAINEL FICA FORA DO PAPEL. O documento acima continua sendo o
 * recibo: quatro colunas, sem botão nenhum entre os números. A edição mora
 * num painel próprio, que lista as mesmas linhas com o que o papel não pode
 * ter — o valor editável e o "remover". Misturar as duas coisas faria o
 * recibo impresso e a tela deixarem de ser a mesma leitura.
 *
 * O ENQUADRAMENTO NÃO É ESCOLHIDO AQUI. A tela manda o CÓDIGO da rubrica
 * (bonificação, aumento, gueltas, indenização, reembolso) e o servidor decide
 * a natureza (salarial × indenizatória) e as incidências de INSS/IRRF/FGTS —
 * ver backend/fazenda/rules/rubrica_folha.py. O que a tela faz é DIZER a
 * consequência antes do lançamento, para o dono não descobrir depois no valor
 * retido: cada opção carrega o fundamento legal e a frase de incidência.
 *
 * A CONSULTA DE CONTAS ABRE EM JANELA SOBREPOSTA (`Modal`, com a animação de
 * entrada/saída que o projeto já tem), não em navegação: escolher a compra
 * que vira desconto não pode custar sair do holerite e perder o contexto.
 */

const selStyle: React.CSSProperties = {
  fontSize: "0.82rem", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.4rem 0.6rem", width: "100%",
};
const rotuloStyle: React.CSSProperties = {
  fontSize: "0.64rem", fontWeight: 600, letterSpacing: "0.04em",
  textTransform: "uppercase", color: "var(--text-muted)",
};

/** A frase que declara o regime da rubrica escolhida — a mesma que vai virar
 *  a coluna Referência da linha, mostrada ANTES de lançar. */
function frasesDoVerbete(item: RubricaCatalogoItem): string {
  if (item.exige_compra !== undefined) return item.fundamento;
  const natureza = item.natureza === "salarial" ? "Natureza salarial" : "Natureza indenizatória";
  const tributos = item.incide_inss
    ? "entra nas bases de INSS, IRRF e FGTS"
    : "não entra nas bases de INSS, IRRF e FGTS";
  const incorpora = item.incorpora_base
    ? " · incorpora ao salário-base a partir da competência seguinte"
    : "";
  return `${natureza} · ${tributos}${incorpora} — ${item.fundamento}`;
}

/** Consulta detalhada de contas, dentro da janela sobreposta. */
function JanelaCompras({ onEscolher, onClose }: {
  onEscolher: (compra: CompraDoDesconto) => void; onClose: () => void;
}) {
  const [busca, setBusca] = useState("");
  const [compras, setCompras] = useState<CompraDoDesconto[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    // Espera de 300 ms: a lista recarrega enquanto se digita, e sem isso cada
    // tecla vira uma consulta ao servidor.
    const id = setTimeout(() => {
      fetchComprasParaDesconto(busca)
        .then((c) => { if (vivo) { setCompras(c); setErro(null); } })
        .catch((e) => { if (vivo) setErro(e.message); });
    }, 300);
    return () => { vivo = false; clearTimeout(id); };
  }, [busca]);

  return (
    <Modal title="Consulta de contas — escolha a compra a descontar" onClose={onClose} width="880px">
      <div className="flex items-center gap-2 mb-3">
        <Search size={14} style={{ color: "var(--text-muted)" }} />
        <input
          style={selStyle} autoFocus
          placeholder="Buscar por descrição, fornecedor, nota ou nº do lançamento…"
          value={busca} onChange={(e) => setBusca(e.target.value)}
        />
      </div>
      {erro && <div className="alert-critico mb-3"><span>Sem dados: {erro}.</span></div>}
      {!compras ? <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Carregando…</p> : (
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead>
              <tr>
                <th>Lançamento</th><th>Descrição</th><th>Fornecedor</th><th>Nota</th>
                <th>Vencimento</th><th style={{ textAlign: "right" }}>Valor</th><th>Situação</th>
              </tr>
            </thead>
            <tbody>
              {compras.map((c) => (
                <tr
                  key={c.conta_id} className="row-clickable" style={{ cursor: "pointer" }}
                  title="Descontar esta compra do holerite"
                  onClick={() => onEscolher(c)}
                >
                  <td style={{ fontSize: "0.78rem" }}>{c.numero_lancamento || "—"}</td>
                  <td style={{ fontSize: "0.78rem", fontWeight: 600 }}>{c.descricao || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{c.fornecedor_cliente || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{c.numero_nota || "—"}</td>
                  <td style={{ fontSize: "0.78rem" }}>{c.data_vencimento ? formatDate(c.data_vencimento) : "—"}</td>
                  <td style={{ textAlign: "right", fontSize: "0.82rem" }}>{formatBRL(c.valor_total)}</td>
                  <td style={{ fontSize: "0.78rem" }}>
                    {c.data_pagamento
                      ? <span style={{ color: "var(--green-light)" }}>Paga em {formatDate(c.data_pagamento)}</span>
                      : <span style={{ color: "var(--text-muted)" }}>Em aberto</span>}
                  </td>
                </tr>
              ))}
              {!compras.length && (
                <tr><td colSpan={7} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                  Nenhuma compra encontrada para esta busca.
                </td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
      <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.7rem" }}>
        O desconto guarda o vínculo com a parcela escolhida: a linha do recibo passa a citar o lançamento, o
        fornecedor e a nota, e o clique nela leva de volta a esta compra.
      </p>
    </Modal>
  );
}

function FormularioRubrica({ especie, opcoes, onSalvar, onCancelar, salvando }: {
  especie: "vencimento" | "desconto";
  opcoes: RubricaCatalogoItem[];
  onSalvar: (dados: { codigo: string; valor: number; descricao: string; conta: CompraDoDesconto | null }) => void;
  onCancelar: () => void;
  salvando: boolean;
}) {
  const [codigo, setCodigo] = useState(opcoes[0]?.codigo || "");
  const [valor, setValor] = useState("");
  const [descricao, setDescricao] = useState("");
  const [compra, setCompra] = useState<CompraDoDesconto | null>(null);
  const [janelaAberta, setJanelaAberta] = useState(false);

  const item = opcoes.find((o) => o.codigo === codigo);
  const exigeCompra = !!item?.exige_compra;
  const numero = Number(valor.replace(",", "."));
  const pronto = !!item && numero > 0 && (!exigeCompra || !!compra);

  return (
    <div style={{
      marginTop: "0.6rem", padding: "0.8rem 0.9rem", background: "var(--surface-2)",
      border: "1px solid var(--border)", borderRadius: "var(--r-sm)",
    }}>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label style={rotuloStyle}>{especie === "vencimento" ? "Vencimento" : "Desconto"}</label>
          <select style={selStyle} value={codigo} onChange={(e) => { setCodigo(e.target.value); setCompra(null); }}>
            {opcoes.map((o) => <option key={o.codigo} value={o.codigo}>{o.rotulo}</option>)}
          </select>
        </div>
        <div>
          <label style={rotuloStyle}>Valor (R$)</label>
          <input
            style={selStyle} inputMode="decimal" placeholder="0,00"
            value={valor} onChange={(e) => setValor(e.target.value)}
          />
        </div>
        <div>
          <label style={rotuloStyle}>Descrição (opcional)</label>
          <input
            style={selStyle} placeholder="ex.: colheita de julho"
            value={descricao} onChange={(e) => setDescricao(e.target.value)}
          />
        </div>
      </div>

      {item && (
        <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem", lineHeight: 1.5 }}>
          {frasesDoVerbete(item)}
        </p>
      )}

      {exigeCompra && (
        <div style={{ marginTop: "0.6rem" }}>
          <button className="btn-ghost" type="button" style={{ fontSize: "0.75rem" }} onClick={() => setJanelaAberta(true)}>
            <Search size={13} /> {compra ? "Trocar a compra" : "Escolher a compra…"}
          </button>
          {compra && (
            <span style={{ fontSize: "0.76rem", marginLeft: "0.6rem" }}>
              {[compra.numero_lancamento, compra.fornecedor_cliente, compra.numero_nota ? `nota ${compra.numero_nota}` : null]
                .filter(Boolean).join(" · ")} — {formatBRL(compra.valor_total)}
            </span>
          )}
        </div>
      )}

      <div className="flex items-center gap-2" style={{ marginTop: "0.7rem" }}>
        <button
          className="btn-primary" type="button" style={{ fontSize: "0.78rem" }}
          disabled={!pronto || salvando}
          title={exigeCompra && !compra ? "Escolha a compra que está sendo descontada" : undefined}
          onClick={() => onSalvar({ codigo, valor: numero, descricao, conta: compra })}
        >
          Acrescentar
        </button>
        <button className="btn-ghost" type="button" style={{ fontSize: "0.78rem" }} onClick={onCancelar}>
          Cancelar
        </button>
      </div>

      {janelaAberta && (
        <JanelaCompras
          onClose={() => setJanelaAberta(false)}
          onEscolher={(c) => { setCompra(c); setJanelaAberta(false); }}
        />
      )}
    </div>
  );
}

export function RubricasHolerite({ folhaId, bloqueio, onMudou }: {
  folhaId: number;
  /** Frase que explica por que não dá para editar (folha paga, recibo
   *  congelado) — quando presente, o painel só LISTA. Dizer o motivo é
   *  melhor que sumir com os botões sem explicação. */
  bloqueio?: string | null;
  onMudou?: () => void;
}) {
  const [catalogo, setCatalogo] = useState<CatalogoRubricas | null>(null);
  const [rubricas, setRubricas] = useState<RubricaFolha[] | null>(null);
  const [abrindo, setAbrindo] = useState<"vencimento" | "desconto" | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [editando, setEditando] = useState<{ id: number; valor: string } | null>(null);

  useEffect(() => { fetchCatalogoRubricas().then(setCatalogo).catch(() => {}); }, []);
  // Nada de zerar a lista aqui dentro (setState síncrono em efeito faz
  // renderização em cascata): quem troca de documento remonta este painel
  // por `key={folhaId}` no Holerite — assim o estado nasce limpo, sem um
  // quadro em que as rubricas de uma pessoa aparecem sob o nome de outra.
  useEffect(() => {
    let vivo = true;
    fetchRubricasFolha(folhaId)
      .then((r) => { if (vivo) setRubricas(r); })
      .catch((e) => { if (vivo) setErro(e.message); });
    return () => { vivo = false; };
  }, [folhaId]);

  async function recarregar() {
    setRubricas(await fetchRubricasFolha(folhaId));
    // O documento inteiro é remontado no servidor (líquido, bases, retenções
    // e as linhas): quem pediu a mudança recarrega o ledger em vez de a tela
    // tentar recalcular por conta própria — foi assim que as duas telas de
    // folha divergiram antes.
    onMudou?.();
  }

  async function acrescentar(
    especie: "vencimento" | "desconto",
    dados: { codigo: string; valor: number; descricao: string; conta: CompraDoDesconto | null },
  ) {
    setSalvando(true);
    setErro(null);
    try {
      await criarRubricaFolha(folhaId, {
        especie, codigo: dados.codigo, valor: dados.valor,
        descricao: dados.descricao || null,
        conta_gerencial_id: dados.conta ? dados.conta.conta_id : null,
      });
      setAbrindo(null);
      await recarregar();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setSalvando(false);
    }
  }

  async function salvarValor(rubrica: RubricaFolha, texto: string) {
    const numero = Number(texto.replace(",", "."));
    setEditando(null);
    if (!(numero > 0) || numero === rubrica.valor) return;
    setSalvando(true);
    setErro(null);
    try {
      await atualizarRubricaFolha(rubrica.id, { valor: numero, descricao: rubrica.descricao });
      await recarregar();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setSalvando(false);
    }
  }

  async function remover(rubrica: RubricaFolha) {
    setSalvando(true);
    setErro(null);
    try {
      await excluirRubricaFolha(rubrica.id);
      await recarregar();
    } catch (e) {
      setErro((e as Error).message);
    } finally {
      setSalvando(false);
    }
  }

  const editavel = !bloqueio;

  return (
    <div className="card" style={{ marginTop: "0.8rem" }}>
      <div className="card-header mb-2">Vencimentos e descontos acrescentados</div>

      {erro && <div className="alert-critico mb-3"><span>{erro}</span></div>}

      {!rubricas ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>Carregando…</p>
      ) : rubricas.length === 0 ? (
        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem" }}>
          Nada acrescentado a este holerite — só o salário, as retenções e os vales.
        </p>
      ) : (
        <div>
          {rubricas.map((r) => (
            <div
              key={r.id}
              className="flex items-center gap-2"
              style={{ padding: "0.45rem 0", borderBottom: "1px dotted var(--border)", flexWrap: "wrap" }}
            >
              <span style={{
                display: "inline-flex", alignItems: "center", gap: "0.2rem", fontSize: "0.66rem",
                fontWeight: 700, padding: "0.05rem 0.35rem", borderRadius: "var(--r-sm)",
                background: r.especie === "vencimento"
                  ? "color-mix(in srgb, var(--green) 16%, transparent)"
                  : "color-mix(in srgb, var(--red) 12%, transparent)",
                color: r.especie === "vencimento" ? "var(--green-light)" : "var(--red)",
              }}>
                {r.especie === "vencimento" ? <Plus size={10} /> : <Minus size={10} />}
                {r.especie === "vencimento" ? "Vencimento" : "Desconto"}
              </span>
              <span style={{ fontSize: "0.82rem", fontWeight: 600 }}>{r.rotulo}</span>
              <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", flexBasis: "100%" }}>
                {r.referencia}
              </span>
              <span style={{ flexGrow: 1 }} />
              {editando?.id === r.id ? (
                <input
                  style={{ ...selStyle, width: "7rem", textAlign: "right" }} autoFocus inputMode="decimal"
                  value={editando.valor}
                  onChange={(e) => setEditando({ id: r.id, valor: e.target.value })}
                  onBlur={(e) => salvarValor(r, e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); }}
                />
              ) : (
                <span
                  className={editavel ? "row-clickable" : undefined}
                  title={editavel ? "Clique para corrigir o valor" : undefined}
                  onClick={editavel ? () => setEditando({ id: r.id, valor: String(r.valor).replace(".", ",") }) : undefined}
                  style={{
                    fontSize: "0.85rem", fontWeight: 700, fontVariantNumeric: "tabular-nums",
                    cursor: editavel ? "pointer" : undefined, padding: "0.1rem 0.3rem",
                    color: r.especie === "vencimento" ? undefined : "var(--red)",
                  }}
                >
                  {formatBRL(r.valor)}
                </span>
              )}
              {editavel && (
                <button
                  className="btn-ghost" type="button" style={{ fontSize: "0.72rem" }}
                  disabled={salvando} title={`Remover ${r.rotulo} deste holerite`}
                  onClick={() => remover(r)}
                >
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {bloqueio ? (
        <p style={{ fontSize: "0.74rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>{bloqueio}</p>
      ) : (
        <>
          <div className="flex items-center gap-2" style={{ marginTop: "0.7rem", flexWrap: "wrap" }}>
            <button
              className="btn-ghost" type="button" style={{ fontSize: "0.78rem" }}
              onClick={() => setAbrindo(abrindo === "vencimento" ? null : "vencimento")}
            >
              <Plus size={13} /> Acrescentar vencimento
            </button>
            <button
              className="btn-ghost" type="button" style={{ fontSize: "0.78rem" }}
              onClick={() => setAbrindo(abrindo === "desconto" ? null : "desconto")}
            >
              <Minus size={13} /> Acrescentar desconto
            </button>
          </div>
          {abrindo && catalogo && (
            <FormularioRubrica
              especie={abrindo}
              opcoes={abrindo === "vencimento" ? catalogo.vencimentos : catalogo.descontos}
              salvando={salvando}
              onCancelar={() => setAbrindo(null)}
              onSalvar={(dados) => acrescentar(abrindo, dados)}
            />
          )}
        </>
      )}
    </div>
  );
}
