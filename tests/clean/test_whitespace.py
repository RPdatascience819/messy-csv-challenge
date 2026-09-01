from __future__ import annotations

import polars as pl
import pytest

from messy_csv.clean import whitespace


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  Ana Souza  ", "Ana Souza"),
        ("Ana  Souza", "Ana Souza"),
        ("\tAna\nSouza ", "Ana Souza"),
        (" 15/03/2024 ", "15/03/2024"),
        ("Ana Souza", "Ana Souza"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalizacao_de_texto(entrada: str | None, esperado: str | None) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    resultado = df.select(whitespace.normalized_text_expr("valor"))

    assert resultado.to_series().to_list() == [esperado]


def test_celula_vazia_vira_nulo_e_nao_string_vazia() -> None:
    """O contrato distingue ausente de invalido: vazio precisa ser nulo, nao ''."""
    df = pl.DataFrame({"valor": [""]}, schema={"valor": pl.String()})

    assert df.select(whitespace.normalized_text_expr("valor")).to_series().null_count() == 1


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Ana Souza", True),
        (" Ana Souza", False),
        ("Ana Souza ", False),
        ("Ana  Souza", False),
        (None, None),
    ],
)
def test_deteccao_de_whitespace_anomalo(entrada: str | None, esperado: bool | None) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    assert df.select(whitespace.is_clean_text_expr("valor")).to_series().to_list() == [esperado]


def test_apply_cria_as_cinco_colunas_e_nao_toca_nas_originais() -> None:
    df = pl.DataFrame(
        {
            "raw_order_id": ["  1 "],
            "raw_order_date": [" 15/03/2024"],
            "raw_customer": ["Ana  Souza"],
            "raw_category": [" moda "],
            "raw_amount": ["R$  100,00"],
        }
    )

    resultado = whitespace.apply(df)

    assert resultado["t_order_id"].to_list() == ["1"]
    assert resultado["t_customer"].to_list() == ["Ana Souza"]
    assert resultado["t_amount"].to_list() == ["R$ 100,00"]
    # a coluna original sobrevive intacta: e ela que a quarentena grava
    assert resultado["raw_customer"].to_list() == ["Ana  Souza"]
