"use client";
// Peças compartilhadas das telas do Rebanho no app móvel:
// busca de um único animal, normalização sem acento e a lista de
// "animais recentes" guardada em localStorage.
import { useEffect, useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { fetchAnimais } from "@/lib/api";
import { fetchComCache } from "@/lib/offline";

export type AnimalMob = {
  numero: string;
  grupo_primario?: string | null;
  categoria_abrev?: string | null;
  del_dias?: number | null;
  ativo?: boolean;
};

/** minúsculas + sem acento, para busca tolerante. */
export function normalizar(s: unknown): string {
  return (s == null ? "" : String(s)).normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase().trim();
}

// ── Animais recentes (localStorage) ──────────────────────────────────────────
const CHAVE_RECENTES = "mob_animais_recentes";
export type Recente = { numero: string; categoria_abrev?: string | null; grupo_primario?: string | null };

export function lerRecentes(): Recente[] {
  try { return JSON.parse(localStorage.getItem(CHAVE_RECENTES) || "[]"); } catch { return []; }
}
export function registrarRecente(r: Recente) {
  try {
    const atuais = lerRecentes().filter((x) => x.numero !== r.numero);
    localStorage.setItem(CHAVE_RECENTES, JSON.stringify([r, ...atuais].slice(0, 5)));
  } catch { /* cheio/indisponível */ }
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
    fetchComCache<AnimalMob[]>("animais", () => fetchAnimais()).then(({ dados }) => {
      if (vivo && dados) setAnimais(dados);
    });
    return () => { vivo = false; };
  }, []);

  const filtrados = useMemo(() => {
    const q = normalizar(busca);
    if (!q) return [];
    return animais.filter((a) => normalizar(a.numero).includes(q)).slice(0, 25);
  }, [animais, busca]);

  const selecionado = animais.find((a) => a.numero === valor);

  if (valor) {
    return (
      <div className="mob-linha" style={{ cursor: "default", marginBottom: 0 }}>
        <span style={{ flex: 1, minWidth: 0 }}>
          <span style={{ display: "block", fontWeight: 700 }}>Brinco {valor}</span>
          {selecionado && <span style={{ display: "block", fontSize: "0.78rem", color: "var(--mob-muted)" }}>{subtituloAnimal(selecionado)}</span>}
        </span>
        <button type="button" onClick={() => { onEscolher(""); setBusca(""); }} aria-label="Trocar animal"
          style={{ width: 36, height: 36, borderRadius: 10, border: "1px solid var(--mob-border)", background: "var(--mob-surface)", color: "var(--mob-text)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, cursor: "pointer" }}>
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
          placeholder={placeholder} inputMode="numeric" autoComplete="off" />
      </div>
      {busca && (
        <div style={{ marginTop: "0.5rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
          {filtrados.map((a) => (
            <button key={a.numero} type="button" className="mob-linha" style={{ marginBottom: 0 }}
              onClick={() => { onEscolher(a.numero, a); setBusca(""); }}>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontWeight: 700 }}>Brinco {a.numero}</span>
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
