"use client";
// Plano › Orçamento › planilha: uma linha por conta (e centro), um mês por
// coluna. Copiar o ano anterior (+x%), aplicar x% em tudo, preencher os 12 meses
// de uma linha, incluir/tirar conta. Os totais de receitas, despesas e
// resultado se refazem na hora (é a planilha que a pessoa está digitando, não o
// relatório); salvar manda só as células que mudaram (PUT /planejamento/orcamento-grade).
import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { AlertTriangle, Copy, Percent, Plus, Save, Undo2, X } from "lucide-react";
import { fetchPlanoContas } from "@/lib/api";
import { fetchItensOrcamento, salvarGradeOrcamento } from "@/lib/apiPlano";
import { MESES_CURTOS, MESES_LONGOS, num } from "@/lib/relatorioContexto";
import {
  aplicarPercentual, celulasAlteradas, chaveGrade, copiarAnoAnterior, lerValor, montarGrade, ordenarGrade, preencherLinha, totaisGrade,
  type ItemOrcamento, type LinhaGrade,
} from "@/lib/relatorioOrcamento";
import type { ContaPlano } from "@/lib/contaGerencial";

export type AcaoInicialGrade = { tipo: "copiar" } | { tipo: "incluir"; codigo: string; nome: string; tipoConta: "receita" | "despesa"; centro: string | null } | null;

const fmt = (v: number) => num(v, Number.isInteger(v) ? 0 : 2);
const somaAno = (xs: number[]) => Math.round(xs.reduce((s, v) => s + v, 0) * 100) / 100;

