"use client";
// Sub-tela PRODUÇÃO (LEITE): controle leiteiro por vaca (individual) ou por
// lote (pesagem de todas as vacas do lote de uma vez, salvando tudo junto),
// mais Pesagem corporal, BST, Secagem, Qualidade do leite, Venda mensal do
// leite e Indução de lactação — reaproveitando os mesmos componentes ricos
// do site dentro do envoltório ".mob-form-embutido", igual ao já feito em
// Financeiro (compra/venda de animal, folha de pagamento).
// Endpoint do desktop: POST /producao/controles (já aceita lista de entradas).
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { Milk, Scale, Moon, Pill, TestTube, Truck, Zap } from "lucide-react";
import { MobCampo, MobAviso, MobVoltar } from "@/components/mobile/ui";
import { BotoesEscolha, GradeAcoes, type Animal, useEnvio, hoje, SeletorAnimal } from "./comum";
import { type EstoqueItem } from "@/components/lancamentos/comumForms";
import { fetchAgenda, fetchEstoque, fetchSanidade } from "@/lib/api";
import { fetchComCache, enviarOuEnfileirar } from "@/lib/offline";

// Wrappers que trocam o authFetch direto dos formulários (compartilhados com
// o desktop) pela fila offline (enviarOuEnfileirar) — só usados aqui, no
// envoltório mobile; o desktop continua chamando a função de lib/api.ts
// direto (valor padrão de cada prop `salvar*`/`aplicarBst`/`marcarInapta`).
async function salvarPesagensOffline(dados: { data_pesagem: string; entradas: { numero_matriz: string; peso_kg: number }[] }) {
  const { enviado, resposta } = await enviarOuEnfileirar("/producao/pesagens", dados, `Pesagem corporal — ${dados.entradas.length} animal(is)`);
  return { criados: resposta?.criados ?? dados.entradas.length, enviado };
}
async function salvarSecagemOffline(dados: Record<string, unknown> & { numero_matriz: string }) {
  const { enviado, resposta } = await enviarOuEnfileirar("/producao/secagem", dados, `Secagem — ${dados.numero_matriz}`);
  return { lote_sugerido: resposta?.lote_sugerido, enviado };
}
async function salvarMovimentacaoOffline(dados: { data_movimento: string; motivo?: string; lote_destino_codigo: string; animais: string[]; origem?: string }) {
  const { enviado, resposta } = await enviarOuEnfileirar("/movimentacoes/mover", dados, `Movimentação — ${dados.animais.join(", ")} → ${dados.lote_destino_codigo}`);
  return { movidos: resposta?.movidos ?? 0, nao_encontrados: resposta?.nao_encontrados ?? [], enviado };
}
async function salvarInducaoOffline(dados: { protocolo_id: number; animais: string[]; data_d0: string; responsavel?: string; observacao?: string }) {
  const { enviado, resposta } = await enviarOuEnfileirar("/producao/inducao-lactacao", dados, `Indução de lactação — ${dados.animais.length} animal(is)`);
  return { criado: resposta?.criado, aviso: resposta?.aviso, animais: resposta?.animais ?? dados.animais.length, eventos_criados: resposta?.eventos_criados ?? 0, enviado };
}
async function salvarQualidadeOffline(dados: { data_coleta: string; numero_matriz: string | null }) {
  const { enviado } = await enviarOuEnfileirar("/producao/qualidade-leite", dados, `Qualidade do leite — ${dados.data_coleta}`);
  return { enviado };
}
async function salvarEntregaOffline(dados: { competencia: string }) {
  const { enviado } = await enviarOuEnfileirar("/producao/entrega-leite", dados, `Entrega de leite — ${dados.competencia}`);
  return { enviado };
}
async function aplicarBstOffline(dados: { numeros_matriz: string[] }) {
  const { enviado } = await enviarOuEnfileirar("/agenda/bst/aplicar", dados, `BST — ${dados.numeros_matriz.length} animal(is)`);
  return { enviado };
}
async function marcarInaptaBstOffline(dados: { numeros_matriz: string[]; inapta?: boolean }) {
  const { enviado } = await enviarOuEnfileirar("/agenda/bst/marcar-inapta", dados, `BST — marcar ${dados.inapta ? "inapta" : "apta"} (${dados.numeros_matriz.length})`);
  return { enviado };
}

