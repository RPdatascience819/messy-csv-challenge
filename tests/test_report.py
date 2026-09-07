from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import polars as pl
import pytest

from messy_csv import contract, generate, metrics, pipeline, report
from messy_csv.clean import currency
from messy_csv.profile import DIMENSION_LABELS, ProfileResult

TODAY = dt.date(2025, 6, 30)
FX = currency.load_fx_rates(currency.FX_PATH)


def _comparacao_minima() -> metrics.Comparison:
    resultado = ProfileResult(
        rows=1,
        completeness=1.0,
        uniqueness=1.0,
        temporal_validity=1.0,
        category_consistency=1.0,
        currency_normalization=1.0,
        text_cleanliness=1.0,
    )
    return metrics.compare(resultado, resultado, rows_quarantined=0)


@pytest.fixture(scope="module")
def transformado(tmp_path_factory: pytest.TempPathFactory) -> pl.DataFrame:
    destino = tmp_path_factory.mktemp("relatorio")
    bruto = pipeline.load_raw(generate.write_dirty_dataset(destino / "dirty.csv"))
    return pipeline.transform(bruto, FX)


@pytest.fixture(scope="module")
def dados(tmp_path_factory: pytest.TempPathFactory) -> report.ReportData:
    """Um relatorio real, construido uma vez: o dataset de 5.000 linhas nao muda."""
    destino = tmp_path_factory.mktemp("relatorio_completo")
    bruto = pipeline.load_raw(generate.write_dirty_dataset(destino / "dirty.csv"))
    frame = pipeline.transform(bruto, FX)
    aceitos, rejeitados = contract.validate(frame, TODAY)
    return report.build(bruto, frame, aceitos, rejeitados, TODAY)


@pytest.fixture(scope="module")
def html(dados: report.ReportData) -> str:
    return report.render(dados)


def test_formata_moeda_sem_depender_do_locale() -> None:
    """f-string com virgula usa a convencao americana; a troca e explicita de proposito."""
    assert report.format_brl(1234.5) == "R$ 1.234,50"
    assert report.format_brl(99.0) == "R$ 99,00"


def test_html_contem_todas_as_secoes_da_spec(html: str) -> None:
    """Spec 9: sumario, cards, tabela de sujeiras, amostras, quarentena e metodologia."""
    for secao in ("sumario", "dimensoes", "sujeiras", "amostras", "quarentena", "metodologia"):
        assert f'id="{secao}"' in html


def test_sumario_mostra_os_dois_scores(dados: report.ReportData, html: str) -> None:
    assert f"{dados.comparison.before.score:.1f}" in html
    assert f"{dados.comparison.after.score:.1f}" in html


def test_seis_cards_de_dimensao(html: str) -> None:
    for rotulo in DIMENSION_LABELS.values():
        assert rotulo in html


def test_nenhuma_requisicao_externa(html: str) -> None:
    """Spec 9: a pagina abre offline, dentro de dez anos, sem CDN de ninguem."""
    assert not re.search(r"https?://|<link\b|@import\b|\bsrc\s*=", html)


def test_viewport_declarado_para_leitura_em_375px(html: str) -> None:
    assert 'name="viewport"' in html


def test_dark_mode_por_media_query(html: str) -> None:
    assert "prefers-color-scheme: dark" in html


def test_amostras_sao_linhas_que_realmente_mudaram(dados: report.ReportData) -> None:
    assert dados.samples
    assert all(amostra.before != amostra.after for amostra in dados.samples)


def test_amostra_respeita_o_limite(transformado: pl.DataFrame) -> None:
    assert len(report.build_samples(transformado, TODAY, limit=3)) == 3


def test_amostra_so_traz_linha_aprovada(dados: report.ReportData) -> None:
    """Mostrar uma linha rejeitada no antes/depois anunciaria uma limpeza que nao houve."""
    for amostra in dados.samples:
        assert amostra.after["order_id"].isdigit()
        assert dt.date.fromisoformat(amostra.after["order_date"]) <= TODAY


def test_quarentena_agrupa_por_motivo_individual(dados: report.ReportData) -> None:
    """Uma linha com dois motivos conta nos dois grupos: a soma pode passar do total."""
    motivos = [grupo.reason for grupo in dados.quarantine]

    assert len(motivos) == len(set(motivos))
    assert contract.REJECT_REASON_SEPARATOR.strip() not in "".join(motivos)
    assert all(grupo.rows > 0 for grupo in dados.quarantine)


def test_quarentena_ordenada_da_maior_para_a_menor(dados: report.ReportData) -> None:
    contagens = [grupo.rows for grupo in dados.quarantine]

    assert contagens == sorted(contagens, reverse=True)


def test_quarentena_vazia_nao_quebra_o_relatorio() -> None:
    vazio = pl.DataFrame(
        schema={
            **{nome: pl.String() for nome in contract.RAW_COLUMNS},
            "reject_reason": pl.String(),
        }
    )

    assert report.group_quarantine(vazio) == []


def test_tabela_de_sujeiras_tem_as_seis_linhas(dados: report.ReportData, html: str) -> None:
    assert len(dados.dirt) == 6
    for item in dados.dirt:
        assert str(item["sujeira"]) in html


def test_conteudo_do_dado_e_escapado() -> None:
    """O CSV e entrada nao confiavel; um nome com < vira texto, nao marcacao."""
    dados = report.ReportData(
        generated_at=TODAY,
        comparison=_comparacao_minima(),
        dirt=[{"sujeira": "Whitespace", "causa": "Digitacao manual", "linhas": 1}],
        samples=[
            report.SampleRow(
                before={
                    "order_id": "1",
                    "order_date": "",
                    "customer": "<script>x</script>",
                    "category": "",
                    "amount": "",
                },
                after={
                    "order_id": "1",
                    "order_date": "2024-03-10",
                    "customer": "ok",
                    "category": "Moda",
                    "amount": "R$ 1,00",
                },
            )
        ],
        quarantine=[],
    )

    renderizado = report.render(dados)

    assert "<script>x</script>" not in renderizado
    assert "&lt;script&gt;" in renderizado


def test_render_e_deterministico(dados: report.ReportData) -> None:
    """Sem relogio interno: gerar duas vezes nao pode sujar o diff do repositorio."""
    assert report.render(dados) == report.render(dados)


def test_write_grava_utf8_e_devolve_o_caminho(dados: report.ReportData, tmp_path: Path) -> None:
    destino = report.write(dados, tmp_path / "sub" / "index.html")

    assert destino.exists()
    assert destino.read_text(encoding="utf-8").startswith("<!doctype html>")
