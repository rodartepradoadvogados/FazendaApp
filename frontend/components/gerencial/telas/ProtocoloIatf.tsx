"use client";
// PROPOSTA — Lançamentos › Reprodutivo › Protocolo IATF (variante desktop, só apresentação, dados de exemplo; sem fetch).
// Substitui FormProtocoloIatf.tsx (lista "em andamento" presa na coluna esquerda, matriz escolhida em modal, cronograma como tabela solta).
//
// O QUE A VERSÃO LIGADA A DADOS PRECISA PRESERVAR (inventário de FormProtocoloIatf.tsx / EditorHormoniosIatf.tsx):
//  · Props: animais (AnimalRow[]), motivosInaptidao (Map número→motivo), idadeMinServico, onSalvo. Montada também em /protocolos.
//  · Modo "novo" (criarProtocoloIatf: {animais, data_d0, protocolo_id, hormonios, forcar}) ou "existente" (adicionarAnimaisIatf(lancamento_id, animais);
//    lista via fetchLancamentosIatf: nome, qtd_animais). Seleção: um animal ou em lote (animais OU lote(s) inteiros, ajustáveis na tabela).
//    A tabela mostra TODAS as fêmeas; inaptas em cinza com o motivo (idade mínima, baixada, a descartar); 409 confirmável ⇒ "Confirmar e lançar mesmo assim" (forcar).
//  · Molde cadastrado opcional (fetchProtocolosIatfCadastrados, só ativos): se escolhido MANDA nos dias e nos hormônios (dias livres: D0/D8/D10/D12…);
//    inseminação = último dia de hormônio + 2 (rules.protocolo_iatf.dia_inseminacao; padrão D11). Sem molde: cronograma clássico D0/D7/D9/D11 e
//    hormônios digitados (EditorHormoniosIatf: por dia, "Definir por" medicamento/princípio ativo/doença/classificação, medicamento, dose, unidade
//    compatível, via, "incluir itens sem estoque"; opcional — sem medicamento só agenda os dias, sem baixa de estoque).
//  · Nome do lançamento automático e somente leitura (mesma regra de nomenclatura_protocolo.py; o nome de verdade vem do backend).
//  · D0 obrigatório no modo novo. Resumo: nº de animais, protocolo, D0.
//  · Retorno: `criado:false` ⇒ mensagem própria (já lançado, nada duplicado — `r.aviso`); sucesso ⇒ "agendado para N animal(is) — X eventos na Agenda (D0 a Dn)".
//    Depois de salvar: limpar seleção, recarregar "em andamento" (e `existentes` no modo existente), chamar onSalvo.
//  · Em andamento (fetchProtocolosIatfAtivos): por protocolo — animais, etapa atual, data da etapa, D0 confirmado; remover animal
//    (removerAnimalIatf) SÓ se nenhuma etapa dela foi confirmada — hoje o servidor recusa e a tela mostra o motivo; aqui o botão já nasce desabilitado
//    para quem tem D0 confirmado (heurística: D0 confirmado ⇒ há etapa confirmada) — confirmar com o dono se o endpoint pode devolver o dado exato.
//  · A inseminação em si (D11) NÃO é lançada aqui: é a tela Inseminação (aviso no passo 3).
import React, { useMemo, useState } from "react";
import { AlertTriangle, HeartPulse, Plus, Trash2, X, Check } from "lucide-react";
import { Ajuda, BarraAcao, BotaoOuro, Faixa, Passo, Pilulas, QuadroGaveta, Selo } from "@/components/gerencial/kit";
import {
  Abas, BuscaMatrizes, EstiloRepro, HOJE_ISO, IDADE_MIN_SERVICO, MATRIZES, PilulasX, TabelaMatrizes, alterna, alternaAptas, diaSemana, filtraBusca, fmtData, somaDias,
} from "@/components/gerencial/telas/ReprodutivoComum";

