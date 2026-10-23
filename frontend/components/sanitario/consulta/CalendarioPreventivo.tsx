"use client";
// Sanidade › Preventiva › Calendário sanitário: grade anual no formato da
// planilha (linhas = vacinas/exames, colunas = meses). Cada célula: animais
// DISTINTOS previstos e, embaixo, os já aplicados. A linha de baixo conta cada
// animal uma vez por mês, mesmo que esteja em várias vacinas (sem somar
// duplicado). Os parâmetros de cada linha (janela, mínimo) ficam visíveis.
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ErroCarregamento, TelaSkeleton } from "@/components/ui";
import { calendario, listarCaixas, listarDias, obterCaixa } from "@/lib/apiSanitario";
import { MESES_CURTOS, fmtData, hojeISO, textoJanela, type CaixaDetalhe } from "@/lib/sanitarioTipos";
import { grupoDoDia, linkCentral } from "@/lib/protocolosNavegacao";
import { Chip, Seg, useCarregar } from "../comum";

export function CalendarioPreventivo() {
  const hoje = hojeISO();
  const anoHoje = Number(hoje.slice(0, 4));
  const mesHoje = Number(hoje.slice(5, 7));
  const [ano, setAno] = useState(anoHoje);
  const cal = useCarregar(() => calendario(ano), [ano]);
  const caixas = useCarregar(() => listarCaixas("todas"), []);
  const dias = useCarregar(() => listarDias({ estado: "abertos" }), []);
  const [detalhes, setDetalhes] = useState<Map<number, CaixaDetalhe>>(new Map());
  useEffect(() => {
    if (!caixas.dados) return;
    let vivo = true;
    Promise.allSettled(caixas.dados.filter((c) => c.estado !== "arquivada").map((c) => obterCaixa(c.id))).then((rs) => {
      if (!vivo) return;
      const m = new Map<number, CaixaDetalhe>();
      rs.forEach((r) => { if (r.status === "fulfilled") m.set(r.value.id, r.value); });
      setDetalhes(m);
    });
    return () => { vivo = false; };
  }, [caixas.dados]);

  const linhas = useMemo(() => {
    if (!cal.dados) return [];
    const nomes = new Map<number, string>();
    for (const m of cal.dados.meses) for (const x of [...m.previstos, ...m.aplicados]) nomes.set(x.caixa_id, x.caixa);
    const resumo = new Map((caixas.dados || []).map((c) => [c.id, c]));
    return [...nomes.entries()].map(([id, nome]) => ({
      id, nome, resumo: resumo.get(id),
      cel: cal.dados!.meses.map((m) => ({
        prev: m.previstos.find((x) => x.caixa_id === id)?.animais || 0,
        apl: m.aplicados.find((x) => x.caixa_id === id)?.animais || 0,
      })),
    })).sort((a, b) => a.nome.localeCompare(b.nome));
  }, [cal.dados, caixas.dados]);

  if (cal.erro) return <ErroCarregamento mensagem={cal.erro} onRetry={cal.recarregar} />;
  return (
    <div className="san-pagina">
      <div className="san-params">
        <span>Ano: <b>{ano}</b></span>
        <Seg<string> rotulo="Ano" valor={String(ano)} onChange={(v) => setAno(Number(v))}
          opcoes={[anoHoje - 1, anoHoje, anoHoje + 1].map((a) => ({ id: String(a), label: String(a) }))} />
        <span>Contagem: <b>animais distintos</b>, rebanho de hoje projetado</span>
        <span>Data-base dos períodos: <b>por vacina</b> (padrão dia 15)</span>
        <span>Mínimo e antecedência: <b>por vacina</b> (coluna)</span>
        <Link href={linkCentral.cadastroPreventivo()} className="san-link">Mudar na Central</Link>
      </div>
      {!cal.dados ? <TelaSkeleton kpis={0} label="Carregando o calendário" /> : (
        <section className="san-bloco" style={cal.carregando ? { opacity: 0.6 } : undefined}>
          <div className="overflow-x-auto">
            <table className="san-cal">
              <thead><tr>
                <th style={{ textAlign: "left" }}>Vacina ou exame</th><th style={{ textAlign: "left" }}>Aviso</th>
                {MESES_CURTOS.map((m, i) => <th key={m} className={`m ${ano === anoHoje && i + 1 === mesHoje ? "hoje" : ""}`}>{m}<br /><span style={{ fontWeight: 400 }}>{String(ano).slice(2)}</span></th>)}
              </tr></thead>
              <tbody>
                {linhas.length ? linhas.map((l) => {
                  const det = detalhes.get(l.id);
                  return (
                    <tr key={l.id}>
                      <td className="nome"><b>{l.nome}</b>{l.resumo && l.resumo.estado !== "ativa" && <> <Chip tipo="inativa">{l.resumo.estado}</Chip></>}
                        <div className="san-nota">{det ? textoJanela(det.definicao) : l.id === 0 ? "lançamentos “outro”" : ""}</div></td>
                      <td className="san-nota san-num" style={{ whiteSpace: "nowrap" }}>{l.resumo ? <>mín. {l.resumo.aglo_min ?? "—"}<br />{det ? `${det.definicao.aviso_antecedencia_dias} d` : ""}</> : "—"}</td>
                      {l.cel.map((c, i) => (
                        <td key={i} className={`m ${ano === anoHoje && i + 1 === mesHoje ? "hoje" : ""}`}>
                          {c.prev ? <span className="on" title={`${c.prev} animais previstos`}>{c.prev}</span> : <span className="zero">·</span>}
                          {c.apl ? <span className="ap" title={`${c.apl} animais aplicados`}>{c.apl} feitos</span> : null}
                        </td>
                      ))}
                    </tr>
                  );
                }) : <tr><td colSpan={14} className="san-nota" style={{ textAlign: "center", padding: "1.2rem" }}>Nada previsto nem aplicado em {ano}.</td></tr>}
              </tbody>
              <tfoot><tr>
                <td>Animais distintos no mês</td><td />
                {cal.dados.meses.map((m) => <td key={m.mes} className="m san-num">{m.previstos_total || "·"}{m.aplicados_total ? <span className="ap">{m.aplicados_total} feitos</span> : null}</td>)}
              </tr></tfoot>
            </table>
          </div>
          <div className="san-bloco-corpo">
            <p className="san-nota" style={{ margin: 0 }}>{cal.dados.nota} Pré-parto e idade entram no mês em que a janela abre; entrada em IA só aparece depois que acontece. Dias marcados no ano: {cal.dados.meses.reduce((s, m) => s + m.dias.length, 0)}.</p>
          </div>
        </section>
      )}
      <section className="san-bloco">
        <div className="san-bloco-cab"><h3>Próximos dias marcados</h3><Link href={linkCentral.aplicarPreventivo()} className="san-link">Abrir na Central</Link></div>
        {dias.erro ? <div className="san-bloco-corpo"><ErroCarregamento mensagem={dias.erro} onRetry={dias.recarregar} /></div>
          : !dias.dados ? <div className="san-bloco-corpo"><div className="skeleton" style={{ height: "3rem" }} /></div>
            : dias.dados.length ? dias.dados.map((d) => (
              <div key={d.id} className="san-nota-ag">
                <span className="ico" aria-hidden="true">{fmtData(d.data, true).slice(0, 2)}</span>
                <div><p><b>{d.nome}</b>{d.hora ? ` · ${d.hora}` : ""}</p><small className="san-num">{d.contagens.animais} animais distintos · {d.contagens.pendentes + d.contagens.feitos} aplicações previstas</small></div>
                <div className="san-acoes"><Link className="btn-ghost san-btn-sm" href={linkCentral.aplicarPreventivo({ dia: d.id }, grupoDoDia(d))}>Abrir</Link></div>
              </div>
            )) : <div className="san-bloco-corpo san-nota">Nenhum dia marcado.</div>}
      </section>
    </div>
  );
}
