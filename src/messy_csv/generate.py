"""Dataset de pedidos propositalmente sujo, deterministico sob a seed 42.

Cada sujeira tem causa plausivel declarada (spec §5). O determinismo vem de uma
unica instancia de random.Random e de uma ordem fixa de sorteios por linha:
trocar a ordem das chamadas muda o dataset inteiro.
"""

from __future__ import annotations

import datetime as dt
import random
from pathlib import Path

import polars as pl

from messy_csv.contract import RAW_COLUMNS

SEED = 42
ROWS = 5_000

DATE_START = dt.date(2023, 1, 1)
DATE_END = dt.date(2024, 12, 31)
OUT_OF_RANGE_START = dt.date(2019, 1, 1)
OUT_OF_RANGE_END = dt.date(2019, 12, 31)

# Tabela explicita: strftime("%b") depende do locale da maquina, e um locale
# pt-BR produziria "mar" — que o parser %b (ingles) do chrono rejeita.
# fmt: off
MONTH_ABBR: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)
# fmt: on

# fmt: off
FIRST_NAMES: tuple[str, ...] = (
    "Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Henrique",
    "Isabela", "João", "Karina", "Lucas", "Mariana", "Nuno", "Olívia", "Paulo",
    "Rafael", "Sofia", "Tiago", "Vitória",
)
# fmt: on

# fmt: off
LAST_NAMES: tuple[str, ...] = (
    "Almeida", "Barbosa", "Carvalho", "Duarte", "Esteves", "Ferreira", "Gomes",
    "Henriques", "Jesus", "Klein", "Lopes", "Martins", "Nogueira", "Oliveira",
    "Pereira", "Queiroz", "Ribeiro", "Santos", "Teixeira", "Vasconcelos",
)
# fmt: on

# Apenas as grafias NAO canonicas: a canonica e sorteada a parte (70% dos casos).
CATEGORY_VARIANTS: dict[str, tuple[str, ...]] = {
    "Eletrônicos": ("eletronicos", "ELETRONICOS", "Eletrônico", "eletro"),
    "Moda": ("moda", "MODA", "Modas", "vestuario"),
    "Casa": ("casa", "Casa e Decoração", "casa_decoracao"),
    "Livros": ("livros", "LIVRO", "livraria"),
    "Esporte": ("esporte", "Esportes", "ESPORTE"),
}
CANONICAL_NAMES: tuple[str, ...] = tuple(CATEGORY_VARIANTS)
UNRECOVERABLE_CATEGORIES: tuple[str, ...] = ("diversos", "outros", "misc")

DUPLICATE_RATE = 0.03
WHITESPACE_RATE = 0.12


def build_frame(seed: int = SEED) -> pl.DataFrame:
    rng = random.Random(seed)
    return pl.from_dicts(
        _build_rows(rng),
        schema={nome: pl.String() for nome in RAW_COLUMNS},
    )


def write_dirty_dataset(path: Path, seed: int = SEED) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    # line_terminator explicito: o hash tem de ser o mesmo no Windows e no CI Linux.
    build_frame(seed).write_csv(path, line_terminator="\n")
    return path


def _build_rows(rng: random.Random) -> list[dict[str, str]]:
    rows = [_make_row(rng, order_id) for order_id in range(1, ROWS + 1)]

    # Retry de integracao com o marketplace: a segunda copia chega degradada,
    # entao a deduplicacao tem de eleger a original (spec §5.4).
    metade = ROWS // 2
    alvos = sorted(rng.sample(range(metade, ROWS), k=int(ROWS * DUPLICATE_RATE)))
    for alvo in alvos:
        origem = rng.randrange(0, metade)
        clone = dict(rows[origem])
        clone[rng.choice(("category", "amount", "customer"))] = ""
        rows[alvo] = clone
    return rows


def _make_row(rng: random.Random, order_id: int) -> dict[str, str]:
    campos = {
        "order_id": _order_id_cell(rng, order_id),
        "order_date": _date_cell(rng),
        "customer": _customer_cell(rng),
        "category": _category_cell(rng),
        "amount": _amount_cell(rng),
    }
    return {nome: _maybe_dirty_whitespace(rng, valor) for nome, valor in campos.items()}


def _order_id_cell(rng: random.Random, order_id: int) -> str:
    if rng.random() < 0.01:
        return rng.choice(("", "ORD-1023", "0"))
    return str(order_id)


def _date_cell(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.01:  # fora do intervalo, mas em formato impecavel
        return _random_date(rng, OUT_OF_RANGE_START, OUT_OF_RANGE_END).isoformat()

    data = _random_date(rng, DATE_START, DATE_END)
    if roll < 0.60:
        return data.isoformat()
    if roll < 0.85:
        return data.strftime("%d/%m/%Y")
    if roll < 0.93:
        return f"{MONTH_ABBR[data.month - 1]} {data.day:02d} {data.year}"
    if roll < 0.98:
        return f"{data.isoformat()} 10:30:00"
    return f"{data.year}-13-{data.day:02d}"  # mes 13: irrecuperavel


def _random_date(rng: random.Random, inicio: dt.date, fim: dt.date) -> dt.date:
    return inicio + dt.timedelta(days=rng.randint(0, (fim - inicio).days))


def _customer_cell(rng: random.Random) -> str:
    if rng.random() < 0.02:
        return ""
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def _category_cell(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.03:
        return ""
    if roll < 0.06:
        return rng.choice(UNRECOVERABLE_CATEGORIES)

    canonica = rng.choice(CANONICAL_NAMES)
    if rng.random() < 0.30:
        return rng.choice(CATEGORY_VARIANTS[canonica])
    return canonica


def _amount_cell(rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.02:
        return ""
    if roll < 0.04:
        return rng.choice(("-", "n/a"))
    if roll < 0.05:
        return rng.choice(("0,00", "-50,00"))

    moeda = "USD" if rng.random() < 0.18 else "BRL"
    valor = round(rng.uniform(19.9, 4999.0), 2)
    if moeda == "USD":
        return f"$ {valor:.2f}" if rng.random() < 0.5 else f"USD {valor:.2f}"

    # 1299.9 -> "1,299.90" -> "1.299,90": separadores trocados via marcador neutro.
    texto = f"{valor:,.2f}".replace(",", "|").replace(".", ",").replace("|", ".")
    return f"R$ {texto}" if rng.random() < 0.5 else texto


def _maybe_dirty_whitespace(rng: random.Random, valor: str) -> str:
    if not valor or rng.random() >= WHITESPACE_RATE:
        return valor
    estilo = rng.randrange(3)
    if estilo == 0:
        return f"  {valor}"
    if estilo == 1:
        return f"{valor}  "
    return valor.replace(" ", "  ", 1)
