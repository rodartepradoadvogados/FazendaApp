"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { CheckCircle2, Loader2, Truck } from "lucide-react";
import { fetchPedidoConfirmacaoPublica, confirmarPedidoPublico, formatBRL, type PedidoConfirmacaoPublicaView } from "@/lib/api";
import { PublicPage } from "@/components/institucional/PublicShell";

const input: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem", fontSize: "0.95rem",
};
const label: React.CSSProperties = { fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.3rem" };

function DadosFaturamento({ fazenda }: { fazenda: NonNullable<PedidoConfirmacaoPublicaView["fazenda"]> }) {
  const doc = fazenda.tipo_documento === "cnpj" ? "CNPJ" : "CPF";
  return (
    <div className="card" style={{ marginBottom: "1rem", fontSize: "0.85rem" }}>
      <div style={{ fontSize: "0.68rem", fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--text-muted)", marginBottom: "0.5em" }}>
        Faturar para
      </div>
      <div style={{ fontWeight: 700 }}>{fazenda.nome}</div>
      {fazenda.documento && <div style={{ color: "var(--text-muted)" }}>{doc}: {fazenda.documento}</div>}
      {fazenda.inscricao_estadual && <div style={{ color: "var(--text-muted)" }}>Inscrição estadual: {fazenda.inscricao_estadual}</div>}
      {fazenda.endereco && <div style={{ color: "var(--text-muted)" }}>{fazenda.endereco}</div>}
      {fazenda.telefone && <div style={{ color: "var(--text-muted)" }}>{fazenda.telefone}</div>}
      {fazenda.email && <div style={{ color: "var(--text-muted)" }}>{fazenda.email}</div>}
    </div>
  );
}

function Conteudo() {
  const params = useParams();
  const token = String(params.token || "");
  const [dados, setDados] = useState<PedidoConfirmacaoPublicaView | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [previsao, setPrevisao] = useState("");
  const [observacao, setObservacao] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    fetchPedidoConfirmacaoPublica(token).then(setDados).catch((e) => setErro(e.message)).finally(() => setCarregando(false));
  }, [token]);

  async function confirmar(recusado: boolean) {
    setEnviando(true); setErro(null);
    try {
      const r = await confirmarPedidoPublico(token, { previsao_entrega: previsao || null, observacao: observacao || null, recusado });
      setResultado(r.status);
    } catch (e: any) {
      setErro(e.message || "Não foi possível confirmar.");
    } finally {
      setEnviando(false);
    }
  }

  if (carregando) return <section style={{ padding: "4.5rem 1.5rem", textAlign: "center" }}><Loader2 className="animate-spin" style={{ margin: "0 auto" }} /></section>;
  if (!dados) return <section style={{ padding: "4.5rem 1.5rem", textAlign: "center" }}><p style={{ color: "var(--red)" }}>{erro || "Link inválido ou expirado."}</p></section>;

  const jaRespondido = resultado || dados.status !== "enviado";

  return (
    <section style={{ padding: "3rem 1.5rem", minHeight: "70vh", maxWidth: "38rem", margin: "0 auto" }}>
      <div className="card" style={{ marginBottom: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5em" }}>
          <Truck size={18} style={{ color: "var(--dourado-light)" }} />
          <h1 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>Confirmar pedido {dados.numero_pedido}</h1>
        </div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.4em" }}>
          Preço e itens já foram fechados na cotação — só peço a previsão de entrega.
        </p>
      </div>

      <div className="card" style={{ marginBottom: "1rem" }}>
        {dados.itens.map((i, idx) => (
          <div key={idx} style={{ display: "flex", justifyContent: "space-between", padding: "0.4em 0", borderBottom: idx < dados.itens.length - 1 ? "1px dashed var(--border)" : "none", fontSize: "0.88rem" }}>
            <span>{i.produto}{i.quantidade != null ? ` · ${i.quantidade}` : ""}</span>
            <span style={{ fontWeight: 600 }}>{formatBRL(i.valor_total_estimado)}</span>
          </div>
        ))}
      </div>

      {dados.fazenda && <DadosFaturamento fazenda={dados.fazenda} />}

      {jaRespondido ? (
        <div className="card" style={{ textAlign: "center", padding: "2rem" }}>
          <CheckCircle2 size={40} style={{ color: "var(--green-light)", margin: "0 auto 0.6rem" }} />
          <h2 style={{ fontSize: "1.05rem", fontWeight: 700 }}>
            {(resultado || dados.status) === "confirmado" ? "Pedido confirmado" : "Resposta registrada"}
          </h2>
          <p style={{ color: "var(--text-muted)", fontSize: "0.88rem" }}>
            {(resultado || dados.status) === "confirmado"
              ? "A fazenda foi avisada. A entrega será conferida por item no recebimento."
              : "A fazenda foi avisada da sua resposta."}
          </p>
        </div>
      ) : (
        <div className="card">
          <label style={label}>Previsão de entrega</label>
          <input style={{ ...input, marginBottom: "0.8em" }} placeholder="ex.: 4 dias úteis" value={previsao} onChange={(e) => setPrevisao(e.target.value)} />
          <label style={label}>Observação (opcional)</label>
          <input style={{ ...input, marginBottom: "1em" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} />
          {erro && <p style={{ color: "var(--red)", fontSize: "0.85rem", marginBottom: "0.6em" }}>{erro}</p>}
          <button className="btn-primary" style={{ width: "100%", justifyContent: "center", marginBottom: "0.6em" }} disabled={enviando} onClick={() => confirmar(false)}>
            {enviando ? <Loader2 size={16} className="animate-spin" /> : null} Confirmar pedido
          </button>
          <button className="btn-ghost" style={{ width: "100%", justifyContent: "center" }} disabled={enviando} onClick={() => confirmar(true)}>
            Não vou conseguir atender este pedido
          </button>
        </div>
      )}
    </section>
  );
}

export default function PedidoConfirmacaoPublicaPage() {
  return (
    <PublicPage variant="institucional">
      <Conteudo />
    </PublicPage>
  );
}
