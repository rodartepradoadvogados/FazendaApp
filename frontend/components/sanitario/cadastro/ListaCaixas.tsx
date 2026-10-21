"use client";
// Central de Protocolos › Vacinas e exames › Cadastro — lista das caixas
// (cada cadastro de vacina/exame é uma "caixa": o animal entra quando cumpre a
// regra e sai quando recebe, deixa de cumprir, sai do rebanho ou a janela
// fecha). Filtro ativa/inativa/arquivada, ações em massa (só administrador),
// aviso "nova versão do catálogo" e o wizard (WizardCaixa) para criar/editar.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Archive, Pencil, Plus, Printer, RefreshCw } from "lucide-react";
import { Modal } from "@/components/Modal";
import { TelaSkeleton, ErroCarregamento } from "@/components/ui";
import { useToast } from "@/components/Toast";
import { atualizarDoCatalogo, listarCaixas, mensagemDoErro, mudarEstadoCaixas, obterCaixa } from "@/lib/apiSanitario";
import { ROTULO_TIPO, textoJanela, textoPublico, type CaixaDetalhe, type CaixaResumo } from "@/lib/sanitarioTipos";
import { Chip, Faixa, Seg, carregarCategoriasSan, useCarregar, useEuSanitario } from "../comum";
import { ModalFicha } from "../FichaCampo";
import { WizardCaixa } from "./WizardCaixa";

type Filtro = "ativa" | "inativa" | "arquivada" | "todas";
type Acao = "ativar" | "inativar" | "arquivar" | "reativar";

function EstadoCaixa({ c }: { c: CaixaResumo }) {
  if (c.estado === "ativa") return <Chip tipo="ok">ativa</Chip>;
  if (c.estado === "arquivada") return <Chip tipo="inativa">arquivada</Chip>;
  return <Chip tipo="inativa">inativa</Chip>;
}

