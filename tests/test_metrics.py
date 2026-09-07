from __future__ import annotations

import pytest

from messy_csv import metrics
from messy_csv.profile import DIMENSION_LABELS, ProfileResult


def _resultado(valor: float, linhas: int = 100) -> ProfileResult:
    return ProfileResult(
        rows=linhas,
        completeness=valor,
        uniqueness=valor,
        temporal_validity=valor,
        category_consistency=valor,
        currency_normalization=valor,
        text_cleanliness=valor,
    )


def test_comparacao_calcula_o_delta_por_dimensao() -> None:
    comparacao = metrics.compare(_resultado(0.5), _resultado(1.0, 90), rows_quarantined=10)

    assert len(comparacao.dimensions) == len(DIMENSION_LABELS)
    assert all(item.delta == pytest.approx(0.5) for item in comparacao.dimensions)


def test_rotulos_das_dimensoes_sao_os_do_profile() -> None:
    comparacao = metrics.compare(_resultado(0.5), _resultado(1.0, 90), rows_quarantined=10)

    assert [item.label for item in comparacao.dimensions] == list(DIMENSION_LABELS.values())


def test_delta_do_score_e_arredondado_a_uma_casa() -> None:
    comparacao = metrics.compare(_resultado(0.5), _resultado(1.0, 90), rows_quarantined=10)

    assert comparacao.score_delta == 50.0


def test_taxa_de_quarentena_usa_o_total_de_entrada() -> None:
    comparacao = metrics.compare(_resultado(0.5), _resultado(1.0, 90), rows_quarantined=10)

    assert comparacao.quarantine_rate == pytest.approx(0.1)
    assert comparacao.rows_kept == 90


def test_piora_produz_delta_negativo() -> None:
    """A metrica nao presume melhora: se o pipeline piorar, o relatorio mostra."""
    comparacao = metrics.compare(_resultado(0.9), _resultado(0.4, 100), rows_quarantined=0)

    assert comparacao.score_delta < 0
