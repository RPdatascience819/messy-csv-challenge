"""Entrypoint: a composicao do projeto e o unico lugar que le o relogio.

Todo modulo de dominio recebe `today` por parametro (12.5). Uma funcao de
negocio que chama `dt.date.today()` por conta propria produz um teste que muda
de resultado sozinho na virada do dia; aqui, na fronteira, a leitura e explicita
e substituivel por `--today`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from messy_csv import contract, generate, pipeline, profile, report
from messy_csv.clean import currency

DATA_DIR = Path("data")
DOCS_DIR = Path("docs")


@dataclass(frozen=True)
class Layout:
    """O mapa de arquivos do projeto em um lugar so.

    Os defaults reproduzem exatamente `pipeline.RAW_PATH` e companhia, e um teste
    amarra os dois. Passar `--data-dir` move o conjunto inteiro, que e o que
    permite testar a CLI sem escrever no repositorio.
    """

    data_dir: Path
    docs_dir: Path

    @property
    def raw(self) -> Path:
        return self.data_dir / "raw" / "orders_dirty.csv"

    @property
    def clean(self) -> Path:
        return self.data_dir / "clean" / "orders.csv"

    @property
    def rejects(self) -> Path:
        return self.data_dir / "rejects" / "rejects.csv"

    @property
    def fx(self) -> Path:
        return self.data_dir / "fx_rates.csv"

    @property
    def report(self) -> Path:
        return self.docs_dir / "index.html"


def _iso_date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as erro:
        raise argparse.ArgumentTypeError(f"data deve ser YYYY-MM-DD, recebi {value!r}") from erro


def _layout(args: argparse.Namespace) -> Layout:
    return Layout(data_dir=args.data_dir, docs_dir=args.docs_dir)


def _load_view(path: Path) -> pl.DataFrame:
    """Aceita o CSV sujo e o limpo: quem abre o repositorio vai tentar os dois."""
    cabecalho = pl.read_csv(path, infer_schema=False, n_rows=0)
    if "amount_brl" in cabecalho.columns:
        return profile.view_from_clean(pl.read_csv(path, try_parse_dates=True))
    return profile.view_from_raw(pl.read_csv(path, infer_schema=False))


def _build_report(layout: Layout, today: dt.date) -> report.ReportData:
    """Refaz a limpeza em memoria de proposito.

    O antes e o depois lado a lado exigem as duas versoes da mesma linha, e o
    frame largo que as carrega nao e persistido. Reconstrui-lo custa segundos e
    dispensa um quarto artefato em disco que so o relatorio leria.
    """
    bruto = pipeline.load_raw(layout.raw)
    transformado = pipeline.transform(bruto, currency.load_fx_rates(layout.fx))
    aceitos, rejeitados = contract.validate(transformado, today)
    return report.build(bruto, transformado, aceitos, rejeitados, today)


def cmd_generate(args: argparse.Namespace) -> int:
    caminho = generate.write_dirty_dataset(_layout(args).raw)
    print(f"gerado: {caminho} ({generate.ROWS} linhas, seed {generate.SEED})")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    resultado = profile.profile(_load_view(args.path), args.today)
    print(json.dumps(resultado.to_dict(), ensure_ascii=False, indent=2))
    return 0


def cmd_clean(args: argparse.Namespace) -> int:
    layout = _layout(args)
    aceitos, rejeitados = pipeline.run(
        args.today,
        raw_path=layout.raw,
        fx_path=layout.fx,
        clean_path=layout.clean,
        rejects_path=layout.rejects,
    )
    print(f"aprovados: {aceitos.height}  quarentena: {rejeitados.height}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    layout = _layout(args)
    dados = _build_report(layout, args.today)
    caminho = report.write(dados, layout.report)
    comparacao = dados.comparison
    print(
        f"relatorio: {caminho}  "
        f"score {comparacao.before.score} -> {comparacao.after.score} "
        f"({comparacao.score_delta:+.1f})"
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    for etapa in (cmd_generate, cmd_clean, cmd_report):
        codigo = etapa(args)
        if codigo != 0:
            return codigo
    return 0


def build_parser() -> argparse.ArgumentParser:
    comum = argparse.ArgumentParser(add_help=False)
    comum.add_argument("--data-dir", type=Path, default=DATA_DIR, help="raiz dos CSVs")
    comum.add_argument("--docs-dir", type=Path, default=DOCS_DIR, help="destino do relatorio")
    comum.add_argument(
        "--today",
        type=_iso_date,
        default=None,
        help="data tratada como hoje (YYYY-MM-DD); padrao: a data do sistema",
    )

    parser = argparse.ArgumentParser(
        prog="messy-csv",
        description="Gera, mede, limpa e publica a prova sobre um CSV propositalmente sujo.",
    )
    sub = parser.add_subparsers(dest="comando")

    sub.add_parser("generate", parents=[comum], help="gera o CSV sujo").set_defaults(
        handler=cmd_generate
    )

    p_profile = sub.add_parser("profile", parents=[comum], help="imprime o profiling em JSON")
    p_profile.add_argument("path", type=Path, help="CSV sujo ou limpo")
    p_profile.set_defaults(handler=cmd_profile)

    sub.add_parser(
        "clean", parents=[comum], help="limpa, valida e grava os dois CSVs"
    ).set_defaults(handler=cmd_clean)
    sub.add_parser("report", parents=[comum], help="gera o index.html").set_defaults(
        handler=cmd_report
    )
    sub.add_parser("run", parents=[comum], help="a cadeia inteira").set_defaults(handler=cmd_run)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "handler", None) is None:
        parser.print_help()
        return 2

    args.today = args.today or dt.date.today()

    try:
        return int(args.handler(args))
    except (FileNotFoundError, pl.exceptions.ComputeError) as erro:
        print(f"arquivo nao encontrado ou ilegivel: {erro}", file=sys.stderr)
        return 2
