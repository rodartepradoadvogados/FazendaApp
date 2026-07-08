"use client";
import { useState } from "react";
import { Layers, Beef, Truck, Package } from "lucide-react";
import CadastroLotes from "./CadastroLotes";
import CadastroAnimalForm from "./CadastroAnimalForm";
import CadastroFornecedores from "./CadastroFornecedores";
import CadastroEstoqueMeta from "./CadastroEstoqueMeta";

const ABAS = [
  ["lotes", "Lotes", Layers],
  ["animal", "Animal (ficha)", Beef],
  ["fornecedores", "Fornecedores", Truck],
  ["estoque", "Itens de estoque", Package],
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
    </div>
  );
}

// CadastroLotes já traz seu próprio título/página (p-6 + h1) por ter existido
// antes desta aba unificada; aqui reaproveitamos o componente todo, só que
// dentro da mesma moldura das outras sub-abas de Cadastro.
function CadastroLotesSemMoldura() {
  return <div style={{ margin: "-1.5rem" }}><CadastroLotes /></div>;
}
