"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, Clock, Loader2, PackageSearch } from "lucide-react";
import { fetchCotacaoPublica, responderCotacaoPublica, type CotacaoPublicaView, type RespostaCotacaoPublicaPayload } from "@/lib/api";
import { PublicPage } from "@/components/institucional/PublicShell";

const input: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem", fontSize: "0.95rem",
};
const label: React.CSSProperties = { fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.3rem" };

type FormItem = RespostaCotacaoPublicaPayload;

function Conteudo() {
  const params = useParams();
  const token = String(params.token || "");
  const [dados, setDados] = useState<CotacaoPublicaView | null>(null);
  const [form, setForm] = useState<Record<number, FormItem>>({});
  const [carregando, setCarregando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [enviado, setEnviado] = useState(false);

  useEffect(() => {
    if (!token) return;
    fetchCotacaoPublica(token).then((d) => {
      setDados(d);
      const inicial: Record<number, FormItem> = {};
      d.itens.forEach((i) => {
        inicial[i.id] = i.resposta ? {
          cotacao_item_id: i.id, recusado: i.resposta.recusado, preco_unitario: i.resposta.preco_unitario ?? undefined,
          frete_incluso: i.resposta.frete_incluso ?? undefined, valor_frete: i.resposta.valor_frete ?? undefined,
          prazo_entrega_dias: i.resposta.prazo_entrega_dias ?? undefined, condicao_pagamento: i.resposta.condicao_pagamento ?? undefined,
          observacao: i.resposta.observacao ?? undefined,
        } : { cotacao_item_id: i.id, frete_incluso: true };
      });
      setForm(inicial);
    }).catch((e) => setErro(e.message)).finally(() => setCarregando(false));
  }, [token]);

  function atualizar(itemId: number, patch: Partial<FormItem>) {
    setForm((prev) => ({ ...prev, [itemId]: { ...prev[itemId], cotacao_item_id: itemId, ...patch } }));
  }

  async function enviar() {
    if (!dados) return;
    setEnviando(true); setErro(null);
    try {
      await responderCotacaoPublica(token, Object.values(form));
      setEnviado(true);
    } catch (e: any) {
      setErro(e.message || "Não foi possível enviar sua resposta.");
    } finally {
      setEnviando(false);
    }
  }

  if (carregando) {
    return <section style={{ padding: "4.5rem 1.5rem", textAlign: "center" }}><Loader2 className="animate-spin" style={{ margin: "0 auto" }} /></section>;
  }
  if (!dados) {
    return (
      <section style={{ padding: "4.5rem 1.5rem", textAlign: "center" }}>
        <p style={{ color: "var(--red)" }}>{erro || "Link inválido ou expirado."}</p>
      </section>
    );
  }

  return (
    <section style={{ padding: "3rem 1.5rem", minHeight: "70vh", maxWidth: "42rem", margin: "0 auto" }}>
      <div className="card" style={{ marginBottom: "1rem" }}>
        <div style={{ fontSize: "0.72rem", letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)" }}>{dados.nome_fazenda}</div>
        <h1 style={{ fontSize: "1.3rem", fontWeight: 700, margin: "0.3em 0" }}>Cotação {dados.numero_cotacao}</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", display: "flex", alignItems: "center", gap: "0.4em" }}>
          <Clock size={14} /> Responda até {new Date(dados.prazo_resposta).toLocaleString("pt-BR")}
        </p>
      </div>

      {enviado ? (
        <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
          <CheckCircle2 size={40} style={{ color: "var(--green-light)", margin: "0 auto 0.6rem" }} />
          <h2 style={{ fontSize: "1.05rem", fontWeight: 700 }}>Resposta enviada</h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>
            Sua proposta foi registrada. Você pode reabrir este link a qualquer momento para corrigir, enquanto a cotação estiver aberta.
          </p>
        </div>
      ) : (
        <>
          {dados.itens.map((item) => {
            const f = form[item.id] || { cotacao_item_id: item.id };
            return (
              <div key={item.id} className="card" style={{ marginBottom: "1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5em", marginBottom: "0.6em" }}>
                  <PackageSearch size={16} style={{ color: "var(--dourado-light)" }} />
                  <div>
                    <div style={{ fontWeight: 700 }}>{item.produto}</div>
                    <div style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>{item.quantidade} {item.unidade}</div>
                  </div>
                </div>

                <label style={{ display: "flex", alignItems: "center", gap: "0.5em", fontSize: "0.85rem", marginBottom: "0.8em" }}>
                  <input type="checkbox" checked={!!f.recusado} onChange={(e) => atualizar(item.id, { recusado: e.target.checked })} />
                  Não atendo este item
                </label>

                {!f.recusado && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.7em" }}>
                    <div><label style={label}>Preço por unidade (R$)</label>
                      <input style={input} type="number" step="0.01" value={f.preco_unitario ?? ""} onChange={(e) => atualizar(item.id, { preco_unitario: e.target.value ? Number(e.target.value) : undefined })} /></div>
                    <div style={{ display: "flex", gap: "0.6em" }}>
                      <button type="button" onClick={() => atualizar(item.id, { frete_incluso: true, valor_frete: undefined })}
                        style={{ flex: 1, padding: "0.6em", borderRadius: "var(--r-sm)", border: `1.5px solid ${f.frete_incluso ? "var(--dourado)" : "var(--border)"}`, background: f.frete_incluso ? "var(--surface-2)" : "transparent", fontWeight: 600, fontSize: "0.85rem" }}>
                        Frete incluso
                      </button>
                      <button type="button" onClick={() => atualizar(item.id, { frete_incluso: false })}
                        style={{ flex: 1, padding: "0.6em", borderRadius: "var(--r-sm)", border: `1.5px solid ${!f.frete_incluso ? "var(--dourado)" : "var(--border)"}`, background: !f.frete_incluso ? "var(--surface-2)" : "transparent", fontWeight: 600, fontSize: "0.85rem" }}>
                        À parte
                      </button>
                    </div>
                    {!f.frete_incluso && (
                      <div><label style={label}>Valor do frete (R$)</label>
                        <input style={input} type="number" step="0.01" value={f.valor_frete ?? ""} onChange={(e) => atualizar(item.id, { valor_frete: e.target.value ? Number(e.target.value) : undefined })} /></div>
                    )}
                    <div><label style={label}>Prazo de entrega (dias)</label>
                      <input style={input} type="number" value={f.prazo_entrega_dias ?? ""} onChange={(e) => atualizar(item.id, { prazo_entrega_dias: e.target.value ? Number(e.target.value) : undefined })} /></div>
                    <div><label style={label}>Condição de pagamento</label>
                      <input style={input} value={f.condicao_pagamento ?? ""} placeholder="ex.: 30 dias" onChange={(e) => atualizar(item.id, { condicao_pagamento: e.target.value })} /></div>
                    <div><label style={label}>Observação (opcional)</label>
                      <input style={input} value={f.observacao ?? ""} onChange={(e) => atualizar(item.id, { observacao: e.target.value })} /></div>
                  </div>
                )}
              </div>
            );
          })}

          {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem" }}>{erro}</p>}
          <button className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={enviando} onClick={enviar}>
            {enviando ? <Loader2 size={16} className="animate-spin" /> : null} Enviar resposta
          </button>
        </>
      )}
    </section>
  );
}

export default function CotacaoPublicaPage() {
  return (
    <PublicPage variant="institucional">
      <Conteudo />
    </PublicPage>
  );
}
