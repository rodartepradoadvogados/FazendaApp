"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { CreditCard, Building2, Clock, TrendingUp, ShieldCheck, CheckCircle2, ExternalLink, AlertTriangle, PieChart } from "lucide-react";
import {
  fetchResumoCowData, fetchFazendas, fetchContratoFazenda, aprovarContratoFazenda, fetchFazendasCofre,
  type ResumoCowData, type Fazenda, type FazendaCofre,
} from "@/lib/api";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";
import { registrarLeituraKpisCowData, calcularTendencia, type PontoHistoricoKpisCowData } from "@/lib/painelCowDataHistorico";
import { Sparkline, SetaTendencia } from "@/components/painel-cowdata/KpiTendencia";

// Ordem de exibição do rodapé "Base de fazendas por plano" — nomes batem com
// PLANOS_CATALOGO no backend (fazenda/models/planos.py); "Sob medida" e "Sem
// contrato ainda" não são planos fechados, por isso vêm depois.
const ORDEM_PLANOS = ["Standard", "Silver", "Gold", "Diamond", "Sob medida", "Sem contrato ainda"];

type ItemFilaAprovacao = { id: number; nome: string; plano: string; precoMensal: number | null };

function Cartao({
  titulo, valor, icon: Icon, cor, historico, tendencia, favoravelSeSobe = true,
}: {
  titulo: string; valor: string; icon: any; cor?: string;
  historico?: number[]; tendencia?: ReturnType<typeof calcularTendencia>; favoravelSeSobe?: boolean;
}) {
  const COR = usePainelCowDataCor();
  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.1rem 1.3rem", flex: "1 1 12rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em", color: COR.mudo, marginBottom: "0.5rem" }}>
        <Icon size={13} /> {titulo}
      </div>
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: "0.6rem" }}>
        <div style={{ fontSize: "1.6rem", fontWeight: 700, color: cor || COR.texto, fontVariantNumeric: "tabular-nums" }}>{valor}</div>
        {historico && <Sparkline valores={historico} cor={cor || COR.doradoClaro} />}
      </div>
      {tendencia && (
        <div style={{ marginTop: "0.4rem" }}>
          <SetaTendencia tendencia={tendencia} favoravelSeSobe={favoravelSeSobe} cor={COR} />
        </div>
      )}
    </div>
  );
}