// Cada sub-aba só baixa seu próprio formulário quando aberta pela 1ª vez —
// importante em conexão de campo, onde o app roda mais.
const FormPesagemCorporal = dynamic(() => import("@/components/FormPesagemCorporal").then((m) => m.FormPesagemCorporal), { ssr: false });
const PainelLancarBst = dynamic(() => import("@/components/PainelLancarBst").then((m) => m.PainelLancarBst), { ssr: false });
const FormSecagem = dynamic(() => import("@/components/FormSecagem").then((m) => m.FormSecagem), { ssr: false });
const FormQualidadeLeite = dynamic(() => import("@/components/FormQualidadeLeite").then((m) => m.FormQualidadeLeite), { ssr: false });
const FormEntregaLeite = dynamic(() => import("@/components/FormEntregaLeite").then((m) => m.FormEntregaLeite), { ssr: false });
const FormInducaoLactacao = dynamic(() => import("@/components/FormInducaoLactacao").then((m) => m.FormInducaoLactacao), { ssr: false });

type Sub = "controle" | "pesagem" | "bst" | "secagem" | "qualidade" | "entrega" | "inducao";

const TITULOS_SUB: Record<Sub, string> = {
  controle: "Controle leiteiro", pesagem: "Pesagem corporal", secagem: "Secagem",
  inducao: "Indução de lactação", qualidade: "Qualidade do leite", entrega: "Venda mensal do leite", bst: "BST",
};

export function FormProducao({ animais, animalFixado, restringirA }: { animais: Animal[]; animalFixado: string | null; restringirA?: Sub[] }) {
  const [sub, setSub] = useState<Sub | null>(null);
  const [agenda, setAgenda] = useState<any>(null);
  const carregarAgenda = () => {
    fetchComCache<any>("producao_agenda_bst", () => fetchAgenda()).then(({ dados }) => { if (dados) setAgenda(dados); });
  };
  useEffect(() => { if (sub === "bst" && !agenda) carregarAgenda(); }, [sub]); // eslint-disable-line react-hooks/exhaustive-deps

  // Estoque e produtos já lançados em Sanidade — só a Secagem precisa (lista
  // de medicamentos de secagem/vacina pré-parto), então busca só na 1ª vez
  // que o usuário abre essa aba.
  const [estoque, setEstoque] = useState<EstoqueItem[]>([]);
  const [produtosSanidade, setProdutosSanidade] = useState<string[]>([]);
  const [estoqueCarregado, setEstoqueCarregado] = useState(false);
  useEffect(() => {
    if (sub !== "secagem" || estoqueCarregado) return;
    setEstoqueCarregado(true);
    fetchComCache<{ itens: EstoqueItem[] }>("estoque_itens_completo", () => fetchEstoque())
      .then(({ dados }) => setEstoque(dados?.itens || []));
    fetchComCache<string[]>("producao_secagem_produtos_sanidade", () =>
      fetchSanidade().then((d) => Array.from(new Set((d.aplicacoes || d.registros || []).map((r: any) => r.produto).filter(Boolean))).sort() as string[])
    ).then(({ dados }) => setProdutosSanidade(dados || []));
  }, [sub, estoqueCarregado]);

  if (!sub) {
    // `restringirA` (opcional): usado pelo Modo Curral para mostrar só
    // controle/pesagem/secagem/BST — sem o prop (undefined), comportamento
    // idêntico ao de hoje, as 7 opções completas usadas por Lançar (LancarTela.tsx).
    const opcoes = [
      { id: "controle", label: "Controle leiteiro", icone: <Milk size={28} />, cor: "var(--mob-azul)" },
      { id: "pesagem", label: "Pesagem corporal", icone: <Scale size={28} />, cor: "var(--mob-roxo)" },
      { id: "secagem", label: "Secagem", icone: <Moon size={28} />, cor: "var(--mob-amarelo)" },
      { id: "inducao", label: "Indução de lactação", icone: <Pill size={28} />, cor: "var(--mob-verde)" },
      { id: "qualidade", label: "Qualidade do leite", icone: <TestTube size={28} />, cor: "var(--mob-laranja)" },
      { id: "entrega", label: "Venda mensal do leite", icone: <Truck size={28} />, cor: "var(--mob-vermelho)" },
      { id: "bst", label: "BST", icone: <Zap size={28} />, cor: "var(--mob-dourado-2)" },
    ].filter((o) => !restringirA || restringirA.includes(o.id as Sub));
    return <GradeAcoes opcoes={opcoes} onEscolher={(id) => setSub(id as Sub)} />;
  }

  return (
    <>
      <MobVoltar titulo={TITULOS_SUB[sub]} onVoltar={() => setSub(null)} />
      {sub === "controle" && <ControleLeiteiro animais={animais} animalFixado={animalFixado} />}
      {sub === "pesagem" && (
        <div className="mob-form-embutido">
          <FormPesagemCorporal animais={animais as any} lotes={lotesDe(animais)} salvarPesagens={salvarPesagensOffline} />
        </div>
      )}
      {sub === "secagem" && (
        <div className="mob-form-embutido">
          <FormSecagem
            animais={animais as any} estoque={estoque} produtos={produtosSanidade}
            salvarSecagem={salvarSecagemOffline as any} salvarMovimentacao={salvarMovimentacaoOffline as any}
          />
        </div>
      )}
      {sub === "inducao" && (
        <div className="mob-form-embutido">
          <FormInducaoLactacao animais={animais as any} salvarInducao={salvarInducaoOffline} />
        </div>
      )}
      {sub === "qualidade" && (
        <div className="mob-form-embutido">
          <FormQualidadeLeite animais={animais as any} salvarQualidade={salvarQualidadeOffline as any} />
        </div>
      )}
      {sub === "entrega" && (
        <div className="mob-form-embutido">
          <FormEntregaLeite salvarEntrega={salvarEntregaOffline as any} />
        </div>
      )}
      {sub === "bst" && (
        <div className="mob-form-embutido">
          {agenda ? (
            <PainelLancarBst agenda={agenda} onAtualizado={carregarAgenda} aplicarBst={aplicarBstOffline} marcarInapta={marcarInaptaBstOffline} />
          ) : <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem" }}>Carregando…</p>}
        </div>
      )}
    </>
  );
}

function lotesDe(animais: Animal[]): string[] {
  return Array.from(new Set(animais.map((a) => a.grupo_primario).filter((g): g is string => !!g))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }));
}

