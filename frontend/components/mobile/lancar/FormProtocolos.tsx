"use client";
// Tela LANÇAR > PROTOCOLOS do app de campo — os 4 tipos de protocolo num só
// bloco: IATF, Indução de lactação, Sanitário e Customizado.
//
// Só o Customizado nasce aqui (nunca existiu lançamento dele no app, igual ao
// site, onde ele também só é lançado pela Central de Protocolos). Os outros
// três REAPROVEITAM o formulário que já existe no seu bloco temático —
// `ProtocoloIatf` (Reprodutivo), `FormInducaoLactacao` (Produção) e
// `CurativaForm` (Sanidade > Curativa). São dois caminhos até o mesmo
// lançamento, com uma só implementação: corrigir o formulário conserta os
// dois caminhos de uma vez.
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { CalendarClock, Pill, Bandage, ListChecks } from "lucide-react";
import { MobCampo, MobVoltar, MobAviso } from "@/components/mobile/ui";
import {
  fetchEstoque, fetchProtocolosCustomizadosParaLancar, fetchPessoas,
  type ProtocoloCustomizado,
} from "@/lib/api";
import {
  type Animal, type EstoqueItem, useCache, useEnvio, hoje,
  GradeAcoes, BotoesEscolha, SeletorAnimal,
} from "./comum";
import { ProtocoloIatf } from "./FormReprodutivo";
import { CurativaForm } from "./FormSanidade";

const FormInducaoLactacao = dynamic(
  () => import("@/components/FormInducaoLactacao").then((m) => m.FormInducaoLactacao), { ssr: false },
);

type Tipo = "iatf" | "inducao" | "sanitario" | "customizado";

const TITULOS: Record<Tipo, string> = {
  iatf: "Protocolo IATF",
  inducao: "Indução de lactação",
  sanitario: "Protocolo sanitário",
  customizado: "Protocolo personalizado",
};

export function FormProtocolos({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoque().then((d) => d.itens as EstoqueItem[]), []);
  const [tipo, setTipo] = useState<Tipo | null>(null);

  if (!tipo) {
    return (
      <GradeAcoes
        opcoes={[
          { id: "iatf", label: "IATF", icone: <CalendarClock size={28} />, cor: "var(--mob-roxo)" },
          { id: "inducao", label: "Indução de lactação", icone: <Pill size={28} />, cor: "var(--mob-azul)" },
          { id: "sanitario", label: "Sanitário", icone: <Bandage size={28} />, cor: "var(--mob-verde)" },
          { id: "customizado", label: "Personalizado", icone: <ListChecks size={28} />, cor: "var(--mob-dourado)" },
        ]}
        onEscolher={(id) => setTipo(id as Tipo)}
      />
    );
  }

  return (
    <>
      <MobVoltar titulo={TITULOS[tipo]} onVoltar={() => setTipo(null)} />
      {tipo === "iatf" && <ProtocoloIatf animais={animais} animalFixado={animalFixado} />}
      {tipo === "inducao" && (
        <div className="mob-form-embutido">
          <FormInducaoLactacao animais={animais as any} />
        </div>
      )}
      {tipo === "sanitario" && (
        <CurativaForm tipo="protocolo" animais={animais} animalFixado={animalFixado} estoque={estoque.dados} />
      )}
      {tipo === "customizado" && <ProtocoloCustomizadoApp animais={animais} animalFixado={animalFixado} />}
    </>
  );
}

