"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity, RefreshCw, AlertTriangle, Baby, Syringe, ListChecks, HeartCrack,
  CheckCircle2, AlertOctagon, CalendarDays, Repeat, Milk,
} from "lucide-react";
import { fetchEstadosReprodutivos, fetchIndicadores, fetchAnimais, type EstadosReprodutivos, type EstadoReprodutivoAnimal } from "@/lib/api";
import { SecaoRecolhivel } from "@/components/ui";
import { BarraExport, TabelaManejo, fmtData, estiloNum, estiloMudo, type Col } from "@/components/RelatoriosManejo";
import { producaoDe, origemDe } from "@/lib/producaoAnimal";

/**
 * SituacaoReprodutivaAoVivo — segunda aba de "Listas" (ver app/relatorios/page.tsx).
 * Mesmos 9 recortes que já existem como drill-down de cards no app móvel
 * (frontend/components/mobile/rebanho/Indicadores.tsx, linhas ~140-370),
 * portados para tabelas de desktop. Diferença central para "Listas de
 * trabalho" (RelatoriosManejo.tsx): aqui o estado reprodutivo é recalculado
 * AO VIVO a partir dos lançamentos (parto/serviço/protocolo) a cada consulta,
 * não lido do Animal.sit_rep congelado do último CSV importado — ver
 * backend/fazenda/rules/estado_reprodutivo.py. Por isso não há semáforo de
 * urgência aqui (não é "atrasado/em dia", é a classificação em si).
 */

// Rótulo de cada estado — mesmas chaves de ROTULO_ESTADO em Indicadores.tsx
// (mobile, linhas 46-49) e de ROTULOS em estado_reprodutivo.py.
const ROTULO_ESTADO: Record<string, string> = {
  gestante: "Gestante", inseminada: "Inseminada", em_protocolo: "Em protocolo (IA atual)",
  pev: "PEV", apta: "Apta", atrasada: "Atrasada", nao_apta: "Não apta", vazia: "Vazia",
};

// "Vazias" é o guarda-chuva de quem não está prenhe, inseminada nem em
// protocolo — mesmo filtro de Indicadores.tsx linha 233.
const ESTADOS_VAZIAS = ["vazia", "apta", "atrasada", "pev", "nao_apta"];

// Dias entre a data de referência do snapshot e uma data-alvo ISO — cópia de
// Indicadores.tsx linhas 64-69 (diasAte).
function diasAte(referenciaIso: string, alvoIso?: string | null): number | null {
  if (!alvoIso) return null;
  const ref = new Date(`${referenciaIso}T00:00:00`);
  const alvo = new Date(`${alvoIso}T00:00:00`);
  return Math.round((alvo.getTime() - ref.getTime()) / 86400000);
}

// Rótulo do tipo de inseminação — cópia de Indicadores.tsx linhas 73-79.
function tipoInseminacaoLabel(a: EstadoReprodutivoAnimal): string {
  const tipo = (a.tipo_servico || "").toLowerCase();
  if (tipo.includes("monta") || tipo.includes("natural")) return "Monta natural";
  const protocolo = (a.protocolo || "").trim();
  if (protocolo && protocolo.toLowerCase() !== "cio natural") return "IA — IATF";
  return "IA — cio natural";
}

function ordenarNumero(a: { numero: string }, b: { numero: string }): number {
  const na = Number(a.numero), nb = Number(b.numero);
  if (!Number.isNaN(na) && !Number.isNaN(nb)) return na - nb;
  return a.numero.localeCompare(b.numero);
}

type Animal = {
  numero: string; grupo_primario?: string | null; categoria_abrev?: string | null;
  del_dias?: number | null;
  /** @deprecated Campo congelado do CSV do Ideagri — prefira `producao_kg`. */
  ult_cl_kg?: number | null;
  // Produção AO VIVO (AnimalProducaoAoVivo, lib/api.ts) — cai para `ult_cl_kg`
  // enquanto o backend novo não estiver publicado.
  producao_kg?: number | null;
  producao_data?: string | null;
  producao_origem?: "controle" | "congelado" | null;
};
type MatrizIep = { numero: string; iep_dias: number; data_ultimo_parto: string };


// Contagem em badge, no lugar do BadgeCores de semáforo (não se aplica aqui).
function BadgeContagem({ n }: { n: number }) {
  return <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{n} animal{n === 1 ? "" : "is"}</span>;
}

