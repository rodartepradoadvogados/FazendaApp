"use client";
import { useEffect, useState } from "react";
import { ShieldCheck, Ban } from "lucide-react";
import {
  fetchFazendas, fetchContratoFazenda, aprovarContratoFazenda, suspenderContratoFazenda,
  type Fazenda, type ContratoFazenda,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

export default function AssinaturasCowData() {
  const COR = usePainelCowDataCor();
  const STATUS_LABEL: Record<string, { label: string; cor: string }> = {
    ativo: { label: "Ativo", cor: COR.verde },
    aguardando_aprovacao: { label: "Aguardando aprovação", cor: COR.dourado },
    suspenso: { label: "Suspenso", cor: COR.vermelho },
  };
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

  // Achata fazenda+contrato para o useOrdenacao poder ler `linha[campo]` direto.
  const linhasOrd = (linhas ?? []).map((l) => ({
    ...l, fazenda_nome: l.fazenda.nome, plano: l.contrato.plano, ciclo_pagamento: l.contrato.ciclo_pagamento,
    preco_mensal: l.contrato.preco_mensal, status: l.contrato.status || "aguardando_aprovacao",
  }));
  const ord = useOrdenacao(linhasOrd);

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Assinaturas</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Contrato e faturamento de cada fazenda-cliente. Edição de plano/módulos fica em Fazendas (clientes).
      </p>
      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", overflowX: "auto", overflowY: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
          <thead>
            <tr style={{ borderBottom: `1px solid ${COR.borda}`, color: COR.mudo, textAlign: "left" }}>
              <ThOrdenavel label="Fazenda" campo="fazenda_nome" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Plano" campo="plano" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Ciclo" campo="ciclo_pagamento" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Valor/mês" campo="preco_mensal" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Status" campo="status" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
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
            {linhas && ord.linhasOrdenadas.map(({ fazenda, contrato }) => {
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
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: "var(--r-sm)", border: `1px solid ${COR.verde}`, background: "transparent", color: COR.verde, cursor: "pointer" }}>
                        <ShieldCheck size={12} /> Aprovar
                      </button>
                    ) : (
                      <button onClick={() => suspender(fazenda.id)} disabled={processando === fazenda.id}
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: "var(--r-sm)", border: `1px solid ${COR.vermelho}`, background: "transparent", color: COR.vermelho, cursor: "pointer" }}>
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
