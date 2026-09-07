from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest

from messy_csv import contract, generate, pipeline, profile
from messy_csv.clean import currency

TODAY = dt.date(2025, 6, 30)
FX = currency.load_fx_rates(currency.FX_PATH)


def _view(*linhas: dict[str, str | None]) -> pl.DataFrame:
    completa: dict[str, str | None] = {
        "order_id": "1",
        "order_date": "2024-03-10",
        "customer": "Ana Souza",
        "category": "Moda",
        "amount": "R$ 100,00",
    }
    registros = [{**completa, **linha} for linha in linhas]
    return pl.DataFrame(registros, schema={n: pl.String() for n in profile.VIEW_COLUMNS})


def test_dataset_impecavel_pontua_cem() -> None:
    resultado = profile.profile(_view({}, {"order_id": "2"}), TODAY)

    assert resultado.score == 100.0
    assert set(resultado.dimensions) == set(profile.DIMENSION_LABELS)


def test_completude_conta_celulas_nao_nulas() -> None:
    resultado = profile.profile(_view({"customer": None}), TODAY)

    assert resultado.completeness == pytest.approx(4 / 5)


def test_unicidade_desconta_ids_repetidos() -> None:
    resultado = profile.profile(_view({}, {}), TODAY)  # ambos com order_id "1"

    assert resultado.uniqueness == pytest.approx(1 / 2)


def test_validade_temporal_reprova_formato_ilegivel_e_data_fora_do_intervalo() -> None:
    resultado = profile.profile(
        _view({}, {"order_date": "2024-13-02"}, {"order_date": "2019-05-01"}), TODAY
    )

    assert resultado.temporal_validity == pytest.approx(1 / 3)


def test_data_em_formato_alternativo_e_valida() -> None:
    """Formato diferente nao e invalidade: o parser aceita os quatro da spec."""
    resultado = profile.profile(_view({"order_date": "15/03/2024"}), TODAY)

    assert resultado.temporal_validity == 1.0


def test_consistencia_de_categoria_reprova_rotulo_irrecuperavel() -> None:
    resultado = profile.profile(_view({}, {"category": "misc"}), TODAY)

    assert resultado.category_consistency == pytest.approx(1 / 2)


def test_nao_informado_conta_como_categoria_canonica() -> None:
    """Rotulo imputado por missing.py pertence ao contrato, mas nao ao mapa canonico."""
    resultado = profile.profile(_view({"category": "Não informado"}), TODAY)

    assert resultado.category_consistency == 1.0


def test_normalizacao_monetaria_reprova_valor_ilegivel() -> None:
    resultado = profile.profile(_view({}, {"amount": "n/a"}), TODAY)

    assert resultado.currency_normalization == pytest.approx(1 / 2)


def test_limpeza_textual_mede_so_celulas_preenchidas() -> None:
    """Ausencia e problema de completude; medir duas vezes puniria o mesmo defeito."""
    resultado = profile.profile(_view({"customer": None, "category": "Moda"}), TODAY)

    assert resultado.text_cleanliness == 1.0


def test_limpeza_textual_reprova_espaco_anomalo() -> None:
    resultado = profile.profile(_view({"customer": "Ana  Souza"}), TODAY)

    assert resultado.text_cleanliness == pytest.approx(1 / 2)


def test_toda_dimensao_fica_entre_zero_e_um(tmp_path: Path) -> None:
    bruto_path = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    visao = profile.view_from_raw(pipeline.load_raw(bruto_path))

    resultado = profile.profile(visao, TODAY)

    assert all(0.0 <= valor <= 1.0 for valor in resultado.dimensions.values())


def test_score_e_a_media_das_seis_dimensoes() -> None:
    resultado = profile.profile(_view({"customer": None}), TODAY)
    esperado = round(sum(resultado.dimensions.values()) / 6 * 100, 1)

    assert resultado.score == esperado


def test_dataset_vazio_e_erro_e_nao_score_zero() -> None:
    vazio = pl.DataFrame(schema={n: pl.String() for n in profile.VIEW_COLUMNS})

    with pytest.raises(ValueError, match="vazio"):
        profile.profile(vazio, TODAY)


def test_limpo_pontua_mais_que_o_sujo(tmp_path: Path) -> None:
    """Spec §8: o score tem de subir do raw para o clean."""
    bruto_path = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    aceitos, _ = pipeline.clean_frame(pipeline.load_raw(bruto_path), FX, TODAY)

    antes = profile.profile(profile.view_from_raw(pipeline.load_raw(bruto_path)), TODAY)
    depois = profile.profile(profile.view_from_clean(aceitos), TODAY)

    assert depois.score > antes.score


def test_dataset_limpo_pontua_cem(tmp_path: Path) -> None:
    """Se o limpo nao fecha em 100, ou o contrato ou a medicao esta errada."""
    bruto_path = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    aceitos, _ = pipeline.clean_frame(pipeline.load_raw(bruto_path), FX, TODAY)

    assert profile.profile(profile.view_from_clean(aceitos), TODAY).score == 100.0


def test_view_from_clean_produz_a_mesma_forma_do_raw(tmp_path: Path) -> None:
    bruto_path = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    aceitos, _ = pipeline.clean_frame(pipeline.load_raw(bruto_path), FX, TODAY)

    visao = profile.view_from_clean(aceitos)

    assert visao.columns == list(profile.VIEW_COLUMNS)
    assert all(dtype == pl.String for dtype in visao.dtypes)


def test_contagem_de_sujeiras_cobre_o_catalogo(tmp_path: Path) -> None:
    bruto_path = generate.write_dirty_dataset(tmp_path / "dirty.csv")
    visao = profile.view_from_raw(pipeline.load_raw(bruto_path))

    sujeiras = profile.dirt_counts(visao)

    assert len(sujeiras) == 6
    assert all(item["linhas"] > 0 for item in sujeiras)
    assert all({"sujeira", "causa", "linhas"} == set(item) for item in sujeiras)


def test_colunas_medidas_batem_com_o_contrato() -> None:
    assert profile.VIEW_COLUMNS == contract.RAW_COLUMNS
