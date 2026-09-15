"use client";
// Base compartilhada dos 4 históricos derivados de /reproducao/servicos
// (Serviços, IAs, Diagnósticos, Perda de prenhez) — mesmos filtros da antiga
// sub-aba única "Reprodução" (animal, data/ciclo, ordem de parto/tentativa,
// método, diagnóstico), cada foco pré-filtrando/ajustando o que faz sentido.
import { useEffect, useMemo, useState, type Dispatch, type SetStateAction } from "react";
import { AlertTriangle, Filter, Pencil, Trash2, X } from "lucide-react";
import { fetchServicosAnalise, atualizarServico, fetchInseminadores, fetchAnimais, ehAdmin, confirmarExclusao } from "@/lib/api";
import { TabBar, MultiFiltro, Indicador, TelaSkeleton } from "@/components/ui";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { usePaginacao, Paginacao } from "@/components/Paginacao";
import { AnimalPickerModal } from "@/components/AnimalPickerModal";
import { LotePicker, opcoesLoteDeAnimais } from "@/components/LotePicker";
import { FiltroCiclo21Dias } from "@/components/FiltroCiclo21Dias";
import { codigoGrupo } from "@/components/lancamentos/comumForms";
import { ciclos21Dias } from "@/lib/ciclos21Dias";
import type { AnimalRow } from "@/components/AnimalModal";
import { estiloSexado } from "@/lib/constants";

export type Serv = {
  id: number;
  numero: string; raca: string; categoria: string;
  ordem_parto: number | null; ordem_tentativa: number | null;
  tipo_servico: string; touro: string; metodo_ia?: string;
  tipo_semen?: string | null; inseminador?: string | null;
  data: string | null; del_servico: number | null; data_d0?: string | null;
  diagnostico: string | null; diagnosticado: boolean; positivo: boolean; perda: boolean;
  // "reinseminacao" quando o NEGATIVO foi concluído pelo sistema (veio uma
  // nova tentativa para a matriz), e não porque alguém tocou a vaca.
  origem_diagnostico?: string | null;
  // 2º exame (reconfirmação) — distinto do toque acima (campo `diagnostico`).
  retoque?: boolean;
  data_reconfirmacao?: string | null;
  diagnostico_reconfirmacao?: string | null;
  data_perda: string | null; motivo_perda: string | null;
  usuario_nome?: string | null;
};

export type Foco = "todos" | "ias" | "diagnosticos" | "perdas";

const DIAG_COR: Record<string, string> = { POSITIVO: "var(--green-light)", NEGATIVO: "var(--red)", ABERTO: "var(--amber)" };
// "nao_informado" é o sentinela gravado pelo "Descartar" da pendência da
// Agenda (ver fazenda.rules.perda_prenhez) — a perda continua registrada,
// só o motivo que o usuário optou por não informar; por isso tem rótulo
// próprio aqui, distinto de "(sem motivo)" (motivo_perda null, ainda
// pendente de decisão — ver o fallback usado nos filtros abaixo).
const MOTIVO_LABEL: Record<string, string> = { aborto: "Aborto", natimorto: "Natimorto", outros: "Outros", nao_informado: "Não informado" };
const fmtDia = (iso: string | null) => (iso ? new Date(iso + "T00:00:00").toLocaleDateString("pt-BR") : "—");
const isoOf = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

const selStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem", width: "100%" };

