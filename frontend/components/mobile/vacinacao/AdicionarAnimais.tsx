"use client";
// "Adicionar animais" no curral (app de campo). Funciona sem sinal: a lista e
// a regra de cada vacina/exame vêm do pacote offline do dia (calculadas pelo
// servidor). Quem está fora da regra pede consentimento com o motivo — nunca
// trava. Brinco sem cadastro também entra (o servidor registra "sem cadastro").
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { casaBusca } from "@/lib/busca";
import { chaveAnimal, foraDaRegra, type AnimalPacote, type ConsentLocal, type ExtraDia } from "@/lib/sanitarioCampo";
import type { PacoteOffline } from "@/lib/sanitarioTipos";
import { ConsentimentoCampo, FaixaSan, Rotulo, type ParFora } from "./comum";

export function AdicionarAnimais({ pacote, jaNoDia, onConfirmar, onVoltar }: {
  pacote: PacoteOffline;
  /** chaves "a:<id>" de quem já está no dia com todas as caixas */
  jaNoDia: Set<string>;
  onConfirmar: (extras: ExtraDia[]) => void;
  onVoltar: () => void;
}) {
  const caixas = pacote.caixas;
  const [busca, setBusca] = useState("");
  const [lote, setLote] = useState("");
  const [cat, setCat] = useState("");
  const [marc, setMarc] = useState<Set<number>>(() => new Set());
  const [semCadastro, setSemCadastro] = useState<string[]>([]);
  const [cxSel, setCxSel] = useState<Set<number>>(() => new Set(caixas.map((c) => c.caixa_id)));
  const [consentir, setConsentir] = useState<ParFora[] | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const nomeCx = useMemo(() => new Map(caixas.map((c) => [c.caixa_id, c.nome_curto || c.nome])), [caixas]);
  const porId = useMemo(() => new Map(pacote.animais.map((a) => [a.animal_id, a])), [pacote.animais]);
  const lotes = useMemo(() => [...new Set(pacote.animais.map((a) => a.lote).filter(Boolean) as string[])].sort(), [pacote.animais]);
  const cats = useMemo(() => [...new Set(pacote.animais.map((a) => a.categoria).filter(Boolean) as string[])].sort(), [pacote.animais]);
  const visiveis = useMemo(() => pacote.animais.filter((a) => !jaNoDia.has(chaveAnimal(a.animal_id, a.brinco))
    && (!busca.trim() || casaBusca(a.brinco, busca)) && (!lote || a.lote === lote) && (!cat || a.categoria === cat)).slice(0, 80),
  [pacote.animais, jaNoDia, busca, lote, cat]);
  const exato = busca.trim() && pacote.animais.some((a) => a.brinco.trim().toLowerCase() === busca.trim().toLowerCase());

  function alternar(id: number) {
    setMarc((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });
    setAviso(null);
  }
  function montar(aceitos: Set<string> | null, cons: Record<string, ConsentLocal>): ExtraDia[] {
    const cxs = [...cxSel];
    const out: ExtraDia[] = [];
    for (const id of marc) {
      const a = porId.get(id) as AnimalPacote;
      const fora = new Map(foraDaRegra(a, cxs).map((f) => [f.caixa_id, f.motivo]));
      const ok = cxs.filter((c) => !fora.has(c) || (aceitos?.has(`${id}|${c}`) ?? false));
      if (!ok.length) continue;
      const consent: Record<string, ConsentLocal> = {};
      for (const c of ok) if (fora.has(c)) consent[String(c)] = cons[`${id}|${c}`];
      out.push({ animal_id: id, numero: a.brinco, caixas: ok, consent });
    }
    for (const n of semCadastro) out.push({ animal_id: null, numero: n, caixas: cxs, consent: {} });
    return out;
  }
  function continuar() {
    if (!marc.size && !semCadastro.length) { setAviso("Marque ao menos um animal."); return; }
    if (!cxSel.size) { setAviso("Escolha ao menos uma vacina/exame."); return; }
    const pares: ParFora[] = [];
    for (const id of marc) {
      const a = porId.get(id);
      for (const f of foraDaRegra(a, [...cxSel])) {
        pares.push({ chave: `${id}|${f.caixa_id}`, numero: a?.brinco || String(id), caixa: nomeCx.get(f.caixa_id) || "", motivo: f.motivo });
      }
    }
    if (pares.length) { setConsentir(pares); return; }
    onConfirmar(montar(null, {}));
  }

  if (consentir) {
    const semAtestado = caixas.some((c) => cxSel.has(c.caixa_id) && !(c.regras as { tem_atestado?: boolean }).tem_atestado);
    return (
      <ConsentimentoCampo itens={consentir} perguntarAtestado={semAtestado} texto={pacote.regras_aviso?.texto_consentimento}
        onVoltar={() => setConsentir(null)}
        onConfirmar={(r) => {
          const cons: Record<string, ConsentLocal> = {};
          for (const k of r.aceitos) {
            const p = consentir.find((x) => x.chave === k)!;
            cons[k] = { aceito: true, motivo_exibido: p.motivo, quer_atestado: r.quer_atestado, atestado_destinatario: r.destinatario };
          }
          const extras = montar(new Set(r.aceitos), cons);
          if (!extras.length) { setConsentir(null); setAviso("Nenhum animal ficou para incluir."); return; }
          onConfirmar(extras);
        }} />
    );
  }

  return (
    <div>
      <Rotulo>Vacinas/exames para os incluídos</Rotulo>
      <div className="mob-san-chips">
        {caixas.map((c) => (
          <button key={c.caixa_id} type="button" className="mob-san-chip" aria-pressed={cxSel.has(c.caixa_id)}
            onClick={() => setCxSel((p) => { const n = new Set(p); if (n.has(c.caixa_id)) n.delete(c.caixa_id); else n.add(c.caixa_id); return n; })}>
            <span>{c.nome_curto || c.nome}</span>
          </button>
        ))}
      </div>
      <Rotulo>Buscar brinco</Rotulo>
      <div style={{ position: "relative" }}>
        <Search size={18} aria-hidden="true" style={{ position: "absolute", left: 12, top: "50%", transform: "translateY(-50%)", color: "var(--mob-muted)" }} />
        <input className="mob-input" style={{ paddingLeft: "2.6rem" }} inputMode="numeric" value={busca} autoComplete="off"
          onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 2401" aria-label="Buscar brinco" />
      </div>
      <div className="mob-san-dupla">
        <select className="mob-input" value={lote} onChange={(e) => setLote(e.target.value)} aria-label="Lote">
          <option value="">Todos os lotes</option>
          {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
        </select>
        <select className="mob-input" value={cat} onChange={(e) => setCat(e.target.value)} aria-label="Categoria">
          <option value="">Todas as categorias</option>
          {cats.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      {busca.trim() && !exato && !semCadastro.includes(busca.trim()) && (
        <button type="button" className="mob-btn-2" style={{ marginTop: "0.6rem" }}
          onClick={() => { setSemCadastro((p) => [...p, busca.trim()]); setBusca(""); }}>
          Brinco {busca.trim()} sem cadastro: incluir assim
        </button>
      )}
      {semCadastro.length > 0 && (
        <FaixaSan tipo="atencao">Sem cadastro: {semCadastro.join(", ")}. Fica registrado pelo brinco.{" "}
          <button type="button" className="mob-btn-2" style={{ marginTop: "0.4rem" }} onClick={() => setSemCadastro([])}>Tirar</button>
        </FaixaSan>
      )}
      <div style={{ marginTop: "0.7rem" }} role="group" aria-label="Animais">
        {visiveis.map((a) => {
          const fora = foraDaRegra(a, [...cxSel]);
          return (
            <label key={a.animal_id} className="mob-san-linha" data-estado={fora.length ? "atencao" : "ok"}>
              <input type="checkbox" checked={marc.has(a.animal_id)} onChange={() => alternar(a.animal_id)} aria-label={`Incluir ${a.brinco}`} />
              <span style={{ flex: 1, minWidth: 0 }}>
                <b style={{ fontSize: "1.1rem" }}>{a.brinco}</b> · {a.categoria || "—"}{a.lote ? ` · ${a.lote}` : ""}
                <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>
                  {fora.length ? fora.map((f) => `${nomeCx.get(f.caixa_id)}: fora (${f.motivo})`).join(" · ") : "na regra"}
                </span>
              </span>
            </label>
          );
        })}
        {!visiveis.length && <p className="mob-san-txt">Nenhum animal com esses filtros.</p>}
      </div>
      {aviso && <FaixaSan tipo="alerta">{aviso}</FaixaSan>}
      <div className="mob-san-dupla" style={{ position: "sticky", bottom: 0, background: "var(--mob-surface)", paddingTop: "0.5rem" }}>
        <button type="button" className="mob-btn-2" onClick={onVoltar}>Cancelar</button>
        <button type="button" className="mob-btn" onClick={continuar}>Incluir ({marc.size + semCadastro.length})</button>
      </div>
    </div>
  );
}
