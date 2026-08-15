"use client";
import { useMemo, useRef, useState } from "react";
import { casaBusca } from "@/lib/busca";

export type TouroPickerItem = {
  naab?: string | null;
  nome: string;
  central?: string | null;
  raca?: string | null;
  tpi?: number | null;
  doses?: number | null;
};

const LIMITE_LISTA = 200;

/**
 * Campo de busca de touro — ao clicar/focar, abre a lista completa (ou a
 * filtrada, conforme digitação) logo abaixo, em vez de exigir texto livre
 * decorado. Continua aceitando digitação livre (ex.: touro da fazenda que
 * não está no catálogo NAAB importado) — selecionar um item da lista só
 * preenche os campos automaticamente por conveniência.
 */
export function TouroPicker({ itens, value, onChangeTexto, onSelecionar, placeholder, style, className, autoFocus }: {
  itens: TouroPickerItem[];
  value: string;
  onChangeTexto: (v: string) => void;
  onSelecionar: (item: TouroPickerItem) => void;
  placeholder?: string;
  style?: React.CSSProperties;
  className?: string;
  autoFocus?: boolean;
}) {
  const [aberto, setAberto] = useState(false);
  const blurTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  const filtrados = useMemo(() => {
    const base = itens.filter((t) =>
      casaBusca(`${t.nome} ${t.naab || ""} ${t.central || ""} ${t.raca || ""}`, value));
    return base.slice(0, LIMITE_LISTA);
  }, [itens, value]);

  return (
    <div style={{ position: "relative" }}>
      <input
        autoFocus={autoFocus}
        value={value}
        onChange={(e) => onChangeTexto(e.target.value)}
        onFocus={() => setAberto(true)}
        onBlur={() => { blurTimeout.current = setTimeout(() => setAberto(false), 150); }}
        placeholder={placeholder || "Buscar touro (nome, NAAB, central)…"}
        style={style}
        className={className}
      />
      {aberto && (
        <div
          onMouseDown={(e) => { if (blurTimeout.current) clearTimeout(blurTimeout.current); e.preventDefault(); }}
          style={{
            position: "absolute", zIndex: 60, top: "100%", left: 0, right: 0, marginTop: "0.25rem",
            background: "var(--surface)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)",
            maxHeight: "16rem", overflowY: "auto", boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
          }}
        >
          {filtrados.length === 0 && (
            <div style={{ padding: "0.6rem 0.7rem", color: "var(--text-muted)", fontSize: "0.78rem" }}>
              Nenhum touro do catálogo encontrado — pode digitar livremente (ex.: touro da fazenda).
            </div>
          )}
          {filtrados.map((t, i) => (
            <div
              key={`${t.naab || t.nome}-${i}`}
              onClick={() => { onSelecionar(t); setAberto(false); }}
              className="row-clickable"
              style={{
                padding: "0.4rem 0.7rem", cursor: "pointer", fontSize: "0.8rem",
                borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between",
                alignItems: "center", gap: "0.6rem",
              }}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                <strong>{t.nome}</strong>
                {t.naab && <span style={{ color: "var(--text-muted)" }}> · {t.naab}</span>}
                {t.central && <span style={{ color: "var(--text-muted)" }}> · {t.central}</span>}
              </span>
              {t.doses != null ? (
                <span style={{ color: "var(--text-muted)", flexShrink: 0, fontSize: "0.74rem" }}>{t.doses} dose(s)</span>
              ) : t.tpi != null ? (
                <span style={{ color: "var(--dourado-light)", fontWeight: 700, flexShrink: 0, fontSize: "0.74rem" }}>TPI {t.tpi}</span>
              ) : null}
            </div>
          ))}
          {itens.length > LIMITE_LISTA && filtrados.length === LIMITE_LISTA && (
            <div style={{ padding: "0.4rem 0.7rem", color: "var(--text-muted)", fontSize: "0.7rem" }}>
              Mostrando {LIMITE_LISTA} de {itens.length} — refine a busca para ver mais.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
