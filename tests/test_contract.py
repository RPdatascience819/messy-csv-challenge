from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from messy_csv import contract

TODAY = dt.date(2025, 6, 30)

_SCHEMA: dict[str, pl.DataType] = {
    "source_index": pl.UInt32(),
    "raw_order_id": pl.String(),
    "raw_order_date": pl.String(),
    "raw_customer": pl.String(),
    "raw_category": pl.String(),
    "raw_amount": pl.String(),
    "t_order_id": pl.String(),
    "t_order_date": pl.String(),
    "t_customer": pl.String(),
    "t_category": pl.String(),
    "t_amount": pl.String(),
    "order_id": pl.Int64(),
    "order_date": pl.Date(),
    "amount_original": pl.Float64(),
    "currency_original": pl.String(),
    "amount_brl": pl.Float64(),
    "category": pl.String(),
    "is_duplicate_loser": pl.Boolean(),
}


def _frame(**overrides: object) -> pl.DataFrame:
    """Uma linha impecavel, com os campos indicados sabotados."""
    base: dict[str, object] = {
        "source_index": 0,
        "raw_order_id": " 1 ",
        "raw_order_date": "15/03/2024",
        "raw_customer": "Ana  Souza",
        "raw_category": "moda",
        "raw_amount": "R$ 100,00",
        "t_order_id": "1",
        "t_order_date": "15/03/2024",
        "t_customer": "Ana Souza",
        "t_category": "moda",
        "t_amount": "R$ 100,00",
        "order_id": 1,
        "order_date": dt.date(2024, 3, 15),
        "amount_original": 100.0,
        "currency_original": "BRL",
        "amount_brl": 100.0,
        "category": "Moda",
        "is_duplicate_loser": False,
    }
    base.update(overrides)
    return pl.DataFrame({key: [value] for key, value in base.items()}, schema=_SCHEMA)


def test_linha_impecavel_e_aprovada() -> None:
    accepted, rejected = contract.validate(_frame(), TODAY)

    assert accepted.height == 1
    assert rejected.height == 0


def test_schema_do_aprovado_bate_com_o_contrato() -> None:
    accepted, _ = contract.validate(_frame(), TODAY)

    assert accepted.columns == list(contract.CLEAN_COLUMNS)
    assert dict(accepted.schema) == contract.clean_schema()


@pytest.mark.parametrize(
    ("motivo", "sabotagem"),
    [
        ("order_id inválido", {"order_id": None}),
        ("order_id inválido", {"order_id": 0}),
        ("order_id duplicado irreconciliável", {"is_duplicate_loser": True}),
        ("data inválida", {"order_date": None}),
        ("data fora do intervalo", {"order_date": dt.date(2019, 5, 1)}),
        ("data fora do intervalo", {"order_date": dt.date(2025, 12, 1)}),
        ("cliente ausente", {"t_customer": None}),
        ("categoria desconhecida", {"category": None}),
        ("valor ausente", {"t_amount": None, "amount_original": None}),
        ("valor inválido", {"t_amount": "n/a", "amount_original": None}),
        ("valor não positivo", {"amount_original": -50.0}),
    ],
)
def test_cada_motivo_tem_ao_menos_um_caso(motivo: str, sabotagem: dict[str, object]) -> None:
    accepted, rejected = contract.validate(_frame(**sabotagem), TODAY)

    assert accepted.height == 0
    assert rejected["reject_reason"].to_list() == [motivo]


def test_todos_os_nove_motivos_sao_alcancaveis() -> None:
    """Nenhum motivo do contrato pode ser letra morta."""
    alcancados = {motivo for motivo, _ in contract.reject_reasons(TODAY)}
    assert len(alcancados) == 9


def test_motivos_multiplos_sao_acumulados_na_ordem_das_regras() -> None:
    _, rejected = contract.validate(
        _frame(order_id=None, t_customer=None, amount_original=-1.0),
        TODAY,
    )

    assert rejected["reject_reason"].to_list() == [
        "order_id inválido; cliente ausente; valor não positivo"
    ]


def test_rejeitado_preserva_as_colunas_originais_intocadas() -> None:
    _, rejected = contract.validate(_frame(order_date=None), TODAY)

    assert rejected.columns == [*contract.RAW_COLUMNS, "reject_reason"]
    # o texto sujo sobrevive: e ele que torna a quarentena auditavel
    assert rejected["order_id"].to_list() == [" 1 "]
    assert rejected["customer"].to_list() == ["Ana  Souza"]


def test_aprovado_com_nulo_residual_levanta_contract_error() -> None:
    """amount_brl nulo so acontece se o cambio faltar: falhar alto, nunca gravar."""
    with pytest.raises(contract.ContractError, match="amount_brl"):
        contract.validate(_frame(amount_brl=None), TODAY)


def test_limite_inferior_do_intervalo_e_inclusivo() -> None:
    accepted, _ = contract.validate(_frame(order_date=contract.MIN_DATE), TODAY)

    assert accepted.height == 1


def test_limite_superior_do_intervalo_e_a_data_injetada() -> None:
    accepted, _ = contract.validate(_frame(order_date=TODAY), TODAY)

    assert accepted.height == 1
