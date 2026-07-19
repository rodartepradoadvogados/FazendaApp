"use client";
import { useEffect, useMemo, useState } from "react";
import { Droplets, AlertTriangle, Check, Ban, X as XIcon } from "lucide-react";
import { aplicarBstLote, marcarInaptaBst, fetchEstoque, fetchPessoas } from "@/lib/api";
import { Modal } from "@/components/Modal";
import { MultiFiltro } from "@/components/ui";

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

  const Tabela = ({ titulo, lista, cor }: { titulo: string; lista: any[]; cor: string }) => (
    <div className="card">
      <div className="card-header mb-2 flex items-center gap-2" style={{ color: cor }}><Droplets size={14} /> {titulo} ({lista.length})</div>
      {!lista.length ? <p style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>Nenhum animal nesta condição.</p> : (
        <div style={{ overflowX: "auto", maxHeight: "280px" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr>{onToggle && <th style={th}></th>}<th style={th}></th><th style={th}>Nº</th><th style={th}>Lote</th><th style={{ ...th, textAlign: "right" }}>DEL</th><th style={th}>Obs.</th></tr></thead>
            <tbody>{lista.map((b: any) => (
              <tr key={b.numero_matriz}>
                {onToggle && <td style={td}><input type="checkbox" checked={!!selecionados?.has(b.numero_matriz)} onChange={() => onToggle(b.numero_matriz)} /></td>}
                <td style={td}>
                  {b.requer_reanalise && (
                    <span title="Retirada do BST — revisar antes de incluir de novo" style={{ display: "inline-block", width: 9, height: 9, borderRadius: "50%", background: "var(--amber)" }} />
                  )}
                </td>
                <td style={{ ...td, fontWeight: 700 }}>{b.numero_matriz}</td>
                <td style={td}>{b.grupo || "—"}</td>
                <td style={{ ...td, textAlign: "right" }}>{b.del_dias ?? "—"}</td>
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

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Tabela titulo="BST — Aptas" lista={aptas} cor="var(--green-light)" />
      <Tabela titulo="BST — Incluir no próximo BST" lista={nuncaAplicadas} cor="var(--amber)" />
      <Tabela titulo="BST — Inaptas p/ próxima aplicação" lista={inaptas} cor="var(--red)" />
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
export function PainelLancarBst({ agenda, onAtualizado }: { agenda: any; onAtualizado: () => void }) {
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [lotesFiltro, setLotesFiltro] = useState<string[]>([]);
  const [dataAplicacao, setDataAplicacao] = useState(() => new Date().toISOString().slice(0, 10));
  const [produto, setProduto] = useState("Lactotropin");
  const [dose, setDose] = useState("");
  const [unidade, setUnidade] = useState("unidade");
  const [responsavel, setResponsavel] = useState("");
  const [confirmacao, setConfirmacao] = useState<"agendar" | "aplicar" | null>(null);
  const [ocupado, setOcupado] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [estoqueItens, setEstoqueItens] = useState<any[]>([]);
  const [pessoas, setPessoas] = useState<any[]>([]);

  useEffect(() => {
    fetchEstoque().then((d) => setEstoqueItens(d.itens || [])).catch(() => setEstoqueItens([]));
    fetchPessoas().then(setPessoas).catch(() => setPessoas([]));
  }, []);

  // Boostin só aparece como opção de produto se já tiver saldo em estoque —
  // caso contrário o lançamento continua só com Lactotropin, mas o item já
  // fica cadastrado (seed no backend) para quando o saldo for lançado.
  const boostinDisponivel = useMemo(
    () => estoqueItens.some((i) => (i.nome || "").trim().toLowerCase() === "boostin" && (i.quantidade || 0) > 0),
    [estoqueItens]
  );
  useEffect(() => {
    if (produto === "Boostin" && !boostinDisponivel) setProduto("Lactotropin");
  }, [boostinDisponivel]); // eslint-disable-line react-hooks/exhaustive-deps

  const pessoasAtivas = useMemo(
    () => pessoas.filter((p) => p.ativo !== false).sort((a, b) => (a.nome || "").localeCompare(b.nome || "")),
    [pessoas]
  );

  const toggle = (numero: string) => setSelecionados((prev) => {
    const novo = new Set(prev);
    novo.has(numero) ? novo.delete(numero) : novo.add(numero);
    return novo;
  });

  const executarAplicar = async () => {
    setOcupado(true); setErro(null);
    try {
      await aplicarBstLote({
        numeros_matriz: Array.from(selecionados), data_aplicacao: dataAplicacao, aplicado: true,
        produto: produto.trim() || "Lactotropin", dose: dose ? Number(dose) : null, unidade: unidade || null,
        responsavel: responsavel.trim() || undefined,
      });
      setSelecionados(new Set());
      onAtualizado();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); setConfirmacao(null); }
  };

  const marcarInapta = async () => {
    setOcupado(true); setErro(null);
    try {
      await marcarInaptaBst({ numeros_matriz: Array.from(selecionados), inapta: true });
      setSelecionados(new Set());
      onAtualizado();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  };

  const reverterInapta = async () => {
    setOcupado(true); setErro(null);
    try {
      await marcarInaptaBst({ numeros_matriz: Array.from(selecionados), inapta: false });
      setSelecionados(new Set());
      onAtualizado();
    } catch (e: any) { setErro(e.message); }
    finally { setOcupado(false); }
  };

  const futura = dataAplicacao > new Date().toISOString().slice(0, 10);
  const inputStyle: React.CSSProperties = { background: "var(--surface-2)", color: "var(--text)", border: "1px solid var(--border)", borderRadius: "6px", padding: "0.35rem 0.5rem", fontSize: "0.8rem" };

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

      <div style={{ maxWidth: "280px" }}>
        <MultiFiltro label="Filtrar por lote" opcoes={lotesDisponiveis} selecionados={lotesFiltro} onChange={setLotesFiltro} />
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
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Produto</label>
            <select style={{ ...inputStyle, width: "9rem" }} value={produto} onChange={(e) => setProduto(e.target.value)}>
              <option value="Lactotropin">Lactotropin</option>
              {boostinDisponivel && <option value="Boostin">Boostin</option>}
            </select></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Dose</label>
            <input type="number" step="0.01" style={{ ...inputStyle, width: "5.5rem" }} value={dose} onChange={(e) => setDose(e.target.value)} /></div>
          <div><label style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>Unidade</label>
            <input style={{ ...inputStyle, width: "5rem" }} value={unidade} onChange={(e) => setUnidade(e.target.value)} placeholder="unidade" /></div>
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
          <button className="btn-ghost" disabled={!selecionados.size || ocupado} onClick={reverterInapta}>
            <XIcon size={14} /> Reverter (voltar a apta)
          </button>
        </div>
      </div>

      {confirmacao && (
        <Modal title={confirmacao === "agendar" ? "Agendar para nova data?" : "Aplicar e dar baixa no estoque?"} onClose={() => setConfirmacao(null)} width="440px">
          <p style={{ fontSize: "0.85rem", marginBottom: "1rem" }}>
            {confirmacao === "agendar"
              ? `A data escolhida (${new Date(dataAplicacao + "T00:00:00").toLocaleDateString("pt-BR")}) é futura. Deseja agendar a aplicação de BST para essa data? Ela ficará pendente na Agenda até ser confirmada.`
              : `Confirma a aplicação de BST (${produto.trim() || "Lactotropin"}${dose ? `, ${dose} ${unidade || ""}` : ""}) na data ${new Date(dataAplicacao + "T00:00:00").toLocaleDateString("pt-BR")} para os ${selecionados.size} animal(is) selecionado(s)? O lançamento vai gerar o registro de sanidade correspondente.`}
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
