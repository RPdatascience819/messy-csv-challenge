from __future__ import annotations

import datetime as dt

import polars as pl

from messy_csv.clean import duplicates

_SCHEMA: dict[str, pl.DataType] = {
    "source_index": pl.UInt32(),
    "t_order_id": pl.String(),
    "order_date": pl.Date(),
    "t_customer": pl.String(),
    "category": pl.String(),
    "amount_original": pl.Float64(),
    "currency_original": pl.String(),
    "amount_brl": pl.Float64(),
}

_COMPLETA: dict[str, object] = {
    "t_order_id": "7",
    "order_date": dt.date(2024, 3, 10),
    "t_customer": "Ana Souza",
    "category": "Moda",
    "amount_original": 100.0,
    "currency_original": "BRL",
    "amount_brl": 100.0,
}


def _frame(*linhas: dict[str, object]) -> pl.DataFrame:
    registros = [
        {"source_index": indice, **_COMPLETA, **linha} for indice, linha in enumerate(linhas)
    ]
    return pl.DataFrame(registros, schema=_SCHEMA)


def test_vence_a_linha_com_menos_nulos() -> None:
    df = _frame({"category": None}, {})  # indice 0 tem um nulo, indice 1 nenhum

    resultado = duplicates.apply(df)

    assert resultado["is_duplicate_loser"].to_list() == [True, False]


def test_empate_e_resolvido_pelo_menor_indice_de_origem() -> None:
    df = _frame({"category": None}, {"t_customer": None})  # um nulo cada

    resultado = duplicates.apply(df)

    assert resultado["is_duplicate_loser"].to_list() == [False, True]


def test_linha_sem_duplicata_nunca_e_marcada() -> None:
    df = _frame({"t_order_id": "7"}, {"t_order_id": "8"})

    assert duplicates.apply(df)["is_duplicate_loser"].to_list() == [False, False]


def test_ids_ilegiveis_nao_sao_tratados_como_duplicatas_entre_si() -> None:
    """Sem esta guarda, todo id invalido cairia no mesmo grupo nulo e viraria duplicata."""
    df = _frame({"t_order_id": "ORD-1023"}, {"t_order_id": ""}, {"t_order_id": None})

    resultado = duplicates.apply(df)

    assert resultado["order_id"].to_list() == [None, None, None]
    assert resultado["is_duplicate_loser"].to_list() == [False, False, False]


def test_order_id_vira_inteiro() -> None:
    df = _frame({"t_order_id": "7"}, {"t_order_id": "0"})

    resultado = duplicates.apply(df)

    assert resultado["order_id"].to_list() == [7, 0]
    assert resultado.schema["order_id"] == pl.Int64


def test_ordem_original_e_restaurada() -> None:
    """A ordenacao por nulos e interna; quem sai daqui sai na ordem do arquivo."""
    df = _frame({"category": None}, {}, {"t_order_id": "9"})

    resultado = duplicates.apply(df)

    assert resultado["source_index"].to_list() == [0, 1, 2]


def test_tres_copias_deixam_apenas_uma_vencedora() -> None:
    df = _frame({"category": None}, {"t_customer": None}, {})

    assert duplicates.apply(df)["is_duplicate_loser"].to_list() == [True, True, False]


def test_nenhuma_linha_e_removida() -> None:
    """D6: o transformador marca, nunca descarta."""
    df = _frame({"category": None}, {}, {})

    assert duplicates.apply(df).height == 3


def test_id_zero_nao_forma_grupo_de_duplicata() -> None:
    """Id invalido nao forma grupo: zero sobrevive ao cast e nao junta pedidos sem relacao."""
    df = _frame({"t_order_id": "0"}, {"t_order_id": "0"})

    resultado = duplicates.apply(df)

    assert resultado["is_duplicate_loser"].to_list() == [False, False]
