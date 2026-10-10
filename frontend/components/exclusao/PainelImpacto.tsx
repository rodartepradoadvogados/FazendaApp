"use client";
// Painel de impacto (Fase 2) — os 4 blocos: BLOQUEIA / SERÁ APAGADO /
// SERÁ REVERTIDO / AVISOS. Cada item mostra título + consequência em frase simples.
import { Ban, Trash2, Undo2, AlertTriangle } from "lucide-react";
import type { ImpactoExclusao, LinhaImpacto, BloqueioExclusao } from "@/lib/exclusao";

function BlocoLinhas({ icone, rotulo, sub, itens, classe, vazioTexto }: {
  icone: React.ReactNode; rotulo: string; sub: string; itens: LinhaImpacto[]; classe: string; vazioTexto?: string;
}) {
  if (itens.length === 0 && vazioTexto === undefined) return null;
  return (
    <div className={`exc-bloco ${classe}`}>
      <div className="exc-bloco-cab">
        <span className="exc-bloco-ic">{icone}</span>
        <div>
          <strong>{rotulo}</strong>
          <span className="muted">{sub}</span>
        </div>
        {itens.length > 0 && <span className="exc-bloco-n">{itens.length}</span>}
      </div>
      {itens.length === 0 ? (
        <p className="muted">{vazioTexto}</p>
      ) : (
        <ul className="exc-bloco-lista">
          {itens.map((l, i) => (
            <li key={i}>
              <span className="exc-linha-titulo">{l.titulo}</span>
              <span className="muted">{l.consequencia}</span>
              {l.chip && <span className="exc-chip">{l.chip}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function BlocoBloqueio({ itens }: { itens: BloqueioExclusao[] }) {
  if (itens.length === 0) return null;
  return (
    <div className="exc-bloco exc-bq">
      <div className="exc-bloco-cab">
        <span className="exc-bloco-ic"><Ban size={16} /></span>
        <div>
          <strong>Bloqueia</strong>
          <span className="muted">Impede de apagar enquanto você não resolver</span>
        </div>
        <span className="exc-bloco-n">{itens.length}</span>
      </div>
      <ul className="exc-bloco-lista">
        {itens.map((b, i) => (
          <li key={i}>
            <span className="exc-linha-titulo">{b.titulo}</span>
            <span className="muted">{b.motivo}</span>
            {b.fazer && <span className="muted exc-fazer">{b.fazer}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function PainelImpacto({ impacto }: { impacto: ImpactoExclusao }) {
  return (
    <div className="exc-painel" aria-live="polite">
      <h2 className="exc-h" tabIndex={-1}>Conferir antes de apagar</h2>
      <BlocoBloqueio itens={impacto.bloqueia ?? []} />
      <BlocoLinhas icone={<Trash2 size={16} />} rotulo="Será apagado" sub="Some do sistema e não volta" itens={impacto.apagar ?? []} classe="exc-ap" />
      <BlocoLinhas icone={<Undo2 size={16} />} rotulo="Será revertido" sub="É ajustado de volta" itens={impacto.reverter ?? []} classe="exc-rv" vazioTexto="Nada será revertido." />
      <BlocoLinhas icone={<AlertTriangle size={16} />} rotulo="Avisos" sub="Atenção" itens={impacto.avisos ?? []} classe="exc-av" vazioTexto="Sem avisos." />
    </div>
  );
}