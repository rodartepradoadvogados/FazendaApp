"use client";
// Sub-tela SANIDADE: aplicação avulsa de um produto OU lançamento de um
// protocolo sanitário — por animal ou por lote.
// Endpoints: POST /sanidade/aplicacoes | POST /sanidade/protocolos/lancamentos.
import { useEffect, useMemo, useState } from "react";
import { Syringe, ClipboardList } from "lucide-react";
import { MobCampo, MobAviso, MobVoltar } from "@/components/mobile/ui";
import { fetchEstoque, fetchProtocolosSanitarios, fetchMedicamentos, fetchPrincipiosAtivos, fetchDoencas } from "@/lib/api";
import { RESPONSAVEIS, VIAS_APLICACAO } from "@/lib/constants";
import {
  type Animal, type EstoqueItem, useCache, useEnvio, hoje,
  MobPill, LinhaPills, SeletorAnimal, unidadesCompativeis, GradeAcoes,
} from "./comum";

type Protocolo = { id: number; nome: string; eh_mastite?: boolean };
const CLASSIF_MASTITE = ["clinica", "subclinica", "ambiental"];

export function FormSanidade({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoque().then((d) => d.itens as EstoqueItem[]), []);
  const protocolos = useCache<Protocolo[]>("protocolos_sanitarios", () => fetchProtocolosSanitarios() as Promise<Protocolo[]>, []);

  const [tipo, setTipo] = useState<"aplicacao" | "protocolo" | null>(null);
  const [modo, setModo] = useState<"animal" | "lote">("animal");
  const [animal, setAnimal] = useState(animalFixado || "");
  const [lote, setLote] = useState("");
  const [data, setData] = useState(hoje());
  const [produto, setProduto] = useState("");
  const [quantidade, setQuantidade] = useState("");
  const [unidade, setUnidade] = useState("");
  const [via, setVia] = useState("");
  const [responsavel, setResponsavel] = useState("");
  const [aplicado, setAplicado] = useState(true);
  // Filtrar o medicamento por doença / princípio ativo (abre só os que casam).
  const [filtrarPor, setFiltrarPor] = useState<"todos" | "principio_ativo" | "doenca">("todos");
  const [criterio, setCriterio] = useState("");
  const [principiosNomes, setPrincipiosNomes] = useState<string[]>([]);
  const [doencasNomes, setDoencasNomes] = useState<string[]>([]);
  const [medicamentosFiltrados, setMedicamentosFiltrados] = useState<string[] | null>(null);
  useEffect(() => {
    fetchPrincipiosAtivos().then((d: any[]) => setPrincipiosNomes(d.map((p) => p.nome))).catch(() => {});
    fetchDoencas().then((d: any[]) => setDoencasNomes(d.map((x) => x.nome))).catch(() => {});
  }, []);
  useEffect(() => {
    if (filtrarPor === "todos" || !criterio) { setMedicamentosFiltrados(null); return; }
    const filtro = filtrarPor === "principio_ativo" ? { principio_ativo: criterio } : { doenca: criterio };
    fetchMedicamentos(filtro).then((m: any[]) => setMedicamentosFiltrados(m.map((x) => x.nome))).catch(() => setMedicamentosFiltrados([]));
  }, [filtrarPor, criterio]);
  // Protocolo sanitário
  const [protocoloId, setProtocoloId] = useState("");
  const [classifMastite, setClassifMastite] = useState("");
  const [obs, setObs] = useState("");

  // Lotes = grupos primários distintos dos animais (mesma base do desktop).
  const lotes = useMemo(() => {
    const set = new Set<string>();
    animais.forEach((a) => { if (a.grupo_primario) set.add(a.grupo_primario); });
    return Array.from(set).sort();
  }, [animais]);

  const produtos = useMemo(() => {
    const base = medicamentosFiltrados ?? estoque.dados.map((e) => e.nome);
    return [...base].sort();
  }, [estoque.dados, medicamentosFiltrados]);
  const compativeis = useMemo(() => unidadesCompativeis(estoque.dados.find((e) => e.nome === produto)?.unidade), [estoque.dados, produto]);
  const protoSel = protocolos.dados.find((p) => String(p.id) === protocoloId);

  function escolherProduto(nome: string) {
    setProduto(nome);
    const comp = unidadesCompativeis(estoque.dados.find((e) => e.nome === nome)?.unidade);
    setUnidade(comp[0] || "");
  }

  const alvoAnimais = () => modo === "animal"
    ? (animal ? [animal] : [])
    : animais.filter((a) => a.grupo_primario === lote).map((a) => a.numero);

  function salvar() {
    const alvo = alvoAnimais();
    if (!alvo.length) return erroValidacao(modo === "animal" ? "Selecione o animal." : "Selecione o lote.");

    if (tipo === "protocolo") {
      if (!protocoloId) return erroValidacao("Selecione o protocolo.");
      if (protoSel?.eh_mastite && alvo.length > 1) return erroValidacao("Protocolo de mastite: lance um animal por vez.");
      if (protoSel?.eh_mastite && !classifMastite) return erroValidacao("Informe a classificação da mastite.");
      enviar(
        "/sanidade/protocolos/lancamentos",
        {
          protocolo_id: Number(protocoloId), numeros_matriz: alvo, data_inicio: data,
          responsavel: responsavel || undefined, observacao: obs || undefined,
          classificacao_mastite: protoSel?.eh_mastite ? classifMastite : undefined,
        },
        `Protocolo ${protoSel?.nome || ""} — ${modo === "animal" ? `animal ${animal}` : `lote ${lote}`}`,
        () => { setProtocoloId(""); setClassifMastite(""); setObs(""); },
      );
      return;
    }

    if (!produto) return erroValidacao("Selecione o produto.");
    if (!(Number(quantidade) > 0)) return erroValidacao("Informe a quantidade.");
    if (!unidade) return erroValidacao("Selecione a unidade.");
    const aplicadoEfetivo = aplicado && data <= hoje();
    enviar(
      "/sanidade/aplicacoes",
      {
        data_aplicacao: data, animais: alvo, responsavel: responsavel || undefined, aplicado: aplicadoEfetivo,
        itens: [{ produto, quantidade: Number(quantidade), unidade, via: via || undefined }],
      },
      `Aplicação ${produto} — ${modo === "animal" ? `animal ${animal}` : `lote ${lote}`}`,
      () => { setProduto(""); setQuantidade(""); setUnidade(""); setVia(""); },
    );
  }

  if (!tipo) {
    return (
      <GradeAcoes
        opcoes={[
          { id: "aplicacao", label: "Aplicação de remédio", icone: <Syringe size={28} />, cor: "var(--mob-azul)" },
          { id: "protocolo", label: "Protocolo sanitário", icone: <ClipboardList size={28} />, cor: "var(--mob-vinho)" },
        ]}
        onEscolher={(id) => setTipo(id as "aplicacao" | "protocolo")}
      />
    );
  }

  return (
    <>
      <MobVoltar titulo={tipo === "aplicacao" ? "Aplicação de remédio" : "Protocolo sanitário"} onVoltar={() => setTipo(null)} />
      <LinhaPills>
        <MobPill ativa={modo === "animal"} onClick={() => setModo("animal")}>Animal</MobPill>
        <MobPill ativa={modo === "lote"} onClick={() => setModo("lote")}>Lote</MobPill>
      </LinhaPills>

      {modo === "animal" ? (
        <MobCampo label="Animal (nº / nome)">
          <SeletorAnimal animais={animais} valor={animal} onChange={setAnimal} placeholder="Buscar animal…" />
        </MobCampo>
      ) : (
        <MobCampo label="Lote">
          <select className="mob-input" value={lote} onChange={(e) => setLote(e.target.value)}>
            <option value="">Selecione o lote…</option>
            {lotes.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </MobCampo>
      )}

      <MobCampo label="Data">
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>

      {tipo === "protocolo" ? (
        <>
          <MobCampo label="Protocolo sanitário">
            <select className="mob-input" value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
              <option value="">Selecione o protocolo…</option>
              {protocolos.dados.map((p) => <option key={p.id} value={p.id}>{p.nome}{p.eh_mastite ? " (mastite)" : ""}</option>)}
            </select>
          </MobCampo>
          {protoSel?.eh_mastite && (
            <MobCampo label="Classificação da mastite">
              <select className="mob-input" value={classifMastite} onChange={(e) => setClassifMastite(e.target.value)}>
                <option value="">Selecione…</option>
                {CLASSIF_MASTITE.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </MobCampo>
          )}
          <MobCampo label="Observação">
            <input className="mob-input" value={obs} onChange={(e) => setObs(e.target.value)} />
          </MobCampo>
        </>
      ) : (
        <>
          <MobCampo label="Filtrar medicamento por">
            <select className="mob-input" value={filtrarPor} onChange={(e) => { setFiltrarPor(e.target.value as typeof filtrarPor); setCriterio(""); setProduto(""); }}>
              <option value="todos">Todos os medicamentos</option>
              <option value="principio_ativo">Princípio ativo</option>
              <option value="doenca">Doença</option>
            </select>
          </MobCampo>
          {filtrarPor !== "todos" && (
            <MobCampo label={filtrarPor === "principio_ativo" ? "Princípio ativo" : "Doença"}>
              <select className="mob-input" value={criterio} onChange={(e) => { setCriterio(e.target.value); setProduto(""); }}>
                <option value="">Selecione…</option>
                {(filtrarPor === "principio_ativo" ? principiosNomes : doencasNomes).map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </MobCampo>
          )}
          <MobCampo label="Produto / medicamento">
            <select className="mob-input" value={produto} onChange={(e) => escolherProduto(e.target.value)} disabled={filtrarPor !== "todos" && !criterio}>
              <option value="">Selecione o produto…</option>
              {produtos.map((nome) => {
                const est = estoque.dados.find((e) => e.nome === nome);
                return <option key={nome} value={nome}>{nome}{est?.quantidade != null ? ` (${est.quantidade} ${est.unidade || ""})` : ""}</option>;
              })}
            </select>
          </MobCampo>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.8rem" }}>
            <MobCampo label="Quantidade (dose)">
              <input type="number" inputMode="decimal" className="mob-input" value={quantidade} onChange={(e) => setQuantidade(e.target.value)} placeholder="0" />
            </MobCampo>
            <MobCampo label="Unidade">
              <select className="mob-input" value={unidade} onChange={(e) => setUnidade(e.target.value)}>
                {!unidade && <option value="">—</option>}
                {compativeis.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </MobCampo>
          </div>
          <MobCampo label="Via de aplicação">
            <select className="mob-input" value={via} onChange={(e) => setVia(e.target.value)}>
              <option value="">Selecione…</option>
              {VIAS_APLICACAO.map((v) => <option key={v} value={v}>{v}</option>)}
            </select>
          </MobCampo>
        </>
      )}

      <MobCampo label="Responsável">
        <select className="mob-input" value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
          <option value="">Selecione…</option>
          {RESPONSAVEIS.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
      </MobCampo>
      {tipo === "aplicacao" && (
        <MobCampo label="Já foi aplicado?">
          {data > hoje() ? (
            <p style={{ fontSize: "0.82rem", color: "var(--mob-ambar)" }}>Data futura — será <strong>programado na Agenda</strong> (não baixa estoque).</p>
          ) : (
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <MobPill ativa={aplicado} onClick={() => setAplicado(true)}>Sim (aplicar agora)</MobPill>
              <MobPill ativa={!aplicado} onClick={() => setAplicado(false)}>Não (programar)</MobPill>
            </div>
          )}
        </MobCampo>
      )}
      <button className="mob-btn" onClick={salvar} disabled={enviando}>{enviando ? "Salvando…" : "Salvar"}</button>
      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
    </>
  );
}
