"use client";
import { useEffect, useMemo, useState } from "react";
import { Droplets, AlertTriangle, Check, Ban, X as XIcon } from "lucide-react";
import { aplicarBstLote, marcarInaptaBst, fetchEstoque, formatDate } from "@/lib/api";
import { usePessoasAtivas } from "@/lib/usePessoasAtivas";
import { Modal } from "@/components/Modal";
import { MultiFiltro } from "@/components/ui";
import { PainelAjustarProximaAplicacaoBst } from "@/components/AjusteProximaAplicacaoBst";
import { useOrdenacao, ThOrdenavel } from "@/components/Ordenavel";
import { EstoquePicker } from "@/components/EstoquePicker";
import { ExportarBotoes } from "@/components/ExportarBotoes";
import type { ColunaExport } from "@/lib/export";

// Mesmo padrão de nome usado no backend para reconhecer um item de estoque
// como BST (ver MARCADORES_BST em fazenda/api/routers/agenda.py) — não há
// categoria/princípio ativo dedicado ainda, então os dois lados casam pelo
// nome do produto.
const MARCADORES_BST = /\b(lactotropin|boostin|bst|somatotropina)\b/i;

const th: React.CSSProperties = { textAlign: "left", padding: "0.4rem 0.6rem", fontSize: "0.72rem", textTransform: "uppercase", color: "var(--text-muted)", borderBottom: "1px solid var(--border)" };
const td: React.CSSProperties = { padding: "0.4rem 0.6rem", fontSize: "0.82rem", borderBottom: "1px solid var(--border)" };

/**
 * Tabelas de status do BST (Aptas / Incluir no próximo BST / Inaptas) — só
 * leitura, sem checkbox nem ação. Usada em Produção › Relatórios de BST
 * (que não lança mais aplicação, só reporta) e reaproveitada como miolo de
 * `PainelLancarBst` (que adiciona a seleção/ações por cima).
 */
