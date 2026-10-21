"use client";
// Pop-up de SELEÇÃO MÚLTIPLA de animais do sanitário (site; o app de campo
// reaproveita a lógica): busca por brinco, filtros de lote e categoria,
// "marcar todos os visíveis" e, quando a tela informa as vacinas/exames em
// jogo, a coluna "na regra / fora: motivo" (vem do back via `checar`).
// Quem está fora pode ser escolhido: a tela que chamou abre o pop-up de
// consentimento depois (nunca trava).
import { useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Modal } from "@/components/Modal";
import { fetchAnimais } from "@/lib/api";
import { casaBusca } from "@/lib/busca";
import { mensagemDoErro } from "@/lib/apiSanitario";
import { diferencaDias, hojeISO, idadeTexto } from "@/lib/sanitarioTipos";
import { Faixa } from "./comum";

export type AnimalSan = {
  id: number; numero: string; lote: string | null; categoria: string | null; sexo: string | null; data_nasc: string | null;
};
export type Elegibilidade = { ok: boolean; texto: string | null };

type LinhaApi = {
  id: number; numero: string; grupo_primario?: string | null; categoria_completa?: string | null; categoria_abrev?: string | null;
  sexo?: string | null; data_nasc?: string | null; eh_semen?: boolean; ativo?: boolean;
};

// Lista de animais ativos (machos incluídos — a regra de cada vacina decide),
// guardada por 60 s para os pop-ups da mesma tela não buscarem de novo.
let _cache: { em: number; p: Promise<AnimalSan[]> } | null = null;
export function carregarAnimaisSan(forcar = false): Promise<AnimalSan[]> {
  const agora = Date.now();
  if (!forcar && _cache && agora - _cache.em < 60000) return _cache.p;
  const p = (fetchAnimais({ incluirMachos: true }) as Promise<LinhaApi[]>).then((rows) => rows
    .filter((a) => !a.eh_semen && a.ativo !== false && typeof a.id === "number")
    .map((a) => ({
      id: a.id, numero: a.numero, lote: a.grupo_primario ?? null, categoria: a.categoria_completa || a.categoria_abrev || null,
      sexo: a.sexo ?? null, data_nasc: a.data_nasc ?? null,
    }))
    .sort((x, y) => x.numero.localeCompare(y.numero, undefined, { numeric: true })));
  _cache = { em: agora, p };
  p.catch(() => { _cache = null; });
  return p;
}