export default function SituacaoReprodutivaAoVivo() {
  const [estados, setEstados] = useState<EstadosReprodutivos | null>(null);
  const [iepPorMatriz, setIepPorMatriz] = useState<MatrizIep[]>([]);
  const [animais, setAnimais] = useState<Animal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const carregar = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchEstadosReprodutivos(), fetchIndicadores(), fetchAnimais() as Promise<Animal[]>])
      .then(([est, ind, an]) => {
        setEstados(est);
        setIepPorMatriz(ind?.reproducao?.iep_por_matriz || []);
        setAnimais(an);
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { carregar(); }, [carregar]);

  const dataRef = estados?.data_referencia || "";
  const estadoAnimais = useMemo(() => estados?.animais || [], [estados]);
  const porNumero = useMemo(() => new Map(animais.map((a) => [a.numero, a])), [animais]);
  const categoriaDe = useCallback(
    (numero: string) => porNumero.get(numero)?.categoria_abrev || porNumero.get(numero)?.grupo_primario || "—",
    [porNumero]
  );

  const gestantes = useMemo(() => estadoAnimais
    .filter((a) => a.estado === "gestante")
    .map((a) => ({ ...a, dias_para_parto: diasAte(dataRef, a.parto_previsto) })), [estadoAnimais, dataRef]);

  const inseminadas = useMemo(() => estadoAnimais
    .filter((a) => a.estado === "inseminada")
    .map((a) => ({ ...a, tipo: tipoInseminacaoLabel(a) })), [estadoAnimais]);

  const emProtocolo = useMemo(() => estadoAnimais
    .filter((a) => a.estado === "em_protocolo")
    .map((a) => ({ ...a, dia_protocolo: a.protocolo_dia_atual != null ? `D${a.protocolo_dia_atual}` : "—" })), [estadoAnimais]);

  const vazias = useMemo(() => estadoAnimais
    .filter((a) => ESTADOS_VAZIAS.includes(a.estado))
    .map((a) => ({ ...a, situacao: ROTULO_ESTADO[a.estado] || a.estado })), [estadoAnimais]);

  const aptas = useMemo(() => estadoAnimais.filter((a) => a.estado === "apta"), [estadoAnimais]);

  const atrasadas = useMemo(() => estadoAnimais.filter((a) => a.estado === "atrasada"), [estadoAnimais]);

  const partoPrevisto = useMemo(() => estadoAnimais
    .filter((e) => {
      if (e.estado !== "gestante" || !e.parto_previsto) return false;
      const faltam = diasAte(dataRef, e.parto_previsto);
      return faltam !== null && faltam >= 0 && faltam <= 30;
    })
    .map((e) => ({ ...e, dias_para_parto: diasAte(dataRef, e.parto_previsto) })), [estadoAnimais, dataRef]);

  const iepLista = useMemo(() => [...iepPorMatriz].sort(ordenarNumero)
    .map((m) => ({ ...m, categoria: categoriaDe(m.numero) })), [iepPorMatriz, categoriaDe]);

  const delProducao = useMemo(() => animais
    .filter((a) => (a.del_dias != null && a.del_dias >= 0) || (producaoDe(a) != null && (producaoDe(a) as number) > 0))
    .sort(ordenarNumero)
    // `producao_valor`/`producao_origem_efetiva` viram campos próprios da linha
    // para a ordenação por coluna (useOrdenacao lê `row[campo]`) e a exportação
    // enxergarem o mesmo valor com fallback já resolvido.
    .map((a) => ({ ...a, categoria: categoriaDe(a.numero), producao_valor: producaoDe(a), producao_origem_efetiva: origemDe(a) })), [animais, categoriaDe]);

  const carregando = loading && !estados;

  return (
    <div className="p-6 animate-in">
      <div className="mb-2 flex items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Activity size={22} style={{ color: "var(--dourado-light)" }} />
            Situação reprodutiva (ao vivo)
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
            Estas listas recalculam a situação de cada animal a partir dos lançamentos do próprio sistema (partos,
            serviços e protocolos) a cada consulta — mudam assim que você lança um evento, e não só no próximo
            upload de planilha.
          </p>
        </div>
        <button type="button" className="btn-ghost" onClick={carregar} title="Recarregar"
          style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {error && (
        <div className="alert-critico mb-4">
          <AlertTriangle size={18} />
          <span>Não foi possível carregar a situação reprodutiva: {error}</span>
        </div>
      )}
      {carregando && <p style={{ color: "var(--text-muted)" }}>Carregando…</p>}

      {estados && (
        <>
          <SecaoRecolhivel titulo="Gestantes" icon={Baby} descricao="Diagnóstico positivo vigente, sem perda de prenhez nem parto posterior." badge={<BadgeContagem n={gestantes.length} />}>
            <BarraExport
              titulo="Gestantes" nomeArquivoBase="reprodutivo_gestantes"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Dias de gestação", key: "dias_gestacao" }, { header: "Dias para o parto", key: "dias_para_parto" }, { header: "Parto previsto", key: "parto_previsto" }]}
              linhas={gestantes.map((g) => ({ numero: g.numero, categoria: g.categoria, dias_gestacao: g.dias_gestacao ?? "", dias_para_parto: g.dias_para_parto ?? "", parto_previsto: fmtData(g.parto_previsto) }))}
            />
            <TabelaManejo semaforo={false} linhas={gestantes} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "Dias de gestação", campo: "dias_gestacao", render: (r) => r.dias_gestacao ?? "—" },
              { header: "Dias para o parto", campo: "dias_para_parto", render: (r) => r.dias_para_parto ?? "—" },
              { header: "Parto previsto", campo: "parto_previsto", render: (r) => fmtData(r.parto_previsto) },
            ] as Col[]} />
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Inseminadas" icon={Syringe} descricao="Têm serviço vigente aguardando diagnóstico." badge={<BadgeContagem n={inseminadas.length} />}>
            <BarraExport
              titulo="Inseminadas" nomeArquivoBase="reprodutivo_inseminadas"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Lote atual", key: "lote" }, { header: "Data da inseminação", key: "data_servico" }, { header: "Tipo", key: "tipo" }]}
              linhas={inseminadas.map((a) => ({ numero: a.numero, categoria: a.categoria, lote: a.lote || "—", data_servico: fmtData(a.data_servico), tipo: a.tipo }))}
            />
            <TabelaManejo semaforo={false} linhas={inseminadas} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "Lote atual", campo: "lote", render: (r) => r.lote || "—" },
              { header: "Data da inseminação", campo: "data_servico", render: (r) => fmtData(r.data_servico), style: estiloMudo },
              { header: "Tipo", campo: "tipo", render: (r) => r.tipo },
            ] as Col[]} />
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Em protocolo (IA atual)" icon={ListChecks} descricao="Dentro da janela D0–D11 de IATF, ainda sem serviço neste ciclo." badge={<BadgeContagem n={emProtocolo.length} />}>
            <BarraExport
              titulo="Em protocolo (IA atual)" nomeArquivoBase="reprodutivo_protocolo"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Dia do protocolo", key: "dia_protocolo" }, { header: "D0", key: "d0" }]}
              linhas={emProtocolo.map((a) => ({ numero: a.numero, categoria: a.categoria, dia_protocolo: a.dia_protocolo, d0: fmtData(a.protocolo_d0) }))}
            />
            <TabelaManejo semaforo={false} linhas={emProtocolo} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "Dia do protocolo", campo: "dia_protocolo", render: (r) => r.dia_protocolo },
              { header: "D0", campo: "protocolo_d0", render: (r) => fmtData(r.protocolo_d0) },
            ] as Col[]} />
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Vazias" icon={HeartCrack} descricao="Quem não está prenhe, inseminada nem em protocolo (PEV, apta, atrasada ou não apta)." badge={<BadgeContagem n={vazias.length} />}>
            <BarraExport
              titulo="Vazias" nomeArquivoBase="reprodutivo_vazias"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Situação", key: "situacao" }, { header: "Lote atual", key: "lote" }]}
              linhas={vazias.map((a) => ({ numero: a.numero, categoria: a.categoria, situacao: a.situacao, lote: a.lote || "—" }))}
            />
            <TabelaManejo semaforo={false} linhas={vazias} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "Situação", campo: "situacao", render: (r) => r.situacao },
              { header: "Lote atual", campo: "lote", render: (r) => r.lote || "—" },
            ] as Col[]} />
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Aptas" icon={CheckCircle2} descricao="Passaram do PEV, ou tiveram diagnóstico negativo/perda sem serviço depois, ou são novilhas aptas." badge={<BadgeContagem n={aptas.length} />}>
            <BarraExport
              titulo="Aptas" nomeArquivoBase="reprodutivo_aptas"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "DEL", key: "del" }, { header: "Lote atual", key: "lote" }]}
              linhas={aptas.map((a) => ({ numero: a.numero, categoria: a.categoria, del: a.del_dias ?? "", lote: a.lote || "—" }))}
            />
            <TabelaManejo semaforo={false} linhas={aptas} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "DEL (dias pós-parto)", campo: "del_dias", render: (r) => r.del_dias ?? "—" },
              { header: "Lote atual", campo: "lote", render: (r) => r.lote || "—" },
            ] as Col[]} />
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Atrasadas" icon={AlertOctagon} descricao="Seriam aptas, mas já passaram do prazo máximo para o 1º serviço." badge={<BadgeContagem n={atrasadas.length} />}>
            <BarraExport
              titulo="Atrasadas" nomeArquivoBase="reprodutivo_atrasadas"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Lote atual", key: "lote" }]}
              linhas={atrasadas.map((a) => ({ numero: a.numero, categoria: a.categoria, lote: a.lote || "—" }))}
            />
            <TabelaManejo semaforo={false} linhas={atrasadas} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "Lote atual", campo: "lote", render: (r) => r.lote || "—" },
            ] as Col[]} />
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="Parto previsto (30 dias)" icon={CalendarDays} descricao="Gestantes com previsão de parto entre hoje e os próximos 30 dias." badge={<BadgeContagem n={partoPrevisto.length} />}>
            <BarraExport
              titulo="Parto previsto (30 dias)" nomeArquivoBase="reprodutivo_parto_previsto"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "Parto previsto", key: "parto_previsto" }, { header: "Dias de gestação", key: "dias_gestacao" }, { header: "Dias para o parto", key: "dias_para_parto" }]}
              linhas={partoPrevisto.map((e) => ({ numero: e.numero, categoria: e.categoria, parto_previsto: fmtData(e.parto_previsto), dias_gestacao: e.dias_gestacao ?? "", dias_para_parto: e.dias_para_parto ?? "" }))}
            />
            <TabelaManejo semaforo={false} linhas={partoPrevisto} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "Parto previsto", campo: "parto_previsto", render: (r) => fmtData(r.parto_previsto) },
              { header: "Dias de gestação", campo: "dias_gestacao", render: (r) => r.dias_gestacao ?? "—" },
              { header: "Dias para o parto", campo: "dias_para_parto", render: (r) => r.dias_para_parto ?? "—" },
            ] as Col[]} />
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="IEP por matriz" icon={Repeat} descricao="Intervalo entre partos de cada matriz com dois ou mais partos registrados." badge={<BadgeContagem n={iepLista.length} />}>
            <BarraExport
              titulo="IEP por matriz" nomeArquivoBase="reprodutivo_iep"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "IEP (dias)", key: "iep_dias" }, { header: "Último parto", key: "ultimo_parto" }]}
              linhas={iepLista.map((m) => ({ numero: m.numero, categoria: m.categoria, iep_dias: m.iep_dias, ultimo_parto: fmtData(m.data_ultimo_parto) }))}
            />
            <TabelaManejo semaforo={false} linhas={iepLista} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "IEP (dias)", campo: "iep_dias", render: (r) => `${r.iep_dias} dias` },
              { header: "Último parto", campo: "data_ultimo_parto", render: (r) => fmtData(r.data_ultimo_parto) },
            ] as Col[]} />
          </SecaoRecolhivel>

          <SecaoRecolhivel titulo="DEL e produção" icon={Milk} descricao="Dias em lactação e última produção conhecida de cada animal." badge={<BadgeContagem n={delProducao.length} />}>
            <BarraExport
              titulo="DEL e produção" nomeArquivoBase="reprodutivo_del_producao"
              colunas={[{ header: "Nº", key: "numero" }, { header: "Categoria", key: "categoria" }, { header: "DEL", key: "del" }, { header: "Última produção (L)", key: "producao" }, { header: "Origem da produção", key: "origem_producao" }]}
              linhas={delProducao.map((a) => ({
                numero: a.numero, categoria: a.categoria, del: a.del_dias ?? "", producao: a.producao_valor ?? "",
                // Rótulo honesto para quem abre a planilha: sem isso, a coluna
                // some a distinção entre um controle lançado no app e o valor
                // congelado do CSV que ela representa dentro do produto.
                origem_producao: a.producao_origem_efetiva === "congelado" ? "CSV importado (congelado)" : a.producao_origem_efetiva === "controle" ? "Controle leiteiro" : "",
              }))}
            />
            <TabelaManejo semaforo={false} linhas={delProducao} colunas={[
              { header: "Nº", campo: "numero", render: (r) => r.numero, style: estiloNum },
              { header: "Categoria", campo: "categoria", render: (r) => r.categoria, style: estiloMudo },
              { header: "DEL", campo: "del_dias", render: (r) => (r.del_dias != null ? `${r.del_dias} dias` : "—") },
              {
                header: "Última produção (L)", campo: "producao_valor", render: (r) => {
                  if (r.producao_valor == null) return "—";
                  const texto = r.producao_valor.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
                  // Rodapé, não alarme: só um asterisco mudo indicando que este
                  // valor não anda mais — quem quiser o porquê passa o mouse.
                  return r.producao_origem_efetiva === "congelado"
                    ? <span style={estiloMudo} title="Valor do último CSV importado — nenhum controle leiteiro lançado no app para este animal">{texto} *</span>
                    : texto;
                },
              },
            ] as Col[]} />
          </SecaoRecolhivel>
        </>
      )}
    </div>
  );
}
