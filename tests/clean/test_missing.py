from __future__ import annotations

import polars as pl

from messy_csv import contract
from messy_csv.clean import missing

_SCHEMA: dict[str, pl.DataType] = {
    "t_category": pl.String(),
    "category": pl.String(),
    "t_customer": pl.String(),
    "amount_original": pl.Float64(),
}


def _frame(t_category: str | None, category: str | None) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "t_category": [t_category],
            "category": [category],
            "t_customer": [None],
            "amount_original": [None],
        },
        schema=_SCHEMA,
    )


def test_categoria_ausente_vira_nao_informado() -> None:
    resultado = missing.apply(_frame(None, None))

    assert resultado["category"].to_list() == ["Não informado"]


def test_categoria_desconhecida_continua_nula() -> None:
    """ "misc" nao e ausencia, e rotulo irrecuperavel: quem decide e o contrato."""
    resultado = missing.apply(_frame("misc", None))

    assert resultado["category"].to_list() == [None]


def test_categoria_valida_nao_e_tocada() -> None:
    resultado = missing.apply(_frame("moda", "Moda"))

    assert resultado["category"].to_list() == ["Moda"]


def test_dinheiro_nunca_e_imputado() -> None:
    """D7: valor monetario inventado corrompe analise financeira."""
    resultado = missing.apply(_frame(None, None))

    assert resultado["amount_original"].to_list() == [None]


def test_cliente_nunca_e_imputado() -> None:
    """D7: sem identificacao nao ha pedido rastreavel."""
    resultado = missing.apply(_frame(None, None))

    assert resultado["t_customer"].to_list() == [None]


def test_nao_ha_coluna_de_flag_de_imputacao() -> None:
    """D7: com uma unica imputacao no projeto, a flag poluiria o contrato."""
    resultado = missing.apply(_frame(None, None))

    assert resultado.columns == ["t_category", "category", "t_customer", "amount_original"]


def test_rotulo_imputado_pertence_ao_contrato() -> None:
    """O cast de Enum do contrato aceita este rotulo — a igualdade nao pode ser coincidencia."""
    assert missing.UNKNOWN_CATEGORY in contract.CATEGORIES
