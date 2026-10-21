"use client";
// Modo GRUPO: marca todos os pendentes e aplica de uma vez (o grupo não
// fecha: dá para incluir animais na hora e aplicar de novo). Ícone de origem
// em cada linha: veio pela janela × incluído manualmente × decisão no curral.
import { useMemo, useState } from "react";
import { Check } from "lucide-react";
import { OrigemIcone } from "@/components/sanitario/comum";
import type { AlvoDia } from "@/lib/sanitarioCampo";
import type { PacoteOffline } from "@/lib/sanitarioTipos";
import { FaixaSan } from "./comum";
import { Ultimos } from "./ModoTronco";
import type { ExecDia } from "./estadoExec";

export function ModoGrupo({ pacote, alvos, exec, filaIds, onAplicar, onDesfazer }: {
  pacote: PacoteOffline; alvos: AlvoDia[]; exec: ExecDia; filaIds: Set<string>;
  onAplicar: (alvos: AlvoDia[]) => Promise<void>;
  onDesfazer: (grupo: string) => Promise<string | null>;
}) {
  const [desmarcados, setDesmarcados] = useState<Set<string>>(() => new Set());
  const [aplicando, setAplicando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const nomes = useMemo(() => new Map(pacote.caixas.map((c) => [c.caixa_id, c.nome_curto || c.nome])), [pacote.caixas]);
  const sel = alvos.filter((a) => !desmarcados.has(a.animal));
  const doses = sel.reduce((s, a) => s + a.caixas.length, 0);
  const ultimos = useMemo(() => {
    const out: { grupo: string; numero: string; caixas: string[]; chaves: string[] }[] = [];
    for (const f of [...exec.feitos].reverse()) {
      let g = out.find((x) => x.grupo === f.grupo && x.numero === f.numero);
      if (!g) { if (out.length >= 3) continue; g = { grupo: f.grupo, numero: f.numero, caixas: [], chaves: [] }; out.push(g); }
      g.caixas.push(f.caixa); g.chaves.push(f.chave);
    }
    return out;
  }, [exec.feitos]);

  async function aplicar() {
    if (!sel.length || aplicando) return;
    setAplicando(true); setMsg(null);
    try {
      await onAplicar(sel);
      try { navigator.vibrate?.(20); } catch { /* sem vibração */ }
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Não foi possível guardar os registros.");
    } finally {
      setAplicando(false);
    }
  }

  if (!alvos.length) {
    return (
      <>
        <FaixaSan tipo="ok" role="status">Todos os animais deste dia foram registrados neste celular
          {exec.feitos.some((f) => filaIds.has(f.chave)) ? " (parte esperando sinal para enviar)" : ""}.</FaixaSan>
        <Ultimos ultimos={ultimos} filaIds={filaIds} onDesfazer={onDesfazer} />
      </>
    );
  }
  return (
    <div>
      <p className="mob-san-txt" style={{ marginTop: 0 }}>{pacote.caixas.map((c) => c.nome_curto || c.nome).join(" · ")}</p>
      <div style={{ display: "flex", gap: "0.5rem", margin: "0.6rem 0" }}>
        <button type="button" className="mob-btn-2" onClick={() => setDesmarcados(new Set())}>Marcar todos</button>
        <button type="button" className="mob-btn-2" onClick={() => setDesmarcados(new Set(alvos.map((a) => a.animal)))}>Desmarcar</button>
      </div>
      <div role="group" aria-label="Animais do grupo">
        {alvos.map((a) => (
          <label key={a.animal} className="mob-san-linha" data-estado={desmarcados.has(a.animal) ? undefined : "ok"}>
            <input type="checkbox" checked={!desmarcados.has(a.animal)} aria-label={`Aplicar em ${a.numero}`}
              onChange={() => setDesmarcados((s) => { const n = new Set(s); if (n.has(a.animal)) n.delete(a.animal); else n.add(a.animal); return n; })} />
            <OrigemIcone origem={a.origem} tamanho={16} />
            <span style={{ flex: 1, minWidth: 0 }}>
              <b style={{ fontSize: "1.15rem" }}>{a.numero}</b>{a.categoria ? ` · ${a.categoria}` : ""}
              <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>{a.caixas.map((c) => nomes.get(c)).join(" + ")}
                {a.semCadastro ? " · sem cadastro" : ""}</span>
            </span>
          </label>
        ))}
      </div>
      {msg && <FaixaSan tipo="alerta">{msg}</FaixaSan>}
      <button type="button" className="mob-btn mob-san-btn-acao" style={{ marginTop: "0.6rem" }} disabled={!sel.length || aplicando} onClick={aplicar}>
        <Check size={22} aria-hidden="true" /> {aplicando ? "Guardando…" : `Aplicar em ${sel.length} ${sel.length === 1 ? "animal" : "animais"} (${doses} ${doses === 1 ? "dose" : "doses"})`}
      </button>
      <Ultimos ultimos={ultimos} filaIds={filaIds} onDesfazer={onDesfazer} />
    </div>
  );
}