function ControleLeiteiro({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [modo, setModo] = useState<"vaca" | "lote">("vaca");
  const [animal, setAnimal] = useState(animalFixado || "");
  const [lote, setLote] = useState("");
  const [data, setData] = useState(hoje());
  const [o1, setO1] = useState("");
  const [o2, setO2] = useState("");
  const [o3, setO3] = useState("");
  const [porVaca, setPorVaca] = useState<Record<string, [string, string, string]>>({});

  const total = (Number(o1) || 0) + (Number(o2) || 0) + (Number(o3) || 0);

  /**
   * Só quem tem lactação ABERTA hoje — mesma fonte única que o backend usa
   * para aceitar o lançamento (`em_lactacao`, calculado da tabela `Lactacao`;
   * ver backend/fazenda/rules/lactacao.py).
   *
   * Este app não filtrava NADA: a lista de animais vinha inteira, e dava para
   * lançar controle leiteiro de bezerra, de novilha ou de vaca seca — o
   * registro ia direto para a produção do rebanho e para a curva de lactação.
   * `em_lactacao === undefined` (app novo contra backend antigo) mantém o
   * comportamento antigo, para a tela não ficar vazia durante o deploy.
   */
  const emLactacao = useMemo(() => animais.filter((a) => a.em_lactacao !== false), [animais]);
  const lotes = useMemo(
    () => Array.from(new Set(emLactacao.map((a) => a.grupo_primario).filter((g): g is string => !!g))).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
    [emLactacao],
  );
  const vacasDoLote = useMemo(() => (lote ? emLactacao.filter((a) => a.grupo_primario === lote) : []), [emLactacao, lote]);
  const setOrdVaca = (numero: string, idx: 0 | 1 | 2, valor: string) =>
    setPorVaca((p) => { const arr: [string, string, string] = [...(p[numero] || ["", "", ""])]; arr[idx] = valor; return { ...p, [numero]: arr }; });
  const totalVaca = (numero: string) => (porVaca[numero] || ["", "", ""]).reduce((s, v) => s + (Number(v) || 0), 0);
  const totalLote = vacasDoLote.reduce((s, a) => s + totalVaca(a.numero), 0);

  // Ordenha em branco vira `null` (não lançada), nunca `0` — um `0` gravado
  // como se fosse ordenha real puxaria a média de manhã/noite para baixo.
  function salvar() {
    if (modo === "vaca") {
      if (!animal) return erroValidacao("Selecione o animal.");
      if (total <= 0) return erroValidacao("Informe o leite de ao menos uma ordenha.");
      const ordenhas: (number | null)[] = [o1.trim() === "" ? null : Number(o1), o2.trim() === "" ? null : Number(o2)];
      if (o3.trim() !== "") ordenhas.push(Number(o3));
      enviar(
        "/producao/controles",
        { data_controle: data, entradas: [{ numero_matriz: animal, ordenhas }] },
        `Controle leiteiro — vaca ${animal} (${total.toFixed(1)} kg)`,
        () => { setO1(""); setO2(""); setO3(""); },
      );
    } else {
      if (!lote) return erroValidacao("Selecione o lote.");
      const entradas = vacasDoLote
        .map((a) => {
          const [v1, v2, v3] = porVaca[a.numero] || ["", "", ""];
          const ordenhas: (number | null)[] = [v1.trim() === "" ? null : Number(v1), v2.trim() === "" ? null : Number(v2)];
          if (v3.trim() !== "") ordenhas.push(Number(v3));
          return { numero_matriz: a.numero, ordenhas };
        })
        .filter((ent) => ent.ordenhas.some((v) => v !== null));
      if (!entradas.length) return erroValidacao("Informe a pesagem de ao menos uma vaca do lote.");
      enviar(
        "/producao/controles",
        { data_controle: data, entradas },
        `Controle leiteiro — lote ${lote} (${entradas.length} vaca(s), ${totalLote.toFixed(1)} kg)`,
        () => { setPorVaca({}); },
      );
    }
  }

  return (
    <>
      <MobCampo label="Lançar por">
        <BotoesEscolha
          opcoes={[{ valor: "vaca", label: "Vaca" }, { valor: "lote", label: "Lote" }]}
          valor={modo} onChange={setModo}
        />
      </MobCampo>

      {modo === "vaca" ? (
        <MobCampo label="Vaca em lactação (nº / nome)">
          <SeletorAnimal animais={emLactacao} valor={animal} onChange={setAnimal} placeholder="Buscar vaca em lactação…" />
        </MobCampo>
      ) : (
        <MobCampo label="Lote">
          <select className="mob-input" value={lote} onChange={(e) => setLote(e.target.value)}>
            <option value="">Selecione…</option>
            {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </MobCampo>
      )}

      <MobCampo label="Data do controle">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>

      {modo === "vaca" ? (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
            <MobCampo label="1ª ordenha (kg)">
              <input type="number" inputMode="decimal" className="mob-input" value={o1} onChange={(e) => setO1(e.target.value)} placeholder="kg" />
            </MobCampo>
            <MobCampo label="2ª ordenha (kg)">
              <input type="number" inputMode="decimal" className="mob-input" value={o2} onChange={(e) => setO2(e.target.value)} placeholder="kg" />
            </MobCampo>
          </div>
          <MobCampo label="3ª ordenha (kg, opcional)">
            <input type="number" inputMode="decimal" className="mob-input" value={o3} onChange={(e) => setO3(e.target.value)} placeholder="kg" />
          </MobCampo>
          <p style={{ margin: "0 0 0.9rem", fontSize: "0.9rem", fontWeight: 700, color: "var(--mob-verde)" }}>
            Total do dia: {total.toFixed(1)} kg
          </p>
        </>
      ) : lote ? (
        <div style={{ marginBottom: "0.9rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
            <span style={{ fontSize: "0.85rem", fontWeight: 700 }}>{vacasDoLote.length} vaca(s) do lote {lote}</span>
            <span style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--mob-verde)" }}>Total: {totalLote.toFixed(1)} kg</span>
          </div>
          <div style={{ display: "grid", gap: "0.6rem" }}>
            {vacasDoLote.map((a) => (
              <div key={a.numero} className="mob-input" style={{ padding: "0.6rem 0.7rem" }}>
                <div style={{ fontWeight: 700, marginBottom: "0.4rem" }}>Nº {a.numero}{a.del_dias != null ? ` · DEL ${a.del_dias}` : ""}</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "0.4rem" }}>
                  <input type="number" inputMode="decimal" className="mob-input" placeholder="1ª (kg)"
                    value={(porVaca[a.numero] || ["", "", ""])[0]} onChange={(e) => setOrdVaca(a.numero, 0, e.target.value)} />
                  <input type="number" inputMode="decimal" className="mob-input" placeholder="2ª (kg)"
                    value={(porVaca[a.numero] || ["", "", ""])[1]} onChange={(e) => setOrdVaca(a.numero, 1, e.target.value)} />
                  <input type="number" inputMode="decimal" className="mob-input" placeholder="3ª (opcional)"
                    value={(porVaca[a.numero] || ["", "", ""])[2]} onChange={(e) => setOrdVaca(a.numero, 2, e.target.value)} />
                </div>
              </div>
            ))}
            {!vacasDoLote.length && <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem" }}>Nenhuma vaca neste lote.</p>}
          </div>
        </div>
      ) : (
        <p style={{ color: "var(--mob-muted)", fontSize: "0.9rem", marginBottom: "0.9rem" }}>Selecione um lote para lançar a pesagem de todas as vacas de uma vez.</p>
      )}

      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
