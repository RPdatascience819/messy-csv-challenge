"""Transformador 2: datas de tres sistemas integrados, em quatro formatos (spec §5.1)."""

from __future__ import annotations

import datetime as dt

import polars as pl

from messy_csv.contract import MIN_DATE

DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%d/%m/%Y", "%b %d %Y")
DATETIME_FORMATS: tuple[str, ...] = ("%Y-%m-%d %H:%M:%S",)


def parse_date_expr(column: str) -> pl.Expr:
    """Tenta cada formato declarado, na ordem; o que nao casa vira nulo auditavel."""
    texto = pl.col(column).str.strip_chars()
    candidatos = [texto.str.strptime(pl.Date, formato, strict=False) for formato in DATE_FORMATS]
    candidatos += [
        # Data com hora: parse como Datetime e trunca. Spec §12.3.
        texto.str.strptime(pl.Datetime, formato, strict=False).dt.date()
        for formato in DATETIME_FORMATS
    ]
    return pl.coalesce(candidatos)


def is_in_range_expr(column: str, today: dt.date) -> pl.Expr:
    data = pl.col(column)
    return (data >= MIN_DATE) & (data <= today)


def apply(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(parse_date_expr("t_order_date").alias("order_date"))