export function ListaCaixas({ abrirCaixaId, abrirPasso }: { abrirCaixaId?: number | null; abrirPasso?: number | null }) {
  const { admin, erro: erroEu } = useEuSanitario();
  const toast = useToast();
  const [filtro, setFiltro] = useState<Filtro>("ativa");
  const [sel, setSel] = useState<Set<number>>(new Set());
  const [wiz, setWiz] = useState<{ caixaId: number | null; passo: number } | null>(
    abrirCaixaId ? { caixaId: abrirCaixaId, passo: abrirPasso ?? 0 } : null);
  const [arquivar, setArquivar] = useState<number[] | null>(null);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [falhas, setFalhas] = useState<string[]>([]);
  const [ficha, setFicha] = useState<number | null>(null);
  const { dados: caixas, erro, carregando, recarregar } = useCarregar(() => listarCaixas("todas"), []);
  const [detalhes, setDetalhes] = useState<Map<number, CaixaDetalhe>>(new Map());
  const [nomesCat, setNomesCat] = useState<Map<number, string>>(new Map());

  // Público e janela de cada caixa (a lista não traz a definição): busca o
  // detalhe de cada uma em paralelo, depois que a lista chegou.
  useEffect(() => {
    if (!caixas) return;
    let vivo = true;
    carregarCategoriasSan().then((l) => { if (vivo) setNomesCat(new Map(l.map((c) => [c.id, c.nome]))); }).catch(() => undefined);
    Promise.allSettled(caixas.map((c) => obterCaixa(c.id))).then((rs) => {
      if (!vivo) return;
      const m = new Map<number, CaixaDetalhe>();
      rs.forEach((r) => { if (r.status === "fulfilled") m.set(r.value.id, r.value); });
      setDetalhes(m);
    });
    return () => { vivo = false; };
  }, [caixas]);

  const contagem = useMemo(() => {
    const l = caixas || [];
    return { ativa: l.filter((c) => c.estado === "ativa").length, inativa: l.filter((c) => c.estado === "inativa").length,
      arquivada: l.filter((c) => c.estado === "arquivada").length, todas: l.length };
  }, [caixas]);
  const visiveis = useMemo(() => (caixas || []).filter((c) => filtro === "todas" || c.estado === filtro), [caixas, filtro]);
  const selVisiveis = visiveis.filter((c) => sel.has(c.id));
  const novas = (caixas || []).filter((c) => c.catalogo?.nova_versao && c.estado !== "arquivada");

  async function acaoEmMassa(acao: Acao, ids: number[], mot?: string) {
    setOcupado(true); setFalhas([]);
    try {
      const r = await mudarEstadoCaixas(ids, acao, mot);
      const nomes = new Map((caixas || []).map((c) => [c.id, c.nome]));
      const erros = r.resultados.filter((x) => !x.ok).map((x) => `${nomes.get(x.caixa_id) || x.caixa_id}: ${x.erro}`);
      setFalhas(erros);
      const ok = r.resultados.filter((x) => x.ok).length;
      if (ok) toast(`${ok} ${ok > 1 ? "cadastros atualizados" : "cadastro atualizado"}.`);
      setSel(new Set());
      recarregar();
    } catch (e) {
      setFalhas([mensagemDoErro(e)]);
    } finally { setOcupado(false); }
  }
  async function atualizarCopia(c: CaixaResumo) {
    setOcupado(true);
    try {
      const det = await atualizarDoCatalogo(c.id);
      toast(`${det.nome}: cópia atualizada para o catálogo v${det.catalogo?.versao}. Vale daqui para frente.`);
      recarregar();
    } catch (e) {
      toast(mensagemDoErro(e), "erro");
    } finally { setOcupado(false); }
  }

  if (wiz) {
    return <WizardCaixa key={`${wiz.caixaId}-${wiz.passo}`} caixaId={wiz.caixaId} passoInicial={wiz.passo} admin={admin}
      onSair={(msg) => { setWiz(null); if (msg) toast(msg); recarregar(); }} />;
  }

  return (
    <div className="san-pagina">
      <div className="san-cab">
        <div>
          <h2>Vacinas e exames da fazenda</h2>
          <p>Cada cadastro é uma caixa: o animal entra quando cumpre a regra e sai quando recebe, deixa de cumprir, sai do rebanho ou a janela fecha. Só administradores cadastram, e só pelo site.</p>
        </div>
        {admin && (
          <button type="button" className="btn-primary" onClick={() => setWiz({ caixaId: null, passo: 0 })}>
            <Plus size={14} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Novo cadastro
          </button>
        )}
      </div>
      {erroEu && <Faixa tipo="atencao">{erroEu}</Faixa>}
      {novas.length > 0 && (
        <Faixa>
          O catálogo central publicou versão nova de <b>{novas.map((c) => `${c.nome} (v${c.catalogo?.versao_central})`).join(", ")}</b>. A sua cópia continua como está até você atualizar.
          {admin && (
            <div className="san-acoes" style={{ marginTop: "0.4rem" }}>
              {novas.map((c) => (
                <button key={c.id} type="button" className="btn-ghost san-btn-sm" disabled={ocupado} onClick={() => atualizarCopia(c)}>
                  <RefreshCw size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />Atualizar {c.nome_curto || c.nome}
                </button>
              ))}
            </div>
          )}
        </Faixa>
      )}
      <div className="san-acoes">
        <Seg<Filtro> rotulo="Filtrar cadastros" valor={filtro} onChange={(f) => { setFiltro(f); setSel(new Set()); }}
          opcoes={([["ativa", "Ativas"], ["inativa", "Inativas"], ["arquivada", "Arquivadas"], ["todas", "Todas"]] as const).map(([k, t]) => ({
            id: k, label: <>{t}<span className="san-num">{contagem[k]}</span></>,
          }))} />
        <span className="san-nota">Padrão de fábrica: B19 e os exames de tuberculose e brucelose vêm <b>inativos</b> até você ativar.</span>
      </div>
      {falhas.length > 0 && <Faixa tipo="alerta">Não deu para todos: {falhas.join("; ")}.</Faixa>}
      {erro ? <ErroCarregamento mensagem={erro} onRetry={recarregar} />
        : carregando && !caixas ? <TelaSkeleton kpis={0} label="Carregando os cadastros" /> : (
          <div className="san-bloco">
            <div className="overflow-x-auto">
              <table className="fazenda-table">
                <thead><tr>
                  {admin && <th><input type="checkbox" aria-label="Selecionar todos os cadastros visíveis"
                    checked={selVisiveis.length > 0 && selVisiveis.length === visiveis.length}
                    onChange={(e) => setSel(e.target.checked ? new Set(visiveis.map((c) => c.id)) : new Set())} /></th>}
                  <th>Cadastro</th><th>Público</th><th>Janela</th><th>Aviso</th><th style={{ textAlign: "right" }}>Na caixa hoje</th>
                  <th>Versão</th><th>Estado</th><th><span className="san-sr">Ações</span></th>
                </tr></thead>
                <tbody>
                  {visiveis.length ? visiveis.map((c) => {
                    const det = detalhes.get(c.id);
                    return (
                      <tr key={c.id}>
                        {admin && <td><input type="checkbox" aria-label={`Selecionar ${c.nome}`} checked={sel.has(c.id)}
                          onChange={(e) => setSel((p) => { const n = new Set(p); if (e.target.checked) n.add(c.id); else n.delete(c.id); return n; })} /></td>}
                        <td style={{ minWidth: 220 }}>
                          <b>{c.nome}</b>
                          <div className="san-tags">
                            <span className="san-tag">{ROTULO_TIPO[c.tipo] || c.tipo}</span>
                            {c.obrigatoria && <span className="san-tag">obrigatório</span>}
                            {det?.definicao.legal_crmv_pedir && <span className="san-tag">CRMV pedido</span>}
                            {c.catalogo && <span className="san-tag">catálogo v{c.catalogo.versao}</span>}
                            {c.catalogo?.nova_versao && <span className="san-tag destaque">nova versão v{c.catalogo.versao_central}</span>}
                            {c.tipo !== "exame" && !c.carencia_aceita && c.estado !== "arquivada" && <span className="san-tag alerta">carência sem aceite</span>}
                          </div>
                          {c.arquivada_motivo && <div className="san-nota">Arquivada: {c.arquivada_motivo}</div>}
                        </td>
                        <td style={{ minWidth: 160 }} className="san-nota">{det ? textoPublico(det.definicao, nomesCat) : "…"}</td>
                        <td style={{ minWidth: 170 }} className="san-nota">{det ? textoJanela(det.definicao) : "…"}</td>
                        <td className="san-num" style={{ whiteSpace: "nowrap" }}>mín. {c.aglo_min ?? "—"}{det ? ` · ${det.definicao.aviso_antecedencia_dias} d` : ""}</td>
                        <td className="san-num" style={{ textAlign: "right" }}>
                          {c.estado === "ativa"
                            ? <Link href={`/sanidade?aba=preventiva&sub=janela&caixa=${c.id}`} className="san-link">{c.na_caixa}</Link> : "—"}
                        </td>
                        <td className="san-num">v{c.versao_numero ?? 1}</td>
                        <td><EstadoCaixa c={c} /></td>
                        <td>
                          <div className="san-acoes" style={{ flexWrap: "nowrap" }}>
                            {admin && c.estado !== "arquivada" && (
                              <button type="button" className="btn-ghost san-btn-sm" onClick={() => setWiz({ caixaId: c.id, passo: 0 })} aria-label={`Editar ${c.nome}`}>
                                <Pencil size={12} aria-hidden="true" style={{ verticalAlign: "-1px", marginRight: 4 }} />Editar
                              </button>
                            )}
                            {admin && c.estado !== "arquivada" && (
                              <button type="button" className="san-link" disabled={ocupado} onClick={() => acaoEmMassa(c.estado === "ativa" ? "inativar" : "ativar", [c.id])}>
                                {c.estado === "ativa" ? "Inativar" : "Ativar"}
                              </button>
                            )}
                            {admin && c.estado === "arquivada" && (
                              <button type="button" className="san-link" disabled={ocupado} onClick={() => acaoEmMassa("reativar", [c.id])}>Tirar do arquivo</button>
                            )}
                            <button type="button" className="san-link" onClick={() => setFicha(c.id)} title="Ficha vazia para imprimir">
                              <Printer size={13} aria-hidden="true" style={{ verticalAlign: "-2px" }} /><span className="san-sr">Ficha vazia de {c.nome}</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  }) : (
                    <tr><td colSpan={admin ? 9 : 8} className="san-nota" style={{ textAlign: "center", padding: "1.2rem" }}>
                      {filtro === "ativa" && contagem.todas ? "Nenhum cadastro ativo. Veja as inativas e ative as que a fazenda usa." : "Nenhum cadastro neste filtro."}
                    </td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      {admin && selVisiveis.length > 0 && (
        <div className="san-barra-sel" role="region" aria-label="Ações em massa">
          <span className="cont">{selVisiveis.length} {selVisiveis.length > 1 ? "cadastros selecionados" : "cadastro selecionado"}</span>
          <button type="button" className="btn-ghost" disabled={ocupado} onClick={() => acaoEmMassa("ativar", selVisiveis.map((c) => c.id))}>Ativar</button>
          <button type="button" className="btn-ghost" disabled={ocupado} onClick={() => acaoEmMassa("inativar", selVisiveis.map((c) => c.id))}>Inativar</button>
          {selVisiveis.some((c) => c.estado === "arquivada")
            ? <button type="button" className="btn-ghost" disabled={ocupado} onClick={() => acaoEmMassa("reativar", selVisiveis.map((c) => c.id))}>Tirar do arquivo</button>
            : <button type="button" className="btn-ghost" disabled={ocupado} onClick={() => { setMotivo(""); setArquivar(selVisiveis.map((c) => c.id)); }}>
              <Archive size={13} aria-hidden="true" style={{ verticalAlign: "-2px", marginRight: 4 }} />Arquivar</button>}
          <button type="button" className="btn-ghost" onClick={() => setSel(new Set())}>Limpar seleção</button>
        </div>
      )}
      <p className="san-nota" style={{ margin: 0 }}>Editar cria uma <b>versão nova</b> que vale daqui para frente; o histórico fica como foi. Arquivar não apaga: tira das telas e pode ser desfeito.</p>

      {arquivar && (
        <Modal title={`Arquivar ${arquivar.length} ${arquivar.length > 1 ? "cadastros" : "cadastro"}`} onClose={() => setArquivar(null)} width="520px">
          <div className="san-modal-corpo">
            <p className="san-modal-sub">Some das telas e para de gerar avisos. O histórico continua; dá para tirar do arquivo depois.</p>
            <div className="san-campo">
              <label htmlFor="arqMot">Motivo (opcional)</label>
              <input id="arqMot" className="san-input" value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="ex.: cadastro repetido" />
            </div>
          </div>
          <div className="san-modal-rodape">
            <button type="button" className="btn-ghost" onClick={() => setArquivar(null)}>Cancelar</button>
            <button type="button" className="btn-primary-gold" disabled={ocupado}
              onClick={async () => { const ids = arquivar; setArquivar(null); await acaoEmMassa("arquivar", ids, motivo.trim() || undefined); }}>Arquivar</button>
          </div>
        </Modal>
      )}
      {ficha != null && <ModalFicha caixaIds={[ficha]} onFechar={() => setFicha(null)} />}
    </div>
  );
}
