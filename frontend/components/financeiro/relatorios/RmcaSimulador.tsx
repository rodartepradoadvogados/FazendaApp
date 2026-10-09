"use client";
// Simulador de cenários do RMCA — veio da tela anterior (page.tsx) para a
// Sobra da comida no molde, com a MESMA mecânica: dois cenários de dieta
// (kg/dia × R$/kg, com a fonte do preço: digitado, última compra ou padrão do
// cadastro), pré-preenchidos com o consumo físico do período, contra a receita
// do leite (litros/dia × preço, descontado o leite dos bezerros). Não lança
// nada — é só simulação no navegador. Mudança visual: sem o verde/vermelho
// dos 45% (não é meta; a referência de mercado mora nas Réguas).
import { useState } from "react";
import { Plus, Trash2, Undo2 } from "lucide-react";
import { brl, num, mesLongo } from "@/lib/relatorioContexto";
import type { RespostaRmcaVaca } from "@/lib/relatorioLeite";

type FonteCusto = "manual" | "ultima_compra" | "padrao";
type FontePrecoLeite = "manual" | "media_laticinio";
type LinhaSimulador = {
  id: string; nome: string; kgDia: number; fonte: FonteCusto;
  precoManual: number; precoUltimaCompra: number | null; precoPadrao: number | null;
};

function diasDoPeriodo(p: { inicio: string; fim: string }): number {
  const ini = new Date(p.inicio + "T00:00:00").getTime();
  const fim = new Date(p.fim + "T00:00:00").getTime();
  return Math.max(1, Math.round((fim - ini) / 86400000) + 1);
}

function linhasDoFisico(dados: RespostaRmcaVaca): LinhaSimulador[] {
  const dias = diasDoPeriodo(dados.periodo);
  return dados.fisico.itens.map((it, i) => ({
    id: `${it.estoque_id ?? it.ingrediente}-${i}`,
    nome: it.ingrediente,
    kgDia: Math.round((it.quantidade_kg / dias) * 100) / 100,
    fonte: "padrao" as FonteCusto,
    precoManual: it.preco_padrao_kg ?? it.valor_unitario ?? 0,
    precoUltimaCompra: it.preco_ultima_compra_kg,
    precoPadrao: it.preco_padrao_kg,
  }));
}

function precoEfetivo(l: LinhaSimulador): number {
  if (l.fonte === "manual") return l.precoManual;
  if (l.fonte === "ultima_compra") return l.precoUltimaCompra ?? l.precoPadrao ?? l.precoManual;
  return l.precoPadrao ?? l.precoManual;
}

const numero = (v: string) => Number(v.replace(",", ".")) || 0;

