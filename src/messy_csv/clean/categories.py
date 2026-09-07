"""Transformador 4: cadastro livre virou variante; o mapa canonico e explicito (§5.2)."""

from __future__ import annotations

import polars as pl

# Chaves ja normalizadas: minusculas, sem acento, separadores virados espaco.
CANONICAL_MAP: dict[str, str] = {
    "eletronicos": "Eletrônicos",
    "eletronico": "Eletrônicos",
    "eletro": "Eletrônicos",
    "moda": "Moda",
    "modas": "Moda",
    "vestuario": "Moda",
    "casa": "Casa",
    "casa e decoracao": "Casa",
    "casa decoracao": "Casa",
    "livros": "Livros",
    "livro": "Livros",
    "livraria": "Livros",
    "esporte": "Esporte",
    "esportes": "Esporte",
}

_ACCENTED = "áàâãäéèêëíìîïóòôõöúùûüçñ"
_PLAIN = "aaaaaeeeeiiiiooooouuuucn"


def normalize_expr(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .str.to_lowercase()
        .str.replace_many(list(_ACCENTED), list(_PLAIN))
        .str.replace_all(r"[_\-]+", " ")
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )


def canonical_expr(column: str) -> pl.Expr:
    """Nulo quando o rotulo e irrecuperavel: a decisao de rejeitar e do contrato."""
    return normalize_expr(column).replace_strict(
        CANONICAL_MAP, default=None, return_dtype=pl.String
    )


def apply(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(canonical_expr("t_category").alias("category"))
