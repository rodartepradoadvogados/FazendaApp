"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { ShieldCheck, Ban, Clock, CheckCircle2, XCircle } from "lucide-react";
import {
  fetchFazendas, fetchContratoFazenda, aprovarContratoFazenda, suspenderContratoFazenda,
  type Fazenda, type ContratoFazenda,
} from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

export default function AssinaturasCowData() {
  const COR = usePainelCowDataCor();
  const searchParams = useSearchParams();
  // Fila filtrada a partir do Cockpit — o card "Aguardando aprovação" linka
  // pra cá com ?filtro=pendente, em vez de ser só decorativo (achado da
  // crítica, ver docs/agents/design-implementation.md §5,
  // confirmar-antes-de-cortar.html).
  const soPendentes = searchParams.get("filtro") === "pendente";
  // Ícone além da cor no status — um operador daltônico não distinguia
  // "Ativo" de "Suspenso" só pela cor (mesmo achado da crítica).
  const STATUS_LABEL: Record<string, { label: string; cor: string; Icon: any }> = {
    ativo: { label: "Ativo", cor: COR.verde, Icon: CheckCircle2 },
    aguardando_aprovacao: { label: "Aguardando aprovação", cor: COR.dourado, Icon: Clock },
    suspenso: { label: "Suspenso", cor: COR.vermelho, Icon: XCircle },
  };
  const [linhas, setLinhas] = useState<{ fazenda: Fazenda; contrato: ContratoFazenda }[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [processando, setProcessando] = useState<number | null>(null);
  const [confirmarSuspensao, setConfirmarSuspensao] = useState<{ id: number; nome: string } | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  function carregar() {
    fetchFazendas()
      .then(async (fazendas) => {
        const linhasCarregadas = await Promise.all(
          fazendas.map(async (fazenda) => ({ fazenda, contrato: await fetchContratoFazenda(fazenda.id) })),
        );
        setLinhas(linhasCarregadas);
      })
      .catch(() => setErro("Não foi possível carregar as assinaturas. Verifique sua conexão e tente novamente."));
  }
  useEffect(carregar, []);

  function mostrarToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3200);
  }

  async function aprovar(fazendaId: number, nome: string) {
    setProcessando(fazendaId); setErro(null);
    try { await aprovarContratoFazenda(fazendaId); carregar(); mostrarToast(`${nome} aprovada com sucesso.`); }
    catch { setErro("Não foi possível aprovar este contrato agora. Tente novamente."); }
    finally { setProcessando(null); }
  }
  async function suspenderConfirmado() {
    if (!confirmarSuspensao) return;
    const { id, nome } = confirmarSuspensao;
    setProcessando(id); setErro(null); setConfirmarSuspensao(null);
    try { await suspenderContratoFazenda(id); carregar(); mostrarToast(`${nome} suspensa com sucesso.`); }
    catch { setErro("Não foi possível suspender este contrato agora. Tente novamente."); }
    finally { setProcessando(null); }
  }

  // Achata fazenda+contrato para o useOrdenacao poder ler `linha[campo]` direto.
  const linhasBase = (linhas ?? []).map((l) => ({
    ...l, fazenda_nome: l.fazenda.nome, plano: l.contrato.plano, ciclo_pagamento: l.contrato.ciclo_pagamento,
    preco_mensal: l.contrato.preco_mensal, status: l.contrato.status || "aguardando_aprovacao",
  }));
  // Pendentes primeiro por padrão — hoje a ordem era arbitrária (achado da
  // crítica: o founder precisa escanear a tabela inteira pra achar quem
  // precisa de atenção).
  const ORDEM_STATUS: Record<string, number> = { aguardando_aprovacao: 0, ativo: 1, suspenso: 2 };
  const linhasOrd = [...linhasBase].sort((a, b) => (ORDEM_STATUS[a.status] ?? 9) - (ORDEM_STATUS[b.status] ?? 9));
  const linhasFiltradas = soPendentes ? linhasOrd.filter((l) => l.status === "aguardando_aprovacao") : linhasOrd;
  const ord = useOrdenacao(linhasFiltradas);

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Assinaturas</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "0.6rem" }}>
        Contrato e faturamento de cada fazenda-cliente. Edição de plano/módulos fica em Fazendas (clientes).
      </p>
      {soPendentes && (
        <p style={{ fontSize: "0.82rem", marginBottom: "0.9rem" }}>
          <span style={{ color: COR.dourado, fontWeight: 700 }}>Mostrando só pendentes de aprovação.</span>{" "}
          <Link href="/painel-cowdata/assinaturas" style={{ color: COR.mudo }}>Ver todas →</Link>
        </p>
      )}
      {erro && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", background: `${COR.vermelho}18`, border: `1px solid ${COR.vermelho}`, borderRadius: "var(--r-sm)", padding: "0.6rem 0.9rem", marginBottom: "1rem" }}>
          <p style={{ color: COR.vermelho, fontSize: "0.85rem", flex: 1, margin: 0 }}>{erro}</p>
          <button onClick={carregar} style={{ background: "transparent", border: `1px solid ${COR.vermelho}`, color: COR.vermelho, borderRadius: "var(--r-sm)", padding: "0.3rem 0.7rem", fontSize: "0.78rem", cursor: "pointer", flexShrink: 0 }}>
            ↻ Tentar novamente
          </button>
        </div>
      )}

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
            {linhas && linhasFiltradas.length === 0 && (
              <tr><td colSpan={6} style={{ padding: "1rem", color: COR.mudo }}>Nenhuma pendente de aprovação agora.</td></tr>
            )}
            {linhas && ord.linhasOrdenadas.map(({ fazenda, contrato }) => {
              const st = STATUS_LABEL[contrato.status || "aguardando_aprovacao"] || { label: "Sem contrato", cor: COR.mudo, Icon: Clock };
              return (
                <tr key={fazenda.id} style={{ borderBottom: `1px solid ${COR.borda}` }}>
                  <td style={{ padding: "0.6rem 1rem" }}>{fazenda.nome}</td>
                  <td style={{ padding: "0.6rem 1rem", textTransform: "capitalize" }}>{contrato.plano || "Sob medida"}</td>
                  <td style={{ padding: "0.6rem 1rem", textTransform: "capitalize" }}>{contrato.ciclo_pagamento || "mensal"}</td>
                  <td style={{ padding: "0.6rem 1rem", fontVariantNumeric: "tabular-nums" }}>{contrato.preco_mensal != null ? `R$ ${contrato.preco_mensal.toFixed(2)}` : "—"}</td>
                  <td style={{ padding: "0.6rem 1rem" }}>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", color: st.cor, fontWeight: 700, fontSize: "0.75rem" }}>
                      <st.Icon size={13} /> {st.label}
                    </span>
                  </td>
                  <td style={{ padding: "0.6rem 1rem", textAlign: "right" }}>
                    {contrato.status !== "ativo" ? (
                      <button onClick={() => aprovar(fazenda.id, fazenda.nome)} disabled={processando === fazenda.id}
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.75rem", padding: "0.3rem 0.6rem", borderRadius: "var(--r-sm)", border: `1px solid ${COR.verde}`, background: "transparent", color: COR.verde, cursor: "pointer" }}>
                        <ShieldCheck size={12} /> Aprovar
                      </button>
                    ) : (
                      <button onClick={() => setConfirmarSuspensao({ id: fazenda.id, nome: fazenda.nome })} disabled={processando === fazenda.id}
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

      {/* Confirmação antes de suspender — a ação de maior consequência do
          sistema não pode ter menos fricção que apagar um lançamento manual
          (achado P0 da crítica, ver
          docs/agents/design-implementation.md §5, confirmar-antes-de-cortar.html). */}
      {confirmarSuspensao && (
        <div onClick={() => setConfirmarSuspensao(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: "1rem" }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.4rem 1.5rem", maxWidth: "26rem", width: "100%" }}>
            <h3 style={{ margin: "0 0 0.5rem", fontSize: "1.05rem", color: COR.texto }}>Suspender acesso?</h3>
            <p style={{ fontSize: "0.85rem", color: COR.mudo, margin: "0 0 1.1rem", lineHeight: 1.5 }}>
              Você está prestes a suspender o acesso de <strong style={{ color: COR.texto }}>{confirmarSuspensao.nome}</strong>. O usuário da fazenda perde acesso ao painel e ao app de campo imediatamente. Pode ser revertido depois, aprovando de novo.
            </p>
            <div style={{ display: "flex", gap: "0.6rem", justifyContent: "flex-end" }}>
              <button onClick={() => setConfirmarSuspensao(null)}
                style={{ background: "transparent", border: `1px solid ${COR.borda}`, color: COR.texto, borderRadius: "var(--r-sm)", padding: "0.5rem 1rem", fontSize: "0.85rem", cursor: "pointer" }}>
                Cancelar
              </button>
              <button onClick={suspenderConfirmado}
                style={{ background: COR.vermelho, border: `1px solid ${COR.vermelho}`, color: "#fff", borderRadius: "var(--r-sm)", padding: "0.5rem 1rem", fontSize: "0.85rem", fontWeight: 700, cursor: "pointer" }}>
                Suspender mesmo assim
              </button>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div style={{ position: "fixed", bottom: "1.5rem", right: "1.5rem", background: COR.verde, color: "#fff", padding: "0.7rem 1.1rem", borderRadius: "var(--r-sm)", fontSize: "0.85rem", fontWeight: 600, boxShadow: "0 10px 24px rgba(0,0,0,0.3)", zIndex: 110 }}>
          {toast}
        </div>
      )}
    </div>
  );
}
