from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from messy_csv import contract, generate, pipeline
from messy_csv.clean import categories, currency, dates, duplicates, missing, whitespace

TODAY = dt.date(2025, 6, 30)
FX = currency.load_fx_rates(currency.FX_PATH)


def _raw(*linhas: dict[str, str | None]) -> pl.DataFrame:
    completa: dict[str, str | None] = {
        "raw_order_id": "7",
        "raw_order_date": "2024-03-10",
        "raw_customer": "Ana Souza",
        "raw_category": "moda",
        "raw_amount": "R$ 100,00",
    }
    registros = [{**completa, **linha} for linha in linhas]
    schema = {f"raw_{nome}": pl.String() for nome in contract.RAW_COLUMNS}
    return pl.DataFrame(registros, schema=schema).with_row_index("source_index")


def test_linha_impecavel_atravessa_o_pipeline() -> None:
    aceitos, rejeitados = pipeline.clean_frame(_raw({}), FX, TODAY)

    assert rejeitados.height == 0
    assert aceitos.to_dicts() == [
        {
            "order_id": 7,
            "order_date": dt.date(2024, 3, 10),
            "customer": "Ana Souza",
            "category": "Moda",
            "amount_original": 100.0,
            "currency_original": "BRL",
            "amount_brl": 100.0,
        }
    ]


def test_clean_frame_e_validate_sobre_transform() -> None:
    """Amarra as duas portas de entrada: o relatorio usa transform, o pipeline usa clean_frame."""
    frame = _raw({}, {"raw_amount": "n/a"})

    aceitos, rejeitados = pipeline.clean_frame(frame, FX, TODAY)
    outros_aceitos, outros_rejeitados = contract.validate(pipeline.transform(frame, FX), TODAY)

    assert aceitos.equals(outros_aceitos)
    assert rejeitados.equals(outros_rejeitados)


def test_ordem_dos_transformadores_decide_a_linha_vencedora() -> None:
    """O teste que a spec §6.1 pede: inverter 5 e 6 elege a linha errada em silencio."""
    frame = _raw(
        {"raw_category": ""},  # indice 0: um nulo
        {},  # indice 1: completa
    )

    aceitos, _ = pipeline.clean_frame(frame, FX, TODAY)
    assert aceitos["category"].to_list() == ["Moda"]

    # Mesma cadeia, com missing antes de duplicates.
    invertido = whitespace.apply(frame)
    invertido = dates.apply(invertido)
    invertido = currency.apply(invertido, FX)
    invertido = categories.apply(invertido)
    invertido = missing.apply(invertido)
    invertido = duplicates.apply(invertido)
    aceitos_invertidos, _ = contract.validate(invertido, TODAY)

    assert aceitos_invertidos["category"].to_list() == ["Não informado"]


def test_nenhuma_linha_desaparece() -> None:
    """D6, verificado por contagem: aprovados mais rejeitados fecham com a entrada."""
    frame = _raw(
        {},
        {"raw_amount": "n/a"},
        {"raw_order_id": "ORD-1023"},
        {"raw_category": "misc"},
        {"raw_order_date": "2019-05-01"},
    )

    aceitos, rejeitados = pipeline.clean_frame(frame, FX, TODAY)

    assert aceitos.height + rejeitados.height == frame.height


def test_todos_os_motivos_aparecem_no_dataset_real(tmp_path: Path) -> None:
    """Spec §8: cada motivo do §4.3 precisa de ao menos um caso com dado real."""
    caminho = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    _, rejeitados = pipeline.clean_frame(pipeline.load_raw(caminho), FX, TODAY)

    produzidos: set[str] = set()
    for motivos in rejeitados["reject_reason"].to_list():
        produzidos.update(motivos.split(contract.REJECT_REASON_SEPARATOR))

    esperados = {motivo for motivo, _ in contract.reject_reasons(TODAY)}
    assert esperados <= produzidos


def test_dataset_aprovado_satisfaz_cem_por_cento_do_contrato(tmp_path: Path) -> None:
    caminho = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    aceitos, _ = pipeline.clean_frame(pipeline.load_raw(caminho), FX, TODAY)

    assert dict(aceitos.schema) == contract.clean_schema()
    assert aceitos.null_count().sum_horizontal().item() == 0
    assert aceitos["order_id"].n_unique() == aceitos.height
    assert aceitos["order_id"].min() > 0
    assert aceitos["order_date"].min() >= contract.MIN_DATE
    assert aceitos["order_date"].max() <= TODAY
    assert aceitos["amount_original"].min() > 0
    assert aceitos["amount_brl"].min() > 0
    assert aceitos.filter(pl.col("customer").str.contains(r"^\s|\s$|  ")).height == 0


def test_load_raw_le_tudo_como_texto(tmp_path: Path) -> None:
    """Spec §4.1: inferencia de schema sobre dado sujo adivinha, e adivinhacao nao audita."""
    caminho = tmp_path / "dirty.csv"
    caminho.write_text(
        "order_id,order_date,customer,category,amount\n1,2024-03-10,Ana,moda,99\n",
        encoding="utf-8",
    )

    frame = pipeline.load_raw(caminho)

    assert frame.columns == ["source_index", *(f"raw_{n}" for n in contract.RAW_COLUMNS)]
    assert frame["raw_order_id"].dtype == pl.String
    assert frame["source_index"].to_list() == [0]


def test_celula_vazia_e_lida_como_nulo(tmp_path: Path) -> None:
    caminho = tmp_path / "dirty.csv"
    caminho.write_text(
        "order_id,order_date,customer,category,amount\n1,2024-03-10,Ana,,99\n",
        encoding="utf-8",
    )

    assert pipeline.load_raw(caminho)["raw_category"].null_count() == 1


def test_run_grava_os_dois_artefatos(tmp_path: Path) -> None:
    bruto = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    limpo = tmp_path / "clean" / "orders.csv"
    rejeitos = tmp_path / "rejects" / "rejects.csv"

    aceitos, rejeitados = pipeline.run(
        TODAY, raw_path=bruto, clean_path=limpo, rejects_path=rejeitos
    )

    assert limpo.exists() and rejeitos.exists()
    assert pl.read_csv(limpo).height == aceitos.height
    assert pl.read_csv(rejeitos).columns == [*contract.RAW_COLUMNS, "reject_reason"]
    assert rejeitados.height > 0


def test_rodar_duas_vezes_produz_o_mesmo_artefato(tmp_path: Path) -> None:
    bruto = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    primeiro = tmp_path / "a.csv"
    segundo = tmp_path / "b.csv"

    pipeline.run(TODAY, raw_path=bruto, clean_path=primeiro, rejects_path=tmp_path / "ra.csv")
    pipeline.run(TODAY, raw_path=bruto, clean_path=segundo, rejects_path=tmp_path / "rb.csv")

    assert primeiro.read_bytes() == segundo.read_bytes()


def test_artefatos_versionados_batem_com_o_pipeline(tmp_path: Path) -> None:
    """Os CSVs commitados sao a vitrine: se divergirem do codigo, a vitrine mente."""
    limpo = tmp_path / "orders.csv"
    rejeitos = tmp_path / "rejects.csv"

    pipeline.run(TODAY, clean_path=limpo, rejects_path=rejeitos)

    assert limpo.read_bytes() == pipeline.CLEAN_PATH.read_bytes()
    assert rejeitos.read_bytes() == pipeline.REJECTS_PATH.read_bytes()
