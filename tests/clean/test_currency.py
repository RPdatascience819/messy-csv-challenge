from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from messy_csv.clean import currency

FX = pl.DataFrame(
    {
        "month": ["2024-03", "2024-03", "2024-04", "2024-04"],
        "currency": ["BRL", "USD", "BRL", "USD"],
        "rate_to_brl": [1.0, 5.0, 1.0, 5.5],
    }
)


@pytest.mark.parametrize(
    ("entrada", "moeda", "valor"),
    [
        ("R$ 1.299,90", "BRL", 1299.90),
        ("1.299,90", "BRL", 1299.90),
        ("R$ 99,00", "BRL", 99.00),
        ("$ 249.00", "USD", 249.00),
        ("USD 249.00", "USD", 249.00),
        ("US$ 249.00", "USD", 249.00),
        ("-50,00", "BRL", -50.00),
        ("0,00", "BRL", 0.00),
        ("n/a", None, None),
        ("-", None, None),
        (None, None, None),
    ],
)
def test_parse_dos_formatos_monetarios(
    entrada: str | None, moeda: str | None, valor: float | None
) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    resultado = df.select(
        currency.amount_expr("valor").alias("amount"),
        currency.currency_expr("valor").alias("currency"),
    )

    assert resultado["amount"].to_list() == pytest.approx([valor])
    assert resultado["currency"].to_list() == [moeda]


def test_ausencia_de_simbolo_assume_real() -> None:
    """Spec §12.4: suposicao declarada, coerente com uma loja brasileira."""
    df = pl.DataFrame({"valor": ["1.299,90"]}, schema={"valor": pl.String()})

    assert df.select(currency.currency_expr("valor")).to_series().to_list() == ["BRL"]


def _frame(amount: str | None, data: dt.date | None) -> pl.DataFrame:
    return pl.DataFrame(
        {"source_index": [0], "t_amount": [amount], "order_date": [data]},
        schema={"source_index": pl.UInt32(), "t_amount": pl.String(), "order_date": pl.Date()},
    )


def test_conversao_usa_a_competencia_do_pedido() -> None:
    marco = currency.apply(_frame("$ 100.00", dt.date(2024, 3, 10)), FX)
    abril = currency.apply(_frame("$ 100.00", dt.date(2024, 4, 10)), FX)

    assert marco["amount_brl"].to_list() == [500.00]
    assert abril["amount_brl"].to_list() == [550.00]


def test_real_nao_e_convertido() -> None:
    resultado = currency.apply(_frame("R$ 100,00", dt.date(2024, 3, 10)), FX)

    assert resultado["amount_brl"].to_list() == [100.00]
    assert resultado["amount_original"].to_list() == [100.00]


def test_amount_brl_tem_duas_casas_decimais() -> None:
    resultado = currency.apply(_frame("$ 33.33", dt.date(2024, 4, 10)), FX)

    assert resultado["amount_brl"].to_list() == [183.32]  # 33.33 * 5.5 = 183.315


def test_procedencia_e_preservada() -> None:
    """D8: sem o original nao ha como auditar nem recalcular a conversao."""
    resultado = currency.apply(_frame("$ 100.00", dt.date(2024, 3, 10)), FX)

    assert set(resultado.columns) >= {"amount_original", "currency_original", "amount_brl"}
    assert resultado["currency_original"].to_list() == ["USD"]


def test_valor_ilegivel_propaga_nulo_sem_quebrar() -> None:
    resultado = currency.apply(_frame("n/a", dt.date(2024, 3, 10)), FX)

    assert resultado["amount_original"].to_list() == [None]
    assert resultado["amount_brl"].to_list() == [None]
    assert resultado.height == 1  # transformador nao rejeita linha (D5)


def test_data_invalida_nao_derruba_a_conversao() -> None:
    resultado = currency.apply(_frame("$ 100.00", None), FX)

    assert resultado["amount_brl"].to_list() == [None]
    assert resultado.height == 1


def test_tabela_versionada_cobre_todo_o_intervalo_do_gerador() -> None:
    """Um mes faltando produziria amount_brl nulo — dado errado em silencio."""
    fx = currency.load_fx_rates(currency.FX_PATH)
    esperados = {
        (f"{ano}-{mes:02d}", moeda)
        for ano in (2023, 2024)
        for mes in range(1, 13)
        for moeda in ("BRL", "USD")
    }

    presentes = set(zip(fx["month"].to_list(), fx["currency"].to_list(), strict=True))
    assert esperados <= presentes


def test_taxa_do_real_e_sempre_um() -> None:
    fx = currency.load_fx_rates(currency.FX_PATH)

    taxas = fx.filter(pl.col("currency") == "BRL")["rate_to_brl"].unique().to_list()
    assert taxas == [1.0]


def test_ordem_de_origem_e_preservada_mesmo_embaralhada() -> None:
    """O sort por source_index garante determinismo para a deduplicacao consumir."""
    df = pl.DataFrame(
        {
            "source_index": [2, 0, 1],
            "t_amount": ["R$ 100,00", "$ 100.00", "$ 200.00"],
            "order_date": [dt.date(2024, 3, 10), dt.date(2024, 3, 10), dt.date(2024, 4, 10)],
        },
        schema={"source_index": pl.UInt32(), "t_amount": pl.String(), "order_date": pl.Date()},
    )

    resultado = currency.apply(df, FX)

    # A ordem foi corrigida pelo sort
    assert resultado["source_index"].to_list() == [0, 1, 2]
    # Os valores acompanharam suas linhas (nao foram embaralhados)
    assert resultado["amount_original"].to_list() == [100.00, 200.00, 100.00]
    assert resultado["amount_brl"].to_list() == [500.00, 1100.00, 100.00]
