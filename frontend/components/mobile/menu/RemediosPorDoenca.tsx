"use client";
// Sub-tela: Remédios por Doença — consulta rápida do "substituto inteligente"
// (mesmo recurso do site, versão campo): escolhe a doença e vê os princípios
// ativos indicados, em ordem de prioridade clínica, com status de estoque.
// Só leitura.
//
// Espec de Sanidade (out/2026), decisões do dono:
//  - mostra a OBSERVAÇÃO clínica da indicação e a dose/via/carência do
//    cadastro das marcas, quando existirem;
//  - 1ª escolha sem estoque e outra com estoque → destaque "use a 2ª escolha";
//  - OFFLINE: a lista de doenças e a última consulta de cada doença ficam
//    guardadas no celular; sem sinal (ou com erro) mostra a cópia com aviso —
//    antes qualquer falha virava "Nenhuma indicação cadastrada", como se a
//    doença não tivesse remédio;
//  - estoque: "Sem apresentações cadastradas" quando não há item nenhum, sem
//    o "0 frasco em estoque" ao lado de "Sem estoque", e plural certo.
import { useMemo, useState } from "react";
import { FlaskConical } from "lucide-react";
import { MobVoltar, MobCard } from "@/components/mobile/ui";
import { fetchDoencas, fetchIndicacoesDoenca, type OpcaoIndicacaoDoenca } from "@/lib/api";
import { AvisoCopia, Carregando, ErroCarga, Vazio, useCarregar } from "@/components/mobile/menu/comum";

const COR_STATUS: Record<OpcaoIndicacaoDoenca["status_estoque"], string> = {
  ok: "var(--mob-verde)", low: "var(--mob-ambar)", out: "var(--mob-vermelho)",
};
const TEXTO_STATUS: Record<OpcaoIndicacaoDoenca["status_estoque"], string> = {
  ok: "Em estoque", low: "Estoque baixo", out: "Sem estoque",
};

// Mesmos tipos de Doenca.TIPOS (backend) — agrupam o seletor em optgroups,
// espelhando components/RemediosPorDoenca.tsx (versão site).
const GRUPOS_TIPO: [string, string][] = [
  ["doenca", "Doenças"], ["reprodutivo", "Reprodutivo"], ["produtivo", "Produtivo"],
  ["preventivo", "Preventivo"], ["suporte", "Suporte"],
];

const CHAVE_DOENCAS = "menu_remedios_doencas";
const chaveIndicacoes = (id: string) => `menu_remedios_doenca_${id}`;

type DoencaLista = { id: number; nome: string; tipo?: string | null; ativo?: boolean };
type Indicacoes = Awaited<ReturnType<typeof fetchIndicacoesDoenca>>;

// Plural da apresentação ("frasco" → "frascos", "galão" → "galões").
const PLURAL: Record<string, string> = { "galão": "galões", "un": "un" };
function plural(unidade: string, qtd: number): string {
  if (qtd < 2) return unidade; // "1,5 frasco", "2 frascos"
  if (PLURAL[unidade]) return PLURAL[unidade];
  return /[aeiou]$/i.test(unidade) ? `${unidade}s` : /r$|z$/i.test(unidade) ? `${unidade}es` : `${unidade}s`;
}

/** Linha de estoque da opção (null = o selo de status já diz tudo). */
export function textoEstoque(o: OpcaoIndicacaoDoenca): string | null {
  if (o.apresentacoes_cadastradas === 0) return "Sem apresentações cadastradas";
  const total = o.total_apresentacoes;
  if (total == null || total <= 0) return null;
  const un = o.unidade_apresentacao || "un";
  return `${total.toLocaleString("pt-BR", { maximumFractionDigits: 2 })} ${plural(un, total)} em estoque`;
}

/** "Sem estoque da 1ª escolha — use a 2ª escolha (Nome)" ou null. */
export function avisoSubstituto(opcoes: OpcaoIndicacaoDoenca[]): string | null {
  if (!opcoes.length) return null;
  const melhor = Math.min(...opcoes.map((o) => o.prioridade));
  const primeiras = opcoes.filter((o) => o.prioridade === melhor);
  if (primeiras.some((o) => o.status_estoque !== "out")) return null;
  const sub = [...opcoes].filter((o) => o.prioridade > melhor && o.status_estoque !== "out")
    .sort((a, b) => a.prioridade - b.prioridade)[0];
  if (!sub) return null;
  return `Sem estoque da ${melhor}ª escolha (${primeiras.map((o) => o.nome).join(", ")}) — use a ${sub.prioridade}ª escolha: ${sub.nome}.`;
}

