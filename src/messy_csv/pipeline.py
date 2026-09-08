"""Carga do CSV sujo, orquestracao dos seis transformadores e escrita dos artefatos."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from messy_csv import contract
from messy_csv.clean import categories, currency, dates, duplicates, missing, whitespace

RAW_PATH = Path("data/raw/orders_dirty.csv")
CLEAN_PATH = Path("data/clean/orders.csv")
REJECTS_PATH = Path("data/rejects/rejects.csv")


def load_raw(path: Path = RAW_PATH) -> pl.DataFrame:
    """Le tudo como texto (§4.1) e ancora a ordem de origem em source_index."""
    bruto = pl.read_csv(path, infer_schema=False)
    renomeado = bruto.rename({nome: f"raw_{nome}" for nome in contract.RAW_COLUMNS})
    return renomeado.with_row_index("source_index")


def transform(df: pl.DataFrame, fx: pl.DataFrame) -> pl.DataFrame:
    """A ordem e fixa e significativa (§6.1): trocar dois passos muda o resultado.

    Devolve o frame largo — raw_*, t_* e as colunas tipadas lado a lado — porque
    o relatorio precisa do antes e do depois na mesma linha (Task 13).
    """
    frame = whitespace.apply(df)
    frame = dates.apply(frame)
    frame = currency.apply(frame, fx)
    frame = categories.apply(frame)
    frame = duplicates.apply(frame)
    frame = missing.apply(frame)
    return frame


def clean_frame(
    df: pl.DataFrame, fx: pl.DataFrame, today: dt.date
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Valida contra o menor entre `today` e o teto que `fx` cobre (Ruling 26).

    Uma data sem competencia cadastrada nao tem taxa para converter: sem o
    grampeamento aqui, ela passaria pela regra de intervalo do contrato e so
    estouraria depois, em `_assert_sem_nulos`, derrubando o processo inteiro em
    vez de cair como "data fora do intervalo" — o motivo que ja existe para isso.
    """
    limite = min(today, currency.max_covered_date(fx))
    return contract.validate(transform(df, fx), limite)


def write_outputs(
    accepted: pl.DataFrame,
    rejected: pl.DataFrame,
    clean_path: Path = CLEAN_PATH,
    rejects_path: Path = REJECTS_PATH,
) -> None:
    for caminho, frame in ((clean_path, accepted), (rejects_path, rejected)):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        # float_precision fixa as duas casas: coluna monetaria nao alterna 1919.0 e 481.69.
        frame.write_csv(caminho, line_terminator="\n", float_precision=2)


def run(
    today: dt.date,
    raw_path: Path = RAW_PATH,
    fx_path: Path = currency.FX_PATH,
    clean_path: Path = CLEAN_PATH,
    rejects_path: Path = REJECTS_PATH,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    accepted, rejected = clean_frame(load_raw(raw_path), currency.load_fx_rates(fx_path), today)
    write_outputs(accepted, rejected, clean_path, rejects_path)
    return accepted, rejected
