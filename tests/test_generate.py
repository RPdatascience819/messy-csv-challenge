from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl

from messy_csv import contract, generate


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_duas_execucoes_produzem_o_mesmo_hash(tmp_path: Path) -> None:
    primeiro = generate.write_dirty_dataset(tmp_path / "a.csv")
    segundo = generate.write_dirty_dataset(tmp_path / "b.csv")

    assert _sha256(primeiro) == _sha256(segundo)


def test_forma_do_dataset() -> None:
    df = generate.build_frame()

    assert df.height == generate.ROWS
    assert df.columns == list(contract.RAW_COLUMNS)
    assert all(dtype == pl.String for dtype in df.dtypes)


def test_seeds_diferentes_produzem_datasets_diferentes() -> None:
    """Prova que o determinismo vem da seed, nao de o gerador ser constante."""
    assert not generate.build_frame(1).equals(generate.build_frame(2))


def test_datas_nao_iso_ficam_perto_de_quarenta_por_cento() -> None:
    """Mede sobre a coluna aparada.

    Sem `strip_chars`, uma data ISO impecavel com espaco na ponta (whitespace,
    outra sujeira) contava como "nao-ISO" e inflava esta metrica de 0.3828 para
    0.4362 — perto o bastante do teto antigo (0.44) para um ajuste futuro em
    `WHITESPACE_RATE` reprovar este teste por um motivo que o nome dele nao diz.
    Valor medido com a seed 42, aparado: 0.3828.
    """
    df = generate.build_frame()
    iso = df.filter(
        pl.col("order_date").str.strip_chars().str.contains(r"^\d{4}-\d{2}-\d{2}$")
    ).height

    nao_iso = (generate.ROWS - iso) / generate.ROWS
    assert 0.37 <= nao_iso <= 0.40


def test_ids_duplicados_ficam_perto_de_tres_por_cento() -> None:
    df = generate.build_frame().with_columns(pl.col("order_id").str.strip_chars())
    numericos = df.filter(pl.col("order_id").str.contains(r"^\d+$") & (pl.col("order_id") != "0"))

    perdidos = numericos.height - numericos["order_id"].n_unique()
    assert 130 <= perdidos <= 170


def test_moeda_estrangeira_fica_perto_de_dezoito_por_cento() -> None:
    df = generate.build_frame()
    usd = df.filter(pl.col("amount").str.contains(r"(?i)(\$|usd)")).height

    # o "R$" tambem contem "$": conta so o que nao e real
    reais = df.filter(pl.col("amount").str.contains(r"R\$")).height
    assert 0.15 <= (usd - reais) / generate.ROWS <= 0.21


def test_todas_as_sujeiras_do_catalogo_e_de_l2_aparecem() -> None:
    df = generate.build_frame()

    assert df.filter(pl.col("customer").str.contains(r"^\s|\s$|  ")).height > 0
    assert df.filter(pl.col("order_date").str.contains(r"^\d{2}/\d{2}/\d{4}$")).height > 0
    assert df.filter(pl.col("order_date").str.contains(r"-13-")).height > 0
    assert df.filter(pl.col("category") == "").height > 0
    assert df.filter(pl.col("category").is_in(["diversos", "outros", "misc"])).height > 0
    assert df.filter(pl.col("amount").is_in(["-", "n/a"])).height > 0
    assert df.filter(pl.col("amount").is_in(["0,00", "-50,00"])).height > 0
    assert df.filter(pl.col("order_id").str.strip_chars() == "ORD-1023").height > 0
    assert df.filter(pl.col("order_date").str.starts_with("2019")).height > 0


def test_mes_abreviado_e_sempre_em_ingles() -> None:
    """O parser %b do chrono le ingles; locale pt-BR quebraria o dataset em silencio."""
    df = generate.build_frame()
    abreviados = df.filter(pl.col("order_date").str.contains(r"^[A-Z][a-z]{2} "))

    assert abreviados.height > 0
    meses = {valor.split()[0] for valor in abreviados["order_date"].to_list()}
    assert meses <= set(generate.MONTH_ABBR)
