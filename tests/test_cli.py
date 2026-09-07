from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from messy_csv import cli, pipeline, profile
from messy_csv.clean import currency

TODAY = "2025-06-30"


@pytest.fixture
def dados(tmp_path: Path) -> Path:
    """Um data-dir isolado com a tabela de cambio real: o resto a CLI gera."""
    destino = tmp_path / "data"
    destino.mkdir()
    shutil.copy(currency.FX_PATH, destino / "fx_rates.csv")
    return destino


def _args(dados: Path, docs: Path, *resto: str) -> list[str]:
    return [*resto, "--data-dir", str(dados), "--docs-dir", str(docs), "--today", TODAY]


def test_layout_padrao_bate_com_os_caminhos_dos_modulos() -> None:
    """Dois lugares definindo onde os arquivos moram e um deles vai ficar para tras."""
    layout = cli.Layout(cli.DATA_DIR, cli.DOCS_DIR)

    assert layout.raw == pipeline.RAW_PATH
    assert layout.clean == pipeline.CLEAN_PATH
    assert layout.rejects == pipeline.REJECTS_PATH
    assert layout.fx == currency.FX_PATH


def test_generate_grava_o_csv_sujo(dados: Path, tmp_path: Path) -> None:
    assert cli.main(_args(dados, tmp_path / "docs", "generate")) == 0
    assert (dados / "raw" / "orders_dirty.csv").exists()


def test_profile_imprime_json_com_score_e_seis_dimensoes(
    dados: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.main(_args(dados, tmp_path / "docs", "generate"))
    capsys.readouterr()

    codigo = cli.main(
        _args(dados, tmp_path / "docs", "profile", str(dados / "raw" / "orders_dirty.csv"))
    )
    saida = json.loads(capsys.readouterr().out)

    assert codigo == 0
    assert saida["rows"] == 5000
    assert set(profile.DIMENSION_LABELS) <= set(saida)
    assert 0 <= saida["score"] <= 100


def test_profile_aceita_o_dataset_limpo(
    dados: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Quem abre o repositorio vai apontar o comando para orders.csv. Tem de funcionar."""
    cli.main(_args(dados, tmp_path / "docs", "run"))
    capsys.readouterr()

    cli.main(_args(dados, tmp_path / "docs", "profile", str(dados / "clean" / "orders.csv")))

    assert json.loads(capsys.readouterr().out)["score"] == 100.0


def test_clean_grava_os_dois_artefatos(dados: Path, tmp_path: Path) -> None:
    cli.main(_args(dados, tmp_path / "docs", "generate"))

    assert cli.main(_args(dados, tmp_path / "docs", "clean")) == 0
    assert (dados / "clean" / "orders.csv").exists()
    assert (dados / "rejects" / "rejects.csv").exists()


def test_run_produz_os_quatro_artefatos(dados: Path, tmp_path: Path) -> None:
    """Criterio de sucesso 4 da spec, verificado por teste e nao por conferencia manual."""
    docs = tmp_path / "docs"

    assert cli.main(_args(dados, docs, "run")) == 0

    for artefato in (
        dados / "raw" / "orders_dirty.csv",
        dados / "clean" / "orders.csv",
        dados / "rejects" / "rejects.csv",
        docs / "index.html",
    ):
        assert artefato.exists(), artefato


def test_run_e_reproduzivel(dados: Path, tmp_path: Path) -> None:
    """Rodar duas vezes com a mesma data nao pode produzir um diff."""
    docs = tmp_path / "docs"
    cli.main(_args(dados, docs, "run"))
    primeiro = (docs / "index.html").read_bytes()

    cli.main(_args(dados, docs, "run"))

    assert (docs / "index.html").read_bytes() == primeiro


def test_today_injetado_move_o_limite_superior_das_datas(
    dados: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sem --today o teste dependeria do relogio do runner e mudaria de resultado sozinho."""
    cli.main(_args(dados, tmp_path / "docs", "generate"))
    capsys.readouterr()
    bruto = str(dados / "raw" / "orders_dirty.csv")

    cli.main(_args(dados, tmp_path / "docs", "profile", bruto))
    recente = json.loads(capsys.readouterr().out)["temporal_validity"]

    cli.main([*_args(dados, tmp_path / "docs", "profile", bruto)[:-1], "2023-06-30"])
    antigo = json.loads(capsys.readouterr().out)["temporal_validity"]

    assert antigo < recente


def test_clean_sem_dataset_bruto_falha_com_mensagem(
    dados: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    codigo = cli.main(_args(dados, tmp_path / "docs", "clean"))

    assert codigo == 2
    assert "orders_dirty.csv" in capsys.readouterr().err


def test_sem_subcomando_mostra_ajuda_e_falha(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 2
    assert "generate" in capsys.readouterr().out


def test_subcomando_desconhecido_e_erro_do_argparse() -> None:
    with pytest.raises(SystemExit) as saida:
        cli.main(["invalido"])

    assert saida.value.code == 2


def test_today_invalido_e_erro_do_argparse() -> None:
    with pytest.raises(SystemExit):
        cli.main(["generate", "--today", "30/06/2025"])


def test_data_padrao_e_hoje() -> None:
    args = cli.build_parser().parse_args(["generate"])

    assert args.today is None or args.today == dt.date.today()