/* ───────────────────────────── dados de exemplo ───────────────────────────── */
type Etapa = { dia: number; produto: string; dose: number; unidade: string; via: string };
const MOLDES: { id: string; nome: string; etapas: Etapa[] }[] = [
  { id: "1", nome: "P4 + E2 clássico", etapas: [
    { dia: 0, produto: "Cidr (implante P4)", dose: 1, unidade: "unidade", via: "Intravaginal" },
    { dia: 0, produto: "Sincrodiol (benzoato)", dose: 2, unidade: "ml", via: "Intramuscular" },
    { dia: 0, produto: "Sincroforte (buserelina)", dose: 1, unidade: "ml", via: "Intramuscular" },
    { dia: 7, produto: "Estron (cloprostenol)", dose: 2, unidade: "ml", via: "Intramuscular" },
    { dia: 9, produto: "SincroCP (cipionato)", dose: 1, unidade: "ml", via: "Intramuscular" },
    { dia: 9, produto: "Estron (cloprostenol)", dose: 2, unidade: "ml", via: "Intramuscular" },
  ] },
  { id: "2", nome: "Curto D0/D8/D10/D12", etapas: [
    { dia: 0, produto: "Cidr (implante P4)", dose: 1, unidade: "unidade", via: "Intravaginal" },
    { dia: 0, produto: "Sincrodiol (benzoato)", dose: 2, unidade: "ml", via: "Intramuscular" },
    { dia: 8, produto: "Estron (cloprostenol)", dose: 2, unidade: "ml", via: "Intramuscular" },
    { dia: 10, produto: "SincroCP (cipionato)", dose: 1, unidade: "ml", via: "Intramuscular" },
    { dia: 12, produto: "Sincroforte (buserelina)", dose: 1, unidade: "ml", via: "Intramuscular" },
  ] },
];
const CLASSICO = [
  { dia: 0, texto: "Implante de progesterona + benzoato de estradiol + acetato de buserelina" },
  { dia: 7, texto: "Cloprostenol" },
  { dia: 9, texto: "Retirar implante + cipionato de estradiol + cloprostenol" },
];
const DIA_IA_PADRAO = 11;
const MEDICAMENTOS = ["Cidr (implante P4)", "Sincrogest (progesterona)", "Sincrodiol (benzoato)", "Sincroforte (buserelina)", "Estron (cloprostenol)", "SincroCP (cipionato)"];
const UNIDADES = ["ml", "unidade", "dose", "L", "kg"];
const VIAS = ["Intramuscular", "Intravaginal", "Subcutânea"];

type Hormonio = { id: number; dia: number; definir: string; produto: string; dose: string; unidade: string; via: string };
const HORMONIOS_INICIAIS: Hormonio[] = [
  { id: 1, dia: 0, definir: "medicamento", produto: "Cidr (implante P4)", dose: "1", unidade: "unidade", via: "Intravaginal" },
  { id: 2, dia: 0, definir: "medicamento", produto: "Sincrodiol (benzoato)", dose: "2", unidade: "ml", via: "Intramuscular" },
  { id: 3, dia: 0, definir: "medicamento", produto: "Sincroforte (buserelina)", dose: "1", unidade: "ml", via: "Intramuscular" },
  { id: 4, dia: 7, definir: "medicamento", produto: "Estron (cloprostenol)", dose: "2", unidade: "ml", via: "Intramuscular" },
  { id: 5, dia: 9, definir: "medicamento", produto: "SincroCP (cipionato)", dose: "1", unidade: "ml", via: "Intramuscular" },
  { id: 6, dia: 9, definir: "medicamento", produto: "Estron (cloprostenol)", dose: "2", unidade: "ml", via: "Intramuscular" },
];