// "Serviços" e "IAs" eram duas abas quase idênticas (a única diferença era o
// filtro de base excluindo monta natural) — viraram uma tela só, com o mesmo
// recorte disponível como um toggle interno em vez de duas rotas de aba.
const hojeISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export default function HistoricoServicos({ foco, titulo, descricao, animaisSel, setAnimaisSel }: {
  foco: Foco; titulo: string; descricao: string;
  // Seleção de animais controlada pelo container das sub-abas (app/reproducao/page.tsx
  // ou app/historico/page.tsx) — sobrevive à troca de sub-aba (Serviços/IAS ↔
  // Diagnósticos ↔ Perda de prenhez) porque é o mesmo state React, e reseta
  // sozinha quando o usuário sai da área (o container desmonta).
  animaisSel: Set<string>;
  setAnimaisSel: Dispatch<SetStateAction<Set<string>>>;
}) {
  const [regs, setRegs] = useState<Serv[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [animais, setAnimais] = useState<AnimalRow[]>([]);
  useEffect(() => { fetchAnimais().then(setAnimais).catch(() => {}); }, []);
  const [ini, setIni] = useState("");
  const [fim, setFim] = useState("");
  const [lotesSel, setLotesSel] = useState<string[]>([]);
  const [ordemParto, setOrdemParto] = useState<string[]>([]);
  const [ordemTentativa, setOrdemTentativa] = useState<string[]>([]);
  const [metodo, setMetodo] = useState<string[]>([]);
  const [diag, setDiag] = useState<string[]>([]);
  const [motivo, setMotivo] = useState<string[]>([]);
  const [modo, setModo] = useState<"data" | "ciclo">("data");
  // Ancoragem livre do filtro "Por ciclo" — mesma UI/semântica de Manejo do
  // Rebanho > Ciclo de 21 dias (ver FiltroCiclo21Dias), mas aqui só recorta os
  // registros já carregados por período em vez de chamar o backend de novo.
  const [ancoraCiclo, setAncoraCiclo] = useState(hojeISO());
  const [cicloModo, setCicloModo] = useState<"inicio" | "fim">("fim");
  const [nCiclosFiltro, setNCiclosFiltro] = useState(1);
  const [categoriaCiclo, setCategoriaCiclo] = useState("todas");
  // Só relevante quando foco === "todos" (tela unificada Serviços/IAS) — troca
  // dinamicamente entre mostrar tudo e só métodos de IA, no lugar da antiga
  // aba "IAs" separada (foco === "ias" continua suportado por trás, para quem
  // ainda passar esse foco diretamente).
  const [soIA, setSoIA] = useState(false);
  const iaOnly = foco === "ias" || (foco === "todos" && soIA);
  const admin = ehAdmin();

  const carregar = () => fetchServicosAnalise().then((d) => setRegs(d.servicos)).catch((e) => setError(e.message));
  useEffect(() => { carregar(); }, []);

  // Inseminadores cadastrados (Configurações > Cadastro > Pessoas, tipo
  // Inseminador) — o campo Inseminador só pode apontar pra alguém cadastrado,
  // não texto livre (evita nome digitado errado nunca batendo com ninguém).
  const [inseminadores, setInseminadores] = useState<string[]>([]);
  useEffect(() => { fetchInseminadores().then(setInseminadores).catch(() => {}); }, []);

  // Edição inline do serviço clicado — os campos mostrados variam conforme o
  // foco (Serviços/IAs editam data/tipo/touro/inseminador; Diagnósticos edita
  // o resultado; Perda de prenhez edita data/motivo da perda), todos no mesmo
  // registro Servico (ver PUT /reproducao/servicos/{id}).
  const [editando, setEditando] = useState<Serv | null>(null);
  const [editVals, setEditVals] = useState({
    data: "", tipoServico: "", touro: "", inseminador: "",
    dataDiagnostico: "", diagnostico: "", dataPerda: "", motivoPerda: "aborto",
  });
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);
  const [erroEdicao, setErroEdicao] = useState<string | null>(null);
  const [avisoExclusao, setAvisoExclusao] = useState<string | null>(null);

  const abrirEdicao = (s: Serv) => {
    setEditando(s);
    setEditVals({
      data: s.data || "", tipoServico: s.tipo_servico === "(sem tipo)" ? "" : s.tipo_servico,
      touro: s.touro === "(sem touro)" ? "" : s.touro, inseminador: s.inseminador === "(sem inseminador)" ? "" : (s.inseminador || ""),
      dataDiagnostico: s.data || "", diagnostico: s.diagnostico || "",
      dataPerda: s.data_perda || "", motivoPerda: s.motivo_perda || "aborto",
    });
    setErroEdicao(null);
  };

  const salvarEdicao = async () => {
    if (!editando) return;
    setSalvandoEdicao(true); setErroEdicao(null);
    try {
      if (foco === "diagnosticos") {
        await atualizarServico(editando.id, { data_diagnostico: editVals.dataDiagnostico || undefined, diagnostico: editVals.diagnostico || undefined });
      } else if (foco === "perdas") {
        await atualizarServico(editando.id, { data_perda_prenhez: editVals.dataPerda || undefined, motivo_perda_prenhez: editVals.motivoPerda || undefined });
      } else {
        await atualizarServico(editando.id, {
          data_servico: editVals.data || undefined, tipo_servico: editVals.tipoServico || undefined,
          reprodutor: editVals.touro || undefined, inseminador: editVals.inseminador || undefined,
        });
      }
      setEditando(null);
      carregar();
    } catch (e: any) {
      setErroEdicao(e.message || "Erro ao salvar");
    } finally {
      setSalvandoEdicao(false);
    }
  };

  // Passa pelo fluxo central e auditado de exclusão (POST /exclusoes/confirmar),
  // igual ao botão de frontend/app/sanidade/page.tsx:960-982 — admin exclui na
  // hora (e a dose de sêmen debitada por este serviço é estornada
  // automaticamente pelo motor genérico), operador vira uma solicitação
  // pendente de aprovação.
  const excluir = async (s: Serv) => {
    const msg = admin
      ? `Excluir o serviço de "${s.numero}" em ${fmtDia(s.data)}? Se houve baixa de dose de sêmen, ela será devolvida ao estoque. Isso não pode ser desfeito.`
      : `Solicitar a exclusão do serviço de "${s.numero}" em ${fmtDia(s.data)}? Um administrador precisa aprovar antes de ser excluída de fato.`;
    if (!window.confirm(msg)) return;
    setSalvandoEdicao(true); setErroEdicao(null); setAvisoExclusao(null);
    try {
      const r = await confirmarExclusao("servico", String(s.id));
      if (r.status === "excluido") {
        setEditando(null);
        carregar();
      } else {
        setAvisoExclusao("Solicitação de exclusão enviada — aguardando aprovação de um administrador.");
      }
    } catch (e: any) {
      setErroEdicao(e.message || "Erro ao excluir");
    } finally {
      setSalvandoEdicao(false);
    }
  };

  // Base do foco — aplicada ANTES dos filtros do usuário (não é opção, é o
  // recorte que define a aba: "IAs"/toggle "Só IA" nunca mostra monta natural,
  // "Diagnósticos" só mostra o que já foi diagnosticado, "Perda de prenhez"
  // só as perdas.
  const base = useMemo(() => {
    if (!regs) return [];
    if (iaOnly) return regs.filter((s) => s.metodo_ia !== "Monta natural");
    if (foco === "diagnosticos") return regs.filter((s) => s.diagnosticado);
    if (foco === "perdas") return regs.filter((s) => s.perda);
    return regs;
  }, [regs, foco, iaOnly]);

  // numero -> código de lote (2 dígitos), pro filtro de Lote abaixo — os
  // registros de Serviço não carregam grupo_primario, só o cadastro do animal tem.
  const loteDoNumero = useMemo(() => {
    const m = new Map<string, string | null>();
    animais.forEach((a) => m.set(a.numero, codigoGrupo(a.grupo_primario)));
    return m;
  }, [animais]);
  const codigosLotes = useMemo(
    () => Array.from(new Set(animais.map((a) => codigoGrupo(a.grupo_primario)).filter((c): c is string => !!c))).sort(),
    [animais]
  );

  // Janelas de ciclo de 21 dias — mesma âncora livre (início/fim) e aritmética
  // de Manejo do Rebanho > Ciclo de 21 dias (ver lib/ciclos21Dias.ts), mas
  // aqui só recorta localmente os registros já carregados por período —
  // não busca de novo no backend (que resolve elegibilidade/R1-R9, um
  // problema diferente do de só filtrar uma tabela por data).
  const ciclosFiltro = useMemo(
    () => ciclos21Dias(ancoraCiclo, cicloModo, nCiclosFiltro),
    [ancoraCiclo, cicloModo, nCiclosFiltro]
  );

  const janelas = useMemo(() => {
    if (modo !== "ciclo" || !ciclosFiltro.length) return null;
    return ciclosFiltro.map((c) => [isoOf(c.inicio), isoOf(c.fim)] as [string, string]);
  }, [modo, ciclosFiltro]);

  // Categoria (vaca/novilha) do filtro de ciclo — reaproveita o campo
  // `categoria` já achatado em cada serviço (categoria do animal na data do
  // serviço); "vaca" = já pariu alguma vez, mesmo critério usado no filtro
  // de categoria do backend (ver carregar_perfis_reprodutivos).
  const categoriaBate = (s: Serv) => {
    if (categoriaCiclo === "todas") return true;
    const c = (s.categoria || "").toLowerCase();
    return c.includes(categoriaCiclo);
  };

  const opc = (f: (s: Serv) => string | null) => {
    const set = new Set<string>(); base.forEach((s) => { const v = f(s); if (v) set.add(v); });
    return Array.from(set).sort((a, b) => (isNaN(+a) || isNaN(+b) ? a.localeCompare(b) : +a - +b));
  };

  const filtrados = useMemo(() => {
    return base.filter((s) =>
      (animaisSel.size === 0 || animaisSel.has(s.numero)) &&
      (!lotesSel.length || lotesSel.includes(loteDoNumero.get(s.numero) || "")) &&
      (modo === "data"
        ? (!ini || (s.data ? s.data >= ini : false)) && (!fim || (s.data ? s.data <= fim : false))
        : (!janelas || (s.data ? janelas.some(([a, b]) => s.data! >= a && s.data! <= b) : false)) && categoriaBate(s)) &&
      (!ordemParto.length || ordemParto.includes(String(s.ordem_parto))) &&
      (!ordemTentativa.length || ordemTentativa.includes(String(s.ordem_tentativa))) &&
      (iaOnly || !metodo.length || metodo.includes(s.metodo_ia || "")) &&
      (foco !== "diagnosticos" || !diag.length || diag.includes(s.diagnostico || "")) &&
      (foco !== "perdas" || !motivo.length || motivo.includes(s.motivo_perda || "(sem motivo)"))
    ).sort((a, b) => ((a.data || "") < (b.data || "") ? 1 : -1));
  }, [base, animaisSel, lotesSel, loteDoNumero, ini, fim, ordemParto, ordemTentativa, metodo, diag, motivo, modo, janelas, categoriaCiclo, foco, iaOnly]);

  const diagnosticados = filtrados.filter((s) => s.diagnosticado).length;
  const positivos = filtrados.filter((s) => s.positivo).length;
  const taxa = diagnosticados ? Math.round((1000 * positivos) / diagnosticados) / 10 : null;
  const perdas = filtrados.filter((s) => s.perda).length;

  const ordServ = useOrdenacao(filtrados);
  const pagServ = usePaginacao(ordServ.linhasOrdenadas);

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-lg font-bold">{titulo}</h2>
        <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>{descricao}</p>
      </div>

      {error && <div className="alert-critico mb-4"><AlertTriangle size={18} /><span>Sem dados: {error}. <a href="/configuracoes?aba=importar" style={{ color: "var(--dourado-light)", textDecoration: "underline" }}>Importe os dados reprodutivos</a>.</span></div>}
      {avisoExclusao && <p style={{ color: "var(--green-light)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{avisoExclusao}</p>}
      {!regs && !error && <TelaSkeleton kpis={0} />}

      {regs && <>
        <div className="card mb-4">
          <div className="card-header mb-3 flex items-center justify-between" style={{ flexWrap: "wrap", gap: "0.5rem" }}>
            <span className="flex items-center gap-2"><Filter size={14} /> Filtros</span>
            {/* Só existe quando foco === "todos" (tela unificada Serviços/IAS) —
                substitui a antiga aba "IAs" separada por um toggle na mesma tela. */}
            {foco === "todos" && (
              <label className="flex items-center gap-2" style={{ fontSize: "0.78rem", color: "var(--text-muted)", cursor: "pointer" }}>
                <input type="checkbox" checked={soIA} onChange={(e) => setSoIA(e.target.checked)} /> Só IA (excluir monta natural)
              </label>
            )}
          </div>
          <TabBar
            abas={[
              { id: "data", label: "Por data", title: "Filtrar por intervalo de datas (de/até)" },
              { id: "ciclo", label: "Por ciclo (21 dias)", title: "Filtrar por ciclo reprodutivo — janelas de 21 dias" },
            ] as const}
            ativa={modo}
            onChange={setModo}
          />
          <div className="mt-3">
            <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Lote(s)</label>
            <LotePicker opcoes={opcoesLoteDeAnimais(animais, codigosLotes)} selecionados={lotesSel} onChange={setLotesSel} placeholder="Todos os lotes" />
          </div>
          {modo === "ciclo" && (
            <div className="mt-3">
              <FiltroCiclo21Dias
                ancora={ancoraCiclo} setAncora={setAncoraCiclo}
                modo={cicloModo} setModo={setCicloModo}
                nCiclos={nCiclosFiltro} setNCiclos={setNCiclosFiltro}
                categoria={categoriaCiclo} setCategoria={setCategoriaCiclo}
              />
            </div>
          )}
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 mt-3">
            <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Animal(is)</label>
              <AnimalPickerModal
                animais={animais} selecionados={animaisSel}
                onToggle={(n) => setAnimaisSel((p) => { const s = new Set(p); s.has(n) ? s.delete(n) : s.add(n); return s; })}
                placeholder="Todos" titulo="Filtrar por animal(is)"
                ocultarFiltroLote
                colunas={[
                  { header: "Nº", render: (a) => <span style={{ fontWeight: 700 }}>{a.numero}</span> },
                  { header: "Lote", render: (a) => a.grupo_primario || "—" },
                  { header: "Categoria", render: (a) => a.categoria_abrev || a.categoria_completa || "—" },
                ]}
              /></div>
            {modo === "data" && (
              <>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>De</label><input type="date" style={selStyle} value={ini} onChange={(e) => setIni(e.target.value)} /></div>
                <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Até</label><input type="date" style={selStyle} value={fim} onChange={(e) => setFim(e.target.value)} /></div>
              </>
            )}
            <MultiFiltro label="Ordem de parto" opcoes={opc((s) => s.ordem_parto === null ? null : String(s.ordem_parto))} selecionados={ordemParto} onChange={setOrdemParto} />
            <MultiFiltro label="Ordem de tentativa" opcoes={opc((s) => s.ordem_tentativa === null ? null : String(s.ordem_tentativa))} selecionados={ordemTentativa} onChange={setOrdemTentativa} />
            {!iaOnly && <MultiFiltro label="Método" opcoes={opc((s) => s.metodo_ia || null)} selecionados={metodo} onChange={setMetodo} />}
            {foco === "diagnosticos" && <MultiFiltro label="Diagnóstico" opcoes={["POSITIVO", "NEGATIVO"]} selecionados={diag} onChange={setDiag} />}
            {foco === "perdas" && <MultiFiltro label="Motivo" opcoes={opc((s) => s.motivo_perda || "(sem motivo)")} selecionados={motivo} onChange={setMotivo} formatar={(m) => MOTIVO_LABEL[m] || m} />}
          </div>
        </div>

        {foco === "perdas" ? (
          <div className="grid grid-cols-1 gap-2 mb-4">
            <Indicador categoria="reprodutivo" valor={filtrados.length} rotulo="Perdas" />
          </div>
        ) : (
          // Concepção/serviço é o número que mede se o programa reprodutivo está
          // funcionando — vira a métrica-âncora em vez de competir em pé de
          // igualdade com Registros/Prenhezes/Perdas, que continuam do lado, menores.
          <div className="card mb-4" style={{ padding: "1.1rem 1.3rem" }}>
            <div style={{ fontSize: ".68rem", fontWeight: 700, letterSpacing: ".13em", textTransform: "uppercase", color: "var(--text-muted)" }}>Concepção / serviço</div>
            <div style={{ fontFamily: "var(--font-heading)", fontSize: "2.6rem", fontWeight: 800, lineHeight: 1, color: "var(--blue)", marginTop: ".25rem", fontVariantNumeric: "tabular-nums" }}>
              {taxa === null ? "—" : `${taxa}%`}
            </div>
            <div style={{ display: "flex", gap: "1.6rem", marginTop: ".9rem", paddingTop: ".8rem", borderTop: "1px solid var(--border)", flexWrap: "wrap" }}>
              <div>
                <div style={{ fontSize: "1.05rem", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>{filtrados.length}</div>
                <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Registros</div>
              </div>
              <div>
                <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--green-light)", fontVariantNumeric: "tabular-nums" }}>{positivos}</div>
                <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Prenhezes</div>
              </div>
              {foco === "todos" && (
                <div>
                  <div style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--amber)", fontVariantNumeric: "tabular-nums" }}>{perdas}</div>
                  <div style={{ fontSize: ".62rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: ".06em", marginTop: ".1rem" }}>Perdas de prenhez</div>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="card">
          <div className="card-header mb-3 flex items-center justify-between"><span>{titulo}</span><span style={{ fontSize: "0.8rem", color: "var(--dourado-light)", fontWeight: 400 }}>{filtrados.length}</span></div>
          <div className="overflow-x-auto" style={{ maxHeight: "560px" }}>
            <table className="fazenda-table">
              <thead><tr>
                <ThOrdenavel label="Matriz" campo="numero" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Data serviço" campo="data" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Tipo" campo="tipo_servico" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Método" campo="metodo_ia" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Diagnóstico" campo="diagnostico" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                <ThOrdenavel label="Ord. parto" campo="ordem_parto" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} alinhar="right" />
                <ThOrdenavel label="Tentativa" campo="ordem_tentativa" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} alinhar="right" />
                <ThOrdenavel label="DEL" campo="del_servico" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} alinhar="right" />
                <ThOrdenavel label="Touro" campo="touro" coluna={ordServ.coluna} dir={ordServ.dir} ordenar={ordServ.ordenar} />
                {foco === "perdas" && <><th style={{ textAlign: "left" }}>Data da perda</th><th style={{ textAlign: "left" }}>Motivo</th></>}
                {admin && <th style={{ textAlign: "left" }}>Usuário</th>}
              </tr></thead>
              <tbody>
                {pagServ.linhasPagina.map((s) => (
                  <tr key={`${s.numero}-${s.data}`} onClick={() => abrirEdicao(s)}
                    style={{ ...estiloSexado(s.tipo_semen), cursor: "pointer" }}
                    title={s.tipo_semen === "sexado" ? "Inseminação com sêmen sexado — clique para editar" : "Clique para editar"}>
                    <td style={{ fontWeight: 700 }}>{s.numero}</td>
                    <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(s.data)}</td>
                    <td style={{ fontSize: "0.78rem" }}>{s.tipo_servico}</td>
                    <td style={{ fontSize: "0.78rem" }}>{s.metodo_ia || "—"}</td>
                    <td>
                      <span style={{ color: DIAG_COR[s.diagnostico || "ABERTO"] || "var(--text-muted)", fontWeight: 600, fontSize: "0.78rem" }}>{s.diagnostico || "ABERTO"}</span>
                      {s.origem_diagnostico === "reinseminacao" && (
                        <span
                          title="Concluído pelo sistema: a matriz foi inseminada de novo, então este serviço não pegou. Não houve exame."
                          style={{ marginLeft: "0.3rem", fontSize: "0.62rem", color: "var(--text-muted)", fontWeight: 400 }}
                        >
                          (auto)
                        </span>
                      )}
                      {s.diagnostico_reconfirmacao ? (
                        <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", marginTop: "0.15rem" }}>
                          Reconfirmação:{" "}
                          <span style={{ color: DIAG_COR[s.diagnostico_reconfirmacao] || "var(--text-muted)", fontWeight: 600 }}>
                            {s.diagnostico_reconfirmacao}
                          </span>
                          {s.data_reconfirmacao ? ` em ${fmtDia(s.data_reconfirmacao)}` : ""}
                        </div>
                      ) : s.retoque ? (
                        <div style={{ fontSize: "0.68rem", color: "var(--amber)", marginTop: "0.15rem" }}>Aguardando retoque</div>
                      ) : null}
                    </td>
                    <td style={{ textAlign: "right" }}>{s.ordem_parto ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{s.ordem_tentativa ?? "—"}</td>
                    <td style={{ textAlign: "right" }}>{s.del_servico ?? "—"}</td>
                    <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.touro}</td>
                    {foco === "perdas" && <>
                      <td style={{ whiteSpace: "nowrap", fontSize: "0.78rem" }}>{fmtDia(s.data_perda)}</td>
                      <td style={{ fontSize: "0.78rem" }}>{s.motivo_perda ? (MOTIVO_LABEL[s.motivo_perda] || s.motivo_perda) : "—"}</td>
                    </>}
                    {admin && <td style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{s.usuario_nome ?? "—"}</td>}
                  </tr>
                ))}
              </tbody>
            </table>
            <Paginacao pagina={pagServ.pagina} totalPaginas={pagServ.totalPaginas} totalLinhas={pagServ.totalLinhas}
              tamanhoPagina={pagServ.tamanhoPagina} onMudarPagina={pagServ.setPagina} onMudarTamanho={pagServ.setTamanhoPagina} />
          </div>
        </div>
      </>}

      {editando && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 80, padding: "1rem" }}>
          <div className="card" onClick={(e) => e.stopPropagation()} style={{ width: "420px", maxWidth: "95vw" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="card-header" style={{ margin: 0, display: "flex", alignItems: "center", gap: "0.4rem" }}><Pencil size={15} /> Editar — matriz {editando.numero}</div>
              <button onClick={() => setEditando(null)} className="btn-ghost" aria-label="Fechar"><X size={16} /></button>
            </div>
            <div className="grid grid-cols-1 gap-3">
              {foco === "diagnosticos" ? (
                <>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Data do diagnóstico</label>
                    <input type="date" style={selStyle} value={editVals.dataDiagnostico} onChange={(e) => setEditVals((v) => ({ ...v, dataDiagnostico: e.target.value }))} /></div>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Diagnóstico</label>
                    <select style={selStyle} value={editVals.diagnostico} onChange={(e) => setEditVals((v) => ({ ...v, diagnostico: e.target.value }))}>
                      <option value="">—</option><option value="POSITIVO">Positivo</option><option value="NEGATIVO">Negativo</option><option value="INDEFINIDO">Indefinido</option>
                    </select></div>
                </>
              ) : foco === "perdas" ? (
                <>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Data da perda</label>
                    <input type="date" style={selStyle} value={editVals.dataPerda} onChange={(e) => setEditVals((v) => ({ ...v, dataPerda: e.target.value }))} /></div>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Motivo</label>
                    <select style={selStyle} value={editVals.motivoPerda} onChange={(e) => setEditVals((v) => ({ ...v, motivoPerda: e.target.value }))}>
                      <option value="aborto">Aborto</option><option value="natimorto">Natimorto</option><option value="outros">Outros</option>
                    </select></div>
                </>
              ) : (
                <>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Data do serviço</label>
                    <input type="date" style={selStyle} value={editVals.data} onChange={(e) => setEditVals((v) => ({ ...v, data: e.target.value }))} /></div>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Tipo de serviço</label>
                    <input style={selStyle} value={editVals.tipoServico} onChange={(e) => setEditVals((v) => ({ ...v, tipoServico: e.target.value }))} placeholder="ex.: IATF, Monta natural…" /></div>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Touro / sêmen</label>
                    <input style={selStyle} value={editVals.touro} onChange={(e) => setEditVals((v) => ({ ...v, touro: e.target.value }))} /></div>
                  <div><label style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Inseminador</label>
                    <select style={selStyle} value={editVals.inseminador} onChange={(e) => setEditVals((v) => ({ ...v, inseminador: e.target.value }))}>
                      <option value="">—</option>
                      {/* Valor já salvo que não bate com nenhum inseminador cadastrado hoje
                          (ex.: pessoa desativada depois) — mantém visível pra não sumir sozinho. */}
                      {editVals.inseminador && !inseminadores.includes(editVals.inseminador) && (
                        <option value={editVals.inseminador}>{editVals.inseminador} (não cadastrado)</option>
                      )}
                      {inseminadores.map((nome) => <option key={nome} value={nome}>{nome}</option>)}
                    </select></div>
                </>
              )}
            </div>
            {erroEdicao && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginTop: "0.6rem" }}>{erroEdicao}</p>}
            <div className="flex items-center justify-between gap-3 mt-4">
              <div className="flex items-center gap-3">
                <button className="btn-primary" onClick={salvarEdicao} disabled={salvandoEdicao}>{salvandoEdicao ? "Salvando…" : "Salvar"}</button>
                <button className="btn-ghost" onClick={() => setEditando(null)}>Cancelar</button>
              </div>
              <button
                className="btn-ghost"
                style={{ color: "var(--red)", display: "flex", alignItems: "center", gap: "0.3rem" }}
                onClick={() => excluir(editando)}
                disabled={salvandoEdicao}
              >
                <Trash2 size={14} /> Excluir
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
