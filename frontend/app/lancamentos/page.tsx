"use client";
import React, { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ClipboardList, Info, Heart, Stethoscope, Milk, Syringe, Wallet, Package, Baby, Scale,
  Search, ExternalLink, BookOpen, X, Plus, AlertTriangle, Trash2, Droplet, CalendarClock, Wheat,
  ChevronDown, ChevronRight, ArrowRightLeft, ShoppingCart, Skull, HeartPulse, Shield, Droplets, Check, Dna,
} from "lucide-react";
import {
  fetchAnimais, fetchEstoque, fetchServicosAnalise, fetchSanidade, criarControlesLeiteiros, salvarDiagnostico, movimentarEstoque, criarAplicacaoSanidade, marcarEventoRealizado,
  fetchSecagemInfo, criarSecagem, sugestaoLoteEvento, criarMovimentacao, criarParto, formatDate,
  criarProtocoloIatf, criarServicoLote, fetchSemenDisponivel, fetchProtocolosIatfAtivos, fetchLancamentosIatf, adicionarAnimaisIatf,
  fetchEventosSanitarios, fetchDoencas, fetchPrincipiosAtivos, fetchCalendarioSanitario, criarCalendarioSanitario, atualizarCalendarioSanitario, excluirCalendarioSanitario, cadastrarPreventivo, fetchAgenda,
  fetchExames,
  atualizarEventoSanitario, fetchEventosVidaVocabulario, fetchRelatorioEventosVida,
  fetchAlimentosPadrao, fetchDietas, encerrarDieta, registrarRealDieta, fetchComparativoDieta,
  fetchProtocolosSanitarios, lancarProtocoloSanitario, fetchMastiteOpcoes, fetchMastiteContexto, fetchLotes, previewCriteriosLote, fetchMedicamentos,
  fetchQualidadeLeite, criarQualidadeLeite, criarEntregaLeiteMensal, registrarColostragem,
  fetchApresentacoesFarmacia, fetchTouros,
  fetchProtocolosInducaoLactacao, lancarInducaoLactacao, fetchInducaoLactacaoAtivos,
  baixarModeloControleLeiteiro, importarControleLeiteiroPlanilha, baixarModeloQualidadeLeite, importarQualidadeLeitePlanilha,
  fetchPedidos, fetchPedido,
  fetchCategoriasManejo, fetchPlanoContas, FINALIDADES_ESTOQUE,
} from "@/lib/api";
import type { ApresentacaoFarmacia, Touro } from "@/lib/api";
import { pedirLancamentoFinanceiro } from "@/lib/estoqueFinanceiroBridge";
import { RESPONSAVEIS, VIAS_APLICACAO } from "@/lib/constants";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPicker } from "@/components/AnimalPicker";
import { TouroPicker, type TouroPickerItem } from "@/components/TouroPicker";
import { SelecaoAnimaisTabela } from "@/components/SelecaoAnimaisTabela";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { SelecaoLotesTabela, LoteRow } from "@/components/SelecaoLotesTabela";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { EstoquePicker } from "@/components/EstoquePicker";
import { FormFinanceiro } from "@/components/FormFinanceiro";
import { FormExclusao } from "@/components/FormExclusao";
import { FormPesagemCorporal } from "@/components/FormPesagemCorporal";
import { UploadPlanilha } from "@/components/UploadPlanilha";
import MovimentarAnimais from "@/components/MovimentarAnimais";
import CompraVendaAnimalForm from "@/components/CompraVendaAnimalForm";
import CompraSemenForm from "@/components/CompraSemenForm";
import BaixarAnimal from "@/components/BaixarAnimal";
import { EditorHormoniosIatf } from "@/components/EditorHormoniosIatf";
import { TabelaNutricionalBotao } from "@/components/TabelaNutricional";
import type { HormonioIatf, SemenDisponivel } from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { TabBar, SecaoRecolhivel, MultiFiltro } from "@/components/ui";
import { useSubNavRegister, type SubNavNode } from "@/components/SubNavContext";
import { Modal } from "@/components/Modal";
import { PainelLancarBst } from "@/components/PainelLancarBst";
import { CadastroProtocolosSanitarios, CadastroEventosSanitarios } from "@/components/CadastroSanitario";
import { CadastrarNovaDieta } from "@/components/CadastroAlimentacao";
import { FormSecagem } from "@/components/FormSecagem";
import { FormQualidadeLeite } from "@/components/FormQualidadeLeite";
import { FormEntregaLeite } from "@/components/FormEntregaLeite";
import { FormInducaoLactacao } from "@/components/FormInducaoLactacao";
import {
  Campo, Secao, inputStyle, lbl, nota,
  type EstoqueItem, type ItemSanidade, itemSanidadeVazio, unidadesCompativeis, EstoqueRestante, codigoGrupo, MOTIVOS_SECAGEM,
} from "@/components/lancamentos/comumForms";

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
const UNIDADES = ["ml", "kg", "L", "unidade", "dose", "saca 30kg", "saca 60kg"];
const MOVIMENTOS_ESTOQUE = ["Aplicação", "Saída de ajuste", "Entrada de ajuste", "Entrada de cortesia", "Doação"];
// Movimentos que reduzem o estoque (baixa).
const MOV_BAIXA = new Set(["Aplicação", "Saída de ajuste", "Doação"]);
const MOVIMENTOS_SOMENTE_ESTOCAVEL = new Set(["Doação", "Entrada de cortesia"]);

function addDias(iso: string, n: number): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00"); d.setDate(d.getDate() + n);
  return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" });
}

// Nome padrão do protocolo IATF: "IATF <D0> A <D11>" (datas dd/mm/aa).
function nomeAutoIatf(d0: string): string {
  if (!d0) return "";
  const fmt = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" });
  const d11 = new Date(d0 + "T00:00:00"); d11.setDate(d11.getDate() + 11);
  return `IATF ${fmt(d0)} A ${fmt(d11.toISOString().slice(0, 10))}`;
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
  // Novo protocolo (cria um lançamento) ou adicionar animais a um já existente.
  const [modo, setModo] = useState<"novo" | "existente">("novo");
  const [emLote, setEmLote] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [um, setUm] = useState("");
  const [d0, setD0] = useState("");
  const [hormonios, setHormonios] = useState<HormonioIatf[]>([]);
  // Protocolos já lançados (para "existente").
  const [existentes, setExistentes] = useState<{ lancamento_id: number; nome_protocolo: string; data_d0: string; qtd_animais: number }[]>([]);
  const [existenteId, setExistenteId] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const recarregarAtivosRef = useRef(() => {});
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleTodos = () => setSel((p) => (p.size === animais.length && animais.length ? new Set() : new Set(animais.map((a) => a.numero))));

  const nomeProtocolo = nomeAutoIatf(d0);

  useEffect(() => {
    if (modo === "existente") fetchLancamentosIatf().then(setExistentes).catch(() => setExistentes([]));
  }, [modo]);

  async function salvar() {
    setErro(null); setSucesso(null);
    const animaisAlvo = emLote ? Array.from(sel) : (um ? [um] : []);
    if (!animaisAlvo.length) { setErro(emLote ? "Selecione ao menos um animal." : "Selecione a matriz."); return; }
    setSalvando(true);
    try {
      if (modo === "existente") {
        if (!existenteId) { setErro("Selecione o protocolo existente."); setSalvando(false); return; }
        const r = await adicionarAnimaisIatf(Number(existenteId), animaisAlvo);
        setSucesso(`${r.adicionados} animal(is) adicionado(s) ao protocolo "${r.nome_protocolo}".`);
      } else {
        if (!d0) { setErro("Informe a data do D0."); setSalvando(false); return; }
        const r = await criarProtocoloIatf({ animais: animaisAlvo, data_d0: d0, protocolo: nomeProtocolo, hormonios });
        setSucesso(`Protocolo "${nomeProtocolo}" agendado para ${r.animais} animal(is) — ${r.eventos_criados} eventos na Agenda (D0/D7/D9/D11).`);
      }
      setSel(new Set()); setUm("");
      recarregarAtivosRef.current();
      if (modo === "existente") fetchLancamentosIatf().then(setExistentes).catch(() => {});
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar protocolo IATF");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <TabBar<"novo" | "existente">
        abas={[
          { id: "novo", label: "Novo protocolo", title: "Criar um novo protocolo IATF (define D0 e hormônios)" },
          { id: "existente", label: "Adicionar a protocolo existente", title: "Incluir animais num protocolo já lançado (mesmo D0 e nome)" },
        ]}
        ativa={modo}
        onChange={setModo}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <Campo label="Seleção">
          <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}>
            <input type="checkbox" checked={emLote} onChange={(e) => setEmLote(e.target.checked)} /> Em lote (vários animais)
          </label>
        </Campo>
        {modo === "novo" ? (
          <>
            <Campo label="Data do D0"><input type="date" style={inputStyle} value={d0} onChange={(e) => setD0(e.target.value)} /></Campo>
            <Campo label="Nome do protocolo (automático)" full>
              <input style={{ ...inputStyle, opacity: 0.85 }} readOnly value={nomeProtocolo || "Informe a data do D0…"} />
            </Campo>
          </>
        ) : (
          <Campo label="Protocolo existente" full>
            <select style={inputStyle} value={existenteId} onChange={(e) => setExistenteId(e.target.value)}>
              <option value="">Selecione o protocolo…</option>
              {existentes.map((l) => <option key={l.lancamento_id} value={l.lancamento_id}>{l.nome_protocolo} — {l.qtd_animais} animal(is)</option>)}
            </select>
          </Campo>
        )}
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

      {modo === "novo" && (
        <>
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
          <EditorHormoniosIatf onChange={setHormonios} />
        </>
      )}
      <ProtocolosIatfAtivos recarregarRef={recarregarAtivosRef} />
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
      </div>
    </>
  );
}

const CAT_TOURO = [
  { id: "convencional" as const, label: "Convencional" },
  { id: "sexado" as const, label: "Sexado" },
  { id: "fazenda" as const, label: "Touro da fazenda" },
];

