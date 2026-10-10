"use client";
// Etapa 2 — encontrar o registro e ver o impacto (Fase 2). Busca dentro do tipo
// escolhido, seleciona e chama /impacto para trazer o Impacto estruturado.
import { useEffect, useState } from "react";
import { buscarExclusao, impactoExclusao } from "@/lib/api";
import type { ImpactoExclusao } from "@/lib/exclusao";

type Candidato = { id: string; titulo: string; subtitulo: string; tipo_real?: string };

export function ListaResultados({ tipo, titulo, aoImpacto, aoErro }: {
  tipo: string;
  titulo: string;
  aoImpacto: (i: ImpactoExclusao) => void;
  aoErro: (m: string) => void;
}) {
  const [termo, setTermo] = useState("");
  const [resultados, setResultados] = useState<Candidato[]>([]);
  const [buscando, setBuscando] = useState(false);
  const [carregando, setCarregando] = useState(false);

  const buscar = async (termoAtual: string) => {
    setBuscando(true);
    try { setResultados(await buscarExclusao(tipo, termoAtual)); }
    catch (e: any) { aoErro(e.message); }
    finally { setBuscando(false); }
  };

  const escolherAlvo = async (cand: Candidato) => {
    setCarregando(true);
    try { aoImpacto((await impactoExclusao(tipo, cand.id)) as ImpactoExclusao); }
    catch (e: any) { aoErro(e.message); }
    finally { setCarregando(false); }
  };

  useEffect(() => { buscar(termo); /* eslint-disable-line react-hooks/exhaustive-deps */ }, [tipo]);

  return (
    <section className="exc-busca" aria-label={`Buscar ${titulo}`}>
      <h2 className="exc-h">{titulo}</h2>
      <div className="exc-busca-linha">
        <input className="exc-input" placeholder="Buscar…" value={termo} onChange={(e) => setTermo(e.target.value)} aria-label="Buscar registro" />
        <button className="btn-primary" onClick={() => buscar(termo)} disabled={buscando}>{buscando ? "Buscando…" : "Buscar"}</button>
      </div>
      {carregando && <p className="muted">Calculando o impacto…</p>}
      {resultados.length === 0 && !buscando && <p className="muted">Nada encontrado.</p>}
      <ul className="exc-resultados">
        {resultados.map((r) => (
          <li key={r.id}>
            <button className="exc-resultado" onClick={() => escolherAlvo(r)}>
              <span className="exc-resultado-titulo">{r.titulo}</span>
              <span className="muted">{r.subtitulo}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}