function TabelaCenario({ titulo, id, linhas, setLinhas, onRecarregar }: {
  titulo: string; id: string; linhas: LinhaSimulador[];
  setLinhas: (fn: (atual: LinhaSimulador[]) => LinhaSimulador[]) => void; onRecarregar: () => void;
}) {
  const atualizar = <K extends keyof LinhaSimulador>(lid: string, campo: K, valor: LinhaSimulador[K]) =>
    setLinhas((atual) => atual.map((l) => (l.id === lid ? { ...l, [campo]: valor } : l)));
  const total = linhas.reduce((s, l) => s + l.kgDia * precoEfetivo(l), 0);
  return (
    <section className="rl-painel" aria-labelledby={`${id}-t`}>
      <h4 className="rl-tit" id={`${id}-t`}>{titulo}</h4>
      <div className="rl-tw">
        <table className="fazenda-table rl-tab">
          <caption className="rl-sr">{titulo}</caption>
          <thead><tr><th scope="col">Ingrediente</th><th scope="col" className="r">kg/dia</th><th scope="col">Fonte do preço</th><th scope="col" className="r">R$/kg</th><th scope="col" className="r">Subtotal/dia</th><th scope="col"><span className="rl-sr">Remover</span></th></tr></thead>
          <tbody>
            {linhas.map((l) => {
              const semFonte = l.fonte === "ultima_compra" && l.precoUltimaCompra == null;
              return (
                <tr key={l.id}>
                  <td style={{ minWidth: "9rem" }}><input className="rl-in" aria-label="Ingrediente" value={l.nome} onChange={(e) => atualizar(l.id, "nome", e.target.value)} style={{ width: "100%" }} /></td>
                  <td className="r"><input className="rl-in" aria-label={`kg por dia de ${l.nome}`} inputMode="decimal" value={l.kgDia} onChange={(e) => atualizar(l.id, "kgDia", numero(e.target.value))} style={{ width: "5.5rem", textAlign: "right" }} /></td>
                  <td style={{ minWidth: "10rem" }}>
                    <select className="rl-in" aria-label={`Fonte do preço de ${l.nome}`} value={l.fonte} onChange={(e) => atualizar(l.id, "fonte", e.target.value as FonteCusto)} style={{ width: "100%" }}>
                      <option value="manual">Digitar R$/kg</option>
                      <option value="ultima_compra">Último preço de compra{l.precoUltimaCompra == null ? " (sem compra registrada)" : ""}</option>
                      <option value="padrao">Preço padrão do cadastro{l.precoPadrao == null ? " (sem cadastro)" : ""}</option>
                    </select>
                  </td>
                  <td className="r">{l.fonte === "manual"
                    ? <input className="rl-in" aria-label={`R$ por kg de ${l.nome}`} inputMode="decimal" value={l.precoManual} onChange={(e) => atualizar(l.id, "precoManual", numero(e.target.value))} style={{ width: "5.5rem", textAlign: "right" }} />
                    : <>{brl(precoEfetivo(l))}{semFonte && <small>sem compra: usa o padrão</small>}</>}</td>
                  <td className="r"><b>{brl(l.kgDia * precoEfetivo(l))}</b></td>
                  <td><button type="button" className="rl-btn" aria-label={`Remover ${l.nome}`} onClick={() => setLinhas((a) => a.filter((x) => x.id !== l.id))}><Trash2 size={13} aria-hidden /></button></td>
                </tr>
              );
            })}
          </tbody>
          <tfoot><tr><td colSpan={4}>Total diário de alimentação</td><td className="r">{brl(total)}</td><td /></tr></tfoot>
        </table>
      </div>
      <div className="rl-acoes" style={{ marginTop: ".5rem" }}>
        <button type="button" className="rl-btn" onClick={() => setLinhas((a) => [...a, { id: `novo-${Date.now()}`, nome: "Novo ingrediente", kgDia: 0, fonte: "manual", precoManual: 0, precoUltimaCompra: null, precoPadrao: null }])}>
          <Plus size={13} aria-hidden /> Adicionar ingrediente
        </button>
        <button type="button" className="rl-btn" onClick={onRecarregar}><Undo2 size={13} aria-hidden /> Recarregar do consumo real</button>
      </div>
    </section>
  );
}