export default function CockpitCowData() {
  const COR = usePainelCowDataCor();
  const [resumo, setResumo] = useState<ResumoCowData | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [historico, setHistorico] = useState<PontoHistoricoKpisCowData[]>([]);

  const [fila, setFila] = useState<ItemFilaAprovacao[] | null>(null);
  const [erroFila, setErroFila] = useState<string | null>(null);
  const [aprovandoId, setAprovandoId] = useState<number | null>(null);

  const [porPlano, setPorPlano] = useState<Record<string, number> | null>(null);
  const [erroPorPlano, setErroPorPlano] = useState<string | null>(null);

  function carregarResumo() {
    fetchResumoCowData()
      .then((r) => { setResumo(r); setHistorico(registrarLeituraKpisCowData(r)); })
      .catch((e) => setErro(e.message));
  }
  useEffect(carregarResumo, []);

  // Rodapé "Base de fazendas por plano" — reaproveita o mesmo endpoint que já
  // alimenta Suporte › Política de aprovação por fazenda (fetchFazendasCofre),
  // que já devolve o plano de cada fazenda-cliente; nenhuma rota nova.
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
      .catch((e) => setErroPorPlano(e.message));
  }, []);

  // Fila de aprovação promovida ao corpo do Cockpit — antes só existia como
  // contagem no cartão "Aguardando aprovação"; para ver QUAIS fazendas eram
  // era preciso ir para Fazendas e abrir uma por uma. Não existe endpoint que
  // já devolva "as fazendas pendentes" prontas (resumo-cowdata só soma), então
  // busca-se a lista completa (fetchFazendas, 1 chamada) e o contrato de cada
  // uma (fetchContratoFazenda, já existe por fazenda) só quando o resumo
  // indica que há alguma pendência — evita o custo quando a fila está vazia,
  // que é o caso comum.
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

  const historicoValores = (chave: keyof Omit<PontoHistoricoKpisCowData, "data">) => historico.map((p) => p[chave]);

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Cockpit</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Visão geral do negócio CowData — separado dos dados operacionais da Fazenda Jairo Nasser.
      </p>

      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", marginBottom: "1.8rem" }}>
        <Cartao
          titulo="MRR (receita mensal recorrente)" valor={resumo ? `R$ ${resumo.mrr.toFixed(2)}` : "—"} icon={TrendingUp} cor={COR.verde}
          historico={historicoValores("mrr")} tendencia={calcularTendencia(historico, "mrr")}
        />
        <Cartao
          titulo="Fazendas-cliente" valor={resumo ? String(resumo.total_fazendas) : "—"} icon={Building2}
          historico={historicoValores("total_fazendas")} tendencia={calcularTendencia(historico, "total_fazendas")}
        />
        <Cartao
          titulo="Contratos ativos" valor={resumo ? String(resumo.ativo) : "—"} icon={CreditCard} cor={COR.verde}
          historico={historicoValores("ativo")} tendencia={calcularTendencia(historico, "ativo")}
        />
        <Cartao
          titulo="Aguardando aprovação" valor={resumo ? String(resumo.aguardando_aprovacao) : "—"} icon={Clock}
          cor={resumo && resumo.aguardando_aprovacao > 0 ? COR.dourado : undefined}
          historico={historicoValores("aguardando_aprovacao")} tendencia={calcularTendencia(historico, "aguardando_aprovacao")}
          favoravelSeSobe={false}
        />
      </div>

      {/* Fila de aprovação — o item mais acionável do painel, promovido para o
          corpo principal em vez de só uma contagem (ver comentário no efeito
          acima). Só aparece quando há pendência de verdade. */}
      {fila && fila.length > 0 && (
        <div style={{ background: COR.cartao, border: `1px solid ${COR.dourado}`, borderRadius: "var(--r-sm)", padding: "1.1rem 1.3rem", marginBottom: "1.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.8rem" }}>
            <Clock size={16} style={{ color: COR.dourado }} />
            <h2 style={{ fontSize: "0.95rem", fontWeight: 700 }}>Fila de aprovação</h2>
            <span style={{ fontSize: "0.72rem", color: COR.mudo }}>{fila.length} contrato(s) aguardando você fechar</span>
          </div>
          {erroFila && <p style={{ color: COR.vermelho, fontSize: "0.8rem", marginBottom: "0.6rem", display: "flex", alignItems: "center", gap: "0.3rem" }}><AlertTriangle size={13} /> {erroFila}</p>}
          <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
            {fila.map((f) => (
              <div key={f.id} style={{
                display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.6rem",
                background: COR.painelAlt, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "0.6rem 0.9rem",
              }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: "0.85rem" }}>{f.nome}</div>
                  <div style={{ fontSize: "0.72rem", color: COR.mudo }}>
                    Plano: {f.plano} {f.precoMensal != null && `— R$ ${f.precoMensal.toFixed(2)}/mês`}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <Link href="/painel-cowdata/fazendas" style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem", fontSize: "0.76rem", color: COR.mudo, textDecoration: "none" }}>
                    <ExternalLink size={13} /> Revisar
                  </Link>
                  <button onClick={() => aprovarNaFila(f.id)} disabled={aprovandoId === f.id} style={{
                    display: "inline-flex", alignItems: "center", gap: "0.35rem", background: "transparent",
                    border: `1px solid ${COR.verde}`, color: COR.verde, borderRadius: "var(--r-sm)", padding: "0.35rem 0.7rem",
                    fontSize: "0.78rem", cursor: "pointer",
                  }}>
                    <CheckCircle2 size={13} /> {aprovandoId === f.id ? "Aprovando…" : "Aprovar"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
      {fila && fila.length === 0 && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", color: COR.mudo, fontSize: "0.8rem", marginBottom: "1.5rem" }}>
          <ShieldCheck size={15} style={{ color: COR.verde }} /> Nenhum contrato aguardando aprovação no momento.
        </div>
      )}

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.2rem 1.4rem", marginBottom: "1.5rem" }}>
        <h2 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "0.6rem" }}>Atalhos</h2>
        <div style={{ display: "flex", gap: "0.8rem", flexWrap: "wrap" }}>
          <Link href="/painel-cowdata/assinaturas" style={{ color: COR.dourado, fontSize: "0.82rem", textDecoration: "none" }}>Ver assinaturas →</Link>
          <Link href="/painel-cowdata/fazendas" style={{ color: COR.dourado, fontSize: "0.82rem", textDecoration: "none" }}>Aprovar/gerenciar contratos →</Link>
          <Link href="/painel-cowdata/financeiro" style={{ color: COR.dourado, fontSize: "0.82rem", textDecoration: "none" }}>Financeiro CowData →</Link>
        </div>
      </div>

      {/* Rodapé — base de fazendas por plano. */}
      <div style={{ borderTop: `1px solid ${COR.borda}`, paddingTop: "1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginBottom: "0.7rem" }}>
          <PieChart size={14} style={{ color: COR.mudo }} />
          <h2 style={{ fontSize: "0.8rem", fontWeight: 700, color: COR.mudo, textTransform: "uppercase", letterSpacing: "0.05em" }}>Base de fazendas por plano</h2>
        </div>
        {erroPorPlano && <p style={{ color: COR.vermelho, fontSize: "0.8rem" }}>{erroPorPlano}</p>}
        {!erroPorPlano && !porPlano && <p style={{ color: COR.mudo, fontSize: "0.8rem" }}>Carregando…</p>}
        {porPlano && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.6rem" }}>
            {ORDEM_PLANOS.filter((rotulo) => porPlano[rotulo] > 0).map((rotulo) => (
              <div key={rotulo} style={{
                display: "flex", alignItems: "baseline", gap: "0.4rem", background: COR.cartao, border: `1px solid ${COR.borda}`,
                borderRadius: "999px", padding: "0.4rem 0.9rem",
              }}>
                <span style={{ fontSize: "1rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{porPlano[rotulo]}</span>
                <span style={{ fontSize: "0.76rem", color: COR.mudo }}>{rotulo}</span>
              </div>
            ))}
            {Object.keys(porPlano).filter((r) => !ORDEM_PLANOS.includes(r)).map((rotulo) => (
              <div key={rotulo} style={{
                display: "flex", alignItems: "baseline", gap: "0.4rem", background: COR.cartao, border: `1px solid ${COR.borda}`,
                borderRadius: "999px", padding: "0.4rem 0.9rem",
              }}>
                <span style={{ fontSize: "1rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{porPlano[rotulo]}</span>
                <span style={{ fontSize: "0.76rem", color: COR.mudo }}>{rotulo}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
