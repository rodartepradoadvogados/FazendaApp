"use client";
// Tela LANÇAR (lançamento rápido) do app de campo. Busca grande no topo que
// "fixa" um animal num chip; seis blocos grandes que abrem sub-telas com
// mini-formulários. Todo envio passa por enviarOuEnfileirar (offline-first).
import { useState } from "react";
import { Activity, Milk, Syringe, Wheat, ArrowLeftRight, Skull, Search, X, ChevronRight } from "lucide-react";
import { MobTitulo, MobBloco, MobVoltar } from "@/components/mobile/ui";
import { fetchAnimais } from "@/lib/api";
import { type Animal, useCache, filtrarAnimais, rotuloAnimal } from "./comum";
import { FormReprodutivo } from "./FormReprodutivo";
import { FormProducao } from "./FormProducao";
import { FormSanidade } from "./FormSanidade";
import { FormAlimentacao } from "./FormAlimentacao";
import Movimentar from "@/components/mobile/rebanho/Movimentar";
import Baixar from "@/components/mobile/rebanho/Baixar";

type Tela = "reprodutivo" | "producao" | "sanidade" | "alimentacao" | "movimentar" | "baixar";

const TITULOS: Record<Tela, string> = {
  reprodutivo: "Reprodutivo",
  producao: "Produção (leite)",
  sanidade: "Sanidade",
  alimentacao: "Alimentação",
  movimentar: "Movimentar animais",
  baixar: "Baixar animal",
};

export function LancarTela() {
  const animais = useCache<Animal[]>("animais", () => fetchAnimais() as Promise<Animal[]>, []);
  const [tela, setTela] = useState<Tela | null>(null);
  const [fixado, setFixado] = useState<Animal | null>(null);

  // ── Sub-tela aberta ────────────────────────────────────────────────────────
  if (tela) {
    return (
      <div>
        <MobVoltar titulo={TITULOS[tela]} onVoltar={() => setTela(null)} />
        {tela === "reprodutivo" && <FormReprodutivo animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "producao" && <FormProducao animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "sanidade" && <FormSanidade animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "alimentacao" && <FormAlimentacao />}
        {tela === "movimentar" && <Movimentar />}
        {tela === "baixar" && <Baixar />}
      </div>
    );
  }

  // ── Tela principal ─────────────────────────────────────────────────────────
  return (
    <div>
      <MobTitulo>Lançamento Rápido</MobTitulo>

      {fixado
        ? <ChipAnimal animal={fixado} onSoltar={() => setFixado(null)} />
        : <BuscaAnimal animais={animais.dados} onEscolher={setFixado} />}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem", marginTop: "0.4rem" }}>
        <MobBloco icone={<Activity size={24} />} label="Reprodutivo" destaque onClick={() => setTela("reprodutivo")} />
        <MobBloco icone={<Milk size={24} />} label="Produção (Leite)" onClick={() => setTela("producao")} />
        <MobBloco icone={<Syringe size={24} />} label="Sanidade" onClick={() => setTela("sanidade")} />
        <MobBloco icone={<Wheat size={24} />} label="Alimentação" onClick={() => setTela("alimentacao")} />
        <MobBloco icone={<ArrowLeftRight size={24} />} label="Movimentar" onClick={() => setTela("movimentar")} />
        <MobBloco icone={<Skull size={24} />} label="Baixar animal" onClick={() => setTela("baixar")} />
      </div>
    </div>
  );
}

// ── Busca grande do topo ───────────────────────────────────────────────────
function BuscaAnimal({ animais, onEscolher }: { animais: Animal[]; onEscolher: (a: Animal) => void }) {
  const [q, setQ] = useState("");
  const resultados = q.trim() ? filtrarAnimais(animais, q).slice(0, 8) : [];
  return (
    <div style={{ marginBottom: "1.1rem" }}>
      <div style={{ position: "relative" }}>
        <Search size={19} style={{ position: "absolute", left: 13, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)", pointerEvents: "none" }} />
        <input className="mob-input" value={q} onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar brinco ou lote…" style={{ paddingLeft: "2.6rem", fontSize: "1.05rem" }} />
      </div>
      {q.trim() !== "" && (
        <div style={{ marginTop: "0.5rem", display: "grid", gap: "0.5rem" }}>
          {resultados.map((a) => (
            <button key={a.numero} type="button" className="mob-linha" onClick={() => { onEscolher(a); setQ(""); }}>
              <span style={{ flex: 1, minWidth: 0 }}>
                <span style={{ display: "block", fontWeight: 700 }}>{a.numero}</span>
                {rotuloAnimal(a) && <span style={{ display: "block", fontSize: "0.82rem", color: "var(--mob-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{rotuloAnimal(a)}</span>}
              </span>
              <ChevronRight size={18} style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
            </button>
          ))}
          {resultados.length === 0 && <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem", padding: "0.2rem 0.1rem" }}>Nenhum animal encontrado.</p>}
        </div>
      )}
    </div>
  );
}

// ── Chip do animal fixado ──────────────────────────────────────────────────
function ChipAnimal({ animal, onSoltar }: { animal: Animal; onSoltar: () => void }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1.1rem",
      padding: "0.7rem 0.8rem 0.7rem 1rem", borderRadius: 14,
      background: "var(--mob-vinho)", color: "#FFFFFF",
    }}>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "block", fontWeight: 800, fontSize: "1rem" }}>{animal.numero}</span>
        {rotuloAnimal(animal) && <span style={{ display: "block", fontSize: "0.8rem", opacity: 0.85, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{rotuloAnimal(animal)}</span>}
      </span>
      <button type="button" onClick={onSoltar} aria-label="Soltar animal"
        style={{ width: 44, height: 44, borderRadius: 10, border: "none", cursor: "pointer", background: "rgba(255,255,255,0.16)", color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <X size={18} />
      </button>
    </div>
  );
}
