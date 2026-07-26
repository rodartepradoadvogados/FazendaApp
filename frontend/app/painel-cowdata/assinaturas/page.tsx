"use client";
import { useEffect, useState } from "react";
import { ShieldCheck, Ban } from "lucide-react";
import {
  fetchFazendas, fetchContratoFazenda, aprovarContratoFazenda, suspenderContratoFazenda,
  type Fazenda, type ContratoFazenda,
} from "@/lib/api";

const COR = { cartao: "#0d1220", borda: "#1c2438", mudo: "#7c8aa8", dourado: "#e8c256", verde: "#3ecf8e", vermelho: "#e05c5c" };

const STATUS_LABEL: Record<string, { label: string; cor: string }> = {
  ativo: { label: "Ativo", cor: COR.verde },
  aguardando_aprovacao: { label: "Aguardando aprovação", cor: COR.dourado },
  suspenso: { label: "Suspenso", cor: COR.vermelho },
};

export default function AssinaturasCowData() {
  const [linhas, setLinhas] = useState<{ fazenda: Fazenda; contrato: ContratoFazenda }[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [processando, setProcessando] = useState<number | null>(null);

  function carregar() {
    fetchFazendas()
      .then(async (fazendas) => {
        const linhasCarregadas = await Promise.all(
          fazendas.map(async (fazenda) => ({ fazenda, contrato: await fetchContratoFazenda(fazenda.id) })),
        );
        setLinhas(linhasCarregadas);
      })
      .catch((e) => setErro(e.message));
  }
  useEffect(carregar, []);

  async function aprovar(fazendaId: number) {
    setProcessando(fazendaId); setErro(null);
    try { await aprovarContratoFazenda(fazendaId); carregar(); }
    catch (e: any) { setErro(e.message); } finally { setProcessando(null); }
  }
  async function suspender(fazendaId: number) {
    setProcessando(fazendaId); setErro(null);
    try { await suspenderContratoFazenda(fazendaId); carregar(); }
    catch (e: any) { setErro(e.message); } finally { setProcessando(null); }
  }

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Assinaturas</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Contrato e faturamento de cada fazenda-cliente. Edição de plano/módulos fica em Fazendas (clientes).
      </p>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "12px", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COR.borda}`, color: COR.mudo, textAlign: "left" }}>
              <th style={{ padding: "0.6rem 1rem" }}>Fazenda</th>
              <th style={{ padding: "0.6rem 1rem" }}>Plano</th>
              <th style={{ padding: "0.6rem 1rem" }}>Ciclo</th>
              <th style={{ padding: "0.6rem 1rem" }}>Valor/mês</th>
              <th style={{ padding: "0.6rem 1rem" }}>Status</th>
              <th style={{ padding: "0.6rem 1rem" }}></th>
            </tr>
          </thead>
          <tbody>
            {linhas === null && (
              <tr><td colSpan={6} style={{ padding: "1rem", color: COR.mudo }}>Carregando…</td></tr>
            )}
            {linhas?.length === 0 && (
              <tr><td colSpan={6} style={{ padding: "1rem", color: COR.mudo }}>Nenhuma fazenda cadastrada ainda.</td></tr>
            )}
            {linhas?.map(({ fazenda, contrato }) => {
              const st = STATUS_LABEL[contrato.status || "aguardando_aprovacao"] || { label: "Sem contrato", cor: COR.mudo };
              return (
                <tr key={fazenda.id} style={{ borderBottom: `1px solid ${COR.borda}` }}>
                  <td style={{ padding: "0.6rem 1rem" }}>{fazenda.nome}</td>
                  <td style={{ padding: "0.6rem 1rem", textTransform: "capitalize" }}>{contrato.plano || "Sob medida"}</td>
                  <td style={{ padding: "0.6rem 1rem", textTransform: "capitalize" }}>{contrato.ciclo_pagamento || "mensal"}</td>
                  <td style={{ padding: "0.6rem 1rem", fontVariantNumeric: "tabular-nums" }}>{contrato.preco_mensal != null ? `R$ ${contrato.preco_mensal.toFixed(2)}` : "—"}</td>
                  <td style={{ padding: "0.6rem 1rem" }}>
                    <span style={{ color: st.cor, fontWeight: 700, fontSize: "0.75rem" }}>{st.label}</span>
                  </td>
                  <td style={{ padding: "0.6rem 1rem", textAlign: "right" }}>
                    {contrato.status !== "ativo" ? (
                      <button onClick={() => aprovar(fazenda.id)} disabled={processando === fazenda.id}
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: "6px", border: `1px solid ${COR.verde}`, background: "transparent", color: COR.verde, cursor: "pointer" }}>
                        <ShieldCheck size={12} /> Aprovar
                      </button>
                    ) : (
                      <button onClick={() => suspender(fazenda.id)} disabled={processando === fazenda.id}
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: "6px", border: `1px solid ${COR.vermelho}`, background: "transparent", color: COR.vermelho, cursor: "pointer" }}>
                        <Ban size={12} /> Suspender
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