// ── Protocolo personalizado (só existe aqui, no app) ────────────────────────
// Espelha o formulário do site (components/lancamentos/FormProtocoloCustomizado),
// reduzido ao essencial de campo: protocolo, alvo (animal ou fazenda), data e
// responsável. O nome do lançamento é montado pelo backend, não se digita.
function ProtocoloCustomizadoApp({ animais, animalFixado }: { animais: Animal[]; animalFixado: string | null }) {
  const { aviso, enviar, enviando, erroValidacao } = useEnvio();
  const [protocolos, setProtocolos] = useState<ProtocoloCustomizado[]>([]);
  const [pessoas, setPessoas] = useState<{ id?: number; nome: string; ativo?: boolean }[]>([]);
  const [protocoloId, setProtocoloId] = useState("");
  const [alvo, setAlvo] = useState<"animal" | "fazenda">("animal");
  const [matriz, setMatriz] = useState(animalFixado || "");
  const [data, setData] = useState(hoje());
  const [responsavel, setResponsavel] = useState("");

  useEffect(() => { fetchProtocolosCustomizadosParaLancar().then(setProtocolos).catch(() => setProtocolos([])); }, []);
  useEffect(() => { fetchPessoas().then(setPessoas as any).catch(() => setPessoas([])); }, []);

  const protocolo = protocolos.find((p) => String(p.id) === protocoloId);
  const rotuloDia = protocolo?.dia_inicial === 1 ? "D1" : "D0";

  function salvar() {
    if (!protocoloId) return erroValidacao("Selecione o protocolo.");
    if (alvo === "animal" && !matriz) return erroValidacao("Selecione a matriz (ou escolha Tarefa da fazenda).");
    if (!data) return erroValidacao(`Informe a data do ${rotuloDia}.`);
    enviar(
      "/protocolos-customizados/lancar",
      {
        protocolo_id: Number(protocoloId),
        animais: alvo === "animal" ? [matriz] : [],
        data_inicio: data,
        responsavel: responsavel || undefined,
      },
      `Protocolo ${protocolo?.nome || ""}${alvo === "animal" ? ` — matriz ${matriz}` : " — tarefa da fazenda"}`,
      () => { if (!animalFixado) setMatriz(""); },
      { ok: "Protocolo lançado — as etapas entram na agenda." },
    );
  }

  const pessoasAtivas = pessoas.filter((p) => p.ativo !== false);

  return (
    <>
      <MobCampo label="Protocolo">
        <select className="mob-input" value={protocoloId} onChange={(e) => setProtocoloId(e.target.value)}>
          <option value="">Selecione…</option>
          {protocolos.map((p) => <option key={p.id} value={p.id}>{p.nome} ({p.duracao_dias} dias)</option>)}
        </select>
      </MobCampo>

      <MobCampo label="Aplicar em">
        <BotoesEscolha
          opcoes={[{ valor: "animal", label: "Animal" }, { valor: "fazenda", label: "Tarefa da fazenda" }]}
          valor={alvo} onChange={setAlvo}
        />
      </MobCampo>

      {alvo === "animal" && (
        <MobCampo label="Matriz (nº / nome)">
          <SeletorAnimal animais={animais} valor={matriz} onChange={setMatriz} placeholder="Buscar matriz…" />
        </MobCampo>
      )}

      <MobCampo label={`Data do ${rotuloDia} (1º dia do cronograma)`}>
        <input type="date" className="mob-input" value={data} onChange={(e) => setData(e.target.value)} />
      </MobCampo>

      <MobCampo label="Responsável (opcional)">
        <select className="mob-input" value={responsavel} onChange={(e) => setResponsavel(e.target.value)}>
          <option value="">—</option>
          {pessoasAtivas.map((p) => <option key={p.id ?? p.nome} value={p.nome}>{p.nome}</option>)}
        </select>
      </MobCampo>

      {protocolo && (
        <p style={{ fontSize: "0.8rem", color: "var(--mob-muted)", marginBottom: "0.8rem" }}>
          Cronograma de {protocolo.duracao_dias} dia(s) — cada etapa vira uma pendência na Agenda.
        </p>
      )}

      {aviso && <MobAviso tipo={aviso.tipo}>{aviso.msg}</MobAviso>}
      <button type="button" className="mob-btn" onClick={salvar} disabled={enviando}>
        {enviando ? "Salvando…" : "Lançar protocolo"}
      </button>
    </>
  );
}
