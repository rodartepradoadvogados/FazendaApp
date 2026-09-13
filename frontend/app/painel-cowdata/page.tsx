"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { CreditCard, Building2, Clock, TrendingUp, LifeBuoy } from "lucide-react";
import { fetchResumoCowData, fetchPedidosRecentesCofre, type ResumoCowData, type PedidoAcessoSuporte } from "@/lib/api";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

function Cartao({ titulo, valor, icon: Icon, cor, href }: { titulo: string; valor: string; icon: any; cor?: string; href?: string }) {
  const COR = usePainelCowDataCor();
  const conteudo = (
    <div style={{ background: COR.cartao, border: `1px solid ${href ? COR.dourado : COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.1rem 1.3rem", flex: "1 1 12rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em", color: COR.mudo, marginBottom: "0.5rem" }}>
        <Icon size={13} /> {titulo}
      </div>
      <div style={{ fontSize: "1.6rem", fontWeight: 700, color: cor || COR.texto, fontVariantNumeric: "tabular-nums" }}>{valor}</div>
      {href && <div style={{ fontSize: "0.72rem", color: COR.dourado, fontWeight: 700, marginTop: "0.3rem" }}>Ver fila →</div>}
    </div>
  );
  // Card "Aguardando aprovação" vira link real pra fila filtrada — antes era
  // decorativo (só ficava dourado), sem linkar pra lugar nenhum (achado P1
  // da crítica, ver docs/agents/design-implementation.md §5,
  // confirmar-antes-de-cortar.html).
  if (href) return <Link href={href} style={{ textDecoration: "none", flex: "1 1 12rem" }}>{conteudo}</Link>;
  return conteudo;
}

export default function CockpitCowData() {
  const COR = usePainelCowDataCor();
  const [resumo, setResumo] = useState<ResumoCowData | null>(null);
  const [pedidosSuporte, setPedidosSuporte] = useState<PedidoAcessoSuporte[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  function carregar() {
    setErro(null);
    fetchResumoCowData().then(setResumo).catch(() => setErro("Não foi possível carregar o resumo do negócio agora. Tente novamente."));
    fetchPedidosRecentesCofre().then(setPedidosSuporte).catch(() => {});
  }
  useEffect(carregar, []);

  const suportePendente = (pedidosSuporte ?? []).filter((p) => p.status === "aguardando_aprovacao");
  const temFila = (resumo?.aguardando_aprovacao ?? 0) > 0 || suportePendente.length > 0;

  return (
    <div className="animate-in">
      <h1 style={{ fontSize: "1.4rem", fontWeight: 700, marginBottom: "0.2rem" }}>Cockpit</h1>
      <p style={{ color: COR.mudo, fontSize: "0.85rem", marginBottom: "1.5rem" }}>
        Visão geral do negócio CowData — separado dos dados operacionais da Fazenda Jairo Nasser.
      </p>

      {erro && (
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", background: `${COR.vermelho}18`, border: `1px solid ${COR.vermelho}`, borderRadius: "var(--r-sm)", padding: "0.6rem 0.9rem", marginBottom: "1rem" }}>
          <p style={{ color: COR.vermelho, fontSize: "0.85rem", flex: 1, margin: 0 }}>{erro}</p>
          <button onClick={carregar} style={{ background: "transparent", border: `1px solid ${COR.vermelho}`, color: COR.vermelho, borderRadius: "var(--r-sm)", padding: "0.3rem 0.7rem", fontSize: "0.78rem", cursor: "pointer", flexShrink: 0 }}>
            ↻ Tentar novamente
          </button>
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.9rem", marginBottom: "1.8rem" }}>
        <Cartao titulo="MRR (receita mensal recorrente)" valor={resumo ? `R$ ${resumo.mrr.toFixed(2)}` : "—"} icon={TrendingUp} cor={COR.verde} />
        <Cartao titulo="Fazendas-cliente" valor={resumo ? String(resumo.total_fazendas) : "—"} icon={Building2} />
        <Cartao titulo="Contratos ativos" valor={resumo ? String(resumo.ativo) : "—"} icon={CreditCard} cor={COR.verde} />
        <Cartao
          titulo="Aguardando aprovação" valor={resumo ? String(resumo.aguardando_aprovacao) : "—"} icon={Clock}
          cor={resumo && resumo.aguardando_aprovacao > 0 ? COR.dourado : undefined}
          href={resumo && resumo.aguardando_aprovacao > 0 ? "/painel-cowdata/assinaturas?filtro=pendente" : undefined}
        />
      </div>

      {/* Fila unificada — "o que precisa de mim hoje", juntando contratos
          pendentes e pedidos de suporte pendentes num só lugar, no lugar do
          card "Atalhos" que só duplicava a sidebar (achado da crítica, ver
          docs/agents/design-implementation.md §5, painel-consistente.html). */}
      <div style={{ background: COR.cartao, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", padding: "1.2rem 1.4rem" }}>
        <h2 style={{ fontSize: "0.95rem", fontWeight: 700, marginBottom: "0.8rem" }}>Hoje</h2>
        {!temFila && (
          <p style={{ color: COR.mudo, fontSize: "0.82rem" }}>Nada pendente agora — tudo em dia.</p>
        )}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {resumo && resumo.aguardando_aprovacao > 0 && (
            <Link href="/painel-cowdata/assinaturas?filtro=pendente" style={{ textDecoration: "none" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.7rem", padding: "0.65rem 0.85rem", borderRadius: "var(--r-sm)", background: COR.painelAlt, borderLeft: `3px solid ${COR.dourado}` }}>
                <Clock size={16} style={{ color: COR.dourado, flexShrink: 0 }} />
                <span style={{ fontSize: "0.82rem", color: COR.texto, flex: 1 }}>
                  {resumo.aguardando_aprovacao} contrato(s) aguardando aprovação
                </span>
                <span style={{ fontSize: "0.72rem", color: COR.dourado, fontWeight: 700 }}>Contrato →</span>
              </div>
            </Link>
          )}
          {suportePendente.map((p) => (
            <Link key={p.id} href="/painel-cowdata/cofre" style={{ textDecoration: "none" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.7rem", padding: "0.65rem 0.85rem", borderRadius: "var(--r-sm)", background: COR.painelAlt, borderLeft: `3px solid ${COR.dourado}` }}>
                <LifeBuoy size={16} style={{ color: COR.dourado, flexShrink: 0 }} />
                <span style={{ fontSize: "0.82rem", color: COR.texto, flex: 1 }}>
                  Sessão de suporte solicitada por {p.fazenda_nome}
                </span>
                <span style={{ fontSize: "0.72rem", color: COR.dourado, fontWeight: 700 }}>Suporte →</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
