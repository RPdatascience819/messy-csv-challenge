from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from messy_csv.clean import dates

TODAY = dt.date(2025, 6, 30)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("2024-03-15", dt.date(2024, 3, 15)),
        ("15/03/2024", dt.date(2024, 3, 15)),
        ("Mar 16 2024", dt.date(2024, 3, 16)),
        ("2024-03-15 10:30:00", dt.date(2024, 3, 15)),
        (" 15/03/2024 ", dt.date(2024, 3, 15)),
        ("2024-13-02", None),
        ("ontem", None),
        (None, None),
    ],
)
def test_parse_dos_formatos_declarados(entrada: str | None, esperado: dt.date | None) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    resultado = df.select(dates.parse_date_expr("valor"))

    assert resultado.to_series().to_list() == [esperado]
    assert resultado.dtypes == [pl.Date]


def test_hora_e_truncada_e_nao_arredondada() -> None:
    """Spec §12.3: timezone ignorado, hora truncada para data."""
    df = pl.DataFrame({"valor": ["2024-03-15 23:59:59"]}, schema={"valor": pl.String()})

    assert df.select(dates.parse_date_expr("valor")).to_series().to_list() == [dt.date(2024, 3, 15)]


def test_formatos_aceitos_sao_exatamente_os_da_spec() -> None:
    """A lista de formatos e contrato publico: mudar exige mudar a spec."""
    assert dates.DATE_FORMATS == ("%Y-%m-%d", "%d/%m/%Y", "%b %d %Y")
    assert dates.DATETIME_FORMATS == ("%Y-%m-%d %H:%M:%S",)


@pytest.mark.parametrize(
    ("data", "esperado"),
    [
        (dt.date(2022, 12, 31), False),
        (dt.date(2023, 1, 1), True),
        (dt.date(2024, 6, 1), True),
        (TODAY, True),
        (dt.date(2025, 7, 1), False),
        (None, None),
    ],
)
def test_intervalo_valido(data: dt.date | None, esperado: bool | None) -> None:
    df = pl.DataFrame({"d": [data]}, schema={"d": pl.Date()})

    assert df.select(dates.is_in_range_expr("d", TODAY)).to_series().to_list() == [esperado]


def test_apply_adiciona_order_date_sem_remover_o_texto() -> None:
    df = pl.DataFrame({"t_order_date": ["15/03/2024", "2024-13-02"]})

    resultado = dates.apply(df)

    assert resultado["order_date"].to_list() == [dt.date(2024, 3, 15), None]
    assert resultado["t_order_date"].to_list() == ["15/03/2024", "2024-13-02"]
