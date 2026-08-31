"""Schema alvo e as nove regras que definem uma linha limpa.

Este e o unico modulo que decide se uma linha e aceita. Os transformadores
consertam o que da e deixam nulo o que nao da; a decisao mora aqui (D5).
"""

from __future__ import annotations

import datetime as dt

import polars as pl

CATEGORIES: tuple[str, ...] = (
    "Eletrônicos",
    "Moda",
    "Casa",
    "Livros",
    "Esporte",
    "Não informado",
)
CURRENCIES: tuple[str, ...] = ("BRL", "USD")

MIN_DATE = dt.date(2023, 1, 1)

RAW_COLUMNS: tuple[str, ...] = (
    "order_id",
    "order_date",
    "customer",
    "category",
    "amount",
)

CLEAN_COLUMNS: tuple[str, ...] = (
    "order_id",
    "order_date",
    "customer",
    "category",
    "amount_original",
    "currency_original",
    "amount_brl",
)

REJECT_REASON_SEPARATOR = "; "


class ContractError(RuntimeError):
    """Uma linha aprovada violou o schema alvo: erro de programa, nao de dado."""


def clean_schema() -> dict[str, pl.DataType]:
    return {
        "order_id": pl.Int64(),
        "order_date": pl.Date(),
        "customer": pl.String(),
        "category": pl.Enum(list(CATEGORIES)),
        "amount_original": pl.Float64(),
        "currency_original": pl.Enum(list(CURRENCIES)),
        "amount_brl": pl.Float64(),
    }


def reject_reasons(today: dt.date) -> list[tuple[str, pl.Expr]]:
    """Os nove motivos do contrato, na ordem em que aparecem em reject_reason."""
    order_id = pl.col("order_id")
    order_date = pl.col("order_date")
    amount = pl.col("amount_original")
    return [
        ("order_id inválido", order_id.is_null() | (order_id <= 0)),
        ("order_id duplicado irreconciliável", pl.col("is_duplicate_loser")),
        ("data inválida", order_date.is_null()),
        (
            "data fora do intervalo",
            order_date.is_not_null() & ((order_date < MIN_DATE) | (order_date > today)),
        ),
        ("cliente ausente", pl.col("t_customer").is_null()),
        ("categoria desconhecida", pl.col("category").is_null()),
        ("valor ausente", pl.col("t_amount").is_null()),
        ("valor inválido", pl.col("t_amount").is_not_null() & amount.is_null()),
        ("valor não positivo", amount.is_not_null() & (amount <= 0)),
    ]


def reject_reason_expr(today: dt.date) -> pl.Expr:
    parts = [
        pl.when(condicao).then(pl.lit(motivo)).otherwise(pl.lit(None, dtype=pl.String))
        for motivo, condicao in reject_reasons(today)
    ]
    return (
        pl.concat_list(parts)
        .list.drop_nulls()
        .list.join(REJECT_REASON_SEPARATOR)
        .alias("reject_reason")
    )


def validate(df: pl.DataFrame, today: dt.date) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Separa o frame do pipeline em aprovados (schema alvo) e rejeitados (originais)."""
    marked = df.with_columns(reject_reason_expr(today))

    rejected = marked.filter(pl.col("reject_reason") != "").select(
        *(pl.col(f"raw_{nome}").alias(nome) for nome in RAW_COLUMNS),
        pl.col("reject_reason"),
    )

    accepted = marked.filter(pl.col("reject_reason") == "").select(
        pl.col("order_id"),
        pl.col("order_date"),
        pl.col("t_customer").alias("customer"),
        pl.col("category").cast(pl.Enum(list(CATEGORIES))),
        pl.col("amount_original"),
        pl.col("currency_original").cast(pl.Enum(list(CURRENCIES))),
        pl.col("amount_brl"),
    )
    _assert_sem_nulos(accepted)
    return accepted, rejected


def _assert_sem_nulos(accepted: pl.DataFrame) -> None:
    """Rede de seguranca: nenhuma regra cobre cambio ausente, e dado errado nao sai daqui."""
    nulos = [
        nome for nome, quantidade in accepted.null_count().row(0, named=True).items() if quantidade
    ]
    if nulos:
        raise ContractError(
            f"linhas aprovadas contem nulo em: {', '.join(nulos)} — "
            "provavel competencia ausente em data/fx_rates.csv"
        )
