"use client";
// Peças compartilhadas das telas do Rebanho no app móvel:
// busca de um único animal e normalização sem acento.
import { useEffect, useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { fetchAnimais } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";
import { normalizarBusca } from "@/lib/busca";

export type AnimalMob = {
  numero: string;
  nome?: string | null;
  grupo_primario?: string | null;
  categoria_abrev?: string | null;
  del_dias?: number | null;
  ativo?: boolean;
};

/** minúsculas, sem acento e sem hífen/underscore/espaço, para busca
 * tolerante — delega ao helper único (lib/busca.ts). */
export function normalizar(s: unknown): string {
  return normalizarBusca(s == null ? "" : String(s));
}

export function subtituloAnimal(a: { categoria_abrev?: string | null; grupo_primario?: string | null }): string {
  return [a.categoria_abrev || "sem categoria", a.grupo_primario || "sem lote"].join(" · ");
}

// ── Busca de um único animal ─────────────────────────────────────────────────
export function BuscaAnimal({
  valor, onEscolher, placeholder = "Buscar brinco ou nome…",
}: {
  valor: string;
  onEscolher: (numero: string, animal?: AnimalMob) => void;
  placeholder?: string;
}) {
  const [animais, setAnimais] = useState<AnimalMob[]>([]);
  const [busca, setBusca] = useState("");

  useEffect(() => {
    let vivo = true;
    // Chave de cache PRÓPRIA ("animais_todos"), não a "animais" compartilhada
    // pelas telas de ação reprodutiva/produtiva (Modo Curral, Lançar, Lotes,
    // Indicadores) — aquelas continuam só-fêmeas de propósito (bezerro/touro
    // não entra em controle leiteiro nem protocolo). Esta busca é "achar
    // qualquer animal da fazenda" (Ficha, drill-down) — machos incluídos.
    fetchComCache<AnimalMob[]>("animais_todos", () => fetchAnimais({ incluirMachos: true })).then(({ dados }) => {
      if (vivo && dados) setAnimais(dados);
    });
    return () => { vivo = false; };
  }, []);

  const filtrados = useMemo(() => {
    const q = normalizar(busca);
    if (!q) return [];
    // Busca por brinco OU nome (como o placeholder promete).
    return animais.filter((a) => normalizar(a.numero).includes(q) || normalizar(a.nome).includes(q)).slice(0, 25);
  }, [animais, busca]);

  const selecionado = animais.find((a) => a.numero === valor);

  if (valor) {
    return (
      <div className="mob-linha" style={{ cursor: "default", marginBottom: 0 }}>
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: "block", fontWeight: 700 }}>Brinco {valor}{selecionado?.nome ? ` · ${selecionado.nome}` : ""}</span>
          {selecionado && <span style={{ display: "block", fontSize: "0.78rem", color: "var(--mob-muted)" }}>{subtituloAnimal(selecionado)}</span>}
        </span>
        <button type="button" onClick={() => { onEscolher(""); setBusca(""); }} aria-label="Trocar animal"
          style={{ width: 56, height: 56, borderRadius: "var(--r-app)", border: "1px solid var(--mob-border)", background: "var(--mob-surface)", color: "var(--mob-text)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, cursor: "pointer" }}>
          <X size={18} />
        </button>
      </div>
    );
  }

  return (
    <div>
      <div style={{ position: "relative" }}>
        <Search size={18} style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)" }} />
        <input className="mob-input" style={{ paddingLeft: "2.4rem" }} value={busca} onChange={(e) => setBusca(e.target.value)}
          placeholder={placeholder} type="search" autoComplete="off" />
      </div>
      {busca && (
        <div style={{ marginTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {filtrados.map((a) => (
            <button key={a.numero} type="button" className="mob-linha" style={{ marginBottom: 0 }}
              onClick={() => { onEscolher(a.numero, a); setBusca(""); }}>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontWeight: 700 }}>Brinco {a.numero}{a.nome ? ` · ${a.nome}` : ""}</span>
                <span style={{ display: "block", fontSize: "0.78rem", color: "var(--mob-muted)" }}>{subtituloAnimal(a)}</span>
              </span>
            </button>
          ))}
          {!filtrados.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.85rem", padding: "0.4rem 0.2rem" }}>Nenhum animal encontrado.</p>}
        </div>
      )}
    </div>
  );
}
