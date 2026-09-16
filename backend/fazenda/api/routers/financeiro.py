"""
Router financeiro — DRE, fluxo de caixa, KPIs e lançamentos financeiros
(contas a pagar/a receber, com parcelamento, conta bancária e importação de XML).
"""
from __future__ import annotations

import calendar
import html
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy import text
from sqlmodel import Session, select

from fazenda.auth import exigir_admin, exigir_nao_consultor, get_current_user, get_fazenda_atual_id, get_fazenda_id_escrita
from fazenda.database import get_session
from fastapi.responses import Response
from fazenda.models import (
    ApresentacaoEmbalagemEstoque, CentroCusto, ClassificacaoLancamento, ContaCorrente, ContaGerencial, EntregaLeiteMensal, Estoque, ExameDefinicao, ExameResultado, Fazenda, FormaPagamentoCadastro, Fornecedor,
    FornecedorClienteApelido,
    LancamentoAnexo, LancamentoItem, LancamentoRecorrente, LoteEstoque, ManutencaoPatrimonio, MovimentoEstoque, Patrimonio, Pessoa, PlanoContaGerencial, Sanidade,
    SeedFlag, Servico, TipoDocumento, TransferenciaContas, Usuario, ValeAvulso, ValeFuncionario,
)
from fazenda.rules import estoque_baixa
from fazenda.rules.auditoria import fazenda_id_seguro, mapa_usu
