"use client";
import React, { Fragment, useEffect, useMemo, useRef, useState } from "react";
import {
  ClipboardList, Info, Heart, Stethoscope, Milk, Syringe, Wallet, Package, Baby, Scale,
  Search, ExternalLink, BookOpen, X, Plus, AlertTriangle, Trash2, Droplet, CalendarClock, Wheat,
  ChevronDown, ChevronRight,
} from "lucide-react";
import {
  fetchAnimais, fetchEstoque, fetchServicosAnalise, fetchSanidade, criarControlesLeiteiros, salvarDiagnostico, movimentarEstoque, criarAplicacaoSanidade, marcarEventoRealizado,
  fetchSecagemInfo, criarSecagem, sugestaoLoteEvento, criarMovimentacao, criarParto, formatDate,
  criarProtocoloIatf, criarServico, fetchProtocolosIatfAtivos,
  fetchEventosSanitarios, fetchDoencas, fetchPrincipiosAtivos, fetchCalendarioSanitario, criarCalendarioSanitario, atualizarCalendarioSanitario,
  fetchAlimentosPadrao, fetchDietas, criarDieta, encerrarDieta, registrarRealDieta, fetchComparativoDieta,
  fetchProtocolosSanitarios, lancarProtocoloSanitario, fetchLotes, previewCriteriosLote,
  fetchQualidadeLeite, criarQualidadeLeite, criarEntregaLeiteMensal, registrarColostragem,
} from "@/lib/api";
import { RESPONSAVEIS, VIAS_APLICACAO } from "@/lib/constants";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { SelecaoAnimaisTabela } from "@/components/SelecaoAnimaisTabela";
import { SelecaoLotesTabela, LoteRow } from "@/components/SelecaoLotesTabela";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import { FormExclusao } from "@/components/FormExclusao";
import { FormPesagemCorporal } from "@/components/FormPesagemCorporal";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { TabBar, SecaoRecolhivel } from "@/components/ui";

type EstoqueItem = { nome: string; quantidade?: number | null; unidade?: string | null; categoria?: string | null; estocavel?: boolean | null };

/**
 * Tela de Lançamentos — entrada de dados operacionais no sistema.
 * Cada tipo (reprodutivo, produção, sanidade, financeiro, dieta, estoque,
 * exclusão) tem um formulário próprio que reage aos dados reais do rebanho
 * (selects, DEL automático, cálculos de colostro, cronograma de IATF) e
 * GRAVA de verdade no banco. A faixa informativa no topo de cada tipo
 * (ver "banner por tipo" no fim do arquivo) descreve o que cada lançamento faz.
 */

const LINK_COLOSTRO = "https://altagenetics.inf.br/shared/Circulares/Informativo_formas%20de%20utiliza%C3%A7%C3%A3o%20colostro_site.pdf";
const cod = (g: string | null | undefined) => (g && /^\d\d/.test(g) ? g.slice(0, 2) : "");
const LACT = ["01", "02", "03"];
const IDADE_MIN_SERVICO = 13; // meses — abaixo disso a fêmea não é apta a serviço
// Sêmen (touros) atualmente em estoque — usados na seleção do touro em Serviço/IA.
const TOUROS_ESTOQUE = [
  "ABS LABEL", "CAMPEAO FI", "COORS", "DESCONHECIDO", "GUINESS", "HAGEN", "HILLUX", "JAG", "LUZIO",
  "MESSI", "METEORO", "MOSAIC", "NABIL", "PRAFESS", "ROBO", "STORMY", "SUCESSOR", "VALENTE", "VICTINHO",
];
const UNIDADES = ["ml", "kg", "L", "unidade", "dose", "saca 30kg", "saca 60kg"];
const MOVIMENTOS_ESTOQUE = ["Aplicação", "Saída de ajuste", "Entrada de ajuste", "Entrada de cortesia", "Doação"];
// Movimentos que reduzem o estoque (baixa).
const MOV_BAIXA = new Set(["Aplicação", "Saída de ajuste", "Doação"]);
const MOVIMENTOS_SOMENTE_ESTOCAVEL = new Set(["Doação", "Entrada de cortesia"]);

const inputStyle: React.CSSProperties = {
  width: "100%", background: "var(--surface-2)", color: "var(--text)",
  border: "1px solid var(--border)", borderRadius: "6px", padding: "0.45rem 0.6rem", fontSize: "0.85rem",
};
const lbl: React.CSSProperties = { fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" };
const nota: React.CSSProperties = { fontSize: "0.7rem", color: "var(--text-muted)", marginLeft: "0.35rem" };

function Campo({ label, children, full }: { label: string; children: React.ReactNode; full?: boolean }) {
  return <div style={{ gridColumn: full ? "1 / -1" : undefined }}><label style={lbl}>{label}</label>{children}</div>;
}

function addDias(iso: string, n: number): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n);
  return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
}

// Seleção de animal via tabela clara (Nº · Grupo · Categoria · Sit. Rep. · DEL).
const SelectAnimal = AnimalPicker;

/* ───────────────────────── Manual do colostro (modal em tela) ───────────────────────── */
const MANUAL_COLOSTRO = [
  { t: "1. Nascimento e ordenha rápida", d: "Curar umbigo (iodo 10%). Ordenhar a vaca na 1ª HORA pós-parto, com higiene total dos tetos. Coletar todo o colostro em balde limpo. Meta: ordenhar dentro da 1ª hora." },
  { t: "2. Teste de qualidade (Brix)", d: "Misturar o colostro. Pingar 2 gotas no refratômetro limpo e ler a escala Brix contra a luz." },
  { t: "3. A decisão", d: ">25% (OURO): congelar/dar (excelente). 18–25% (PRATA): enriquecer com pó até 25% (médio). <18% (BRONZE): descartar 1ª mamada (ruim) — apenas se o estoque estiver cheio." },
  { t: "4. Banco de colostro (congelamento)", d: "2 L de colostro OURO (>25%) no saco. Tirar o ar, selar, etiquetar (data, vaca, Brix), deitar na forma e congelar." },
  { t: "5. A hora de mamar", d: "Descongelar em banho-maria (máx. 50°C — use termômetro!). Fornecer a 37°C. Volume: 10% do peso vivo (aprox. 4 L)." },
  { t: "6. O tira-teima (monitoramento)", d: "Coletar sangue da bezerra entre 24h e 48h de vida. Separar o soro e medir no refratômetro. Meta: Brix do soro > 8,4%." },
];
const MANUAL_SANGUE = [
  { t: "1. O momento certo", d: "Coletar entre 24h e 48h após o nascimento. Antes de 24h a absorção continua; após 48h perde precisão." },
  { t: "2. A coleta", d: "Conter a bezerra. Agulha e tubo limpos (tampa vermelha). Coletar 5 ml da veia jugular. Higiene total." },
  { t: "3. Separação do soro", d: "Deixar o tubo em pé em temperatura ambiente por 2–4 horas. O sangue coagula e libera o soro (líquido amarelo)." },
  { t: "4. Leitura no refratômetro", d: "Limpar o refratômetro. Pingar uma gota do SORO amarelo (não o sangue). Ler a escala Brix contra a luz." },
  { t: "5. Resultado e ação", d: "≥ 8,4% (sucesso): manter rotina, bezerra protegida. 8,1–8,3% (alerta): monitorar e revisar rotina de colostro. ≤ 8,0% (falha): ação urgente, bezerra desprotegida." },
  { t: "6. Ação urgente (falha ≤ 8,0%)", d: "1) Isolar a bezerra. 2) Monitorar temperatura 2x/dia. 3) Avisar Vet/Gerente. 4) Auditar urgente a rotina de colostro." },
];

function ManualColostroModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "500px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Manual — Rotina do Colostro</div>
          <button onClick={onClose} title="Fechar" aria-label="Fechar" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="space-y-2">
          {MANUAL_COLOSTRO.map((s) => (
            <div key={s.t} style={{ borderLeft: "3px solid var(--green-light)", paddingLeft: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
            </div>
          ))}
        </div>
        <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="flex items-center gap-2 mt-4" style={{ color: "var(--dourado-light)", fontSize: "0.8rem" }}>
          <ExternalLink size={14} /> Abrir a tabela oficial da Alta (PDF)
        </a>
      </div>
    </div>
  );
}

