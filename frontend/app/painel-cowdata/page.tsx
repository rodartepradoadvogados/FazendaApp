"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { CreditCard, Building2, Clock, TrendingUp } from "lucide-react";
import { fetchResumoCowData, type ResumoCowData } from "@/lib/api";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

function Cartao({ titulo, valor, icon: Icon, cor }: { titulo: string; valor: string; icon: any; cor?: string }) {
  const COR = usePainelCowDataCor();
  return (
    <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.1rem 1.3rem", flex: "1 1 12rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em", color: COR.mudo, marginBottom: "0.5rem" }}>
        <Icon size={13} /> {titulo}
      </div>
      <div style={{ fontSize: "1.6rem", fontWeight: 700, color: cor || COR.texto, fontVariantNumeric: "tabular-nums" }}>{valor}</div>
    </div>
  );
}

export default function CockpitCowData() {
  const COR = usePainelCowDataCor();
  const [resumo, setResumo] = useState<ResumoCowData | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => { fetchResumoCowData().then(setResumo).catch((e) => setErro(e.message)); }, []);

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Cockpit</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Visão geral do negócio CowData — separado dos dados operacionais da Fazenda Jairo Nasser.
      </p>

      {erro && <p style={{ color: COR.vermelho, fontSize: "0.85rem", marginBottom: "1rem" }}>{erro}</p>}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", marginBottom: "1.8rem" }}>
        <Cartao titulo="MRR (receita mensal recorrente)" valor={resumo ? `R$ ${resumo.mrr.toFixed(2)}` : "—"} icon={TrendingUp} cor={COR.verde} />
        <Cartao titulo="Fazendas-cliente" valor={resumo ? String(resumo.total_fazendas) : "—"} icon={Building2} />
        <Cartao titulo="Contratos ativos" valor={resumo ? String(resumo.ativo) : "—"} icon={CreditCard} cor={COR.verde} />
        <Cartao titulo="Aguardando aprovação" valor={resumo ? String(resumo.aguardando_aprovacao) : "—"} icon={Clock} cor={resumo && resumo.aguardando_aprovacao > 0 ? COR.dourado : undefined} />
      </div>

      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.2rem 1.4rem" }}>
        <h2 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "0.6rem" }}>Atalhos</h2>
        <div style={{ display: "flex", gap: "0.8rem", flexWrap: "wrap" }}>
          <Link href="/painel-cowdata/assinaturas" style={{ color: COR.dourado, fontSize: "0.82rem", textDecoration: "none" }}>Ver assinaturas →</Link>
          <Link href="/painel-cowdata/fazendas" style={{ color: COR.dourado, fontSize: "0.82rem", textDecoration: "none" }}>Aprovar/gerenciar contratos →</Link>
          <Link href="/painel-cowdata/financeiro" style={{ color: COR.dourado, fontSize: "0.82rem", textDecoration: "none" }}>Financeiro CowData →</Link>
        </div>
      </div>
    </div>
  );
}
