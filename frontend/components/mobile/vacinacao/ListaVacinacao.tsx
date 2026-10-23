"use client";
// Menu › Vacinação (app de campo): vacinas e exames de hoje e de amanhã
// (GET /sanitario/campo/hoje), o comunicado da véspera, o card "Leite
// separado" e a fila do aparelho. Ao abrir a lista com sinal, os pacotes
// offline dos dias já são baixados e guardados — no curral, sem sinal, o dia
// abre do mesmo jeito. Tocar num dia abre a execução (tronco/grupo).
import { useEffect, useState } from "react";
import { CalendarDays, ChevronRight, Droplet, Milk } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import { fetchComCache, lerCache } from "@/lib/offline";
import { campoHoje, leiteSeparado, pacoteOffline } from "@/lib/apiSanitario";
import { marcarCampoAtivo } from "@/lib/filaSanitario";
import {
  ROTULO_ESTADO_DIA, ROTULO_MODO_LEITE, fmtData, textoProduto,
  type CampoHoje, type LeiteSeparado, type ModoLeite, type PacoteOffline, type ProdutoIn,
} from "@/lib/sanitarioTipos";
import { ExecucaoDia, chavePacote } from "./ExecucaoDia";
import { FaixaSan, PainelFila, Rotulo, rotuloCrmv, useComCopia, useEuCampo } from "./comum";

const CHAVE_HOJE = "san_campo_hoje";