export default function RemediosPorDoenca({ onVoltar }: { onVoltar: () => void }) {
  const [doencaId, setDoencaId] = useState("");
  const lista = useCarregar<DoencaLista[]>(CHAVE_DOENCAS, () => fetchDoencas());
  const doencas = useMemo(() => (Array.isArray(lista.dados) ? lista.dados : []).filter((x) => x.ativo !== false), [lista.dados]);
  const ind = useCarregar<Indicacoes>(chaveIndicacoes(doencaId || "0"), () => fetchIndicacoesDoenca(Number(doencaId)),
    { habilitado: !!doencaId });

  const grupos = useMemo(() => GRUPOS_TIPO
    .map(([tipo, label]) => ({
      label,
      itens: doencas.filter((d) => (tipo === "doenca" ? !d.tipo || d.tipo === "doenca" : d.tipo === tipo)),
    }))
    .filter((g) => g.itens.length > 0), [doencas]);

  // Resposta de OUTRA doença (a anterior, enquanto a nova carrega) não conta.
  const dados = ind.dados && String(ind.dados.doenca_id) === doencaId ? ind.dados : null;
  const opcoes = dados?.opcoes ?? null;
  const aviso = opcoes ? avisoSubstituto(opcoes) : null;
  const semSinal = typeof navigator !== "undefined" && !navigator.onLine;

  return (
    <div>
      <MobVoltar titulo="Remédios por Doença" subtitulo="Remédios indicados e estoque" onVoltar={onVoltar} />

      {lista.doCache && doencas.length > 0 && !doencaId && <AvisoCopia chave={CHAVE_DOENCAS} mostrar />}
      {!lista.carregando && doencas.length === 0 && (
        lista.doCache
          ? <ErroCarga mensagem="Sem sinal e sem a lista de doenças guardada neste celular. Abra com sinal uma vez." onTentar={lista.recarregar} />
          : <Vazio icon={FlaskConical}>Nenhuma doença cadastrada.</Vazio>
      )}

      {doencas.length > 0 && (
        <>
          <label htmlFor="remedios-doenca" style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--mob-muted)", marginBottom: "0.3rem" }}>
            Doença
          </label>
          <select id="remedios-doenca" className="mob-input" value={doencaId} onChange={(e) => setDoencaId(e.target.value)} style={{ marginBottom: "1rem" }}>
            <option value="">Selecione…</option>
            {grupos.map((g) => (
              <optgroup key={g.label} label={g.label}>
                {g.itens.map((d) => <option key={d.id} value={d.id}>{d.nome}</option>)}
              </optgroup>
            ))}
          </select>
        </>
      )}

      {!doencaId ? (
        doencas.length > 0 && <Vazio icon={FlaskConical}>Escolha uma doença para ver os remédios indicados.</Vazio>
      ) : ind.carregando && !dados ? (
        <Carregando />
      ) : !dados ? (
        // Falhou e não há cópia desta doença: diz o que aconteceu (nunca "nenhuma indicação").
        <ErroCarga mensagem={semSinal || !ind.mensagemErro
          ? "Sem sinal e sem cópia desta doença neste celular. Consulte uma vez com sinal para guardar."
          : `Não foi possível consultar: ${ind.mensagemErro}`} onTentar={ind.recarregar} />
      ) : (
        <>
          {ind.doCache && <AvisoCopia chave={chaveIndicacoes(doencaId)} mostrar />}
          {ind.doCache && ind.mensagemErro && <ErroCarga mensagem={`Não foi possível atualizar: ${ind.mensagemErro}`} onTentar={ind.recarregar} />}
          {opcoes!.length === 0 ? (
            <Vazio icon={FlaskConical}>Nenhuma indicação cadastrada para essa doença.</Vazio>
          ) : (
            <>
              {aviso && (
                <div role="status" style={{
                  margin: "0 0 0.8rem", padding: "0.7rem 0.8rem", borderRadius: "var(--r-app)", fontSize: "0.88rem", fontWeight: 700,
                  border: "1px solid var(--mob-ambar)", borderLeft: "4px solid var(--mob-ambar)", color: "var(--mob-text)",
                  background: "color-mix(in srgb, var(--mob-ambar) 10%, transparent)",
                }}>{aviso}</div>
              )}
              {opcoes!.map((o) => <CartaoOpcao key={o.principio_ativo_id} o={o} />)}
            </>
          )}
        </>
      )}
    </div>
  );
}

function CartaoOpcao({ o }: { o: OpcaoIndicacaoDoenca }) {
  const estoque = textoEstoque(o);
  const bulas = o.bulas || [];
  return (
    <MobCard style={{ marginBottom: "0.6rem" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        <span style={{
          fontSize: "0.72rem", fontWeight: 800, padding: "0.15rem 0.55rem", borderRadius: "999px", flexShrink: 0,
          background: o.prioridade === 1 ? "var(--mob-verde)" : "var(--mob-surface-2)",
          color: o.prioridade === 1 ? "var(--mob-verde-fg)" : "var(--mob-muted)",
          border: o.prioridade === 1 ? "none" : "1px solid var(--mob-border)",
        }}>
          {o.prioridade}ª escolha
        </span>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: COR_STATUS[o.status_estoque], flexShrink: 0, marginLeft: "auto" }} />
        <span style={{ fontSize: "0.78rem", fontWeight: 600, color: COR_STATUS[o.status_estoque] }}>{TEXTO_STATUS[o.status_estoque]}</span>
      </div>
      <div style={{ fontWeight: 800, fontSize: "1rem", marginTop: "0.4rem" }}>{o.nome}</div>
      {o.classificacao && <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)" }}>{o.classificacao}</div>}
      {estoque && <div style={{ fontSize: "0.82rem", color: "var(--mob-muted)", marginTop: "0.1rem" }}>{estoque}</div>}
      {o.nota && (
        <div style={{ fontSize: "0.84rem", color: "var(--mob-text)", marginTop: "0.4rem" }}><strong>Observação:</strong> {o.nota}</div>
      )}
      {bulas.map((b) => (
        <div key={b.marca} style={{ fontSize: "0.8rem", color: "var(--mob-text)", marginTop: "0.4rem", paddingTop: "0.35rem", borderTop: "1px solid var(--mob-border)" }}>
          <strong>{b.marca}</strong>{b.em_estoque ? " (no estoque)" : ""}
          {b.dose && <div>Dose: {b.dose}</div>}
          {b.via && <div>Via: {b.via}</div>}
          {b.carencia && <div>{b.carencia}</div>}
        </div>
      ))}
      {o.marcas.length > 0 && !bulas.length && (
        <div style={{ fontSize: "0.8rem", color: "var(--mob-text)", marginTop: "0.3rem" }}>Marcas: {o.marcas.join(", ")}</div>
      )}
    </MobCard>
  );
}