export function SeletorAnimais({
  titulo = "Escolher animais", subtitulo, jaSelecionados = [], excluir = [], rotuloOk = "Usar",
  checar, onConfirmar, onFechar,
}: {
  titulo?: string;
  subtitulo?: string;
  /** IDs já marcados ao abrir. */
  jaSelecionados?: number[];
  /** IDs que não aparecem (ex.: já estão no dia). */
  excluir?: number[];
  rotuloOk?: string;
  /** Opcional: confere a regra das vacinas/exames em jogo (o back responde). */
  checar?: (ids: number[]) => Promise<Map<number, Elegibilidade>>;
  onConfirmar: (ids: number[], animais: AnimalSan[]) => void;
  onFechar: () => void;
}) {
  const [animais, setAnimais] = useState<AnimalSan[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [eleg, setEleg] = useState<Map<number, Elegibilidade> | null>(null);
  const [erroEleg, setErroEleg] = useState<string | null>(null);
  const [busca, setBusca] = useState("");
  const [lote, setLote] = useState("");
  const [cat, setCat] = useState("");
  const [soNaRegra, setSoNaRegra] = useState(false);
  const [marc, setMarc] = useState<Set<number>>(() => new Set(jaSelecionados));
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    carregarAnimaisSan()
      .then((l) => {
        if (!vivo) return;
        setAnimais(l);
        if (checar) {
          checar(l.map((a) => a.id))
            .then((m) => { if (vivo) setEleg(m); })
            .catch((e) => { if (vivo) setErroEleg(mensagemDoErro(e, "Não foi possível conferir a regra agora.")); });
        }
      })
      .catch((e) => { if (vivo) setErro(mensagemDoErro(e, "Não foi possível carregar os animais.")); });
    return () => { vivo = false; };
    // abre uma vez; `checar` é fixo enquanto o pop-up está aberto
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fora = useMemo(() => new Set(excluir), [excluir]);
  const lotes = useMemo(() => [...new Set((animais || []).map((a) => a.lote).filter(Boolean) as string[])].sort(), [animais]);
  const cats = useMemo(() => [...new Set((animais || []).map((a) => a.categoria).filter(Boolean) as string[])].sort(), [animais]);
  const hoje = hojeISO();
  const visiveis = useMemo(() => (animais || []).filter((a) => !fora.has(a.id)
    && (!busca.trim() || casaBusca(a.numero, busca))
    && (!lote || a.lote === lote) && (!cat || a.categoria === cat)
    && (!soNaRegra || !eleg || eleg.get(a.id)?.ok)), [animais, fora, busca, lote, cat, soNaRegra, eleg]);

  function alternar(id: number) {
    setMarc((p) => { const n = new Set(p); if (n.has(id)) n.delete(id); else n.add(id); return n; });
    setAviso(null);
  }
  function confirmar() {
    if (!marc.size) { setAviso("Marque ao menos um animal."); return; }
    const ids = [...marc];
    onConfirmar(ids, (animais || []).filter((a) => marc.has(a.id)));
  }

  return (
    <Modal title={titulo} onClose={onFechar} width="760px" zIndex={110}>
      <div className="san-modal-corpo">
        <p className="san-modal-sub">{subtitulo || "Busque, filtre e marque vários."}</p>
        <div className="san-linha">
          <div className="san-campo">
            <label htmlFor="saBusca">Buscar brinco</label>
            <div style={{ position: "relative" }}>
              <Search size={14} aria-hidden="true" style={{ position: "absolute", left: 9, top: 11, color: "var(--text-muted)" }} />
              <input id="saBusca" className="san-input" style={{ paddingLeft: 28 }} type="search" inputMode="numeric"
                value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="ex.: 24" autoComplete="off" />
            </div>
          </div>
          <div className="san-campo medio">
            <label htmlFor="saLote">Lote</label>
            <select id="saLote" className="san-input" value={lote} onChange={(e) => setLote(e.target.value)}>
              <option value="">Todos os lotes</option>
              {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </div>
          <div className="san-campo medio">
            <label htmlFor="saCat">Categoria</label>
            <select id="saCat" className="san-input" value={cat} onChange={(e) => setCat(e.target.value)}>
              <option value="">Todas</option>
              {cats.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>
        </div>
        {checar && (
          <label className="san-liga" style={{ padding: 0 }}>
            <input type="checkbox" checked={soNaRegra} onChange={(e) => setSoNaRegra(e.target.checked)} disabled={!eleg} />
            <span>Mostrar só quem está na regra{!eleg && !erroEleg ? " (conferindo…)" : ""}</span>
          </label>
        )}
        {erroEleg && <Faixa tipo="atencao">{erroEleg} Você ainda pode escolher; o sistema confere ao gravar.</Faixa>}
        {erro ? <Faixa tipo="alerta">{erro}</Faixa> : !animais ? (
          <div className="skeleton" style={{ height: "14rem" }} role="status" aria-label="Carregando animais" />
        ) : (
          <div className="san-lista-sel" role="group" aria-label="Animais">
            {visiveis.length ? visiveis.map((a) => {
              const e = eleg?.get(a.id);
              const idade = a.data_nasc ? idadeTexto(diferencaDias(a.data_nasc.slice(0, 10), hoje)) : "—";
              return (
                <label key={a.id} className={marc.has(a.id) ? "marcado" : undefined}>
                  <input type="checkbox" checked={marc.has(a.id)} onChange={() => alternar(a.id)} aria-label={`Selecionar ${a.numero}`} />
                  <b className="san-num">{a.numero}</b>
                  <span>{a.categoria || "—"} · {a.lote || "sem lote"}<br /><span className="san-nota">{a.sexo === "M" ? "macho" : "fêmea"} · {idade}</span></span>
                  <span className={`st ${e ? (e.ok ? "ok" : "fora") : ""}`}>
                    {checar ? (e ? (e.ok ? "na regra" : `fora: ${e.texto || "não cumpre a regra"}`) : eleg ? "—" : "") : ""}
                  </span>
                </label>
              );
            }) : <div className="san-bloco-corpo san-nota">Nenhum animal com esses filtros.</div>}
          </div>
        )}
        {aviso && <p className="san-erro-txt" role="alert" style={{ margin: 0 }}>{aviso}</p>}
      </div>
      <div className="san-modal-rodape">
        <button type="button" className="btn-ghost esq" onClick={() => {
          setMarc((p) => { const n = new Set(p); visiveis.forEach((a) => n.add(a.id)); return n; });
        }} disabled={!visiveis.length}>Marcar todos os visíveis</button>
        {marc.size > 0 && <button type="button" className="btn-ghost" onClick={() => setMarc(new Set())}>Limpar</button>}
        <button type="button" className="btn-ghost" onClick={onFechar}>Cancelar</button>
        <button type="button" className="btn-primary-gold" onClick={confirmar}>{rotuloOk} ({marc.size})</button>
      </div>
    </Modal>
  );
}