export function GradeOrcamento({ ano, cc, centros, acaoInicial, onSalvo }: {
  ano: number; cc: string; centros: string[]; acaoInicial: AcaoInicialGrade; onSalvo: () => void;
}) {
  const [original, setOriginal] = useState<LinhaGrade[] | null>(null);
  const [atual, setAtual] = useState<LinhaGrade[]>([]);
  const [anterior, setAnterior] = useState<LinhaGrade[]>([]);
  const [plano, setPlano] = useState<ContaPlano[]>([]);
  const [textos, setTextos] = useState<Record<string, string>>({});
  const [erro, setErro] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [pct, setPct] = useState("5");
  const [novo, setNovo] = useState<{ codigo: string; tipo: "receita" | "despesa"; centro: string }>({ codigo: "", tipo: "despesa", centro: cc === "todos" ? "" : cc });
  const [preencher, setPreencher] = useState<{ chave: string; valor: string }>({ chave: "", valor: "" });
  const tabela = useRef<HTMLTableElement>(null);
  const acaoFeita = useRef(false);
  const visivel = (l: LinhaGrade) => cc === "todos" || l.centro === cc;
  // O nome da conta vem com o item (GET /planejamento/orcamento devolve nome_conta_gerencial).
  // A ação vinda do relatório ("Copiar o orçamento de…", "Incluir no orçamento") vale uma vez, na 1ª leitura.
  const aplicarLeitura = useMemo(() => ([a, b]: [ItemOrcamento[], ItemOrcamento[]]) => {
    const g = montarGrade(a), ant = montarGrade(b);
    let inicial = g;
    if (acaoInicial && !acaoFeita.current) {
      acaoFeita.current = true;
      const antVisivel = ant.filter((l) => cc === "todos" || l.centro === cc);
      if (acaoInicial.tipo === "copiar" && antVisivel.length) {
        inicial = copiarAnoAnterior(g, antVisivel, 0);
        setAviso(`Orçamento de ${ano - 1} copiado para ${ano}. Confira e salve.`);
      } else if (acaoInicial.tipo === "incluir") {
        const k = chaveGrade(acaoInicial.codigo, acaoInicial.centro);
        if (!g.some((l) => l.chave === k)) {
          inicial = ordenarGrade([...g, { chave: k, codigo: acaoInicial.codigo, centro: acaoInicial.centro, tipo: acaoInicial.tipoConta, nome: acaoInicial.nome,
            valores: Array(12).fill(0), itensPorMes: Array(12).fill(0) }]);
        }
        setAviso(`${acaoInicial.nome} entrou na planilha: preencha os meses e salve.`);
      }
    }
    setOriginal(g); setAtual(inicial); setAnterior(ant); setTextos({}); setErro(null);
  }, [ano, cc, acaoInicial]);
  const lerItens = useMemo(() => () => Promise.all([fetchItensOrcamento(ano), fetchItensOrcamento(ano - 1)]), [ano]);

  useEffect(() => { fetchPlanoContas().then((p: ContaPlano[]) => setPlano(p.filter((c) => c.ativa !== false))).catch(() => {}); }, []);
  useEffect(() => {
    let vivo = true;
    lerItens().then((x) => { if (vivo) aplicarLeitura(x); }).catch((e) => { if (vivo) setErro((e as Error).message); });
    return () => { vivo = false; };
  }, [lerItens, aplicarLeitura]);
  const anteriorVisivel = anterior.filter(visivel);

  const alteradas = useMemo(() => (original ? celulasAlteradas(original, atual) : []), [original, atual]);
  const sujo = alteradas.length > 0;
  useEffect(() => {
    if (!sujo) return;
    const aviso = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", aviso);
    return () => window.removeEventListener("beforeunload", aviso);
  }, [sujo]);

  const linhas = atual.filter(visivel);
  const tot = totaisGrade(linhas);
  const mudou = (l: LinhaGrade, m: number) => {
    const o = original?.find((x) => x.chave === l.chave);
    return Math.abs((o ? o.valores[m] : 0) - l.valores[m]) >= 0.005;
  };

  const confirmar = (l: LinhaGrade, m: number, texto: string) => {
    const k = `${l.chave}#${m}`;
    const v = lerValor(texto);
    if (v == null) { setTextos((t) => ({ ...t, [k]: texto })); return false; }
    setTextos((t) => { const n = { ...t }; delete n[k]; return n; });
    setAtual((g) => g.map((x) => (x.chave === l.chave ? { ...x, valores: x.valores.map((y, i) => (i === m ? v : y)) } : x)));
    return true;
  };
  const tecla = (e: KeyboardEvent<HTMLInputElement>, l: LinhaGrade, m: number, i: number) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    if (!confirmar(l, m, e.currentTarget.value)) return;
    const prox = tabela.current?.querySelector<HTMLInputElement>(`input[data-l="${i + (e.shiftKey ? -1 : 1)}"][data-m="${m}"]`);
    prox?.focus(); prox?.select();
  };

  const salvar = async () => {
    if (!original || !alteradas.length) return;
    setSalvando(true); setErro(null);
    try {
      const r = await salvarGradeOrcamento(ano, alteradas);
      aplicarLeitura(await lerItens());
      setAviso(`Orçamento de ${ano} salvo: ${r.criadas} ${r.criadas === 1 ? "valor novo" : "valores novos"}, ${r.atualizadas} ${r.atualizadas === 1 ? "alterado" : "alterados"}, ${r.excluidas} ${r.excluidas === 1 ? "apagado" : "apagados"}.${r.ignoradas.length ? ` ${r.ignoradas.length} célula(s) com vários itens ficaram como estavam — ajuste item a item.` : ""}`);
      onSalvo();
    } catch (e) { setErro((e as Error).message); } finally { setSalvando(false); }
  };

  const incluir = () => {
    const c = plano.find((x) => x.codigo === novo.codigo);
    if (!c) return;
    const centro = cc === "todos" ? (novo.centro || null) : cc;
    const k = chaveGrade(c.codigo, centro);
    if (atual.some((l) => l.chave === k)) { setAviso(`${c.nome} já está na planilha.`); return; }
    setAtual((g) => ordenarGrade([...g, { chave: k, codigo: c.codigo, centro, tipo: novo.tipo, nome: c.nome, valores: Array(12).fill(0), itensPorMes: Array(12).fill(0) }]));
    setNovo((n) => ({ ...n, codigo: "" }));
    setAviso(`${c.nome} entrou na planilha.`);
  };

  if (erro && !original) return <div className="rl-aviso erro" role="alert"><AlertTriangle size={18} aria-hidden /><div><b>Não foi possível abrir a planilha.</b><p>{erro}</p></div></div>;
  if (!original) return <div className="skeleton" style={{ height: 320 }} role="status" aria-label="Carregando a planilha" />;

  const pctNum = lerValor(pct);
  const linhaCel = (l: LinhaGrade, i: number) => (
    <tr key={l.chave}>
      <td className="stk">
        <span className="nome">{l.nome}</span>
        <span className="meta">{l.codigo}{l.centro ? ` · ${l.centro}` : " · sem centro"}{l.itensPorMes.some((n) => n > 1) ? " · tem mês com vários itens" : ""}</span>
        {!l.itensPorMes.some((n) => n > 1) && (
          <span className="acoesl rl-noprint">
            <button type="button" className="rl-mini" onClick={() => setAtual((g) => g.filter((x) => x.chave !== l.chave))} aria-label={`Tirar ${l.nome} do orçamento de ${ano}`}>
              <X size={12} aria-hidden /> Tirar
            </button>
          </span>
        )}
      </td>
      {l.valores.map((v, m) => {
        const k = `${l.chave}#${m}`, varios = l.itensPorMes[m] > 1, inval = textos[k] !== undefined;
        return (
          <td key={m}>
            <input className={`rl-cel${mudou(l, m) ? " mud" : ""}${inval ? " inv" : ""}`} inputMode="decimal" data-l={i} data-m={m}
              value={textos[k] ?? fmt(v)} disabled={varios} aria-invalid={inval || undefined}
              title={varios ? `${l.itensPorMes[m]} itens neste mês: ajuste item a item na tela anterior` : undefined}
              aria-label={`${l.nome}, ${MESES_LONGOS[m]} de ${ano}`}
              onChange={(e) => setTextos((t) => ({ ...t, [k]: e.target.value }))}
              onFocus={(e) => e.currentTarget.select()}
              onBlur={(e) => { if (textos[k] !== undefined) confirmar(l, m, e.currentTarget.value); }}
              onKeyDown={(e) => tecla(e, l, m, i)} />
          </td>
        );
      })}
      <td className="r"><b>{fmt(somaAno(l.valores))}</b></td>
    </tr>
  );
  const totRow = (nome: string, xs: number[], neg = false) => (
    <tr className="tot"><td className="stk">{nome}</td>
      {xs.map((v, m) => <td key={m} className={neg && v < 0 ? "neg" : undefined} style={neg && v < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{fmt(v)}</td>)}
      <td style={neg && somaAno(xs) < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{fmt(somaAno(xs))}</td></tr>
  );
  const rec = linhas.filter((l) => l.tipo === "receita"), des = linhas.filter((l) => l.tipo === "despesa");

  return (
    <section className="rl-painel" aria-labelledby="rl-og-t">
      <h3 className="rl-tit" id="rl-og-t">Orçamento {ano} · {cc === "todos" ? "todos os centros" : cc}</h3>
      <p style={{ margin: "0 0 .7rem", fontSize: ".86rem", color: "var(--text-muted)", maxWidth: "80ch" }}>
        Uma linha por conta, um mês por coluna. Digite e tecle Enter (desce) ou Tab (vai para o lado). Valores em reais, pelo mês do gasto.
        Célula esmaecida tem mais de um item no mês (lançados um a um): ajuste na tela anterior.
      </p>
      <div className="rl-ferr rl-noprint">
        <button type="button" className="rl-btn" disabled={!anteriorVisivel.length} title={anteriorVisivel.length ? undefined : `Não há orçamento de ${ano - 1} para copiar`}
          onClick={() => { setAtual((g) => copiarAnoAnterior(g, anteriorVisivel, pctNum ?? 0)); setAviso(`Orçamento de ${ano - 1} copiado${pctNum ? ` com ${pct}%` : ""}. Confira e salve.`); }}>
          <Copy size={14} aria-hidden /> Copiar {ano - 1}{pctNum ? ` + ${pct}%` : ""}
        </button>
        <label>% para copiar ou aplicar
          <input className="rl-in num" inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value)} aria-invalid={pctNum == null || undefined} />
        </label>
        <button type="button" className="rl-btn" disabled={pctNum == null || !pctNum}
          onClick={() => { setAtual((g) => [...aplicarPercentual(g.filter(visivel), pctNum!), ...g.filter((l) => !visivel(l))]); setAviso(`${pct}% aplicado em todas as linhas visíveis.`); }}>
          <Percent size={14} aria-hidden /> Aplicar em tudo
        </button>
        <label>Preencher os 12 meses de
          <select className="rl-in" value={preencher.chave} onChange={(e) => setPreencher((p) => ({ ...p, chave: e.target.value }))}>
            <option value="">escolha a linha…</option>
            {linhas.map((l) => <option key={l.chave} value={l.chave}>{l.nome}{l.centro && cc === "todos" ? ` (${l.centro})` : ""}</option>)}
          </select>
        </label>
        <label>com o valor
          <input className="rl-in num" inputMode="decimal" value={preencher.valor} onChange={(e) => setPreencher((p) => ({ ...p, valor: e.target.value }))} />
        </label>
        <button type="button" className="rl-btn" disabled={!preencher.chave || lerValor(preencher.valor) == null}
          onClick={() => { setAtual((g) => preencherLinha(g, preencher.chave, lerValor(preencher.valor)!)); setAviso("Linha preenchida nos 12 meses."); }}>
          Preencher
        </button>
      </div>
      <div className="rl-ferr rl-noprint">
        <label>Incluir conta
          <select className="rl-in" value={novo.codigo} style={{ maxWidth: "18rem" }} onChange={(e) => setNovo((n) => ({ ...n, codigo: e.target.value }))}>
            <option value="">escolha no plano de contas…</option>
            {plano.map((c) => <option key={c.codigo} value={c.codigo}>{c.codigo} · {c.nome}</option>)}
          </select>
        </label>
        <label>Tipo
          <select className="rl-in" value={novo.tipo} onChange={(e) => setNovo((n) => ({ ...n, tipo: e.target.value as "receita" | "despesa" }))}>
            <option value="despesa">Despesa</option><option value="receita">Receita</option>
          </select>
        </label>
        {cc === "todos" && (
          <label>Centro de custo
            <select className="rl-in" value={novo.centro} onChange={(e) => setNovo((n) => ({ ...n, centro: e.target.value }))}>
              <option value="">sem centro</option>{centros.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        )}
        <button type="button" className="rl-btn" disabled={!novo.codigo} onClick={incluir}><Plus size={14} aria-hidden /> Incluir</button>
      </div>
      <p className="rl-hintdeslize" aria-hidden>Deslize a planilha para o lado para ver os meses.</p>
      <div className="rl-gtw">
        <table className="fazenda-table rl-gtab" ref={tabela}>
          <caption className="rl-sr">Orçamento {ano}: conta por mês</caption>
          <thead><tr><th scope="col" className="stk">Conta</th>{MESES_CURTOS.map((m) => <th key={m} scope="col" style={{ textAlign: "right" }}>{m}</th>)}<th scope="col" style={{ textAlign: "right" }}>Ano</th></tr></thead>
          <tbody>
            <tr className="sec"><td className="stk">Receitas</td><td colSpan={13} /></tr>
            {rec.map((l) => linhaCel(l, linhas.indexOf(l)))}
            {!rec.length && <tr><td className="stk" style={{ color: "var(--text-muted)" }}>Nenhuma receita orçada</td><td colSpan={13} /></tr>}
            {totRow("Total de receitas", tot.receitas)}
            <tr className="sec"><td className="stk">Despesas</td><td colSpan={13} /></tr>
            {des.map((l) => linhaCel(l, linhas.indexOf(l)))}
            {!des.length && <tr><td className="stk" style={{ color: "var(--text-muted)" }}>Nenhuma despesa orçada</td><td colSpan={13} /></tr>}
            {totRow("Total de despesas", tot.despesas)}
            {totRow("Resultado orçado", tot.resultado, true)}
          </tbody>
        </table>
      </div>
      <p style={{ margin: ".55rem 0 0", fontSize: ".78rem", color: "var(--text-muted)" }}>
        Totais separados: receitas, despesas e o resultado (receitas − despesas). Litros previstos ainda não entram no orçamento — o R$/L do orçado usa os litros entregues.
      </p>
      <p aria-live="polite" style={{ margin: ".5rem 0 0", fontSize: ".84rem", minHeight: "1.2em" }}>{aviso}</p>
      {erro && <div className="rl-aviso erro" role="alert" style={{ marginTop: ".5rem" }}><AlertTriangle size={18} aria-hidden /><div><b>Não foi possível salvar.</b><p>{erro}</p></div></div>}
      {sujo && (
        <div className="rl-barsalvar rl-noprint" role="region" aria-label="Alterações não salvas">
          <span><b>{alteradas.length}</b> {alteradas.length === 1 ? "valor alterado" : "valores alterados"} — ainda não salvos.</span>
          <span style={{ display: "flex", gap: ".5rem" }}>
            <button type="button" className="rl-btn" onClick={() => { setAtual(original); setTextos({}); setAviso("Alterações descartadas."); }}><Undo2 size={14} aria-hidden /> Descartar</button>
            <button type="button" className="rl-btn pri" onClick={salvar} disabled={salvando}><Save size={14} aria-hidden /> {salvando ? "Salvando…" : "Salvar o orçamento"}</button>
          </span>
        </div>
      )}
    </section>
  );
}