export function TabelasStatusBst({ agenda, selecionados, onToggle }: { agenda: any; selecionados?: Set<string>; onToggle?: (numero: string) => void }) {
  const aptas: any[] = agenda?.bst_elegiveis ?? [];
  const nuncaAplicadas: any[] = agenda?.bst_nunca_aplicados ?? [];
  const inaptas: any[] = agenda?.bst_excluidos ?? [];
  // Filtro "ver DEL de hoje / DEL projetado" (pedido do usuário — antes as
  // duas colunas ficavam sempre lado a lado, sem opção de focar só numa).
  // "ambos" (padrão) mantém o comportamento anterior.
  const [verDel, setVerDel] = useState<"ambos" | "atual" | "projetado">("ambos");

  const Tabela = ({ titulo, lista, cor }: { titulo: string; lista: any[]; cor: string }) => {
    const ord = useOrdenacao(lista);
    return (
    <div className="card">
      <div className="card-header mb-2 flex items-center gap-2" style={{ color: cor }}><Droplets size={14} /> {titulo} ({lista.length})</div>
      {!lista.length ? <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nenhum animal nesta condição.</p> : (
        <div style={{ overflowX: "auto", maxHeight: "280px" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>
              {onToggle && <th style={th}></th>}
              <th style={th}></th>
              <ThOrdenavel label="Nº" campo="numero_matriz" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              <ThOrdenavel label="Lote" campo="grupo" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} />
              {verDel !== "projetado" && (
                <ThOrdenavel label="DEL atual" campo="del_atual" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
              )}
              {verDel !== "atual" && (
                <ThOrdenavel label="DEL projetado" campo="del_projetado" coluna={ord.coluna} dir={ord.dir} ordenar={ord.ordenar} alinhar="right" />
              )}
              <th style={th}>Obs.</th>
            </tr></thead>
            <tbody>{ord.linhasOrdenadas.map((b: any) => (
              <tr key={b.numero_matriz}>
                {onToggle && <td style={td}><input type="checkbox" checked={!!selecionados?.has(b.numero_matriz)} onChange={() => onToggle(b.numero_matriz)} /></td>}
                <td style={td}>
                  {b.requer_reanalise && (
                    <span title="Retirada do BST — revisar antes de incluir de novo" style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: "var(--amber)" }} />
                  )}
                </td>
                <td style={{ ...td, fontWeight: 700 }}>{b.numero_matriz}</td>
                <td style={td}>{b.grupo || "—"}</td>
                {verDel !== "projetado" && <td style={{ ...td, textAlign: "right" }}>{b.del_atual ?? "—"}</td>}
                {verDel !== "atual" && <td style={{ ...td, textAlign: "right" }}>{b.del_projetado ?? "—"}</td>}
                <td style={{ ...td, color: "var(--text-muted)", fontSize: "0.75rem" }}>
                  {b.requer_reanalise ? (b.motivo_exclusao || "Retirada do BST — revisar") : lista === nuncaAplicadas ? "Nunca aplicada — apta na próxima" : "—"}
                </td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </div>
    );
  };

  const opcoesVerDel: [typeof verDel, string][] = [
    ["ambos", "Ambos"], ["atual", "Só DEL atual"], ["projetado", "Só DEL projetado"],
  ];

  // Exportação (PDF/Excel) das 3 listas juntas — mesma tabela usada tanto na
  // Agenda (card de BST) quanto em Lançamentos > Produção > BST e em
  // Produção > Relatórios de BST, já que todas renderizam via este
  // componente. "Situação" identifica de qual das 3 tabelas a linha veio.
  const colunasExport: ColunaExport[] = [
    { header: "Nº", key: "numero_matriz" },
    { header: "Lote", key: "grupo" },
    { header: "DEL atual", key: "del_atual" },
    { header: "DEL projetado", key: "del_projetado" },
    { header: "Situação", key: "situacao" },
    { header: "Obs.", key: "obs" },
  ];
  const linhasExport = useMemo(() => [
    ...aptas.map((b) => ({ ...b, situacao: "Apta", obs: "" })),
    ...nuncaAplicadas.map((b) => ({ ...b, situacao: "Incluir no próximo BST", obs: "Nunca aplicada — apta na próxima" })),
    ...inaptas.map((b) => ({ ...b, situacao: "Inapta", obs: b.requer_reanalise ? (b.motivo_exclusao || "Retirada do BST — revisar") : "" })),
  ], [aptas, nuncaAplicadas, inaptas]);

  return (
    <div className="space-y-2">
      <p style={{ fontSize: "0.76rem", color: "var(--text-muted)" }}>
        "DEL atual" é o DEL de hoje; "DEL projetado" é o DEL que o animal terá na data da próxima aplicação de BST
        {agenda?.proxima_visita_bst ? <> (<strong>{formatDate(agenda.proxima_visita_bst)}</strong>)</> : null} — é essa
        projeção que decide se a vaca chega apta na hora certa.
      </p>
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>Ver:</span>
          <div className="flex gap-1">
            {opcoesVerDel.map(([valor, rotulo]) => (
              <button key={valor} type="button" onClick={() => setVerDel(valor)}
                className={verDel === valor ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem" }}>
                {rotulo}
              </button>
            ))}
          </div>
        </div>
        <ExportarBotoes titulo="BST — DEL atual e projetado" colunas={colunasExport} linhas={linhasExport} nomeArquivoBase="bst_del" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Tabela titulo="BST — Aptas" lista={aptas} cor="var(--green-light)" />
        <Tabela titulo="BST — Incluir no próximo BST" lista={nuncaAplicadas} cor="var(--amber)" />
        <Tabela titulo="BST — Inaptas p/ próxima aplicação" lista={inaptas} cor="var(--red)" />
      </div>
    </div>
  );
}

/**
 * Painel de LANÇAMENTO de BST — seleção de animais direto nas 3 tabelas de
 * status (via `TabelasStatusBst`), com ação "aplicar" (data-aware: pergunta
 * agendar vs. aplicar+baixa, capturando produto/dose/unidade/responsável) e
 * ação distinta "marcar como inapta" (não pode ser combinada com aplicar no
 * mesmo lançamento).
 *
 * Exclusivo de Lançamentos › Produção › BST — Produção › Relatórios de BST
 * usa só `TabelasStatusBst` (leitura) + o histórico consolidado, sem poder
 * lançar aplicação por ali (ver `RelatoriosBstView` em app/producao/page.tsx).
 *
 * "Incluir no próximo BST" reúne: (1) nunca aplicadas que estarão aptas na
 * data da próxima aplicação, e (2) animais retirados do BST (`excluir_bst`)
 * — estes últimos vêm com `requer_reanalise: true` e ganham a bolinha
 * amarela na tabela, sinalizando que precisam ser reavaliados antes de
 * entrar de novo no lançamento.
 */
type DadosAplicarBst = {
  numeros_matriz: string[]; data_aplicacao: string; aplicado?: boolean; produto?: string;
  dose?: number | null; unidade?: string | null; responsavel?: string; dose_por_animal?: boolean;
};
type DadosMarcarInaptaBst = { numeros_matriz: string[]; inapta?: boolean };

export function PainelLancarBst({
  agenda, onAtualizado, aplicarBst = aplicarBstLote, marcarInapta: marcarInaptaFn = marcarInaptaBst,
}: {
  agenda: any; onAtualizado: () => void;
  aplicarBst?: (dados: DadosAplicarBst) => Promise<unknown>;
  marcarInapta?: (dados: DadosMarcarInaptaBst) => Promise<unknown>;
}) {
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [lotesFiltro, setLotesFiltro] = useState<string[]>([]);
  const [dataAplicacao, setDataAplicacao] = useState(() => new Date().toISOString().slice(0, 10));
  const [produto, setProduto] = useState("Lactotropin");
  const [dose, setDose] = useState("");
  // A dose informada é de UM animal (padrão — igual sempre foi) ou o TOTAL
  // já aplicado ao lote inteiro? Comunicar isso certo pro backend evita
  // baixar o estoque errado (total tratado como se fosse por animal, N
  // vezes maior que o real) e confundir o relatório por animal.
  const [dosePorAnimal, setDosePorAnimal] = useState(true);
  const [unidade, setUnidade] = useState("unidade");
  const [responsavel, setResponsavel] = useState("");
  const [confirmacao, setConfirmacao] = useState<"agendar" | "aplicar" | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [estoqueItens, setEstoqueItens] = useState<any[]>([]);
  const { pessoas: pessoasAtivas } = usePessoasAtivas();

  useEffect(() => {
    fetchEstoque().then((d) => setEstoqueItens(d.itens || [])).catch(() => setEstoqueItens([]));
  }, []);

  // Itens de estoque reconhecidos como BST (mesmo critério do backend) —
  // Lactotropin/Boostin aparecem aqui só se já cadastrados, mas qualquer
  // outro produto com nome batendo no padrão também entra (ex.: genérico
  // cadastrado pelo usuário em Configurações > Cadastro > Estoque).
  const itensBst = useMemo(
    () => estoqueItens.filter((i) => MARCADORES_BST.test(i.nome || "")),
    [estoqueItens]
  );

  const toggle = (numero: string) => setSelecionados((prev) => {
    const novo = new Set(prev);
    novo.has(numero) ? novo.delete(numero) : novo.add(numero);
    return novo;
  });

  const executarAplicar = async () => {
    setOcupado(true); setErro(null);
    try {
      await aplicarBst({
        numeros_matriz: Array.from(selecionados), data_aplicacao: dataAplicacao, aplicado: true,
        produto: produto.trim() || "Lactotropin", dose: dose ? Number(dose) : null, unidade: unidade || null,
        responsavel: responsavel.trim() || undefined, dose_por_animal: dosePorAnimal,
      });
      setSelecionados(new Set());
      onAtualizado();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); setConfirmacao(null); }
  };

  const marcarInapta = async () => {
    setOcupado(true); setErro(null);
    try {
      await marcarInaptaFn({ numeros_matriz: Array.from(selecionados), inapta: true });
      setSelecionados(new Set());
      onAtualizado();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  };

  const reverterInapta = async () => {
    setOcupado(true); setErro(null);
    try {
      await marcarInaptaFn({ numeros_matriz: Array.from(selecionados), inapta: false });
      setSelecionados(new Set());
      onAtualizado();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  };

  const futura = dataAplicacao > new Date().toISOString().slice(0, 10);
  const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "var(--r-sm)", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

  const lotesDisponiveis = useMemo(() => {
    const todos: any[] = [
      ...(agenda?.bst_elegiveis ?? []),
      ...(agenda?.bst_nunca_aplicados ?? []),
      ...(agenda?.bst_excluidos ?? []),
    ];
    return Array.from(new Set(todos.map((b) => b.grupo).filter(Boolean))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
  }, [agenda]);

  const agendaFiltrada = useMemo(() => {
    if (!lotesFiltro.length) return agenda;
    const filtro = (lista: any[]) => (lista ?? []).filter((b) => lotesFiltro.includes(b.grupo));
    return {
      ...agenda,
      bst_elegiveis: filtro(agenda?.bst_elegiveis),
      bst_nunca_aplicados: filtro(agenda?.bst_nunca_aplicados),
      bst_excluidos: filtro(agenda?.bst_excluidos),
    };
  }, [agenda, lotesFiltro]);

  return (
    <div className="space-y-4">
      {erro && <div className="alert-critico"><AlertTriangle size={16} /><span>{erro}</span></div>}

      <div className="card">
        <PainelAjustarProximaAplicacaoBst
          proximaVisitaBst={agenda?.proxima_visita_bst ?? null}
          intervaloBstDias={agenda?.intervalo_bst ?? null}
          onAjustado={onAtualizado}
        />
      </div>

      <div style={{ maxWidth: "280px" }}>
        <MultiFiltro label="Filtrar por lote" opcoes={lotesDisponiveis} selecionados={lotesFiltro} onChange={setLotesFiltro} />
      </div>

      <div className="flex items-center gap-2 flex-wrap">
        {([
          ["aptas", "Selecionar todas aptas", agendaFiltrada?.bst_elegiveis],
          ["para incluir", "Selecionar todas para incluir", agendaFiltrada?.bst_nunca_aplicados],
          ["inaptas", "Selecionar todas inaptas", agendaFiltrada?.bst_excluidos],
        ] as [string, string, any[] | undefined][]).map(([nomeCategoria, rotulo, lista]) => {
          const numeros = (lista ?? []).map((b) => b.numero_matriz as string);
          const todasMarcadas = numeros.length > 0 && numeros.every((n) => selecionados.has(n));
          return (
            <button key={rotulo} type="button" className={todasMarcadas ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.76rem" }}
              disabled={!numeros.length}
              onClick={() => setSelecionados((prev) => {
                const novo = new Set(prev);
                if (todasMarcadas) numeros.forEach((n) => novo.delete(n));
                else numeros.forEach((n) => novo.add(n));
                return novo;
              })}>
              {todasMarcadas ? `Desmarcar ${nomeCategoria}` : rotulo} ({numeros.length})
            </button>
          );
        })}
        <span style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginLeft: "0.3rem" }}>
          {selecionados.size} animal(is) selecionado(s)
        </span>
      </div>

      <TabelasStatusBst agenda={agendaFiltrada} selecionados={selecionados} onToggle={toggle} />

      <div className="card">
        <div className="card-header mb-2">Lançar para os selecionados ({selecionados.size})</div>
        <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.6rem" }}>
          Marque animais em qualquer uma das tabelas acima. "Aplicar" e "Marcar como inapta" são ações distintas —
          não é possível aplicar e marcar como inapta na mesma seleção. Quem não for marcado em nenhuma ação
          simplesmente não se aplica (nenhuma mudança).
        </p>
        <div className="flex items-end gap-3 flex-wrap">
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Data da aplicação</label>
            <input type="date" style={inputStyle} value={dataAplicacao} onChange={(e) => setDataAplicacao(e.target.value)} /></div>
          <div style={{ width: "13rem" }}><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Produto</label>
            <EstoquePicker
              itens={itensBst}
              value={produto}
              onChange={(nome) => {
                setProduto(nome);
                const item = itensBst.find((i) => i.nome === nome);
                if (item?.unidade) setUnidade(item.unidade);
              }}
              placeholder="Selecionar produto…"
              finalidades={["Medicamento"]}
              incluirNaoEstocaveis
            /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Dose</label>
            <input type="number" step="0.01" style={{ ...inputStyle, width: "5.5rem" }} value={dose} onChange={(e) => setDose(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Unidade</label>
            <input style={{ ...inputStyle, width: "5rem" }} value={unidade} onChange={(e) => setUnidade(e.target.value)} placeholder="unidade" /></div>
          <div>
            <label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Essa dose é</label>
            <div className="flex items-center gap-1">
              <button type="button" className={dosePorAnimal ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.74rem", padding: "0.3rem 0.6rem" }}
                onClick={() => setDosePorAnimal(true)}>Por animal</button>
              <button type="button" className={!dosePorAnimal ? "btn-primary" : "btn-ghost"} style={{ fontSize: "0.74rem", padding: "0.3rem 0.6rem" }}
                title="A dose informada é o total já aplicado para todos os selecionados — o sistema divide pelo número de animais antes de baixar do estoque e lançar por animal."
                onClick={() => setDosePorAnimal(false)}>Total do lote selecionado</button>
            </div>
          </div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Responsável</label>
            <select style={{ ...inputStyle, width: "9rem" }} value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
              <option value="">Opcional</option>
              {pessoasAtivas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
            </select></div>
          <button className="btn-primary" disabled={!selecionados.size || ocupado} onClick={() => setConfirmacao(futura ? "agendar" : "aplicar")}>
            <Check size={14} /> Aplicar BST
          </button>
          <button className="btn-ghost" disabled={!selecionados.size || ocupado} onClick={marcarInapta} style={{ color: "var(--red)" }}>
            <Ban size={14} /> Marcar como inapta
          </button>
          <button className="btn-ghost" disabled={!selecionados.size || ocupado} onClick={reverterInapta} title="Volta para a lista &quot;Incluir no próximo BST&quot; — só conta como apta de novo após uma nova aplicação">
            <XIcon size={14} /> Reverter (incluir de novo)
          </button>
        </div>
      </div>

      {confirmacao && (
        <Modal title={confirmacao === "agendar" ? "Agendar para nova data?" : "Aplicar e dar baixa no estoque?"} onClose={() => setConfirmacao(null)} width="440px">
          <p style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
            {confirmacao === "agendar"
              ? `A data escolhida (${new Date(dataAplicacao + "T00:00:00").toLocaleDateString("pt-BR")}) é futura. Deseja agendar a aplicação de BST para essa data? Ela ficará pendente na Agenda até ser confirmada.`
              : `Confirma a aplicação de BST (${produto.trim() || "Lactotropin"}${dose ? `, ${dose} ${unidade || ""} ${dosePorAnimal ? "por animal" : "no TOTAL do lote"}` : ""}) na data ${new Date(dataAplicacao + "T00:00:00").toLocaleDateString("pt-BR")} para os ${selecionados.size} animal(is) selecionado(s)? O lançamento vai gerar o registro de sanidade correspondente.`}
          </p>
          <div className="flex gap-2 justify-end">
            <button className="btn-ghost" onClick={() => setConfirmacao(null)}>Não</button>
            <button className="btn-primary" disabled={ocupado} onClick={executarAplicar}>{ocupado ? "…" : "Sim"}</button>
          </div>
        </Modal>
      )}
    </div>
  );
}
