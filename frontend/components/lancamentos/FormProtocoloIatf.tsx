"use client";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Check, AlertTriangle, X, Syringe } from "lucide-react";
import { adicionarAnimaisIatf, criarProtocoloIatf, fetchLancamentosIatf, fetchProtocolosIatfAtivos, fetchProtocolosIatfCadastrados, formatDate, removerAnimalIatf } from "@/lib/api";
import type { HormonioIatf, ProtocoloIatfMolde } from "@/lib/api";
import { AnimalRow } from "@/components/AnimalModal";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { EditorHormoniosIatf } from "@/components/EditorHormoniosIatf";
import { TabBar, EstadoVazio } from "@/components/ui";
import { Modal } from "@/components/Modal";
import { Campo, inputStyle, lbl, nota } from "@/components/lancamentos/comumForms";
import { SelectAnimal, addDias, IDADE_MIN_SERVICO_PADRAO } from "@/components/lancamentos/_shared";
import { ErroApi } from "@/lib/api";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";

// Mesma regra de fazenda/rules/nomenclatura_protocolo.py — só para pré-visualização;
// o nome de fato é sempre calculado no backend.
function nomeAutoIatf(d0: string, nomeBase: string, diaFinal: number): string {
  if (!d0) return "";
  const fmt = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "2-digit" });
  const dFinal = new Date(d0 + "T00:00:00"); dFinal.setDate(dFinal.getDate() + diaFinal);
  return `${nomeBase.toUpperCase()} - ${fmt(d0)} A ${fmt(dFinal.toISOString().slice(0, 10))} (D0 A D${diaFinal} - ${diaFinal + 1} DIAS)`;
}

// A inseminação acontece 2 dias depois da ÚLTIMA etapa de hormônio do
// protocolo — D9 → D11 no clássico (sem molde), D12 → D14 num molde
// D0/D8/D10/D12. Mesma regra de fazenda.rules.protocolo_iatf.dia_inseminacao.
const DIA_INSEMINACAO_PADRAO = 11;
function diaInseminacao(diasHormonio: number[]): number {
  return diasHormonio.length ? Math.max(...diasHormonio) + 2 : DIA_INSEMINACAO_PADRAO;
}
const HORMONIOS: Record<string, string[]> = {
  progesterona: ["Sincrogest", "Cidr"],
  benzoato: ["Sincrodiol"],
  buserelina: ["Sincroforte"],
  cloprostenol: ["Estron"],
  cipionato: ["SincroCP"],
};

type ProtocoloIatfAtivo = {
  lancamento_id: number; nome_protocolo: string; data_d0: string;
  animais: { numero_matriz: string; etapa_atual: string; data_etapa_atual: string | null; d0_confirmado?: boolean }[];
};

