"use client";
// Início do Painel CowData dentro do app (nativo/PWA) — substitui a gaveta
// lateral pensada pro desktop por uma grade mobile de verdade: um cartão por
// grupo (Negócio/Administração/Operação), com os KPIs do Cockpit à mostra no
// grupo Negócio. Pedido explícito do usuário (01/09/2026), aprovado a partir
// da proposta em /design.
//
// Reaproveita GRUPOS/gruposVisiveisPainelCowData do layout do site (mesma
// lista, mesmo filtro por área de quem não é dono) — nunca duplica a lista
// de áreas, senão as duas vias saem de sincronia.
import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, ChevronRight } from "lucide-react";
import { gruposVisiveisPainelCowData } from "@/app/painel-cowdata/layout";
import { CowDataWordmark } from "@/components/CowDataWordmark";
import { ehDono, fetchResumoCowData, type ResumoCowData } from "@/lib/api";
import { usePainelCowDataCor } from "@/lib/painelCowDataTema";

// O item "Cockpit" do site aponta pra raiz (/painel-cowdata, onde mora o
// Cockpit de desktop) — dentro do app ele precisa ir pra tela mobile
// dedicada (ver app/painel-cowdata/cockpit/page.tsx), senão cairia de volta
// nesta mesma grade (o mesmo caminho vira o Cockpit OU o início, conforme
// PainelCowDataShell::appMode).
function hrefMobile(area: string, href: string): string {
  return area === "cockpit" ? "/painel-cowdata/cockpit" : href;
}

export default function InicioMobilePainelCowData() {
  const COR = usePainelCowDataCor();
  const [resumo, setResumo] = useState<ResumoCowData | null>(null);
  useEffect(() => { fetchResumoCowData().then(setResumo).catch(() => {}); }, []);

  const grupos = gruposVisiveisPainelCowData();
  const souDono = ehDono();

  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "calc(1.3rem + env(safe-area-inset-top, 0px)) 1.1rem 1rem", borderBottom: `1px solid ${COR.borda}` }}>
        <Link href="/app" style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.75rem", color: COR.mudo, textDecoration: "none", marginBottom: "0.9rem" }}>
          <ArrowLeft size={13} /> Voltar à fazenda
        </Link>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div style={{ width: 30, height: 30, borderRadius: 2, background: COR.dourado, flexShrink: 0 }} />
          <CowDataWordmark size="1.15rem" cowColor={COR.textoPainel} dataColor={COR.doradoClaro} />
        </div>
        <p style={{ fontSize: "0.64rem", color: COR.mudo, textTransform: "uppercase", letterSpacing: "0.08em", margin: "0.45rem 0 0" }}>
          Painel da empresa
        </p>
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: "1rem 1.1rem 2rem", display: "flex", flexDirection: "column", gap: "1.1rem" }}>
        {grupos.map((g) => {
          const temCockpit = souDono && g.titulo === "Negócio";
          return (
            <div key={g.titulo} style={{ background: COR.painelAlt, border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", overflow: "hidden" }}>
              <p style={{ fontSize: "0.64rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.07em", color: COR.mudo, margin: 0, padding: "0.85rem 0.9rem 0" }}>
                {g.titulo}
              </p>

              {temCockpit && resumo && (
                <div style={{
                  display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 1, background: COR.borda,
                  margin: "0.7rem 0.9rem 0", border: `1px solid ${COR.borda}`, borderRadius: "var(--r-sm)", overflow: "hidden",
                }}>
                  <CelulaKpi cor={COR} valor={`R$ ${resumo.mrr.toFixed(0)}`} label="MRR" destaque="verde" />
                  <CelulaKpi cor={COR} valor={String(resumo.total_fazendas)} label="fazendas" />
                  <CelulaKpi cor={COR} valor={String(resumo.ativo)} label="contratos" destaque="verde" />
                  <CelulaKpi cor={COR} valor={String(resumo.aguardando_aprovacao)} label="pendentes" destaque={resumo.aguardando_aprovacao > 0 ? "dourado" : undefined} />
                </div>
              )}

              <div style={{ padding: "0.6rem", display: "flex", flexDirection: "column", gap: "0.1rem", marginTop: temCockpit ? "0.3rem" : "0.3rem" }}>
                {g.itens.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Link key={item.href} href={hrefMobile(item.area, item.href)}
                      style={{
                        display: "flex", alignItems: "center", gap: "0.65rem", padding: "0.7rem 0.9rem",
                        borderRadius: "var(--r-sm)", textDecoration: "none", color: COR.texto,
                      }}>
                      <Icon size={17} style={{ color: COR.doradoClaro, flexShrink: 0 }} />
                      <span style={{ flex: 1, fontSize: "0.85rem" }}>{item.label}</span>
                      <ChevronRight size={15} style={{ color: COR.mudo, flexShrink: 0 }} />
                    </Link>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CelulaKpi({ cor, valor, label, destaque }: { cor: ReturnType<typeof usePainelCowDataCor>; valor: string; label: string; destaque?: "verde" | "dourado" }) {
  const corValor = destaque === "verde" ? cor.verde : destaque === "dourado" ? cor.dourado : cor.texto;
  return (
    <div style={{ background: cor.painel, padding: "0.6rem 0.35rem", textAlign: "center" }}>
      <div style={{ fontSize: "0.9rem", fontWeight: 700, color: corValor, fontVariantNumeric: "tabular-nums" }}>{valor}</div>
      <div style={{ fontSize: "0.56rem", color: cor.mudo, marginTop: "0.15rem" }}>{label}</div>
    </div>
  );
}