type AnimalAndamento = { n: string; etapa: string; data: string; d0: boolean; pronta?: boolean };
type Andamento = { id: number; nome: string; d0: string; animais: AnimalAndamento[] };
const ANDAMENTO: Andamento[] = [
  { id: 1, nome: "PROTOCOLO IATF - 06/10/26 A 17/10/26 (D0 A D11 - 12 DIAS)", d0: "2026-10-06", animais: [
    { n: "7120", etapa: "D11 · Inseminação", data: "2026-10-17", d0: true, pronta: true },
    { n: "4790", etapa: "D11 · Inseminação", data: "2026-10-17", d0: true, pronta: true },
    { n: "1087", etapa: "D11 · Inseminação", data: "2026-10-17", d0: true, pronta: true },
    { n: "1092", etapa: "D11 · Inseminação", data: "2026-10-17", d0: true, pronta: true },
    { n: "13180", etapa: "D11 · Inseminação", data: "2026-10-17", d0: true, pronta: true },
  ] },
  { id: 2, nome: "PROTOCOLO IATF - 12/10/26 A 23/10/26 (D0 A D11 - 12 DIAS)", d0: "2026-10-12", animais: [
    { n: "6401", etapa: "D7 · Cloprostenol", data: "2026-10-19", d0: true },
    { n: "6433", etapa: "D7 · Cloprostenol", data: "2026-10-19", d0: true },
    { n: "6450", etapa: "D7 · Cloprostenol", data: "2026-10-19", d0: true },
    { n: "6477", etapa: "D0 · Implante", data: "2026-10-12", d0: false },
  ] },
  { id: 3, nome: "CURTO D0/D8/D10/D12 - 14/10/26 A 28/10/26 (D0 A D14 - 15 DIAS)", d0: "2026-10-14", animais: [
    { n: "5512", etapa: "D8 · Cloprostenol", data: "2026-10-22", d0: true },
    { n: "5530", etapa: "D8 · Cloprostenol", data: "2026-10-22", d0: true },
    { n: "5544", etapa: "D0 · Implante", data: "2026-10-14", d0: false },
  ] },
];

/** Mesma regra de nomenclatura_protocolo.py — só pré-visualização; o nome de verdade é calculado no backend. */
function nomeAuto(d0: string, base: string, diaFinal: number): string {
  if (!d0) return "";
  const f = (iso: string) => { const [a, m, d] = iso.split("-"); return `${d}/${m}/${a.slice(2)}`; };
  return `${base.toUpperCase()} - ${f(d0)} A ${f(somaDias(d0, diaFinal))} (D0 A D${diaFinal} - ${diaFinal + 1} DIAS)`;
}
const diaInseminacao = (dias: number[]) => (dias.length ? Math.max(...dias) + 2 : DIA_IA_PADRAO);

/* ───────────────────────────── subcomponentes (fora do pai) ───────────────────────────── */
type NoTempo = { dia: number; data: string; linhas: string[]; subtitulo?: string; fim?: boolean };
function LinhaDoTempo({ nos }: { nos: NoTempo[] }) {
  return (
    <ol className="rp-linha-tempo" style={{ listStyle: "none", margin: 0, padding: 0 }} aria-label="Cronograma do protocolo">
      {nos.map((n) => (
        <li key={n.dia} className={`rp-etapa${n.fim ? " rp-etapa-fim" : ""}`}>
          <span className="rp-no" data-fim={n.fim ? "true" : undefined}>D{n.dia}</span>
          <span className="rp-etapa-data">{n.data ? fmtData(n.data, true) : "—"}</span>
          <span className="rp-etapa-dow">{n.data ? diaSemana(n.data) : ""}</span>
          <span className="rp-etapa-txt">
            {n.subtitulo && <i>{n.subtitulo}</i>}
            {n.linhas.length ? n.linhas.map((l) => <span key={l} style={{ display: "block" }}>{l}</span>) : <i>sem medicamento informado</i>}
          </span>
        </li>
      ))}
    </ol>
  );
}

