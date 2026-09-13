"use client";
// Cockpit mobile do Painel CowData — mesmos dados do Cockpit de desktop
// (app/painel-cowdata/page.tsx), em layout nativo pro app: KPIs em grade
// 2x2, fila de aprovação e atalhos como lista, sem o cartão largo pensado
// pra tela grande. Só alcançável de dentro do app (ver
// InicioMobilePainelCowData e PainelCowDataShell::appMode) — o Cockpit de
// desktop continua intacto na raiz /painel-cowdata.
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, CheckCircle2, Clock, ExternalLink, PieChart } from "lucide-react";
import {
  fetchResumoCowData, fetchFazendas, fetchContratoFazenda, aprovarContratoFazenda, fetchFazendasCofre,
  type ResumoCowData, type Fazenda, type FazendaCofre,
} from "@/lib/api";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

const ORDEM_PLANOS = ["Standard", "Silver", "Gold", "Diamond", "Sob medida", "Sem contrato ainda"];

type ItemFilaAprovacao = { id: number; nome: string; plano: string; precoMensal: number | null };

export default function CockpitMobile() {
  const COR = usePainelCowDataCor();
  const [resumo, setResumo] = useState<ResumoCowData | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [fila, setFila] = useState<ItemFilaAprovacao[] | null>(null);
  const [erroFila, setErroFila] = useState<string | null>(null);
  const [aprovandoId, setAprovandoId] = useState<number | null>(null);
  const [porPlano, setPorPlano] = useState<Record<string, number> | null>(null);

  function carregarResumo() {
    fetchResumoCowData().then(setResumo).catch((e) => setErro(e.message));
  }
  useEffect(carregarResumo, []);

  useEffect(() => {
    fetchFazendasCofre()
      .then((fazendas: FazendaCofre[]) => {
        const contagem: Record<string, number> = {};
        for (const f of fazendas) {
          const rotulo = f.plano_nome || "Sem contrato ainda";
          contagem[rotulo] = (contagem[rotulo] || 0) + 1;
        }
        setPorPlano(contagem);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!resumo) return;
    if (resumo.aguardando_aprovacao === 0) { setFila([]); return; }
    let cancelado = false;
    fetchFazendas()
      .then(async (fazendas: Fazenda[]) => {
        const comContrato = await Promise.allSettled(
          fazendas.map(async (f) => ({ f, contrato: await fetchContratoFazenda(f.id) })),
        );
        if (cancelado) return;
        const pendentes: ItemFilaAprovacao[] = comContrato
          .filter((r): r is PromiseFulfilledResult<{ f: Fazenda; contrato: Awaited<ReturnType<typeof fetchContratoFazenda>> }> => r.status === "fulfilled")
          .map((r) => r.value)
          .filter((x) => x.contrato.status === "aguardando_aprovacao")
          .map((x) => ({
            id: x.f.id, nome: x.f.nome,
            plano: x.contrato.plano ? x.contrato.plano.charAt(0).toUpperCase() + x.contrato.plano.slice(1) : "Sob medida",
            precoMensal: x.contrato.preco_mensal ?? null,
          }));
        setFila(pendentes);
      })
      .catch((e) => { if (!cancelado) setErroFila(e.message); });
    return () => { cancelado = true; };
  }, [resumo?.aguardando_aprovacao]);

  async function aprovarNaFila(id: number) {
    setAprovandoId(id);
    setErroFila(null);
    try {
      await aprovarContratoFazenda(id);
      setFila((atual) => (atual || []).filter((f) => f.id !== id));
      carregarResumo();
    } catch (e: any) { setErroFila(e.message); } finally { setAprovandoId(null); }
  }

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "calc(1.1rem + env(safe-area-inset-top, 0px)) 1.1rem 0.9rem", borderBottom: `1px solid ${COR.borda}` }}>
        <Link href="/painel-cowdata" style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.75rem", color: COR.mudo, textDecoration: "none", marginBottom: "0.7rem" }}>
          <ArrowLeft size={13} /> Painel CowData
        </Link>
        <h1 style={{ fontSize: "1.2rem", fontWeight: 700, margin: 0 }}>Cockpit</h1>
        <p style={{ color: COR.mudo, fontSize: "0.78rem", margin: "0.25rem 0 0" }}>
          Visão geral do negócio — separada dos dados da Fazenda Jairo Nasser.
        </p>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "1rem 1.1rem 2rem", display: "flex", flexDirection: "column", gap: "1.2rem" }}>
        {erro && <p style={{ color: COR.vermelho, fontSize: "0.82rem" }}>{erro}</p>}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "0.7rem" }}>
          <CartaoKpi cor={COR} label="MRR" valor={resumo ? `R$ ${resumo.mrr.toFixed(2)}` : "—"} destaque="verde" />
          <CartaoKpi cor={COR} label="Fazendas-cliente" valor={resumo ? String(resumo.total_fazendas) : "—"} />
          <CartaoKpi cor={COR} label="Contratos ativos" valor={resumo ? String(resumo.ativo) : "—"} destaque="verde" />
          <CartaoKpi cor={COR} label="Aguardando aprovação" valor={resumo ? String(resumo.aguardando_aprovacao) : "—"}
            destaque={resumo && resumo.aguardando_aprovacao > 0 ? "dourado" : undefined} />
        </div>

        {fila && fila.length > 0 && (
          <div style={{ background: COR.painelAlt, border: `1px solid ${COR.dourado}`, borderRadius: "var(--r-sm)", padding: "0.9rem 1rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.7rem" }}>
              <Clock size={15} style={{ color: COR.dourado }} />
              <h2 style={{ fontSize: "0.88rem", fontWeight: 700, margin: 0 }}>Fila de aprovação</h2>
            </div>
            {erroFila && <p style={{ color: COR.vermelho, fontSize: "0.78rem", marginBottom: "0.5rem" }}>{erroFila}</p>}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
              {fila.map((f) => (
                <div key={f.id} style={{ background: COR.painel, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.6rem 0.8rem" }}>
                  <div style={{ fontWeight: 600, fontSize: "0.84rem" }}>{f.nome}</div>
                  <div style={{ fontSize: "0.7rem", color: COR.mudo, marginBottom: "0.5rem" }}>
                    Plano: {f.plano} {f.precoMensal != null && `— R$ ${f.precoMensal.toFixed(2)}/mês`}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.7rem" }}>
                    <Link href="/painel-cowdata/fazendas" style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.74rem", color: COR.mudo, textDecoration: "none" }}>
                      <ExternalLink size={12} /> Revisar
                    </Link>
                    <button onClick={() => aprovarNaFila(f.id)} disabled={aprovandoId === f.id} style={{
                      display: "inline-flex", alignItems: "center", gap: "0.3rem", background: "transparent",
                      border: `1px solid ${COR.verde}`, color: COR.verde, borderRadius: "var(--r-sm)", padding: "0.3rem 0.6rem",
                      fontSize: "0.74rem", cursor: "pointer",
                    }}>
                      <CheckCircle2 size={12} /> {aprovandoId === f.id ? "Aprovando…" : "Aprovar"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
        {fila && fila.length === 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: COR.mudo, fontSize: "0.8rem" }}>
            <CheckCircle2 size={15} style={{ color: COR.verde }} /> Nenhum contrato aguardando aprovação no momento.
          </div>
        )}

        <div style={{ background: COR.painelAlt, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1rem 1.1rem" }}>
          <h2 style={{ fontSize: "0.88rem", fontWeight: 700, margin: "0 0 0.7rem" }}>Atalhos</h2>
          <div style={{ display: "flex", flexDirection: "column", gap: "0.55rem" }}>
            <Link href="/painel-cowdata/assinaturas" style={{ color: COR.doradoClaro, fontSize: "0.82rem", textDecoration: "none" }}>Ver assinaturas →</Link>
            <Link href="/painel-cowdata/fazendas" style={{ color: COR.doradoClaro, fontSize: "0.82rem", textDecoration: "none" }}>Aprovar/gerenciar contratos →</Link>
            <Link href="/painel-cowdata/financeiro" style={{ color: COR.doradoClaro, fontSize: "0.82rem", textDecoration: "none" }}>Financeiro CowData →</Link>
          </div>
        </div>

        <div style={{ borderTop: `1px solid ${COR.borda}`, paddingTop: "0.9rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.6rem" }}>
            <PieChart size={12} style={{ color: COR.mudo }} />
            <h2 style={{ fontSize: "0.7rem", fontWeight: 700, color: COR.mudo, textTransform: "uppercase", letterSpacing: "0.05em", margin: 0 }}>
              Base de fazendas por plano
            </h2>
          </div>
          {!porPlano && <p style={{ color: COR.mudo, fontSize: "0.8rem" }}>Carregando…</p>}
          {porPlano && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
              {[...ORDEM_PLANOS.filter((r) => porPlano[r] > 0), ...Object.keys(porPlano).filter((r) => !ORDEM_PLANOS.includes(r))].map((rotulo) => (
                <div key={rotulo} style={{
                  display: "flex", alignItems: "baseline", gap: "0.35rem", background: COR.painelAlt, border: `1px solid ${COR.borda}`,
                  borderRadius: "999px", padding: "0.35rem 0.8rem",
                }}>
                  <span style={{ fontSize: "0.92rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{porPlano[rotulo]}</span>
                  <span style={{ fontSize: "0.7rem", color: COR.mudo }}>{rotulo}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function CartaoKpi({ cor, label, valor, destaque }: {
  cor: ReturnType<typeof usePainelCowDataCor>; label: string; valor: string; destaque?: "verde" | "dourado";
}) {
  const corValor = destaque === "verde" ? cor.verde : destaque === "dourado" ? cor.dourado : cor.texto;
  return (
    <div style={{ background: cor.painelAlt, border: `1px solid ${cor.borda}`, borderRadius: "var(--r-sm)", padding: "0.85rem 0.9rem" }}>
      <div style={{ fontSize: "0.62rem", textTransform: "uppercase", letterSpacing: "0.06em", color: cor.mudo, marginBottom: "0.5rem" }}>{label}</div>
      <div style={{ fontSize: "1.35rem", fontWeight: 700, color: corValor, fontVariantNumeric: "tabular-nums" }}>{valor}</div>
    </div>
  );
}
