"""Transformador 1: apara e colapsa espacos. Digitacao manual no painel (spec §5)."""

from __future__ import annotations

import polars as pl

from messy_csv.contract import RAW_COLUMNS


def normalized_text_expr(column: str) -> pl.Expr:
    limpo = pl.col(column).str.replace_all(r"\s+", " ").str.strip_chars()
    return pl.when(limpo.str.len_chars() == 0).then(pl.lit(None, dtype=pl.String)).otherwise(limpo)


def is_clean_text_expr(column: str) -> pl.Expr:
    """True quando a celula ja esta normalizada. Nulo para celula nula.

    O nulo propagado e proposital: a metrica de limpeza textual mede so celulas
    preenchidas — ausencia e problema de completude, nao de formatacao.
    """
    valor = pl.col(column)
    return valor == valor.str.replace_all(r"\s+", " ").str.strip_chars()


def apply(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        normalized_text_expr(f"raw_{nome}").alias(f"t_{nome}") for nome in RAW_COLUMNS
    )
