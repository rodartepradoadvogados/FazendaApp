"use client";
import { TabBar } from "@/components/ui";

const campoStyle: React.CSSProperties = {
  width: "100%", padding: "0.4rem 0.6rem", borderRadius: 6, fontSize: "0.85rem",
  background: "var(--surface-2)", border: "1px solid var(--border)", color: "var(--text)",
};

/**
 * Filtro de ciclos de 21 dias — data de referência (âncora), quantos ciclos,
 * categoria e se a âncora é o INÍCIO do primeiro ciclo (conta para frente) ou
 * o FIM do último (conta para trás). Extraído de app/ciclos-21-dias/page.tsx
 * para ser reaproveitado também no filtro "Por ciclo" de Histórico >
 * Reprodução (HistoricoServicos.tsx) — mesma UI, cálculo de janelas em
 * lib/ciclos21Dias.ts.
 */
export function FiltroCiclo21Dias({
  ancora, setAncora, modo, setModo, nCiclos, setNCiclos, categoria, setCategoria,
}: {
  ancora: string; setAncora: (v: string) => void;
  modo: "inicio" | "fim"; setModo: (v: "inicio" | "fim") => void;
  nCiclos: number; setNCiclos: (v: number) => void;
  categoria: string; setCategoria: (v: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
      <div>
        <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Data de referência</label>
        <input type="date" value={ancora} onChange={(e) => setAncora(e.target.value)} style={campoStyle} />
      </div>
      <div>
        <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Nº de ciclos</label>
        <input type="number" min={1} max={26} value={nCiclos}
          onChange={(e) => setNCiclos(Math.min(26, Math.max(1, Number(e.target.value) || 1)))} style={campoStyle} />
      </div>
      <div>
        <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Categoria</label>
        <select value={categoria} onChange={(e) => setCategoria(e.target.value)} style={campoStyle}>
          <option value="todas">Todas</option>
          <option value="vaca">Vacas</option>
          <option value="novilha">Novilhas</option>
        </select>
      </div>
      <div>
        <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>A data é o…</label>
        <TabBar<"inicio" | "fim">
          abas={[
            { id: "inicio", label: "Início", title: "A data escolhida é o primeiro dia do 1º ciclo — conta para frente" },
            { id: "fim", label: "Fim", title: "A data escolhida é o último dia do último ciclo — conta para trás" },
          ]}
          ativa={modo}
          onChange={setModo}
        />
      </div>
    </div>
  );
}