export default function RmcaSimulador({ dados }: { dados: RespostaRmcaVaca }) {
  const [cenarioA, setCenarioA] = useState<LinhaSimulador[]>(() => linhasDoFisico(dados));
  const [cenarioB, setCenarioB] = useState<LinhaSimulador[]>(() => linhasDoFisico(dados));
  const [litrosDia, setLitrosDia] = useState(() => (dados.atual.dias > 0 && dados.atual.litros > 0 ? Math.round(dados.atual.litros / dados.atual.dias) : 1000));
  const [fonteVenda, setFonteVenda] = useState<FontePrecoLeite>("manual");
  const [precoVendaManual, setPrecoVendaManual] = useState(() => (dados.preco_bruto_l != null ? Math.round(dados.preco_bruto_l * 100) / 100 : 3));
  const [litrosBezerros, setLitrosBezerros] = useState(0);
  const [fonteBezerro, setFonteBezerro] = useState<FontePrecoLeite>("manual");
  const [precoBezerro, setPrecoBezerro] = useState(3);

  const media = dados.preco_medio_litro_leite?.preco_por_litro ?? null;
  const precoVenda = fonteVenda === "media_laticinio" ? (media ?? precoVendaManual) : precoVendaManual;
  const precoBez = fonteBezerro === "media_laticinio" ? (media ?? precoBezerro) : precoBezerro;
  const litrosVendidos = Math.max(0, litrosDia - litrosBezerros);
  const receita = litrosVendidos * precoVenda;
  const custo = (ls: LinhaSimulador[]) => ls.reduce((s, l) => s + l.kgDia * precoEfetivo(l), 0);
  const cenarios = [{ nome: "Cenário A — dieta de hoje", custo: custo(cenarioA) }, { nome: "Cenário B — dieta pretendida", custo: custo(cenarioB) }];

  return (
    <div style={{ display: "grid", gap: ".75rem" }}>
      <p className="rl-hint" style={{ marginTop: 0 }}>
        Os dois cenários começam com o consumo registrado pela Alimentação no período (kg/dia). Edite à vontade; nada é lançado.
      </p>
      <div className="rl-dois" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,26rem),1fr))" }}>
        <TabelaCenario titulo="Cenário A — dieta de hoje" id="rl-simA" linhas={cenarioA} setLinhas={setCenarioA} onRecarregar={() => setCenarioA(linhasDoFisico(dados))} />
        <TabelaCenario titulo="Cenário B — dieta pretendida" id="rl-simB" linhas={cenarioB} setLinhas={setCenarioB} onRecarregar={() => setCenarioB(linhasDoFisico(dados))} />
      </div>
      <section className="rl-painel" aria-labelledby="rl-sim-rec">
        <h4 className="rl-tit" id="rl-sim-rec">Receita do leite (a mesma nos dois cenários)</h4>
        <div className="rl-busca">
          <div className="rl-campo"><label htmlFor="rl-sim-l">Litros produzidos/dia</label>
            <input id="rl-sim-l" className="rl-in" inputMode="decimal" value={litrosDia} onChange={(e) => setLitrosDia(numero(e.target.value))} /></div>
          <div className="rl-campo"><label htmlFor="rl-sim-fv">Preço de venda</label>
            <select id="rl-sim-fv" className="rl-in" value={fonteVenda} onChange={(e) => setFonteVenda(e.target.value as FontePrecoLeite)}>
              <option value="manual">Valor digitado</option>
              <option value="media_laticinio">Média paga pelo laticínio{media == null ? " (sem dado ainda)" : ""}</option>
            </select></div>
          {fonteVenda === "manual" && <div className="rl-campo"><label htmlFor="rl-sim-pv">R$/litro</label>
            <input id="rl-sim-pv" className="rl-in" inputMode="decimal" value={precoVendaManual} onChange={(e) => setPrecoVendaManual(numero(e.target.value))} /></div>}
          <div className="rl-campo"><label htmlFor="rl-sim-lb">Leite para bezerros (L/dia)</label>
            <input id="rl-sim-lb" className="rl-in" inputMode="decimal" value={litrosBezerros} onChange={(e) => setLitrosBezerros(numero(e.target.value))} /></div>
          <div className="rl-campo"><label htmlFor="rl-sim-fb">Valor do leite dos bezerros</label>
            <select id="rl-sim-fb" className="rl-in" value={fonteBezerro} onChange={(e) => setFonteBezerro(e.target.value as FontePrecoLeite)}>
              <option value="manual">Valor padrão digitado</option>
              <option value="media_laticinio">Média paga pelo laticínio{media == null ? " (sem dado ainda)" : ""}</option>
            </select></div>
          {fonteBezerro === "manual" && <div className="rl-campo"><label htmlFor="rl-sim-pb">R$/litro (padrão)</label>
            <input id="rl-sim-pb" className="rl-in" inputMode="decimal" value={precoBezerro} onChange={(e) => setPrecoBezerro(numero(e.target.value))} /></div>}
        </div>
        {dados.preco_medio_litro_leite && (
          <p className="rl-hint">Última nota do laticínio ({mesLongo(dados.preco_medio_litro_leite.competencia)}): {brl(dados.preco_medio_litro_leite.preco_por_litro)}/L
            ({brl(dados.preco_medio_litro_leite.receita)} ÷ {num(dados.preco_medio_litro_leite.litros, 0)} L).</p>
        )}
        <div className="rl-dl-par" style={{ marginTop: ".6rem" }}>
          <span>Litros disponíveis para venda</span><b>{num(litrosVendidos, 0)} L/dia</b>
          <span>Receita de venda</span><b>{brl(receita)}/dia</b>
          <span>Valor do leite dos bezerros (informativo)</span><b>{brl(litrosBezerros * precoBez)}/dia</b>
        </div>
      </section>
      <div className="rl-dois" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(min(100%,18rem),1fr))" }} aria-live="polite">
        {cenarios.map((c) => (
          <section key={c.nome} className="rl-painel" aria-label={c.nome}>
            <h4 className="rl-tit">{c.nome}</h4>
            <div className="rl-dl-par">
              <span>Comida por dia</span><b>{brl(c.custo)}</b>
              <span>Comida ÷ receita de venda</span><b>{receita > 0 ? `${num((100 * c.custo) / receita, 1)}%` : "—"}</b>
              <span>Sobra da comida por dia</span><b className={receita - c.custo < 0 ? "neg" : undefined} style={receita - c.custo < 0 ? { color: "var(--st-venc-fg)" } : undefined}>{brl(receita - c.custo)}</b>
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
