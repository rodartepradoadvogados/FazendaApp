"use client";
// Etapas 4 e 10 — aplica o resultado calculado como uma DietaLancamento real
// do lote (entra no fluxo de Alimentação já existente). Em caso de dieta
// ativa no lote, o backend devolve 409 na primeira tentativa; a UI mostra o
// alerta com o checkbox "encerrar a dieta ativa" e tenta de novo com
// encerrar_anterior:true — sem isso, a segunda chamada faria a mesma
// pergunta de novo para sempre.
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2 } from "lucide-react";
import { fetchLotes } from "@/lib/api";
import {
  AplicarDietaPayload, DietaAtivaConflitoError, Resultado, aplicarSimulacao, contextoFormulacao,
} from "@/lib/dietas";

type LoteOpcao = { codigo: string; nome?: string | null };

function hoje(): string {
  return new Date().toISOString().slice(0, 10);
}

export function AplicarNaDietaModal({
  simulacaoId, loteDefault, resultado, onFechar,
}: {
  simulacaoId: number; loteDefault: number | null; resultado: Resultado; onFechar: () => void;
}) {
  const [lotes, setLotes] = useState<LoteOpcao[]>([]);
  const [lote, setLote] = useState<number | null>(loteDefault);
  const [qtdAnimais, setQtdAnimais] = useState<number | null>(null);
  const [dataAbertura, setDataAbertura] = useState(hoje());
  const [base, setBase] = useState<"total" | "animal">("total");
  const [responsavel, setResponsavel] = useState("");
  const [dataPrevistaEncerramento, setDataPrevistaEncerramento] = useState("");
  const [encerrarAnterior, setEncerrarAnterior] = useState(false);
  const [conflito, setConflito] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<{ dieta_lancamento_id: number; itens_criados: number; qtd_animais: number } | null>(null);

  useEffect(() => { fetchLotes().then((ls: LoteOpcao[]) => setLotes(ls.filter((l) => /^\d\d/.test(l.codigo)))).catch(() => {}); }, []);
  useEffect(() => {
    if (lote == null) { setQtdAnimais(null); return; }
    contextoFormulacao(lote).then((ctx) => setQtdAnimais(ctx.qtd_animais)).catch(() => setQtdAnimais(null));
  }, [lote]);

  async function enviar(forcarEncerrar = false) {
    if (lote == null) { setErro("Escolha o lote."); return; }
    setEnviando(true);
    setErro(null);
    setConflito(null);
    const payload: AplicarDietaPayload = {
      lote, data_abertura: dataAbertura, base_quantidade: base,
      responsavel: responsavel.trim() || null, data_prevista_encerramento: dataPrevistaEncerramento || null,
      encerrar_anterior: forcarEncerrar || encerrarAnterior,
    };
    try {
      const r = await aplicarSimulacao(simulacaoId, payload);
      setSucesso(r);
    } catch (e) {
      if (e instanceof DietaAtivaConflitoError) {
        setConflito(e.message);
      } else {
        setErro((e as Error).message);
      }
    } finally {
      setEnviando(false);
    }
  }

  const qtd = qtdAnimais || 1;

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 70, display: "flex", alignItems: "center", justifyContent: "center", background: "var(--overlay)" }} onClick={onFechar}>
      <div onClick={(e) => e.stopPropagation()} className="card" style={{ width: "min(40rem, 94vw)", maxHeight: "88vh", overflowY: "auto" }}>
        {sucesso ? (
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: "var(--green)", marginBottom: "0.6rem" }}>
              <CheckCircle2 size={20} />
              <h3 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 700 }}>Dieta lançada no lote {lote}</h3>
            </div>
            <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
              {sucesso.itens_criados} ingrediente(s) lançados para {sucesso.qtd_animais} animal(is).
            </p>
            <div style={{ display: "flex", gap: "0.6rem", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button type="button" className="btn-ghost" onClick={onFechar}>Fechar</button>
              <a href="/alimentacao" className="btn-primary-gold" style={{ textDecoration: "none" }}>Ver em Alimentação</a>
            </div>
          </div>
        ) : (
          <>
            <h3 style={{ margin: "0 0 0.8rem", fontSize: "1.05rem", fontWeight: 700, color: "var(--text)" }}>Aplicar na dieta atual</h3>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.7rem" }}>
              <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                Lote *
                <select value={lote ?? ""} onChange={(e) => setLote(e.target.value ? Number(e.target.value) : null)}
                  style={{ width: "100%", marginTop: "0.2rem", padding: "0.42rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }}>
                  <option value="">Escolha o lote</option>
                  {lotes.map((l) => <option key={l.codigo} value={Number(l.codigo.slice(0, 2))}>Lote {l.codigo}{l.nome ? ` — ${l.nome}` : ""}</option>)}
                </select>
              </label>
              <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                Data de abertura *
                <input type="date" value={dataAbertura} onChange={(e) => setDataAbertura(e.target.value)}
                  style={{ width: "100%", marginTop: "0.2rem", padding: "0.42rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
              </label>
              <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                Base da quantidade
                <select value={base} onChange={(e) => setBase(e.target.value as "total" | "animal")}
                  style={{ width: "100%", marginTop: "0.2rem", padding: "0.42rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }}>
                  <option value="total">Total do lote/dia</option>
                  <option value="animal">Por cabeça/dia</option>
                </select>
              </label>
              <label style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
                Responsável
                <input value={responsavel} onChange={(e) => setResponsavel(e.target.value)}
                  style={{ width: "100%", marginTop: "0.2rem", padding: "0.42rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
              </label>
              <label style={{ fontSize: "0.76rem", color: "var(--text-muted)", gridColumn: "1 / -1" }}>
                Data prevista de encerramento
                <input type="date" value={dataPrevistaEncerramento} onChange={(e) => setDataPrevistaEncerramento(e.target.value)}
                  style={{ width: "100%", marginTop: "0.2rem", padding: "0.42rem 0.6rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.85rem" }} />
              </label>
            </div>

            <div style={{ marginTop: "1rem" }}>
              <h4 style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--gold-deep)", textTransform: "uppercase", letterSpacing: "0.05em", margin: "0 0 0.4rem" }}>
                Prévia — {qtdAnimais == null ? "escolha o lote para ver a quantidade de animais" : `${qtdAnimais} animal(is)`}
              </h4>
              <div className="card" style={{ padding: 0, maxHeight: "14rem", overflow: "auto" }}>
                <table className="fazenda-table">
                  <thead><tr><th>Ingrediente</th><th>kg MN/dia</th></tr></thead>
                  <tbody>
                    {resultado.ingredientes.map((ing) => (
                      <tr key={ing.nome}>
                        <td>{ing.nome}</td>
                        <td>{(base === "total" ? ing.kg_materia_natural_dia * qtd : ing.kg_materia_natural_dia).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {conflito && (
              <div className="alert-critico" style={{ marginTop: "0.9rem", flexDirection: "column", alignItems: "flex-start", gap: "0.5rem" }}>
                <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}><AlertTriangle size={15} /> {conflito}</span>
                <label style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", color: "var(--text)" }}>
                  <input type="checkbox" checked={encerrarAnterior} onChange={(e) => setEncerrarAnterior(e.target.checked)} />
                  Encerrar a dieta ativa nesta data
                </label>
              </div>
            )}
            {erro && <div className="alert-critico" style={{ marginTop: "0.9rem" }}>{erro}</div>}

            <div style={{ display: "flex", gap: "0.6rem", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
              <button
                type="button" className="btn-primary-gold" disabled={enviando}
                onClick={() => enviar(conflito != null && encerrarAnterior)}
              >
                {enviando ? "Aplicando…" : conflito ? "Tentar novamente" : "Aplicar"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
