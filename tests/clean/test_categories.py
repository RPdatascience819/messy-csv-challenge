from __future__ import annotations

import polars as pl
import pytest

from messy_csv import contract
from messy_csv.clean import categories


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Eletrônicos", "Eletrônicos"),
        ("eletronicos", "Eletrônicos"),
        ("ELETRONICOS", "Eletrônicos"),
        ("Eletrônico", "Eletrônicos"),
        ("eletro", "Eletrônicos"),
        ("Moda", "Moda"),
        ("MODA", "Moda"),
        ("Modas", "Moda"),
        ("vestuario", "Moda"),
        ("Casa", "Casa"),
        ("Casa e Decoração", "Casa"),
        ("casa_decoracao", "Casa"),
        ("Livros", "Livros"),
        ("LIVRO", "Livros"),
        ("livraria", "Livros"),
        ("Esporte", "Esporte"),
        ("Esportes", "Esporte"),
        ("ESPORTE", "Esporte"),
        ("diversos", None),
        ("outros", None),
        ("misc", None),
        (None, None),
    ],
)
def test_mapa_canonico(entrada: str | None, esperado: str | None) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    assert df.select(categories.canonical_expr("valor")).to_series().to_list() == [esperado]


def test_diversos_e_irrecuperavel_de_proposito() -> None:
    """Spec §5.2: sem uma categoria irrecuperavel a quarentena nunca seria exercitada."""
    df = pl.DataFrame({"valor": ["diversos"]}, schema={"valor": pl.String()})

    assert df.select(categories.canonical_expr("valor")).to_series().null_count() == 1


def test_todo_valor_canonico_pertence_ao_contrato() -> None:
    assert set(categories.CANONICAL_MAP.values()) <= set(contract.CATEGORIES)


def test_nao_informado_nao_e_produzido_aqui() -> None:
    """Imputacao e responsabilidade de missing.py, e roda depois (§6.1)."""
    assert "Não informado" not in categories.CANONICAL_MAP.values()


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Casa e Decoração", "casa e decoracao"),
        ("casa_decoracao", "casa decoracao"),
        ("  ELETRÔNICOS  ", "eletronicos"),
        ("Esportes", "esportes"),
    ],
)
def test_normalizacao_remove_acento_caixa_e_separador(entrada: str, esperado: str) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    assert df.select(categories.normalize_expr("valor")).to_series().to_list() == [esperado]


def test_apply_adiciona_category_sem_remover_o_texto() -> None:
    df = pl.DataFrame({"t_category": ["ELETRONICOS", "misc"]})

    resultado = categories.apply(df)

    assert resultado["category"].to_list() == ["Eletrônicos", None]
    assert resultado["t_category"].to_list() == ["ELETRONICOS", "misc"]
