"""Transformador 6: a unica imputacao do projeto (D7).

Roda por ultimo, depois que a disputa de duplicatas ja foi decidida (§6.1).
"""

from __future__ import annotations

import polars as pl

UNKNOWN_CATEGORY = "Não informado"


def apply(df: pl.DataFrame) -> pl.DataFrame:
    # Celula vazia vira rotulo honesto; rotulo irrecuperavel continua nulo para
    # que o contrato o rejeite como `categoria desconhecida`.
    return df.with_columns(
        pl.when(pl.col("category").is_null() & pl.col("t_category").is_null())
        .then(pl.lit(UNKNOWN_CATEGORY))
        .otherwise(pl.col("category"))
        .alias("category")
    )