function FormInseminacao({ animais }: { animais: AnimalRow[] }) {
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [dataServico, setDataServico] = useState("");
  const [tipo, setTipo] = useState<"cio_natural" | "iatf" | "monta_natural">("cio_natural");
  const [categoria, setCategoria] = useState<"convencional" | "sexado" | "fazenda">("convencional");
  const [touro, setTouro] = useState("");
  const [responsavel, setResponsavel] = useState("");
  // IATF: vincular a um lançamento já existente + auto-lançar retroativo.
  const [protocoloId, setProtocoloId] = useState("");
  const [autoLancar, setAutoLancar] = useState(false);
  const [lancamentos, setLancamentos] = useState<{ lancamento_id: number; nome_protocolo: string; data_d0: string }[]>([]);
  const [semen, setSemen] = useState<SemenDisponivel | null>(null);
  // Origem da seleção: avulsa (qualquer matriz apta) ou vinda de um protocolo
  // IATF em andamento — nesse caso a lista se restringe às matrizes no D11.
  const [origemSelecao, setOrigemSelecao] = useState<"avulsa" | "protocolo">("avulsa");
  const [protocolosAtivos, setProtocolosAtivos] = useState<{ lancamento_id: number; nome_protocolo: string; data_d0: string; animais: { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null }[] }[]>([]);
  useEffect(() => { fetchProtocolosIatfAtivos().then(setProtocolosAtivos).catch(() => setProtocolosAtivos([])); }, []);
  const protocolosD11 = useMemo(
    () => protocolosAtivos
      .map((p) => ({ ...p, animaisD11: p.animais.filter((a) => a.etapa_atual === "D11") }))
      .filter((p) => p.animaisD11.length > 0),
    [protocolosAtivos]
  );
  const mapaProtocoloPorAnimal = useMemo(() => {
    const m = new Map<string, string>();
    protocolosD11.forEach((p) => p.animaisD11.forEach((a) => m.set(a.numero_matriz, p.nome_protocolo)));
    return m;
  }, [protocolosD11]);
  const animaisProtocolo = useMemo(() => animais.filter((a) => mapaProtocoloPorAnimal.has(a.numero)), [animais, mapaProtocoloPorAnimal]);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  // "Incluir touros sem estoque": troca a fonte da seleção de touro pelo
  // catálogo NAAB completo, em vez de restringir aos que têm dose no estoque.
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [catalogoTouros, setCatalogoTouros] = useState<Touro[]>([]);
  useEffect(() => {
    if (incluirSemEstoque && !catalogoTouros.length) fetchTouros().then(setCatalogoTouros).catch(() => {});
  }, [incluirSemEstoque, catalogoTouros.length]);
  const itensCatalogoTouros: TouroPickerItem[] = useMemo(
    () => catalogoTouros.map((t) => ({ naab: t.naab, nome: t.nome || t.naab, central: t.central, raca: t.raca, tpi: t.tpi })),
    [catalogoTouros]
  );

  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleTodos = () => setSel((p) => (p.size === animais.length && animais.length ? new Set() : new Set(animais.map((a) => a.numero))));

  // Inseminação avulsa: animal(is) ou lote(s) — dentro de lote, pode escolher
  // mais de um; o protocolo IATF em andamento continua só por animal (D11).
  const [vinculoInsem, setVinculoInsem] = useState<"animal" | "lote">("animal");
  const [lotesSelecionadosInsem, setLotesSelecionadosInsem] = useState<string[]>([]);
  const codigosLotesAptas = useMemo(
    () => Array.from(new Set(animais.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [animais]
  );
  const animaisDoLoteInsem = useMemo(() => {
    const cods = new Set(lotesSelecionadosInsem);
    return animais.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [animais, lotesSelecionadosInsem]);
  // Ao escolher lote(s), começa com todas as aptas do(s) lote(s) marcadas;
  // a janela suspensa abaixo permite desmarcar animal a animal.
  const [selLoteInsem, setSelLoteInsem] = useState<Set<string>>(new Set());
  const toggleLoteInsem = (n: string) => setSelLoteInsem((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelLoteInsem(new Set(animaisDoLoteInsem.map((a) => a.numero)));
  }, [lotesSelecionadosInsem.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  const alvoFinal = useMemo(
    () => (origemSelecao === "avulsa" && vinculoInsem === "lote" ? selLoteInsem : sel),
    [origemSelecao, vinculoInsem, selLoteInsem, sel]
  );

  useEffect(() => {
    fetchSemenDisponivel().then(setSemen).catch(() => setSemen(null));
    fetchLancamentosIatf().then(setLancamentos).catch(() => setLancamentos([]));
  }, []);

  // Vindo da Agenda (link "Ir para Inseminação" do D11): pré-seleciona matriz + IATF.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    const numeroMatriz = qs.get("numero_matriz");
    if (numeroMatriz) setSel(new Set([numeroMatriz]));
    if (qs.get("protocolo")) { setTipo("iatf"); setOrigemSelecao("protocolo"); }
  }, []);

  // Na origem "protocolo", quando a seleção pertence a um único lançamento
  // IATF, vincula automaticamente — evita o usuário ter que escolher à toa.
  useEffect(() => {
    if (origemSelecao !== "protocolo") return;
    const ids = new Set<number>();
    sel.forEach((n) => {
      const p = protocolosD11.find((pp) => pp.animaisD11.some((a) => a.numero_matriz === n));
      if (p) ids.add(p.lancamento_id);
    });
    setProtocoloId(ids.size === 1 ? String([...ids][0]) : "");
  }, [sel, origemSelecao, protocolosD11]);

  // Touro da fazenda ⇒ sempre monta natural.
  useEffect(() => { if (categoria === "fazenda") setTipo("monta_natural"); }, [categoria]);

  const tourosDaCategoria = useMemo(
    () => (semen?.touros || []).filter((t) => t.tipo === categoria),
    [semen, categoria]
  );

  async function salvar() {
    setErro(null); setSucesso(null);
    const alvo = Array.from(alvoFinal);
    if (!alvo.length) { setErro("Selecione ao menos uma matriz."); return; }
    if (!dataServico) { setErro("Informe a data da inseminação."); return; }
    setSalvando(true);
    try {
      const r = await criarServicoLote({
        animais: alvo, data_servico: dataServico, tipo,
        reprodutor: touro || undefined, responsavel: responsavel || undefined,
        protocolo_lancamento_id: tipo === "iatf" && protocoloId ? Number(protocoloId) : null,
        auto_lancar_iatf: tipo === "iatf" ? autoLancar : false,
        tipo_semen: categoria === "fazenda" ? null : categoria,
      });
      if (r.incompativeis.length) {
        setVinculoInsem("animal"); setLotesSelecionadosInsem([]); setSel(new Set(r.incompativeis));
        setErro(`${r.incompativeis.join(", ")} não estão em nenhum protocolo IATF. Vincule a um protocolo existente ou marque "lançar protocolo automaticamente (D0 retroativo)" e salve de novo.`);
        if (r.criados) setSucesso(`${r.criados} inseminação(ões) registrada(s).`);
      } else {
        setSucesso(`${r.criados} inseminação(ões) registrada(s)${tipo === "iatf" ? " (IATF)" : tipo === "monta_natural" ? " (monta natural)" : " (cio natural)"}.`);
        setSel(new Set()); setLotesSelecionadosInsem([]); setTouro("");
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao registrar inseminação");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      {semen && (semen.abaixo_minimo.convencional || semen.abaixo_minimo.sexado) && (
        <div className="mb-3" style={{ display: "flex", gap: "0.5rem", alignItems: "flex-start", background: "rgba(220,38,38,0.1)", border: "1px solid var(--red)", borderRadius: 8, padding: "0.6rem 0.8rem" }}>
          <AlertTriangle size={16} style={{ color: "var(--red)", marginTop: "0.1rem" }} />
          <span style={{ fontSize: "0.8rem" }}>
            Estoque de sêmen abaixo do mínimo:{" "}
            {semen.abaixo_minimo.convencional && `convencional ${semen.totais.convencional}/${semen.minimos.convencional}`}
            {semen.abaixo_minimo.convencional && semen.abaixo_minimo.sexado && " · "}
            {semen.abaixo_minimo.sexado && `sexado ${semen.totais.sexado}/${semen.minimos.sexado}`}. Registre a compra na NF.
          </span>
        </div>
      )}

      <div className="mb-3">
        <label style={lbl}>Origem da inseminação</label>
        <TabBar<"avulsa" | "protocolo">
          abas={[
            { id: "avulsa", label: "Inseminação avulsa", title: "Escolher livremente entre as matrizes aptas" },
            { id: "protocolo", label: "Protocolo de IATF atual", title: "Mostrar apenas as matrizes no D11 de um protocolo IATF em andamento" },
          ]}
          ativa={origemSelecao}
          onChange={(o) => { setOrigemSelecao(o); setSel(new Set()); setLotesSelecionadosInsem([]); setVinculoInsem("animal"); if (o === "protocolo") setTipo("iatf"); }}
        />
        {origemSelecao === "protocolo" && !animaisProtocolo.length && (
          <p style={{ ...nota, color: "var(--amber)" }}>Nenhuma matriz está no D11 de um protocolo IATF em andamento no momento.</p>
        )}
      </div>

      <Campo label={origemSelecao === "protocolo" ? "Matrizes no D11 do protocolo IATF — pode selecionar várias" : "Matriz / novilha (aptas) — animal(is) ou lote(s)"} full>
        {origemSelecao === "protocolo" ? (
          <AnimalPickerModal
            animais={animaisProtocolo}
            selecionados={sel} onToggle={toggle}
            titulo="Escolher matrizes no D11 (IATF)"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
              { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
              { header: "Protocolo", render: (a: AnimalRow) => mapaProtocoloPorAnimal.get(a.numero) || "—" },
            ]}
          />
        ) : (
          <>
            <TabBar<"animal" | "lote">
              abas={[
                { id: "animal", label: "Animal(is)", title: "Selecionar matrizes/novilhas individualmente" },
                { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes — mostra as aptas de cada lote escolhido" },
              ]}
              ativa={vinculoInsem}
              onChange={setVinculoInsem}
            />
            {vinculoInsem === "animal" ? (
              <AnimalPickerModal
                animais={animais}
                selecionados={sel} onToggle={toggle}
                titulo="Escolher matriz / novilha"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
                ]}
              />
            ) : (
              <div style={{ marginTop: "0.5rem" }}>
                <LotePicker
                  opcoes={opcoesLoteDeAnimais(animais, codigosLotesAptas)}
                  selecionados={lotesSelecionadosInsem}
                  onChange={setLotesSelecionadosInsem}
                  placeholder="Selecionar lote(s)…"
                />
                {lotesSelecionadosInsem.length > 0 && (
                  <div style={{ marginTop: "0.6rem" }}>
                    <AnimalPickerModal
                      animais={animaisDoLoteInsem} selecionados={selLoteInsem} onToggle={toggleLoteInsem}
                      titulo="Ajustar aptas do(s) lote(s) selecionado(s)"
                      placeholder="Ajustar aptas do(s) lote(s)…"
                      colunas={[
                        { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                        { header: "Lote", render: (a) => a.grupo_primario || "—" },
                        { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
                      ]}
                    />
                    <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                      {selLoteInsem.size} de {animaisDoLoteInsem.length} apta(s) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir alguma.
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </Campo>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <Campo label="Data da inseminação"><input type="date" style={inputStyle} value={dataServico} onChange={(e) => setDataServico(e.target.value)} /></Campo>
        <Campo label="Categoria do touro / sêmen">
          <select style={inputStyle} value={categoria} onChange={(e) => { setCategoria(e.target.value as typeof categoria); setTouro(""); }}>
            {CAT_TOURO.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </select>
        </Campo>
        <Campo label={`Touro (${categoria === "fazenda" ? "monta natural" : incluirSemEstoque ? "catálogo NAAB completo" : "em estoque"})`}>
          {!incluirSemEstoque ? (
            <select style={inputStyle} value={touro} onChange={(e) => setTouro(e.target.value)}>
              <option value="">Selecione…</option>
              {tourosDaCategoria.map((t) => <option key={t.nome} value={t.nome}>{t.nome}{t.tipo !== "fazenda" ? ` (${t.doses} doses)` : ""}</option>)}
            </select>
          ) : (
            <TouroPicker style={inputStyle} itens={itensCatalogoTouros} value={touro} placeholder="Buscar touro no catálogo NAAB..."
              onChangeTexto={setTouro} onSelecionar={(t) => setTouro(t.nome)} />
          )}
          {!incluirSemEstoque && !tourosDaCategoria.length && <p style={{ fontSize: "0.72rem", color: "var(--amber)", marginTop: 2 }}>Nenhum touro {categoria} em estoque.</p>}
          {categoria !== "fazenda" && (
            <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", marginTop: "0.4rem", fontSize: "0.76rem", color: "var(--text-muted)", cursor: "pointer" }}>
              <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => { setIncluirSemEstoque(e.target.checked); setTouro(""); }} />
              Incluir touros sem estoque (catálogo completo NAAB)
            </label>
          )}
        </Campo>
        <Campo label="Responsável / inseminador">
          <select style={inputStyle} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}><option value="">Selecione…</option>{RESPONSAVEIS.map((r) => <option key={r}>{r}</option>)}</select>
        </Campo>
      </div>

      <div className="mt-3">
        <label style={lbl}>Tipo de cobertura</label>
        <TabBar<"cio_natural" | "iatf" | "monta_natural">
          abas={[
            { id: "cio_natural", label: "Cio natural", title: "Inseminação de cio natural (sem protocolo)" },
            { id: "iatf", label: "IATF", title: "Inseminação de um protocolo IATF" },
            { id: "monta_natural", label: "Monta natural", title: "Cobertura por touro (monta natural)" },
          ]}
          ativa={tipo}
          onChange={(t) => { if (categoria !== "fazenda" && origemSelecao !== "protocolo") setTipo(t); }}
        />
        {categoria === "fazenda" && <p style={nota}>Touro da fazenda selecionado — registrado como <strong>monta natural</strong>.</p>}
        {origemSelecao === "protocolo" && <p style={nota}>Origem "Protocolo de IATF atual" — sempre registrado como <strong>IATF</strong>.</p>}
      </div>

      {tipo === "iatf" && origemSelecao === "protocolo" && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <p style={{ fontSize: "0.82rem" }}>
            {protocoloId
              ? <>Vinculado automaticamente ao protocolo <strong>{protocolosD11.find((p) => String(p.lancamento_id) === protocoloId)?.nome_protocolo}</strong>.</>
              : "Cada matriz será vinculada ao seu próprio protocolo IATF em andamento (detectado automaticamente)."}
          </p>
        </div>
      )}

      {tipo === "iatf" && origemSelecao === "avulsa" && (
        <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <Campo label="Vincular ao protocolo IATF">
              <select style={inputStyle} value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
                <option value="">Automático (o protocolo pendente do animal)</option>
                {lancamentos.map((l) => <option key={l.lancamento_id} value={l.lancamento_id}>{l.nome_protocolo}</option>)}
              </select>
            </Campo>
            <Campo label="Se o animal não estiver em protocolo">
              <label className="flex items-center gap-2" style={{ fontSize: "0.82rem", padding: "0.45rem 0" }}>
                <input type="checkbox" checked={autoLancar} onChange={(e) => setAutoLancar(e.target.checked)} /> Lançar protocolo automaticamente (D0 retroativo)
              </label>
            </Campo>
          </div>
          <p style={nota}>O protocolo automático conta o D0 para trás (data do serviço − 11 dias) e só registra o protocolo — não gera aplicação de hormônio.</p>
        </div>
      )}

      <p style={nota}>Matriz lista apenas fêmeas aptas (≥ {IDADE_MIN_SERVICO} meses).</p>
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

  // Animal(is) ou lote(s) — dentro de lote, pode escolher mais de um; a lista de
  // animais mostrada é sempre a das servidas dentro do(s) lote(s) escolhido(s).
  const [vinculo, setVinculo] = useState<"animal" | "lote">("animal");
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const codigosLotesServidas = useMemo(
    () => Array.from(new Set(servidas.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [servidas]
  );
  const animaisDoLote = useMemo(() => {
    const cods = new Set(lotesSelecionados);
    return servidas.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [servidas, lotesSelecionados]);
  // Ao escolher lote(s), começa com todas as servidas do(s) lote(s) marcadas;
  // a janela suspensa abaixo permite desmarcar animal a animal.
  const [selLote, setSelLote] = useState<Set<string>>(new Set());
  const toggleLote = (n: string) => setSelLote((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelLote(new Set(animaisDoLote.map((a) => a.numero)));
  }, [lotesSelecionados.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps
  const numerosAlvo = useMemo(
    () => (vinculo === "lote" ? selLote : selecionados),
    [vinculo, selLote, selecionados]
  );

  const [data, setData] = useState("");
  const [metodo, setMetodo] = useState("");
  const [resultado, setResultado] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Animais selecionados com menos de 30 dias desde a última inseminação/cobertura.
  const animaisComAviso = useMemo(() => {
    if (!data) return [];
    return Array.from(numerosAlvo).filter((n) => {
      const us = ultServico[n];
      if (!us) return false;
      const dias = (new Date(data + "T00:00:00").getTime() - new Date(us + "T00:00:00").getTime()) / 86400000;
      return dias >= 0 && dias < 30;
    });
  }, [numerosAlvo, data, ultServico]);

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!numerosAlvo.size || !data || !resultado) { setErro("Selecione ao menos uma matriz, a data e o resultado do diagnóstico."); return; }
    setSalvando(true);
    // Loop por animal: registra quais salvaram e quais falharam, para não perder
    // o trabalho já feito nem a seleção dos que precisam de nova tentativa.
    const salvos: string[] = [];
    const falhados: string[] = [];
    try {
      for (const numero of numerosAlvo) {
        try {
          await salvarDiagnostico({ numero_matriz: numero, data_diagnostico: data, resultado: resultado as any, metodo: metodo || undefined });
          salvos.push(numero);
        } catch {
          falhados.push(numero);
        }
      }
      if (falhados.length) {
        // Sucesso parcial: passa para seleção individual só com quem falhou, para reenviar.
        setVinculo("animal"); setLotesSelecionados([]); setSelecionados(new Set(falhados));
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
        setSelecionados(new Set()); setLotesSelecionados([]); setData(""); setMetodo(""); setResultado("");
      }
    } catch (e: any) {
      setErro(e.message || "Erro ao salvar diagnóstico");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <Campo label="Matriz / novilha (servidas) — animal(is) ou lote(s)" full>
        <TabBar<"animal" | "lote">
          abas={[
            { id: "animal", label: "Animal(is)", title: "Selecionar matrizes/novilhas individualmente" },
            { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes — mostra as servidas de cada lote escolhido" },
          ]}
          ativa={vinculo}
          onChange={setVinculo}
        />
        {vinculo === "animal" ? (
          <AnimalPickerModal
            animais={servidas} selecionados={selecionados} onToggle={toggle}
            titulo="Escolher matriz / novilha servida"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
              { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
              { header: "Última IA/cobertura", render: (a) => ultServico[a.numero] ? new Date(ultServico[a.numero] + "T00:00:00").toLocaleDateString("pt-BR") : "—" },
            ]}
          />
        ) : (
          <div style={{ marginTop: "0.5rem" }}>
            <LotePicker
              opcoes={opcoesLoteDeAnimais(servidas, codigosLotesServidas)}
              selecionados={lotesSelecionados}
              onChange={setLotesSelecionados}
              placeholder="Selecionar lote(s)…"
            />
            {lotesSelecionados.length > 0 && (
              <div style={{ marginTop: "0.6rem" }}>
                <AnimalPickerModal
                  animais={animaisDoLote} selecionados={selLote} onToggle={toggleLote}
                  titulo="Ajustar servidas do(s) lote(s) selecionado(s)"
                  placeholder="Ajustar servidas do(s) lote(s)…"
                  colunas={[
                    { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                    { header: "Lote", render: (a) => a.grupo_primario || "—" },
                    { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
                    { header: "Última IA/cobertura", render: (a) => ultServico[a.numero] ? new Date(ultServico[a.numero] + "T00:00:00").toLocaleDateString("pt-BR") : "—" },
                  ]}
                />
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                  {selLote.size} de {animaisDoLote.length} servida(s) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir alguma.
                </p>
              </div>
            )}
          </div>
        )}
      </Campo>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        <Campo label="Data do diagnóstico"><input type="date" style={inputStyle} value={data} onChange={(e) => setData(e.target.value)} /></Campo>
        <Campo label="Método">
          <select style={inputStyle} value={metodo} onChange={(e) => setMetodo(e.target.value)}>
            <option value="" disabled>Selecione…</option><option>Palpação</option><option>Ultrassom</option><option>Cio de repasse</option>
          </select>
        </Campo>
        <Campo label="Resultado" full>
          <select style={inputStyle} value={resultado} onChange={(e) => setResultado(e.target.value)}>
            <option value="" disabled>Selecione…</option>
            <option value="retoque">Positivo — marcar para retoque (segue em observação para reconfirmar)</option>
            <option value="reconfirmada">Positivo — reconfirmada (prenhez confirmada)</option>
            <option value="negativo">Negativo (vazia)</option>
            <option value="indefinido">Indefinido (inconclusivo — reavaliar)</option>
          </select>
        </Campo>
      </div>
      {metodo === "Cio de repasse" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.4rem" }}>
          <strong>Cio de repasse:</strong> a vaca retornou ao cio após a inseminação. Detecção esperada — scratch (adesivo) aplicado por volta de 14 dias após a última IA/monta e cio natural observado entre 15 e 28 dias após o scratch.
        </p>
      )}

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
      {resultado === "indefinido" && (
        <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.6rem" }}>
          Resultado <strong>inconclusivo</strong> — a matriz <strong>não</strong> vira vazia; segue para nova avaliação.
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

// Eficiência de colostragem em 4 níveis por Brix sérico (%) OU proteína
// sérica (g/dL) — o que estiver disponível (Brix tem prioridade).
function classeColostragemUI(brix: number | null, proteina: number | null): { txt: string; cor: string } {
  const excelente = { txt: "Excelente", cor: "var(--green-light)" };
  const boa = { txt: "Boa", cor: "var(--dourado-light)" };
  const aceitavel = { txt: "Aceitável", cor: "var(--amber)" };
  const ruim = { txt: "Ruim — bezerra desprotegida", cor: "var(--red)" };
  if (brix != null && !Number.isNaN(brix)) {
    if (brix > 9.4) return excelente;
    if (brix >= 8.9) return boa;
    if (brix >= 8.1) return aceitavel;
    return ruim;
  }
  if (proteina != null && !Number.isNaN(proteina)) {
    if (proteina > 6.2) return excelente;
    if (proteina >= 5.8) return boa;
    if (proteina >= 5.1) return aceitavel;
    return ruim;
  }
  return { txt: "—", cor: "var(--text-muted)" };
}

function FormParto({ animais, lotes }: { animais: AnimalRow[]; lotes: string[] }) {
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [matriz, setMatriz] = useState("");
  const [dataParto, setDataParto] = useState(() => new Date().toISOString().slice(0, 10));
  const [tipoParto, setTipoParto] = useState("");
  const [gemelar, setGemelar] = useState(false);
  const [gemelarSexo, setGemelarSexo] = useState("");
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
  const [horaParto, setHoraParto] = useState("");
  const [horaColostro, setHoraColostro] = useState("");
  const [pesoNascer, setPesoNascer] = useState("");
  const [manualColostroAberto, setManualColostroAberto] = useState(false);
  const [manualSangueAberto, setManualSangueAberto] = useState(false);

  const [soro, setSoro] = useState("");
  const [proteinaSerica, setProteinaSerica] = useState("");
  const [apenasColostroPo, setApenasColostroPo] = useState(false);
  const brixN = brix ? Number(brix) : null;
  const litrosN = litros ? Number(litros) : 0;
  const cls = brixN != null ? classeColostro(brixN) : null;
  const soroN = soro ? Number(soro) : null;
  const clsSoro = soroN != null ? classeSoro(soroN) : null;
  const enriquecer = brixN != null && brixN < 25;
  const medidasPorL = enriquecer ? Math.max(0, Number(alvo) - brixN!) : 0;
  const totalMedidas = medidasPorL * (litrosN || 1);
  // Intervalo parto→colostro em horas (a partir de "HH:MM"), tratando virada de dia.
  const intervaloColostroHoras = (() => {
    if (!horaParto || !horaColostro) return null;
    const [hp, mp] = horaParto.split(":").map(Number);
    const [hc, mc] = horaColostro.split(":").map(Number);
    if ([hp, mp, hc, mc].some((n) => Number.isNaN(n))) return null;
    let diff = (hc * 60 + mc) - (hp * 60 + mp);
    if (diff < 0) diff += 24 * 60; // colostro no dia seguinte ao parto
    return diff / 60;
  })();

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

  // Nascimento: o bezerro cai automaticamente no lote sugerido (bezerreiro),
  // sem perguntar — diferente da mãe, aqui não há confirmação nenhuma.
  async function alocarSemConfirmar(numero: string, categoriaAbrev: string, extra: { del_dias?: number | null; data_nasc?: string | null }, motivo: string, falhas: string[]) {
    try {
      const { lote_sugerido } = await sugestaoLoteEvento({ numero_matriz: numero, categoria_abrev: categoriaAbrev, ...extra });
      if (lote_sugerido) {
        await criarMovimentacao({ data_movimento: dataParto, motivo, lote_destino_codigo: lote_sugerido.codigo, animais: [numero] });
        return lote_sugerido.rotulo as string;
      }
    } catch (e: any) {
      falhas.push(`alocação do animal ${numero} não pôde ser feita${e?.message ? `: ${e.message}` : ""}`);
    }
    return null;
  }

  // Lançamento em lote: partos simples (sem gêmeos/colostro/IgG) de várias
  // matrizes de um mesmo lote de uma vez — mesma data e tipo de parto para
  // todas, cria/retenção de placenta editável linha a linha. Cada linha chama
  // o mesmo endpoint do lançamento único (não existe endpoint de parto em
  // lote no backend); a mudança de lote da mãe (que pede confirmação one-by-one
  // no modo "Uma matriz") não é feita automaticamente aqui para não abrir N
  // caixas de confirmação — só a alocação da cria (sem confirmação) é mantida.
  const [loteBatch, setLoteBatch] = useState("");
  const [selBatch, setSelBatch] = useState<Set<string>>(new Set());
  const [dadosBatch, setDadosBatch] = useState<Record<string, { criaNumero: string; criaSexo: string; criaBaixada: boolean; retencaoPlacenta: boolean }>>({});
  const [salvandoBatch, setSalvandoBatch] = useState(false);
  const [erroBatch, setErroBatch] = useState<string | null>(null);
  const [sucessoBatch, setSucessoBatch] = useState<string | null>(null);

  const animaisDoLoteBatch = useMemo(() => (loteBatch ? animais.filter((a) => a.grupo_primario === loteBatch) : []), [animais, loteBatch]);

  useEffect(() => {
    setSelBatch(new Set(animaisDoLoteBatch.map((a) => a.numero)));
  }, [loteBatch]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleBatch(numero: string) {
    setSelBatch((p) => { const s = new Set(p); s.has(numero) ? s.delete(numero) : s.add(numero); return s; });
  }
  function toggleTodosBatch() {
    setSelBatch((p) => (p.size === animaisDoLoteBatch.length && animaisDoLoteBatch.length ? new Set() : new Set(animaisDoLoteBatch.map((a) => a.numero))));
  }
  function campoBatch(numero: string) {
    return dadosBatch[numero] || { criaNumero: "", criaSexo: "", criaBaixada: false, retencaoPlacenta: false };
  }
  function setCampoBatch(numero: string, patch: Partial<{ criaNumero: string; criaSexo: string; criaBaixada: boolean; retencaoPlacenta: boolean }>) {
    setDadosBatch((p) => ({ ...p, [numero]: { ...campoBatch(numero), ...patch } }));
  }

  async function salvarLote() {
    setErroBatch(null); setSucessoBatch(null);
    const alvo = Array.from(selBatch);
    if (!alvo.length) { setErroBatch("Selecione ao menos uma matriz do lote."); return; }
    if (!dataParto) { setErroBatch("Informe a data do parto."); return; }
    setSalvandoBatch(true);
    let partosOk = 0;
    const criasOk: string[] = [];
    const falhas: string[] = [];
    for (const numero of alvo) {
      const d = campoBatch(numero);
      try {
        const crias = d.criaNumero ? [{ numero: d.criaNumero, sexo: d.criaSexo === "Macho" ? "M" : "F", nasceu_viva: !d.criaBaixada }] : [];
        const r = await criarParto({
          numero_matriz: numero, data_parto: dataParto, tipo_parto: tipoParto || undefined,
          crias, retencao_placenta: d.retencaoPlacenta, gemelar: false,
        });
        partosOk += 1;
        for (const c of r.crias_criadas as string[]) {
          criasOk.push(c);
          await alocarSemConfirmar(c, d.criaSexo === "Macho" ? "Bezerro" : "Bezerra", { data_nasc: dataParto }, "Nascimento", falhas);
        }
      } catch (e: any) {
        falhas.push(`${numero}: ${e.message || "erro ao registrar parto"}`);
      }
    }
    setSucessoBatch(
      `${partosOk} de ${alvo.length} parto(s) registrado(s)${criasOk.length ? `; cria(s) cadastrada(s): ${criasOk.join(", ")}` : ""}.` +
      `${falhas.length ? ` Atenção: ${falhas.join("; ")}.` : ""} A mudança de lote das mães não é automática aqui — use Rebanho > Movimentar animais, se precisar.`
    );
    if (partosOk) { setSelBatch(new Set()); setDadosBatch({}); setLoteBatch(""); }
    setSalvandoBatch(false);
  }

  // Todo parto pergunta se a mãe muda para o lote 3 — independentemente de
  // critério, ao contrário da sugestão genérica (que só age quando o animal
  // ainda não tem lote). Confirmando, move; não confirmando, ela permanece no
  // lote em que já estava.
  async function confirmarMudancaLote3(numero: string, falhas: string[]) {
    try {
      const lotes = await fetchLotes();
      const lote3 = (lotes as any[]).find((l) => l.codigo === "03");
      if (!lote3) return null;
      if (window.confirm(`Confirmar mudança de lote da vaca ${numero} para o lote 3 — ${lote3.nome}?`)) {
        await criarMovimentacao({ data_movimento: dataParto, motivo: "Parto", lote_destino_codigo: lote3.codigo, animais: [numero] });
        return lote3.rotulo as string;
      }
    } catch (e: any) {
      falhas.push(`mudança de lote da vaca ${numero} não pôde ser feita${e?.message ? `: ${e.message}` : ""}`);
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
        gemelar_sexo: gemelar ? (gemelarSexo || undefined) : undefined,
      });
      // Efeitos colaterais do parto (alocação de lote e colostragem) são
      // complementares: não bloqueiam o parto já salvo, mas as falhas são
      // coletadas para avisar o usuário no fim, em vez de sumirem em silêncio.
      const falhasEfeito: string[] = [];
      const alocacoes: string[] = [];
      const rotuloMae = await confirmarMudancaLote3(matriz, falhasEfeito);
      if (rotuloMae) alocacoes.push(`${matriz} → ${rotuloMae}`);
      for (const c of r.crias_criadas as string[]) {
        const sexoCria = c === cria2Numero ? cria2Sexo : criaSexo;
        const rotulo = await alocarSemConfirmar(c, sexoCria === "Macho" ? "Bezerro" : "Bezerra", { data_nasc: dataParto }, "Nascimento", falhasEfeito);
        if (rotulo) alocacoes.push(`${c} → ${rotulo}`);
      }
      // Colostragem/IgG acima descrevem só a 1ª cria (o formulário tem um único
      // bloco de colostro mesmo em parto gemelar) — grava se a cria foi criada
      // e algum dado foi informado.
      const criaRegistrada = r.crias_criadas.includes(criaNumero);
      if (criaRegistrada && (tomouColostro || litros || brix || soro || proteinaSerica || horaParto || horaColostro || pesoNascer || apenasColostroPo)) {
        try {
          await registrarColostragem({
            numero_animal: criaNumero,
            tomou_colostro: tomouColostro ? tomouColostro === "Sim" : undefined,
            litros_colostro: litrosN || undefined,
            brix_colostro: brixN ?? undefined,
            data_colostro: brix ? dataParto : undefined,
            hora_parto: horaParto || undefined,
            hora_colostro: horaColostro || undefined,
            peso_nascer_kg: pesoNascer ? Number(pesoNascer) : undefined,
            brix_soro: soroN ?? undefined,
            proteina_serica: proteinaSerica ? Number(proteinaSerica) : undefined,
            apenas_colostro_po: apenasColostroPo || undefined,
            data_teste_sangue: soro ? dataParto : undefined,
          });
        } catch (e: any) {
          falhasEfeito.push(`a colostragem não pôde ser gravada${e?.message ? `: ${e.message}` : ""}`);
        }
      }
      setSucesso(`Parto registrado (ordem ${r.ordem_parto}).${r.crias_criadas.length ? ` Cria(s) cadastrada(s): ${r.crias_criadas.join(", ")}.` : ""}${alocacoes.length ? ` Alocação: ${alocacoes.join("; ")}.` : ""}${falhasEfeito.length ? ` Atenção: ${falhasEfeito.join("; ")}.` : ""}`);
      setMatriz(""); setTipoParto(""); setGemelar(false); setGemelarSexo("");
      setCriaNumero(""); setCriaSexo(""); setCriaBaixada(false);
      setCria2Numero(""); setCria2Sexo(""); setCria2Baixada(false);
      setRetencaoPlacenta(false);
      setTomou(""); setLitros(""); setBrix(""); setSoro(""); setProteinaSerica("");
      setHoraParto(""); setHoraColostro(""); setPesoNascer(""); setApenasColostroPo(false);
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

      <div className="mb-3">
        <TabBar<"animal" | "lote">
          abas={[
            { id: "animal", label: "Uma matriz", title: "Lançar o parto de uma matriz, com cria, colostragem e IgG" },
            { id: "lote", label: "Várias matrizes (lote)", title: "Selecionar um lote e lançar partos simples de várias matrizes de uma vez" },
          ]}
          ativa={modo}
          onChange={setModo}
        />
      </div>

      {modo === "lote" ? (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Campo label="Lote">
              <select style={inputStyle} value={loteBatch} onChange={(e) => setLoteBatch(e.target.value)}>
                <option value="">Selecione…</option>
                {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
              </select>
            </Campo>
            <Campo label="Data do parto (todas)"><input type="date" style={inputStyle} value={dataParto} onChange={(e) => setDataParto(e.target.value)} /></Campo>
            <Campo label="Tipo de parto (todas)">
              <select style={inputStyle} value={tipoParto} onChange={(e) => setTipoParto(e.target.value)}>
                <option value="">Selecione…</option><option>Normal</option>
                <option>Distócico moderado</option><option>Distócico severo</option>
                <option>Cesariana</option>
              </select>
            </Campo>
          </div>

          {loteBatch ? (
            <div className="card mt-3" style={{ padding: 0 }}>
              <div className="card-header m-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
                <span>Matrizes do lote {loteBatch} ({animaisDoLoteBatch.length})</span>
                <button type="button" className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={toggleTodosBatch} disabled={!animaisDoLoteBatch.length}>
                  {selBatch.size === animaisDoLoteBatch.length && animaisDoLoteBatch.length ? "Limpar seleção" : "Selecionar todos"}
                </button>
              </div>
              <div className="overflow-x-auto" style={{ maxHeight: "460px" }}>
                <table className="fazenda-table" style={{ margin: 0 }}>
                  <thead><tr><th></th><th>Nº</th><th>Nº da cria (vazio = baixa)</th><th>Sexo da cria</th><th>Cria baixada?</th><th>Retenção de placenta</th></tr></thead>
                  <tbody>
                    {animaisDoLoteBatch.map((a) => {
                      const d = campoBatch(a.numero);
                      const marcada = selBatch.has(a.numero);
                      return (
                        <tr key={a.numero} style={{ opacity: marcada ? 1 : 0.45 }}>
                          <td><input type="checkbox" checked={marcada} onChange={() => toggleBatch(a.numero)} /></td>
                          <td style={{ fontWeight: 700 }}>{a.numero}</td>
                          <td><input style={inputStyle} disabled={!marcada} value={d.criaNumero} onChange={(e) => setCampoBatch(a.numero, { criaNumero: e.target.value })} placeholder="ex.: 483" /></td>
                          <td>
                            <select style={inputStyle} disabled={!marcada} value={d.criaSexo} onChange={(e) => setCampoBatch(a.numero, { criaSexo: e.target.value })}>
                              <option value="">—</option><option>Fêmea</option><option>Macho</option>
                            </select>
                          </td>
                          <td>
                            <select style={inputStyle} disabled={!marcada} value={d.criaBaixada ? "Sim" : "Não"} onChange={(e) => setCampoBatch(a.numero, { criaBaixada: e.target.value === "Sim" })}>
                              <option>Não</option><option>Sim</option>
                            </select>
                          </td>
                          <td style={{ textAlign: "center" }}>
                            <input type="checkbox" disabled={!marcada} checked={d.retencaoPlacenta} onChange={(e) => setCampoBatch(a.numero, { retencaoPlacenta: e.target.checked })} />
                          </td>
                        </tr>
                      );
                    })}
                    {!animaisDoLoteBatch.length && <tr><td colSpan={6} style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>Nenhum animal neste lote.</td></tr>}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p style={nota}>Selecione um lote para ver a lista de matrizes e lançar vários partos de uma vez.</p>
          )}

          <p style={nota}>
            Modo simplificado: grava matriz, data, tipo de parto, cria e retenção de placenta de cada uma. Para
            parto gemelar, colostragem e IgG, use "Uma matriz". A mudança de lote da mãe (lote 3) precisa ser feita
            depois, manualmente, em Rebanho {"›"} Movimentar animais.
          </p>

          {erroBatch && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erroBatch}</p>}
          {sucessoBatch && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucessoBatch}</p>}
          <div className="flex items-center gap-3 mt-4">
            <button className="btn-primary" onClick={salvarLote} disabled={salvandoBatch}>{salvandoBatch ? "Salvando…" : "Salvar todos"}</button>
          </div>
        </>
      ) : (
        <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Matriz (nº)"><SelectAnimal animais={animais} value={matriz} onChange={setMatriz} placeholder="Selecione a matriz que pariu…" /></Campo>
        <Campo label="Data do parto"><input type="date" style={inputStyle} value={dataParto} onChange={(e) => setDataParto(e.target.value)} /></Campo>
        <Campo label="Tipo de parto">
          <select style={inputStyle} value={tipoParto} onChange={(e) => setTipoParto(e.target.value)}>
            <option value="">Selecione…</option><option>Normal</option>
            <option>Distócico moderado</option><option>Distócico severo</option>
            <option>Cesariana</option>
          </select>
        </Campo>
        <Campo label="Retenção de placenta"><label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}><input type="checkbox" checked={retencaoPlacenta} onChange={(e) => setRetencaoPlacenta(e.target.checked)} /> Sim (gera item na Agenda)</label></Campo>
        <Campo label="Parto gemelar (2 crias)"><label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}><input type="checkbox" checked={gemelar} onChange={(e) => setGemelar(e.target.checked)} /> Sim</label></Campo>
        {gemelar && (
          <Campo label="Sexos do parto gemelar">
            <select style={inputStyle} value={gemelarSexo} onChange={(e) => setGemelarSexo(e.target.value)}>
              <option value="">Selecione… (ou deriva dos sexos)</option>
              <option value="FF">FF — duas fêmeas</option>
              <option value="FM">FM — fêmea e macho (fêmea pode ser freemartin)</option>
              <option value="MM">MM — dois machos</option>
            </select>
          </Campo>
        )}
      </div>

      <div className="card mt-3" style={{ background: "var(--surface-2)" }}>
        <div className="card-header mb-2 flex items-center gap-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
          <Baby size={14} /> Cadastro da cria (prole)
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <Campo label="Número da cria (vazio = baixa automática)"><input style={inputStyle} value={criaNumero} onChange={(e) => setCriaNumero(e.target.value)} placeholder="ex.: 483 — em branco, natimorto/baixa" /></Campo>
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
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-2">
            <Campo label="Hora do parto"><input type="time" style={inputStyle} value={horaParto} onChange={(e) => setHoraParto(e.target.value)} /></Campo>
            <Campo label="Hora do colostro"><input type="time" style={inputStyle} value={horaColostro} onChange={(e) => setHoraColostro(e.target.value)} /></Campo>
            <Campo label="Peso ao nascer (kg)"><input type="number" step="0.1" inputMode="decimal" style={inputStyle} value={pesoNascer} onChange={(e) => setPesoNascer(e.target.value)} placeholder="ex.: 38" /></Campo>
          </div>
          {horaParto && horaColostro && (
            <p style={{ fontSize: "0.76rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
              Intervalo parto→colostro: <strong style={{ color: intervaloColostroHoras != null && intervaloColostroHoras <= 6 ? "var(--green-light)" : "var(--amber)" }}>
                {intervaloColostroHoras != null ? `${intervaloColostroHoras.toFixed(1)} h` : "—"}</strong> (ideal ≤ 6 h; quanto antes, melhor a absorção de IgG).
            </p>
          )}
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
            Colher entre <strong>24h e 48h</strong> após o nascimento. Pode informar <strong>Brix sérico</strong> OU
            <strong> proteína sérica</strong>. Classificação: excelente (Brix &gt;9,4% · prot. &gt;6,2 g/dL) ·
            boa (8,9–9,3% · 5,8–6,1) · aceitável (8,1–8,8% · 5,1–5,7) · ruim (abaixo disso).
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
            <Campo label="Brix do soro (%)">
              <select style={inputStyle} value={soro} onChange={(e) => setSoro(e.target.value)}>
                <option value="" disabled>Selecione…</option>
                {OPCOES_SORO.map((v) => <option key={v} value={v}>{v.replace(".", ",")}%</option>)}
              </select>
            </Campo>
            <Campo label="Proteína sérica (g/dL)">
              <input type="number" step="0.1" inputMode="decimal" style={inputStyle} value={proteinaSerica} onChange={(e) => setProteinaSerica(e.target.value)} placeholder="ex.: 6,0" />
            </Campo>
          </div>
          {(clsSoro || proteinaSerica) && (
            <p style={{ fontSize: "0.82rem", marginTop: "0.4rem" }}>
              Eficiência de colostragem: <strong style={{ color: classeColostragemUI(soroN, proteinaSerica ? Number(proteinaSerica) : null).cor }}>
                {classeColostragemUI(soroN, proteinaSerica ? Number(proteinaSerica) : null).txt}</strong>
            </p>
          )}
          <label className="flex items-center gap-2" style={{ fontSize: "0.8rem", marginTop: "0.4rem" }}>
            <input type="checkbox" checked={apenasColostroPo} onChange={(e) => setApenasColostroPo(e.target.checked)} /> Bezerra recebeu somente colostro em pó (sem colostro materno)
          </label>
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
      )}
    </>
  );
}

// Upload de planilha (Excel/.xlsx ou CSV) — usado tanto em Controle leiteiro
// (por animal ou por lote, um botão de modelo cada) quanto em Qualidade do
// leite (um modelo só). O parser do backend identifica o formato sozinho.
function FormControle({ animais, lotesLact }: { animais: AnimalRow[]; lotesLact: string[] }) {
  const [modo, setModo] = useState<"vaca" | "lote" | "planilha">("vaca");
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
  // Controle leiteiro é só de quem está em lactação: em lote de lactação
  // (01/02/03) ou com DEL em curso (> 0).
  const animaisLact = useMemo(
    () => animais.filter((a) => (a.grupo_primario && lotesLact.includes(a.grupo_primario)) || ((a.del_dias ?? 0) > 0)),
    [animais, lotesLact],
  );
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
            <option value="planilha">Importar de planilha</option>
          </select>
        </Campo>
        {modo !== "planilha" && (
          <Campo label="Nº de ordenhas">
            <select style={inputStyle} value={nOrd} onChange={(e) => setNOrd(Number(e.target.value))}>
              <option value={2}>2 ordenhas</option>
              <option value={3}>3 ordenhas</option>
            </select>
          </Campo>
        )}
        {modo === "vaca" && (
          <>
            <Campo label="Vaca (só em lactação)"><SelectAnimal animais={animaisLact} value={vaca} onChange={setVaca} placeholder="Selecione a vaca em lactação…" /></Campo>
            <Campo label="DEL (automático)"><input style={{ ...inputStyle, opacity: 0.8 }} value={del != null ? `${del} dias` : "—"} readOnly /></Campo>
          </>
        )}
        {modo === "lote" && (
          <Campo label="Lote">
            <select style={inputStyle} value={lote} onChange={(e) => setLote(e.target.value)}>
              <option value="">Selecione…</option>
              {lotesLact.map((l) => <option key={l} value={l}>{l}</option>)}
            </select>
          </Campo>
        )}
        {modo !== "planilha" && (
          <Campo label="Data do controle"><input type="date" style={inputStyle} value={dataControle} onChange={(e) => setDataControle(e.target.value)} /></Campo>
        )}
      </div>

      {modo === "planilha" && (
        <UploadPlanilha
          modelos={[
            { label: "Modelo por animal", baixar: () => baixarModeloControleLeiteiro("animal") },
            { label: "Modelo por lote", baixar: () => baixarModeloControleLeiteiro("lote") },
          ]}
          onImportar={importarControleLeiteiroPlanilha}
        />
      )}

      {modo !== "planilha" && (modo === "vaca" ? (
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
      ))}

      {modo !== "planilha" && erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {modo !== "planilha" && sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

      {modo !== "planilha" && (
        <div className="flex items-center gap-3 mt-4">
          <button className="btn-primary" onClick={salvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        </div>
      )}
    </>
  );
}

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
  // "Já foi aplicado?" — quando Não (ou data futura), nada baixa do estoque:
  // fica programado na Agenda até você dar baixa.
  const [aplicado, setAplicado] = useState(true);
  // Vindo da Agenda ("Dar baixa" de um evento sanitário): ao salvar, marca o
  // evento como realizado para sumir da Agenda.
  const [eventoAgenda, setEventoAgenda] = useState<string | null>(null);
  // "Qual frasco/apresentação você está usando?" — por item, as apresentações
  // (frascos/marcas) do mesmo princípio ativo que existem no estoque. Só pergunta
  // quando há mais de uma.
  const [frascosPorItem, setFrascosPorItem] = useState<Record<number, ApresentacaoFarmacia[]>>({});
  // Lançamento por doença ou princípio ativo: abre só os medicamentos que
  // correspondem ao critério (via Farmácia). Listas de opções e produtos
  // filtrados por item.
  const [principiosNomes, setPrincipiosNomes] = useState<string[]>([]);
  const [doencasNomes, setDoencasNomes] = useState<string[]>([]);
  const [opcoesPorItem, setOpcoesPorItem] = useState<Record<number, string[]>>({});
  // Catálogo geral de medicamento/hormônio/vacina (finalidade "Medicamento",
  // com saldo em estoque) para o modo "Medicamento (todos)" — ração/material/
  // equipamento não aparecem mais aqui. "Incluir itens sem estoque" resolve o
  // problema na hora (mesmo padrão do "incluir touros sem estoque").
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [catalogoMedicamentos, setCatalogoMedicamentos] = useState<string[]>([]);
  useEffect(() => {
    fetchMedicamentos({ incluir_sem_estoque: incluirSemEstoque }).then((m: any[]) => setCatalogoMedicamentos(m.map((x) => x.nome))).catch(() => {});
  }, [incluirSemEstoque]);
  useEffect(() => {
    fetchPrincipiosAtivos().then((d: any[]) => setPrincipiosNomes(d.map((p) => p.nome))).catch(() => {});
    fetchDoencas().then((d: any[]) => setDoencasNomes(d.map((x) => x.nome))).catch(() => {});
  }, []);

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
        ...itemSanidadeVazio(),
        produto, via: qs.get("via") || "", quantidade: qs.get("dose") || "", unidade: qs.get("unidade") || "",
      }]);
    }
    setEventoAgenda(qs.get("evento_agenda"));
  }, []);

  const toggleLote = (l: string) => setLotesSel((p) => { const s = new Set(p); s.has(l) ? s.delete(l) : s.add(l); return s; });
  // Lista de produtos vem do relatório de sanidade (medicamentos já aplicados),
  // complementada pelo catálogo geral de medicamento/hormônio/vacina em estoque.
  const listaProdutos = Array.from(new Set([...produtos, ...catalogoMedicamentos])).sort();

  const atualizarItem = (idx: number, patch: Partial<ItemSanidade>) => setItens((p) => {
    const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n;
  });
  const escolherProduto = (idx: number, produto: string) => {
    const compativeis = unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade);
    atualizarItem(idx, { produto, unidade: compativeis[0] || "", estoque_id: null });
    // "Qual frasco?": busca as apresentações do mesmo princípio ativo. Mais de
    // uma → o usuário escolhe; só uma → já fixa nela.
    fetchApresentacoesFarmacia({ produto }).then((fr) => {
      setFrascosPorItem((p) => ({ ...p, [idx]: fr }));
      if (fr.length === 1) atualizarItem(idx, { estoque_id: fr[0].estoque_id });
    }).catch(() => setFrascosPorItem((p) => ({ ...p, [idx]: [] })));
  };
  const acrescentarItem = () => setItens((p) => [...p, itemSanidadeVazio()]);
  const removerItem = (idx: number) => setItens((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  // Muda o modo de escolha do medicamento (todos / por princípio ativo / por doença).
  const escolherDefinirPor = (idx: number, valor: ItemSanidade["definirPor"]) => {
    atualizarItem(idx, { definirPor: valor, criterio: "", produto: "", unidade: "", estoque_id: null });
    setOpcoesPorItem((o) => ({ ...o, [idx]: [] }));
  };
  const escolherCriterio = (idx: number, criterio: string) => {
    atualizarItem(idx, { criterio, produto: "", unidade: "", estoque_id: null });
    if (!criterio) { setOpcoesPorItem((o) => ({ ...o, [idx]: [] })); return; }
    const def = itens[idx].definirPor;
    const filtro = def === "principio_ativo" ? { principio_ativo: criterio } : { doenca: criterio };
    fetchMedicamentos({ ...filtro, incluir_sem_estoque: incluirSemEstoque })
      .then((m: any[]) => setOpcoesPorItem((o) => ({ ...o, [idx]: m.map((x) => x.nome) })))
      .catch(() => setOpcoesPorItem((o) => ({ ...o, [idx]: [] })));
  };

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
      const hojeStr = new Date().toISOString().slice(0, 10);
      const aplicadoEfetivo = aplicado && dataAplicacao <= hojeStr;
      const r = await criarAplicacaoSanidade({
        data_aplicacao: dataAplicacao, animais: animaisAlvo, responsavel: responsavel || undefined, observacao: observacao || undefined,
        itens: itensValidos.map((i) => ({ produto: i.produto, via: i.via || undefined, quantidade: Number(i.quantidade), unidade: i.unidade, estoque_id: i.estoque_id ?? undefined })),
        aplicado: aplicadoEfetivo,
      });
      if (aplicadoEfetivo && eventoAgenda) { await marcarEventoRealizado(eventoAgenda).catch(() => {}); setEventoAgenda(null); }
      setSucesso(r.programado
        ? `Aplicação PROGRAMADA na Agenda (não baixou estoque). Dê baixa quando aplicar.`
        : `${r.criados} aplicação(ões) lançada(s) com sucesso.${r.avisos?.length ? " " + r.avisos.join(" ") : ""}${eventoAgenda ? " Baixado da Agenda." : ""}`);
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
        <Campo label="Já foi aplicado?" full>
          {dataAplicacao > new Date().toISOString().slice(0, 10) ? (
            <p style={{ fontSize: "0.8rem", color: "var(--amber)" }}>Data futura — será <strong>programado na Agenda</strong> (não baixa estoque até você dar baixa).</p>
          ) : (
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={aplicado} onChange={() => setAplicado(true)} /> Sim — aplicar e baixar o estoque agora</label>
              <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={!aplicado} onChange={() => setAplicado(false)} /> Não — só programar na Agenda</label>
            </div>
          )}
        </Campo>
      </div>

      <Secao>Produtos aplicados</Secao>
      <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.78rem", color: "var(--text-muted)", cursor: "pointer" }}>
        <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => setIncluirSemEstoque(e.target.checked)} />
        Incluir itens sem estoque
      </label>
      <div className="space-y-3">
        {itens.map((item, idx) => {
          const estoqueItem = estoque.find((e) => e.nome === item.produto);
          const compativeis = unidadesCompativeis(estoqueItem?.unidade);
          return (
            <div key={idx} style={{ border: "1px solid var(--border)", borderRadius: "8px", padding: "0.75rem", position: "relative" }}>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3" style={{ marginBottom: "0.6rem" }}>
                <Campo label="Definir medicamento por">
                  <select style={inputStyle} value={item.definirPor} onChange={(e) => escolherDefinirPor(idx, e.target.value as ItemSanidade["definirPor"])}>
                    <option value="medicamento">Medicamento (todos)</option>
                    <option value="principio_ativo">Princípio ativo</option>
                    <option value="doenca">Doença</option>
                  </select>
                </Campo>
                {item.definirPor !== "medicamento" && (
                  <Campo label={item.definirPor === "principio_ativo" ? "Princípio ativo" : "Doença"}>
                    <select style={inputStyle} value={item.criterio} onChange={(e) => escolherCriterio(idx, e.target.value)}>
                      <option value="">Selecione…</option>
                      {(item.definirPor === "principio_ativo" ? principiosNomes : doencasNomes).map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                  </Campo>
                )}
              </div>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Campo label={`Produto/medicamento ${idx + 1}`}>
                  <EstoquePicker
                    itens={(item.definirPor === "medicamento" ? listaProdutos : (opcoesPorItem[idx] || [])).map((nome) => estoque.find((e) => e.nome === nome) || { nome })}
                    value={item.produto} onChange={(nome) => escolherProduto(idx, nome)}
                    placeholder={item.definirPor !== "medicamento" && !item.criterio ? `Escolha ${item.definirPor === "principio_ativo" ? "o princípio ativo" : "a doença"} primeiro` : "Selecionar produto…"}
                  />
                  {item.definirPor !== "medicamento" && item.criterio && !(opcoesPorItem[idx] || []).length && (
                    <p style={{ fontSize: "0.68rem", color: "var(--amber)", marginTop: 2 }}>Nenhum medicamento com esse critério.</p>
                  )}
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
              {(frascosPorItem[idx]?.length ?? 0) > 1 && (
                <div style={{ marginTop: "0.6rem", background: "var(--surface-2)", border: "1px solid var(--dourado)", borderRadius: 8, padding: "0.55rem 0.7rem" }}>
                  <label style={{ fontSize: "0.76rem", fontWeight: 700, color: "var(--dourado-light)", display: "block", marginBottom: "0.3rem" }}>
                    Qual frasco/apresentação você está usando agora?
                  </label>
                  <select style={inputStyle} value={item.estoque_id ?? ""} onChange={(e) => atualizarItem(idx, { estoque_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">Selecione o frasco…</option>
                    {frascosPorItem[idx].map((f) => (
                      <option key={f.estoque_id} value={f.estoque_id}>
                        {f.nome}{f.marca ? ` · ${f.marca}` : ""} — saldo {f.saldo} {f.unidade || ""}{!f.estoque_inicializado ? " (sem estoque inicial)" : ""}
                      </option>
                    ))}
                  </select>
                </div>
              )}
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
  dosagem: string | null; unidade: string | null; frequencia_valor: number; frequencia_unidade: string;
  data_evento: string; proxima_ocorrencia: string; observacao: string | null; ativo: boolean;
};
// Separador usado para guardar mais de uma categoria-alvo no mesmo campo
// (texto único no banco — cada regra continua com um único categoria_alvo).
const SEP_CATEGORIAS = ", ";

const FREQUENCIA_UNIDADES = [
  { v: "dias", l: "dia(s)" }, { v: "meses", l: "mês(es)" }, { v: "anos", l: "ano(s)" },
];

function FormCalendarioSanitario({ estoque }: { estoque: EstoqueItem[] }) {
  const [eventos, setEventos] = useState<OpcaoNomeAtivo[]>([]);
  const [doencas, setDoencas] = useState<OpcaoNomeAtivo[]>([]);
  const [principios, setPrincipios] = useState<OpcaoNomeAtivo[]>([]);
  // Categorias de vida (Configurações > Cadastro > Categorias) — a lista real
  // usada para "período de vida", nada a ver com CATEGORIAS_ANIMAIS (critérios
  // de lançamento em massa por status reprodutivo, usado mais abaixo neste arquivo).
  const [categoriasVida, setCategoriasVida] = useState<string[]>([]);
  const [regras, setRegras] = useState<RegraCalendario[] | null>(null);

  const [editando, setEditando] = useState<number | null>(null);
  const [eventoId, setEventoId] = useState("");
  const [categoriaAlvoSel, setCategoriaAlvoSel] = useState<string[]>([]);
  const [doencaId, setDoencaId] = useState("");
  const [produto, setProduto] = useState("");
  const [principioId, setPrincipioId] = useState("");
  const [dosagem, setDosagem] = useState("");
  const [unidade, setUnidade] = useState("");
  const [veterinario, setVeterinario] = useState("");
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [dataEvento, setDataEvento] = useState("");
  const [observacao, setObservacao] = useState("");
  const [realizado, setRealizado] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  // Frequência periódica (regra recorrente do calendário) OU por evento de
  // vida (desmama, aptidão, secagem…) — nesse 2º modo não cria regra nenhuma:
  // configura o EVENTO SANITÁRIO selecionado para agendar por animal (mesmo
  // mecanismo que já gera a Agenda por evento — ver eventos_sanitarios.py).
  const [modoFreq, setModoFreq] = useState<"periodica" | "evento_vida">("periodica");
  const [gatilhosVida, setGatilhosVida] = useState<{ gatilho: string; rotulo: string }[]>([]);
  const [gatilho, setGatilho] = useState("nascimento");
  const [gatilhoLote, setGatilhoLote] = useState("");
  const [gatilhoIdadeMeses, setGatilhoIdadeMeses] = useState("");
  const [offsetDias, setOffsetDias] = useState("0");

  useEffect(() => { fetchEventosVidaVocabulario().then(setGatilhosVida).catch(() => {}); }, []);

  const eventoSel = eventos.find((e) => String(e.id) === eventoId) as any;
  const ehExame = eventoSel?.categoria_preventiva === "exame";

  // Ao escolher um evento já cadastrado como "por evento" (tipo_agendamento
  // == evento), o modo já vem pré-selecionado e os campos de gatilho preenchidos.
  useEffect(() => {
    if (!eventoSel) return;
    if (eventoSel.tipo_agendamento === "evento" && eventoSel.gatilho) {
      setModoFreq("evento_vida");
      setGatilho(eventoSel.gatilho);
      setGatilhoLote(eventoSel.gatilho_lote || "");
      setGatilhoIdadeMeses(eventoSel.gatilho_idade_meses ? String(eventoSel.gatilho_idade_meses) : "");
      setOffsetDias(eventoSel.offset_dias != null ? String(eventoSel.offset_dias) : "0");
    } else {
      setModoFreq("periodica");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventoId]);

  const carregarRegras = () => fetchCalendarioSanitario().then(setRegras).catch((e) => setErro(e.message));
  const carregarEventos = () => fetchEventosSanitarios().then((d) => setEventos(d.filter((e: OpcaoNomeAtivo) => e.ativo))).catch(() => {});
  useEffect(() => {
    carregarEventos();
    fetchDoencas().then((d) => setDoencas(d.filter((e: OpcaoNomeAtivo) => e.ativo))).catch(() => {});
    fetchPrincipiosAtivos().then((d) => setPrincipios(d.filter((e: OpcaoNomeAtivo) => e.ativo !== false))).catch(() => {});
    fetchCategoriasManejo().then((d) => setCategoriasVida(d.filter((c) => c.ativo).map((c) => c.nome))).catch(() => {});
    carregarRegras();
  }, []);
  const [abrirNovoEvento, setAbrirNovoEvento] = useState(false);

  const limpar = () => {
    setEditando(null); setEventoId(""); setCategoriaAlvoSel([]); setDoencaId(""); setProduto("");
    setPrincipioId(""); setDosagem(""); setUnidade(""); setVeterinario(""); setFreqValor("1"); setFreqUnidade("meses");
    setDataEvento(""); setObservacao(""); setRealizado(false);
    setModoFreq("periodica"); setGatilho("nascimento"); setGatilhoLote(""); setGatilhoIdadeMeses(""); setOffsetDias("0");
  };

  const abrirEdicao = (r: RegraCalendario) => {
    setEditando(r.id); setEventoId(String(r.evento_sanitario_id));
    setCategoriaAlvoSel(r.categoria_alvo ? r.categoria_alvo.split(SEP_CATEGORIAS).map((c) => c.trim()).filter(Boolean) : []);
    setDoencaId(r.doenca_id ? String(r.doenca_id) : ""); setProduto(r.produto || "");
    setPrincipioId(r.principio_ativo_id ? String(r.principio_ativo_id) : ""); setDosagem(r.dosagem || "");
    setUnidade(r.unidade || "");
    setVeterinario((r as any).veterinario || "");
    setFreqValor(String(r.frequencia_valor)); setFreqUnidade(r.frequencia_unidade);
    setDataEvento(r.data_evento); setObservacao(r.observacao || ""); setRealizado(false);
  };

  const excluir = async (r: RegraCalendario) => {
    if (!window.confirm(`Excluir a regra do calendário "${r.evento_sanitario_nome}" de ${formatDate(r.data_evento)}?`)) return;
    try { await excluirCalendarioSanitario(r.id); carregarRegras(); }
    catch (e: any) { setErro(e.message); }
  };

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!eventoId) { setErro("Selecione o evento sanitário."); return; }
    if (modoFreq === "periodica" && (!dataEvento || !freqValor)) { setErro("Selecione a frequência e a data do evento."); return; }
    if (modoFreq === "evento_vida" && gatilho === "entrada_lote" && !gatilhoLote.trim()) { setErro("Informe o lote do gatilho (entrada no lote)."); return; }
    if (modoFreq === "evento_vida" && gatilho === "novilha_apta" && !gatilhoIdadeMeses) { setErro("Informe a idade-alvo em meses (aptidão de novilha)."); return; }
    setSalvando(true);
    try {
      if (modoFreq === "evento_vida") {
        // Não cria regra recorrente — configura o EVENTO SANITÁRIO selecionado
        // para agendar por evento de vida (por animal), preservando os demais
        // campos já cadastrados nele (produto padrão, dose, doença...).
        await atualizarEventoSanitario(Number(eventoId), {
          ...eventoSel, tipo_agendamento: "evento", gatilho,
          gatilho_lote: gatilho === "entrada_lote" ? gatilhoLote.trim() : null,
          gatilho_idade_meses: gatilho === "novilha_apta" ? Number(gatilhoIdadeMeses) : null,
          offset_dias: offsetDias ? Number(offsetDias) : 0,
        });
        setSucesso("Evento sanitário configurado para agendar por evento de vida.");
        limpar();
        carregarEventos();
        setSalvando(false);
        return;
      }
      const dados = {
        evento_sanitario_id: Number(eventoId), categoria_alvo: categoriaAlvoSel.length ? categoriaAlvoSel.join(SEP_CATEGORIAS) : undefined,
        doenca_id: doencaId ? Number(doencaId) : undefined,
        produto: ehExame ? undefined : (produto || undefined),
        principio_ativo_id: ehExame ? undefined : (principioId ? Number(principioId) : undefined),
        dosagem: ehExame ? undefined : (dosagem || undefined),
        unidade: ehExame ? undefined : (unidade || undefined),
        veterinario: veterinario || undefined,
        frequencia_valor: Number(freqValor), frequencia_unidade: freqUnidade, data_evento: dataEvento,
        observacao: observacao || undefined, realizado,
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
          <div className="flex items-center gap-2">
            <select style={inputStyle} value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
              <option value="">Selecione…</option>{eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}</option>)}
            </select>
            <button type="button" className="btn-ghost" title="Cadastrar novo evento sanitário" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoEvento(true)}>
              <Plus size={13} /> Novo
            </button>
          </div>
          {abrirNovoEvento && (
            <Modal title="Novo evento sanitário" onClose={() => { setAbrirNovoEvento(false); carregarEventos(); }} width="900px">
              <CadastroEventosSanitarios />
            </Modal>
          )}
        </Campo>
        <Campo label="Categoria(s) alvo (período de vida)">
          <MultiFiltro
            label="Categorias" opcoes={Array.from(new Set([...categoriasVida, ...categoriaAlvoSel]))}
            selecionados={categoriaAlvoSel} onChange={setCategoriaAlvoSel}
            permitirNovo placeholderNovo="+ outra categoria…"
            onAdicionarNovo={(v) => setCategoriaAlvoSel((p) => Array.from(new Set([...p, v])))}
          />
        </Campo>
        <Campo label="Doença combatida">
          <select style={inputStyle} value={doencaId} onChange={(e) => setDoencaId(e.target.value)}>
            <option value="">—</option>{doencas.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
          </select>
        </Campo>
        {ehExame ? (
          <Campo label="Veterinário (exame)">
            <input style={inputStyle} value={veterinario} onChange={(e) => setVeterinario(e.target.value)} placeholder="ex.: Dr. Carlos" />
          </Campo>
        ) : (
          <>
            <Campo label="Princípio ativo">
              <select style={inputStyle} value={principioId} onChange={(e) => setPrincipioId(e.target.value)}>
                <option value="">—</option>{principios.map((p) => <option key={p.id} value={p.id}>{p.nome}</option>)}
              </select>
            </Campo>
            <Campo label="Produto (item de estoque)">
              <EstoquePicker itens={estoque} value={produto} onChange={setProduto} />
            </Campo>
            <Campo label="Dosagem recomendada">
              <input style={inputStyle} value={dosagem} onChange={(e) => setDosagem(e.target.value)} placeholder="ex.: 2 mL a 5 mL (conforme bula)" />
            </Campo>
            <Campo label="Unidade">
              <select style={inputStyle} value={unidade} onChange={(e) => setUnidade(e.target.value)}>
                <option value="">—</option>
                {unidadesCompativeis(estoque.find((e) => e.nome === produto)?.unidade).map((u) => <option key={u}>{u}</option>)}
              </select>
            </Campo>
          </>
        )}
        <Campo label="Repetir por" full>
          <div className="flex items-center gap-4" style={{ fontSize: "0.85rem" }}>
            <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
              <input type="radio" checked={modoFreq === "periodica"} onChange={() => setModoFreq("periodica")} /> Frequência periódica
            </label>
            <label className="flex items-center gap-2" style={{ cursor: "pointer" }}>
              <input type="radio" checked={modoFreq === "evento_vida"} onChange={() => setModoFreq("evento_vida")} /> Evento de vida do animal
            </label>
          </div>
        </Campo>
        {modoFreq === "periodica" ? (
          <>
            <Campo label="Frequência">
              <div className="flex items-center gap-2">
                <input type="number" min={1} style={inputStyle} value={freqValor} onChange={(e) => setFreqValor(e.target.value)} />
                <select style={inputStyle} value={freqUnidade} onChange={(e) => setFreqUnidade(e.target.value)}>
                  {FREQUENCIA_UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}
                </select>
              </div>
            </Campo>
            <Campo label="Data do evento (referência)"><input type="date" style={inputStyle} value={dataEvento} onChange={(e) => setDataEvento(e.target.value)} /></Campo>
          </>
        ) : (
          <>
            <Campo label="Evento de vida">
              <select style={inputStyle} value={gatilho} onChange={(e) => setGatilho(e.target.value)}>
                {gatilhosVida.map((g) => <option key={g.gatilho} value={g.gatilho}>{g.rotulo}</option>)}
              </select>
            </Campo>
            {gatilho === "entrada_lote" && (
              <Campo label="Lote do gatilho"><input style={inputStyle} value={gatilhoLote} onChange={(e) => setGatilhoLote(e.target.value)} placeholder="ex.: PRE_PARTO" /></Campo>
            )}
            {gatilho === "novilha_apta" && (
              <Campo label="Idade-alvo (meses)"><input type="number" min={1} style={inputStyle} value={gatilhoIdadeMeses} onChange={(e) => setGatilhoIdadeMeses(e.target.value)} placeholder="ex.: 13" /></Campo>
            )}
            <Campo label="Dias após o gatilho"><input type="number" style={inputStyle} value={offsetDias} onChange={(e) => setOffsetDias(e.target.value)} /></Campo>
            <div style={{ gridColumn: "1 / -1" }}>
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                Este modo não cria uma regra de frequência — ele configura o evento sanitário selecionado para entrar na Agenda
                automaticamente quando cada animal atingir esse evento de vida (por animal, não por rebanho todo).
              </p>
            </div>
          </>
        )}
        <Campo label="Observação" full><input style={inputStyle} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>

      {ehExame && (
        <p style={{ fontSize: "0.75rem", color: "var(--blue)", marginTop: "0.5rem" }}>
          Exame — sem baixa de estoque, só o agendamento. Use o botão "Lançar financeiro" na aba Sanidade &gt; Preventivo para registrar o custo do exame.
        </p>
      )}
      {modoFreq === "periodica" && (
        <label className="flex items-center gap-2 mt-2" style={{ fontSize: "0.8rem" }}>
          <input type="checkbox" checked={realizado} onChange={(e) => setRealizado(e.target.checked)} /> Já foi realizado (não entra como pendência na Agenda)
        </label>
      )}

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
                    <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem" }} onClick={() => abrirEdicao(r)}>Editar</button>
                      <button className="btn-ghost" style={{ fontSize: "0.72rem", color: "var(--red)" }} onClick={() => excluir(r)}>Excluir</button>
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

type ProtocoloEtapaLocal = { id?: number; dia: number; criterio_tipo?: string; produto: string; dosagem: number; unidade: string; via?: string | null };
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

// ─────────────────────── Preventivo — aplicação (vacina/exame) ───────────────────────
type EventoPrev = {
  id: number; nome: string; categoria_preventiva: string | null; doenca_nome: string | null;
  produto_padrao: string | null; dose_padrao: number | null; unidade_padrao: string | null;
  exame_definicao_id: number | null;
};
const LABEL_CAT_PREV: Record<string, string> = { vacina: "Vacina", exame: "Exame", tratamento: "Tratamento", outros: "Outros" };
type ExameDef = { id: number; nome: string; tipo_resultado: "diagnostico" | "numerico"; faixa_min: number | null; faixa_max: number | null; acao_abaixo: string | null; acao_dentro: string | null; acao_acima: string | null };
const LABEL_RESULTADO_EXAME: Record<string, string> = { positivo: "Positivo", negativo: "Negativo", indefinido: "Indefinido" };

function FormPreventivoAplicacao({ animais, lotes, estoque }: { animais: AnimalRow[]; lotes: string[]; estoque: EstoqueItem[] }) {
  const [eventos, setEventos] = useState<EventoPrev[]>([]);
  const [eventoId, setEventoId] = useState("");
  const [dataEvento, setDataEvento] = useState("");
  const [freqValor, setFreqValor] = useState("1");
  const [freqUnidade, setFreqUnidade] = useState("meses");
  const [veterinario, setVeterinario] = useState("");
  const [vinculo, setVinculo] = useState<"animal" | "lote" | "categoria">("animal");
  const [animaisSel, setAnimaisSel] = useState<Set<string>>(new Set());

  // Lote: pode selecionar mais de um — janela suspensa mostra só os animais
  // dos lotes escolhidos, com "selecionar todos" (mesmo padrão da Inseminação).
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const codigosLotesTodos = useMemo(
    () => Array.from(new Set(animais.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [animais]
  );
  const animaisDosLotesSel = useMemo(() => {
    const cods = new Set(lotesSelecionados);
    return animais.filter((a) => { const c = codigoGrupo(a.grupo_primario); return c && cods.has(c); });
  }, [animais, lotesSelecionados]);
  const [selDosLotes, setSelDosLotes] = useState<Set<string>>(new Set());
  const toggleDosLotes = (n: string) => setSelDosLotes((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelDosLotes(new Set(animaisDosLotesSel.map((a) => a.numero)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lotesSelecionados.join("|")]);

  // Categoria: pode escolher mais de uma — ao concluir, abre janela suspensa
  // com a união dos animais de todas as categorias marcadas.
  const [categoriasSel, setCategoriasSel] = useState<Set<string>>(new Set());
  const toggleCategoria = (id: string) => setCategoriasSel((p) => { const s = new Set(p); s.has(id) ? s.delete(id) : s.add(id); return s; });
  const [animaisCategoriasUniao, setAnimaisCategoriasUniao] = useState<string[]>([]);
  useEffect(() => {
    if (!categoriasSel.size) { setAnimaisCategoriasUniao([]); return; }
    Promise.all(Array.from(categoriasSel).map((id) => {
      const cat = CATEGORIAS_ANIMAIS.find((c) => c.id === id);
      if (!cat) return Promise.resolve([] as string[]);
      return previewCriteriosLote(cat.criterios).then((r: any) => r.animais || []).catch(() => [] as string[]);
    })).then((listas) => setAnimaisCategoriasUniao(Array.from(new Set(listas.flat()))));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [Array.from(categoriasSel).sort().join("|")]);
  const animaisDasCategoriasSel = useMemo(() => {
    const nums = new Set(animaisCategoriasUniao);
    return animais.filter((a) => nums.has(a.numero));
  }, [animais, animaisCategoriasUniao]);
  const [selDasCategorias, setSelDasCategorias] = useState<Set<string>>(new Set());
  const toggleDasCategorias = (n: string) => setSelDasCategorias((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  useEffect(() => {
    setSelDasCategorias(new Set(animaisCategoriasUniao));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animaisCategoriasUniao.join("|")]);

  const [realizado, setRealizado] = useState(false);
  // "Já foi aplicado?" — só para vacina/tratamento (exame usa o checkbox "realizado" abaixo,
  // já que não existe uma aplicação de produto para exame). Não aplicado ainda vira
  // pendência (AplicacaoAgendada) em vez de Sanidade — mesmo padrão de FormSanidade.
  const [aplicado, setAplicado] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: "ok" | "erro"; txt: string } | null>(null);
  // Vindo da Agenda ("Dar baixa" de um evento/regra sanitária preventiva): ao
  // salvar, marca a pendência original como realizada para sumir da Agenda.
  const [eventoAgenda, setEventoAgenda] = useState<string | null>(null);

  // Diagnóstico do exame (positivo/negativo/indefinido) ou resultado numérico
  // — só para eventos categoria_preventiva == "exame". Nunca gera aplicação
  // de medicamento; positivo marca "A descartar" automaticamente.
  const [exames, setExames] = useState<ExameDef[]>([]);
  const [diagnostico, setDiagnostico] = useState<"" | "positivo" | "negativo" | "indefinido">("");
  const [resultadoNumerico, setResultadoNumerico] = useState("");

  useEffect(() => { fetchEventosSanitarios().then((d) => setEventos(d.filter((e: any) => e.ativo))).catch(() => {}); }, []);
  useEffect(() => { fetchExames().then(setExames).catch(() => {}); }, []);
  useEffect(() => { setDiagnostico(""); setResultadoNumerico(""); }, [eventoId]);

  // Pré-preenche a partir da Agenda — evento, data e (se for por animal) o
  // número da matriz já vêm prontos; o restante (categoria/lote, se for um
  // lembrete de rebanho) o usuário escolhe na hora.
  useEffect(() => {
    const qs = new URLSearchParams(window.location.search);
    if (qs.get("ir") !== "preventivo_aplicacao") return;
    const evId = qs.get("evento_sanitario_id");
    if (evId) setEventoId(evId);
    const data = qs.get("data"); if (data) setDataEvento(data);
    const numero = qs.get("numero_matriz");
    if (numero) { setVinculo("animal"); setAnimaisSel(new Set([numero])); }
    setEventoAgenda(qs.get("evento_agenda"));
  }, []);

  const evento = eventos.find((e) => String(e.id) === eventoId);
  const ehExame = evento?.categoria_preventiva === "exame";
  const exameDef = evento?.exame_definicao_id ? exames.find((x) => x.id === evento.exame_definicao_id) : undefined;
  const modoNumerico = ehExame && exameDef?.tipo_resultado === "numerico";

  // Produto padrão do evento zerado/negativo/no mínimo — oferece a opção de
  // escolher um medicamento substituto na hora do lançamento.
  const estoquePorNome = useMemo(() => new Map(estoque.map((e) => [e.nome, e])), [estoque]);
  const itemPadrao = evento?.produto_padrao ? estoquePorNome.get(evento.produto_padrao) : undefined;
  const produtoPadraoBaixo = !!itemPadrao && ((itemPadrao.quantidade ?? 0) <= 0 || (itemPadrao.estoque_minimo != null && (itemPadrao.quantidade ?? 0) < itemPadrao.estoque_minimo));
  const [usarSubstituto, setUsarSubstituto] = useState(false);
  const [produtoSubstituto, setProdutoSubstituto] = useState("");
  const [opcoesSubstituto, setOpcoesSubstituto] = useState<{ nome: string; quantidade?: number | null; unidade?: string | null }[]>([]);
  useEffect(() => {
    setUsarSubstituto(false); setProdutoSubstituto(""); setOpcoesSubstituto([]);
  }, [eventoId]);
  useEffect(() => {
    if (!usarSubstituto) return;
    const filtro = itemPadrao?.classificacao_medicamento ? { classificacao: itemPadrao.classificacao_medicamento }
      : itemPadrao?.principio_ativo ? { principio_ativo: itemPadrao.principio_ativo } : {};
    fetchMedicamentos(filtro).then((m: any[]) => setOpcoesSubstituto(m)).catch(() => setOpcoesSubstituto([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usarSubstituto]);

  const numeros = useMemo(() => {
    if (vinculo === "animal") return Array.from(animaisSel);
    if (vinculo === "lote") return Array.from(selDosLotes);
    return Array.from(selDasCategorias);
  }, [vinculo, animaisSel, selDosLotes, selDasCategorias]);

  // Regra já existente no calendário sanitário para o mesmo evento preventivo
  // — pergunta se o usuário quer lançar o próximo evento já agendado (puxa
  // data/frequência dela) ou se é mesmo um lançamento avulso/novo.
  const [regraExistente, setRegraExistente] = useState<any | null>(null);
  const [decisaoRegra, setDecisaoRegra] = useState<"existente" | "novo" | null>(null);
  useEffect(() => {
    setRegraExistente(null);
    setDecisaoRegra(null);
    if (!eventoId || eventoAgenda) return;
    fetchCalendarioSanitario({ eventoSanitarioId: Number(eventoId) })
      .then((regras: any[]) => { if (regras.length) setRegraExistente(regras[0]); })
      .catch(() => {});
  }, [eventoId, eventoAgenda]);
  const usarRegraExistente = () => {
    if (!regraExistente) return;
    setDataEvento(regraExistente.proxima_ocorrencia || regraExistente.data_evento);
    setFreqValor(String(regraExistente.frequencia_valor));
    setFreqUnidade(regraExistente.frequencia_unidade);
    if (regraExistente.veterinario) setVeterinario(regraExistente.veterinario);
    setDecisaoRegra("existente");
  };

  const alvoLabel = vinculo === "lote" ? lotesSelecionados.join(", ")
    : vinculo === "categoria" ? Array.from(categoriasSel).map((id) => CATEGORIAS_ANIMAIS.find((c) => c.id === id)?.label).filter(Boolean).join(", ")
    : "";

  const toggle = (n: string) => setAnimaisSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleTodos = () => setAnimaisSel((p) => p.size === animais.length ? new Set() : new Set(animais.map((a) => a.numero)));

  async function salvar() {
    setMsg(null);
    if (!eventoId) { setMsg({ tipo: "erro", txt: "Escolha o evento preventivo." }); return; }
    if (!dataEvento) { setMsg({ tipo: "erro", txt: "Informe a data de referência." }); return; }
    // "Repetir a cada" aceita 0 — 0 significa "não repetir", isto é, um
    // lançamento avulso que não entra no calendário sanitário (cadastrar-
    // Preventivo do backend já cuida disso quando frequencia_valor == 0).
    const freqValorNum = freqValor.trim() === "" ? 1 : Number(freqValor);
    setSalvando(true);
    try {
      const substituto = usarSubstituto && produtoSubstituto ? estoquePorNome.get(produtoSubstituto) : undefined;
      const r = await cadastrarPreventivo({
        evento_sanitario_id: Number(eventoId), categoria_alvo: alvoLabel || null, data_evento: dataEvento,
        frequencia_valor: freqValorNum, frequencia_unidade: freqUnidade,
        animais: numeros, aplicar: !ehExame, aplicado, veterinario: veterinario || null,
        produto: substituto?.nome, unidade: substituto?.unidade,
        resultado_exame: ehExame && !modoNumerico && diagnostico ? diagnostico : undefined,
        resultado_numerico: ehExame && modoNumerico && resultadoNumerico !== "" ? Number(resultadoNumerico) : undefined,
      });
      // Para vacina/tratamento, "aplicado" já diz se aconteceu (some da Agenda) ou
      // não (continua pendente); exame usa o checkbox "realizado" independente.
      const marcarOcorrenciaFeita = ehExame ? realizado : aplicado;
      if (marcarOcorrenciaFeita && r?.regra?.id) {
        await marcarEventoRealizado(`calendario_sanitario_${r.regra.id}__${dataEvento}`).catch(() => {});
      }
      // Veio da Agenda (link "Dar baixa") — marca a pendência de origem como
      // realizada só se de fato foi feito, senão ela deve continuar aparecendo.
      if (eventoAgenda && marcarOcorrenciaFeita) {
        await marcarEventoRealizado(eventoAgenda).catch(() => {});
        setEventoAgenda(null);
      }
      const nApl = r?.aplicacao ? (r.aplicacao.criados || r.aplicacao.agendadas || 0) : 0;
      const agendado = !ehExame && !aplicado && nApl > 0;
      let txtDiagnostico = "";
      if (r?.resultado_exame) {
        const { resultado, banda, animais: nDiag } = r.resultado_exame;
        if (resultado === "positivo") txtDiagnostico = ` · ${nDiag} animal(is) positivo(s) — marcado(s) automaticamente "A descartar".`;
        else if (resultado === "negativo") txtDiagnostico = ` · ${nDiag} animal(is) negativo(s) (liberada).`;
        else if (resultado === "indefinido") txtDiagnostico = ` · ${nDiag} animal(is) indefinido(s) — marcado(s) para repetir o exame.`;
        else if (banda) txtDiagnostico = ` · resultado numérico: ${banda === "abaixo" ? "abaixo da faixa" : banda === "acima" ? "acima da faixa" : "dentro da faixa"}.`;
      }
      setMsg({ tipo: "ok", txt: `Preventivo registrado no calendário${nApl ? ` · ${nApl} aplicação(ões)${agendado ? " programada(s) na Agenda" : ""}` : ""}${ehExame ? " (exame — sem baixa de estoque)" : ""}${txtDiagnostico}.` });
      setAnimaisSel(new Set()); setLotesSelecionados([]); setCategoriasSel(new Set());
      setDiagnostico(""); setResultadoNumerico("");
    } catch (e: any) { setMsg({ tipo: "erro", txt: e.message }); }
    finally { setSalvando(false); }
  }

  return (
    <>
      <p style={nota}>Registra um preventivo (vacina/exame/tratamento) mirando animais, categoria ou lote — grava a regra no calendário e, para vacina/tratamento, a aplicação com baixa de estoque. Exame não baixa estoque; permite vincular o veterinário.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2">
        <Campo label="Evento preventivo">
          <select style={inputStyle} value={eventoId} onChange={(e) => setEventoId(e.target.value)}>
            <option value="">Selecione…</option>
            {eventos.map((ev) => <option key={ev.id} value={ev.id}>{ev.nome}{ev.categoria_preventiva ? ` — ${LABEL_CAT_PREV[ev.categoria_preventiva] || ev.categoria_preventiva}` : ""}</option>)}
          </select>
        </Campo>
        <Campo label="Data de referência"><input type="date" style={inputStyle} value={dataEvento} onChange={(e) => setDataEvento(e.target.value)} /></Campo>
        <Campo label="Repetir a cada">
          <div className="flex items-center gap-2">
            <input type="number" min={0} style={inputStyle} value={freqValor} onChange={(e) => setFreqValor(e.target.value)} />
            <select style={inputStyle} value={freqUnidade} onChange={(e) => setFreqUnidade(e.target.value)}>
              {FREQUENCIA_UNIDADES.map((u) => <option key={u.v} value={u.v}>{u.l}</option>)}
            </select>
          </div>
          <p style={{ fontSize: "0.7rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>0 = não repetir — evento avulso, não entra no calendário sanitário.</p>
        </Campo>
        {ehExame && (
          <Campo label="Veterinário (exame)"><input style={inputStyle} value={veterinario} onChange={(e) => setVeterinario(e.target.value)} placeholder="ex.: Dr. Carlos" /></Campo>
        )}
      </div>

      {evento && (evento.doenca_nome || evento.produto_padrao) && (
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
          {evento.doenca_nome && <>Previne: <strong>{evento.doenca_nome}</strong>. </>}
          {!ehExame && evento.produto_padrao && <>Produto padrão: <strong>{evento.produto_padrao}</strong>{evento.dose_padrao != null ? ` (${evento.dose_padrao}${evento.unidade_padrao ? " " + evento.unidade_padrao : ""})` : ""}.</>}
          {ehExame && <span style={{ color: "var(--blue)" }}> Exame — sem baixa de estoque, só agendamento.</span>}
        </p>
      )}
      {!ehExame && produtoPadraoBaixo && (
        <div style={{ marginTop: "0.4rem" }}>
          <p style={{ fontSize: "0.72rem", color: "var(--amber)", margin: 0 }}>⚠ Estoque de "{evento?.produto_padrao}" zerado, negativo ou no mínimo.</p>
          <label className="flex items-center gap-2" style={{ fontSize: "0.75rem", color: "var(--text-muted)", cursor: "pointer" }}>
            <input type="checkbox" checked={usarSubstituto} onChange={(e) => { setUsarSubstituto(e.target.checked); setProdutoSubstituto(""); }} />
            Selecionar medicamento substituto
          </label>
          {usarSubstituto && (
            <div style={{ marginTop: "0.25rem", maxWidth: 320 }}>
              <EstoquePicker itens={opcoesSubstituto} value={produtoSubstituto} onChange={setProdutoSubstituto} placeholder="Selecione o substituto…" />
            </div>
          )}
        </div>
      )}

      {regraExistente && decisaoRegra === null && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 75, padding: "1rem" }}>
          <div className="card" style={{ width: "480px", maxWidth: "95vw" }}>
            <div className="card-header mb-2">Já existe uma regra agendada para este evento</div>
            <p style={{ fontSize: "0.82rem", color: "var(--text)", marginBottom: "0.5rem" }}>
              O evento <strong>{evento?.nome}</strong> já tem uma regra no calendário sanitário
              {regraExistente.categoria_alvo ? <> para <strong>{regraExistente.categoria_alvo}</strong></> : ""},
              {" "}com próxima ocorrência em <strong>{new Date(regraExistente.proxima_ocorrencia + "T00:00:00").toLocaleDateString("pt-BR")}</strong> (repete a cada {regraExistente.frequencia_valor} {regraExistente.frequencia_unidade}).
            </p>
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              Deseja lançar o próximo evento já agendado (a data e a frequência abaixo serão preenchidas automaticamente) ou é um novo evento avulso?
            </p>
            <div className="flex items-center gap-3">
              <button className="btn-primary" onClick={usarRegraExistente}>Usar o evento já agendado</button>
              <button className="btn-ghost" onClick={() => setDecisaoRegra("novo")}>É um novo evento avulso</button>
            </div>
          </div>
        </div>
      )}

      {ehExame && (
        <div style={{ marginTop: "0.9rem", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: "10px", padding: "0.9rem 1rem" }}>
          <p style={{ fontWeight: 700, fontSize: "0.85rem", marginBottom: "0.6rem" }}>Diagnóstico do exame{exameDef ? ` — ${exameDef.nome}` : ""}</p>
          {!modoNumerico ? (
            <>
              <div className="flex items-center gap-2" style={{ flexWrap: "wrap" }}>
                {(["positivo", "negativo", "indefinido"] as const).map((r) => (
                  <button key={r} type="button" onClick={() => setDiagnostico((d) => (d === r ? "" : r))}
                    style={{ fontSize: "0.8rem", padding: "0.4rem 1rem", borderRadius: "999px", cursor: "pointer",
                      border: "1px solid " + (diagnostico === r ? "var(--dourado)" : "var(--border)"),
                      background: diagnostico === r ? "rgba(94,26,46,0.4)" : "transparent",
                      color: diagnostico === r ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: diagnostico === r ? 700 : 500 }}>
                    {LABEL_RESULTADO_EXAME[r]}
                  </button>
                ))}
              </div>
              <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                Aplica-se aos animais marcados abaixo. <strong>Positivo</strong> marca automaticamente "A descartar";
                {" "}<strong>negativo</strong> fica liberada; <strong>indefinido</strong> marca para repetir o exame — para fins de relatório.
              </p>
            </>
          ) : (
            <>
              <div style={{ maxWidth: 220 }}>
                <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Valor lançado</label>
                <input type="number" inputMode="decimal" style={inputStyle} value={resultadoNumerico} onChange={(e) => setResultadoNumerico(e.target.value)} />
              </div>
              {exameDef?.faixa_min != null && exameDef?.faixa_max != null && (
                <p style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: "0.5rem" }}>
                  Faixa cadastrada: {exameDef.faixa_min} a {exameDef.faixa_max}.
                  {exameDef.acao_abaixo && <> Abaixo: {exameDef.acao_abaixo}.</>}
                  {exameDef.acao_dentro && <> Dentro: {exameDef.acao_dentro}.</>}
                  {exameDef.acao_acima && <> Acima: {exameDef.acao_acima}.</>}
                </p>
              )}
            </>
          )}
        </div>
      )}

      <div style={{ marginTop: "0.85rem" }}>
        <TabBar<"animal" | "lote" | "categoria">
          abas={[{ id: "animal", label: "Animais" }, { id: "lote", label: "Lote" }, { id: "categoria", label: "Categoria" }]}
          ativa={vinculo} onChange={setVinculo}
        />
      </div>

      {vinculo === "animal" && (
        <div className="mt-2">
          <AnimalPickerModal
            animais={animais} selecionados={animaisSel} onToggle={toggle}
            titulo="Selecionar animal(is)"
            colunas={[
              { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
              { header: "Lote", render: (a) => a.grupo_primario || "—" },
              { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
              { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
            ]}
          />
        </div>
      )}
      {vinculo === "lote" && (
        <div className="mt-2">
          <LotePicker opcoes={opcoesLoteDeAnimais(animais, codigosLotesTodos)} selecionados={lotesSelecionados} onChange={setLotesSelecionados} placeholder="Selecionar lote(s)…" />
          {lotesSelecionados.length > 0 && (
            <div style={{ marginTop: "0.6rem" }}>
              <AnimalPickerModal
                animais={animaisDosLotesSel} selecionados={selDosLotes} onToggle={toggleDosLotes}
                titulo="Ajustar animais do(s) lote(s) selecionado(s)"
                placeholder="Ajustar animais do(s) lote(s)…"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
                  { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
                ]}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {selDosLotes.size} de {animaisDosLotesSel.length} animal(is) no(s) lote(s) selecionado(s) — desmarque na janela acima para excluir algum.
              </p>
            </div>
          )}
        </div>
      )}
      {vinculo === "categoria" && (
        <div className="mt-2">
          <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Selecione uma ou mais categorias:</p>
          <div className="flex flex-wrap gap-3">
            {CATEGORIAS_ANIMAIS.map((c) => (
              <label key={c.id} className="flex items-center gap-2" style={{ fontSize: "0.8rem", cursor: "pointer" }}>
                <input type="checkbox" checked={categoriasSel.has(c.id)} onChange={() => toggleCategoria(c.id)} /> {c.label}
              </label>
            ))}
          </div>
          {categoriasSel.size > 0 && (
            <div style={{ marginTop: "0.6rem" }}>
              <AnimalPickerModal
                animais={animaisDasCategoriasSel} selecionados={selDasCategorias} onToggle={toggleDasCategorias}
                titulo="Ajustar animais das categorias selecionadas"
                placeholder="Ajustar animais das categorias…"
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
                  { header: "Sit. rep.", render: (a) => a.sit_rep || "—" },
                ]}
              />
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                {selDasCategorias.size} de {animaisDasCategoriasSel.length} animal(is) na(s) categoria(s) selecionada(s) — desmarque na janela acima para excluir algum.
              </p>
            </div>
          )}
        </div>
      )}

      {ehExame ? (
        <label className="flex items-center gap-2 mt-3" style={{ fontSize: "0.8rem" }}>
          <input type="checkbox" checked={realizado} onChange={(e) => setRealizado(e.target.checked)} /> Já foi realizado (não entra como pendência na Agenda)
        </label>
      ) : (
        <Campo label="Já foi aplicado?" full>
          <div className="flex items-center gap-4 mt-1">
            <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={aplicado} onChange={() => setAplicado(true)} /> Sim — aplicar e baixar o estoque agora</label>
            <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", cursor: "pointer" }}><input type="radio" checked={!aplicado} onChange={() => setAplicado(false)} /> Não — só programar na Agenda</label>
          </div>
        </Campo>
      )}

      {msg && <p style={{ fontSize: "0.8rem", marginTop: "0.6rem", color: msg.tipo === "ok" ? "var(--green-light)" : "var(--red)" }}>{msg.txt}</p>}
      <div className="flex items-center gap-3 mt-3">
        <button className="btn-primary" onClick={salvar} disabled={salvando}>
          <Check size={14} /> {salvando ? "Salvando…" : `Registrar preventivo${numeros.length ? ` (${numeros.length} animais)` : ""}`}
        </button>
      </div>
    </>
  );
}

// ─────────────────────── BST — seleção nas tabelas (Aptas/Incluir no próximo BST/Inaptas) ───────────────────────
function BstLancamentoView() {
  const [dados, setDados] = useState<any | null>(null);
  const carregar = () => fetchAgenda().then(setDados).catch(() => setDados(null));
  useEffect(() => { carregar(); }, []);
  return (
    <>
      <p style={nota}>BST (somatotropina bovina) — marque os animais direto nas tabelas e lance (aplicar, agendar ou marcar inapta).</p>
      <PainelLancarBst agenda={dados} onAtualizado={carregar} />
    </>
  );
}

function FormProtocoloSanitario({ animais, estoque }: { animais: AnimalRow[]; estoque: EstoqueItem[] }) {
  const [protocolos, setProtocolos] = useState<ProtocoloLocal[]>([]);
  const [protocoloId, setProtocoloId] = useState("");
  const [matriz, setMatriz] = useState("");
  const [dataInicio, setDataInicio] = useState(() => new Date().toISOString().slice(0, 10));
  const [responsavel, setResponsavel] = useState("");
  const [observacao, setObservacao] = useState("");
  const [classificacaoMastite, setClassificacaoMastite] = useState("");
  const [grauMastite, setGrauMastite] = useState("");
  const [agente, setAgente] = useState("");
  const [resultadoCmt, setResultadoCmt] = useState("");
  const [tetosSel, setTetosSel] = useState<Set<string>>(new Set());
  const [agentesMastite, setAgentesMastite] = useState<string[]>([]);
  const [ctxMastite, setCtxMastite] = useState<{ del_atual: number | null; ccs_ultima: number | null; cmt_ultimo: string | null } | null>(null);
  // Etapas cadastradas por princípio ativo/classificação: escolher o medicamento agora.
  const [escolhasMed, setEscolhasMed] = useState<Record<number, string>>({});
  const [medOpcoes, setMedOpcoes] = useState<Record<number, { nome: string; quantidade?: number | null; unidade?: string | null }[]>>({});
  // "Incluir itens sem estoque" — mesmo padrão da Inseminação/Sanidade avulsa.
  const [incluirSemEstoque, setIncluirSemEstoque] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

  const protocoloSel = protocolos.find((p) => String(p.id) === protocoloId);
  useEffect(() => { if (protocoloSel?.eh_mastite && !agentesMastite.length) fetchMastiteOpcoes().then((o) => setAgentesMastite(o.agentes)).catch(() => {}); }, [protocoloSel?.eh_mastite]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (protocoloSel?.eh_mastite && matriz) { fetchMastiteContexto(matriz).then(setCtxMastite).catch(() => setCtxMastite(null)); }
    else setCtxMastite(null);
  }, [protocoloSel?.eh_mastite, matriz]);

  // Lançamento em massa (protocolos que não são de mastite): animal(is), lote(s) ou categoria de animais.
  const [vinculo, setVinculo] = useState<"animal" | "lote" | "categoria">("animal");
  const [animaisSelecionados, setAnimaisSelecionados] = useState<Set<string>>(new Set());
  const [lotesSelecionados, setLotesSelecionados] = useState<Set<string>>(new Set());
  const [lotesTodos, setLotesTodos] = useState<LoteRow[]>([]);
  const [pickerAberto, setPickerAberto] = useState<"lote" | null>(null);
  const abrirPickerLotes = () => {
    if (!lotesTodos.length) fetchLotes().then(setLotesTodos).catch(() => {});
    setPickerAberto("lote");
  };
  const toggleAnimalSelecionado = (numero: string) => setAnimaisSelecionados((p) => { const n = new Set(p); n.has(numero) ? n.delete(numero) : n.add(numero); return n; });
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

  const carregarProtocolos = () => fetchProtocolosSanitarios().then((d) => setProtocolos(d.filter((p: ProtocoloLocal) => p.ativo))).catch(() => {});
  useEffect(() => { carregarProtocolos(); }, []);
  const [abrirNovoProtocolo, setAbrirNovoProtocolo] = useState(false);

  const protocolo = protocolos.find((p) => p.id === Number(protocoloId));
  const toggleTeto = (t: string) => setTetosSel((p) => { const s = new Set(p); s.has(t) ? s.delete(t) : s.add(t); return s; });

  // Ao escolher o protocolo, carrega os medicamentos que cumprem o critério de
  // cada etapa cadastrada por princípio ativo/classificação.
  const etapasCriterio = useMemo(
    () => (protocolo?.etapas || []).filter((e) => (e.criterio_tipo || "medicamento") !== "medicamento" && e.id != null),
    [protocolo]
  );
  // Etapas de produto FIXO (cadastrado direto no protocolo, não por critério)
  // — pode faltar o medicamento cadastrado; se estiver zerado/negativo/no
  // mínimo, oferece a opção de escolher um substituto na hora do lançamento.
  const etapasFixas = useMemo(
    () => (protocolo?.etapas || []).filter((e) => (e.criterio_tipo || "medicamento") === "medicamento" && e.id != null),
    [protocolo]
  );
  const estoquePorNome = useMemo(() => new Map(estoque.map((e) => [e.nome, e])), [estoque]);
  const estoqueBaixo = (produto: string) => {
    const item = estoquePorNome.get(produto);
    if (!item) return false;
    const qtd = item.quantidade ?? 0;
    return qtd <= 0 || (item.estoque_minimo != null && qtd < item.estoque_minimo);
  };
  const [substitutosAtivos, setSubstitutosAtivos] = useState<Set<number>>(new Set());
  const [medOpcoesSubstituto, setMedOpcoesSubstituto] = useState<Record<number, { nome: string; quantidade?: number | null; unidade?: string | null }[]>>({});
  const toggleSubstituto = (etapaId: number, produtoOriginal: string) => {
    setSubstitutosAtivos((p) => {
      const n = new Set(p);
      if (n.has(etapaId)) {
        n.delete(etapaId);
        setEscolhasMed((s) => { const c = { ...s }; delete c[etapaId]; return c; });
      } else {
        n.add(etapaId);
        const item = estoquePorNome.get(produtoOriginal);
        const filtro = item?.classificacao_medicamento ? { classificacao: item.classificacao_medicamento }
          : item?.principio_ativo ? { principio_ativo: item.principio_ativo } : {};
        fetchMedicamentos({ ...filtro, incluir_sem_estoque: incluirSemEstoque })
          .then((m) => setMedOpcoesSubstituto((o) => ({ ...o, [etapaId]: m as any[] })))
          .catch(() => setMedOpcoesSubstituto((o) => ({ ...o, [etapaId]: [] })));
      }
      return n;
    });
  };
  useEffect(() => {
    setEscolhasMed({});
    setSubstitutosAtivos(new Set());
    setMedOpcoesSubstituto({});
    if (!protocolo) { setMedOpcoes({}); return; }
    const crit = (protocolo.etapas || []).filter((e) => (e.criterio_tipo || "medicamento") !== "medicamento" && e.id != null);
    if (!crit.length) { setMedOpcoes({}); return; }
    Promise.all(crit.map((e) =>
      fetchMedicamentos({ ...(e.criterio_tipo === "principio_ativo" ? { principio_ativo: e.produto } : e.criterio_tipo === "doenca" ? { doenca: e.produto } : { classificacao: e.produto }), incluir_sem_estoque: incluirSemEstoque })
        .then((m) => [e.id as number, m] as const).catch(() => [e.id as number, [] as any[]] as const)
    )).then((pares) => setMedOpcoes(Object.fromEntries(pares)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [protocoloId, incluirSemEstoque]);

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
    const faltando = etapasCriterio.find((e) => !escolhasMed[e.id as number]);
    if (faltando) { setErro(`Escolha o medicamento da etapa D${faltando.dia} (${faltando.produto}).`); return; }

    setSalvando(true);
    try {
      const r = await lancarProtocoloSanitario({
        protocolo_id: protocolo.id, numeros_matriz: numeros, data_inicio: dataInicio,
        responsavel: responsavel || undefined, observacao: observacao || undefined,
        classificacao_mastite: classificacaoMastite || undefined,
        grau_mastite: grauMastite ? Number(grauMastite) : undefined, agente: agente || undefined,
        resultado_cmt: resultadoCmt || undefined,
        tetos_afetados: Array.from(tetosSel),
        escolhas_medicamento: Object.fromEntries([
          ...etapasCriterio.map((e) => [String(e.id), escolhasMed[e.id as number]]),
          ...etapasFixas.filter((e) => substitutosAtivos.has(e.id as number) && escolhasMed[e.id as number]).map((e) => [String(e.id), escolhasMed[e.id as number]]),
        ]),
      });
      const avisoTxt = (r.avisos && r.avisos.length) ? " ⚠️ " + r.avisos.join(" ") : "";
      setSucesso(`Protocolo "${protocolo.nome}" lançado para ${r.criados} animal(is) — ${protocolo.etapas.length} evento(s) na Agenda por animal.${avisoTxt}`);
      setMatriz(""); setObservacao(""); setClassificacaoMastite(""); setGrauMastite(""); setAgente(""); setResultadoCmt(""); setTetosSel(new Set());
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
          <div className="flex items-center gap-2">
            <select style={inputStyle} value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
              <option value="">Selecione…</option>
              {protocolos.map((p) => <option key={p.id} value={p.id}>{p.nome}{p.eh_mastite ? " (mastite)" : ""}</option>)}
            </select>
            <button type="button" className="btn-ghost" title="Cadastrar novo protocolo sanitário" style={{ fontSize: "0.72rem", whiteSpace: "nowrap" }} onClick={() => setAbrirNovoProtocolo(true)}>
              <Plus size={13} /> Novo
            </button>
          </div>
          {abrirNovoProtocolo && (
            <Modal title="Novo protocolo sanitário" onClose={() => { setAbrirNovoProtocolo(false); carregarProtocolos(); }} width="900px">
              <CadastroProtocolosSanitarios />
            </Modal>
          )}
        </Campo>
        <Campo label="Data de início (D1)"><input type="date" style={inputStyle} value={dataInicio} onChange={(e) => setDataInicio(e.target.value)} /></Campo>

        {etapasCriterio.length > 0 && (
          <div style={{ gridColumn: "1 / -1", background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 8, padding: "0.75rem" }}>
            <p style={{ fontSize: "0.78rem", fontWeight: 700, color: "var(--dourado-light)", marginBottom: "0.5rem" }}>Escolha o medicamento de cada etapa (cadastrada por critério)</p>
            <label className="flex items-center gap-2 mb-2" style={{ fontSize: "0.75rem", color: "var(--text-muted)", cursor: "pointer" }}>
              <input type="checkbox" checked={incluirSemEstoque} onChange={(e) => setIncluirSemEstoque(e.target.checked)} />
              Incluir itens sem estoque
            </label>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {etapasCriterio.map((e) => (
                <div key={e.id}>
                  <label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>D{e.dia} — {e.criterio_tipo === "principio_ativo" ? "Princípio ativo" : e.criterio_tipo === "doenca" ? "Doença" : "Classificação"}: <strong>{e.produto}</strong></label>
                  <EstoquePicker
                    itens={medOpcoes[e.id as number] || []} value={escolhasMed[e.id as number] || ""}
                    onChange={(nome) => setEscolhasMed((s) => ({ ...s, [e.id as number]: nome }))}
                    placeholder="Selecione o medicamento…"
                  />
                  {!(medOpcoes[e.id as number] || []).length && <p style={{ fontSize: "0.7rem", color: "var(--amber)" }}>Nenhum medicamento cadastrado com esse critério.</p>}
                </div>
              ))}
            </div>
          </div>
        )}

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
              <AnimalPickerModal animais={animais} selecionados={animaisSelecionados} onToggle={toggleAnimalSelecionado} colunas={pickerColunasAnimais} titulo="Selecionar animal(is)" />
            )}
            {vinculo === "lote" && (
              <button type="button" className="btn-ghost" style={{ fontSize: "0.75rem" }} onClick={abrirPickerLotes}>
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
          {ctxMastite && (
            <div className="flex items-center gap-4 mb-2" style={{ flexWrap: "wrap", fontSize: "0.78rem" }}>
              <span>DEL: <strong>{ctxMastite.del_atual != null ? `${ctxMastite.del_atual} dias` : "—"}</strong></span>
              <span>Última CCS: <strong>{ctxMastite.ccs_ultima != null ? `${ctxMastite.ccs_ultima} mil/mL` : "—"}</strong></span>
              <span>Último CMT: <strong>{ctxMastite.cmt_ultimo || "—"}</strong></span>
            </div>
          )}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <Campo label="Classificação">
              <select style={inputStyle} value={classificacaoMastite} onChange={(e) => setClassificacaoMastite(e.target.value)}>
                <option value="">Selecione…</option>
                {CLASSIFICACOES_MASTITE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </Campo>
            <Campo label="Grau">
              <select style={inputStyle} value={grauMastite} onChange={(e) => setGrauMastite(e.target.value)}>
                <option value="">Selecione…</option>
                <option value="1">Grau 1</option><option value="2">Grau 2</option><option value="3">Grau 3</option>
              </select>
            </Campo>
            <Campo label="Agente (patógeno)">
              <input style={inputStyle} list="agentes-mastite" value={agente} onChange={(e) => setAgente(e.target.value)} placeholder="Selecione ou digite…" />
              <datalist id="agentes-mastite">{agentesMastite.map((a) => <option key={a} value={a} />)}</datalist>
            </Campo>
            <Campo label="Resultado do CMT">
              <select style={inputStyle} value={resultadoCmt} onChange={(e) => setResultadoCmt(e.target.value)}>
                <option value="">Selecione…</option>
                {["-", "+", "++", "+++"].map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            </Campo>
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
              {cronograma.map((e, i) => {
                const fixa = (e.criterio_tipo || "medicamento") === "medicamento" && e.id != null;
                const baixo = fixa && estoqueBaixo(e.produto);
                return (
                  <tr key={i}>
                    <td>D{e.dia}</td>
                    <td>{e.data}</td>
                    <td>
                      {e.produto}
                      {baixo && (
                        <div style={{ marginTop: "0.3rem" }}>
                          <p style={{ fontSize: "0.7rem", color: "var(--amber)", margin: 0 }}>⚠ Estoque zerado, negativo ou no mínimo.</p>
                          <label className="flex items-center gap-2" style={{ fontSize: "0.72rem", color: "var(--text-muted)", cursor: "pointer" }}>
                            <input type="checkbox" checked={substitutosAtivos.has(e.id as number)} onChange={() => toggleSubstituto(e.id as number, e.produto)} />
                            Selecionar medicamento substituto
                          </label>
                          {substitutosAtivos.has(e.id as number) && (
                            <div style={{ marginTop: "0.25rem" }}>
                              <EstoquePicker
                                itens={medOpcoesSubstituto[e.id as number] || []} value={escolhasMed[e.id as number] || ""}
                                onChange={(nome) => setEscolhasMed((s) => ({ ...s, [e.id as number]: nome }))}
                                placeholder="Selecione o substituto…"
                              />
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    <td>{e.dosagem} {e.unidade}</td>
                    <td>{e.via || "—"}</td>
                  </tr>
                );
              })}
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

      {pickerAberto === "lote" && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 55, padding: "1rem" }}>
          <div className="card" style={{ width: "640px", maxWidth: "95vw", maxHeight: "85vh", display: "flex", flexDirection: "column" }}>
            <div className="card-header mb-3">Selecionar lote(s)</div>
            <SelecaoLotesTabela lotes={lotesTodos} selecionados={lotesSelecionados} toggle={toggleLoteSelecionado} toggleTodos={toggleTodosLotes} />
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

function FormAlimentacaoDieta() {
  const [dietas, setDietas] = useState<DietaLote[] | null>(null);
  const [alimentosPadrao, setAlimentosPadrao] = useState<string[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);

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

  const atualizarItemReal = (idx: number, patch: Partial<ItemDieta>) => setItensReal((p) => { const n = [...p]; n[idx] = { ...n[idx], ...patch }; return n; });
  const acrescentarItemReal = () => setItensReal((p) => [...p, itemDietaVazio()]);
  const removerItemReal = (idx: number) => setItensReal((p) => (p.length > 1 ? p.filter((_, i) => i !== idx) : p));

  async function confirmarEncerramento(dieta: DietaLote) {
    setErro(null); setSucesso(null);
    try {
      await encerrarDieta(dieta.id, dataEncerramento);
      setEncerrando(null);
      setSucesso(`Dieta do lote ${dieta.lote} encerrada. Para lançar uma nova, use "Cadastrar nova dieta" acima.`);
      carregar();
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

  return (
    <>
      {/* Mesma tela de Configurações > Cadastro > Alimentação — quantidade só
          por animal/dia, cálculo automático de lote/dia e lote/trato (nota
          explicativa dentro do próprio componente). */}
      <div className="flex justify-end mb-2"><TabelaNutricionalBotao /></div>
      <CadastrarNovaDieta onSalvo={carregar} />
      <datalist id="alimentos-padrao-dieta">{alimentosPadrao.map((a) => <option key={a} value={a} />)}</datalist>

      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}

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

const MOVIMENTOS_SAIDA = MOVIMENTOS_ESTOQUE.filter((m) => MOV_BAIXA.has(m));
const MOVIMENTOS_ENTRADA = MOVIMENTOS_ESTOQUE.filter((m) => !MOV_BAIXA.has(m));

function FormEstoque({ estoque, onIrParaFinanceiro }: { estoque: EstoqueItem[]; onIrParaFinanceiro?: (leaf: "financeiro_despesa" | "financeiro_receita") => void }) {
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

  // Filtros para achar o produto certo mais rápido. Por padrão só mostra
  // itens estocáveis (itens não estocáveis existem só para lançamento
  // financeiro, sem controle de quantidade) — "Somente itens em estoque"
  // deixa de ser um filtro fixo e vira uma opção que dá para desmarcar.
  const [busca, setBusca] = useState("");
  const [somenteEstocaveis, setSomenteEstocaveis] = useState(true);
  const [fCategoria, setFCategoria] = useState("");
  const [fFinalidade, setFFinalidade] = useState("");
  const [fPrincipioAtivo, setFPrincipioAtivo] = useState("");
  const [fContaGerencial, setFContaGerencial] = useState("");
  const [planoContas, setPlanoContas] = useState<{ codigo: string; nome: string }[]>([]);
  useEffect(() => { fetchPlanoContas().then(setPlanoContas).catch(() => {}); }, []);

  const itensBase = useMemo(() => somenteEstocaveis ? estoque.filter((e) => e.estocavel !== false) : estoque, [estoque, somenteEstocaveis]);
  const nomeConta = (codigo: string) => planoContas.find((c) => c.codigo === codigo)?.nome || codigo;

  // Cada filtro se aplica sobre os outros três (nunca sobre si mesmo) — assim
  // as OPÇÕES de cada seletor também se restringem conforme os demais já
  // escolhidos ("os filtros se comunicam"), não só a lista final de itens.
  const passaFiltros = (e: EstoqueItem, exceto?: keyof EstoqueItem) =>
    (exceto === "categoria" || !fCategoria || e.categoria === fCategoria) &&
    (exceto === "finalidade" || !fFinalidade || e.finalidade === fFinalidade) &&
    (exceto === "principio_ativo" || !fPrincipioAtivo || e.principio_ativo === fPrincipioAtivo) &&
    (exceto === "conta_gerencial_despesa_padrao" || !fContaGerencial || e.conta_gerencial_despesa_padrao === fContaGerencial);

  const opcoesPara = (campo: keyof EstoqueItem) =>
    Array.from(new Set(itensBase.filter((e) => passaFiltros(e, campo)).map((e) => e[campo]).filter(Boolean))).sort() as string[];

  const categorias = useMemo(() => opcoesPara("categoria"), [itensBase, fFinalidade, fPrincipioAtivo, fContaGerencial]);
  const finalidades = useMemo(() => opcoesPara("finalidade"), [itensBase, fCategoria, fPrincipioAtivo, fContaGerencial]);
  const principiosAtivos = useMemo(() => opcoesPara("principio_ativo"), [itensBase, fCategoria, fFinalidade, fContaGerencial]);
  const contasUsadas = useMemo(() => opcoesPara("conta_gerencial_despesa_padrao"), [itensBase, fCategoria, fFinalidade, fPrincipioAtivo]);

  const itensFiltrados = useMemo(() => itensBase.filter((e) =>
    passaFiltros(e) && (!busca.trim() || e.nome.toLowerCase().includes(busca.trim().toLowerCase()))
  ), [itensBase, fCategoria, fFinalidade, fPrincipioAtivo, fContaGerencial, busca]);

  // Vínculo opcional a um item de Pedido de compra — só entrada de estoque faz
  // sentido vincular (uma saída não "atende" um pedido de compra). É só a
  // partir deste vínculo que o pedido passa a refletir aqui em Estoque.
  const [pedidosCompra, setPedidosCompra] = useState<{ id: number; numero_pedido: string; fornecedor_cliente: string | null }[]>([]);
  const [pedidoId, setPedidoId] = useState("");
  const [itensPedido, setItensPedido] = useState<{ id: number; produto_servico: string }[]>([]);
  const [pedidoItemId, setPedidoItemId] = useState("");

  useEffect(() => {
    if (tipo !== "entrada") return;
    fetchPedidos({ tipo: "compra" })
      .then((lista: any[]) => setPedidosCompra(lista.filter((p) => p.status !== "cancelado" && p.status !== "atendido")))
      .catch(() => {});
  }, [tipo]);
  useEffect(() => {
    if (!pedidoId) { setItensPedido([]); setPedidoItemId(""); return; }
    fetchPedido(Number(pedidoId)).then((p: any) => setItensPedido(p.itens || [])).catch(() => {});
  }, [pedidoId]);

  // Valor do movimento (opcional) e gerar lançamento financeiro a partir dele.
  const [lancarValor, setLancarValor] = useState(false);
  const [valorUnitario, setValorUnitario] = useState("");
  const [gerarFinanceiro, setGerarFinanceiro] = useState(false);

  const item = estoque.find((e) => e.nome === produto);
  const q = Number(qtd) || 0;
  const baixa = MOV_BAIXA.has(mov);
  const restante = item ? (item.quantidade ?? 0) + (baixa ? -q : q) : null;
  const valorTotalCalc = lancarValor && valorUnitario ? q * Number(valorUnitario) : null;

  async function salvar() {
    setErro(null); setSucesso(null);
    if (!produto || !tipo || !mov || !q) { setErro("Selecione o produto, o tipo de movimento e a quantidade."); return; }
    setSalvando(true);
    try {
      const r = await movimentarEstoque({
        nome: produto, movimento: mov, quantidade: q, unidade: unidade || item?.unidade || undefined, data_movimento: dataMov, observacao: observacao || undefined,
        pedido_id: tipo === "entrada" && pedidoId ? Number(pedidoId) : null,
        pedido_item_id: tipo === "entrada" && pedidoItemId ? Number(pedidoItemId) : null,
      });
      setSucesso(`Estoque de ${produto} atualizado: ${r.quantidade} ${r.unidade || ""}.`);
      if (gerarFinanceiro) {
        pedirLancamentoFinanceiro({
          tipo: tipo === "entrada" ? "despesa" : "receita",
          produto,
          quantidade: q,
          unidade: unidade || item?.unidade || null,
          valor_unitario: lancarValor && valorUnitario ? Number(valorUnitario) : null,
          valor_total: valorTotalCalc,
          codigo_conta_gerencial: (tipo === "entrada" ? item?.conta_gerencial_despesa_padrao : item?.conta_gerencial_receita_padrao) || null,
          data_emissao: dataMov,
          observacao: observacao || undefined,
        });
        onIrParaFinanceiro?.(tipo === "entrada" ? "financeiro_despesa" : "financeiro_receita");
      }
      setMov(""); setQtd(""); setObservacao(""); setPedidoId(""); setPedidoItemId("");
      setLancarValor(false); setValorUnitario(""); setGerarFinanceiro(false);
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar movimento de estoque");
    } finally {
      setSalvando(false);
    }
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-3">
        <Campo label="Categoria">
          <select style={inputStyle} value={fCategoria} onChange={(e) => setFCategoria(e.target.value)}>
            <option value="">Todas</option>
            {categorias.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </Campo>
        <Campo label="Medicamento / finalidade">
          <select style={inputStyle} value={fFinalidade} onChange={(e) => setFFinalidade(e.target.value)}>
            <option value="">Todas</option>
            {finalidades.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </Campo>
        <Campo label="Princípio ativo">
          <select style={inputStyle} value={fPrincipioAtivo} onChange={(e) => setFPrincipioAtivo(e.target.value)}>
            <option value="">Todos</option>
            {principiosAtivos.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </Campo>
        <Campo label="Conta gerencial">
          <select style={inputStyle} value={fContaGerencial} onChange={(e) => setFContaGerencial(e.target.value)}>
            <option value="">Todas</option>
            {contasUsadas.map((c) => <option key={c} value={c}>{nomeConta(c)}</option>)}
          </select>
        </Campo>
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8rem", marginBottom: "0.9rem", cursor: "pointer" }}>
        <input type="checkbox" checked={somenteEstocaveis} onChange={(e) => setSomenteEstocaveis(e.target.checked)} /> Somente itens em estoque
      </label>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Buscar / selecionar item">
          <EstoquePicker
            itens={itensFiltrados}
            value={produto}
            onChange={setProduto}
            placeholder="Buscar item…"
            finalidades={FINALIDADES_ESTOQUE}
            incluirNaoEstocaveis={!somenteEstocaveis}
          />
          {itensFiltrados.length !== itensBase.length && (
            <span style={{ fontSize: "0.68rem", color: "var(--text-muted)" }}>{itensFiltrados.length} de {itensBase.length} itens no filtro atual</span>
          )}
          {item?.estoque_semen_id != null && (
            <span style={{ fontSize: "0.68rem", color: "var(--dourado-light)", display: "flex", alignItems: "center", gap: "0.25rem", marginTop: "0.2rem" }}>
              <Dna size={11} /> Vinculado ao Estoque de sêmen — este movimento também ajusta as doses do touro.
            </span>
          )}
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
        {tipo === "entrada" && (
          <>
            <Campo label="Vincular a um pedido de compra (opcional)">
              <select style={inputStyle} value={pedidoId} onChange={(e) => { setPedidoId(e.target.value); setPedidoItemId(""); }}>
                <option value="">— Nenhum —</option>
                {pedidosCompra.map((p) => <option key={p.id} value={p.id}>{p.numero_pedido} — {p.fornecedor_cliente || "sem contraparte"}</option>)}
              </select>
            </Campo>
            {pedidoId && (
              <Campo label="Item do pedido">
                <select style={inputStyle} value={pedidoItemId} onChange={(e) => setPedidoItemId(e.target.value)}>
                  <option value="">— Nenhum —</option>
                  {itensPedido.map((i) => <option key={i.id} value={i.id}>{i.produto_servico}</option>)}
                </select>
                <span style={{ fontSize: "0.68rem", color: "var(--text-muted)", display: "block", marginTop: "0.2rem" }}>
                  É só a partir deste vínculo que o pedido passa a refletir aqui em Estoque.
                </span>
              </Campo>
            )}
          </>
        )}
        <Campo label="Lançar valor deste movimento?">
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem" }}>
            <input type="checkbox" checked={lancarValor} onChange={(e) => setLancarValor(e.target.checked)} /> Informar valor unitário
          </label>
        </Campo>
        {lancarValor && (
          <Campo label="Valor unitário (R$)">
            <input type="number" inputMode="decimal" style={inputStyle} value={valorUnitario} onChange={(e) => setValorUnitario(e.target.value)} />
          </Campo>
        )}
        <Campo label="Gerar movimentação financeira?" full>
          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.85rem" }}>
            <input type="checkbox" checked={gerarFinanceiro} onChange={(e) => setGerarFinanceiro(e.target.checked)} />
            Ao salvar, abrir um lançamento de {tipo === "saida" ? "receita (Contas a receber)" : "despesa (Contas a pagar)"} já com produto, quantidade e valor deste balanço
          </label>
        </Campo>
        <Campo label="Observação" full><textarea style={{ ...inputStyle, minHeight: "3rem" }} value={observacao} onChange={(e) => setObservacao(e.target.value)} /></Campo>
      </div>
      {item && mov && (
        <p style={{ fontSize: "0.78rem", marginTop: "0.3rem" }}>
          {baixa ? "Baixa" : "Entrada"} · Estoque atual: <strong>{item.quantidade ?? 0} {item.unidade || ""}</strong> → depois:{" "}
          <strong style={{ color: (restante ?? 0) < 0 ? "var(--red)" : "var(--green-light)" }}>{restante} {item.unidade || ""}</strong>
          {(restante ?? 0) < 0 && <span style={{ color: "var(--red)" }}> (insuficiente!)</span>}
          {valorTotalCalc != null && <> · Valor do movimento: <strong>{valorTotalCalc.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</strong></>}
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
// Ordem alfabética pelo label (ignorando acento), com "Excluir lançamento"
// sempre por último — não é alfabético de propósito (é a ação mais perigosa).
const TIPOS_GRUPOS = [
  { id: "alimentacao_dieta", label: "Alimentação", icon: Wheat, desc: "Dieta por lote: plano programado, real oferecido e histórico de abertura/encerramento.", leaf: "alimentacao_dieta" },
  {
    id: "animais", label: "Animais", icon: ArrowRightLeft,
    desc: "Movimentar animais entre lotes, comprar/vender ou dar baixa (morte/descarte).",
    subs: [
      { id: "mover_animais", label: "Movimentar animais", icon: ArrowRightLeft, desc: "Transferir um ou vários animais de lote." },
      {
        id: "compra_venda", label: "Compra / Venda", icon: ShoppingCart, desc: "Registrar a compra ou a venda de animal(is).",
        subs: [
          { id: "comprar_animal", label: "Comprar animal", icon: ShoppingCart, desc: "Registrar a compra de animal(is) — vendedor via fornecedor, conta gerencial restrita, GTA/ICMS, comissão de corretagem." },
          { id: "comprar_semen", label: "Comprar sêmen", icon: Dna, desc: "Registrar a compra de sêmen — touro já cadastrado ou do banco de dados NAAB, conta gerencial restrita (Sêmen); soma as doses ao estoque de sêmen." },
          { id: "vender_animal", label: "Vender animal", icon: ShoppingCart, desc: "Registrar a venda de animal(is) — comprador via cadastro, motivo/categoria(s) da venda, conta gerencial restrita, GTA/ICMS, comissão de corretagem." },
        ],
      },
      { id: "baixar_animal", label: "Baixa", icon: Skull, desc: "Registrar saída do rebanho: venda, morte, descarte ou marcar 'A descartar'." },
    ],
  },
  { id: "estoque", label: "Balanço de estoque", icon: Package, desc: "Entrada ou saída de item do estoque (balanço do saldo).", leaf: "estoque" },
  {
    id: "financeiro", label: "Financeiro", icon: Wallet,
    desc: "Lançamento de receita ou despesa.",
    subs: [
      { id: "financeiro_despesa", label: "Contas a pagar (despesa)", icon: Wallet, desc: "Lançamento de despesa/conta a pagar." },
      { id: "financeiro_receita", label: "Contas a receber (receita)", icon: Wallet, desc: "Lançamento de receita/conta a receber." },
    ],
  },
  {
    id: "producao", label: "Produção", icon: Milk,
    desc: "Controle leiteiro ou pesagem corporal.",
    subs: [
      { id: "controle", label: "Controle leiteiro", icon: Milk, desc: "Pesagem de leite por vaca ou por lote." },
      { id: "pesagem", label: "Pesagem corporal", icon: Scale, desc: "Peso vivo por animal ou por lote — acompanha o crescimento do rebanho." },
      { id: "secagem", label: "Secagem", icon: Droplet, desc: "Registro de secagem, motivo, ECC e produto(s) — sugere a mudança para o lote de secas." },
      { id: "inducao_lactacao", label: "Indução de lactação", icon: Syringe, desc: "Lança o protocolo de indução (18 ou 28 dias) em um ou vários animais — gera o cronograma completo na Agenda." },
      { id: "qualidade_leite", label: "Qualidade do leite", icon: Milk, desc: "CCS, CBT, gordura, proteína, sólidos totais e ESD — por vaca ou do tanque (rebanho em lactação)." },
      { id: "entrega_leite", label: "Venda mensal do leite", icon: Milk, desc: "Quantidade entregue ao laticínio no mês — compara com o controle leiteiro e a receita recebida." },
      { id: "bst", label: "BST", icon: Droplets, desc: "Somatotropina bovina — selecione os animais direto nas tabelas de Aptas/Incluir no próximo BST/Inaptas e lance (aplicar, agendar ou marcar inapta)." },
    ],
  },
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
    id: "sanidade", label: "Sanitário", icon: HeartPulse,
    desc: "Tratamento curativo ou manejo preventivo.",
    grupos: [
      {
        id: "sanidade_curativa", label: "Curativa", icon: HeartPulse,
        desc: "Tratamento curativo: aplicações de medicamento e protocolos sanitários.",
        subs: [
          { id: "sanidade_aplicacao", label: "Aplicações", icon: Syringe, desc: "Aplicação de medicamento curativo — por animal, categoria, vários animais ou lote." },
          { id: "protocolo_sanitario", label: "Protocolo sanitário", icon: ClipboardList, desc: "Aplicar um protocolo cadastrado (mastite e outros) a um animal — gera um evento na Agenda por dia (D1, D2...)." },
        ],
      },
      {
        id: "sanidade_preventiva", label: "Preventiva", icon: Shield,
        desc: "Manejo preventivo: aplicações preventivas e calendário sanitário.",
        subs: [
          { id: "preventivo_aplicacao", label: "Aplicações", icon: Syringe, desc: "Aplicar um preventivo (vacina/exame) a animais, categoria ou lote — registra e alimenta o calendário." },
          { id: "calendario_sanitario", label: "Calendário sanitário", icon: CalendarClock, desc: "Regra recorrente (sazonal/de rebanho ou por fase fisiológica): evento, frequência, produto e dosagem." },
        ],
      },
    ],
  },
  { id: "exclusao", label: "Excluir lançamento", icon: Trash2, desc: "Apagar um lançamento já salvo, com filtros e prévia de impacto.", leaf: "exclusao" },
];

// Um item de "subs" pode, por sua vez, ter os próprios "subs" (mais um nível
// de sub-aba — caso de Compra/Venda dentro de Animais) — achata recursivamente
// até sobrarem só as folhas de verdade (as que têm formulário próprio).
function achatarSubs(itens: any[]): any[] {
  return itens.flatMap((it) => (it.subs ? achatarSubs(it.subs) : [it]));
}

// Constrói o nó da árvore de sub-navegação recursivamente, para os itens que
// tiverem sub-abas próprias (mesmo caso acima).
function paraSubNavNode(it: any): SubNavNode {
  return { id: it.id, label: it.label, icon: it.icon, children: it.subs?.map(paraSubNavNode) };
}

// Lista achatada de sub-tipos (folhas), usada para saber qual formulário renderizar.
// Um grupo pode ter folhas direto (subs), estar sozinho (leaf) ou se ramificar em
// sub-grupos (grupos) — caso do Sanitário, que abre Curativa/Preventiva antes das folhas.
const TIPOS_LEAFS = TIPOS_GRUPOS.flatMap((g) =>
  g.grupos ? g.grupos.flatMap((sg) => achatarSubs(sg.subs)) : g.subs ? achatarSubs(g.subs) : [{ id: g.leaf!, label: g.label, icon: g.icon, desc: g.desc }]
);

export default function LancamentosPage() {
  const [sel, setSel] = useState("protocolo_iatf");
  const [sujo, setSujo] = useState(false);
  // Contas a pagar também permite compra de sêmen — em vez de duplicar o
  // fluxo, reusa o mesmo formulário/endpoint de Lançamentos > Animais >
  // Compra/Venda > Comprar sêmen (mesma CompraSemen + baixa/soma de doses).
  const [despesaCompraSemen, setDespesaCompraSemen] = useState(false);
  // Atalho vindo da Agenda (ex.: "Ir para Inseminação" de um lembrete D11 de protocolo IATF).
  useEffect(() => {
    const ir = new URLSearchParams(window.location.search).get("ir");
    if (ir && TIPOS_LEAFS.some((t) => t.id === ir)) setSel(ir);
  }, []);
  const trocarTipo = useCallback((novoId: string) => {
    if (novoId === sel) return;
    if (sujo && !window.confirm("Você tem certeza que quer sair dessa página? Os dados não salvos serão perdidos.")) return;
    setSujo(false);
    setSel(novoId);
  }, [sel, sujo]);
  // Redirecionamento pós-salvamento (ex.: Balanço de estoque → Financeiro com
  // "gerar movimentação financeira"): o balanço já foi salvo com sucesso, então
  // não é "sair com dados não salvos" — troca direto, sem o confirm de saída.
  const irParaFinanceiroAposEstoque = useCallback((leaf: "financeiro_despesa" | "financeiro_receita") => {
    setSujo(false);
    setSel(leaf);
  }, []);
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

  // Piloto do drill-down: a Sidebar desenha esta árvore (grupo → sub-grupo →
  // folha) no lugar da lista de módulos enquanto Lançamentos estiver aberto.
  const subNavTree: SubNavNode[] = useMemo(() => TIPOS_GRUPOS.map((g) => ({
    id: g.leaf ?? g.id, label: g.label, icon: g.icon,
    children: g.grupos
      ? g.grupos.map((sg) => ({ id: sg.id, label: sg.label, icon: sg.icon, children: sg.subs.map(paraSubNavNode) }))
      : g.subs?.map(paraSubNavNode),
  })), []);
  useSubNavRegister(useMemo(() => ({ tree: subNavTree, activeId: sel, onSelect: trocarTipo }), [subNavTree, sel, trocarTipo]));

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
          ) : sel === "preventivo_aplicacao" ? (
            <><strong style={{ color: "var(--text)" }}>Preventivo já grava de verdade.</strong> Escolha o evento preventivo (vacina/exame), o lote/categoria e marque os animais — registra o calendário e, se for vacina/tratamento, a aplicação com baixa de estoque. Exame não baixa estoque.</>
          ) : sel === "calendario_sanitario" ? (
            <><strong style={{ color: "var(--text)" }}>Calendário sanitário já grava de verdade.</strong> Cada regra recorrente vira pendência na Agenda (dá baixa) e aparece na aba Sanidade &gt; Preventivo, com filtro por data e por evento.</>
          ) : sel === "bst" ? (
            <><strong style={{ color: "var(--text)" }}>BST — somatotropina bovina.</strong> Vacas aptas e excluídas do dia, com a próxima visita de BST.</>
          ) : sel === "protocolo_sanitario" ? (
            <><strong style={{ color: "var(--text)" }}>Protocolo sanitário já grava de verdade.</strong> Cria um evento na Agenda por etapa (D1, D2...) — ao marcar "realizado", dá baixa automática do produto no Estoque.</>
          ) : sel === "secagem" ? (
            <><strong style={{ color: "var(--text)" }}>Secagem já grava de verdade.</strong> Ao salvar, sugere mover a vaca para o lote das secas — você confirma antes da mudança.</>
          ) : sel === "inducao_lactacao" ? (
            <><strong style={{ color: "var(--text)" }}>Indução de lactação já grava de verdade.</strong> Gera um evento por dia do cronograma na Agenda — medicamentos com baixa automática de estoque, e uma observação de manejo (implante, adaptação na ordenha, iniciar a ordenha) visível para o funcionário.</>
          ) : sel === "qualidade_leite" ? (
            <><strong style={{ color: "var(--text)" }}>Qualidade do leite já grava de verdade.</strong> Lance por uma vaca ou pelo tanque (todas as vacas em lactação) — alimenta o relatório e o gráfico de qualidade em Produção.</>
          ) : sel === "entrega_leite" ? (
            <><strong style={{ color: "var(--text)" }}>Venda mensal já grava de verdade.</strong> Compara o controle leiteiro projetado do mês, a receita do laticínio e o que foi de fato entregue.</>
          ) : sel === "parto" ? (
            <><strong style={{ color: "var(--text)" }}>Parto/nascimento já grava de verdade.</strong> Cadastra a cria e sugere o lote de mãe e cria (confirmação antes de mover). Colostragem/IgG da 1ª cria também gravam — veja em Sanidade &gt; Relatório sanitário de bezerras.</>
          ) : sel === "protocolo_iatf" ? (
            <><strong style={{ color: "var(--text)" }}>Protocolo IATF já grava de verdade.</strong> Agenda só os passos hormonais (D0/D7/D9/D11) na Agenda — a inseminação em si é lançada à parte, na sub-aba Inseminação.</>
          ) : sel === "inseminacao" ? (
            <><strong style={{ color: "var(--text)" }}>Inseminação já grava de verdade.</strong> Registra a cobertura/IA (cio natural ou vinda de um protocolo IATF já agendado) e calcula a ordem/intervalo de tentativas.</>
          ) : null}
        </p>
      </div>

      <div className="card" onChange={() => sel !== "exclusao" && setSujo(true)}>
        <div className="card-header mb-1 flex items-center gap-2"><tipo.icon size={14} /> {tipo.label}</div>
        <p style={{ color: "var(--text-muted)", fontSize: "0.78rem", margin: "0.4rem 0 1rem" }}>{tipo.desc}</p>
        {sel === "protocolo_iatf" && <FormProtocoloIatf animais={aptasServico} />}
        {sel === "inseminacao" && <FormInseminacao animais={aptasServico} />}
        {sel === "diagnostico" && <FormDiagnostico animais={animais} ultServico={ultServico} />}
        {sel === "parto" && <FormParto animais={animais} lotes={lotes} />}
        {sel === "controle" && <FormControle animais={animais} lotesLact={lotesLact} />}
        {sel === "pesagem" && <FormPesagemCorporal animais={animais} lotes={lotes} />}
        {sel === "secagem" && <FormSecagem animais={animais} estoque={estoque} produtos={produtosSanidade} />}
        {sel === "inducao_lactacao" && <FormInducaoLactacao animais={animais} />}
        {sel === "qualidade_leite" && <FormQualidadeLeite animais={animais} />}
        {sel === "entrega_leite" && <FormEntregaLeite />}
        {sel === "sanidade_aplicacao" && <FormSanidade animais={animais} lotes={lotes} estoque={estoque} produtos={produtosSanidade} />}
        {sel === "preventivo_aplicacao" && <FormPreventivoAplicacao animais={animais} lotes={lotes} estoque={estoque} />}
        {sel === "calendario_sanitario" && <FormCalendarioSanitario estoque={estoque} />}
        {sel === "bst" && <BstLancamentoView />}
        {sel === "protocolo_sanitario" && <FormProtocoloSanitario animais={animais} estoque={estoque} />}
        {sel === "financeiro_despesa" && (
          <>
            <div className="flex flex-wrap gap-2 mb-4">
              <button type="button" className={despesaCompraSemen ? "btn-secondary" : "btn-primary"} style={{ fontSize: "0.8rem" }}
                onClick={() => setDespesaCompraSemen(false)}>
                Lançamento genérico
              </button>
              <button type="button" className={despesaCompraSemen ? "btn-primary" : "btn-secondary"} style={{ fontSize: "0.8rem" }}
                onClick={() => setDespesaCompraSemen(true)}>
                Compra de sêmen
              </button>
            </div>
            {despesaCompraSemen ? (
              <>
                <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "1rem" }}>
                  Mesmo formulário de Lançamentos &gt; Animais &gt; Compra/Venda &gt; Comprar sêmen — a compra soma as
                  doses no Estoque de sêmen e gera a conta a pagar (3.01.02.01 — Sêmen) automaticamente.
                </p>
                <CompraSemenForm />
              </>
            ) : (
              <FormFinanceiro tipo="despesa" responsaveis={RESPONSAVEIS} onSujo={setSujo} />
            )}
          </>
        )}
        {sel === "financeiro_receita" && <FormFinanceiro tipo="receita" responsaveis={RESPONSAVEIS} onSujo={setSujo} />}
        {sel === "estoque" && <FormEstoque estoque={estoque} onIrParaFinanceiro={irParaFinanceiroAposEstoque} />}
        {sel === "mover_animais" && <MovimentarAnimais />}
        {sel === "comprar_animal" && <CompraVendaAnimalForm modo="compra" animais={animais} />}
        {sel === "comprar_semen" && <CompraSemenForm />}
        {sel === "vender_animal" && <CompraVendaAnimalForm modo="venda" animais={animais} />}
        {sel === "baixar_animal" && <BaixarAnimal />}
        {sel === "alimentacao_dieta" && <FormAlimentacaoDieta />}
        {sel === "exclusao" && <FormExclusao />}
      </div>
    </div>
  );
}
