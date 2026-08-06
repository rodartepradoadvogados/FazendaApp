"use client";
import { useState } from "react";
import { Package, MapPin, Tag, Target, Ruler, Box, Scale } from "lucide-react";
import CadastroEstoqueMeta from "./CadastroEstoqueMeta";
import { ListaCadastroSimples } from "./ListaCadastroSimples";
import {
  fetchLocaisArmazenamento, criarLocalArmazenamento, atualizarLocalArmazenamento, excluirLocalArmazenamento,
  fetchCategoriasEstoqueCadastro, criarCategoriaEstoque, atualizarCategoriaEstoque, excluirCategoriaEstoque,
  fetchFinalidadesEstoqueCadastro, criarFinalidadeEstoque, atualizarFinalidadeEstoque, excluirFinalidadeEstoque,
  fetchUnidadesEstoqueCadastro, criarUnidadeEstoque, atualizarUnidadeEstoque, excluirUnidadeEstoque,
  fetchUnidadesEmbalagemEstoqueCadastro, criarUnidadeEmbalagemEstoque, atualizarUnidadeEmbalagemEstoque, excluirUnidadeEmbalagemEstoque,
  fetchUnidadesMedidaEmbalagemEstoqueCadastro, criarUnidadeMedidaEmbalagemEstoque, atualizarUnidadeMedidaEmbalagemEstoque, excluirUnidadeMedidaEmbalagemEstoque,
} from "@/lib/api";

const ABAS = [
  ["itens", "Itens de Estoque", Package],
  ["locais-armazenamento", "Local de Armazenamento", MapPin],
  ["categorias", "Categoria", Tag],
  ["finalidades", "Finalidade", Target],
  ["unidades", "Unidade", Ruler],
  ["unidades-embalagem", "Unidade (embalagem)", Box],
  ["unidades-medida", "Unidade de Medida", Scale],
] as const;
// Reexportado para o Cadastro compor a árvore de sub-navegação (Configurações
// › Cadastro › Estoque › estas 7 abas) sem duplicar rótulos/ícones.
export type AbaCadastroEstoque = (typeof ABAS)[number][0];
export const ABAS_CADASTRO_ESTOQUE = ABAS;

export default function CadastroEstoque({ abaControlada, onAbaChange }: {
  abaControlada?: AbaCadastroEstoque; onAbaChange?: (id: AbaCadastroEstoque) => void;
} = {}) {
  const [abaInterna, setAbaInterna] = useState<AbaCadastroEstoque>("itens");
  const aba = abaControlada ?? abaInterna;

  return (
    <div>
      {aba === "itens" && <CadastroEstoqueMeta />}

      {aba === "locais-armazenamento" && (
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2"><MapPin size={16} /> Local de armazenamento</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Onde cada item de estoque fica guardado (ex.: "Farmácia 1", "Depósito", "Botijão 1") — escolhido no
            cadastro/edição do item.
          </p>
          <ListaCadastroSimples
            fetchFn={fetchLocaisArmazenamento} criarFn={criarLocalArmazenamento} atualizarFn={atualizarLocalArmazenamento} excluirFn={excluirLocalArmazenamento}
            nomeNovo="Novo local" placeholderNome='ex.: "Farmácia 1"' semRegistros="Nenhum local de armazenamento cadastrado ainda."
          />
        </div>
      )}

      {aba === "categorias" && (
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2"><Tag size={16} /> Categoria</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Categoria do item de estoque (ex.: "Medicamentos e produtos veterinários", "Sêmen e genética") — mesma
            lista usada no cadastro de fornecedores.
          </p>
          <ListaCadastroSimples
            fetchFn={fetchCategoriasEstoqueCadastro} criarFn={criarCategoriaEstoque} atualizarFn={atualizarCategoriaEstoque} excluirFn={excluirCategoriaEstoque}
            nomeNovo="Nova categoria" placeholderNome='ex.: "Equipamentos e manutenção"' semRegistros="Nenhuma categoria cadastrada ainda."
          />
        </div>
      )}

      {aba === "finalidades" && (
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2"><Target size={16} /> Finalidade</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Decide se o item aparece nos seletores de aplicação de medicamento/hormônio — só "Medicamento" entra
            nesses seletores.
          </p>
          <ListaCadastroSimples
            fetchFn={fetchFinalidadesEstoqueCadastro} criarFn={criarFinalidadeEstoque} atualizarFn={atualizarFinalidadeEstoque} excluirFn={excluirFinalidadeEstoque}
            nomeNovo="Nova finalidade" placeholderNome='ex.: "Material/Insumo"' semRegistros="Nenhuma finalidade cadastrada ainda."
          />
        </div>
      )}

      {aba === "unidades" && (
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2"><Ruler size={16} /> Unidade</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Unidade de estoque usada em toda baixa/consumo do item (ex.: "ml", "kg", "dose", "saca 30kg").
          </p>
          <ListaCadastroSimples
            fetchFn={fetchUnidadesEstoqueCadastro} criarFn={criarUnidadeEstoque} atualizarFn={atualizarUnidadeEstoque} excluirFn={excluirUnidadeEstoque}
            nomeNovo="Nova unidade" placeholderNome='ex.: "saca 30kg"' semRegistros="Nenhuma unidade cadastrada ainda."
          />
        </div>
      )}

      {aba === "unidades-embalagem" && (
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2"><Box size={16} /> Unidade (embalagem)</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Como o item vem embalado (ex.: "Saca", "Pote", "Frasco") — a Alimentação usa isso para converter kg
            necessários em número de embalagens a comprar.
          </p>
          <ListaCadastroSimples
            fetchFn={fetchUnidadesEmbalagemEstoqueCadastro} criarFn={criarUnidadeEmbalagemEstoque} atualizarFn={atualizarUnidadeEmbalagemEstoque} excluirFn={excluirUnidadeEmbalagemEstoque}
            nomeNovo="Nova unidade de embalagem" placeholderNome='ex.: "Pacote"' semRegistros="Nenhuma unidade de embalagem cadastrada ainda."
          />
        </div>
      )}

      {aba === "unidades-medida" && (
        <div className="card">
          <div className="card-header mb-3 flex items-center gap-2"><Scale size={16} /> Unidade de medida</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Conversão da embalagem (ex.: "kg/saca", "ml/frasco") — junto com a quantidade por embalagem, define
            quanto cabe em cada unidade de embalagem.
          </p>
          <ListaCadastroSimples
            fetchFn={fetchUnidadesMedidaEmbalagemEstoqueCadastro} criarFn={criarUnidadeMedidaEmbalagemEstoque} atualizarFn={atualizarUnidadeMedidaEmbalagemEstoque} excluirFn={excluirUnidadeMedidaEmbalagemEstoque}
            nomeNovo="Nova unidade de medida" placeholderNome='ex.: "litros/garrafa"' semRegistros="Nenhuma unidade de medida cadastrada ainda."
          />
        </div>
      )}
    </div>
  );
}
