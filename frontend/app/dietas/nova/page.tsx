"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchLotes, logout } from "@/lib/api";
import { criarSimulacao } from "@/lib/dietas";

type LoteOpcao = { codigo: string; nome?: string | null };

export default function NovaSimulacaoPage() {
  const router = useRouter();
  const [nome, setNome] = useState("");
  const [lote, setLote] = useState("");
  const [lotes, setLotes] = useState<LoteOpcao[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    fetchLotes()
      .then((ls: LoteOpcao[]) => setLotes(ls.filter((l) => /^\d\d/.test(l.codigo))))
      .catch(() => {});
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!nome.trim()) { setErro("Informe um nome para a simulação."); return; }
    setSalvando(true);
    setErro(null);
    try {
      const sim = await criarSimulacao({ nome: nome.trim(), lote: lote ? Number(lote) : null });
      router.push(`/dietas/${sim.id}`);
    } catch (e: any) {
      setErro(e.message);
      setSalvando(false);
    }
  }

  return (
    <div style={{ maxWidth: "34rem", margin: "0 auto" }}>
      <h1 style={{ margin: "0 0 0.2rem", fontSize: "1.3rem", fontWeight: 800, color: "var(--text)" }}>Nova simulação</h1>
      <p style={{ margin: "0 0 1.2rem", fontSize: "0.85rem", color: "var(--text-muted)" }}>
        Dê um nome à simulação e, se já souber, escolha o lote — os dados do lote pré-preenchem a Etapa 2.
      </p>

      <form onSubmit={onSubmit} className="card" style={{ display: "flex", flexDirection: "column", gap: "0.9rem" }}>
        <div>
          <label style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Nome da simulação *</label>
          <input
            autoFocus value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Ex.: Lote 03 — ajuste de outubro"
            style={{ width: "100%", padding: "0.5rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.9rem" }}
          />
        </div>
        <div>
          <label style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>Lote (opcional)</label>
          <select
            value={lote} onChange={(e) => setLote(e.target.value)}
            style={{ width: "100%", padding: "0.5rem 0.7rem", borderRadius: "var(--r-sm)", border: "1px solid var(--border)", background: "var(--surface)", color: "var(--text)", fontSize: "0.9rem" }}
          >
            <option value="">Sem lote definido</option>
            {lotes.map((l) => (
              <option key={l.codigo} value={Number(l.codigo.slice(0, 2))}>
                Lote {l.codigo}{l.nome ? ` — ${l.nome}` : ""}
              </option>
            ))}
          </select>
        </div>

        {erro && (
          <div className="alert-critico" style={{ flexDirection: "column", alignItems: "flex-start", gap: "0.5rem" }}>
            <span>{erro}</span>
            {/* Essa mensagem específica (backend: get_fazenda_atual_id sem "fid" no
                token) não tem nenhuma saída na própria tela — a fazenda vem do
                LOGIN, não de um seletor aqui dentro. O jeito de resolver é sair e
                entrar de novo (o login pede pra escolher a fazenda explicitamente
                quando há mais de uma vinculada, ou auto-seleciona quando só há uma
                — ver POST /auth/login). Vale também abrir esta aba de novo depois,
                nunca reaproveitar uma já aberta antes do login novo. */}
            {erro.includes("Selecione a fazenda") && (
              <button type="button" className="btn-primary-gold" onClick={() => logout()}>
                Sair e entrar de novo
              </button>
            )}
          </div>
        )}

        <div style={{ display: "flex", gap: "0.6rem", justifyContent: "flex-end" }}>
          <button type="button" className="btn-ghost" onClick={() => router.push("/dietas")}>Cancelar</button>
          <button type="submit" className="btn-primary-gold" disabled={salvando}>
            {salvando ? "Criando…" : "Criar e continuar"}
          </button>
        </div>
      </form>
    </div>
  );
}
