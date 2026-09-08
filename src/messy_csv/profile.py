"""As seis dimensoes de qualidade do §7, medidas com a regua dos transformadores.

Nao ha um segundo parser aqui: `dates`, `currency`, `categories` e `whitespace`
exportam suas expressoes e este modulo as consome. Se "data valida" fosse
definida duas vezes, o before/after compararia reguas diferentes e a melhora
reportada incluiria a divergencia entre os dois codigos.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import polars as pl

from messy_csv import contract
from messy_csv.clean import categories, currency, dates, whitespace

VIEW_COLUMNS: tuple[str, ...] = ("order_id", "order_date", "customer", "category", "amount")
TEXT_COLUMNS: tuple[str, ...] = ("customer", "category")

DIMENSION_LABELS: dict[str, str] = {
    "completeness": "Completude",
    "uniqueness": "Unicidade",
    "temporal_validity": "Validade temporal",
    "category_consistency": "Consistência de categoria",
    "currency_normalization": "Normalização monetária",
    "text_cleanliness": "Limpeza textual",
}


@dataclass(frozen=True)
class ProfileResult:
    rows: int
    completeness: float
    uniqueness: float
    temporal_validity: float
    category_consistency: float
    currency_normalization: float
    text_cleanliness: float

    @property
    def dimensions(self) -> dict[str, float]:
        return {chave: float(getattr(self, chave)) for chave in DIMENSION_LABELS}

    @property
    def score(self) -> float:
        """Media aritmetica das seis: pesos iguais sao escolha deliberada (§7)."""
        valores = list(self.dimensions.values())
        return round(sum(valores) / len(valores) * 100, 1)

    def to_dict(self) -> dict[str, float | int]:
        return {"rows": self.rows, **self.dimensions, "score": self.score}


def _ausente_vira_nulo(nome: str) -> pl.Expr:
    """Celula vazia e ausencia, nao texto: o gerador a escreve como "" e o read_csv nao a nula."""
    coluna = pl.col(nome)
    return (
        pl.when(coluna.str.strip_chars() == "")
        .then(pl.lit(None, dtype=pl.String))
        .otherwise(coluna)
    )


def view_from_raw(df: pl.DataFrame) -> pl.DataFrame:
    """Aceita o frame carregado pelo pipeline (raw_*) ou o CSV cru."""
    if "raw_order_id" in df.columns:
        return df.select(_ausente_vira_nulo(f"raw_{nome}").alias(nome) for nome in VIEW_COLUMNS)
    return df.select(_ausente_vira_nulo(nome).alias(nome) for nome in VIEW_COLUMNS)


def view_from_clean(df: pl.DataFrame) -> pl.DataFrame:
    """Renderiza o dataset limpo de volta a forma textual medida no raw.

    E o que torna antes e depois comparaveis por construcao, e nao por duas
    implementacoes parecidas que se espera que continuem parecidas.
    """
    valor = pl.col("amount_original").round(2).cast(pl.String)
    return df.select(
        pl.col("order_id").cast(pl.String).alias("order_id"),
        pl.col("order_date").dt.to_string("%Y-%m-%d").alias("order_date"),
        pl.col("customer"),
        pl.col("category").cast(pl.String).alias("category"),
        pl.when(pl.col("currency_original") == "USD")
        .then(pl.format("USD {}", valor))
        .otherwise(pl.format("R$ {}", valor.str.replace(r"\.", ",")))
        .alias("amount"),
    )


def profile(view: pl.DataFrame, today: dt.date) -> ProfileResult:
    linhas = view.height
    if linhas == 0:
        raise ValueError("dataset vazio nao tem qualidade a medir")

    enriquecido = view.with_columns(
        dates.parse_date_expr("order_date").alias("_date"),
        currency.amount_expr("amount").alias("_amount"),
        _category_ok_expr().alias("_category_ok"),
    )

    preenchidas = sum(int(enriquecido[nome].is_not_null().sum()) for nome in VIEW_COLUMNS)
    datas_validas = int(
        enriquecido.select(
            (pl.col("_date").is_not_null() & dates.is_in_range_expr("_date", today)).sum()
        ).item()
    )

    textos = enriquecido.select(
        whitespace.is_clean_text_expr(nome).alias(nome) for nome in TEXT_COLUMNS
    )
    textos_limpos = sum(int(textos[nome].sum() or 0) for nome in TEXT_COLUMNS)
    textos_preenchidos = sum(int(textos[nome].count()) for nome in TEXT_COLUMNS)

    return ProfileResult(
        rows=linhas,
        completeness=preenchidas / (linhas * len(VIEW_COLUMNS)),
        uniqueness=enriquecido["order_id"].drop_nulls().str.strip_chars().n_unique() / linhas,
        temporal_validity=datas_validas / linhas,
        category_consistency=int(enriquecido["_category_ok"].sum()) / linhas,
        currency_normalization=int(enriquecido["_amount"].is_not_null().sum()) / linhas,
        # denominador so com celulas preenchidas: ausencia ja pesa em completude
        text_cleanliness=(textos_limpos / textos_preenchidos) if textos_preenchidos else 1.0,
    )


def _category_ok_expr() -> pl.Expr:
    """Linha em categoria canonica (§7).

    Duas formas contam: o rotulo que o mapa canonico reconhece, e o rotulo que
    ja e um valor do contrato. A segunda existe por causa de `Nao informado`,
    que missing.py produz e que de proposito nao esta no mapa canonico (D7).
    """
    canonica = categories.canonical_expr("category").is_not_null()
    ja_no_contrato = pl.col("category").str.strip_chars().is_in(list(contract.CATEGORIES))
    return (canonica | ja_no_contrato).fill_null(False)


def dirt_counts(view: pl.DataFrame) -> list[dict[str, object]]:
    """Linhas afetadas por cada sujeira do catalogo §5, para a tabela do relatorio."""
    enriquecido = view.with_columns(
        categories.canonical_expr("category").alias("_category"),
        currency.currency_expr("amount").alias("_currency"),
    )
    texto_sujo = pl.any_horizontal(
        ~whitespace.is_clean_text_expr(nome).fill_null(True) for nome in VIEW_COLUMNS
    )
    id_numerico = pl.col("order_id").str.strip_chars().str.contains(r"^\d+$")

    return [
        {
            "sujeira": "Whitespace",
            "causa": "Digitação manual no painel",
            "linhas": enriquecido.filter(texto_sujo).height,
        },
        {
            "sujeira": "Datas inconsistentes",
            "causa": "Três sistemas integrados",
            "linhas": enriquecido.filter(
                ~pl.col("order_date").str.contains(r"^\d{4}-\d{2}-\d{2}$").fill_null(False)
            ).height,
        },
        {
            "sujeira": "IDs duplicados",
            "causa": "Retry de integração com marketplace",
            "linhas": enriquecido.filter(id_numerico & pl.col("order_id").is_duplicated()).height,
        },
        {
            "sujeira": "Valores ausentes",
            "causa": "Falha parcial de importação",
            "linhas": enriquecido.filter(
                pl.any_horizontal(pl.col(nome).is_null() for nome in VIEW_COLUMNS)
            ).height,
        },
        {
            "sujeira": "Moedas mistas",
            "causa": "Loja vende para fora do Brasil",
            "linhas": enriquecido.filter(pl.col("_currency") == "USD").height,
        },
        {
            "sujeira": "Categorias inconsistentes",
            "causa": "Cadastro livre, sem enum",
            "linhas": enriquecido.filter(
                pl.col("_category").is_null()
                | (pl.col("_category") != pl.col("category").str.strip_chars())
            ).height,
        },
    ]
