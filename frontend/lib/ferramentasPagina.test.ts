import test from "node:test";
import assert from "node:assert/strict";
import { motivoBloqueioClique, podeEnviarComEnter } from "./ferramentasPagina.ts";

function falso(props: Record<string, unknown>): Element {
  const el = {
    innerText: "",
    type: "",
    name: "",
    placeholder: "",
    dataset: {},
    getAttribute: (n: string) => (props[`attr_${n}`] as string | undefined) ?? null,
    closest: () => null,
    ...props,
  };
  return el as unknown as Element;
}

test("clique em ação destrutiva ou de gravação é bloqueado", () => {
  for (const rotulo of ["Excluir", "Apagar animal", "Remover lote", "Cancelar pedido", "Salvar", "Confirmar", "Sair"]) {
    assert.ok(motivoBloqueioClique(falso({ innerText: rotulo })), rotulo);
  }
  assert.ok(motivoBloqueioClique(falso({ type: "submit", innerText: "Ok" })));
  assert.ok(motivoBloqueioClique(falso({ dataset: { destrutivo: "" } })));
  assert.ok(motivoBloqueioClique(falso({ innerText: "Ok", attr_aria_label: "x", "attr_aria-label": "Excluir lote" })));
});

test("clique em aba, filtro e detalhe continua liberado", () => {
  for (const rotulo of ["Rebanho", "Ver detalhes", "Lotes", "Próxima página", "Hoje"]) {
    assert.equal(motivoBloqueioClique(falso({ innerText: rotulo })), null, rotulo);
  }
});

test("Enter só vale em campo de busca ou filtro", () => {
  assert.equal(podeEnviarComEnter(falso({ type: "search" })), true);
  assert.equal(podeEnviarComEnter(falso({ placeholder: "Buscar animal" })), true);
  assert.equal(podeEnviarComEnter(falso({ name: "peso" })), false);
});
