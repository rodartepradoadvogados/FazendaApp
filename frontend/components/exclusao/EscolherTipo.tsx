"use client";
// Etapa 1 — escolher o que apagar (Fase 2). Lista os tipos disponíveis com busca.
// O agrupamento por domínio (Fin/Reb/San/…) chega na Fase 3, junto com o endpoint
// /exclusoes/tipos enriquecido; aqui a lista plana já permite buscar e escolher.
import { useEffect, useMemo, useState } from "react";
import { fetchTiposExclusao } from "@/lib/api";
import type { Selecao } from "./useExclusao";

type Tipo = { id: string; label: string; sem_filtro_data: boolean };

export function EscolherTipo({ ocultarTipos, aoEscolher }: { ocultarTipos?: string[]; aoEscolher: (s: Selecao) => void }) {
  const [tipos, setTipos] = useState<Tipo[]>([]);
  const [termo, setTermo] = useState("");

  useEffect(() => {
    fetchTiposExclusao()
      .then((t: Tipo[]) => setTipos(ocultarTipos ? t.filter((x) => !ocultarTipos.includes(x.id)) : t))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const filtrados = useMemo(() => {
    const q = termo.trim().toLowerCase();
    return tipos.filter((t) => !q || t.label.toLowerCase().includes(q));
  }, [tipos, termo]);

  return (
    <section className="exc-escolher" aria-labelledby="exc-titulo">
      <h2 className="exc-h" id="exc-titulo">O que você quer apagar?</h2>
      <input
        className="exc-input"
        placeholder="Buscar um tipo…"
        value={termo}
        onChange={(e) => setTermo(e.target.value)}
        aria-label="Buscar tipo de registro"
        autoFocus
      />
      {filtrados.length === 0 && <p className="muted">Nenhum tipo encontrado.</p>}
      <ul className="exc-tipos">
        {filtrados.map((t) => (
          <li key={t.id}>
            <button className="exc-tipo" onClick={() => aoEscolher({ tipo: t.id, id: "", titulo: t.label })}>
              {t.label}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}