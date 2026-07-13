"use client";
import { useState } from "react";
import { Layers, Beef, Truck, Package, ArrowRightLeft, Users, HeartPulse, HeartCrack, Wrench, Trash2, Dna, Wheat, Pill, Scale, Baby } from "lucide-react";
import CadastroLotes from "./CadastroLotes";
import CadastroAlimentacao from "./CadastroAlimentacao";
import CadastroPesagem from "./CadastroPesagem";
import CadastroRecria from "./CadastroRecria";
import Farmacia from "./Farmacia";
import CadastroAnimalForm from "./CadastroAnimalForm";
import CadastroFornecedores from "./CadastroFornecedores";
import CadastroEstoqueMeta from "./CadastroEstoqueMeta";
import CadastroEstoqueSemen from "./CadastroEstoqueSemen";
import CadastroMotivosMovimentacao from "./CadastroMotivosMovimentacao";
import CadastroMotivosBaixa from "./CadastroMotivosBaixa";
import CadastroServicos from "./CadastroServicos";
import CadastroPessoas from "./CadastroPessoas";
import CadastroSanitario, { type AbaCadastroSanitario } from "./CadastroSanitario";
import CadastroTouros from "./CadastroTouros";
import { FormExclusao } from "./FormExclusao";

export const ABAS_CADASTRO = [
  ["lotes", "Lotes", Layers],
  ["animal", "Animal (ficha)", Beef],
  ["fornecedores", "Fornecedores", Truck],
  ["estoque", "Itens de estoque", Package],
  ["estoque-semen", "Estoque de sêmen", Dna],
  ["touros", "Touros (NAAB)", Dna],
  ["farmacia", "Farmácia", Pill],
  ["alimentacao", "Alimentação", Wheat],
  ["motivos", "Motivos de movimentação", ArrowRightLeft],
  ["motivos-baixa", "Motivos de baixa", HeartCrack],
  ["servicos", "Serviços", Wrench],
  ["pessoas", "Pessoas", Users],
  ["sanitario", "Sanitário", HeartPulse],
  ["pesagem", "Pesagem do rebanho", Scale],
  ["recria", "Categorias", Baby],
  ["excluir", "Excluir cadastros", Trash2],
] as const;
export type AbaCadastro = (typeof ABAS_CADASTRO)[number][0];

// Rendida dentro de Configurações › Cadastro. A aba ativa (e a de Sanitário,
// um nível abaixo) vêm controladas de fora — Configurações é quem registra a
// árvore completa de sub-navegação (Configurações › Cadastro › Sanitário),
// já que só um componente pode ser dono do registro por vez sem risco de um
// sobrescrever o outro na mesma renderização.
export default function Cadastro({ aba: abaExterna, onAbaChange, abaSanitario: abaSanitarioExterna, onAbaSanitarioChange }: {
  aba?: AbaCadastro; onAbaChange?: (id: AbaCadastro) => void;
  abaSanitario?: AbaCadastroSanitario; onAbaSanitarioChange?: (id: AbaCadastroSanitario) => void;
} = {}) {
  const [abaInterna, setAbaInterna] = useState<AbaCadastro>("lotes");
  const [abaSanitarioInterna, setAbaSanitarioInterna] = useState<AbaCadastroSanitario>("principios");
  const aba = abaExterna ?? abaInterna;
  const abaSanitario = abaSanitarioExterna ?? abaSanitarioInterna;
  const setAbaSanitario = onAbaSanitarioChange ?? setAbaSanitarioInterna;

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Layers size={22} style={{ color: "var(--dourado)" }} /> Cadastro</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Dados mestres do site: lotes, animais, fornecedores/fabricantes/clientes e metadados de itens de estoque.
        </p>
      </div>

      {aba === "lotes" && <CadastroLotesSemMoldura />}
      {aba === "animal" && <CadastroAnimalForm />}
      {aba === "fornecedores" && <CadastroFornecedores />}
      {aba === "estoque" && <CadastroEstoqueMeta />}
      {aba === "estoque-semen" && <CadastroEstoqueSemen />}
      {aba === "touros" && <CadastroTouros />}
      {aba === "farmacia" && <Farmacia />}
      {aba === "alimentacao" && <CadastroAlimentacao />}
      {aba === "motivos" && <CadastroMotivosMovimentacao />}
      {aba === "motivos-baixa" && <CadastroMotivosBaixa />}
      {aba === "servicos" && <CadastroServicos />}
      {aba === "pessoas" && <CadastroPessoas />}
      {aba === "sanitario" && <CadastroSanitario abaControlada={abaSanitario} onAbaChange={setAbaSanitario} />}
      {aba === "pesagem" && <CadastroPesagem />}
      {aba === "recria" && <CadastroRecria />}
      {aba === "excluir" && (
        <>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Para remover um animal do rebanho, use Rebanho &gt; Baixar animal (registra motivo, gera histórico e,
            em caso de venda, o lançamento financeiro) — não uma exclusão direta da ficha.
          </p>
          <FormExclusao ocultarTipos={["animal"]} />
        </>
      )}
    </div>
  );
}

// CadastroLotes já traz seu próprio título/página (p-6 + h1) por ter existido
// antes desta aba unificada; aqui reaproveitamos o componente todo, só que
// dentro da mesma moldura das outras sub-abas de Cadastro.
function CadastroLotesSemMoldura() {
  return <div style={{ margin: "-1.5rem" }}><CadastroLotes /></div>;
}
