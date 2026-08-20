"""
Guarda de formato dos lotes do Milknews.

Estes arquivos passam a ser escritos por uma Routine agendada, sem ninguém
conferindo antes do commit (ver `.claude/skills/milknews/SKILL.md`). Quando o
autor de um arquivo é automático, a checagem também precisa ser — senão o único
momento em que o erro aparece é em produção.

E aqui o estrago é maior do que parece: `MILKNEWS_LOTES` é montado no IMPORT de
`fazenda/api/routers/news.py` (`_carregar_lotes_milknews` roda em nível de
módulo). Um JSON malformado não quebra só o blog — impede o módulo de importar,
e com ele a aplicação inteira de subir. Um lote ruim é um deploy derrubado.

O teste afirma só o que o carregador realmente exige, e nada além disso: não é
papel dele julgar o conteúdo jornalístico, que é responsabilidade das regras de
verificação da skill.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest

LOTES = Path(__file__).resolve().parent.parent / "fazenda" / "seed_data" / "milknews_lotes"

# Campos que `publicar_lotes_milknews` lê sem `.get()` (news.py:313-317) — sem
# eles a publicação estoura KeyError.
OBRIGATORIOS = ("manchete", "link")


def _arquivos() -> list[Path]:
    return sorted(LOTES.glob("*.json"))


# O nome do lote é `milknews_AAAAMMDD` COM SUFIXO OPCIONAL — os lotes reais
# incluem `milknews_20260718b`, `milknews_20260723_b` e
# `milknews_20260720_aprovadas`. A data são os 8 dígitos; o resto desambigua
# dois lotes do mesmo dia.
_DATA_NO_NOME = re.compile(r"^milknews_(\d{8})")


def _data_do_lote(arquivo: Path) -> date:
    achado = _DATA_NO_NOME.match(arquivo.stem)
    assert achado, f"nome fora do padrão milknews_AAAAMMDD[sufixo]: {arquivo.name}"
    return datetime.strptime(achado.group(1), "%Y%m%d").date()


def test_diretorio_de_lotes_existe():
    assert LOTES.is_dir(), f"diretório de lotes sumiu: {LOTES}"
    assert _arquivos(), "nenhum lote encontrado — o blog ficaria vazio"


@pytest.mark.parametrize("arquivo", _arquivos(), ids=lambda p: p.stem)
class TestFormatoDoLote:
    """Um caso por arquivo: quando quebrar, o nome do teste já diz qual lote."""

    def test_json_valido_e_lista(self, arquivo: Path):
        """A falha mais cara: JSON inválido impede o import de news.py."""
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        assert isinstance(dados, list), "o lote tem de ser uma LISTA de posts"
        assert dados, "lote vazio — publique nada em vez de um arquivo vazio"

    def test_campos_obrigatorios_presentes(self, arquivo: Path):
        for i, item in enumerate(json.loads(arquivo.read_text(encoding="utf-8"))):
            for campo in OBRIGATORIOS:
                assert (item.get(campo) or "").strip(), f"item {i}: `{campo}` vazio ou ausente"

    def test_link_seque_a_convencao_e_e_unico_no_lote(self, arquivo: Path):
        """`link` é a chave de deduplicação na publicação (news.py:313) — dois
        posts com o mesmo link fazem o segundo sumir silenciosamente."""
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        esperado = f"/news#milknews-{_data_do_lote(arquivo).isoformat()}-"
        links = [item["link"] for item in dados]
        assert len(set(links)) == len(links), f"links repetidos no lote: {links}"
        for link in links:
            assert link.startswith(esperado), f"{link} não segue {esperado}NN"

    def test_data_publicacao_bate_com_o_nome_do_arquivo(self, arquivo: Path):
        """Data no post diferente da data do lote foi sempre erro de cópia."""
        esperada = _data_do_lote(arquivo).isoformat()
        for i, item in enumerate(json.loads(arquivo.read_text(encoding="utf-8"))):
            if item.get("data_publicacao"):
                assert str(item["data_publicacao"]).strip() == esperada, (
                    f"item {i}: data_publicacao {item['data_publicacao']} != {esperada}"
                )

    def test_data_nao_esta_no_futuro(self, arquivo: Path):
        """Regra da skill, travada aqui: dado com data futura é erro, não furo.
        Já apareceu um resumo de busca citando 28/08 num dia 20/08 — publicar
        aquilo teria posto data impossível no blog.

        Compara contra HOJE, não contra o mtime do arquivo: num clone novo o
        mtime é a hora do checkout, sempre posterior à data do lote, e a
        asserção passaria sempre sem verificar nada."""
        publicada = _data_do_lote(arquivo)
        assert publicada <= date.today(), (
            f"lote afirma cobrir {publicada}, que ainda não chegou (hoje é {date.today()})"
        )

    def test_resumo_cabe_no_limite_do_carregador(self, arquivo: Path):
        """Acima de RESUMO_MAX o carregador TRUNCA em silêncio (news.py:229).
        Melhor falhar aqui que publicar frase cortada no meio."""
        from fazenda.api.routers.news import RESUMO_MAX

        for i, item in enumerate(json.loads(arquivo.read_text(encoding="utf-8"))):
            resumo = (item.get("resumo") or "").strip()
            assert len(resumo) <= RESUMO_MAX, (
                f"item {i}: resumo com {len(resumo)} caracteres, máximo {RESUMO_MAX}"
            )

    def test_fontes_sao_links_http(self, arquivo: Path):
        """`fontes` é o registro de auditoria de quem conferiu o quê. Texto solto
        ali não permite ninguém refazer a checagem."""
        for i, item in enumerate(json.loads(arquivo.read_text(encoding="utf-8"))):
            for fonte in item.get("fontes", []) or []:
                assert str(fonte).strip().startswith("http"), (
                    f"item {i}: fonte não é URL: {fonte!r}"
                )


def test_todos_os_lotes_carregam_pelo_proprio_loader():
    """Prova de fogo: roda a função que o app roda no import. Se isto passar,
    `news.py` importa."""
    from fazenda.api.routers.news import _carregar_lotes_milknews

    lotes = _carregar_lotes_milknews()
    assert len(lotes) == len(_arquivos())
    for chave, itens in lotes.items():
        assert isinstance(itens, list) and itens, f"lote {chave} vazio"