export default function ListaVacinacao({ onVoltar, diaInicial }: { onVoltar: () => void; diaInicial?: number | null }) {
  const [aberto, setAberto] = useState<number | null>(diaInicial ?? null);
  const hojeQ = useComCopia<CampoHoje>(CHAVE_HOJE, campoHoje);
  const leite = useComCopia<LeiteSeparado>("san_leite_separado", leiteSeparado);
  const eu = useEuCampo();
  const [baixados, setBaixados] = useState<Record<number, boolean>>({});

  useEffect(() => { marcarCampoAtivo(); }, []);
  // Baixa (e guarda) o pacote offline de cada dia listado — com sinal.
  useEffect(() => {
    const dias = hojeQ.dados?.dias || [];
    let vivo = true;
    for (const d of dias) {
      fetchComCache(chavePacote(d.id), () => pacoteOffline(d.id)).then((r) => {
        if (vivo) setBaixados((b) => ({ ...b, [d.id]: !!r.dados }));
      });
    }
    return () => { vivo = false; };
  }, [hojeQ.dados]);

  if (aberto != null) return <ExecucaoDia diaId={aberto} onVoltar={() => { setAberto(null); hojeQ.recarregar(); }} />;

  const dias = hojeQ.dados?.dias || [];
  const deHoje = dias.filter((d) => d.quando === "hoje");
  const deAmanha = dias.filter((d) => d.quando === "amanha");
  const nomeEstoque = (diaId: number, estoqueId: number | null) =>
    estoqueId ? lerCache<PacoteOffline>(chavePacote(diaId))?.estoques.find((e) => e.id === estoqueId)?.nome : undefined;

  return (
    <div>
      <MobVoltar titulo="Vacinação" subtitulo="Vacinas e exames de hoje e de amanhã" onVoltar={onVoltar} />
      {hojeQ.doCache && hojeQ.dados && <p className="mob-san-txt" style={{ marginTop: "-0.5rem", marginBottom: "0.6rem" }}>Sem sinal: lista guardada neste celular.</p>}
      <PainelFila eu={eu} partes={{ aviso: true, decisoes: true }} />

      {deAmanha.map((d) => (
        <div key={`v${d.id}`} className="mob-card" data-estado="normal" style={{ padding: "0.95rem 1rem", marginBottom: "0.7rem" }}>
          <span className="mob-san-rotulo" style={{ marginTop: 0 }}>Comunicado da véspera</span>
          <h2 style={{ fontSize: "1.1rem", fontWeight: 800, margin: "0.2rem 0" }}>Amanhã, {fmtData(d.data, true)}{d.hora ? ` às ${d.hora}` : ""}</h2>
          <p style={{ fontWeight: 700 }}>{d.nome}</p>
          <p className="mob-san-txt">
            {d.contagens.animais} {d.contagens.animais === 1 ? "animal" : "animais"}
            {d.veterinario?.texto ? ` · ${d.veterinario.texto}` : ""}{d.veterinario?.crmv ? ` · ${rotuloCrmv(d.veterinario.crmv)}` : ""}
          </p>
          <p className="mob-san-txt"><b>Separar:</b> {d.caixas.filter((c) => c.tipo !== "exame")
            .map((c) => `${c.nome_curto}: ${textoProduto(c.produto as ProdutoIn, nomeEstoque(d.id, c.produto.estoque_id))}`).join("; ") || "material do exame"}</p>
        </div>
      ))}

      <Rotulo>Hoje e amanhã</Rotulo>
      {hojeQ.carregando && !hojeQ.dados && <p className="mob-san-txt">Carregando…</p>}
      {!hojeQ.carregando && !hojeQ.dados && (
        <FaixaSan tipo="alerta">Sem sinal e sem lista guardada neste celular. Abra com sinal uma vez.</FaixaSan>
      )}
      {hojeQ.dados && !dias.length && (
        <div style={{ textAlign: "center", padding: "1.5rem 1rem", color: "var(--mob-muted)" }}>
          <CalendarDays size={28} aria-hidden="true" style={{ margin: "0 auto 0.5rem", display: "block" }} />
          <p style={{ fontWeight: 700, color: "var(--mob-text)" }}>Nenhuma vacina ou exame para hoje ou amanhã.</p>
        </div>
      )}
      {[...deHoje, ...deAmanha].map((d) => {
        const feitos = d.contagens.feitos, total = d.contagens.feitos + d.contagens.pendentes;
        return (
          <button key={d.id} type="button" className="mob-linha" style={{ marginBottom: "0.6rem" }} onClick={() => setAberto(d.id)}
            aria-label={`Abrir ${d.nome}`}>
            <span style={{ flex: 1, minWidth: 0 }}>
              <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>
                {d.quando === "hoje" ? (d.data < (hojeQ.dados?.hoje || "") ? fmtData(d.data, true) : "Hoje") : "Amanhã"}{d.hora ? ` · ${d.hora}` : ""} · {ROTULO_ESTADO_DIA[d.estado] || d.estado}
              </span>
              <b style={{ display: "block", fontSize: "1.05rem" }}>{d.nome}</b>
              <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>
                {d.contagens.animais} {d.contagens.animais === 1 ? "animal" : "animais"} · {feitos} de {total} feitos
                {baixados[d.id] ? " · guardado no celular" : ""}
              </span>
            </span>
            <ChevronRight size={20} aria-hidden="true" style={{ color: "var(--mob-muted)" }} />
          </button>
        );
      })}

      <Rotulo>Leite separado</Rotulo>
      <div className="mob-card" data-estado={leite.dados?.animais ? "atrasado" : "feito"} style={{ padding: "0.95rem 1rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
          <Milk size={22} aria-hidden="true" style={{ color: "var(--mob-dourado-2)" }} />
          <b style={{ fontSize: "1.05rem" }}>
            {leite.dados ? `${leite.dados.animais} ${leite.dados.animais === 1 ? "animal" : "animais"} com leite em carência` : leite.carregando ? "Carregando…" : "Sem dados neste celular"}
          </b>
        </div>
        {leite.doCache && leite.dados && <p className="mob-san-txt">Cópia guardada neste celular.</p>}
        {(leite.dados?.itens || []).slice(0, 8).map((i, k) => (
          <div key={`${i.numero}-${k}`} style={{ display: "flex", gap: "0.5rem", alignItems: "baseline", borderTop: "1px solid var(--mob-border)", padding: "0.5rem 0", marginTop: k ? 0 : "0.5rem" }}>
            <Droplet size={14} aria-hidden="true" style={{ color: "var(--mob-muted)", flexShrink: 0 }} />
            <span style={{ flex: 1, minWidth: 0 }}>
              <b>{i.numero || "—"}</b> · {i.caixa || i.produto || (i.origem === "curativo" ? "tratamento" : "vacina")}
              <span className="mob-san-txt" style={{ display: "block", marginTop: 0 }}>
                até {fmtData(i.liberacao_leite, true)} · {ROTULO_MODO_LEITE[i.modo as ModoLeite] || i.modo}
              </span>
            </span>
          </div>
        ))}
        {(leite.dados?.itens.length || 0) > 8 && <p className="mob-san-txt">e mais {(leite.dados?.itens.length || 0) - 8}.</p>}
      </div>
      <div style={{ marginTop: "1rem" }}><PainelFila eu={eu} partes={{ resultados: true }} /></div>
    </div>
  );
}
