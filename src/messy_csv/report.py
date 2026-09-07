"""Do frame largo ao HTML: composicao dos dados do relatorio e renderizacao.

Nenhuma funcao aqui le o relogio. `generated_at` entra por parametro, como todo
o resto do projeto (12.5), porque um relatorio que carimba a hora sozinho
produz um diff novo a cada execucao e destroi a prova de determinismo.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import jinja2
import polars as pl

from messy_csv import contract, metrics, profile

SAMPLE_SIZE = 8
TEMPLATE_DIR = Path(__file__).parent / "templates"
TEMPLATE_NAME = "report.html.j2"
REPORT_PATH = Path("docs/index.html")


def format_brl(value: float) -> str:
    """1234.5 -> 'R$ 1.234,50'. A troca de separadores e manual e proposital.

    `locale.setlocale` depende de o locale pt_BR existir na maquina, e ele nao
    existe no runner do CI. Um relatorio cujo numero muda conforme o sistema
    operacional nao serve como prova de nada.
    """
    americano = f"{value:,.2f}"
    return "R$ " + americano.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


@dataclass(frozen=True)
class SampleRow:
    before: dict[str, str]
    after: dict[str, str]


@dataclass(frozen=True)
class QuarantineGroup:
    reason: str
    rows: int
    example: dict[str, str]


@dataclass(frozen=True)
class ReportData:
    generated_at: dt.date
    comparison: metrics.Comparison
    dirt: list[dict[str, object]]
    samples: list[SampleRow]
    quarantine: list[QuarantineGroup]

    @property
    def columns(self) -> tuple[str, ...]:
        """O template itera as cinco colunas do dado bruto sem reimportar o contrato."""
        return contract.RAW_COLUMNS


def build_samples(
    transformed: pl.DataFrame, today: dt.date, limit: int = SAMPLE_SIZE
) -> list[SampleRow]:
    """As primeiras `limit` linhas aprovadas em que a limpeza mudou algo.

    A selecao e por ordem de origem, nao por sorteio: uma amostra aleatoria
    mudaria a cada execucao e o relatorio deixaria de ser reproduzivel.
    """
    aprovadas = (
        transformed.with_columns(contract.reject_reason_expr(today))
        .filter(pl.col("reject_reason") == "")
        .sort("source_index")
        .select(
            *(pl.col(f"raw_{nome}") for nome in contract.RAW_COLUMNS),
            "order_id",
            "order_date",
            "t_customer",
            "category",
            "amount_brl",
        )
    )

    amostras: list[SampleRow] = []
    for linha in aprovadas.to_dicts():
        antes = {nome: str(linha[f"raw_{nome}"] or "") for nome in contract.RAW_COLUMNS}
        depois = {
            "order_id": str(linha["order_id"]),
            "order_date": str(linha["order_date"].isoformat()),
            "customer": str(linha["t_customer"]),
            "category": str(linha["category"]),
            "amount": format_brl(float(linha["amount_brl"])),
        }
        if antes != depois:
            amostras.append(SampleRow(before=antes, after=depois))
        if len(amostras) == limit:
            break
    return amostras


def group_quarantine(rejected: pl.DataFrame) -> list[QuarantineGroup]:
    """Uma linha com dois motivos conta nos dois grupos.

    A soma dos grupos pode ultrapassar o total de linhas rejeitadas, e isso e
    correto: a pergunta que a secao responde e "quantas linhas cada regra pegou",
    nao "como as linhas se dividem".
    """
    if rejected.height == 0:
        return []

    explodido = rejected.with_columns(
        pl.col("reject_reason").str.split(contract.REJECT_REASON_SEPARATOR)
    ).explode("reject_reason")

    grupos = (
        explodido.group_by("reject_reason", maintain_order=True)
        .agg(pl.len().alias("linhas"), pl.exclude("reject_reason").first())
        .sort(["linhas", "reject_reason"], descending=[True, False])
    )

    return [
        QuarantineGroup(
            reason=str(linha["reject_reason"]),
            rows=int(linha["linhas"]),
            example={nome: str(linha[nome] or "") for nome in contract.RAW_COLUMNS},
        )
        for linha in grupos.to_dicts()
    ]


def build(
    raw: pl.DataFrame,
    transformed: pl.DataFrame,
    accepted: pl.DataFrame,
    rejected: pl.DataFrame,
    today: dt.date,
) -> ReportData:
    visao_bruta = profile.view_from_raw(raw)
    antes = profile.profile(visao_bruta, today)
    depois = profile.profile(profile.view_from_clean(accepted), today)
    return ReportData(
        generated_at=today,
        comparison=metrics.compare(antes, depois, rows_quarantined=rejected.height),
        dirt=profile.dirt_counts(visao_bruta),
        samples=build_samples(transformed, today),
        quarantine=group_quarantine(rejected),
    )


def _environment() -> jinja2.Environment:
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render(data: ReportData) -> str:
    """`StrictUndefined` e `autoescape` nao sao preferencia de estilo.

    Sem o primeiro, um nome de variavel errado no template vira string vazia e o
    relatorio publica uma secao em branco sem avisar. Sem o segundo, um nome de
    cliente vindo do CSV pode injetar marcacao na pagina publicada.
    """
    return _environment().get_template(TEMPLATE_NAME).render(data=data)


def write(data: ReportData, path: Path = REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(data), encoding="utf-8", newline="\n")
    return path