function TabelaAnimaisProtocolo({ p, removendo, remover }: {
  p: ProtocoloIatfAtivo; removendo: string | null; remover: (lancamentoId: number, numero: string) => void;
}) {
  const ord = useOrdenacao(p.animais);
  return (
    <table className="fazenda-table" style={{ margin: 0 }}>
      <thead><tr>
        <ThOrdenavel label="Nº" campo="numero_matriz" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
        <ThOrdenavel label="Etapa atual" campo="etapa_atual" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
        <ThOrdenavel label="Data" campo="data_etapa_atual" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
        <ThOrdenavel label="D0" campo="d0_confirmado" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
        <th></th>
      </tr></thead>
      <tbody>
        {ord.linhasOrdenadas.map((a) => (
          <tr key={a.numero_matriz}>
            <td style={{ fontWeight: 700 }}>{a.numero_matriz}</td>
            <td>{a.etapa_atual}</td>
            <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{a.data_etapa_atual ? formatDate(a.data_etapa_atual) : "—"}</td>
            <td>
              {a.d0_confirmado ? (
                <span title="D0 confirmado na Agenda" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.74rem", color: "var(--green-light)" }}>
                  <Check size={13} /> confirmado
                </span>
              ) : (
                <span title="D0 ainda não confirmado na Agenda — pode ter entrado no protocolo sem ter sido implantada" style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem", fontSize: "0.74rem", color: "var(--amber)" }}>
                  <AlertTriangle size={13} /> não confirmado
                </span>
              )}
            </td>
            <td style={{ textAlign: "right" }}>
              <button
                type="button" className="btn-ghost" style={{ color: "var(--red)", fontSize: "0.72rem", display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                disabled={removendo === `${p.lancamento_id}-${a.numero_matriz}`}
                onClick={() => remover(p.lancamento_id, a.numero_matriz)}
                title="Remover este animal do protocolo (corrige inclusão por engano)"
              >
                <X size={12} /> Remover
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ProtocolosIatfAtivos({ recarregarRef }: { recarregarRef: React.MutableRefObject<() => void> }) {
  const [ativos, setAtivos] = useState<ProtocoloIatfAtivo[] | null>(null);
  const [abertos, setAbertos] = useState<Set<number>>(new Set());
  const [removendo, setRemovendo] = useState<string | null>(null);
  const toggle = (id: number) => setAbertos((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const carregar = () => fetchProtocolosIatfAtivos().then(setAtivos).catch(() => setAtivos([]));
  useEffect(() => { carregar(); recarregarRef.current = carregar; }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function remover(lancamentoId: number, numero: string) {
    if (!window.confirm(`Remover ${numero} deste protocolo? Só é possível se nenhuma etapa dela já foi confirmada.`)) return;
    const chave = `${lancamentoId}-${numero}`;
    setRemovendo(chave);
    try {
      await removerAnimalIatf(lancamentoId, numero);
      await carregar();
    } catch (e: any) {
      window.alert(e.message || "Não foi possível remover este animal.");
    } finally {
      setRemovendo(null);
    }
  }

  if (!ativos || !ativos.length) {
    return <EstadoVazio icon={Syringe}>Nenhum protocolo IATF em andamento.</EstadoVazio>;
  }
  return (
    <div className="card" style={{ background: "var(--surface-2)" }}>
      <div className="card-header mb-2" style={{ background: "none", color: "var(--dourado-light)", padding: "0 0 0.3rem" }}>
        Protocolos IATF em andamento ({ativos.length})
      </div>
      <div className="space-y-2">
        {ativos.map((p) => {
          const aberto = abertos.has(p.lancamento_id);
          return (
            <div key={p.lancamento_id} style={{ border: "1px solid var(--border)", borderRadius: "var(--r-sm)", overflow: "hidden" }}>
              <button onClick={() => toggle(p.lancamento_id)} title={aberto ? "Clique para recolher os animais" : "Clique para ver os animais e etapas"} style={{ width: "100%", display: "flex", alignItems: "center", gap: "0.6rem", padding: "0.5rem 0.8rem", background: "var(--surface)", border: "none", color: "var(--text)", cursor: "pointer", textAlign: "left" }}>
                {aberto ? <ChevronDown size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} /> : <ChevronRight size={15} style={{ color: "var(--dourado-light)", flexShrink: 0 }} />}
                <span style={{ fontWeight: 700, fontSize: "0.85rem" }}>{p.nome_protocolo}</span>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>D0 {formatDate(p.data_d0)} — {p.animais.length} animal(is)</span>
              </button>
              {aberto && <TabelaAnimaisProtocolo p={p} removendo={removendo} remover={remover} />}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function FormProtocoloIatf({ animais, motivosInaptidao, idadeMinServico = IDADE_MIN_SERVICO_PADRAO, onSalvo }: {
  animais: AnimalRow[];
  // numero -> motivo de inaptidão (ver FormInseminacao e rules/aptidao.py).
  motivosInaptidao?: Map<string, string>;
  idadeMinServico?: number;
  onSalvo?: () => void;
}) {
  // Novo protocolo (cria um lançamento) ou adicionar animais a um já existente.
  const [modo, setModo] = useState<"novo" | "existente">("novo");
  const [podeForcar, setPodeForcar] = useState(false);
  const [emLote, setEmLote] = useState(false);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [um, setUm] = useState("");
  // Seleção "em lote" pode ser por animal (picker de sempre) ou por lote(s)
  // inteiro(s) — escolher o(s) lote(s) pré-seleciona seus animais, ainda
  // ajustável (todos/nenhum/individual) na janela de confirmação abaixo.
  const [vinculoProtocolo, setVinculoProtocolo] = useState<"animal" | "lote">("animal");
  const [lotesSelecionados, setLotesSelecionados] = useState<string[]>([]);
  const [selLote, setSelLote] = useState<Set<string>>(new Set());
  const [d0, setD0] = useState("");
  const [hormonios, setHormonios] = useState<HormonioIatf[]>([]);
  // Protocolos já lançados (para "existente").
  const [existentes, setExistentes] = useState<{ lancamento_id: number; nome_protocolo: string; data_d0: string; qtd_animais: number }[]>([]);
  const [existenteId, setExistenteId] = useState("");
  // Molde cadastrado (Central de Protocolos > Cadastro), opcional. Escolhido,
  // ele passa a MANDAR nos dias e nos hormônios — os dias são livres (um
  // molde pode ser D0/D8/D10/D12, não só D0/D7/D9), então o cronograma do
  // lançamento é o do molde, não mais o clássico fixo. Sem molde, nada muda:
  // hormônios digitados na hora, cronograma clássico D0/D7/D9/D11.
  const [moldes, setMoldes] = useState<ProtocoloIatfMolde[]>([]);
  const [moldeId, setMoldeId] = useState("");
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [sucesso, setSucesso] = useState<string | null>(null);
  const [mostrarRecap, setMostrarRecap] = useState(false);
  const recarregarAtivosRef = useRef(() => {});
  const toggle = (n: string) => setSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const toggleLote = (n: string) => setSelLote((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; });
  const codigosLotes = useMemo(
    () => Array.from(new Set(animais.map((a) => a.grupo_primario).filter((g): g is string => !!g))).sort(),
    [animais]
  );
  const animaisDoLote = useMemo(() => {
    const cods = new Set(lotesSelecionados);
    return animais.filter((a) => a.grupo_primario && cods.has(a.grupo_primario));
  }, [animais, lotesSelecionados]);
  useEffect(() => {
    setSelLote(new Set(animaisDoLote.map((a) => a.numero)));
  }, [lotesSelecionados.join("|")]); // eslint-disable-line react-hooks/exhaustive-deps

  const moldeSelecionado = moldes.find((m) => String(m.id) === moldeId) || null;
  const nomeBase = moldeSelecionado?.nome || "Protocolo IATF";
  const diasHormonioMolde = moldeSelecionado
    ? Array.from(new Set(moldeSelecionado.etapas.map((e) => e.dia))).sort((a, b) => a - b)
    : [];
  const diaFinal = moldeSelecionado ? diaInseminacao(diasHormonioMolde) : DIA_INSEMINACAO_PADRAO;
  const nomeProtocolo = nomeAutoIatf(d0, nomeBase, diaFinal);
  // Hormônios efetivamente enviados: do molde (etapa por etapa, direto —
  // mesma resolução de estoque por princípio ativo que já acontece na Agenda
  // ao confirmar o dia) quando um molde foi escolhido; digitados na hora
  // (EditorHormoniosIatf), como sempre, quando não.
  const hormoniosEfetivos = moldeSelecionado
    ? moldeSelecionado.etapas.map((e) => ({ dia: e.dia, produto: e.produto, dose: e.dose, unidade: e.unidade, via: e.via }))
    : hormonios;

  useEffect(() => { fetchProtocolosIatfCadastrados().then((ms) => setMoldes(ms.filter((m) => m.ativo))).catch(() => setMoldes([])); }, []);

  useEffect(() => {
    if (modo === "existente") fetchLancamentosIatf().then(setExistentes).catch(() => setExistentes([]));
  }, [modo]);

  const animaisAlvo = emLote ? Array.from(vinculoProtocolo === "lote" ? selLote : sel) : (um ? [um] : []);

  // Debitado por animal (ver EditorHormoniosIatf/backend) — soma por produto
  // para o recap de confirmação abaixo (P0: "Salvar" único sem recapitulação
  // de nº de animais/estoque a debitar, achado da crítica do lote 2).
  const resumoHormonios = useMemo(() => {
    const porProduto = new Map<string, { dose: number; unidade: string }>();
    hormoniosEfetivos.forEach((h) => {
      if (!h.dose) return;
      const atual = porProduto.get(h.produto) || { dose: 0, unidade: h.unidade || "" };
      atual.dose += h.dose;
      porProduto.set(h.produto, atual);
    });
    return Array.from(porProduto.entries()).map(([produto, { dose, unidade }]) => ({
      produto, doseTotalPorAnimal: dose, unidade, doseTotalGeral: dose * animaisAlvo.length,
    }));
  }, [hormoniosEfetivos, animaisAlvo.length]);

  function iniciarSalvar() {
    setErro(null); setSucesso(null); setPodeForcar(false);
    if (!animaisAlvo.length) { setErro(emLote ? "Selecione ao menos um animal." : "Selecione a matriz."); return; }
    if (modo === "novo") {
      if (!d0) { setErro("Informe a data do D0."); return; }
      setMostrarRecap(true);
      return;
    }
    if (!existenteId) { setErro("Selecione o protocolo existente."); return; }
    salvar();
  }

  async function salvar(forcar = false) {
    setErro(null); setSucesso(null); setPodeForcar(false);
    if (!animaisAlvo.length) { setErro(emLote ? "Selecione ao menos um animal." : "Selecione a matriz."); return; }
    setSalvando(true);
    try {
      if (modo === "existente") {
        if (!existenteId) { setErro("Selecione o protocolo existente."); setSalvando(false); return; }
        const r = await adicionarAnimaisIatf(Number(existenteId), animaisAlvo);
        setSucesso(`${r.adicionados} animal(is) adicionado(s) ao protocolo "${r.nome_protocolo}".`);
      } else {
        if (!d0) { setErro("Informe a data do D0."); setSalvando(false); return; }
        const r = await criarProtocoloIatf({ animais: animaisAlvo, data_d0: d0, protocolo_id: moldeId ? Number(moldeId) : null, hormonios: hormoniosEfetivos, forcar: forcar || undefined });
        // `criado: false` = o backend achou um lançamento ativo idêntico (mesmo
        // protocolo/D0/animais, ou mesmo D0/animais/hormônios num ad-hoc sem
        // molde) e reaproveitou em vez de duplicar — duplo clique ou retry da
        // fila offline. Sem este ramo a tela dizia "agendado ... — 0 eventos
        // na Agenda", que parece defeito (mesmo padrão de FormInducaoLactacao).
        setSucesso(r.criado === false
          ? (r.aviso || "Este protocolo já estava lançado para estes animais nesta data — nada foi duplicado.")
          : `Protocolo "${nomeProtocolo}" agendado para ${r.animais} animal(is) — ${r.eventos_criados} eventos na Agenda (D0 a D${diaFinal}).`);
      }
      setSel(new Set()); setUm("");
      recarregarAtivosRef.current();
      if (modo === "existente") fetchLancamentosIatf().then(setExistentes).catch(() => {});
      onSalvo?.();
    } catch (e: any) {
      setErro(e.message || "Erro ao lançar protocolo IATF");
      // 409 de aptidão confirmável — ver o mesmo tratamento em FormInseminacao.
      if (e instanceof ErroApi && e.status === 409 && e.confirmavel) setPodeForcar(true);
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mt-3">
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
        <ProtocolosIatfAtivos recarregarRef={recarregarAtivosRef} />
      </div>
      <div style={{ maxHeight: "calc(100vh - 220px)", overflowY: "auto", paddingRight: "0.4rem" }}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Campo label="Seleção">
          <label className="flex items-center gap-2" style={{ fontSize: "0.85rem", padding: "0.45rem 0" }}>
            <input type="checkbox" checked={emLote} onChange={(e) => setEmLote(e.target.checked)} /> Em lote (vários animais)
          </label>
        </Campo>
        {modo === "novo" ? (
          <>
            <Campo label="Protocolo cadastrado (opcional)">
              <select style={inputStyle} value={moldeId} onChange={(e) => setMoldeId(e.target.value)}>
                <option value="">Sem molde — informar hormônios abaixo</option>
                {moldes.map((m) => <option key={m.id} value={m.id}>{m.nome}</option>)}
              </select>
            </Campo>
            <Campo label="Data do D0"><input type="date" style={inputStyle} value={d0} onChange={(e) => setD0(e.target.value)} /></Campo>
            <Campo label="Nome do lançamento (automático)" full>
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
        {emLote ? (
          <>
            <TabBar<"animal" | "lote">
              abas={[
                { id: "animal", label: "Animal(is)", title: "Selecionar matrizes/novilhas individualmente" },
                { id: "lote", label: "Lote(s)", title: "Selecionar um ou mais lotes — pré-seleciona os animais de cada um, ajustável" },
              ]}
              ativa={vinculoProtocolo}
              onChange={setVinculoProtocolo}
            />
            {vinculoProtocolo === "animal" ? (
              <AnimalPickerModal
                animais={animais} selecionados={sel} onToggle={toggle}
                titulo="Escolher animais para o protocolo IATF"
                motivosInaptidao={motivosInaptidao}
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                ]}
              />
            ) : (
              <div style={{ marginTop: "0.5rem" }}>
                <LotePicker
                  opcoes={opcoesLoteDeAnimais(animais, codigosLotes)}
                  selecionados={lotesSelecionados}
                  onChange={setLotesSelecionados}
                  placeholder="Selecionar lote(s)…"
                />
                {lotesSelecionados.length > 0 && (
                  <div style={{ marginTop: "0.6rem" }}>
                    <AnimalPickerModal
                      animais={animaisDoLote} selecionados={selLote} onToggle={toggleLote}
                      titulo="Confirmar animais do(s) lote(s) selecionado(s)"
                      placeholder="Confirmar animais do(s) lote(s)…"
                      motivosInaptidao={motivosInaptidao}
                      // Sem isso, o lote entrava inteiro por padrão e o
                      // usuário só via quem foi incluído se lembrasse de
                      // clicar aqui — mesma disciplina de FormInseminacao.tsx.
                      abrirAoMudar={lotesSelecionados.join("|")}
                      colunas={[
                        { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                        { header: "Lote", render: (a) => a.grupo_primario || "—" },
                      ]}
                    />
                    <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.3rem" }}>
                      {selLote.size} de {animaisDoLote.length} animal(is) no(s) lote(s) selecionado(s) — "Selecionar todos"/"Limpar seleção" ou desmarque um a um na janela acima.
                    </p>
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          <SelectAnimal animais={animais} value={um} onChange={setUm} placeholder="Selecione a matriz…" motivosInaptidao={motivosInaptidao} />
        )}
      </div>
      <p style={nota}>
        A lista mostra todas as fêmeas — as <strong>inaptas em cinza</strong>, com o motivo (idade mínima de {idadeMinServico} meses,
        animal baixado ou a descartar). Isso só agenda o protocolo hormonal — a inseminação em si (D{diaFinal}) é
        lançada à parte, na sub-aba Inseminação.
      </p>

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
                  {moldeSelecionado ? (
                    <>
                      {diasHormonioMolde.map((dia) => {
                        const doDia = moldeSelecionado.etapas.filter((e) => e.dia === dia);
                        const descricao = doDia
                          .map((e) => `${e.dose ? `${e.dose}${e.unidade ? ` ${e.unidade}` : ""} ` : ""}${e.produto}`)
                          .join(" + ");
                        return <tr key={dia}><td style={{ fontWeight: 700 }}>D{dia}</td><td>{addDias(d0, dia)}</td><td>{descricao}</td></tr>;
                      })}
                      <tr><td style={{ fontWeight: 700, color: "var(--green-light)" }}>D{diaFinal}</td><td>{addDias(d0, diaFinal)}</td><td style={{ color: "var(--green-light)" }}>Inseminação (IATF)</td></tr>
                    </>
                  ) : (
                    <>
                      <tr><td style={{ fontWeight: 700 }}>D0</td><td>{addDias(d0, 0)}</td><td>Implante de progesterona + Benzoato de estradiol + Acetato de buserelina</td></tr>
                      <tr><td style={{ fontWeight: 700 }}>D7</td><td>{addDias(d0, 7)}</td><td>Cloprostenol</td></tr>
                      <tr><td style={{ fontWeight: 700 }}>D9</td><td>{addDias(d0, 9)}</td><td>Retirar implante + Cipionato de estradiol + Cloprostenol</td></tr>
                      <tr><td style={{ fontWeight: 700, color: "var(--green-light)" }}>D11</td><td>{addDias(d0, 11)}</td><td style={{ color: "var(--green-light)" }}>Inseminação (IATF)</td></tr>
                    </>
                  )}
                </tbody>
              </table>
            </div>
            <p style={nota}>
              {moldeSelecionado
                ? `Cronograma do molde "${moldeSelecionado.nome}" — a inseminação (D${diaFinal}) é sempre 2 dias depois da última etapa cadastrada. Ao salvar, cria estes eventos na Agenda para cada animal selecionado.`
                : "Ao salvar, cria os eventos D0/D7/D9/D11 na Agenda para cada animal selecionado."}
            </p>
          </div>
          {moldeSelecionado ? (
            <p style={{ ...nota, marginTop: "0.5rem" }}>
              Hormônios vindos do molde acima — para mudar dose, produto ou dia, edite o molde em <strong>Central de Protocolos › Cadastro</strong>.
              Ao confirmar cada dia na Agenda, você ainda escolhe o frasco em estoque do princípio ativo, como em qualquer protocolo.
            </p>
          ) : (
            <EditorHormoniosIatf onChange={setHormonios} />
          )}
        </>
      )}
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erro}</p>}
      {sucesso && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{sucesso}</p>}
      <div className="flex items-center gap-3 mt-4">
        <button className="btn-primary" onClick={iniciarSalvar} disabled={salvando}>{salvando ? "Salvando…" : "Salvar"}</button>
        {podeForcar && (
          <button className="btn-secondary" onClick={() => salvar(true)} disabled={salvando}
            title="Lança o protocolo assumindo a situação descrita acima">
            Confirmar e lançar mesmo assim
          </button>
        )}
      </div>
      </div>
      </div>

      {mostrarRecap && (
        <Modal title="Confirmar protocolo IATF" onClose={() => setMostrarRecap(false)} width="480px">
          <p style={{ fontSize: "0.85rem", marginBottom: "0.8rem" }}>
            <strong>{nomeProtocolo}</strong> será agendado para <strong>{animaisAlvo.length} animal(is)</strong>, com eventos D0 a D{diaFinal} na Agenda.
          </p>
          {resumoHormonios.length > 0 ? (
            <>
              <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.4rem" }}>Estoque a debitar (soma de todas as etapas × animais selecionados):</p>
              <table className="fazenda-table" style={{ margin: "0 0 0.8rem" }}>
                <thead><tr><th>Produto</th><th style={{ textAlign: "right" }}>Dose/animal</th><th style={{ textAlign: "right" }}>Total a debitar</th></tr></thead>
                <tbody>
                  {resumoHormonios.map((h) => (
                    <tr key={h.produto}>
                      <td style={{ fontSize: "0.82rem" }}>{h.produto}</td>
                      <td style={{ textAlign: "right", fontSize: "0.82rem" }}>{h.doseTotalPorAnimal} {h.unidade}</td>
                      <td style={{ textAlign: "right", fontWeight: 700, fontSize: "0.82rem" }}>{h.doseTotalGeral} {h.unidade}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginBottom: "0.8rem" }}>Nenhum hormônio com dose informada — o débito de estoque acontece ao confirmar cada etapa na Agenda.</p>
          )}
          <div className="flex justify-end gap-2">
            <button className="btn-ghost" onClick={() => setMostrarRecap(false)}>Cancelar</button>
            <button className="btn-primary" disabled={salvando} onClick={() => { setMostrarRecap(false); salvar(); }}>
              {salvando ? "Salvando…" : "Confirmar e salvar"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
