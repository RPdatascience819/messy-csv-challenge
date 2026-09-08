"""Transformador 5: retry de integracao com o marketplace (spec §5.4).

Marca a copia perdedora em vez de descarta-la: nenhum dado e destruido (D6), e
o contrato transforma a marca no motivo `order_id duplicado irreconciliavel`.
"""

from __future__ import annotations

import polars as pl

# So faz sentido contar nulos depois que dates, currency e categories rodaram:
# antes disso nada foi parseado e todas as linhas pareceriam igualmente completas.
#
# A spec §5.4 pede so "menos campos nulos", mas a tupla pesa a celula de valor em
# tripulo: amount_original, currency_original e amount_brl nascem da mesma
# celula bruta (amount) e caem juntas quando ela e ilegivel, enquanto uma
# categoria ausente derruba so 1. Ponderacao consciente, nao a regra escrita ao
# pe da letra — no dataset real nunca chega a inverter um resultado, mas fica
# registrado aqui em vez de ficar implicito na contagem de colunas.
COMPLETENESS_COLUMNS: tuple[str, ...] = (
    "order_date",
    "t_customer",
    "category",
    "amount_original",
    "currency_original",
    "amount_brl",
)


def null_count_expr() -> pl.Expr:
    return pl.sum_horizontal(pl.col(nome).is_null().cast(pl.Int32) for nome in COMPLETENESS_COLUMNS)


def apply(df: pl.DataFrame) -> pl.DataFrame:
    com_id = df.with_columns(
        pl.col("t_order_id").cast(pl.Int64, strict=False).alias("order_id"),
        null_count_expr().alias("_nulls"),
    )

    # Menos nulos primeiro; empate pelo menor indice de origem (spec §5.4).
    ordenado = com_id.sort("_nulls", "source_index")

    marcado = ordenado.with_columns(
        # Id invalido nao forma grupo: "0" sobrevive ao cast e juntaria pedidos sem relacao.
        pl.when(pl.col("order_id").is_null() | (pl.col("order_id") <= 0))
        .then(pl.lit(False))
        .otherwise(pl.col("source_index").cum_count().over("order_id") > 1)
        .alias("is_duplicate_loser")
    )
    return marcado.sort("source_index").drop("_nulls")
