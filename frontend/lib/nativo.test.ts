import test from "node:test";
import assert from "node:assert/strict";
import { mimeDoArquivo } from "./nativo.ts";

test("mimeDoArquivo escolhe o tipo pela extensão (o Android escolhe o leitor por ele)", () => {
  assert.equal(mimeDoArquivo("rebanho_lotes_2026-10-24.pdf"), "application/pdf");
  assert.equal(mimeDoArquivo("RELATORIO.PDF"), "application/pdf");
  assert.equal(mimeDoArquivo("planilha.xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
  assert.equal(mimeDoArquivo("dados.csv"), "text/csv");
  assert.equal(mimeDoArquivo("sem_extensao"), "application/octet-stream");
});
