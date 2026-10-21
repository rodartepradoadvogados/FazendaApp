"""
Schemas Pydantic do /sanitario — TODOS com `extra="forbid"`: campo
desconhecido é recusado (422) em vez de descartado em silêncio (AGENTS.md:
"o Pydantic descarta campo desconhecido sem erro"). Vocabulário fechado por
`Literal`, espelhando fazenda/models/sanitario_preventivo.py.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

TipoCaixa = Literal["vacina", "exame", "vermifugo", "outro"]
ProdutoModo = Literal["estoque", "sem_estoque", "vazio", "nao_se_aplica"]
DoseUnidade = Literal["mL", "dose", "g", "comprimido", "mL_por_kg", "mL_por_x_kg"]
EventoTipo = Literal["idade", "pre_parto", "entrada_ia", "parto", "secagem", "compra"]
PeriodoModo = Literal["meses", "frequencia", "continuo"]
AoFechar = Literal["perder", "manter", "descartar"]
Condicao = Literal["prenhe", "pre_parto", "lactacao", "seca", "apta_ia"]
ModoLeite = Literal["bloqueio", "descarte", "tanque"]
Resultado = Literal["positivo", "negativo", "inconclusivo", "nao_lido"]
ColunaFicha = Literal["brinco", "categoria", "lote", "idade", "peso", "dose", "partida", "aplicado", "resultado",
                      "assinatura", "obs"]


class Esquema(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ════════════════════════════════════════════════════════════════════════════
# Definição da caixa (wizard) — o MESMO formato volta no GET
# ════════════════════════════════════════════════════════════════════════════
class AtestadoIn(Esquema):
    destinatario_tipo: Optional[Literal["orgao", "laticinio", "comprador", "outro"]] = None
    destinatario_texto: Optional[str] = None
    pessoa_id: Optional[int] = None
    fornecedor_id: Optional[int] = None
    quando: Literal["aplicacao", "nfe", "primeiro"] = "primeiro"
    dias: int = Field(default=30, ge=0)


class ComprovacaoIn(Esquema):
    dias: int = Field(default=180, ge=1)
    aviso_dias: int = Field(default=30, ge=0)
    push: bool = True
    email: bool = False


class LeituraIn(Esquema):
    modo: Literal["so_resultado", "diferenca", "medidas"] = "so_resultado"
    horas: Optional[int] = None
    tolerancia: Optional[int] = None


class SerieDoseIn(Esquema):
    dose: int = Field(ge=2)
    apos_dias: int = Field(ge=1)
    janela_dias: int = Field(default=30, ge=1)


class CaixaDefinicaoIn(Esquema):
    # 1 identificação
    nome: Optional[str] = None
    nome_curto: Optional[str] = None
    tipo: TipoCaixa = "vacina"
    obrigatoria: bool = False
    # 2 produto
    produto_modo: ProdutoModo = "vazio"
    estoque_id: Optional[int] = None
    produto_texto: Optional[str] = None
    dose_valor: Optional[float] = None
    dose_unidade: Optional[DoseUnidade] = None
    dose_x_kg: Optional[float] = None
    peso_ausente: Literal["exigir", "estimado"] = "estimado"
    # 3 público
    pub_sexo: Literal["F", "M", "ambos"] = "ambos"
    pub_cat_modo: Literal["incluir", "excluir"] = "incluir"
    categorias: list[int] = Field(default_factory=list)
    pub_idade_min_dias: Optional[int] = None
    pub_idade_max_dias: Optional[int] = None
    pub_condicoes: list[Condicao] = Field(default_factory=list)
    pub_hist_tipo: Optional[Literal["ja", "nunca"]] = None
    pub_hist_caixa_id: Optional[int] = None
    # 4 janela
    jan_usa_evento: bool = False
    evento_tipo: Optional[EventoTipo] = None
    evento_de_dias: Optional[int] = None
    evento_ate_dias: Optional[int] = None
    jan_usa_periodo: bool = False
    periodo_modo: Optional[PeriodoModo] = None
    periodo_grupos: list[list[int]] = Field(default_factory=list)
    periodo_anos: Optional[int] = None
    periodo_ano_base: Optional[int] = None
    data_base_dia: int = 15
    comecar_em: Optional[date] = None
    ao_fechar: AoFechar = "manter"
    serie: list[SerieDoseIn] = Field(default_factory=list)
    # 5 aglomeração e aviso
    aglo_min: int = 4
    aviso_antecedencia_dias: int = 30
    aviso_fim_janela_dias: Optional[int] = None
    push_admin: bool = True
    # 6 veterinário e etapas legais
    legal_crmv_pedir: bool = False
    legal_atestado: Optional[AtestadoIn] = None
    legal_comprovacao: Optional[ComprovacaoIn] = None
    legal_leitura: Optional[LeituraIn] = None
    legal_reagente_aviso: bool = False
    legal_marca_texto: Optional[str] = None
    # 7 carência (NULL = não informada, nunca zero)
    car_leite_dias: Optional[int] = None
    car_carne_dias: Optional[int] = None
    car_modo_leite: Optional[ModoLeite] = None
    # 8 ficha de campo
    ficha_colunas: list[ColunaFicha] = Field(default_factory=list)
    observacao: Optional[str] = None

    def para_definicao(self) -> dict:
        d = self.model_dump()
        for k in ("legal_atestado", "legal_comprovacao", "legal_leitura"):
            v = getattr(self, k)
            d[k] = v.model_dump(exclude_none=True) if v is not None else None
        d["serie"] = [s.model_dump() for s in self.serie]
        return d


class CatalogoDefinicaoIn(CaixaDefinicaoIn):
    """O catálogo não conhece os IDs da fazenda: categorias por REFERÊNCIA de
    nome e "já/nunca recebeu" pela chave do catálogo (resolvidos na ativação)."""
    categorias_ref: list[str] = Field(default_factory=list)
    pub_hist_catalogo_chave: Optional[str] = None
    fallback_idade_min_dias: Optional[int] = None


class CaixaCriarIn(Esquema):
    definicao: CaixaDefinicaoIn
    estado: Literal["ativa", "inativa"] = "inativa"
    aceitar_carencia: bool = False


class CaixaVersaoIn(Esquema):
    definicao: CaixaDefinicaoIn
    aceitar_carencia: bool = False


class CaixaValidarIn(Esquema):
    definicao: CaixaDefinicaoIn
    etapa: Optional[int] = Field(default=None, ge=1, le=9)
    caixa_id: Optional[int] = None


class PreviaIn(Esquema):
    definicao: CaixaDefinicaoIn
    data_base: Optional[date] = None


class CaixasEstadoIn(Esquema):
    caixa_ids: list[int] = Field(min_length=1)
    acao: Literal["ativar", "inativar", "arquivar", "reativar"]
    motivo: Optional[str] = None


class AceiteCarenciaIn(Esquema):
    modo_leite: ModoLeite
    leite_dias: Optional[int] = Field(default=None, ge=0)
    carne_dias: Optional[int] = Field(default=None, ge=0)


class AtivarCatalogoIn(Esquema):
    estado: Literal["ativa", "inativa"] = "inativa"
    # Wizard "Do catálogo": a cópia só é criada ao CONCLUIR, já com os ajustes
    # feitos nas etapas (vira a versão 1, ligada ao catálogo). Sem `definicao`,
    # copia o item do catálogo como está.
    definicao: Optional[CaixaDefinicaoIn] = None
    aceitar_carencia: bool = False


class ParametrosIn(Esquema):
    uf: Optional[str] = None
    prazos_legais_ativo: Optional[bool] = None
    antecedencia_padrao_dias: Optional[int] = Field(default=None, ge=0)
    corrigir_ate: Optional[Literal["fechar_dia"]] = None
    dose_externa_sem_data: Optional[Literal["contar", "nao_contar"]] = None
    peso_estimado: Optional[Literal["aceitar", "exigir"]] = None
    modo_tuberculina: Optional[Literal["so_resultado", "diferenca", "medidas"]] = None
    aviso_offline_horas: Optional[int] = Field(default=None, ge=1)


# ════════════════════════════════════════════════════════════════════════════
# Dias ("Vacina"/"Exame") e registros
# ════════════════════════════════════════════════════════════════════════════
class VeterinarioIn(Esquema):
    pessoa_id: Optional[int] = None
    texto: Optional[str] = None
    crmv: Optional[str] = None


class ProdutoIn(Esquema):
    modo: Optional[ProdutoModo] = None
    estoque_id: Optional[int] = None
    lote_estoque_id: Optional[int] = None
    texto: Optional[str] = None
    dose_valor: Optional[float] = None
    dose_unidade: Optional[DoseUnidade] = None
    dose_x_kg: Optional[float] = None


class DiaItemIn(Esquema):
    animal_id: int
    caixa_id: Optional[int] = None
    caixa_ids: Optional[list[int]] = None


class ConsentimentoIn(Esquema):
    animal_id: int
    caixa_id: Optional[int] = None
    aceito: bool
    motivo_exibido: Optional[str] = None
    quer_atestado: Optional[bool] = None
    atestado_destinatario: Optional[str] = None


class DecisaoRiscosIn(Esquema):
    decisao: Literal["manter", "ajustar", "dividir"]
    texto: Optional[str] = None


class DiaCriarIn(Esquema):
    caixa_ids: list[int] = Field(min_length=1)
    data: date
    hora: Optional[str] = None
    data_prevista: Optional[date] = None
    veterinario: Optional[VeterinarioIn] = None
    produtos: dict[int, ProdutoIn] = Field(default_factory=dict)
    itens: Optional[list[DiaItemIn]] = None
    consentimentos: list[ConsentimentoIn] = Field(default_factory=list)
    decisao_riscos: Optional[DecisaoRiscosIn] = None
    observacao: Optional[str] = None


class DiaEditarIn(Esquema):
    versao_lock: int
    data: Optional[date] = None
    hora: Optional[str] = None
    data_prevista: Optional[date] = None
    veterinario: Optional[VeterinarioIn] = None
    produtos: dict[int, ProdutoIn] = Field(default_factory=dict)
    observacao: Optional[str] = None
    decisao_riscos: Optional[DecisaoRiscosIn] = None


class DiaItensIn(Esquema):
    itens: list[DiaItemIn] = Field(min_length=1)
    consentimentos: list[ConsentimentoIn] = Field(default_factory=list)


class SimularIn(Esquema):
    caixa_ids: list[int] = Field(min_length=1)
    data: date
    data_prevista: Optional[date] = None
    animal_ids: Optional[list[int]] = None


class CarenciaDecisaoIn(Esquema):
    modo: Optional[ModoLeite] = None
    leite_dias: Optional[int] = Field(default=None, ge=0)
    carne_dias: Optional[int] = Field(default=None, ge=0)


class DiaCarenciaIn(Esquema):
    caixa_id: int
    modo: ModoLeite
    leite_dias: Optional[int] = Field(default=None, ge=0)
    carne_dias: Optional[int] = Field(default=None, ge=0)


class ConsentimentoRegistroIn(Esquema):
    aceito: bool
    motivo_exibido: Optional[str] = None
    quer_atestado: Optional[bool] = None
    atestado_destinatario: Optional[str] = None


class RegistroIn(Esquema):
    chave_idempotencia: Optional[str] = None
    animal_id: Optional[int] = None
    numero_animal: Optional[str] = None
    caixa_id: Optional[int] = None
    data: Optional[date] = None
    hora: Optional[str] = None
    dose_num: Optional[int] = Field(default=None, ge=1)
    produto: Optional[ProdutoIn] = None
    peso_kg: Optional[float] = Field(default=None, gt=0)
    partida_texto: Optional[str] = None
    fabricante: Optional[str] = None
    validade: Optional[date] = None
    aplicador_pessoa_id: Optional[int] = None
    aplicador_texto: Optional[str] = None
    veterinario_pessoa_id: Optional[int] = None
    veterinario_texto: Optional[str] = None
    crmv_texto: Optional[str] = None
    resultado: Optional[Resultado] = None
    resultado_valor: Optional[float] = None
    resultado_detalhe: Optional[dict] = None
    atestado_numero: Optional[str] = None
    atestado_destinatario: Optional[str] = None
    consentimento: Optional[ConsentimentoRegistroIn] = None
    carencia: Optional[CarenciaDecisaoIn] = None


class DiaRegistrosIn(Esquema):
    registros: list[RegistroIn] = Field(min_length=1)
    canal: Literal["site", "app", "curral"] = "site"
    dispositivo_uid: Optional[str] = None
    carencia: dict[int, CarenciaDecisaoIn] = Field(default_factory=dict)


class DiaAplicarIn(Esquema):
    item_ids: Optional[list[int]] = None
    hora: Optional[str] = None
    aplicador_pessoa_id: Optional[int] = None
    aplicador_texto: Optional[str] = None
    canal: Literal["site", "app", "curral"] = "site"
    carencia: dict[int, CarenciaDecisaoIn] = Field(default_factory=dict)


class DesfazerIn(Esquema):
    registro_ids: list[int] = Field(min_length=1)


class EstornoIn(Esquema):
    motivo: str = Field(min_length=1)


class ResultadoIn(Esquema):
    resultado: Resultado
    resultado_valor: Optional[float] = None
    resultado_detalhe: Optional[dict] = None
    veterinario_pessoa_id: Optional[int] = None
    veterinario_texto: Optional[str] = None
    crmv_texto: Optional[str] = None


class FecharDiaIn(Esquema):
    faltantes: Literal["voltar", "dispensar"] = "voltar"
    motivo: Optional[str] = None


class CancelarDiaIn(Esquema):
    motivo: Optional[str] = None


class DispensaItemIn(Esquema):
    caixa_id: int
    animal_id: int
    ciclo_chave: Optional[str] = None
    dose_num: Optional[int] = None


class DispensarIn(Esquema):
    itens: list[DispensaItemIn] = Field(min_length=1)
    acao: Literal["dispensar", "descartar"] = "dispensar"
    motivo: Optional[str] = None


class ConflitoDecisaoIn(Esquema):
    manter: Literal["existente", "novo"]


class PrazoCumprirIn(Esquema):
    documento_numero: Optional[str] = None
    cumprido_em: Optional[date] = None


# ════════════════════════════════════════════════════════════════════════════
# Lançamento simples / ficha / app
# ════════════════════════════════════════════════════════════════════════════
class AtestadoLancIn(Esquema):
    numero: Optional[str] = None
    destinatario: Optional[str] = None


class LancamentoSimplesIn(Esquema):
    caixa_id: Optional[int] = None
    outro_texto: Optional[str] = None
    data: date
    retroativo_motivo: Optional[str] = None
    origem: Literal["lancamento_simples", "ficha"] = "lancamento_simples"
    animal_ids: list[int] = Field(default_factory=list)
    numeros: list[str] = Field(default_factory=list)
    produto: Optional[ProdutoIn] = None
    peso_kg: dict[int, float] = Field(default_factory=dict)
    aplicador_pessoa_id: Optional[int] = None
    aplicador_texto: Optional[str] = None
    veterinario_pessoa_id: Optional[int] = None
    veterinario_texto: Optional[str] = None
    crmv_texto: Optional[str] = None
    atestado: Optional[AtestadoLancIn] = None
    carencia: Optional[CarenciaDecisaoIn] = None
    resultados: dict[int, Resultado] = Field(default_factory=dict)
    consentimentos: list[ConsentimentoIn] = Field(default_factory=list)
    chave_lote: Optional[str] = None


class RegistroSyncIn(RegistroIn):
    dia_id: Optional[int] = None
    outro_texto: Optional[str] = None
    # Lançamento simples retroativo guardado no celular (sem dia): o motivo
    # vai junto pela fila e fica no registro + log "registro.retroativo".
    retroativo_motivo: Optional[str] = None


class CienciaPreparacaoIn(Esquema):
    """Ciência nominal da preparação pré-curral: quem começou o dia com itens
    da conferência em aberto. Vai pela fila offline do app (Idempotency-Key)."""
    itens_abertos: list[str] = Field(default_factory=list)
    pessoa_id: Optional[int] = None
    texto: Optional[str] = None
    em: Optional[datetime] = None
    dispositivo_uid: Optional[str] = None


class SincronizarIn(Esquema):
    dispositivo_uid: str = Field(min_length=1)
    nome: Optional[str] = None
    registros: list[RegistroSyncIn] = Field(default_factory=list)
    fila_pendentes_restantes: int = Field(default=0, ge=0)


class HeartbeatIn(Esquema):
    dispositivo_uid: str = Field(min_length=1)
    nome: Optional[str] = None
    fila_pendentes: int = Field(default=0, ge=0)
    fila_mais_antigo_em: Optional[datetime] = None


# ════════════════════════════════════════════════════════════════════════════
# Cockpit CowData — catálogo central
# ════════════════════════════════════════════════════════════════════════════
class CatalogoCriarIn(Esquema):
    chave: str = Field(min_length=1, pattern=r"^[a-z0-9_]+$")
    nome: str = Field(min_length=1)
    tipo: TipoCaixa = "vacina"
    padrao_fabrica: bool = False
    ativo: bool = True
    uf_sugerida: Optional[str] = None
    definicao: CatalogoDefinicaoIn
    nota_mudanca: Optional[str] = None
    base_legal: Optional[str] = None


class CatalogoEditarIn(Esquema):
    nome: Optional[str] = None
    ativo: Optional[bool] = None
    padrao_fabrica: Optional[bool] = None
    uf_sugerida: Optional[str] = None


class CatalogoVersaoIn(Esquema):
    definicao: CatalogoDefinicaoIn
    nota_mudanca: Optional[str] = None
    base_legal: Optional[str] = None
