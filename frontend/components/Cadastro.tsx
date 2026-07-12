"use client";
import { useState } from "react";
import { Layers, Beef, Truck, Package, ArrowRightLeft, Users, HeartPulse, HeartCrack, Wrench, Trash2, Dna, Wheat, Pill } from "lucide-react";
import CadastroLotes from "./CadastroLotes";
import CadastroAlimentacao from "./CadastroAlimentacao";
import Farmacia from "./Farmacia";
import CadastroAnimalForm from "./CadastroAnimalForm";
import CadastroFornecedores from "./CadastroFornecedores";
import CadastroEstoqueMeta from "./CadastroEstoqueMeta";
import CadastroEstoqueSemen from "./CadastroEstoqueSemen";
import CadastroMotivosMovimentacao from "./CadastroMotivosMovimentacao";
import CadastroMotivosBaixa from "./CadastroMotivosBaixa";
import CadastroServicos from "./CadastroServicos";
import CadastroPessoas from "./CadastroPessoas";
import CadastroSanitario from "./CadastroSanitario";
import { FormExclusao } from "./FormExclusao";

const ABAS = [
  ["lotes", "Lotes", Layers],
  ["animal", "Animal (ficha)", Beef],
  ["fornecedores", "Fornecedores", Truck],
  ["estoque", "Itens de estoque", Package],
  ["estoque-semen", "Estoque de sêmen", Dna],
  ["farmacia", "Farmácia", Pill],
  ["alimentacao", "Alimentação", Wheat],
  ["motivos", "Motivos de movimentação", ArrowRightLeft],
  ["motivos-baixa", "Motivos de baixa", HeartCrack],
  ["servicos", "Serviços", Wrench],
  ["pessoas", "Pessoas", Users],
  ["sanitario", "Sanitário", HeartPulse],
  ["excluir", "Excluir cadastros", Trash2],
] as const;

export default function Cadastro() {
  const [aba, setAba] = useState<(typeof ABAS)[number][0]>("lotes");

  return (
    <div className="p-6 animate-in">
      <div className="mb-4">
        <h1 className="text-2xl font-bold flex items-center gap-2"><Layers size={22} style={{ color: "var(--dourado)" }} /> Cadastro</h1>
        <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Dados mestres do site: lotes, animais, fornecedores/fabricantes/clientes e metadados de itens de estoque.
        </p>
      </div>

      <div className="flex items-center gap-2 mb-4" style={{ flexWrap: "wrap" }}>
        {ABAS.map(([id, label, Icon]) => (
          <button key={id} onClick={() => setAba(id)}
            style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8rem", padding: "0.4rem 0.9rem", borderRadius: "999px", cursor: "pointer",
              border: "1px solid " + (aba === id ? "var(--dourado)" : "var(--border)"),
              background: aba === id ? "rgba(94,26,46,0.4)" : "transparent",
              color: aba === id ? "var(--dourado-light)" : "var(--text-muted)", fontWeight: aba === id ? 700 : 500 }}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {aba === "lotes" && <CadastroLotesSemMoldura />}
      {aba === "animal" && <CadastroAnimalForm />}
      {aba === "fornecedores" && <CadastroFornecedores />}
      {aba === "estoque" && <CadastroEstoqueMeta />}
      {aba === "estoque-semen" && <CadastroEstoqueSemen />}
      {aba === "farmacia" && <Farmacia />}
      {aba === "alimentacao" && <CadastroAlimentacao />}
      {aba === "motivos" && <CadastroMotivosMovimentacao />}
      {aba === "motivos-baixa" && <CadastroMotivosBaixa />}
      {aba === "servicos" && <CadastroServicos />}
      {aba === "pessoas" && <CadastroPessoas />}
      {aba === "sanitario" && <CadastroSanitario />}
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
