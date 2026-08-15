"use client";
// Painel do Contador — acesso do contador externo da fazenda (vínculo
// UsuarioFazenda.contador, ver backend/fazenda/models/multitenant.py e
// AuthShell.tsx::ehPainelContador). Deliberadamente "soa diferente" do resto
// do sistema (nem a paleta vinho/verde/azul da fazenda, nem o navy+dourado
// do Painel CowData): tipografia serifada de livro-caixa sobre grafite
// neutro-azulado (paleta cinza-azulada do redesign, sem o cobre/marrom da
// versão anterior), com friso duplo no cabeçalho — a intenção é que nunca
// pareça "mais uma tela da fazenda". Não tem equivalente no app móvel (ver
// AuthShell.tsx).
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft } from "lucide-react";
import { ehContador, getFazendaAtual, getUsuario, logout } from "@/lib/api";
import { consumirVeioDaAdministracao } from "@/lib/portalAdministracao";

export const CORES_CONTADOR = {
  bg: "#1A2028",
  painel: "#212832",
  painelAlt: "#262E39",
  borda: "#39424F",
  bordaClara: "#4B5563",
  texto: "#F1F3F5",
  mudo: "#9CA6B4",
  cobre: "#6B7F99",
  cobreClaro: "#8FA0B5",
  positivo: "#8faa7b",
  negativo: "#b5544a",
};

const FONTE_SERIF = "'Iowan Old Style', 'Palatino Linotype', Georgia, serif";
const FONTE_BASE = "system-ui, -apple-system, sans-serif";

export default function ContadorLayout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const fazenda = getFazendaAtual();
  const usuario = getUsuario();
  const C = CORES_CONTADOR;

  // Quem chega aqui pelo portal Administração (aba "Painel do Contador",
  // ver InsightsLayout.tsx) precisa voltar para lá, não para a Capa da
  // fazenda — ver lib/portalAdministracao.ts.
  const [voltarHref, setVoltarHref] = useState("/");
  const [voltarLabel, setVoltarLabel] = useState("Voltar à fazenda");
  useEffect(() => {
    if (consumirVeioDaAdministracao()) {
      setVoltarHref("/usuarios");
      setVoltarLabel("Voltar à Administração");
    }
  }, []);

  return (
    <div style={{ minHeight: "100vh", background: C.bg, color: C.texto, fontFamily: FONTE_BASE }}>
      <header style={{ borderBottom: `1px solid ${C.borda}`, background: C.painel }}>
        <div style={{ maxWidth: "1100px", margin: "0 auto", padding: "1.4rem 1.6rem 1.1rem" }}>
          {/* O contador de verdade não tem "fazenda" pra voltar — esse link só
              aparece para o proprietário espiando esta tela pela Sidebar >
              Administração (ver AuthShell.tsx). */}
          {!ehContador() && (
            <Link href={voltarHref} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", color: C.mudo, textDecoration: "none", marginBottom: "0.9rem" }}>
              <ArrowLeft size={13} /> {voltarLabel}
            </Link>
          )}
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: "0.6rem" }}>
            <div>
              <p style={{ fontFamily: FONTE_SERIF, fontSize: "1.5rem", fontWeight: 700, letterSpacing: "0.01em", margin: 0, color: C.texto }}>
                Painel do Contador
              </p>
              <p style={{ fontSize: "0.78rem", color: C.mudo, margin: "0.15rem 0 0", textTransform: "uppercase", letterSpacing: "0.08em" }}>
                {fazenda?.nome || "Fazenda"} {(fazenda?.cidade || fazenda?.uf) && `— ${[fazenda.cidade, fazenda.uf].filter(Boolean).join("/")}`}
              </p>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.9rem" }}>
              <span style={{
                fontSize: "0.68rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em",
                color: C.cobreClaro, border: `1px solid ${C.cobre}`, borderRadius: "var(--r-sm)", padding: "0.2rem 0.5rem",
              }}>
                Somente leitura
              </span>
              <div style={{ textAlign: "right" }}>
                <p style={{ fontSize: "0.78rem", margin: 0, color: C.texto }}>{usuario?.nome || usuario?.username}</p>
                <button type="button" onClick={logout}
                  style={{ background: "none", border: "none", padding: 0, color: C.mudo, fontSize: "0.72rem", textDecoration: "underline", cursor: "pointer" }}>
                  Sair
                </button>
              </div>
            </div>
          </div>
        </div>
        {/* Friso duplo — a assinatura visual do "livro-caixa", distinta de
            qualquer outra casca do sistema. */}
        <div style={{ height: "1px", background: C.bordaClara }} />
        <div style={{ height: "3px", background: C.bg }} />
        <div style={{ height: "1px", background: C.borda }} />
      </header>
      <main style={{ maxWidth: "1100px", margin: "0 auto", padding: "1.8rem 1.6rem 3rem" }}>{children}</main>
    </div>
  );
}
