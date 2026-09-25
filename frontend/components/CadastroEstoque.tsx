"use client";
import { useEffect, useState } from "react";
import { Package, MapPin, Tag, Target, Ruler, Box, Scale, BadgeDollarSign } from "lucide-react";
import CadastroEstoqueMeta from "./CadastroEstoqueMeta";
import { ListaCadastroSimples } from "./ListaCadastroSimples";
import {
  fetchLocaisArmazenamento, criarLocalArmazenamento, atualizarLocalArmazenamento, excluirLocalArmazenamento,
  fetchCategoriasEstoqueCadastro, criarCategoriaEstoque, atualizarCategoriaEstoque, excluirCategoriaEstoque,
  fetchFinalidadesEstoqueCadastro, criarFinalidadeEstoque, atualizarFinalidadeEstoque, excluirFinalidadeEstoque,
  fetchUnidadesEstoqueCadastro, criarUnidadeEstoque, atualizarUnidadeEstoque, excluirUnidadeEstoque,
  fetchUnidadesEmbalagemEstoqueCadastro, criarUnidadeEmbalagemEstoque, atualizarUnidadeEmbalagemEstoque, excluirUnidadeEmbalagemEstoque,
  fetchUnidadesMedidaEmbalagemEstoqueCadastro, criarUnidadeMedidaEmbalagemEstoque, atualizarUnidadeMedidaEmbalagemEstoque, excluirUnidadeMedidaEmbalagemEstoque,
  fetchPrecosReferenciaCowData, fetchConfigPrecosReferenciaCowData, configurarPrecosReferenciaCowData, type PrecoReferenciaCowData,
} from "@/lib/api";

const ABAS = [
  ["itens", "Itens de Estoque", Package],
  ["locais-armazenamento", "Local de Armazenamento", MapPin],
  ["categorias", "Classificação", Tag],
  ["finalidades", "Finalidade", Target],
  ["unidades", "Unidade", Ruler],
  ["unidades-embalagem", "Unidade (embalagem)", Box],
  ["unidades-medida", "Unidade de Medida", Scale],
  ["precos-referencia-cowdata", "Preços de referência CowData", BadgeDollarSign],
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
          <div className="card-header mb-3 flex items-center gap-2"><Tag size={16} /> Classificação</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
            Classificação do item de estoque (ex.: "Medicamentos e produtos veterinários", "Sêmen e genética") — mesma
            lista usada no cadastro de fornecedores.
          </p>
          <ListaCadastroSimples
            fetchFn={fetchCategoriasEstoqueCadastro} criarFn={criarCategoriaEstoque} atualizarFn={atualizarCategoriaEstoque} excluirFn={excluirCategoriaEstoque}
            nomeNovo="Nova classificação" placeholderNome='ex.: "Equipamentos e manutenção"' semRegistros="Nenhuma classificação cadastrada ainda."
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

      {aba === "precos-referencia-cowdata" && <PrecosReferenciaCowData />}
    </div>
  );
}

function formatBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

// Catálogo de preços-base sugeridos que a CowData mantém, cotizando com os
// PRÓPRIOS fornecedores (nunca aparecem aqui) — só um número de apoio pra
// fazenda decidir o próprio preço. Ver backend/fazenda/api/routers/
// estoque.py::precos_referencia_cowdata (leitura filtrada, nunca escreve em
// Estoque.valor_unitario) e fazenda/models/catalogo_cowdata.py.
function PrecosReferenciaCowData() {
  const [precos, setPrecos] = useState<PrecoReferenciaCowData[] | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [mostrar, setMostrar] = useState(true);
  const [salvando, setSalvando] = useState(false);

  useEffect(() => {
    fetchConfigPrecosReferenciaCowData().then((c) => setMostrar(c.mostrar_precos_referencia_cowdata)).catch(() => {});
    fetchPrecosReferenciaCowData().then(setPrecos).catch((e) => setErro(e instanceof Error ? e.message : "Erro ao carregar"));
  }, []);

  async function alternarVisibilidade() {
    setSalvando(true);
    try {
      const novo = !mostrar;
      await configurarPrecosReferenciaCowData(novo);
      setMostrar(novo);
    } catch (e) { setErro(e instanceof Error ? e.message : "Erro ao salvar"); } finally { setSalvando(false); }
  }

  return (
    <div className="card">
      <div className="card-header mb-3 flex items-center gap-2"><BadgeDollarSign size={16} /> Preços de referência CowData</div>
      <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginBottom: "0.8rem" }}>
        Valores de apoio que a CowData atribui a produtos-padrão após cotizar com fornecedores próprios — nunca o
        fornecedor, só o valor e a data em que foi atribuído. Não substitui nem preenche o preço do seu item de estoque:
        é só uma referência para você decidir.
      </p>
      <label className="flex items-center gap-2 mb-4" style={{ fontSize: "0.82rem", color: "var(--text)" }}>
        <input type="checkbox" checked={mostrar} disabled={salvando} onChange={alternarVisibilidade} />
        Mostrar preços de referência CowData (também no formulário de novo item de estoque)
      </label>
      {erro && <p style={{ color: "var(--red)", fontSize: "0.8rem", marginBottom: "0.6rem" }}>{erro}</p>}
      {!precos ? (
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Carregando…</p>
      ) : !mostrar ? (
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Desligado — ligue a caixa acima para ver os valores de novo.</p>
      ) : precos.length === 0 ? (
        <p style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Nenhum preço de referência publicado ainda.</p>
      ) : (
        <table className="fazenda-table" style={{ width: "100%" }}>
          <thead>
            <tr><th>Produto</th><th>Classificação</th><th style={{ textAlign: "right" }}>Valor</th><th>Atribuído em</th></tr>
          </thead>
          <tbody>
            {precos.map((p) => (
              <tr key={p.produto_padrao_id}>
                <td style={{ fontSize: "0.85rem" }}>{p.nome} {p.unidade && <span style={{ color: "var(--text-muted)" }}>({p.unidade})</span>}</td>
                <td style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>{p.classificacao || "—"}</td>
                <td style={{ fontSize: "0.85rem", textAlign: "right", fontWeight: 700 }}>{formatBRL(p.valor)}</td>
                <td style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{new Date(p.atribuido_em).toLocaleDateString("pt-BR")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
