"use client";
// Tela LANÇAR (lançamento rápido) do app de campo. Busca grande no topo que
// "fixa" um animal num chip; seis blocos grandes que abrem sub-telas com
// mini-formulários. Todo envio passa por enviarOuEnfileirar (offline-first).
import { useState } from "react";
import { Activity, Milk, Syringe, Wheat, Package, BarChart3, Search, X, ChevronRight, ExternalLink } from "lucide-react";
import { MobTitulo, MobBloco, MobVoltar } from "@/components/mobile/ui";
import { fetchAnimais, podeModulo } from "@/lib/api";
import { type Animal, useCache, filtrarAnimais, rotuloAnimal } from "./comum";
import { FormReprodutivo } from "./FormReprodutivo";
import { FormProducao } from "./FormProducao";
import { FormSanidade } from "./FormSanidade";
import { FormAlimentacao } from "./FormAlimentacao";
import { FormEstoque } from "./FormEstoque";

type Tela = "reprodutivo" | "producao" | "sanidade" | "alimentacao" | "estoque" | "financeiro";

const TITULOS: Record<Tela, string> = {
  reprodutivo: "Reprodutivo",
  producao: "Produção (leite)",
  sanidade: "Sanidade",
  alimentacao: "Alimentação",
  estoque: "Estoque",
  financeiro: "Financeiro",
};

export function LancarTela() {
  const animais = useCache<Animal[]>("animais", () => fetchAnimais() as Promise<Animal[]>, []);
  const [tela, setTela] = useState<Tela | null>(null);
  const [fixado, setFixado] = useState<Animal | null>(null);
  const podeFinanceiro = podeModulo("financeiro");

  // ── Sub-tela aberta ────────────────────────────────────────────────────────
  if (tela) {
    return (
      <div>
        <MobVoltar titulo={TITULOS[tela]} onVoltar={() => setTela(null)} />
        {tela === "reprodutivo" && <FormReprodutivo animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "producao" && <FormProducao animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "sanidade" && <FormSanidade animais={animais.dados} animalFixado={fixado?.numero || null} />}
        {tela === "alimentacao" && <FormAlimentacao />}
        {tela === "estoque" && <FormEstoque />}
        {tela === "financeiro" && <TelaFinanceiro />}
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
        <MobBloco icone={<Package size={24} />} label="Estoque" onClick={() => setTela("estoque")} />
        {podeFinanceiro && <MobBloco icone={<BarChart3 size={24} />} label="Financeiro" onClick={() => setTela("financeiro")} />}
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
        style={{ width: 36, height: 36, borderRadius: 10, border: "none", cursor: "pointer", background: "rgba(255,255,255,0.16)", color: "#FFFFFF", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
        <X size={18} />
      </button>
    </div>
  );
}

// ── Financeiro: só o atalho para o lançamento completo (complexo p/ o campo) ─
function TelaFinanceiro() {
  return (
    <div>
      <p style={{ color: "var(--mob-muted)", fontSize: "0.98rem", lineHeight: 1.5, marginBottom: "1.1rem" }}>
        O lançamento financeiro tem muitos campos (conta, centro de custo, parcelas) — melhor fazer no sistema completo.
      </p>
      <a href="/lancamentos" className="mob-btn" style={{ textDecoration: "none" }}>
        <ExternalLink size={18} /> Abrir lançamento financeiro completo
      </a>
    </div>
  );
}