function ManualSangueModal({ onClose }: { onClose: () => void }) {
  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60, padding: "1rem" }} onClick={onClose}>
      <div className="card" style={{ width: "500px", maxWidth: "96vw", maxHeight: "88vh", overflowY: "auto" }} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <div className="card-header" style={{ margin: 0 }}>Manual — Teste de Sangue (IgG)</div>
          <button onClick={onClose} title="Fechar" aria-label="Fechar" style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer" }}><X size={20} /></button>
        </div>
        <div className="space-y-2">
          {MANUAL_SANGUE.map((s) => (
            <div key={s.t} style={{ borderLeft: "3px solid var(--blue)", paddingLeft: "0.6rem" }}>
              <p style={{ fontSize: "0.8rem", fontWeight: 700 }}>{s.t}</p>
              <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>{s.d}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ───────────────────────── Formulários por tipo ───────────────────────── */

// Subtítulo de seção dentro de um formulário.
const Secao = ({ children }: { children: React.ReactNode }) => (
  <p style={{ fontSize: "0.72rem", fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase", color: "var(--dourado-light)", margin: "1rem 0 0.5rem" }}>{children}</p>
);

const HORMONIOS: Record<string, string[]> = {
  progesterona: ["Sincrogest", "Cidr"],
  benzoato: ["Sincrodiol"],
  buserelina: ["Sincroforte"],
  cloprostenol: ["Estron"],
  cipionato: ["SincroCP"],
};

type ProtocoloIatfAtivo = {
  lancamento_id: number; nome_protocolo: string; data_d0: string;
  animais: { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null }[];
};

function ProtocolosIatfAtivos({ recarregarRef }: { recarregarRef: React.MutableRefObject<() => void> }) {
  const [ativos, setAtivos] = useState<ProtocoloIatfAtivo[] | null>(null);
  const [abertos, setAbertos] = useState<Set<number>>(new Set());
  const toggle = (id: number) => setAbertos((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const carregar = () => fetchProtocolosIatfAtivos().then(setAtivos).catch(() => setAtivos([]));
  useEffect(() => { carregar(); recarregarRef.current = carregar; }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!ativos || !ativos.length) return null;
  return (
    <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
      <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
        Protocolos IATF em andamento ({ativos.length})
      </div>
      <div className="space-y-2">
        {ativos.map((p) => {
          const aberto = abertos.has(p.lancamento_id);
          return (
            <div key={p.lancamento_id} style={{ border: "1px solid var(--border)", borderRadius: "8px", overflow: "hidden" }}>
              <button onClick={() => toggle(p.lancamento_id)} title={aberto ? "Clique para recolher os animais" : "Clique para ver os animais e etapas"} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.8rem", background: "var(--surface)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                {aberto ? <ChevronDown size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} /> : <ChevronRight size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />}
                <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{p.nome_protocolo}</span>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>D0 {formatDate(p.data_d0)} — {p.animais.length} animal(is)</span>
              </button>
              {aberto && (
                <table className="fazenda-table" style={{ margin: 0 }}>
                  <thead><tr><th>Nº</th><th>Etapa atual</th><th>Data</th></tr></thead>
                  <tbody>
                    {p.animais.map((a) => (
                      <tr key={a.numero_matriz}>
                        <td style={{ fontWeight: 700 }}>{a.numero_matriz}</td>
                        <td>{a.etapa_atual}</td>
                        <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{a.data_etapa_atual ? formatDate(a.data_etapa_atual) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function FormProtocoloIatf({ animais }: { animais: AnimalRow[] }) {
  const [emLote, setEmLote] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [um, setUm] = useState("");
  const [d0, setD0] = useState("");
  const [nomeProtocolo, setNomeProtocolo] = useState("Protocolo padrão");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const recarregarAtivosRef = useRef(() => {});
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleTodos = () => setSel((p) => (p.size === animais.length && animais.length ? new Set() : new Set(animais.map((a) => a.numero))));

  async function salvar() {
    setErro(null); setSucesso(null);
    const animaisAlvo = emLote ? Array.from(sel) : (um ? [um] : []);
    if (!animaisAlvo.length) { setErro(emLote ? "Selecione ao menos um animal." : "Selecione a matriz."); return; }
    if (!d0) { setErro("Informe a data do D0."); return; }
    setSalvando(true);
    try {
      const r = await criarProtocoloIatf({ animais: animaisAlvo, data_d0: d0, protocolo: nomeProtocolo });
      setSucesso(`Protocolo agendado para ${r.animais} animal(is) — ${r.eventos_criados} eventos criados na Agenda (D0/D7/D9/D11).`);
      setSel(new Set()); setUm("");
      recarregarAtivosRef.current();
    } catch (e: any) {
      setErro(e.message || "Erro ao agendar protocolo IATF");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Protocolo">
          <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}>
            <input type="checkbox" checked={emLote} onChange={(e) => setEmLote(e.target.checked)} /> Em lote (vários animais)
          </label>
        </Campo>
        <Campo label="Data do D0"><input type="date" style={inputStyle} value={d0} onChange={(e) => setD0(e.target.value)} /></Campo>
        <Campo label="Nome do protocolo"><input style={inputStyle} value={nomeProtocolo} onChange={(e) => setNomeProtocolo(e.target.value)} /></Campo>
      </div>
      <div className="mt-3">
        <label style={lbl}>Matriz (nº)</label>
        {emLote
          ? <SelecaoAnimaisTabela
              animais={animais} selecionados={sel} toggle={toggle} toggleTodos={toggleTodos}
              colunas={[
                { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                { header: "Lote", render: (a) => a.grupo_primario || "—" },
              ]}
            />
          : <SelectAnimal animais={animais} value={um} onChange={setUm} placeholder="Selecione a matriz…" />}
      </div>
      <p style={nota}>Matriz lista apenas fêmeas aptas (≥ {IDADE_MIN_SERVICO} meses). Isso só agenda o protocolo hormonal — a inseminação em si (D11) é lançada à parte, na sub-aba Inseminação.</p>

      <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
        <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
          Cronograma IATF — vai para a Agenda
        </div>
        <div className="overflow-x-auto">
          <table className="fazenda-table">
            <thead><tr><th>Dia</th><th>Data</th><th>Ação / hormônio</th></tr></thead>
            <tbody>
              <tr><td style={{ fontWeight: 700 }}>D0</td><td>{addDias(d0, 0)}</td><td>Implante de progesterona + Benzoato de estradiol + Acetato de buserelina</td></tr>
              <tr><td style={{ fontWeight: 700 }}>D7</td><td>{addDias(d0, 7)}</td><td>Cloprostenol</td></tr>
              <tr><td style={{ fontWeight: 700 }}>D9</td><td>{addDias(d0, 9)}</td><td>Retirar implante + Cipionato de estradiol + Cloprostenol</td></tr>
              <tr><td style={{ fontWeight: 700, color: "var(--green-light)" }}>D11</td><td>{addDias(d0, 11)}</td><td style={{ color: "var(--green-light)" }}>Inseminação (IATF)</td></tr>
            </tbody>
          </table>
        </div>
        <p style={nota}>Ao salvar, cria os eventos D0/D7/D9/D11 na Agenda para cada animal selecionado.</p>
      </div>
      <ProtocolosIatfAtivos recarregarRef={recarregarAtivosRef} />
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

function FormInseminacao({ animais }: { animais: AnimalRow[] }) {
  const [matriz, setMatriz] = useState("");
  const [veioDeProtocolo, setVeioDeProtocolo] = useState(false);
  const [nomeProtocolo, setNomeProtocolo] = useState("Protocolo padrão");
  const [dataServico, setDataServico] = useState("");
  const [touro, setTouro] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Vindo da Agenda (link "Ir para Inseminação" do D11 de um protocolo IATF) —
  // pré-seleciona a matriz e o nome do protocolo.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const numeroMatriz = qs.get("numero_matriz");
    const protocolo = qs.get("protocolo");
    if (numeroMatriz) setMatriz(numeroMatriz);
    if (protocolo) { setVeioDeProtocolo(true); setNomeProtocolo(protocolo); }
  }, []);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!matriz) { setErro("Selecione a matriz."); return; }
    if (!dataServico) { setErro("Informe a data da inseminação."); return; }
    setSalvando(true);
    try {
      const r = await criarServico({
        numero_matriz: matriz, data_servico: dataServico,
        tipo_servico: "IA", protocolo: veioDeProtocolo ? nomeProtocolo : undefined,
        reprodutor: touro || undefined, responsavel: responsavel || undefined,
      });
      setSucesso(`Inseminação registrada (tentativa ${r.ordem_tentativa}${r.protocolo ? `, protocolo ${r.protocolo}` : " — cio natural"}).`);
      setMatriz(""); setTouro(""); setVeioDeProtocolo(false);
    } catch (e: any) {
      setErro(e.message || "Erro ao registrar inseminação");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Matriz (nº)"><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz…" /></Campo>
        <Campo label="Data da inseminação"><input type="date" style={inputStyle} value={dataServico} onChange={(e) => setDataServico(e.target.value)} /></Campo>
        <Campo label="Veio de um protocolo IATF já agendado?">
          <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}>
            <input type="checkbox" checked={veioDeProtocolo} onChange={(e) => setVeioDeProtocolo(e.target.checked)} /> Sim
          </label>
        </Campo>
        {veioDeProtocolo && <Campo label="Nome do protocolo"><input style={inputStyle} value={nomeProtocolo} onChange={(e) => setNomeProtocolo(e.target.value)} /></Campo>}
        <Campo label="Touro / sêmen (em estoque)">
          <select style={inputStyle} value={touro} onChange={(e) => setTouro(e.target.value)}><option value="">Selecione o sêmen…</option>{TOUROS_ESTOQUE.map((t) => <option key={t}>{t}</option>)}</select>
        </Campo>
        <Campo label="Responsável / inseminador">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="">Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select>
        </Campo>
      </div>
      <p style={nota}>
        Matriz lista apenas fêmeas aptas (≥ {IDADE_MIN_SERVICO} meses).{" "}
        {veioDeProtocolo ? "Marca esta inseminação como a etapa D11 do protocolo informado." : "Sem protocolo marcado: registra como cio natural, sem cronograma hormonal."}
      </p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

function FormDiagnostico({ animais, ultServico }: { animais: AnimalRow[]; ultServico: Record<string, string> }) {
  // Lista as matrizes servidas (inseminadas ou prenhes a reconfirmar).
  const servidas = useMemo(() => animais.filter((a) => a.sit_rep === "Ins." || a.sit_rep === "Ges."), [animais]);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const toggle = (n: string) => setSelecionados((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleTodos = () => setSelecionados((p) => (p.size === servidas.length && servidas.length ? new Set() : new Set(servidas.map((a) => a.numero))));
  const [data, setData] = useState("");
  const [metodo, setMetodo] = useState("");
  const [resultado, setResultado] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Animais selecionados com menos de 30 dias desde a última inseminação/cobertura.
  const animaisComAviso = useMemo(() => {
    if (!data) return [];
    return Array.from(selecionados).filter((n) => {
      const us = ultServico[n];
      if (!us) return false;
      const dias = (new Date(data + "T00:00:00").getTime() - new Date(us + "T00:00:00").getTime()) / 86400000;
      return dias >= 0 && dias < 30;
    });
  }, [selecionados, data, ultServico]);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!selecionados.size || !data || !resultado) { setErro("Selecione ao menos uma matriz, a data e o resultado do diagnóstico."); return; }
    setSalvando(true);
    // Loop por animal: registra quais salvaram e quais falharam, para não perder
    // o trabalho já feito nem a seleção dos que precisam de nova tentativa.
    const salvos: string[] = [];
    const falhados: string[] = [];
    try {
      for (const numero of selecionados) {
        try {
          await salvarDiagnostico({ numero_matriz: numero, data_diagnostico: data, resultado: resultado as any, metodo: metodo || undefined });
          salvos.push(numero);
        } catch {
          falhados.push(numero);
        }
      }
      if (falhados.length) {
        // Sucesso parcial: mantém selecionados só os que falharam, para reenviar.
        setSelecionados(new Set(falhados));
        if (salvos.length) {
          setSucesso(`Salvos: ${salvos.length}.`);
          setErro(`Falharam: ${falhados.join(", ")} — tente novamente só esses.`);
        } else {
          setErro(`Nenhum diagnóstico salvo. Falharam: ${falhados.join(", ")} — tente novamente.`);
        }
      } else {
        setSucesso(
          resultado === "retoque"
            ? `Diagnóstico salvo para ${salvos.length} animal(is). Entraram na agenda para retoque.`
            : `Diagnóstico salvo para ${salvos.length} animal(is).`
        );
        setSelecionados(new Set()); setData(""); setMetodo(""); setResultado("");
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar diagnóstico");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <Campo label="Matriz / novilha (servidas) — pode selecionar várias" full>
        <SelecaoAnimaisTabela
          animais={servidas} selecionados={selecionados} toggle={toggle} toggleTodos={toggleTodos}
          colunas={[
            { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
            { header: "Lote", render: (a) => a.grupo_primario || "—" },
            { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
            { header: "Última IA/cobertura", render: (a) => ultServico[a.numero] ? new Date(ultServico[a.numero] + "T00:00:00").toLocaleDateString("pt-BR") : "—" },
          ]}
        />
      </Campo>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <Campo label="Data do diagnóstico"><input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></Campo>
        <Campo label="Método">
          <select style={inputStyle} value={metodo} onChange={(e) => setMetodo(e.target.value)}>
            <option value="" disabled>Selecione…</option><option>Palpação</option><option>Ultrassom</option>
          </select>
        </Campo>
        <Campo label="Resultado" full>
          <select style={inputStyle} value={resultado} onChange={(e) => setResultado(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            <option value="retoque">Positivo — marcar para retoque (segue em observação para reconfirmar)</option>
            <option value="reconfirmada">Positivo — reconfirmada (prenhez confirmada)</option>
            <option value="negativo">Negativo ou indefinido</option>
          </select>
        </Campo>
      </div>

      {animaisComAviso.length > 0 && (
        <div className="mt-3" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", background: "rgba(217,119,6,0.12)", border: "1px solid var(--amber)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
          <AlertTriangle size={16} style={{ color: "var(--amber)", marginTop: "0.1rem" }} />
          <span style={{ fontSize: "0.8rem" }}>
            {animaisComAviso.length} animal(is) com menos de 30 dias da última inseminação/cobertura: {animaisComAviso.join(", ")}. Deseja confirmar mesmo assim?
          </span>
        </div>
      )}
      {resultado === "negativo" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Ao confirmar, os animais ficam como <strong>vazia</strong> e serão colocados para observação no próximo serviço.
        </p>
      )}
      {resultado === "retoque" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Os animais entram na <strong>agenda para retoque</strong>, no dia do próximo serviço.
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

// Classificação padrão ouro/prata/bronze (manual da fazenda):
//  > 25% OURO (excelente) · 18–25% PRATA (médio, enriquecer) · < 18% BRONZE (ruim).
// Tabela de enriquecimento: medidas de pó por litro = Brix alvo − Brix atual.
function classeColostro(brix: number): { txt: string; cor: string } {
  if (brix > 25) return { txt: "Ouro (excelente)", cor: "var(--dourado-light)" };
  if (brix >= 18) return { txt: "Prata (médio — enriquecer)", cor: "var(--text-muted)" };
  return { txt: "Bronze (ruim — descartar 1ª mamada)", cor: "var(--red)" };
}

// Brix do soro (teste de IgG): >=8,4 sucesso; 8,1-8,3 alerta; <=8,0 falha.
function classeSoro(brix: number): { txt: string; cor: string } {
  if (brix >= 8.4) return { txt: "Sucesso — bezerra protegida", cor: "var(--green-light)" };
  if (brix >= 8.1) return { txt: "Alerta — monitorar, revisar colostro", cor: "var(--amber)" };
  return { txt: "Falha — bezerra desprotegida (ação urgente)", cor: "var(--red)" };
}
const OPCOES_SORO = Array.from({ length: 13 }, (_, i) => (6 + i * 0.5).toFixed(1)); // 6,0 … 12,0

function FormParto({ animais }: { animais: AnimalRow[] }) {
  const [matriz, setMatriz] = useState("");
  const [dataParto, setDataParto] = useState(() => new Date().toISOString().slice(0, 10));
  const [tipoParto, setTipoParto] = useState("");
  const [gemelar, setGemelar] = useState(false);
  const [criaNumero, setCriaNumero] = useState("");
  const [criaSexo, setCriaSexo] = useState("");
  const [criaBaixada, setCriaBaixada] = useState(false);
  const [cria2Numero, setCria2Numero] = useState("");
  const [cria2Sexo, setCria2Sexo] = useState("");
  const [cria2Baixada, setCria2Baixada] = useState(false);
  const [retencaoPlacenta, setRetencaoPlacenta] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const [tomouColostro, setTomou] = useState("");
  const [litros, setLitros] = useState("");
  const [brix, setBrix] = useState("");
  const [alvo, setAlvo] = useState("25");
  const [manualColostroAberto, setManualColostroAberto] = useState(false);
  const [manualSangueAberto, setManualSangueAberto] = useState(false);

  const [soro, setSoro] = useState("");
  const brixN = brix ? Number(brix) : null;
  const litrosN = litros ? Number(litros) : 0;
  const cls = brixN != null ? classeColostro(brixN) : null;
  const soroN = soro ? Number(soro) : null;
  const clsSoro = soroN != null ? classeSoro(soroN) : null;
  const enriquecer = brixN != null && brixN < 25;
  const medidasPorL = enriquecer ? Math.max(0, Number(alvo) - brixN!) : 0;
  const totalMedidas = medidasPorL * (litrosN || 1);

  async function alocarSeConfirmado(numero: string, categoriaAbrev: string, extra: { del_dias?: number | null; data_nasc?: string | null }, motivo: string, falhas: string[]) {
    try {
      const { lote_sugerido } = await sugestaoLoteEvento({ numero_matriz: numero, categoria_abrev: categoriaAbrev, ...extra });
      if (lote_sugerido && window.confirm(`Alocar o animal ${numero} no lote ${lote_sugerido.rotulo}? Ele ainda não tem lote definido.`)) {
        await criarMovimentacao({ data_movimento: dataParto, motivo, lote_destino_codigo: lote_sugerido.codigo, animais: [numero] });
        return lote_sugerido.rotulo as string;
      }
    } catch (e: any) {
      // Sugestão/alocação é best-effort — não bloqueia o parto já salvo, mas
      // avisamos para o usuário não achar que o animal já foi movido de lote.
      falhas.push(`alocação do animal ${numero} não pôde ser feita${e?.message ? `: ${e.message}` : ""}`);
    }
    return null;
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!matriz) { setErro("Selecione a matriz que pariu."); return; }
    const crias = [
      ...(criaNumero ? [{ numero: criaNumero, sexo: criaSexo === "Macho" ? "M" : "F", nasceu_viva: !criaBaixada }] : []),
      ...(gemelar && cria2Numero ? [{ numero: cria2Numero, sexo: cria2Sexo === "Macho" ? "M" : "F", nasceu_viva: !cria2Baixada }] : []),
    ];
    setSalvando(true);
    try {
      const r = await criarParto({
        numero_matriz: matriz, data_parto: dataParto, tipo_parto: tipoParto || undefined,
        crias, retencao_placenta: retencaoPlacenta, gemelar,
      });
      // Efeitos colaterais do parto (alocação de lote e colostragem) são
      // complementares: não bloqueiam o parto já salvo, mas as falhas são
      // coletadas para avisar o usuário no fim, em vez de sumirem em silêncio.
      const falhasEfeito: string[] = [];
      const alocacoes: string[] = [];
      const rotuloMae = await alocarSeConfirmado(matriz, "Vaca", { del_dias: 0 }, "Parto", falhasEfeito);
      if (rotuloMae) alocacoes.push(`${matriz} → ${rotuloMae}`);
      for (const c of r.crias_criadas as string[]) {
        const sexoCria = c === cria2Numero ? cria2Sexo : criaSexo;
        const rotulo = await alocarSeConfirmado(c, sexoCria === "Macho" ? "Bezerro" : "Bezerra", { data_nasc: dataParto }, "Nascimento", falhasEfeito);
        if (rotulo) alocacoes.push(`${c} → ${rotulo}`);
      }
      // Colostragem/IgG acima descrevem só a 1ª cria (o formulário tem um único
      // bloco de colostro mesmo em parto gemelar) — grava se a cria foi criada
      // e algum dado foi informado.
      const criaRegistrada = r.crias_criadas.includes(criaNumero);
      if (criaRegistrada && (tomouColostro || litros || brix || soro)) {
        try {
          await registrarColostragem({
            numero_animal: criaNumero,
            tomou_colostro: tomouColostro ? tomouColostro === "Sim" : undefined,
            litros_colostro: litrosN || undefined,
            brix_colostro: brixN ?? undefined,
            data_colostro: brix ? dataParto : undefined,
            brix_soro: soroN ?? undefined,
            data_teste_sangue: soro ? dataParto : undefined,
          });
        } catch (e: any) {
          falhasEfeito.push(`a colostragem não pôde ser gravada${e?.message ? `: ${e.message}` : ""}`);
        }
      }
      setSucesso(`Parto registrado (ordem ${r.ordem_parto}).${r.crias_criadas.length ? ` Cria(s) cadastrada(s): ${r.crias_criadas.join(", ")}.` : ""}${alocacoes.length ? ` Alocação: ${alocacoes.join("; ")}.` : ""}${falhasEfeito.length ? ` Atenção: ${falhasEfeito.join("; ")}.` : ""}`);
      setMatriz(""); setTipoParto(""); setGemelar(false);
      setCriaNumero(""); setCriaSexo(""); setCriaBaixada(false);
      setCria2Numero(""); setCria2Sexo(""); setCria2Baixada(false);
      setRetencaoPlacenta(false);
      setTomou(""); setLitros(""); setBrix(""); setSoro("");
    } catch (e: any) {
      setErro(e.message || "Erro ao registrar parto");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      {manualColostroAberto && <ManualColostroModal onClose={() => setManualColostroAberto(false)} />}
      {manualSangueAberto && <ManualSangueModal onClose={() => setManualSangueAberto(false)} />}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Matriz (nº)"><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz que pariu…" /></Campo>
        <Campo label="Data do parto"><input type="date" style={inputStyle} value={dataParto} onChange={(e) => setDataParto(e.target.value)} /></Campo>
        <Campo label="Tipo de parto">
          <select style={inputStyle} value={tipoParto} onChange={(e) => setTipoParto(e.target.value)}>
            <option value="">Selecione…</option><option>Normal</option><option>Distócico</option><option>Cesariana</option>
          </select>
        </Campo>
        <Campo label="Retenção de placenta"><label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}><input type="checkbox" checked={retencaoPlacenta} onChange={(e) => setRetencaoPlacenta(e.target.checked)} /> Sim</label></Campo>
        <Campo label="Parto gemelar (2 crias)"><label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}><input type="checkbox" checked={gemelar} onChange={(e) => setGemelar(e.target.checked)} /> Sim</label></Campo>
      </div>

      <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
        <div className="card-header mb-2 flex items-center gap-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
          <Baby size={14} /> Cadastro da cria (prole)
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Campo label="Número da cria"><input style={inputStyle} value={criaNumero} onChange={(e) => setCriaNumero(e.target.value)} placeholder="ex.: 483" /></Campo>
          <Campo label="Sexo da cria"><select style={inputStyle} value={criaSexo} onChange={(e) => setCriaSexo(e.target.value)}><option value="" disabled>Selecione…</option><option>Fêmea</option><option>Macho</option></select></Campo>
          <Campo label="Cria baixada? (não entra no rebanho)">
            <select style={inputStyle} value={criaBaixada ? "Sim" : "Não"} onChange={(e) => setCriaBaixada(e.target.value === "Sim")}><option>Não</option><option>Sim</option></select>
          </Campo>
        </div>
        {gemelar && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3" style={{ borderTop: "1px solid var(--border)", paddingTop: "0.75rem" }}>
            <Campo label="Número da 2ª cria"><input style={inputStyle} value={cria2Numero} onChange={(e) => setCria2Numero(e.target.value)} placeholder="ex.: 484" /></Campo>
            <Campo label="Sexo da 2ª cria"><select style={inputStyle} value={cria2Sexo} onChange={(e) => setCria2Sexo(e.target.value)}><option value="" disabled>Selecione…</option><option>Fêmea</option><option>Macho</option></select></Campo>
            <Campo label="2ª cria baixada?">
              <select style={inputStyle} value={cria2Baixada ? "Sim" : "Não"} onChange={(e) => setCria2Baixada(e.target.value === "Sim")}><option>Não</option><option>Sim</option></select>
            </Campo>
          </div>
        )}

        <div className="mt-3" style={{ background: "rgba(22,101,52,0.12)", border: "1px solid var(--green-light)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
          <p style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--green-light)" }}>Colostragem da cria</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            <Campo label="Tomou colostro?"><select style={inputStyle} value={tomouColostro} onChange={(e) => setTomou(e.target.value)}><option value="" disabled>Selecione…</option><option>Sim</option><option>Não</option></select></Campo>
            <Campo label="Quantidade de colostro (litros)">
              <select style={inputStyle} value={litros} onChange={(e) => setLitros(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {["1", "1.5", "2", "2.5", "3", "3.5", "4", "4.5", "5"].map((l) => <option key={l} value={l}>{l} L</option>)}
              </select>
            </Campo>
            <Campo label="Brix do colostro (%)">
              <select style={inputStyle} value={brix} onChange={(e) => setBrix(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {Array.from({ length: 21 }, (_, i) => 15 + i).map((b) => <option key={b} value={b}>{b}%</option>)}
              </select>
            </Campo>
          </div>

          {cls && (
            <div className="mt-2" style={{ fontSize: "0.82rem" }}>
              Qualidade: <strong style={{ color: cls.cor }}>{cls.txt}</strong>
              {enriquecer && (
                <div style={{ marginTop: "0.5rem", background: "rgba(94,26,46,0.2)", border: "1px solid var(--border)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
                  <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                    <span>Enriquecer até</span>
                    <select style={{ ...inputStyle, width: "auto", padding: "0.2rem 0.4rem" }} value={alvo} onChange={(e) => setAlvo(e.target.value)}>
                      {["22", "23", "24", "25", "26", "27", "28", "29", "30"].map((a) => <option key={a} value={a}>{a}%</option>)}
                    </select>
                  </div>
                  <p style={{ marginTop: "0.4rem" }}>
                    Adicionar <strong style={{ color: "var(--dourado-light)" }}>{medidasPorL} medida(s) de colostro em pó por litro</strong> (15 g cada).
                    {litrosN > 0 && <> Para {litrosN} L: <strong>{totalMedidas} medidas ≈ {totalMedidas * 15} g</strong>.</>}
                  </p>
                </div>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 mt-2" style={{ flexWrap: "wrap" }}>
            <button onClick={() => setManualColostroAberto(true)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><BookOpen size={13} /> Manual do colostro</button>
            <a href={LINK_COLOSTRO} target="_blank" rel="noreferrer" className="flex items-center gap-1" style={{ color: "var(--dourado-light)", fontSize: "0.75rem" }}><ExternalLink size={13} /> Tabela oficial (PDF)</a>
          </div>
        </div>

        <div className="mt-3" style={{ background: "rgba(30,111,168,0.1)", border: "1px solid var(--blue)", borderRadius: "8px", padding: "0.6rem 0.8rem" }}>
          <p style={{ fontSize: "0.8rem", fontWeight: 700, color: "var(--blue)" }}>Exame de sangue (IgG) da cria</p>
          <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
            Colher entre <strong>24h e 48h</strong> após o nascimento. Meta: Brix do soro &gt; 8,4%
            (≥ 8,4% sucesso · 8,1–8,3% alerta · ≤ 8,0% falha).
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            <Campo label="Brix do soro (%)">
              <select style={inputStyle} value={soro} onChange={(e) => setSoro(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {OPCOES_SORO.map((v) => <option key={v} value={v}>{v.replace(".", ",")}%</option>)}
              </select>
            </Campo>
            {clsSoro && <div style={{ display: "flex", alignItems: "flex-end" }}><p style={{ fontSize: "0.82rem" }}>Resultado: <strong style={{ color: clsSoro.cor }}>{clsSoro.txt}</strong></p></div>}
          </div>
          <div className="flex items-center gap-3 mt-2" style={{ flexWrap: "wrap" }}>
            <button onClick={() => setManualSangueAberto(true)} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><BookOpen size={13} /> Manual do sangue</button>
          </div>
        </div>
      </div>
      <p style={nota}>
        Matriz, data, tipo de parto, crias e retenção de placenta já gravam de verdade. Ao salvar, sugere o lote da
        mãe e de cada cria (confirmação antes de mover). Colostragem e IgG da 1ª cria também são gravadas — o
        histórico completo aparece em Sanidade → Relatório sanitário de bezerras.
      </p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

function FormControle({ animais, lotesLact }: { animais: AnimalRow[]; lotesLact: string[] }) {
  const [modo, setModo] = useState<"vaca" | "lote">("vaca");
  const [vaca, setVaca] = useState("");
  const [lote, setLote] = useState("");
  const [nOrd, setNOrd] = useState(2);
  const [ord, setOrd] = useState<string[]>(["", "", ""]);
  const [porVaca, setPorVaca] = useState<Record<string, string[]>>({});
  const [dataControle, setDataControle] = useState(() => new Date().toISOString().slice(0, 10));
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const del = useMemo(() => animais.find((a) => a.numero === vaca)?.del_dias ?? null, [animais, vaca]);
  const total = ord.slice(0, nOrd).reduce((s, v) => s + (Number(v) || 0), 0);

  // Vacas do lote selecionado — abre a listagem individual pra pesagem de cada uma.
  const vacasDoLote = useMemo(() => (lote ? animais.filter((a) => a.grupo_primario === lote) : []), [animais, lote]);
  const ordVacas = useOrdenacao(vacasDoLote);
  const setOrdVaca = (numero: string, idx: number, valor: string) =>
    setPorVaca((p) => { const arr = [...(p[numero] || ["", "", ""])]; arr[idx] = valor; return { ...p, [numero]: arr }; });
  const totalVaca = (numero: string) => (porVaca[numero] || []).slice(0, nOrd).reduce((s, v) => s + (Number(v) || 0), 0);
  const totalLote = vacasDoLote.reduce((s, a) => s + totalVaca(a.numero), 0);

  function limpar() {
    setOrd(["", "", ""]);
    setPorVaca({});
  }

  async function salvar() {
    setErro(null); setSucesso(null);
    const entradas = modo === "vaca"
      ? (vaca ? [{ numero_matriz: vaca, ordenhas: ord.slice(0, nOrd).map((v) => Number(v) || 0) }] : [])
      : vacasDoLote.map((a) => ({ numero_matriz: a.numero, ordenhas: (porVaca[a.numero] || []).slice(0, nOrd).map((v) => Number(v) || 0) }))
          .filter((e) => e.ordenhas.some((v) => v > 0));
    if (!entradas.length) { setErro(modo === "vaca" ? "Selecione a vaca e informe ao menos uma ordenha." : "Informe a pesagem de ao menos uma vaca do lote."); return; }
    setSalvando(true);
    try {
      const r = await criarControlesLeiteiros({ data_controle: dataControle, entradas });
      setSucesso(`${r.criados} ${r.criados === 1 ? "pesagem" : "pesagens"} lançada${r.criados === 1 ? "" : "s"} com sucesso.`);
      limpar();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar controle leiteiro");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Modalidade">
          <select style={inputStyle} value={modo} onChange={(e) => { setModo(e.target.value as any); setErro(null); setSucesso(null); }}>
            <option value="vaca">Por vaca</option>
            <option value="lote">Por lote</option>
          </select>
        </Campo>
        <Campo label="Nº de ordenhas">
          <select style={inputStyle} value={nOrd} onChange={(e) => setNOrd(Number(e.target.value))}>
            <option value={2}>2 ordenhas</option>
            <option value={3}>3 ordenhas</option>
          </select>
        </Campo>
        {modo === "vaca" ? (
          <>
            <Campo label="Vaca"><SelectAnimal animais={animais} value={vaca} onChange={setVaca} placeholder="Selecione a vaca…" /></Campo>
            <Campo label="DEL (automático)"><input style={{ ...inputStyle, opacity: 0.8 }} value={del != null ? `${del} dias` : "—"} readOnly /></Campo>
          </>
        ) : (
          <Campo label="Lote">
            <select style={inputStyle} value={lote} onChange={(e) => setLote(e.target.value)}>
              <option value="">Selecione…</option>
              {lotesLact.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Campo>
        )}
        <Campo label="Data do controle"><input type="date" style={inputStyle} value={dataControle} onChange={(e) => setDataControle(e.target.value)} /></Campo>
      </div>

      {modo === "vaca" ? (
        <div className="mt-3">
          <label style={lbl}>Quilos por ordenha</label>
          <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
            {Array.from({ length: nOrd }, (_, i) => (
              <div key={i}>
                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{i + 1}ª ordenha</span>
                <input type="number" inputMode="decimal" style={{ ...inputStyle, width: "7rem" }} value={ord[i]}
                  onChange={(e) => setOrd((p) => { const n = [...p]; n[i] = e.target.value; return n; })} placeholder="kg" />
              </div>
            ))}
            <div>
              <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Total do dia</span>
              <div style={{ ...inputStyle, width: "7rem", fontWeight: 700, color: "var(--green-light)" }}>{total.toFixed(1)} kg</div>
            </div>
          </div>
        </div>
      ) : lote ? (
        <div className="card mt-3" style={{ padding: 0 }}>
          <div className="card-header m-3 flex items-center justify-between">
            <span>Vacas do lote {lote} ({vacasDoLote.length})</span>
            <span style={{ fontSize: "0.78rem", color: "var(--green-light)", fontWeight: 700 }}>Total do lote: {totalLote.toFixed(1)} kg</span>
          </div>
          <div className="overflow-x-auto" style={{ maxHeight: "460px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead>
                <tr>
                  <ThOrdenavel label="Nº" campo="numero" coluna={ordVacas.coluna} dir={ordVacas.dir} ordenar={ordVacas.ordenar} />
                  <ThOrdenavel label="DEL" campo="del_dias" coluna={ordVacas.coluna} dir={ordVacas.dir} ordenar={ordVacas.ordenar} />
                  {Array.from({ length: nOrd }, (_, i) => <th key={i} style={{ textAlign: "right" }}>{i + 1}ª ordenha (kg)</th>)}
                  <th style={{ textAlign: "right" }}>Total</th>
                </tr>
              </thead>
              <tbody>
                {ordVacas.linhasOrdenadas.map((a) => (
                  <tr key={a.numero}>
                    <td style={{ fontWeight: 700 }}>{a.numero}</td>
                    <td style={{ textAlign: "right", fontSize: "0.78rem" }}>{a.del_dias ?? "—"}</td>
                    {Array.from({ length: nOrd }, (_, i) => (
                      <td key={i}>
                        <input type="number" inputMode="decimal" style={{ ...inputStyle, textAlign: "right" }}
                          value={(porVaca[a.numero] || [])[i] || ""} onChange={(e) => setOrdVaca(a.numero, i, e.target.value)} placeholder="kg" />
                      </td>
                    ))}
                    <td style={{ textAlign: "right", fontWeight: 700, color: "var(--green-light)" }}>{totalVaca(a.numero).toFixed(1)}</td>
                  </tr>
                ))}
                {!vacasDoLote.length && <tr><td colSpan={nOrd + 3} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhuma vaca neste lote.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <p style={nota}>Selecione um lote para ver a listagem de vacas e lançar a pesagem individual de todas de uma vez.</p>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

// Prévia do estoque restante após uma baixa de quantidade.
function EstoqueRestante({ estoque, produto, quantidade }: { estoque: EstoqueItem[]; produto: string; quantidade: number }) {
  const item = estoque.find((e) => e.nome === produto);
  if (!item) return null;
  const atual = item.quantidade ?? 0;
  const restante = atual - (quantidade || 0);
  return (
    <p style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
      Estoque atual: <strong>{atual} {item.unidade || ""}</strong> → após a aplicação:{" "}
      <strong style={{ color: restante < 0 ? "var(--red)" : "var(--green-light)" }}>{restante} {item.unidade || ""}</strong>
      {restante < 0 && <span style={{ color: "var(--red)" }}> (estoque insuficiente!)</span>}
    </p>
  );
}

// Mesma regra do backend (fazenda.rules.unidades): unidade de aplicação
// precisa ser compatível com a unidade de estoque do produto — ex.: um
// produto guardado em "ml" pode ser aplicado em ml/unidade/dose, mas não em L.
const GRUPOS_UNIDADE: string[][] = [["ml", "unidade", "dose"], ["L", "kg"]];
function unidadesCompativeis(unidadeEstoque: string | null | undefined): string[] {
  if (!unidadeEstoque) return UNIDADES;
  const grupo = GRUPOS_UNIDADE.find((g) => g.includes(unidadeEstoque));
  return grupo || [unidadeEstoque];
}

type ItemSanidade = { produto: string; via: string; quantidade: string; unidade: string };
const itemSanidadeVazio = (): ItemSanidade => ({ produto: "", via: "", quantidade: "", unidade: "" });

function FormSanidade({ animais, lotes, estoque, produtos }: { animais: AnimalRow[]; lotes: string[]; estoque: EstoqueItem[]; produtos: string[] }) {
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [animal, setAnimal] = useState("");
  const [lotesSel, setLotesSel] = useState<Set<string>>(new Set());
  const [itens, setItens] = useState<ItemSanidade[]>([itemSanidadeVazio()]);
  const [dataAplicacao, setDataAplicacao] = useState(() => new Date().toISOString().slice(0, 10));
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  // Vindo da Agenda ("Dar baixa" de um evento sanitário): ao salvar, marca o
  // evento como realizado para sumir da Agenda.
  const [eventoAgenda, setEventoAgenda] = useState<string | null>(null);

  // Pré-preenche a partir da Agenda (medicamento padrão do evento sanitário),
  // deixando tudo editável na hora.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get("ir") !== "sanidade_aplicacao") return;
    const numero = qs.get("numero_matriz");
    if (numero) { setModo("animal"); setAnimal(numero); }
    const data = qs.get("data"); if (data) setDataAplicacao(data);
    const produto = qs.get("produto");
    if (produto) {
      setItens([{
        produto, via: qs.get("via") || "", quantidade: qs.get("dose") || "", unidade: qs.get("unidade") || "",
      }]);
    }
    setEventoAgenda(qs.get("evento_agenda"));
  }, []);

  const toggleLote = (l: string) => setLotesSel((p) => { const s = new Set(p); s.has(l) ? s.delete(l) : s.add(l); return s; });
  // Lista de produtos vem do relatório de sanidade (medicamentos já aplicados),
  // complementada pelos itens do estoque que ainda não apareceram na sanidade.
  const nomesEstoque = estoque.map((e) => e.nome);
  const listaProdutos = Array.from(new Set([...produtos, ...nomesEstoque])).sort();

  const atualizarItem = (idx: number, patch: Partial<ItemSanidade>) => setItens((p) => {
    const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n;
  });
  const escolherProduto = (idx: number, produto: string) => {
    const compativeis = unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade);
    atualizarItem(idx, { produto, unidade: compativeis[0] || "" });
  };
  const acrescentarItem = () => setItens((p) => [...p, itemSanidadeVazio()]);
  const removerItem = (idx: number) => setItens((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  async function salvar() {
    setErro(null); setSucesso(null);
    const animaisAlvo = modo === "animal"
      ? (animal ? [animal] : [])
      : animais.filter((a) => a.grupo_primario && lotesSel.has(a.grupo_primario)).map((a) => a.numero);
    if (!animaisAlvo.length) { setErro(modo === "animal" ? "Selecione o animal." : "Selecione ao menos um lote."); return; }
    const itensValidos = itens.filter((i) => i.produto && Number(i.quantidade) > 0 && i.unidade);
    if (!itensValidos.length) { setErro("Adicione ao menos um produto com quantidade e unidade."); return; }

    setSalvando(true);
    try {
      const r = await criarAplicacaoSanidade({
        data_aplicacao: dataAplicacao, animais: animaisAlvo, responsavel: responsavel || undefined, observacao: observacao || undefined,
        itens: itensValidos.map((i) => ({ produto: i.produto, via: i.via || undefined, quantidade: Number(i.quantidade), unidade: i.unidade })),
      });
      if (eventoAgenda) { await marcarEventoRealizado(eventoAgenda).catch(() => {}); setEventoAgenda(null); }
      setSucesso(`${r.criados} aplicação(ões) lançada(s) com sucesso.${r.avisos?.length ? " " + r.avisos.join(" ") : ""}${eventoAgenda ? " Baixado da Agenda." : ""}`);
      setItens([itemSanidadeVazio()]); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar aplicação de sanidade");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Lançar por">
          <select style={inputStyle} value={modo} onChange={(e) => setModo(e.target.value as any)}><option value="animal">Animal</option><option value="lote">Lote</option></select>
        </Campo>
        <Campo label="Data"><input type="date" style={inputStyle} value={dataAplicacao} onChange={(e) => setDataAplicacao(e.target.value)} /></Campo>
        {modo === "animal"
          ? <Campo label="Animal" full><SelectAnimal animais={animais} value={animal} onChange={setAnimal} /></Campo>
          : <Campo label="Lotes" full>
              <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
                {lotes.map((l) => <label key={l} className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}><input type="checkbox" checked={lotesSel.has(l)} onChange={() => toggleLote(l)} /> {l}</label>)}
              </div>
            </Campo>}
        <Campo label="Responsável"><select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="" disabled>Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select></Campo>
        <Campo label="Observação"><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>

      <Secao>Produtos aplicados</Secao>
      <div className="space-y-3">
        {itens.map((item, idx) => {
          const estoqueItem = estoque.find((e) => e.nome === item.produto);
          const compativeis = unidadesCompativeis(estoqueItem?.unidade);
          return (
            <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.75rem", position: "relative" }}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Campo label={`Produto/medicamento ${idx + 1}`}>
                  <select style={inputStyle} value={item.produto} onChange={(e) => escolherProduto(idx, e.target.value)}>
                    <option value="" disabled>Selecione…</option>
                    {listaProdutos.map((nome) => {
                      const est = estoque.find((e) => e.nome === nome);
                      return <option key={nome} value={nome}>{nome}{est?.quantidade != null ? ` (${est.quantidade} ${est.unidade || ""})` : ""}</option>;
                    })}
                  </select>
                </Campo>
                <Campo label="Via">
                  <select style={inputStyle} value={item.via} onChange={(e) => atualizarItem(idx, { via: e.target.value })}>
                    <option value="">Selecione…</option>
                    {VIAS_APLICACAO.map((o) => <option key={o}>{o}</option>)}
                  </select>
                </Campo>
                <Campo label="Quantidade (dose)"><input type="number" inputMode="decimal" style={inputStyle} value={item.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} /></Campo>
                <Campo label="Unidade">
                  <select style={inputStyle} value={item.unidade} onChange={(e) => atualizarItem(idx, { unidade: e.target.value })}>
                    {compativeis.map((u) => <option key={u}>{u}</option>)}
                  </select>
                </Campo>
              </div>
              {item.produto && <EstoqueRestante estoque={estoque} produto={item.produto} quantidade={Number(item.quantidade) || 0} />}
              {itens.length > 1 && (
                <button onClick={() => removerItem(idx)} title="Remover este item" aria-label="Remover este item" className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", color: "var(--red)", fontSize: "0.72rem" }}>
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          );
        })}
      </div>
      <button onClick={acrescentarItem} className="btn-ghost flex items-center gap-1 mt-2" style={{ fontSize: "0.78rem" }}><Plus size={14} /> Acrescentar produto</button>

      <p style={nota}>Ao salvar, dá baixa da quantidade no estoque (por animal, ou multiplicada pelo efetivo dos lotes) quando a unidade escolhida bater com a unidade de estoque do produto.</p>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

type OpcaoNomeAtivo = { id: number; nome: string; ativo: boolean };
type RegraCalendario = {
  id: number; evento_sanitario_id: number; evento_sanitario_nome: string;
  categoria_alvo: string | null; doenca_id: number | null; doenca_nome: string | null;
  produto: string | null; principio_ativo_id: number | null; principio_ativo_nome: string | null;
  dosagem: string | null; frequencia_valor: number; frequencia_unidade: string;
  data_evento: string; proxima_ocorrencia: string; observacao: string | null; ativo: boolean;
};

const FREQUENCIA_UNIDADES = [
  { v: "dias", l: "dia(s)" }, { v: "meses", l: "mês(es)" }, { v: "anos", l: "ano(s)" },
];

function FormCalendarioSanitario({ estoque }: { estoque: EstoqueItem[] }) {
  const [eventos, setEventos] = useState<OpcaoNomeAtivo[]>([]);
  const [doencas, setDoencas] = useState<OpcaoNomeAtivo[]>([]);
  const [principios, setPrincipios] = useState<OpcaoNomeAtivo[]>([]);
  const [regras, setRegras] = useState<RegraCalendario[] | null>(null);

  const [editando, setEditando] = useState<number | null>(null);
  const [eventoId, setEventoId] = useState("");
  const [categoriaAlvo, setCategoriaAlvo] = useState("");
  const [doencaId, setDoencaId] = useState("");
  const [produto, setProduto] = useState("");
  const [principioId, setPrincipioId] = useState("");
  const [dosagem, setDosagem] = useState("");
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [dataEvento, setDataEvento] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const carregarRegras = () => fetchCalendarioSanitario().then(setRegras).catch((e) => setErro(e.message));
  useEffect(() => {
    fetchEventosSanitarios().then((d) => setEventos(d.filter((e: OpcaoNomeAtivo) => e.ativo))).catch(() => {});
    fetchDoencas().then((d) => setDoencas(d.filter((e: OpcaoNomeAtivo) => e.ativo))).catch(() => {});
    fetchPrincipiosAtivos().then((d) => setPrincipios(d.filter((e: OpcaoNomeAtivo) => e.ativo))).catch(() => {});
    carregarRegras();
  }, []);

  const limpar = () => {
    setEditando(null); setEventoId(""); setCategoriaAlvo(""); setDoencaId(""); setProduto("");
    setPrincipioId(""); setDosagem(""); setFreqValor("1"); setFreqUnidade("meses"); setDataEvento(""); setObservacao("");
  };

  const abrirEdicao = (r: RegraCalendario) => {
    setEditando(r.id); setEventoId(String(r.evento_sanitario_id)); setCategoriaAlvo(r.categoria_alvo || "");
    setDoencaId(r.doenca_id ? String(r.doenca_id) : ""); setProduto(r.produto || "");
    setPrincipioId(r.principio_ativo_id ? String(r.principio_ativo_id) : ""); setDosagem(r.dosagem || "");
    setFreqValor(String(r.frequencia_valor)); setFreqUnidade(r.frequencia_unidade);
    setDataEvento(r.data_evento); setObservacao(r.observacao || "");
  };

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!eventoId || !dataEvento || !freqValor) { setErro("Selecione o evento sanitário, a frequência e a data do evento."); return; }
    setSalvando(true);
    try {
      const dados = {
        evento_sanitario_id: Number(eventoId), categoria_alvo: categoriaAlvo || undefined,
        doenca_id: doencaId ? Number(doencaId) : undefined, produto: produto || undefined,
        principio_ativo_id: principioId ? Number(principioId) : undefined, dosagem: dosagem || undefined,
        frequencia_valor: Number(freqValor), frequencia_unidade: freqUnidade, data_evento: dataEvento,
        observacao: observacao || undefined,
      };
      if (editando) await atualizarCalendarioSanitario(editando, dados);
      else await criarCalendarioSanitario(dados);
      setSucesso(editando ? "Regra atualizada com sucesso." : "Regra do calendário sanitário criada com sucesso.");
      limpar();
      carregarRegras();
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar a regra do calendário sanitário");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <p style={nota}>
        Ex.: <strong>Vermífugo</strong> a cada 4 meses para bezerras (calendário sazonal), ou <strong>Brucelose B19</strong> uma
        vez, no nascimento (protocolo por fase fisiológica) — escolha o evento, a frequência e preencha a dosagem.
      </p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
        <Campo label="Evento sanitário">
          <select style={inputStyle} value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
            <option value="">Selecione…</option>{eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
          </select>
        </Campo>
        <Campo label="Categoria alvo">
          <input style={inputStyle} value={categoriaAlvo} onChange={(e) => setCategoriaAlvo(e.target.value)} placeholder="ex.: Bezerras (até 4 a 8 meses)" />
        </Campo>
        <Campo label="Doença combatida">
          <select style={inputStyle} value={doencaId} onChange={(e) => setDoencaId(e.target.value)}>
            <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
          </select>
        </Campo>
        <Campo label="Princípio ativo">
          <select style={inputStyle} value={principioId} onChange={(e) => setPrincipioId(e.target.value)}>
            <option value="">—</option>{principios.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
          </select>
        </Campo>
        <Campo label="Produto (item de estoque)">
          <input style={inputStyle} list="produtos-calendario-sanitario" value={produto} onChange={(e) => setProduto(e.target.value)} placeholder="ex.: VACINA RB 51 - FR 25 DS" />
          <datalist id="produtos-calendario-sanitario">{estoque.map((e) => <option key={e.nome} value={e.nome} />)}</datalist>
        </Campo>
        <Campo label="Dosagem recomendada">
          <input style={inputStyle} value={dosagem} onChange={(e) => setDosagem(e.target.value)} placeholder="ex.: 2 mL a 5 mL (conforme bula)" />
        </Campo>
        <Campo label="Frequência">
          <div className="flex items-center gap-2">
            <input type="number" min={1} style={inputStyle} value={freqValor} onChange={(e) => setFreqValor(e.target.value)} />
            <select style={inputStyle} value={freqUnidade} onChange={(e) => setFreqUnidade(e.target.value)}>
              {FREQUENCIA_UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}
            </select>
          </div>
        </Campo>
        <Campo label="Data do evento (referência)"><input type="date" style={inputStyle} value={dataEvento} onChange={(e) => setDataEvento(e.target.value)} /></Campo>
        <Campo label="Observação" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : editando ? "Salvar alterações" : "Salvar"}</button>
        {editando && <button className="btn-ghost" onClick={limpar}>Cancelar edição</button>}
      </div>

      {regras && (
        <div className="mt-4">
          <SecaoRecolhivel
            titulo="Regras cadastradas"
            defaultAberta={false}
            descricao="Regras recorrentes já cadastradas no calendário sanitário"
            badge={<span style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700 }}>{regras.length}</span>}
          >
          <div className="overflow-x-auto" style={{ maxHeight: "320px" }}>
            <table className="fazenda-table" style={{ margin: 0 }}>
              <thead><tr><th>Evento</th><th>Categoria alvo</th><th>Frequência</th><th>Próxima ocorrência</th><th></th></tr></thead>
              <tbody>
                {regras.map((r) => (
                  <tr key={r.id}>
                    <td style={{ fontWeight: 700 }}>{r.evento_sanitario_nome}</td>
                    <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{r.categoria_alvo || "—"}</td>
                    <td style={{ fontSize: "0.78rem" }}>a cada {r.frequencia_valor} {FREQUENCIA_UNIDADES.find((u) => u.v === r.frequencia_unidade)?.l}</td>
                    <td style={{ fontSize: "0.78rem" }}>{formatDate(r.proxima_ocorrencia)}</td>
                    <td style={{ textAlign: "right" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => abrirEdicao(r)}>Editar</button>
                    </td>
                  </tr>
                ))}
                {!regras.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma regra cadastrada ainda.</td></tr>}
              </tbody>
            </table>
          </div>
          </SecaoRecolhivel>
        </div>
      )}
    </>
  );
}

type ProtocoloEtapaLocal = { dia: number; produto: string; dosagem: number; unidade: string; via?: string | null };
type ProtocoloLocal = { id: number; nome: string; eh_mastite: boolean; ativo: boolean; etapas: ProtocoloEtapaLocal[] };
const TETOS = ["AE", "AD", "PD", "PE"] as const;
const CLASSIFICACOES_MASTITE = [["clinica", "Clínica"], ["subclinica", "Subclínica"], ["ambiental", "Ambiental"]] as const;

// Categorias prontas de animais para o lançamento em massa do protocolo sanitário
// — reaproveita o mesmo motor de critérios cumulativos de Configurações > Lotes
// (POST /lotes/preview), sem precisar criar um lote de verdade.
const CATEGORIAS_ANIMAIS = [
  { id: "novilhas_inseminadas", label: "Novilhas inseminadas", criterios: { novilhas_inseminadas: true } },
  { id: "novilhas_gestantes", label: "Novilhas gestantes", criterios: { novilhas_gestantes: true } },
  { id: "lactacao", label: "Vacas em lactação", criterios: { status_lactacao: "lactacao" } },
  { id: "secas", label: "Vacas secas", criterios: { status_lactacao: "seca" } },
  { id: "pre_parto_15", label: "Pré-parto (próximos 15 dias)", criterios: { dias_para_parto_min: 0, dias_para_parto_max: 15 } },
  { id: "em_tratamento", label: "Em tratamento", criterios: { em_tratamento: true } },
] as const;

// Mesmo esquema de código de 2 dígitos usado em fazenda.rules.alimentacao._codigo_grupo,
// para expandir lote(s) selecionado(s) no número de matrículas correspondente.
function codigoGrupo(grupo: string | null | undefined): string | null {
  if (!grupo) return null;
  const g = grupo.trim();
  return g.length >= 2 && /^\d\d/.test(g) ? g.slice(0, 2) : null;
}

function FormProtocoloSanitario({ animais }: { animais: AnimalRow[] }) {
  const [protocolos, setProtocolos] = useState<ProtocoloLocal[]>([]);
  const [protocoloId, setProtocoloId] = useState("");
  const [matriz, setMatriz] = useState("");
  const [dataInicio, setDataInicio] = useState(() => new Date().toISOString().slice(0, 10));
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [classificacaoMastite, setClassificacaoMastite] = useState("");
  const [resultadoCmt, setResultadoCmt] = useState("");
  const [tetosSel, setTetosSel] = useState<Set<string>>(new Set());
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Lançamento em massa (protocolos que não são de mastite): animal(is), lote(s) ou categoria de animais.
  const [vinculo, setVinculo] = useState<"animal" | "lote" | "categoria">("animal");
  const [animaisSelecionados, setAnimaisSelecionados] = useState<Set<string>>(new Set());
  const [lotesSelecionados, setLotesSelecionados] = useState<Set<string>>(new Set());
  const [lotesTodos, setLotesTodos] = useState<LoteRow[]>([]);
  const [pickerAberto, setPickerAberto] = useState<"animal" | "lote" | null>(null);
  const abrirPicker = (tipo: "animal" | "lote") => {
    if (tipo === "lote" && !lotesTodos.length) fetchLotes().then(setLotesTodos).catch(() => {});
    setPickerAberto(tipo);
  };
  const toggleAnimalSelecionado = (numero: string) => setAnimaisSelecionados((p) => { const n = new Set(p); n.has(numero) ? n.delete(numero) : n.add(numero); return n; });
  const toggleTodosAnimais = () => setAnimaisSelecionados((p) => (p.size === animais.length ? new Set() : new Set(animais.map((a) => a.numero))));
  const toggleLoteSelecionado = (codigo: string) => setLotesSelecionados((p) => { const n = new Set(p); n.has(codigo) ? n.delete(codigo) : n.add(codigo); return n; });
  const toggleTodosLotes = () => setLotesSelecionados((p) => (p.size === lotesTodos.length ? new Set() : new Set(lotesTodos.map((l) => l.codigo))));
  const pickerColunasAnimais = [
    { header: "Grupo", render: (a: AnimalRow) => a.grupo_primario || "—" },
    { header: "Categoria", render: (a: AnimalRow) => a.categoria_abrev || a.categoria_completa || "—" },
  ];

  const [categoriaId, setCategoriaId] = useState("");
  const [animaisCategoria, setAnimaisCategoria] = useState<string[] | null>(null);
  const [carregandoCategoria, setCarregandoCategoria] = useState(false);
  useEffect(() => {
    if (!categoriaId) { setAnimaisCategoria(null); return; }
    const categoria = CATEGORIAS_ANIMAIS.find((c) => c.id === categoriaId);
    if (!categoria) return;
    setCarregandoCategoria(true);
    previewCriteriosLote({ codigo: "categoria", nome: categoria.label, ...categoria.criterios })
      .then((d) => setAnimaisCategoria(d.animais || []))
      .catch(() => setAnimaisCategoria([]))
      .finally(() => setCarregandoCategoria(false));
  }, [categoriaId]);

  const animaisDoLote = useMemo(
    () => animais.filter((a) => { const cod = codigoGrupo(a.grupo_primario); return cod && lotesSelecionados.has(cod); }).map((a) => a.numero),
    [animais, lotesSelecionados]
  );

  const numerosSelecionados = useMemo(() => {
    if (vinculo === "animal") return Array.from(animaisSelecionados);
    if (vinculo === "lote") return animaisDoLote;
    return animaisCategoria || [];
  }, [vinculo, animaisSelecionados, animaisDoLote, animaisCategoria]);

  useEffect(() => { fetchProtocolosSanitarios().then((d) => setProtocolos(d.filter((p: ProtocoloLocal) => p.ativo))).catch(() => {}); }, []);

  const protocolo = protocolos.find((p) => p.id === Number(protocoloId));
  const toggleTeto = (t: string) => setTetosSel((p) => { const s = new Set(p); s.has(t) ? s.delete(t) : s.add(t); return s; });

  const cronograma = useMemo(() => {
    if (!protocolo || !dataInicio) return [];
    return [...protocolo.etapas].sort((a, b) => a.dia - b.dia).map((e) => ({
      ...e, data: addDias(dataInicio, e.dia - 1),
    }));
  }, [protocolo, dataInicio]);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!protocolo) { setErro("Selecione o protocolo."); return; }
    const numeros = protocolo.eh_mastite ? (matriz ? [matriz] : []) : numerosSelecionados;
    if (!numeros.length) { setErro("Selecione ao menos um animal, lote ou categoria."); return; }
    if (protocolo.eh_mastite && !classificacaoMastite) { setErro("Informe a classificação da mastite (clínica, subclínica ou ambiental)."); return; }

    setSalvando(true);
    try {
      const r = await lancarProtocoloSanitario({
        protocolo_id: protocolo.id, numeros_matriz: numeros, data_inicio: dataInicio,
        responsavel: responsavel || undefined, observacao: observacao || undefined,
        classificacao_mastite: classificacaoMastite || undefined, resultado_cmt: resultadoCmt || undefined,
        tetos_afetados: Array.from(tetosSel),
      });
      setSucesso(`Protocolo "${protocolo.nome}" lançado para ${r.criados} animal(is) — ${protocolo.etapas.length} evento(s) na Agenda por animal.`);
      setMatriz(""); setObservacao(""); setClassificacaoMastite(""); setResultadoCmt(""); setTetosSel(new Set());
      setAnimaisSelecionados(new Set()); setLotesSelecionados(new Set()); setCategoriaId("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar protocolo sanitário");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Protocolo">
          <select style={inputStyle} value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
            <option value="">Selecione…</option>
            {protocolos.map((p) => <option key={p.id} value={p.id}>{p.nome}{p.eh_mastite ? " (mastite)" : ""}</option>)}
          </select>
        </Campo>
        <Campo label="Data de início (D1)"><input type="date" style={inputStyle} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></Campo>

        {protocolo?.eh_mastite ? (
          <Campo label="Matriz (nº)" full><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz…" /></Campo>
        ) : (
          <Campo label="Animal(is), lote(s) ou categoria" full>
            <TabBar<"animal" | "lote" | "categoria">
              abas={[
                { id: "animal", label: "Animal(is)", title: "Selecionar animais individualmente" },
                { id: "lote", label: "Lote(s)", title: "Aplicar a todos os animais de um ou mais lotes" },
                { id: "categoria", label: "Categoria de animais", title: "Aplicar a uma categoria pronta (ex.: vacas em lactação, secas)" },
              ]}
              ativa={vinculo}
              onChange={setVinculo}
            />
            {vinculo === "animal" && (
              <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => abrirPicker("animal")}>
                {animaisSelecionados.size ? `${animaisSelecionados.size} animal(is) selecionado(s) — alterar` : "Selecionar animais…"}
              </button>
            )}
            {vinculo === "lote" && (
              <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => abrirPicker("lote")}>
                {lotesSelecionados.size ? `${lotesSelecionados.size} lote(s) selecionado(s) (${animaisDoLote.length} animal(is)) — alterar` : "Selecionar lotes…"}
              </button>
            )}
            {vinculo === "categoria" && (
              <div>
                <select style={inputStyle} value={categoriaId} onChange={(e) => setCategoriaId(e.target.value)}>
                  <option value="">Selecione…</option>
                  {CATEGORIAS_ANIMAIS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </select>
                {categoriaId && (
                  <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                    {carregandoCategoria ? "Calculando…" : `${(animaisCategoria || []).length} animal(is) atendem a este critério.`}
                  </p>
                )}
              </div>
            )}
          </Campo>
        )}

        <Campo label="Responsável"><select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="" disabled>Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select></Campo>
        <Campo label="Observação"><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>

      {protocolo?.eh_mastite && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.6rem" }}>Tratamento diferenciado de mastite</p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Campo label="Classificação">
              <select style={inputStyle} value={classificacaoMastite} onChange={(e) => setClassificacaoMastite(e.target.value)}>
                <option value="">Selecione…</option>
                {CLASSIFICACOES_MASTITE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Campo>
            <Campo label="Resultado do CMT"><input style={inputStyle} value={resultadoCmt} onChange={(e) => setResultadoCmt(e.target.value)} placeholder="ex.: +++ (forte)" /></Campo>
            <Campo label="Teto(s) afetado(s)" full>
              <div className="flex gap-3" style={{ flexWrap: "wrap" }}>
                {TETOS.map((t) => (
                  <label key={t} className="flex items-center gap-2" style={{ fontSize: "0.8rem" }}>
                    <input type="checkbox" checked={tetosSel.has(t)} onChange={() => toggleTeto(t)} /> {t}
                  </label>
                ))}
              </div>
            </Campo>
          </div>
        </div>
      )}

      {cronograma.length > 0 && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.4rem" }}>Cronograma — vai para a Agenda</p>
          <table className="fazenda-table">
            <thead><tr><th>Dia</th><th>Data</th><th>Produto</th><th>Dosagem</th><th>Via</th></tr></thead>
            <tbody>
              {cronograma.map((e, i) => (
                <tr key={i}>
                  <td>D{e.dia}</td>
                  <td>{e.data}</td>
                  <td>{e.produto}</td>
                  <td>{e.dosagem} {e.unidade}</td>
                  <td>{e.via || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={nota}>Ao salvar, cria um evento na Agenda por dia — marcar "realizado" dá baixa automática do produto no Estoque.</p>
        </div>
      )}

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>
          {salvando ? "Salvando…" : "Lançar protocolo"}
        </button>
      </div>

      {pickerAberto && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 55, padding: "1rem" }}>
          <div className="card" style={{ width: "640px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="card-header mb-3">{pickerAberto === "animal" ? "Selecionar animal(is)" : "Selecionar lote(s)"}</div>
            {pickerAberto === "animal" ? (
              <SelecaoAnimaisTabela animais={animais} selecionados={animaisSelecionados} toggle={toggleAnimalSelecionado} toggleTodos={toggleTodosAnimais} colunas={pickerColunasAnimais} />
            ) : (
              <SelecaoLotesTabela lotes={lotesTodos} selecionados={lotesSelecionados} toggle={toggleLoteSelecionado} toggleTodos={toggleTodosLotes} />
            )}
            <div className="flex justify-end gap-2 mt-4">
              <button onClick={() => setPickerAberto(null)} className="btn-primary">OK</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

type ItemDieta = { alimento: string; quantidade: string; unidade: string };
const itemDietaVazio = (): ItemDieta => ({ alimento: "", quantidade: "", unidade: "kg" });

type DietaLote = {
  id: number; lote: number; responsavel: string | null; data_abertura: string;
  data_prevista_encerramento: string | null; data_efetivo_encerramento: string | null;
  observacao: string | null; ativa: boolean;
  itens_programados: { alimento: string; quantidade: number; unidade: string }[];
};
type ItemComparativo = { alimento: string; unidade: string; programado: number; real_total: number; real_dias: number; real_media_dia: number | null };

function FormAlimentacaoDieta({ lotes }: { lotes: string[] }) {
  const [dietas, setDietas] = useState<DietaLote[] | null>(null);
  const [alimentosPadrao, setAlimentosPadrao] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Nova dieta
  const [loteNovo, setLoteNovo] = useState("");
  const [responsavel, setResponsavel] = useState("Alexandre Scarpa");
  const [dataAbertura, setDataAbertura] = useState(() => new Date().toISOString().slice(0, 10));
  const [dataPrevista, setDataPrevista] = useState("");
  const [observacaoNova, setObservacaoNova] = useState("");
  const [itens, setItens] = useState<ItemDieta[]>([itemDietaVazio()]);
  const [salvando, setSalvando] = useState(false);

  // Encerrar / registrar real / comparativo
  const [encerrando, setEncerrando] = useState<number | null>(null);
  const [dataEncerramento, setDataEncerramento] = useState(() => new Date().toISOString().slice(0, 10));
  const [registrando, setRegistrando] = useState<number | null>(null);
  const [dataReal, setDataReal] = useState(() => new Date().toISOString().slice(0, 10));
  const [itensReal, setItensReal] = useState<ItemDieta[]>([itemDietaVazio()]);
  const [comparandoId, setComparandoId] = useState<number | null>(null);
  const [comparativo, setComparativo] = useState<ItemComparativo[] | null>(null);

  const carregar = () => fetchDietas().then(setDietas).catch((e) => setErro(e.message));
  useEffect(() => {
    carregar();
    fetchAlimentosPadrao().then(setAlimentosPadrao).catch(() => {});
  }, []);

  // Vindo da Agenda (link "Ir para Dieta" do evento de análise de encerramento)
  // — abre direto a seção de encerrar a dieta ativa daquele lote.
  useEffect(() => {
    if (!dietas) return;
    const lote = new URLSearchParams(window.location.search).get("lote");
    if (!lote) return;
    const ativa = dietas.find((d) => d.lote === Number(lote) && d.ativa);
    if (ativa) setEncerrando(ativa.id);
  }, [dietas]);

  const atualizarItem = (idx: number, patch: Partial<ItemDieta>) => setItens((p) => { const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n; });
  const acrescentarItem = () => setItens((p) => [...p, itemDietaVazio()]);
  const removerItem = (idx: number) => setItens((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  const atualizarItemReal = (idx: number, patch: Partial<ItemDieta>) => setItensReal((p) => { const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n; });
  const acrescentarItemReal = () => setItensReal((p) => [...p, itemDietaVazio()]);
  const removerItemReal = (idx: number) => setItensReal((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  async function salvarDieta() {
    setErro(null); setSucesso(null);
    const loteNum = Number(cod(loteNovo));
    if (!loteNovo || !loteNum) { setErro("Selecione o lote."); return; }
    if (!dataAbertura) { setErro("Informe a data de abertura."); return; }
    const itensValidos = itens.filter((i) => i.alimento && Number(i.quantidade) > 0 && i.unidade);
    if (!itensValidos.length) { setErro("Adicione ao menos um alimento com quantidade e unidade."); return; }

    setSalvando(true);
    try {
      await criarDieta({
        lote: loteNum, responsavel: responsavel || undefined, data_abertura: dataAbertura,
        data_prevista_encerramento: dataPrevista || undefined, observacao: observacaoNova || undefined,
        itens: itensValidos.map((i) => ({ alimento: i.alimento, quantidade: Number(i.quantidade), unidade: i.unidade })),
      });
      setSucesso(`Dieta lançada para o lote ${loteNovo}.`);
      setLoteNovo(""); setDataPrevista(""); setObservacaoNova(""); setItens([itemDietaVazio()]);
      carregar();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar dieta");
    } finally {
      setSalvando(false);
    }
  }

  async function confirmarEncerramento(dieta: DietaLote) {
    setErro(null); setSucesso(null);
    try {
      await encerrarDieta(dieta.id, dataEncerramento);
      setEncerrando(null);
      setSucesso(`Dieta do lote ${dieta.lote} encerrada.`);
      carregar();
      if (window.confirm(`Dieta do lote ${dieta.lote} encerrada. Deseja lançar uma nova dieta para este lote agora?`)) {
        const loteLabel = lotes.find((l) => Number(cod(l)) === dieta.lote) || "";
        setLoteNovo(loteLabel);
        setDataAbertura(dataEncerramento);
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao encerrar dieta");
    }
  }

  async function salvarReal(dietaId: number) {
    setErro(null); setSucesso(null);
    const itensValidos = itensReal.filter((i) => i.alimento && Number(i.quantidade) > 0 && i.unidade);
    if (!itensValidos.length) { setErro("Adicione ao menos um alimento com quantidade e unidade."); return; }
    try {
      await registrarRealDieta(dietaId, {
        data: dataReal, itens: itensValidos.map((i) => ({ alimento: i.alimento, quantidade: Number(i.quantidade), unidade: i.unidade })),
      });
      setSucesso("Real oferecido registrado com sucesso.");
      setRegistrando(null); setItensReal([itemDietaVazio()]);
      if (comparandoId === dietaId) abrirComparativo(dietaId);
    } catch (e: any) {
      setErro(e.message || "Erro ao registrar o real oferecido");
    }
  }

  const abrirComparativo = (dietaId: number) => {
    setComparandoId((atual) => (atual === dietaId ? null : dietaId));
    if (comparandoId !== dietaId) {
      fetchComparativoDieta(dietaId).then((d) => setComparativo(d.itens)).catch((e) => setErro(e.message));
    }
  };

  const listaAlimentos = alimentosPadrao;

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Lote">
          <select style={inputStyle} value={loteNovo} onChange={(e) => setLoteNovo(e.target.value)}>
            <option value="">Selecione…</option>{lotes.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </Campo>
        <Campo label="Responsável (nutricionista)">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
            <option value="">—</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}
          </select>
        </Campo>
        <Campo label="Data de abertura"><input type="date" style={inputStyle} value={dataAbertura} onChange={(e) => setDataAbertura(e.target.value)} /></Campo>
        <Campo label="Data prevista de encerramento (opcional)"><input type="date" style={inputStyle} value={dataPrevista} onChange={(e) => setDataPrevista(e.target.value)} /></Campo>
        <Campo label="Observação" full><input style={inputStyle} value={observacaoNova} onChange={(e) => setObservacaoNova(e.target.value)} /></Campo>
      </div>
      <p style={nota}>A data prevista de encerramento entra na Agenda como um evento para análise. Só uma dieta pode ficar ativa por lote — encerre a atual antes de lançar outra.</p>

      <Secao>Plano programado (formulado)</Secao>
      <div className="space-y-3">
        {itens.map((item, idx) => (
          <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.75rem", position: "relative" }}>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              <Campo label={`Alimento ${idx + 1}`}>
                <input style={inputStyle} list="alimentos-padrao-dieta" value={item.alimento} onChange={(e) => atualizarItem(idx, { alimento: e.target.value })} placeholder="ex.: Silagem" />
              </Campo>
              <Campo label="Quantidade total do lote/dia"><input type="number" inputMode="decimal" style={inputStyle} value={item.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} /></Campo>
              <Campo label="Unidade">
                <select style={inputStyle} value={item.unidade} onChange={(e) => atualizarItem(idx, { unidade: e.target.value })}>
                  {UNIDADES.map((u) => <option key={u}>{u}</option>)}
                </select>
              </Campo>
            </div>
            {itens.length > 1 && (
              <button onClick={() => removerItem(idx)} title="Remover este item" aria-label="Remover este item" className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", color: "var(--red)", fontSize: "0.72rem" }}>
                <Trash2 size={13} />
              </button>
            )}
          </div>
        ))}
      </div>
      <datalist id="alimentos-padrao-dieta">{listaAlimentos.map((a) => <option key={a} value={a} />)}</datalist>
      <button onClick={acrescentarItem} className="btn-ghost flex items-center gap-1 mt-2" style={{ fontSize: "0.78rem" }}><Plus size={14} /> Acrescentar alimento</button>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvarDieta} disabled={salvando}>{salvando ? "Salvando…" : "Lançar dieta"}</button>
      </div>

      {dietas && (
        <div className="mt-4">
          <SecaoRecolhivel
            titulo="Dietas lançadas"
            defaultAberta={false}
            descricao="Histórico de dietas por lote — comparativo, real oferecido e encerramento"
            badge={<span style={{ fontSize: "0.72rem", color: "var(--dourado-light)", fontWeight: 700 }}>{dietas.length}</span>}
          >
          <div className="overflow-x-auto">
            <table className="fazenda-table">
              <thead><tr><th>Lote</th><th>Responsável</th><th>Abertura</th><th>Prev. encerramento</th><th>Situação</th><th></th></tr></thead>
              <tbody>
                {dietas.map((d) => (
                  <Fragment key={d.id}>
                    <tr>
                      <td style={{ fontWeight: 700 }}>{d.lote}</td>
                      <td style={{ fontSize: "0.78rem" }}>{d.responsavel || "—"}</td>
                      <td style={{ fontSize: "0.78rem" }}>{formatDate(d.data_abertura)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{d.data_prevista_encerramento ? formatDate(d.data_prevista_encerramento) : "—"}</td>
                      <td>
                        <span style={{ fontSize: "0.72rem", fontWeight: 700, color: d.ativa ? "var(--green-light)" : "var(--text-muted)" }}>
                          {d.ativa ? "Ativa" : `Encerrada em ${formatDate(d.data_efetivo_encerramento!)}`}
                        </span>
                      </td>
                      <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                        <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => abrirComparativo(d.id)}>Comparativo</button>
                        {d.ativa && <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => setRegistrando(registrando === d.id ? null : d.id)}>Registrar real</button>}
                        {d.ativa && <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => setEncerrando(encerrando === d.id ? null : d.id)}>Encerrar</button>}
                      </td>
                    </tr>
                    {encerrando === d.id && (
                      <tr><td colSpan={6} style={{ padding: 0 }}>
                        <div style={{ background: "var(--surface-2)", padding: "0.75rem", display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                          <label style={lbl}>Data de encerramento efetivo</label>
                          <input type="date" style={{ ...inputStyle, width: "auto" }} value={dataEncerramento} onChange={(e) => setDataEncerramento(e.target.value)} />
                          <button className="btn-primary" style={{ fontSize: "0.75rem" }} onClick={() => confirmarEncerramento(d)}>Confirmar encerramento</button>
                          <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setEncerrando(null)}>Cancelar</button>
                        </div>
                      </td></tr>
                    )}
                    {registrando === d.id && (
                      <tr><td colSpan={6} style={{ padding: 0 }}>
                        <div style={{ background: "var(--surface-2)", padding: "0.75rem" }}>
                          <div className="flex items-center gap-2 mb-2">
                            <label style={lbl}>Data</label>
                            <input type="date" style={{ ...inputStyle, width: "auto" }} value={dataReal} onChange={(e) => setDataReal(e.target.value)} />
                          </div>
                          {itensReal.map((item, idx) => (
                            <div key={idx} className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-2" style={{ alignItems: "end" }}>
                              <Campo label="Alimento"><input style={inputStyle} list="alimentos-padrao-dieta" value={item.alimento} onChange={(e) => atualizarItemReal(idx, { alimento: e.target.value })} /></Campo>
                              <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={item.quantidade} onChange={(e) => atualizarItemReal(idx, { quantidade: e.target.value })} /></Campo>
                              <Campo label="Unidade">
                                <select style={inputStyle} value={item.unidade} onChange={(e) => atualizarItemReal(idx, { unidade: e.target.value })}>{UNIDADES.map((u) => <option key={u}>{u}</option>)}</select>
                              </Campo>
                              {itensReal.length > 1 && <button onClick={() => removerItemReal(idx)} title="Remover este alimento" aria-label="Remover este alimento" className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem" }}><Trash2 size={13} /></button>}
                            </div>
                          ))}
                          <button onClick={acrescentarItemReal} className="btn-ghost flex items-center gap-1" style={{ fontSize: "0.75rem" }}><Plus size={13} /> Acrescentar alimento</button>
                          <div className="flex items-center gap-2 mt-2">
                            <button className="btn-primary" style={{ fontSize: "0.75rem" }} onClick={() => salvarReal(d.id)}>Salvar real oferecido</button>
                            <button className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={() => setRegistrando(null)}>Cancelar</button>
                          </div>
                        </div>
                      </td></tr>
                    )}
                    {comparandoId === d.id && comparativo && (
                      <tr><td colSpan={6} style={{ padding: 0 }}>
                        <div style={{ background: "var(--surface-2)", padding: "0.75rem" }}>
                          <table className="fazenda-table" style={{ margin: 0 }}>
                            <thead><tr><th>Alimento</th><th style={{ textAlign: "right" }}>Programado (dia)</th><th style={{ textAlign: "right" }}>Real (total)</th><th style={{ textAlign: "right" }}>Dias registrados</th><th style={{ textAlign: "right" }}>Real (média/dia)</th></tr></thead>
                            <tbody>
                              {comparativo.map((c) => (
                                <tr key={c.alimento}>
                                  <td style={{ fontWeight: 700 }}>{c.alimento}</td>
                                  <td style={{ textAlign: "right" }}>{c.programado} {c.unidade}</td>
                                  <td style={{ textAlign: "right" }}>{c.real_total} {c.unidade}</td>
                                  <td style={{ textAlign: "right" }}>{c.real_dias}</td>
                                  <td style={{ textAlign: "right", fontWeight: 600, color: c.real_media_dia != null && c.real_media_dia > c.programado ? "var(--amber)" : "var(--green-light)" }}>
                                    {c.real_media_dia != null ? `${c.real_media_dia} ${c.unidade}` : "—"}
                                  </td>
                                </tr>
                              ))}
                              {!comparativo.length && <tr><td colSpan={5} style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>Sem itens.</td></tr>}
                            </tbody>
                          </table>
                        </div>
                      </td></tr>
                    )}
                  </Fragment>
                ))}
                {!dietas.length && <tr><td colSpan={6} style={{ color: "var(--text-muted)", fontSize: "0.85rem", textAlign: "center", padding: "1rem" }}>Nenhuma dieta lançada ainda.</td></tr>}
              </tbody>
            </table>
          </div>
          </SecaoRecolhivel>
        </div>
      )}
    </>
  );
}

const MOTIVOS_SECAGEM = [
  { v: "doente", l: "Animal doente" },
  { v: "baixa_producao", l: "Baixa produção" },
  { v: "comportamento", l: "Comportamento" },
  { v: "mastite", l: "Mastite" },
  { v: "casco", l: "Problema de casco" },
  { v: "rotina", l: "Rotina" },
  { v: "outros", l: "Outros" },
];

function FormSecagem({ animais, estoque, produtos }: { animais: AnimalRow[]; estoque: EstoqueItem[]; produtos: string[] }) {
  const [matriz, setMatriz] = useState("");
  const [info, setInfo] = useState<{ del_atual: number | null; data_prevista_secagem: string | null; deve_secar: boolean | null; motivo_exclusao: string | null } | null>(null);
  const [carregandoInfo, setCarregandoInfo] = useState(false);
  const [dataSecagem, setDataSecagem] = useState(() => new Date().toISOString().slice(0, 10));
  const [motivo, setMotivo] = useState("");
  const [ecc, setEcc] = useState("");
  const [observacao, setObservacao] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [itens, setItens] = useState<ItemSanidade[]>([itemSanidadeVazio()]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  useEffect(() => {
    if (!matriz) { setInfo(null); return; }
    setCarregandoInfo(true);
    fetchSecagemInfo(matriz)
      .then((d) => { setInfo(d); if (d.data_prevista_secagem) setDataSecagem(d.data_prevista_secagem); })
      .catch(() => setInfo(null))
      .finally(() => setCarregandoInfo(false));
  }, [matriz]);

  const nomesEstoque = estoque.map((e) => e.nome);
  const listaProdutos = Array.from(new Set([...produtos, ...nomesEstoque])).sort();
  const atualizarItem = (idx: number, patch: Partial<ItemSanidade>) => setItens((p) => { const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n; });
  const escolherProduto = (idx: number, produto: string) => {
    const compativeis = unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade);
    atualizarItem(idx, { produto, unidade: compativeis[0] || "" });
  };
  const acrescentarItem = () => setItens((p) => [...p, itemSanidadeVazio()]);
  const removerItem = (idx: number) => setItens((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!matriz) { setErro("Selecione a vaca."); return; }
    if (!motivo) { setErro("Selecione o motivo da secagem."); return; }
    const itensValidos = itens.filter((i) => i.produto && Number(i.quantidade) > 0 && i.unidade);

    setSalvando(true);
    try {
      const r = await criarSecagem({
        numero_matriz: matriz, data_secagem: dataSecagem, motivo,
        escore_condicao_corporal: ecc ? Number(ecc) : null,
        observacao: observacao || undefined, responsavel: responsavel || undefined,
        produtos: itensValidos.map((i) => ({ produto: i.produto, via: i.via || undefined, quantidade: Number(i.quantidade), unidade: i.unidade })),
      });
      let msg = "Secagem lançada com sucesso.";
      if (r.avisos?.length) msg += " " + r.avisos.join(" ");
      if (r.lote_sugerido && window.confirm(`Deseja alocar a vaca ${matriz} no lote ${r.lote_sugerido.rotulo} (lote das secas)?`)) {
        await criarMovimentacao({ data_movimento: dataSecagem, motivo: "Secagem", lote_destino_codigo: r.lote_sugerido.codigo, animais: [matriz] });
        msg += ` Movida para o lote ${r.lote_sugerido.rotulo}.`;
      }
      setSucesso(msg);
      setMatriz(""); setMotivo(""); setEcc(""); setObservacao(""); setItens([itemSanidadeVazio()]);
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar secagem");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Vaca"><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a vaca…" /></Campo>
        <Campo label="DEL atual">
          <input style={{ ...inputStyle, opacity: 0.8 }} readOnly value={carregandoInfo ? "Carregando…" : info?.del_atual != null ? `${info.del_atual} dias` : "—"} />
        </Campo>
        <Campo label="Data prevista de secagem (60 dias antes do parto)">
          <input style={{ ...inputStyle, opacity: 0.8 }} readOnly value={info?.data_prevista_secagem ? formatDate(info.data_prevista_secagem) : "—"} />
        </Campo>
        <Campo label="Data da secagem (pode ser retroativa)"><input type="date" style={inputStyle} value={dataSecagem} onChange={(e) => setDataSecagem(e.target.value)} /></Campo>
        <Campo label="Motivo da secagem">
          <select style={inputStyle} value={motivo} onChange={(e) => setMotivo(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            {MOTIVOS_SECAGEM.map((m) => <option key={m.v} value={m.v}>{m.l}</option>)}
          </select>
        </Campo>
        <Campo label="Escore de condição corporal (opcional, 1 a 5)">
          <input type="number" step={0.25} min={1} max={5} style={inputStyle} value={ecc} onChange={(e) => setEcc(e.target.value)} placeholder="ex.: 3,25" />
        </Campo>
        <Campo label="Responsável"><select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="">Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select></Campo>
        <Campo label="Observação"><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      {info?.motivo_exclusao && <p style={{ ...nota, color: "var(--amber)" }}>{info.motivo_exclusao}</p>}

      <Secao>Produto(s) de secagem (opcional)</Secao>
      <div className="space-y-3">
        {itens.map((item, idx) => {
          const estoqueItem = estoque.find((e) => e.nome === item.produto);
          const compativeis = unidadesCompativeis(estoqueItem?.unidade);
          return (
            <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.75rem", position: "relative" }}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Campo label={`Medicamento ${idx + 1}`}>
                  <select style={inputStyle} value={item.produto} onChange={(e) => escolherProduto(idx, e.target.value)}>
                    <option value="" disabled>Selecione…</option>
                    {listaProdutos.map((nome) => {
                      const est = estoque.find((e) => e.nome === nome);
                      return <option key={nome} value={nome}>{nome}{est?.quantidade != null ? ` (${est.quantidade} ${est.unidade || ""})` : ""}</option>;
                    })}
                  </select>
                </Campo>
                <Campo label="Via">
                  <select style={inputStyle} value={item.via} onChange={(e) => atualizarItem(idx, { via: e.target.value })}>
                    <option value="">Selecione…</option>
                    {["Intramuscular", "Subcutânea", "Intramamária", "Oral", "Tópica"].map((o) => <option key={o}>{o}</option>)}
                  </select>
                </Campo>
                <Campo label="Dosagem"><input type="number" inputMode="decimal" style={inputStyle} value={item.quantidade} onChange={(e) => atualizarItem(idx, { quantidade: e.target.value })} /></Campo>
                <Campo label="Unidade">
                  <select style={inputStyle} value={item.unidade} onChange={(e) => atualizarItem(idx, { unidade: e.target.value })}>
                    {compativeis.map((u) => <option key={u}>{u}</option>)}
                  </select>
                </Campo>
              </div>
              {item.produto && <EstoqueRestante estoque={estoque} produto={item.produto} quantidade={Number(item.quantidade) || 0} />}
              {itens.length > 1 && (
                <button onClick={() => removerItem(idx)} title="Remover este item" aria-label="Remover este item" className="btn-ghost" style={{ position: "absolute", top: "0.5rem", right: "0.5rem", color: "var(--red)", fontSize: "0.72rem" }}>
                  <Trash2 size={13} />
                </button>
              )}
            </div>
          );
        })}
      </div>
      <button onClick={acrescentarItem} className="btn-ghost flex items-center gap-1 mt-2" style={{ fontSize: "0.78rem" }}><Plus size={14} /> Acrescentar produto</button>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

function FormQualidadeLeite({ animais }: { animais: AnimalRow[] }) {
  const [alvo, setAlvo] = useState<"tanque" | "vaca">("tanque");
  const [matriz, setMatriz] = useState("");
  const [dataColeta, setDataColeta] = useState(() => new Date().toISOString().slice(0, 10));
  const [ccs, setCcs] = useState("");
  const [cbt, setCbt] = useState("");
  const [gordura, setGordura] = useState("");
  const [proteina, setProteina] = useState("");
  const [solidosTotais, setSolidosTotais] = useState("");
  const [esd, setEsd] = useState("");
  const [lactose, setLactose] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const num = (v: string) => (v.trim() === "" ? null : Number(v.replace(",", ".")));

  async function salvar() {
    setErro(null); setSucesso(null);
    if (alvo === "vaca" && !matriz) { setErro("Selecione a vaca."); return; }
    if (!dataColeta) { setErro("Informe a data da coleta."); return; }

    setSalvando(true);
    try {
      await criarQualidadeLeite({
        numero_matriz: alvo === "vaca" ? matriz : null,
        data_coleta: dataColeta,
        ccs: num(ccs), cbt: num(cbt), gordura_pct: num(gordura), proteina_pct: num(proteina),
        solidos_totais_pct: num(solidosTotais), esd_pct: num(esd), lactose_pct: num(lactose),
        observacao: observacao || undefined,
      });
      setSucesso("Qualidade do leite lançada com sucesso.");
      setMatriz(""); setCcs(""); setCbt(""); setGordura(""); setProteina(""); setSolidosTotais(""); setEsd(""); setLactose(""); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar qualidade do leite");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <TabBar<"tanque" | "vaca">
        abas={[
          { id: "tanque", label: "Todas as vacas em lactação (tanque)", title: "Coleta única representando o rebanho em lactação (amostra do tanque)" },
          { id: "vaca", label: "Uma vaca", title: "Coleta individual de uma vaca" },
        ]}
        ativa={alvo}
        onChange={setAlvo}
      />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {alvo === "vaca" && <Campo label="Vaca" full><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a vaca…" /></Campo>}
        <Campo label="Data da coleta"><input type="date" style={inputStyle} value={dataColeta} onChange={(e) => setDataColeta(e.target.value)} /></Campo>
      </div>

      <Secao>Índices de qualidade</Secao>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        <Campo label="CCS (mil céls./mL)"><input type="number" inputMode="decimal" style={inputStyle} value={ccs} onChange={(e) => setCcs(e.target.value)} /></Campo>
        <Campo label="CBT (mil UFC/mL)"><input type="number" inputMode="decimal" style={inputStyle} value={cbt} onChange={(e) => setCbt(e.target.value)} /></Campo>
        <Campo label="Gordura (%)"><input type="number" inputMode="decimal" style={inputStyle} value={gordura} onChange={(e) => setGordura(e.target.value)} /></Campo>
        <Campo label="Proteína (%)"><input type="number" inputMode="decimal" style={inputStyle} value={proteina} onChange={(e) => setProteina(e.target.value)} /></Campo>
        <Campo label="Sólidos totais — ST (%)"><input type="number" inputMode="decimal" style={inputStyle} value={solidosTotais} onChange={(e) => setSolidosTotais(e.target.value)} /></Campo>
        <Campo label="ESD (%)"><input type="number" inputMode="decimal" style={inputStyle} value={esd} onChange={(e) => setEsd(e.target.value)} /></Campo>
        <Campo label="Lactose (%) — opcional"><input type="number" inputMode="decimal" style={inputStyle} value={lactose} onChange={(e) => setLactose(e.target.value)} /></Campo>
      </div>
      <Campo label="Observação" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

function FormEntregaLeite() {
  const [competencia, setCompetencia] = useState(() => new Date().toISOString().slice(0, 7));
  const [quantidade, setQuantidade] = useState("");
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!competencia) { setErro("Selecione o mês."); return; }
    if (!quantidade || Number(quantidade) <= 0) { setErro("Informe a quantidade entregue (litros)."); return; }

    setSalvando(true);
    try {
      await criarEntregaLeiteMensal({ competencia, quantidade_litros: Number(quantidade.replace(",", ".")), observacao: observacao || undefined });
      setSucesso(`Entrega de ${competencia} lançada com sucesso.`);
      setQuantidade(""); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar entrega mensal do leite");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Mês (competência)"><input type="month" style={inputStyle} value={competencia} onChange={(e) => setCompetencia(e.target.value)} /></Campo>
        <Campo label="Quantidade entregue (litros)"><input type="number" inputMode="decimal" style={inputStyle} value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="soma das notinhas/app do laticínio no mês" /></Campo>
        <Campo label="Observação" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      <p style={nota}>Some as notinhas de entrega (ou o total do app do laticínio) do mês inteiro e lance aqui uma vez por mês — o relatório de Produção compara com o controle leiteiro projetado e a receita recebida.</p>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

const MOVIMENTOS_SAIDA = MOVIMENTOS_ESTOQUE.filter((m) => MOV_BAIXA.has(m));
const MOVIMENTOS_ENTRADA = MOVIMENTOS_ESTOQUE.filter((m) => !MOV_BAIXA.has(m));

function FormEstoque({ estoque }: { estoque: EstoqueItem[] }) {
  const [produto, setProduto] = useState("");
  const [tipo, setTipo] = useState<"entrada" | "saida" | "">("");
  const [mov, setMov] = useState("");
  const [qtd, setQtd] = useState("");
  const [unidade, setUnidade] = useState("");
  const [dataMov, setDataMov] = useState(() => new Date().toISOString().slice(0, 10));
  const [observacao, setObservacao] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const item = estoque.find((e) => e.nome === produto);
  const q = Number(qtd) || 0;
  const baixa = MOV_BAIXA.has(mov);
  const restante = item ? (item.quantidade ?? 0) + (baixa ? -q : q) : null;

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!produto || !tipo || !mov || !q) { setErro("Selecione o produto, o tipo de movimento e a quantidade."); return; }
    setSalvando(true);
    try {
      const r = await movimentarEstoque({ nome: produto, movimento: mov, quantidade: q, unidade: unidade || item?.unidade || undefined, data_movimento: dataMov, observacao: observacao || undefined });
      setSucesso(`Estoque de ${produto} atualizado: ${r.quantidade} ${r.unidade || ""}.`);
      setMov(""); setQtd(""); setObservacao("");
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar movimento de estoque");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Produto / medicamento">
          <select style={inputStyle} value={produto} onChange={(e) => setProduto(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            {estoque.map((e) => <option key={e.nome} value={e.nome}>{e.nome}{e.quantidade != null ? ` (${e.quantidade} ${e.unidade || ""})` : ""}</option>)}
          </select>
        </Campo>
        <Campo label="Tipo de movimento">
          <select style={inputStyle} value={tipo} onChange={(e) => { setTipo(e.target.value as any); setMov(""); }}>
            <option value="" disabled>Selecione…</option>
            <option value="entrada">Entrada</option>
            <option value="saida">Saída</option>
          </select>
        </Campo>
        <Campo label="Movimento">
          <select style={inputStyle} value={mov} onChange={(e) => setMov(e.target.value)} disabled={!tipo}>
            <option value="" disabled>{tipo ? "Selecione…" : "Escolha o tipo primeiro"}</option>
            {(tipo === "entrada" ? MOVIMENTOS_ENTRADA : tipo === "saida" ? MOVIMENTOS_SAIDA : [])
              .filter((m) => item?.estocavel !== false || !MOVIMENTOS_SOMENTE_ESTOCAVEL.has(m))
              .map((m) => <option key={m}>{m}</option>)}
          </select>
        </Campo>
        <Campo label="Quantidade"><input type="number" inputMode="decimal" style={inputStyle} value={qtd} onChange={(e) => setQtd(e.target.value)} /></Campo>
        <Campo label="Unidade">
          <select style={inputStyle} value={unidade || item?.unidade || "unidade"} onChange={(e) => setUnidade(e.target.value)}>
            {UNIDADES.map((u) => <option key={u}>{u}</option>)}
          </select>
        </Campo>
        <Campo label="Data"><input type="date" style={inputStyle} value={dataMov} onChange={(e) => setDataMov(e.target.value)} /></Campo>
        <Campo label="Observação" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      {item && mov && (
        <p style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
          {baixa ? "Baixa" : "Entrada"} · Estoque atual: <strong>{item.quantidade ?? 0} {item.unidade || ""}</strong> → depois:{" "}
          <strong style={{ color: (restante ?? 0) < 0 ? "var(--red)" : "var(--green-light)" }}>{restante} {item.unidade || ""}</strong>
          {(restante ?? 0) < 0 && <span style={{ color: "var(--red)" }}> (insuficiente!)</span>}
        </p>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

// Tipos de lançamento, agrupados: alguns grupos (Reprodutivo, Produção) têm uma
// camada inferior de sub-tipos, para economizar abas no menu.
const TIPOS_GRUPOS = [
  {
    id: "reprodutivo", label: "Reprodutivo", icon: Heart,
    desc: "Serviço/IA, diagnóstico de gestação ou parto/nascimento.",
    subs: [
      { id: "protocolo_iatf", label: "Protocolo IATF", icon: Heart, desc: "Agendar só o protocolo hormonal (D0/D7/D9/D11) na agenda — individual ou em lote." },
      { id: "inseminacao", label: "Inseminação", icon: Heart, desc: "Registrar a inseminação/cobertura em si — cio natural ou de um protocolo já agendado." },
      { id: "diagnostico", label: "Diagnóstico de gestação", icon: Stethoscope, desc: "Resultado do toque / diagnóstico de prenhez." },
      { id: "parto", label: "Parto / nascimento", icon: Baby, desc: "Registro de parto, da cria e do manejo de colostro." },
    ],
  },
  {
    id: "producao", label: "Produção", icon: Milk,
    desc: "Controle leiteiro ou pesagem corporal.",
    subs: [
      { id: "controle", label: "Controle leiteiro", icon: Milk, desc: "Pesagem de leite por vaca ou por lote." },
      { id: "pesagem", label: "Pesagem corporal", icon: Scale, desc: "Peso vivo por animal ou por lote — acompanha o crescimento do rebanho." },
      { id: "secagem", label: "Secagem", icon: Droplet, desc: "Registro de secagem, motivo, ECC e produto(s) — sugere a mudança para o lote de secas." },
      { id: "qualidade_leite", label: "Qualidade do leite", icon: Milk, desc: "CCS, CBT, gordura, proteína, sólidos totais e ESD — por vaca ou do tanque (rebanho em lactação)." },
      { id: "entrega_leite", label: "Entrega mensal do leite", icon: Milk, desc: "Quantidade entregue ao laticínio no mês — compara com o controle leiteiro e a receita recebida." },
    ],
  },
  {
    id: "sanidade", label: "Sanidade", icon: Syringe,
    desc: "Aplicação de medicamento ou regra do calendário sanitário.",
    subs: [
      { id: "sanidade_aplicacao", label: "Aplicação", icon: Syringe, desc: "Aplicação de medicamento/vacina — por animal ou por lote." },
      { id: "calendario_sanitario", label: "Calendário sanitário", icon: CalendarClock, desc: "Regra recorrente (sazonal/de rebanho ou por fase fisiológica): evento, frequência, produto e dosagem." },
      { id: "protocolo_sanitario", label: "Protocolo sanitário", icon: ClipboardList, desc: "Aplicar um protocolo cadastrado (mastite e outros) a um animal — gera um evento na Agenda por dia (D1, D2...)." },
    ],
  },
  {
    id: "financeiro", label: "Financeiro", icon: Wallet,
    desc: "Lançamento de receita ou despesa.",
    subs: [
      { id: "financeiro_despesa", label: "Contas a pagar (despesa)", icon: Wallet, desc: "Lançamento de despesa/conta a pagar." },
      { id: "financeiro_receita", label: "Contas a receber (receita)", icon: Wallet, desc: "Lançamento de receita/conta a receber." },
    ],
  },
  { id: "alimentacao_dieta", label: "Alimentação", icon: Wheat, desc: "Dieta por lote: plano programado, real oferecido e histórico de abertura/encerramento.", leaf: "alimentacao_dieta" },
  { id: "estoque", label: "Estoque", icon: Package, desc: "Entrada ou saída de item do estoque.", leaf: "estoque" },
  { id: "exclusao", label: "Exclusão", icon: Trash2, desc: "Apagar um lançamento já salvo, com prévia de impacto.", leaf: "exclusao" },
];

// Lista achatada de sub-tipos (folhas), usada para saber qual formulário renderizar.
const TIPOS_LEAFS = TIPOS_GRUPOS.flatMap((g) => (g.subs ? g.subs : [{ id: g.leaf!, label: g.label, icon: g.icon, desc: g.desc }]));
// Grupo dono de um determinado sub-tipo (folha).
const grupoDoSel = (id: string) => TIPOS_GRUPOS.find((g) => g.leaf === id || g.subs?.some((s) => s.id === id))?.id ?? "reprodutivo";

export default function LancamentosPage() {
  const [sel, setSel] = useState("protocolo_iatf");
  const [sujo, setSujo] = useState(false);
  // Atalho vindo da Agenda (ex.: "Ir para Inseminação" de um lembrete D11 de protocolo IATF).
  useEffect(() => {
    const ir = new URLSearchParams(window.location.search).get("ir");
    if (ir && TIPOS_LEAFS.some((t) => t.id === ir)) setSel(ir);
  }, []);
  const trocarTipo = (novoId: string) => {
    if (novoId === sel) return;
    if (sujo && !window.confirm("Você tem certeza que quer sair dessa página? Os dados não salvos serão perdidos.")) return;
    setSujo(false);
    setSel(novoId);
  };
  // Avisa também ao fechar a aba/recarregar/sair do site com dados não salvos.
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => { if (sujo) { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [sujo]);
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  const [estoque, setEstoque] = useState<EstoqueItem[]>([]);
  const [servicos, setServicos] = useState<any[]>([]);
  const [produtosSanidade, setProdutosSanidade] = useState<string[]>([]);
  useEffect(() => {
    fetchAnimais().then(setAnimais).catch(() => {});
    fetchEstoque().then((d) => setEstoque(d.itens || [])).catch(() => {});
    fetchServicosAnalise().then((d) => setServicos(d.servicos || [])).catch(() => {});
    fetchSanidade().then((d) => setProdutosSanidade(Array.from(new Set((d.aplicacoes || d.registros || []).map((r: any) => r.produto).filter(Boolean))).sort() as string[])).catch(() => {});
  }, []);

  // Última IA/cobertura por matriz (para o diagnóstico puxar automático).
  const ultServico = useMemo(() => {
    const m: Record<string, string> = {};
    servicos.forEach((s) => { if (s.numero && s.data && (!m[s.numero] || s.data > m[s.numero])) m[s.numero] = s.data; });
    return m;
  }, [servicos]);

  // Lotes: remove duplicados que diferem só por maiúscula/minúscula (ex.: "03 - Média"
  // e "03 - MÉDIA"), mantendo a versão em caixa-alta.
  const lotes = useMemo(() => {
    const porChave = new Map<string, string>();
    (animais.map((a) => a.grupo_primario).filter(Boolean) as string[]).forEach((l) => {
      const chave = l.toUpperCase();
      const atual = porChave.get(chave);
      if (!atual || l === l.toUpperCase()) porChave.set(chave, l === l.toUpperCase() ? l : atual || l);
    });
    return Array.from(porChave.values()).sort();
  }, [animais]);
  const lotesLact = useMemo(() => lotes.filter((l) => LACT.includes(cod(l))), [lotes]);
  // Fêmeas aptas a serviço: idade >= 13 meses (mantém as sem idade informada, por segurança).
  const aptasServico = useMemo(() => animais.filter((a) => {
    const idade = (a as any).idade_meses;
    return idade == null || idade >= IDADE_MIN_SERVICO;
  }), [animais]);
  const tipo = TIPOS_LEAFS.find((t) => t.id === sel)!;
  const grupoAtivo = grupoDoSel(sel);

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><ClipboardList size={22} style={{ color: "var(--dourado-light)" }} /> Lançamentos</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>Entrada de dados direto no sistema — escolha o tipo e preencha.</p>
      </div>

      <div className="card mb-4" style={{ display: "flex", gap: "0.6rem", alignItems: "flex-start", background: "rgba(94,26,46,0.18)" }}>
        <Info size={16} style={{ color: "var(--dourado-light)", marginTop: "0.15rem", flexShrink: 0 }} />
        <p style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
          {sel === "financeiro_despesa" || sel === "financeiro_receita" ? (
            <><strong style={{ color: "var(--text)" }}>Financeiro já grava de verdade.</strong> Os lançamentos aqui vão para o banco permanente e aparecem nas 5 abas de contas do menu Financeiro.</>
          ) : sel === "controle" ? (
            <><strong style={{ color: "var(--text)" }}>Controle leiteiro já grava de verdade.</strong> As pesagens lançadas aqui vão para o banco permanente.</>
          ) : sel === "pesagem" ? (
            <><strong style={{ color: "var(--text)" }}>Pesagem corporal já grava de verdade.</strong> Os pesos lançados aqui vão para o banco permanente e alimentam o relatório de GMD/GPD logo abaixo.</>
          ) : sel === "exclusao" ? (
            <><strong style={{ color: "var(--text)" }}>Exclusão apaga de verdade.</strong> Administradores excluem na hora; os demais usuários só solicitam, e a exclusão fica pendente de aprovação.</>
          ) : sel === "diagnostico" ? (
            <><strong style={{ color: "var(--text)" }}>Diagnóstico já grava de verdade.</strong> Um resultado marcado para retoque entra na agenda automaticamente.</>
          ) : sel === "estoque" ? (
            <><strong style={{ color: "var(--text)" }}>Estoque já grava de verdade.</strong> Entradas e saídas lançadas aqui atualizam a quantidade do item na hora.</>
          ) : sel === "alimentacao_dieta" ? (
            <><strong style={{ color: "var(--text)" }}>Dieta já grava de verdade.</strong> Só uma dieta fica ativa por lote; ao encerrar, você pode lançar a próxima na hora. A data prevista de encerramento entra na Agenda para análise.</>
          ) : sel === "sanidade_aplicacao" ? (
            <><strong style={{ color: "var(--text)" }}>Sanidade já grava de verdade.</strong> Aceita vários produtos por lançamento; a baixa de estoque só acontece quando a unidade escolhida bate com a do estoque.</>
          ) : sel === "calendario_sanitario" ? (
            <><strong style={{ color: "var(--text)" }}>Calendário sanitário já grava de verdade.</strong> Cada regra recorrente aparece na aba Sanidade &gt; Calendário sanitário, com filtro por data e por evento.</>
          ) : sel === "protocolo_sanitario" ? (
            <><strong style={{ color: "var(--text)" }}>Protocolo sanitário já grava de verdade.</strong> Cria um evento na Agenda por etapa (D1, D2...) — ao marcar "realizado", dá baixa automática do produto no Estoque.</>
          ) : sel === "secagem" ? (
            <><strong style={{ color: "var(--text)" }}>Secagem já grava de verdade.</strong> Ao salvar, sugere mover a vaca para o lote das secas — você confirma antes da mudança.</>
          ) : sel === "qualidade_leite" ? (
            <><strong style={{ color: "var(--text)" }}>Qualidade do leite já grava de verdade.</strong> Lance por uma vaca ou pelo tanque (todas as vacas em lactação) — alimenta o relatório e o gráfico de qualidade em Produção.</>
          ) : sel === "entrega_leite" ? (
            <><strong style={{ color: "var(--text)" }}>Entrega mensal já grava de verdade.</strong> Compara o controle leiteiro projetado do mês, a receita do laticínio e o que foi de fato entregue.</>
          ) : sel === "parto" ? (
            <><strong style={{ color: "var(--text)" }}>Parto/nascimento já grava de verdade.</strong> Cadastra a cria e sugere o lote de mãe e cria (confirmação antes de mover). Colostragem/IgG da 1ª cria também gravam — veja em Sanidade &gt; Relatório sanitário de bezerras.</>
          ) : sel === "protocolo_iatf" ? (
            <><strong style={{ color: "var(--text)" }}>Protocolo IATF já grava de verdade.</strong> Agenda só os passos hormonais (D0/D7/D9/D11) na Agenda — a inseminação em si é lançada à parte, na sub-aba Inseminação.</>
          ) : sel === "inseminacao" ? (
            <><strong style={{ color: "var(--text)" }}>Inseminação já grava de verdade.</strong> Registra a cobertura/IA (cio natural ou vinda de um protocolo IATF já agendado) e calcula a ordem/intervalo de tentativas.</>
          ) : null}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr] gap-4">
        <div className="card" style={{ padding: "0.5rem", alignSelf: "start" }}>
          <div className="space-y-1">
            {TIPOS_GRUPOS.map((g) => {
              const Icon = g.icon;
              const ativo = g.id === grupoAtivo;
              const alvo = g.subs ? (ativo ? sel : g.subs[0].id) : g.leaf!;
              return (
                <div key={g.id}>
                  <button onClick={() => trocarTipo(alvo)}
                    style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.55rem 0.7rem", borderRadius: "8px", cursor: "pointer", textAlign: "left",
                      border: "1px solid " + (ativo ? "var(--dourado)" : "transparent"), background: ativo ? "rgba(94,26,46,0.4)" : "transparent",
                      color: ativo ? "var(--dourado-light)" : "var(--text-muted)", fontSize: "0.85rem", fontWeight: ativo ? 700 : 500 }}>
                    <Icon size={16} /> {g.label}
                  </button>
                  {ativo && g.subs && (
                    <div className="space-y-1" style={{ paddingLeft: "1.4rem", marginTop: "0.2rem" }}>
                      {g.subs.map((s) => {
                        const SIcon = s.icon; const subAtivo = s.id === sel;
                        return (
                          <button key={s.id} onClick={() => trocarTipo(s.id)}
                            style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.4rem 0.6rem", borderRadius: "6px", cursor: "pointer", textAlign: "left",
                              border: "1px solid " + (subAtivo ? "var(--dourado)" : "transparent"), background: subAtivo ? "rgba(94,26,46,0.3)" : "transparent",
                              color: subAtivo ? "var(--dourado-light)" : "var(--text-muted)", fontSize: "0.78rem", fontWeight: subAtivo ? 700 : 500 }}>
                            <SIcon size={13} /> {s.label}
                          </button>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        <div className="card" onChange={() => sel !== "exclusao" && setSujo(true)}>
          <div className="card-header mb-1 flex items-center gap-2"><tipo.icon size={14} /> {tipo.label}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0.4rem 0 1rem" }}>{tipo.desc}</p>
          {sel === "protocolo_iatf" && <FormProtocoloIatf animais={aptasServico} />}
          {sel === "inseminacao" && <FormInseminacao animais={aptasServico} />}
          {sel === "diagnostico" && <FormDiagnostico animais={animais} ultServico={ultServico} />}
          {sel === "parto" && <FormParto animais={animais} />}
          {sel === "controle" && <FormControle animais={animais} lotesLact={lotesLact} />}
          {sel === "pesagem" && <FormPesagemCorporal animais={animais} lotes={lotes} />}
          {sel === "secagem" && <FormSecagem animais={animais} estoque={estoque} produtos={produtosSanidade} />}
          {sel === "qualidade_leite" && <FormQualidadeLeite animais={animais} />}
          {sel === "entrega_leite" && <FormEntregaLeite />}
          {sel === "sanidade_aplicacao" && <FormSanidade animais={animais} lotes={lotes} estoque={estoque} produtos={produtosSanidade} />}
          {sel === "calendario_sanitario" && <FormCalendarioSanitario estoque={estoque} />}
          {sel === "protocolo_sanitario" && <FormProtocoloSanitario animais={animais} />}
          {sel === "financeiro_despesa" && <FormFinanceiro tipo="despesa" responsaveis={RESPONSAVEIS} onSujo={setSujo} />}
          {sel === "financeiro_receita" && <FormFinanceiro tipo="receita" responsaveis={RESPONSAVEIS} onSujo={setSujo} />}
          {sel === "estoque" && <FormEstoque estoque={estoque} />}
          {sel === "alimentacao_dieta" && <FormAlimentacaoDieta lotes={lotes} />}
          {sel === "exclusao" && <FormExclusao />}
        </div>
      </div>
    </div>
  );
}
