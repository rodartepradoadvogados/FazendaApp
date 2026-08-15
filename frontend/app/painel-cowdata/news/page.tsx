"use client";
// Painel CowData > News — mesmo admin de matérias do blog (News) já usado em
// Configurações > News de qualquer fazenda. NoticiaNews/FonteNews não têm
// fazenda_id — o blog é global por natureza, uma só lista para todo mundo —
// e as rotas /news/materias* já são guardadas por exigir_pode_publicar
// (Usuario.pode_publicar_materias_blog), não por fazenda selecionada; o
// dono já nasce com essa permissão (ver backend/fazenda/auth.py). Reaproveita
// o componente inteiro: ele já usa .card/var(--surface)/var(--text) etc.,
// que o layout do Painel CowData escopa para a própria paleta escura
// (tokensPainel em app/painel-cowdata/layout.tsx), então não precisa de
// nenhuma adaptação visual.
import NewsAdmin from "@/components/NewsAdmin";

export default function NewsCowData() {
  return (
    <div style={{ padding: "1.4rem" }}>
      <NewsAdmin />
    </div>
  );
}
