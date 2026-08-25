"use client";
// Sanitário do Modo Curral — pula a escolha Curativa/Preventiva de
// FormSanidade.tsx: no curral "sempre será curativo" (decisão explícita do
// usuário), então vai direto para as 2 opções que já existem dentro de
// Curativa (Aplicação de remédio / Protocolo sanitário — as únicas 2 de
// TipoCurativa, nada a filtrar). Não reaproveita FormSanidade inteiro aqui
// (o `onVoltar` dele, `setModalidade(null)`, fica confuso de adaptar sem
// risco de regredir o fluxo completo); em vez disso reusa `CurativaForm`,
// já exportado standalone de FormSanidade.tsx exatamente para esse tipo de
// reaproveitamento (mesma técnica de FormProtocolos).
import { useState } from "react";
import dynamic from "next/dynamic";
import { Syringe, ClipboardList } from "lucide-react";
import { MobVoltar } from "@/components/mobile/ui";
import { useCache, type Animal, type EstoqueItem, GradeAcoes } from "@/components/mobile/lancar/comum";
import { fetchEstoque } from "@/lib/api";

const CurativaForm = dynamic(() => import("@/components/mobile/lancar/FormSanidade").then((m) => m.CurativaForm), { ssr: false });

type TipoCurativa = "aplicacao" | "protocolo";
const TITULOS: Record<TipoCurativa, string> = { aplicacao: "Aplicação de remédio", protocolo: "Protocolo sanitário" };

export function CurralSanitario({ animais }: { animais: Animal[] }) {
  // MESMA chave de cache que FormSanidade.tsx usa (`estoque_itens`) — evita
  // uma 2ª requisição se a tela Lançar completa já foi aberta na sessão.
  const estoque = useCache<EstoqueItem[]>("estoque_itens", () => fetchEstoque().then((d) => d.itens as EstoqueItem[]), []);
  const [tipo, setTipo] = useState<TipoCurativa | null>(null);

  if (!tipo) {
    // Mesmas 2 opções da grade "Curativa" de FormSanidade.tsx (`!tipo`) —
    // só que aqui já é a tela raiz do Sanitário, sem passar pela pergunta
    // Curativa/Preventiva.
    return (
      <GradeAcoes
        opcoes={[
          { id: "aplicacao", label: "Aplicação de remédio", icone: <Syringe size={28} />, cor: "var(--mob-azul)" },
          { id: "protocolo", label: "Protocolo sanitário", icone: <ClipboardList size={28} />, cor: "var(--mob-roxo)" },
        ]}
        onEscolher={(id) => setTipo(id as TipoCurativa)}
      />
    );
  }

  return (
    <>
      <MobVoltar titulo={TITULOS[tipo]} onVoltar={() => setTipo(null)} />
      <CurativaForm tipo={tipo} animais={animais} animalFixado={null} estoque={estoque.dados} />
    </>
  );
}
