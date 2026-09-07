"""Transformador 3: parse do simbolo monetario e conversao por competencia (D4).

Roda depois de `dates` porque o join de cambio usa o mes de order_date (§6.1).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

FX_PATH = Path("data/fx_rates.csv")

_USD_PREFIX = r"(?i)^(us\$|usd|\$)"
_ANY_SYMBOL = r"(?i)^(r\$|us\$|usd|brl|\$)\s*"


def load_fx_rates(path: Path = FX_PATH) -> pl.DataFrame:
    return pl.read_csv(
        path,
        schema={"month": pl.String(), "currency": pl.String(), "rate_to_brl": pl.Float64()},
    )


def currency_expr(column: str) -> pl.Expr:
    """USD quando ha simbolo americano; BRL por padrao (spec §12.4).

    Nulo quando o valor nao e parseavel: sem valor nao ha moeda a declarar, e
    deixar "BRL" numa linha sem valor poluiria a quarentena com dado inventado.
    """
    texto = pl.col(column).str.strip_chars()
    return (
        pl.when(amount_expr(column).is_null())
        .then(pl.lit(None, dtype=pl.String))
        .when(texto.str.contains(_USD_PREFIX))
        .then(pl.lit("USD"))
        .otherwise(pl.lit("BRL"))
    )


def amount_expr(column: str) -> pl.Expr:
    """BRL usa ponto de milhar e virgula decimal; USD usa o inverso."""
    texto = pl.col(column).str.strip_chars()
    sem_simbolo = texto.str.replace(_ANY_SYMBOL, "").str.strip_chars()
    numero = (
        pl.when(texto.str.contains(_USD_PREFIX))
        .then(sem_simbolo.str.replace_all(",", ""))
        .otherwise(sem_simbolo.str.replace_all(r"\.", "").str.replace_all(",", "."))
    )
    return (
        pl.when(numero.str.contains(r"^-?\d+(\.\d+)?$"))
        .then(numero.cast(pl.Float64, strict=False))
        .otherwise(pl.lit(None, dtype=pl.Float64))
    )


def apply(df: pl.DataFrame, fx: pl.DataFrame) -> pl.DataFrame:
    com_valores = df.with_columns(
        amount_expr("t_amount").alias("amount_original"),
        currency_expr("t_amount").alias("currency_original"),
        pl.col("order_date").dt.strftime("%Y-%m").alias("_month"),
    )

    tabela = fx.rename({"month": "_month", "currency": "currency_original", "rate_to_brl": "_rate"})
    convertido = com_valores.join(
        tabela, on=["_month", "currency_original"], how="left", validate="m:1"
    )

    return (
        convertido.with_columns(
            (pl.col("amount_original") * pl.col("_rate")).round(2).alias("amount_brl")
        )
        # o join nao promete preservar a ordem; source_index promete
        .sort("source_index")
        .drop("_month", "_rate")
    )