function EditorHormonios({ linhas, onChange }: { linhas: Hormonio[]; onChange: (l: Hormonio[]) => void }) {
  const dias = [0, 7, 9];
  const [semEstoque, setSemEstoque] = useState(false);
  const atualiza = (id: number, p: Partial<Hormonio>) => onChange(linhas.map((l) => (l.id === id ? { ...l, ...p } : l)));
  const adiciona = (dia: number) => onChange([...linhas, { id: Math.max(0, ...linhas.map((l) => l.id)) + 1, dia, definir: "medicamento", produto: "", dose: "", unidade: "ml", via: "" }]);
  return (
    <div className="rp-bloco">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <div className="rp-bloco-t">Medicamentos por dia (opcional) — dão baixa no estoque quando você confirma o dia na Agenda</div>
        <label style={{ display: "inline-flex", gap: "0.4rem", alignItems: "center", fontSize: "0.76rem", color: "var(--text-muted)", cursor: "pointer" }}>
          <input type="checkbox" checked={semEstoque} onChange={(e) => setSemEstoque(e.target.checked)} /> Incluir itens sem estoque
        </label>
      </div>
      <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "30rem" }}>
        <table className="gv-tabela">
          <thead><tr>
            <th scope="col">Definir por</th><th scope="col">Medicamento</th><th scope="col" className="gv-dir">Dose</th><th scope="col">Unidade</th><th scope="col">Via de aplicação</th>
            <th scope="col" style={{ width: "2.6rem" }}><span style={{ position: "absolute", left: "-9999px" }}>Remover</span></th>
          </tr></thead>
          <tbody>
            {dias.map((dia) => (
              <React.Fragment key={dia}>
                <tr className="gv-grupo">
                  <th scope="rowgroup" colSpan={5}>D{dia} — {CLASSICO.find((c) => c.dia === dia)?.texto}</th>
                  <th scope="col" style={{ textAlign: "right", padding: "0.1rem 0.4rem" }}>
                    <button type="button" className="btn-ghost" style={{ display: "inline-flex", gap: "0.25rem", alignItems: "center", textTransform: "none", letterSpacing: 0, fontSize: "0.78rem" }} onClick={() => adiciona(dia)} aria-label={`Adicionar medicamento no D${dia}`}><Plus size={13} aria-hidden="true" /> medicamento</button>
                  </th>
                </tr>
                {linhas.filter((l) => l.dia === dia).map((l) => (
                  <tr key={l.id}>
                    <td>
                      <select className="rp-cel" aria-label={`Definir por, D${dia}`} value={l.definir} onChange={(e) => atualiza(l.id, { definir: e.target.value })}>
                        <option value="medicamento">Medicamento</option><option value="principio_ativo">Princípio ativo</option><option value="doenca">Doença</option><option value="classificacao">Classificação</option>
                      </select>
                    </td>
                    <td>
                      <select className="rp-cel" aria-label={`Medicamento, D${dia}`} value={l.produto} onChange={(e) => atualiza(l.id, { produto: e.target.value })}>
                        <option value="">Selecione…</option>{MEDICAMENTOS.map((m) => <option key={m}>{m}</option>)}
                      </select>
                    </td>
                    <td><input className="rp-cel" style={{ textAlign: "right", maxWidth: "5rem" }} inputMode="decimal" aria-label={`Dose, D${dia}`} value={l.dose} onChange={(e) => atualiza(l.id, { dose: e.target.value })} placeholder="0" /></td>
                    <td><select className="rp-cel" aria-label={`Unidade, D${dia}`} value={l.unidade} onChange={(e) => atualiza(l.id, { unidade: e.target.value })}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select></td>
                    <td><select className="rp-cel" aria-label={`Via, D${dia}`} value={l.via} onChange={(e) => atualiza(l.id, { via: e.target.value })}><option value="">Selecione…</option>{VIAS.map((v) => <option key={v}>{v}</option>)}</select></td>
                    <td><button type="button" className="rp-seta" aria-label="Remover medicamento" title="Remover" onClick={() => onChange(linhas.filter((x) => x.id !== l.id))}><Trash2 size={14} /></button></td>
                  </tr>
                ))}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <Ajuda>Cada dose é multiplicada pelo nº de vacas confirmadas. Sem medicamentos, o protocolo só agenda os dias (sem baixa de estoque). Dia da inseminação = último dia de hormônio + 2.</Ajuda>
    </div>
  );
}

function TabelaAndamento({ dados, removidos, onRemover, busca }: { dados: Andamento[]; removidos: ReadonlySet<string>; onRemover: (n: string) => void; busca: string }) {
  const q = busca.trim().toLowerCase();
  return (
    <div className="gv-tabela-moldura" style={{ ["--gv-altura-tabela" as string]: "40rem" }}>
      <table className="gv-tabela">
        <thead><tr>
          <th scope="col">Nº</th><th scope="col">Etapa atual</th><th scope="col">Data da etapa</th><th scope="col">D0 na Agenda</th><th scope="col" className="gv-dir">Corrigir</th>
        </tr></thead>
        <tbody>
          {dados.map((p) => {
            const animais = p.animais.filter((a) => !removidos.has(a.n) && (!q || a.n.toLowerCase().includes(q)));
            return (
              <React.Fragment key={p.id}>
                <tr className="gv-grupo">
                  <th scope="rowgroup" colSpan={5}>{p.nome} · D0 {fmtData(p.d0)} · {p.animais.filter((a) => !removidos.has(a.n)).length} animais</th>
                </tr>
                {animais.map((a) => (
                  <tr key={a.n}>
                    <td className="gv-forte">{a.n}</td>
                    <td>{a.etapa} {a.pronta && <Selo tom="ok" titulo="Protocolo vigente sem inseminação lançada">Pronta para inseminar</Selo>}</td>
                    <td className="gv-num">{fmtData(a.data)}</td>
                    <td>
                      {a.d0
                        ? <Selo tom="ok" titulo="D0 confirmado na Agenda"><Check size={11} aria-hidden="true" /> Confirmado</Selo>
                        : <Selo tom="atencao" titulo="D0 ainda não confirmado na Agenda — pode ter entrado no protocolo sem ter sido implantada"><AlertTriangle size={11} aria-hidden="true" /> Não confirmado</Selo>}
                    </td>
                    <td className="gv-dir">
                      <button type="button" className="btn-ghost" disabled={a.d0} onClick={() => onRemover(a.n)}
                        title={a.d0 ? "Não dá para remover: já há etapa confirmada na Agenda" : "Remover este animal do protocolo (corrige inclusão por engano)"}
                        style={{ display: "inline-flex", gap: "0.25rem", alignItems: "center", padding: "0.2rem 0.55rem", fontSize: "0.74rem", opacity: a.d0 ? 0.4 : 1, cursor: a.d0 ? "not-allowed" : "pointer" }}>
                        <X size={12} aria-hidden="true" /> Remover
                      </button>
                    </td>
                  </tr>
                ))}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ───────────────────────────── a tela ───────────────────────────── */
const MATRIZES_IATF = MATRIZES.map((m) => ({ ...m, diag: false }));
type Aba = "lancar" | "andamento";
type Modo = "novo" | "existente";
type Retorno = "sucesso" | "ja_lancado" | "confirmar" | null;

export function ProtocoloIatf({ estado = "lancar" }: { estado?: Aba }) {
  const [aba, setAba] = useState<Aba>(estado);
  const [modo, setModo] = useState<Modo>("novo");
  const [origem, setOrigem] = useState<"animais" | "lotes">("animais");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [sel, setSel] = useState<Set<string>>(() => new Set(["11153", "3335", "075", "9378", "4821", "1110", "4802"]));
  const [busca, setBusca] = useState("");
  const [moldeId, setMoldeId] = useState("");
  const [d0, setD0] = useState(HOJE_ISO);
  const [hormonios, setHormonios] = useState<Hormonio[]>(HORMONIOS_INICIAIS);
  const [existenteId, setExistenteId] = useState("2");
  const [retorno, setRetorno] = useState<Retorno>("sucesso");
  const [removidos, setRemovidos] = useState<Set<string>>(new Set());
  const [buscaAnd, setBuscaAnd] = useState("");

  const molde = MOLDES.find((m) => m.id === moldeId) ?? null;
  const diasMolde = molde ? [...new Set(molde.etapas.map((e) => e.dia))].sort((a, b) => a - b) : [];
  const diaIA = molde ? diaInseminacao(diasMolde) : DIA_IA_PADRAO;
  const nomeBase = molde?.nome ?? "Protocolo IATF";
  const nome = nomeAuto(d0, nomeBase, diaIA);
  const existente = ANDAMENTO.find((p) => String(p.id) === existenteId);

  const lotes = useMemo(() => {
    const m = new Map<string, number>();
    MATRIZES.forEach((x) => m.set(x.lote, (m.get(x.lote) ?? 0) + 1));
    return [...m.entries()].sort(([a], [b]) => a.localeCompare(b, "pt-BR", { numeric: true }));
  }, []);
  const base = origem === "animais" ? MATRIZES_IATF : MATRIZES_IATF.filter((m) => lotesSel.includes(m.lote));
  const visiveis = filtraBusca(base, busca);
  const marcadas = MATRIZES_IATF.filter((m) => sel.has(m.n));
  const nSel = marcadas.length;
  const nConf = marcadas.filter((m) => m.apt !== "apta").length;

  function alternaLote(lote: string) {
    const ativo = lotesSel.includes(lote);
    setLotesSel(ativo ? lotesSel.filter((l) => l !== lote) : [...lotesSel, lote]);
    const aptas = MATRIZES.filter((m) => m.lote === lote && m.apt === "apta");
    setSel((p) => { const s = new Set(p); aptas.forEach((m) => (ativo ? s.delete(m.n) : s.add(m.n))); return s; });
  }

  // Linha do tempo: do molde (etapa por etapa) ou clássico + hormônios digitados
  const nos: NoTempo[] = molde
    ? [
        ...diasMolde.map((dia) => ({
          dia, data: somaDias(d0, dia),
          linhas: molde.etapas.filter((e) => e.dia === dia).map((e) => `${e.dose} ${e.unidade === "unidade" ? "un" : e.unidade} ${e.produto}`),
        })),
        { dia: diaIA, data: somaDias(d0, diaIA), linhas: ["Inseminação (IATF)"], fim: true },
      ]
    : [
        ...CLASSICO.map((c) => ({
          dia: c.dia, data: somaDias(d0, c.dia), subtitulo: c.texto,
          linhas: hormonios.filter((h) => h.dia === c.dia && h.produto).map((h) => `${h.dose || "?"} ${h.unidade === "unidade" ? "un" : h.unidade} ${h.produto}`),
        })),
        { dia: DIA_IA_PADRAO, data: somaDias(d0, DIA_IA_PADRAO), linhas: ["Inseminação (IATF)"], fim: true },
      ];

  const faixa = [
    { rotulo: "Protocolos em andamento", valor: ANDAMENTO.length },
    { rotulo: "Animais em protocolo", valor: ANDAMENTO.reduce((s, p) => s + p.animais.length, 0) },
    { rotulo: "Prontas para inseminar", valor: ANDAMENTO.reduce((s, p) => s + p.animais.filter((a) => a.pronta).length, 0), tom: "ok" as const },
    { rotulo: "D0 sem confirmar", valor: ANDAMENTO.reduce((s, p) => s + p.animais.filter((a) => !a.d0).length, 0), tom: "atencao" as const },
    { rotulo: "Moldes ativos", valor: MOLDES.length },
  ];

  const resumo = modo === "novo"
    ? `${nSel} ${nSel === 1 ? "animal" : "animais"} · ${molde ? molde.nome : "Protocolo IATF (sem molde)"}`
    : `${nSel} ${nSel === 1 ? "animal" : "animais"} entram em “${existente ? existente.nome.slice(0, 40) + "…" : "—"}”`;
  const detalhe = !nSel ? "Marque ao menos um animal na tabela do passo 2"
    : modo === "novo"
      ? (!d0 ? "Falta a data do D0" : `D0 ${fmtData(d0)} · inseminação D${diaIA} em ${fmtData(somaDias(d0, diaIA))}${nConf ? ` · ${nConf} pede(m) confirmação` : ""}`)
      : (!existente ? "Escolha o protocolo no passo 3" : `Mesmo D0 do protocolo (${fmtData(existente.d0)})${nConf ? ` · ${nConf} pede(m) confirmação` : ""}`);
  const podeSalvar = nSel > 0 && (modo === "novo" ? !!d0 : !!existente);

  return (
    <QuadroGaveta titulo="Lançar › Reprodutivo › Protocolo IATF" icone={HeartPulse} largura={1320}>
      <EstiloRepro />
      <Faixa itens={faixa} />
      <Abas<Aba> rotulo="Protocolo IATF" ativa={aba} onChange={setAba} abas={[
        { id: "lancar", nome: "Lançar protocolo" },
        { id: "andamento", nome: "Em andamento", n: ANDAMENTO.length },
      ]} />

      {aba === "andamento" && (
        <div role="tabpanel" aria-labelledby="aba-andamento" style={{ display: "flex", flexDirection: "column", gap: "0.6rem" }}>
          <div className="rp-ferr">
            <BuscaMatrizes valor={buscaAnd} onChange={setBuscaAnd} rotulo="Buscar animal" />
            <span className="rp-contagem">{ANDAMENTO.length} protocolos · {ANDAMENTO.reduce((s, p) => s + p.animais.length, 0) - removidos.size} animais</span>
          </div>
          <TabelaAndamento dados={ANDAMENTO} removidos={removidos} onRemover={(n) => setRemovidos((p) => alterna(p, n))} busca={buscaAnd} />
          <Ajuda>
            “Pronta para inseminar” = protocolo vigente sem inseminação lançada; ela vai para a tela <strong>Inseminação</strong> (origem “Protocolo IATF vigente”).
            Remover um animal corrige inclusão por engano e <strong>só é possível enquanto nenhuma etapa dele foi confirmada na Agenda</strong>.
          </Ajuda>
        </div>
      )}

      {aba === "lancar" && (
        <div role="tabpanel" aria-labelledby="aba-lancar">
          <Passo n={1} id="iatf-p1" titulo="O que fazer">
            <Pilulas<Modo> rotulo="Modo" valor={modo} onChange={setModo} opcoes={[
              { id: "novo", nome: "Novo protocolo", titulo: "Criar um novo protocolo IATF (define D0 e hormônios)" },
              { id: "existente", nome: "Adicionar a um em andamento", n: ANDAMENTO.length, titulo: "Incluir animais num protocolo já lançado (mesmo D0 e nome)" },
            ]} />
            <p className="gv-ajuda">
              {modo === "novo" ? "Cria um lançamento com D0, hormônios e os eventos de cada etapa na Agenda." : "Os animais entram com o mesmo D0, nome e hormônios do protocolo escolhido."}
            </p>
          </Passo>

          <Passo n={2} id="iatf-p2" titulo="Matrizes" direita={
            <span className="rp-contagem" aria-live="polite">{nSel} de {visiveis.length} {nSel === 1 ? "marcada" : "marcadas"}{nConf > 0 && ` · ${nConf} pede(m) confirmação`}</span>
          }>
            <div className="rp-ferr">
              <PilulasX<"animais" | "lotes"> rotulo="Escolher por" valor={origem} onChange={(o) => { setOrigem(o); setLotesSel([]); }}
                opcoes={[{ id: "animais", nome: "Animais" }, { id: "lotes", nome: "Lotes", n: lotes.length }]} />
              <BuscaMatrizes valor={busca} onChange={setBusca} />
              <button type="button" className="btn-ghost" onClick={() => setSel((p) => alternaAptas(p, visiveis))}>Marcar / desmarcar as aptas</button>
              <button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!nSel}>Limpar</button>
            </div>
            {origem === "lotes" && (
              <Pilulas<string> rotulo="Lotes" valor={lotesSel} onChange={alternaLote} opcoes={lotes.map(([l, n]) => ({ id: l, nome: l, n }))} />
            )}
            <TabelaMatrizes matrizes={visiveis} sel={sel} mostrarProtocolo altura="48rem"
              vazio={origem === "lotes" ? "Marque um ou mais lotes acima." : "Nenhuma fêmea bate com a busca."}
              onToggle={(n) => setSel((p) => alterna(p, n))} onToggleAptas={() => setSel((p) => alternaAptas(p, visiveis))}
              onToggleLote={(_l, itens) => setSel((p) => alternaAptas(p, itens))} />
            <Ajuda>
              A lista mostra <strong>todas as fêmeas</strong>; as <strong>inaptas ficam em cinza</strong>, com o motivo (idade mínima de {IDADE_MIN_SERVICO} meses, animal baixado ou a descartar) e ainda podem ser marcadas — o servidor pede confirmação.
              Isto só agenda o protocolo hormonal: a inseminação em si (D{modo === "novo" ? diaIA : DIA_IA_PADRAO}) é lançada à parte, na tela <strong>Inseminação</strong>.
            </Ajuda>
          </Passo>

          <Passo n={3} id="iatf-p3" titulo={modo === "novo" ? "Protocolo e cronograma" : "Protocolo existente"}>
            {modo === "novo" ? (
              <>
                <div className="rp-grade-2">
                  <div className="rp-col">
                    <div className="gv-campo">
                      <label htmlFor="iatf-molde">Protocolo cadastrado (opcional)</label>
                      <select id="iatf-molde" className="rp-select" value={moldeId} onChange={(e) => setMoldeId(e.target.value)}>
                        <option value="">Sem molde — informar hormônios abaixo</option>
                        {MOLDES.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
                      </select>
                    </div>
                    <div className="gv-campo">
                      <label htmlFor="iatf-d0">Data do D0</label>
                      <input id="iatf-d0" type="date" className="rp-input" value={d0} onChange={(e) => setD0(e.target.value)} />
                    </div>
                    <div className="gv-campo">
                      <label htmlFor="iatf-nome">Nome do lançamento (automático)</label>
                      <input id="iatf-nome" className="rp-input" readOnly value={nome || "Informe a data do D0…"} style={{ fontVariantNumeric: "tabular-nums" }} />
                    </div>
                    <p className="gv-ajuda">
                      {molde
                        ? <>O molde <strong>manda nos dias e nos hormônios</strong>; para mudar dose, produto ou dia, edite em <strong>Central de Protocolos › Cadastro</strong>. Ao confirmar cada dia na Agenda você ainda escolhe o frasco em estoque do princípio ativo.</>
                        : <>Sem molde: cronograma clássico D0/D7/D9/D11 e hormônios digitados ao lado. A inseminação é sempre 2 dias depois da última etapa de hormônio.</>}
                    </p>
                  </div>
                  <div className="rp-bloco">
                    <div className="rp-bloco-t">Cronograma — vai para a Agenda de cada animal</div>
                    <LinhaDoTempo nos={nos} />
                    <p className="gv-ajuda" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.5rem" }}>
                      Ao salvar, cria os eventos D0 a D{diaIA} na Agenda para cada animal marcado ({nSel} × {nos.length} = <strong>{nSel * nos.length}</strong> eventos).
                    </p>
                  </div>
                </div>
                {!molde && <EditorHormonios linhas={hormonios} onChange={setHormonios} />}
              </>
            ) : (
              <>
                <div className="rp-grade-2e">
                  <div className="gv-campo">
                    <label htmlFor="iatf-exist">Protocolo em andamento</label>
                    <select id="iatf-exist" className="rp-select" value={existenteId} onChange={(e) => setExistenteId(e.target.value)}>
                      <option value="">Selecione o protocolo…</option>
                      {ANDAMENTO.map((p) => <option key={p.id} value={p.id}>{p.nome} — {p.animais.length} animais</option>)}
                    </select>
                  </div>
                  {existente && (
                    <div className="rp-bloco">
                      <div className="rp-bloco-t">O que muda no protocolo</div>
                      <div style={{ fontSize: "0.85rem" }}>
                        D0 <strong>{fmtData(existente.d0)}</strong> · hoje {existente.animais.length} animais → <strong>{existente.animais.length + nSel}</strong> com os {nSel} marcados.
                      </div>
                      <p className="gv-ajuda">Os eventos das etapas já vencidas também entram na Agenda dos novos animais — confira antes de lançar.</p>
                    </div>
                  )}
                </div>
              </>
            )}
          </Passo>
        </div>
      )}

      {aba === "lancar" && (
        <BarraAcao
          resumo={resumo}
          detalhe={detalhe}
          retorno={retorno && (
            <div className="rp-retorno-linha">
              {retorno === "sucesso" && (
                <>
                  <span className="rp-ok">✓ Protocolo “PROTOCOLO IATF - 14/10/26 A 25/10/26 (D0 A D11 - 12 DIAS)” agendado para 3 animais — 12 eventos na Agenda (D0 a D11).</span>
                  <span className="gv-espaco" style={{ flex: 1 }} />
                  <button type="button" className="btn-ghost" onClick={() => setAba("andamento")}>Ver em andamento</button>
                </>
              )}
              {retorno === "ja_lancado" && <span className="rp-mudo" role="status">Este protocolo já estava lançado para estes animais nesta data — nada foi duplicado.</span>}
              {retorno === "confirmar" && (
                <>
                  <span className="rp-err" role="alert">Novilha 1110 sem pesagem registrada: o peso mínimo não pôde ser conferido.</span>
                  <span style={{ flex: 1 }} />
                  <button type="button" className="btn-secondary" onClick={() => setRetorno("sucesso")}>Confirmar e lançar mesmo assim</button>
                </>
              )}
            </div>
          )}
          secundaria={<button type="button" className="btn-ghost" onClick={() => setSel(new Set())} disabled={!nSel}>Limpar</button>}
          acao={<BotaoOuro desabilitado={!podeSalvar} onClick={() => setRetorno("sucesso")}>{modo === "novo" ? `Lançar protocolo${nSel ? ` (${nSel})` : ""}` : `Adicionar${nSel ? ` ${nSel}` : ""} ao protocolo`}</BotaoOuro>}
        />
      )}
    </QuadroGaveta>
  );
}
