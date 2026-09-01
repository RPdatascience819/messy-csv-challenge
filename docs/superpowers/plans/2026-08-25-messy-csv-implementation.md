# Messy CSV Challenge — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir o repositório completo do Messy CSV Challenge — gerador determinístico de dataset sujo, pipeline de limpeza testado com TDD, validação com quarentena e relatório HTML publicado — na ordem em que as decisões foram tomadas, sem retrofit.

**Architecture:** Pacote Python único (`src/messy_csv/`) com camadas separadas por responsabilidade: seis transformadores puros `DataFrame -> DataFrame` em `clean/`, um validador central em `contract.py` que é o único lugar onde "limpo" está definido, e um profiler que reusa as mesmas expressões Polars dos transformadores para medir antes e depois com a mesma régua. O frame do pipeline carrega colunas `raw_*` (texto original, intocado), `t_*` (texto aparado) e as colunas tipadas do contrato lado a lado — nada é sobrescrito, então a quarentena mostra o dado como ele chegou.

**Tech Stack:** Python 3.13, uv, Polars (eager), Jinja2, pytest + pytest-cov, ruff, mypy strict, pre-commit, GitHub Actions, GitHub Pages.

**Spec:** `docs/superpowers/specs/2026-08-24-messy-csv-design.md`

---

## Global Constraints

Valores copiados literalmente da spec. Valem para toda tarefa.

- **Python 3.13** é o runtime mínimo (§10). O Python do sistema é 3.11 — resolver com `uv python pin 3.13`, nunca com o interpretador global.
- **Polars eager** (`pl.DataFrame`), nunca `LazyFrame` (D3).
- **`infer_schema=False`** na leitura do CSV sujo: as cinco colunas entram como texto (§4.1).
- **Seed fixa `42`**, **5.000 linhas** no gerador (§5).
- **Intervalo válido de datas:** `2023-01-01` até a data de execução (§4.2). Toda função que precisa de "hoje" recebe `today: datetime.date` como parâmetro — nunca chama `date.today()` internamente (§12.5).
- **Categorias canônicas:** `Eletrônicos`, `Moda`, `Casa`, `Livros`, `Esporte`, `Não informado` (§4.2).
- **Moedas:** `BRL`, `USD` (§4.2).
- **Motivos de rejeição** (exatamente estes nove, §4.3): `order_id inválido`, `order_id duplicado irreconciliável`, `data inválida`, `data fora do intervalo`, `cliente ausente`, `categoria desconhecida`, `valor ausente`, `valor inválido`, `valor não positivo`. Separador na coluna `reject_reason`: `"; "`.
- **Ordem dos transformadores é fixa** (§6.1): whitespace → dates → currency → categories → duplicates → missing. Nunca reordenar.
- **Transformadores nunca rejeitam linha; o contrato nunca transforma dado** (D5).
- **Dinheiro nunca é imputado** (D7). Só `category` ausente vira `Não informado`.
- **Nenhuma requisição externa** no HTML do relatório: CSS local ou inline (§9).
- **Cobertura mínima 90%** em `contract.py` e em `clean/` (§8).
- **Mensagens de commit** em português, formato Conventional Commits.
- Todo módulo começa com `from __future__ import annotations`.

---

## Lacunas da spec resolvidas neste plano

A spec é detalhada, mas cinco pontos ficariam impossíveis de implementar sem uma
decisão adicional. Cada decisão está isolada aqui para poder ser vetada sem
reescrever o resto do plano.

### L1 — Ordem das etapas: profiling depois do pipeline

A spec ordena Profiling (Etapa 6) antes do Pipeline (Etapa 7). Mas as seis
dimensões do §7 medem precisamente o que os transformadores consertam: "datas
parseáveis e no intervalo", "linhas em categoria canônica", "valores parseáveis
com moeda identificada". Escrever `profile.py` primeiro exigiria duplicar os
parsers ou fazer retrofit depois — os dois contradizem a tese do projeto.

**Decisão:** o plano constrói os transformadores primeiro (Tasks 5–11) e o
profiler depois (Task 12), importando as expressões públicas de `clean/`. Assim
existe **uma única definição** de "data válida" no repositório, e o before/after
do relatório é comparável por construção, não por coincidência. O critério da
Etapa 6 ("score do raw calculado e reproduzível") continua sendo cumprido.

### L2 — Quatro motivos de rejeição sem produtor

O §4.3 lista nove motivos; o catálogo do §5 só gera cinco deles. Sem geração,
`rejects.csv` nunca conteria `order_id inválido`, `data fora do intervalo`,
`valor inválido` ou `valor não positivo`, e o teste de quarentena do §8 ("cada
motivo é produzido por ao menos um caso") seria insatisfazível com dado real.

**Decisão — taxas adicionadas ao gerador:**

| Motivo | Taxa | Como é gerado |
|---|---|---|
| `order_id inválido` | 1% | `""`, `"ORD-1023"` ou `"0"` no lugar do id |
| `data fora do intervalo` | 1% | data sorteada em 2019, formatada em ISO |
| `valor inválido` | 2% | `"-"` ou `"n/a"` |
| `valor não positivo` | 1% | `"0,00"` ou `"-50,00"` |

Os 4% de `amount` ausente do §5 são divididos: **2% célula vazia** (motivo
`valor ausente`) e **2% texto não-parseável** (motivo `valor inválido`). A
distinção importa porque são falhas diferentes — importação que perdeu o campo
versus importação que trouxe lixo — e a quarentena deve dizer qual foi.

O 1% de datas fora do intervalo sai da fatia `%Y-%m-%d` do §5.1, que passa de
60% para 59%; as demais proporções não mudam.

### L3 — Perdedor da deduplicação vai para a quarentena

O §5.4 diz que a linha vencedora, se ainda violar o contrato, é quarentenada com
o motivo `order_id duplicado irreconciliável`. Mas a vencedora que viola já
recebe seus motivos específicos (`valor ausente`, etc.), e as **perdedoras**
seriam descartadas silenciosamente — o que contradiz D6, "Nenhum dado é
destruído".

**Decisão:** `duplicates.py` marca as perdedoras com a booleana
`is_duplicate_loser`; `contract.py` as rejeita com o motivo `order_id duplicado
irreconciliável`. O motivo passa a ter exatamente um produtor, `rejects.csv`
contém toda linha descartada, e D6 é literalmente verdadeiro.

### L4 — Ancoragem temporal do dataset e da tabela de câmbio

A spec não diz em que intervalo o gerador sorteia datas, mas `data/fx_rates.csv`
precisa de um intervalo finito de competências para ser escrito à mão.

**Decisão:** o gerador sorteia datas em **2023-01-01 a 2024-12-31** (mais o 1%
de L2 em 2019). A tabela de câmbio cobre as 24 competências desse intervalo,
para `USD` e para `BRL` (esta com taxa `1.000000`, tornando o join total e
dispensando caso especial no código). Um teste garante que toda competência
presente no dado aceito existe na tabela — se um mês faltasse, `amount_brl`
viraria nulo e o dado sairia errado em silêncio.

### L5 — Quem converte `order_id` para inteiro

Os seis transformadores do §6 não incluem um passo de tipagem de `order_id`.

**Decisão:** `duplicates.py` faz o cast, por ser o primeiro e único consumidor
de `order_id`. Criar um sétimo transformador para uma linha de código seria
abstração especulativa.

---

## Estrutura de arquivos

```
messy-csv-challenge/
├─ .github/workflows/ci.yml
├─ .gitignore
├─ .pre-commit-config.yaml
├─ pyproject.toml
├─ uv.lock
├─ README.md
├─ data/
│  ├─ fx_rates.csv                  # versionado à mão (D4)
│  ├─ raw/orders_dirty.csv          # gerado
│  ├─ clean/orders.csv              # gerado
│  └─ rejects/rejects.csv           # gerado
├─ docs/
│  ├─ .nojekyll                     # desliga o Jekyll do GitHub Pages
│  ├─ index.html                    # gerado, publicado no Pages
│  └─ superpowers/{specs,plans}/
├─ src/messy_csv/
│  ├─ __init__.py
│  ├─ contract.py     # schema alvo, nove regras, separação aprovados/rejeitados
│  ├─ generate.py     # dataset sujo determinístico (seed 42)
│  ├─ pipeline.py     # carga, orquestração dos seis, escrita dos artefatos
│  ├─ profile.py      # ProfileResult + as seis dimensões + contagens de sujeira
│  ├─ metrics.py      # compara dois ProfileResult
│  ├─ report.py       # monta ReportData e renderiza via Jinja2
│  ├─ cli.py          # argparse: generate/profile/clean/report/run
│  ├─ templates/report.html.j2
│  └─ clean/
│     ├─ __init__.py
│     ├─ whitespace.py
│     ├─ dates.py
│     ├─ currency.py
│     ├─ categories.py
│     ├─ duplicates.py
│     └─ missing.py
└─ tests/
   ├─ conftest.py
   ├─ test_contract.py
   ├─ test_generate.py
   ├─ test_pipeline.py
   ├─ test_profile.py
   ├─ test_metrics.py
   ├─ test_report.py
   ├─ test_cli.py
   └─ clean/test_{whitespace,dates,currency,categories,duplicates,missing}.py
```

### Ciclo de vida das colunas do frame

Nenhum transformador sobrescreve coluna existente. O frame só cresce:

| Estágio | Colunas adicionadas | Tipo |
|---|---|---|
| carga | `source_index`, `raw_order_id`, `raw_order_date`, `raw_customer`, `raw_category`, `raw_amount` | `UInt32`, `String`×5 |
| whitespace | `t_order_id`, `t_order_date`, `t_customer`, `t_category`, `t_amount` | `String`×5 |
| dates | `order_date` | `Date` |
| currency | `amount_original`, `currency_original`, `amount_brl` | `Float64`, `String`, `Float64` |
| categories | `category` | `String` (vira `Enum` no contrato) |
| duplicates | `order_id`, `is_duplicate_loser` | `Int64`, `Boolean` |
| missing | (reescreve só `category`) | — |

`raw_*` sobrevive intacto até o fim: é o que a quarentena grava. Essa é a razão
de os transformadores escreverem em colunas novas em vez de mutar as originais.

---

## Task 1: Repositório, ambiente e esqueleto do pacote

Cobre as Etapas 1 e 2 da spec. Ao final existe um repositório Git com a spec
como primeiro commit e um ambiente `uv` reprodutível que roda pytest.

**Files:**
- Create: `.gitignore`, `pyproject.toml`, `.python-version`, `src/messy_csv/__init__.py`, `src/messy_csv/clean/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`
- Generated: `uv.lock`

**Interfaces:**
- Consumes: nada (primeira tarefa)
- Produces: pacote importável `messy_csv` com `__version__: str`; comandos `uv run pytest`, `uv run ruff`, `uv run mypy` disponíveis

- [ ] **Step 1: Inicializar o repositório com a spec como primeiro commit**

O primeiro commit precisa conter **apenas** a spec. É o que prova, no `git log`,
que o design veio antes do código.

```bash
git init
git add docs/superpowers/specs/2026-08-24-messy-csv-design.md
git commit -m "docs: spec de design do Messy CSV Challenge"
```

- [ ] **Step 2: Verificar que o primeiro commit contém só a spec**

Run: `git log --stat --oneline`
Expected: um único commit, com exatamente um arquivo alterado, o `.md` da spec.

- [ ] **Step 3: Fixar o Python 3.13**

O Python do sistema é 3.11. `uv` baixa e fixa a versão certa sem tocar no
interpretador global — é essa a razão de o projeto usar `uv` e não `venv`.

```bash
uv python pin 3.13
```

Isso cria `.python-version` com o conteúdo `3.13`.

- [ ] **Step 4: Escrever o `.gitignore`**

```gitignore
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
```

`data/raw/`, `data/clean/`, `data/rejects/` e `docs/index.html` **não** são
ignorados: são artefatos determinísticos, e o repositório deve mostrá-los
prontos para quem abrir em cinco minutos.

- [ ] **Step 5: Escrever o `pyproject.toml`**

```toml
[project]
name = "messy-csv"
version = "0.1.0"
description = "Ciclo completo de qualidade de dados: gerar sujeira, medir, limpar e publicar a prova"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "polars>=1.20",
    "jinja2>=3.1",
]

[project.scripts]
messy-csv = "messy_csv.cli:main"

[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-cov>=6.0",
    "mypy>=1.14",
    "ruff>=0.9",
    "pre-commit>=4.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/messy_csv"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.coverage.run]
source = ["src/messy_csv"]
```

- [ ] **Step 6: Criar o esqueleto do pacote**

`src/messy_csv/__init__.py`:

```python
"""Ciclo completo de qualidade de dados sobre um CSV propositalmente sujo."""

from __future__ import annotations

__version__ = "0.1.0"
```

`src/messy_csv/clean/__init__.py`:

```python
"""Transformadores puros: cada um recebe e devolve um DataFrame, sem rejeitar linha."""

from __future__ import annotations
```

`tests/__init__.py`: arquivo vazio.

- [ ] **Step 7: Escrever o teste de fumaça**

Ele existe para provar que o ambiente está de pé antes de qualquer lógica de
domínio.

`tests/test_smoke.py`:

```python
from __future__ import annotations

import messy_csv


def test_pacote_importa_e_declara_versao() -> None:
    assert messy_csv.__version__ == "0.1.0"
```

- [ ] **Step 8: Sincronizar o ambiente e rodar o teste**

Run: `uv sync && uv run pytest`
Expected: `1 passed`. O arquivo `uv.lock` foi criado.

- [ ] **Step 9: Confirmar a versão do Python do ambiente**

Run: `uv run python -c "import sys; print(sys.version_info[:2])"`
Expected: `(3, 13)` — não `(3, 11)`.

- [ ] **Step 10: Commit**

```bash
git add .gitignore .python-version pyproject.toml uv.lock src tests
git commit -m "chore: ambiente uv com Python 3.13 e esqueleto do pacote"
```

---

## Task 2: Ferramental de qualidade e CI

Cobre a Etapa 3. O critério da spec é explícito e incomum: ruff, mypy,
pre-commit e CI rodando **em repositório ainda vazio**. A razão é que uma
barreira instalada depois só reprova código que já existe, e a tentação passa a
ser afrouxar a barreira em vez de consertar o código. Instalada antes, ela nunca
teve nada a perdoar.

**Files:**
- Create: `.pre-commit-config.yaml`, `.github/workflows/ci.yml`
- Modify: `pyproject.toml` (acrescentar `[tool.ruff]` e `[tool.mypy]`)

**Interfaces:**
- Consumes: `pyproject.toml` e o ambiente da Task 1
- Produces: os comandos de verificação usados por toda tarefa seguinte —
  `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`,
  `uv run pytest`

- [ ] **Step 1: Adicionar a configuração do ruff e do mypy ao `pyproject.toml`**

Acrescente ao final do arquivo:

```toml
[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = [
    "E", "W",   # pycodestyle
    "F",        # pyflakes
    "I",        # isort
    "N",        # pep8-naming
    "UP",       # pyupgrade
    "B",        # flake8-bugbear
    "SIM",      # flake8-simplify
    "RUF",      # regras do próprio ruff
]

[tool.mypy]
python_version = "3.13"
strict = true
warn_unreachable = true
files = ["src"]
```

`strict = true` liga de uma vez `disallow_untyped_defs`, `no_implicit_optional`,
`warn_return_any` e mais nove flags. Ligar o conjunto agora significa que toda
função nascerá anotada; ligar depois significaria uma tarefa de anotação em
massa que ninguém faz.

- [ ] **Step 2: Rodar as três verificações no repositório ainda vazio**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: as três passam. Se `ruff format --check` reclamar do esqueleto, rode
`uv run ruff format .` e siga.

- [ ] **Step 3: Escrever o `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-toml
      - id: check-added-large-files

  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.4
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy (strict)
        entry: uv run mypy src
        language: system
        pass_filenames: false
        types: [python]
```

O hook do mypy é `local` de propósito: o hook oficial roda num ambiente isolado
que não enxerga `polars`, e um type-check sem os stubs das dependências reprova
o que está certo e aprova o que está errado.

**Atenção Windows:** `trailing-whitespace` e `end-of-file-fixer` normalizam
finais de linha. Se o Git estiver com `core.autocrlf=true`, o hook e o Git
brigam a cada commit. Rode `git config core.autocrlf input` neste repositório.

- [ ] **Step 4: Instalar e rodar os hooks**

```bash
git config core.autocrlf input
uv run pre-commit install
uv run pre-commit run --all-files
```

Expected: todos os hooks passam (ou corrigem arquivos e passam na segunda
execução).

- [ ] **Step 5: Escrever o workflow de CI**

`.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Instalar uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Sincronizar o ambiente
        run: uv sync --locked

      - name: Lint
        run: uv run ruff check .

      - name: Formatacao
        run: uv run ruff format --check .

      - name: Type check
        run: uv run mypy src

      - name: Testes com cobertura
        run: uv run pytest --cov=messy_csv --cov-report=term-missing

      - name: Cobertura minima em contract.py e clean/
        run: >
          uv run coverage report
          --include="*/messy_csv/contract.py,*/messy_csv/clean/*"
          --fail-under=90
```

O último passo existe porque `--cov-fail-under` só sabe aplicar um limiar
global, e a spec exige 90% em dois caminhos específicos. Um limiar global de 90%
seria satisfeito por testes concentrados no gerador enquanto o contrato ficasse
descoberto — exatamente o inverso do que importa.

`uv sync --locked` falha se `uv.lock` estiver desatualizado. É o que torna o
lockfile uma promessa verificada, e não um arquivo decorativo.

- [ ] **Step 6: Commit**

```bash
git add .pre-commit-config.yaml .github/workflows/ci.yml pyproject.toml
git commit -m "chore: ruff, mypy strict, pre-commit e CI antes do primeiro modulo"
```

---

## Task 3: Contrato de dados

Cobre a Etapa 4. `contract.py` é o único lugar do repositório onde "limpo" está
definido (D5). Ele nasce **antes** de qualquer pipeline: se o alvo fosse escrito
depois dos transformadores, ele descreveria o que os transformadores já fazem em
vez de definir o que eles precisam fazer.

**Files:**
- Create: `src/messy_csv/contract.py`
- Test: `tests/test_contract.py`

**Interfaces:**
- Consumes: nada além de Polars
- Produces:
  - `CATEGORIES: tuple[str, ...]`, `CURRENCIES: tuple[str, ...]`, `MIN_DATE: dt.date`
  - `RAW_COLUMNS: tuple[str, ...]`, `CLEAN_COLUMNS: tuple[str, ...]`
  - `clean_schema() -> dict[str, pl.DataType]`
  - `reject_reason_expr(today: dt.date) -> pl.Expr`
  - `validate(df: pl.DataFrame, today: dt.date) -> tuple[pl.DataFrame, pl.DataFrame]`
  - `ContractError(RuntimeError)`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_contract.py`:

```python
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
    alcancados = {
        motivo
        for motivo, _ in contract.reject_reasons(TODAY)
    }
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
```

O último par de testes existe por causa da suposição §12.5: o limite superior é
"a data de execução". Um teste que chamasse `date.today()` passaria hoje e
falharia amanhã. Injetar `TODAY` transforma uma dependência de relógio em um
parâmetro — é por isso que `validate` recebe `today` e nunca o consulta.

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/test_contract.py -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'messy_csv.contract'`.

- [ ] **Step 3: Escrever `contract.py`**

```python
"""Schema alvo e as nove regras que definem uma linha limpa.

Este e o unico modulo que decide se uma linha e aceita. Os transformadores
consertam o que da e deixam nulo o que nao da; a decisao mora aqui (D5).
"""

from __future__ import annotations

import datetime as dt

import polars as pl

CATEGORIES: tuple[str, ...] = (
    "Eletrônicos",
    "Moda",
    "Casa",
    "Livros",
    "Esporte",
    "Não informado",
)
CURRENCIES: tuple[str, ...] = ("BRL", "USD")

MIN_DATE = dt.date(2023, 1, 1)

RAW_COLUMNS: tuple[str, ...] = (
    "order_id",
    "order_date",
    "customer",
    "category",
    "amount",
)

CLEAN_COLUMNS: tuple[str, ...] = (
    "order_id",
    "order_date",
    "customer",
    "category",
    "amount_original",
    "currency_original",
    "amount_brl",
)

REJECT_REASON_SEPARATOR = "; "


class ContractError(RuntimeError):
    """Uma linha aprovada violou o schema alvo: erro de programa, nao de dado."""


def clean_schema() -> dict[str, pl.DataType]:
    return {
        "order_id": pl.Int64(),
        "order_date": pl.Date(),
        "customer": pl.String(),
        "category": pl.Enum(list(CATEGORIES)),
        "amount_original": pl.Float64(),
        "currency_original": pl.Enum(list(CURRENCIES)),
        "amount_brl": pl.Float64(),
    }


def reject_reasons(today: dt.date) -> list[tuple[str, pl.Expr]]:
    """Os nove motivos do contrato, na ordem em que aparecem em reject_reason."""
    order_id = pl.col("order_id")
    order_date = pl.col("order_date")
    amount = pl.col("amount_original")
    return [
        ("order_id inválido", order_id.is_null() | (order_id <= 0)),
        ("order_id duplicado irreconciliável", pl.col("is_duplicate_loser")),
        ("data inválida", order_date.is_null()),
        (
            "data fora do intervalo",
            order_date.is_not_null() & ((order_date < MIN_DATE) | (order_date > today)),
        ),
        ("cliente ausente", pl.col("t_customer").is_null()),
        ("categoria desconhecida", pl.col("category").is_null()),
        ("valor ausente", pl.col("t_amount").is_null()),
        ("valor inválido", pl.col("t_amount").is_not_null() & amount.is_null()),
        ("valor não positivo", amount.is_not_null() & (amount <= 0)),
    ]


def reject_reason_expr(today: dt.date) -> pl.Expr:
    parts = [
        pl.when(condicao).then(pl.lit(motivo)).otherwise(pl.lit(None, dtype=pl.String))
        for motivo, condicao in reject_reasons(today)
    ]
    return (
        pl.concat_list(parts)
        .list.drop_nulls()
        .list.join(REJECT_REASON_SEPARATOR)
        .alias("reject_reason")
    )


def validate(df: pl.DataFrame, today: dt.date) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Separa o frame do pipeline em aprovados (schema alvo) e rejeitados (originais)."""
    marked = df.with_columns(reject_reason_expr(today))

    rejected = marked.filter(pl.col("reject_reason") != "").select(
        *(pl.col(f"raw_{nome}").alias(nome) for nome in RAW_COLUMNS),
        pl.col("reject_reason"),
    )

    accepted = marked.filter(pl.col("reject_reason") == "").select(
        pl.col("order_id"),
        pl.col("order_date"),
        pl.col("t_customer").alias("customer"),
        pl.col("category").cast(pl.Enum(list(CATEGORIES))),
        pl.col("amount_original"),
        pl.col("currency_original").cast(pl.Enum(list(CURRENCIES))),
        pl.col("amount_brl"),
    )
    _assert_sem_nulos(accepted)
    return accepted, rejected


def _assert_sem_nulos(accepted: pl.DataFrame) -> None:
    """Rede de seguranca: nenhuma regra cobre cambio ausente, e dado errado nao sai daqui."""
    nulos = [
        nome for nome, quantidade in accepted.null_count().row(0, named=True).items() if quantidade
    ]
    if nulos:
        raise ContractError(
            f"linhas aprovadas contem nulo em: {', '.join(nulos)} — "
            "provavel competencia ausente em data/fx_rates.csv"
        )
```

Duas escolhas merecem justificativa:

**`reject_reasons()` é pública.** Ela poderia ser privada, mas então o teste
"todos os nove motivos são alcançáveis" precisaria importar `_rules` — um teste
que fura o encapsulamento para verificar a completude do contrato. Expor a lista
de regras é mais honesto: ela **é** o contrato, e o relatório também a consome
para listar os motivos possíveis.

**`_assert_sem_nulos` levanta em vez de rejeitar.** Um nulo residual em linha
aprovada não é dado sujo — é bug de programa (competência faltando em
`fx_rates.csv`). Transformá-lo em motivo de rejeição esconderia o bug dentro de
um artefato que parece normal. Falhar alto força o conserto.

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/test_contract.py -v`
Expected: todos PASS.

- [ ] **Step 5: Verificar cobertura e tipos**

Run: `uv run pytest --cov=messy_csv.contract --cov-report=term-missing tests/test_contract.py && uv run mypy src`
Expected: cobertura de `contract.py` ≥ 90%; mypy sem erro.

- [ ] **Step 6: Commit**

```bash
git add src/messy_csv/contract.py tests/test_contract.py
git commit -m "feat: contrato de dados com os nove motivos de quarentena"
```

---

## Task 4: Gerador determinístico do dataset sujo

Cobre a Etapa 5. O critério é determinismo provado por hash: duas execuções com
seed 42 produzem o mesmo SHA-256. Sem isso, o before/after do relatório mediria
duas amostras diferentes e a melhora poderia ser ruído.

**Files:**
- Create: `src/messy_csv/generate.py`
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: `contract.RAW_COLUMNS`
- Produces:
  - `SEED: int`, `ROWS: int`, `DATE_START: dt.date`, `DATE_END: dt.date`
  - `build_frame(seed: int = SEED) -> pl.DataFrame` (5 colunas `String`)
  - `write_dirty_dataset(path: Path, seed: int = SEED) -> Path`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_generate.py`:

```python
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
    df = generate.build_frame()
    iso = df.filter(pl.col("order_date").str.contains(r"^\d{4}-\d{2}-\d{2}$")).height

    nao_iso = (generate.ROWS - iso) / generate.ROWS
    assert 0.36 <= nao_iso <= 0.44


def test_ids_duplicados_ficam_perto_de_tres_por_cento() -> None:
    df = generate.build_frame().with_columns(pl.col("order_id").str.strip_chars())
    numericos = df.filter(
        pl.col("order_id").str.contains(r"^\d+$") & (pl.col("order_id") != "0")
    )

    perdidos = numericos.height - numericos["order_id"].n_unique()
    assert 130 <= perdidos <= 170


def test_moeda_estrangeira_fica_perto_de_dezoito_por_cento() -> None:
    df = generate.build_frame()
    usd = df.filter(pl.col("amount").str.contains(r"(?i)(\$|usd)")).height

    # o "R$" tambem contem "$": conta so o que nao e real
    reais = df.filter(pl.col("amount").str.contains(r"R\$")).height
    assert 0.15 <= (usd - reais) / generate.ROWS <= 0.21


def test_todas_as_seis_sujeiras_aparecem() -> None:
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
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/test_generate.py -v`
Expected: FAIL com `ImportError: cannot import name 'generate'`.

- [ ] **Step 3: Escrever `generate.py`**

```python
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
MONTH_ABBR: tuple[str, ...] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)

FIRST_NAMES: tuple[str, ...] = (
    "Ana", "Bruno", "Carla", "Diego", "Eduarda", "Felipe", "Gabriela", "Henrique",
    "Isabela", "João", "Karina", "Lucas", "Mariana", "Nuno", "Olívia", "Paulo",
    "Rafael", "Sofia", "Tiago", "Vitória",
)
LAST_NAMES: tuple[str, ...] = (
    "Almeida", "Barbosa", "Carvalho", "Duarte", "Esteves", "Ferreira", "Gomes",
    "Henriques", "Jesus", "Klein", "Lopes", "Martins", "Nogueira", "Oliveira",
    "Pereira", "Queiroz", "Ribeiro", "Santos", "Teixeira", "Vasconcelos",
)

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
```

Três detalhes que decidem se o determinismo se sustenta:

**`random.Random(42)`, não `numpy.random`.** O Mersenne Twister da stdlib é
estável entre versões do Python para `random()`, `randint`, `choice` e `sample`.
NumPy já mudou o gerador padrão uma vez; a spec não pede NumPy, e a dependência
extra traria o risco sem trazer nada.

**Ordem de sorteio fixa por linha.** Cada `_make_row` consome os sorteios sempre
na mesma sequência. Inserir um campo novo no meio deslocaria toda a cadeia e
mudaria o hash — é a razão de o teste de hash existir: ele denuncia edições
aparentemente inócuas.

**`line_terminator="\n"` explícito.** No Windows o padrão poderia gravar `\r\n`,
e o mesmo código produziria hashes diferentes localmente e no CI. O teste de
determinismo passaria nos dois lugares e mesmo assim o artefato seria outro.

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/test_generate.py -v`
Expected: todos PASS.

- [ ] **Step 5: Gerar e versionar o dataset sujo**

```bash
uv run python -c "from pathlib import Path; from messy_csv import generate; print(generate.write_dirty_dataset(Path('data/raw/orders_dirty.csv')))"
```

Run: `uv run python -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('data/raw/orders_dirty.csv').read_bytes()).hexdigest())"`
Expected: um hash. Anote-o — ele deve permanecer igual até o fim do projeto.

- [ ] **Step 6: Commit**

```bash
git add src/messy_csv/generate.py tests/test_generate.py data/raw/orders_dirty.csv
git commit -m "feat: gerador deterministico do dataset sujo com seed 42"
```

---

## Task 5: Transformador 1 — whitespace

Primeiro dos seis, e primeiro por necessidade: `" 15/03/2024 "` não casa com
nenhum formato de data, e `" moda "` não casa com nenhuma chave do mapa
canônico. Todo parse posterior assume texto já aparado (§6.1).

**Files:**
- Create: `src/messy_csv/clean/whitespace.py`
- Test: `tests/clean/__init__.py`, `tests/clean/test_whitespace.py`

**Interfaces:**
- Consumes: `contract.RAW_COLUMNS`; frame com as colunas `raw_*`
- Produces:
  - `normalized_text_expr(column: str) -> pl.Expr` — apara, colapsa e converte vazio em nulo
  - `is_clean_text_expr(column: str) -> pl.Expr` — `Boolean`, usada pela métrica de limpeza textual
  - `apply(df: pl.DataFrame) -> pl.DataFrame` — adiciona `t_order_id`, `t_order_date`, `t_customer`, `t_category`, `t_amount`

- [ ] **Step 1: Escrever os testes que falham**

`tests/clean/__init__.py`: arquivo vazio.

`tests/clean/test_whitespace.py`:

```python
from __future__ import annotations

import polars as pl
import pytest

from messy_csv.clean import whitespace


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  Ana Souza  ", "Ana Souza"),
        ("Ana  Souza", "Ana Souza"),
        ("\tAna\nSouza ", "Ana Souza"),
        (" 15/03/2024 ", "15/03/2024"),
        ("Ana Souza", "Ana Souza"),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalizacao_de_texto(entrada: str | None, esperado: str | None) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    resultado = df.select(whitespace.normalized_text_expr("valor"))

    assert resultado.to_series().to_list() == [esperado]


def test_celula_vazia_vira_nulo_e_nao_string_vazia() -> None:
    """O contrato distingue ausente de invalido: vazio precisa ser nulo, nao ''."""
    df = pl.DataFrame({"valor": [""]}, schema={"valor": pl.String()})

    assert df.select(whitespace.normalized_text_expr("valor")).to_series().null_count() == 1


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Ana Souza", True),
        (" Ana Souza", False),
        ("Ana Souza ", False),
        ("Ana  Souza", False),
        (None, None),
    ],
)
def test_deteccao_de_whitespace_anomalo(entrada: str | None, esperado: bool | None) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    assert df.select(whitespace.is_clean_text_expr("valor")).to_series().to_list() == [esperado]


def test_apply_cria_as_cinco_colunas_e_nao_toca_nas_originais() -> None:
    df = pl.DataFrame(
        {
            "raw_order_id": ["  1 "],
            "raw_order_date": [" 15/03/2024"],
            "raw_customer": ["Ana  Souza"],
            "raw_category": [" moda "],
            "raw_amount": ["R$  100,00"],
        }
    )

    resultado = whitespace.apply(df)

    assert resultado["t_order_id"].to_list() == ["1"]
    assert resultado["t_customer"].to_list() == ["Ana Souza"]
    assert resultado["t_amount"].to_list() == ["R$ 100,00"]
    # a coluna original sobrevive intacta: e ela que a quarentena grava
    assert resultado["raw_customer"].to_list() == ["Ana  Souza"]
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/clean/test_whitespace.py -v`
Expected: FAIL com `ImportError: cannot import name 'whitespace'`.

- [ ] **Step 3: Escrever `whitespace.py`**

```python
"""Transformador 1: apara e colapsa espacos. Digitacao manual no painel (spec §5)."""

from __future__ import annotations

import polars as pl

from messy_csv.contract import RAW_COLUMNS


def normalized_text_expr(column: str) -> pl.Expr:
    limpo = pl.col(column).str.replace_all(r"\s+", " ").str.strip_chars()
    return (
        pl.when(limpo.str.len_chars() == 0)
        .then(pl.lit(None, dtype=pl.String))
        .otherwise(limpo)
    )


def is_clean_text_expr(column: str) -> pl.Expr:
    """True quando a celula ja esta normalizada. Nulo para celula nula.

    O nulo propagado e proposital: a metrica de limpeza textual mede so celulas
    preenchidas — ausencia e problema de completude, nao de formatacao.
    """
    valor = pl.col(column)
    return valor == valor.str.replace_all(r"\s+", " ").str.strip_chars()


def apply(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(
        normalized_text_expr(f"raw_{nome}").alias(f"t_{nome}") for nome in RAW_COLUMNS
    )
```

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/clean/test_whitespace.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add src/messy_csv/clean/whitespace.py tests/clean/
git commit -m "feat: transformador de whitespace com vazio virando nulo"
```

---

## Task 6: Transformador 2 — datas

Aqui está o argumento central de D2. `pl.coalesce` de formatos declarados torna
cada formato aceito uma linha de código visível, e a falha vira `null`
auditável — que a métrica de validade temporal lê direto. O `format="mixed"` do
pandas inferiria linha a linha: funciona, mas não deixa rastro do que foi
inferido.

**Files:**
- Create: `src/messy_csv/clean/dates.py`
- Test: `tests/clean/test_dates.py`

**Interfaces:**
- Consumes: coluna `t_order_date` (`String`)
- Produces:
  - `DATE_FORMATS: tuple[str, ...]`, `DATETIME_FORMATS: tuple[str, ...]`
  - `parse_date_expr(column: str) -> pl.Expr` → `Date`
  - `is_in_range_expr(column: str, today: dt.date) -> pl.Expr` → `Boolean`
  - `apply(df: pl.DataFrame) -> pl.DataFrame` — adiciona `order_date` (`Date`)

- [ ] **Step 1: Escrever os testes que falham**

`tests/clean/test_dates.py`:

```python
from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from messy_csv.clean import dates

TODAY = dt.date(2025, 6, 30)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("2024-03-15", dt.date(2024, 3, 15)),
        ("15/03/2024", dt.date(2024, 3, 15)),
        ("Mar 16 2024", dt.date(2024, 3, 16)),
        ("2024-03-15 10:30:00", dt.date(2024, 3, 15)),
        (" 15/03/2024 ", dt.date(2024, 3, 15)),
        ("2024-13-02", None),
        ("ontem", None),
        (None, None),
    ],
)
def test_parse_dos_formatos_declarados(entrada: str | None, esperado: dt.date | None) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    resultado = df.select(dates.parse_date_expr("valor"))

    assert resultado.to_series().to_list() == [esperado]
    assert resultado.dtypes == [pl.Date]


def test_hora_e_truncada_e_nao_arredondada() -> None:
    """Spec §12.3: timezone ignorado, hora truncada para data."""
    df = pl.DataFrame({"valor": ["2024-03-15 23:59:59"]}, schema={"valor": pl.String()})

    assert df.select(dates.parse_date_expr("valor")).to_series().to_list() == [
        dt.date(2024, 3, 15)
    ]


def test_formatos_aceitos_sao_exatamente_os_da_spec() -> None:
    """A lista de formatos e contrato publico: mudar exige mudar a spec."""
    assert dates.DATE_FORMATS == ("%Y-%m-%d", "%d/%m/%Y", "%b %d %Y")
    assert dates.DATETIME_FORMATS == ("%Y-%m-%d %H:%M:%S",)


@pytest.mark.parametrize(
    ("data", "esperado"),
    [
        (dt.date(2022, 12, 31), False),
        (dt.date(2023, 1, 1), True),
        (dt.date(2024, 6, 1), True),
        (TODAY, True),
        (dt.date(2025, 7, 1), False),
        (None, None),
    ],
)
def test_intervalo_valido(data: dt.date | None, esperado: bool | None) -> None:
    df = pl.DataFrame({"d": [data]}, schema={"d": pl.Date()})

    assert df.select(dates.is_in_range_expr("d", TODAY)).to_series().to_list() == [esperado]


def test_apply_adiciona_order_date_sem_remover_o_texto() -> None:
    df = pl.DataFrame({"t_order_date": ["15/03/2024", "2024-13-02"]})

    resultado = dates.apply(df)

    assert resultado["order_date"].to_list() == [dt.date(2024, 3, 15), None]
    assert resultado["t_order_date"].to_list() == ["15/03/2024", "2024-13-02"]
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/clean/test_dates.py -v`
Expected: FAIL com `ImportError: cannot import name 'dates'`.

- [ ] **Step 3: Escrever `dates.py`**

```python
"""Transformador 2: datas de tres sistemas integrados, em quatro formatos (spec §5.1)."""

from __future__ import annotations

import datetime as dt

import polars as pl

from messy_csv.contract import MIN_DATE

DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%d/%m/%Y", "%b %d %Y")
DATETIME_FORMATS: tuple[str, ...] = ("%Y-%m-%d %H:%M:%S",)


def parse_date_expr(column: str) -> pl.Expr:
    """Tenta cada formato declarado, na ordem; o que nao casa vira nulo auditavel."""
    texto = pl.col(column).str.strip_chars()
    candidatos = [
        texto.str.strptime(pl.Date, formato, strict=False) for formato in DATE_FORMATS
    ]
    candidatos += [
        # Data com hora: parse como Datetime e trunca. Spec §12.3.
        texto.str.strptime(pl.Datetime, formato, strict=False).dt.date()
        for formato in DATETIME_FORMATS
    ]
    return pl.coalesce(candidatos)


def is_in_range_expr(column: str, today: dt.date) -> pl.Expr:
    data = pl.col(column)
    return (data >= MIN_DATE) & (data <= today)


def apply(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(parse_date_expr("t_order_date").alias("order_date"))
```

Dois pontos que passariam despercebidos:

**`strict=False` é o que torna o `coalesce` possível.** Com `strict=True` o
primeiro formato que não casasse levantaria exceção e o segundo nunca seria
tentado. É `strict=False` que transforma "não casou" em `null`, e é o `null` que
permite ao próximo candidato assumir.

**O formato com hora é parseado como `Datetime` e truncado.** `strptime` para
`pl.Date` com um formato que contém `%H:%M:%S` não é confiável entre versões, e
`pl.coalesce` exige que todos os candidatos tenham o mesmo dtype — misturar
`Date` e `Datetime` falharia no schema.

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/clean/test_dates.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add src/messy_csv/clean/dates.py tests/clean/test_dates.py
git commit -m "feat: parse de datas por coalesce de formatos declarados"
```

---

## Task 7: Tabela de câmbio e transformador 3 — moeda

D4: a conversão faz join pela competência mensal do pedido, não por uma taxa
única. Uma taxa única converteria um pedido de janeiro de 2023 com a cotação de
dezembro de 2024 — erro conceitual que ninguém nota olhando o CSV final.

Roda **depois** de `dates` porque a competência sai de `order_date` (§6.1).

**Files:**
- Create: `data/fx_rates.csv`, `src/messy_csv/clean/currency.py`
- Test: `tests/clean/test_currency.py`

**Interfaces:**
- Consumes: coluna `t_amount` (`String`), coluna `order_date` (`Date`)
- Produces:
  - `FX_PATH: Path`, `load_fx_rates(path: Path) -> pl.DataFrame`
  - `currency_expr(column: str) -> pl.Expr` → `String`
  - `amount_expr(column: str) -> pl.Expr` → `Float64`
  - `apply(df: pl.DataFrame, fx: pl.DataFrame) -> pl.DataFrame` — adiciona `amount_original`, `currency_original`, `amount_brl`

- [ ] **Step 1: Escrever `data/fx_rates.csv`**

Taxas fictícias porém plausíveis (§12.1). As linhas `BRL` com taxa `1.000000`
existem para que o join seja total: sem elas, `BRL` precisaria de um `when/then`
especial no código, e um mês de `USD` faltando ficaria indistinguível do caso
normal.

```csv
month,currency,rate_to_brl
2023-01,BRL,1.000000
2023-02,BRL,1.000000
2023-03,BRL,1.000000
2023-04,BRL,1.000000
2023-05,BRL,1.000000
2023-06,BRL,1.000000
2023-07,BRL,1.000000
2023-08,BRL,1.000000
2023-09,BRL,1.000000
2023-10,BRL,1.000000
2023-11,BRL,1.000000
2023-12,BRL,1.000000
2024-01,BRL,1.000000
2024-02,BRL,1.000000
2024-03,BRL,1.000000
2024-04,BRL,1.000000
2024-05,BRL,1.000000
2024-06,BRL,1.000000
2024-07,BRL,1.000000
2024-08,BRL,1.000000
2024-09,BRL,1.000000
2024-10,BRL,1.000000
2024-11,BRL,1.000000
2024-12,BRL,1.000000
2023-01,USD,5.201400
2023-02,USD,5.183000
2023-03,USD,5.224600
2023-04,USD,5.017900
2023-05,USD,4.968300
2023-06,USD,4.841700
2023-07,USD,4.812500
2023-08,USD,4.903800
2023-09,USD,4.947200
2023-10,USD,5.083600
2023-11,USD,4.923500
2023-12,USD,4.901100
2024-01,USD,4.918700
2024-02,USD,4.962400
2024-03,USD,4.991300
2024-04,USD,5.138900
2024-05,USD,5.152600
2024-06,USD,5.364700
2024-07,USD,5.531200
2024-08,USD,5.548800
2024-09,USD,5.478400
2024-10,USD,5.601500
2024-11,USD,5.792300
2024-12,USD,6.048900
```

- [ ] **Step 2: Escrever os testes que falham**

`tests/clean/test_currency.py`:

```python
from __future__ import annotations

import datetime as dt

import polars as pl
import pytest

from messy_csv.clean import currency

FX = pl.DataFrame(
    {
        "month": ["2024-03", "2024-03", "2024-04", "2024-04"],
        "currency": ["BRL", "USD", "BRL", "USD"],
        "rate_to_brl": [1.0, 5.0, 1.0, 5.5],
    }
)


@pytest.mark.parametrize(
    ("entrada", "moeda", "valor"),
    [
        ("R$ 1.299,90", "BRL", 1299.90),
        ("1.299,90", "BRL", 1299.90),
        ("R$ 99,00", "BRL", 99.00),
        ("$ 249.00", "USD", 249.00),
        ("USD 249.00", "USD", 249.00),
        ("US$ 249.00", "USD", 249.00),
        ("-50,00", "BRL", -50.00),
        ("0,00", "BRL", 0.00),
        ("n/a", None, None),
        ("-", None, None),
        (None, None, None),
    ],
)
def test_parse_dos_formatos_monetarios(
    entrada: str | None, moeda: str | None, valor: float | None
) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    resultado = df.select(
        currency.amount_expr("valor").alias("amount"),
        currency.currency_expr("valor").alias("currency"),
    )

    assert resultado["amount"].to_list() == pytest.approx([valor])
    assert resultado["currency"].to_list() == [moeda]


def test_ausencia_de_simbolo_assume_real() -> None:
    """Spec §12.4: suposicao declarada, coerente com uma loja brasileira."""
    df = pl.DataFrame({"valor": ["1.299,90"]}, schema={"valor": pl.String()})

    assert df.select(currency.currency_expr("valor")).to_series().to_list() == ["BRL"]


def _frame(amount: str | None, data: dt.date | None) -> pl.DataFrame:
    return pl.DataFrame(
        {"source_index": [0], "t_amount": [amount], "order_date": [data]},
        schema={"source_index": pl.UInt32(), "t_amount": pl.String(), "order_date": pl.Date()},
    )


def test_conversao_usa_a_competencia_do_pedido() -> None:
    marco = currency.apply(_frame("$ 100.00", dt.date(2024, 3, 10)), FX)
    abril = currency.apply(_frame("$ 100.00", dt.date(2024, 4, 10)), FX)

    assert marco["amount_brl"].to_list() == [500.00]
    assert abril["amount_brl"].to_list() == [550.00]


def test_real_nao_e_convertido() -> None:
    resultado = currency.apply(_frame("R$ 100,00", dt.date(2024, 3, 10)), FX)

    assert resultado["amount_brl"].to_list() == [100.00]
    assert resultado["amount_original"].to_list() == [100.00]


def test_amount_brl_tem_duas_casas_decimais() -> None:
    resultado = currency.apply(_frame("$ 33.33", dt.date(2024, 4, 10)), FX)

    assert resultado["amount_brl"].to_list() == [183.32]  # 33.33 * 5.5 = 183.315


def test_procedencia_e_preservada() -> None:
    """D8: sem o original nao ha como auditar nem recalcular a conversao."""
    resultado = currency.apply(_frame("$ 100.00", dt.date(2024, 3, 10)), FX)

    assert set(resultado.columns) >= {"amount_original", "currency_original", "amount_brl"}
    assert resultado["currency_original"].to_list() == ["USD"]


def test_valor_ilegivel_propaga_nulo_sem_quebrar() -> None:
    resultado = currency.apply(_frame("n/a", dt.date(2024, 3, 10)), FX)

    assert resultado["amount_original"].to_list() == [None]
    assert resultado["amount_brl"].to_list() == [None]
    assert resultado.height == 1  # transformador nao rejeita linha (D5)


def test_data_invalida_nao_derruba_a_conversao() -> None:
    resultado = currency.apply(_frame("$ 100.00", None), FX)

    assert resultado["amount_brl"].to_list() == [None]
    assert resultado.height == 1


def test_tabela_versionada_cobre_todo_o_intervalo_do_gerador() -> None:
    """Um mes faltando produziria amount_brl nulo — dado errado em silencio."""
    fx = currency.load_fx_rates(currency.FX_PATH)
    esperados = {
        (f"{ano}-{mes:02d}", moeda)
        for ano in (2023, 2024)
        for mes in range(1, 13)
        for moeda in ("BRL", "USD")
    }

    presentes = set(zip(fx["month"].to_list(), fx["currency"].to_list(), strict=True))
    assert esperados <= presentes


def test_taxa_do_real_e_sempre_um() -> None:
    fx = currency.load_fx_rates(currency.FX_PATH)

    taxas = fx.filter(pl.col("currency") == "BRL")["rate_to_brl"].unique().to_list()
    assert taxas == [1.0]
```

- [ ] **Step 3: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/clean/test_currency.py -v`
Expected: FAIL com `ImportError: cannot import name 'currency'`.

- [ ] **Step 4: Escrever `currency.py`**

```python
"""Transformador 3: parse do simbolo monetario e conversao por competencia (D4).

Roda depois de `dates` porque o join de cambio usa o mes de order_date (§6.1).
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

FX_PATH = Path("data/fx_rates.csv")

_USD_PREFIX = r"(?i)^(us\$|usd|\$)"
_ANY_SYMBOL = r"(?i)^(r\$|us\$|usd|brl|\$)\s*"


def load_fx_rates(path: Path = FX_PATH) -> pl.DataFrame:
    return pl.read_csv(
        path,
        schema={"month": pl.String(), "currency": pl.String(), "rate_to_brl": pl.Float64()},
    )


def currency_expr(column: str) -> pl.Expr:
    """USD quando ha simbolo americano; BRL por padrao (spec §12.4).

    Nulo quando o valor nao e parseavel: sem valor nao ha moeda a declarar, e
    deixar "BRL" numa linha sem valor poluiria a quarentena com dado inventado.
    """
    texto = pl.col(column).str.strip_chars()
    return (
        pl.when(amount_expr(column).is_null())
        .then(pl.lit(None, dtype=pl.String))
        .when(texto.str.contains(_USD_PREFIX))
        .then(pl.lit("USD"))
        .otherwise(pl.lit("BRL"))
    )


def amount_expr(column: str) -> pl.Expr:
    """BRL usa ponto de milhar e virgula decimal; USD usa o inverso."""
    texto = pl.col(column).str.strip_chars()
    sem_simbolo = texto.str.replace(_ANY_SYMBOL, "").str.strip_chars()
    numero = (
        pl.when(texto.str.contains(_USD_PREFIX))
        .then(sem_simbolo.str.replace_all(",", ""))
        .otherwise(sem_simbolo.str.replace_all(r"\.", "").str.replace_all(",", "."))
    )
    return (
        pl.when(numero.str.contains(r"^-?\d+(\.\d+)?$"))
        .then(numero.cast(pl.Float64, strict=False))
        .otherwise(pl.lit(None, dtype=pl.Float64))
    )


def apply(df: pl.DataFrame, fx: pl.DataFrame) -> pl.DataFrame:
    com_valores = df.with_columns(
        amount_expr("t_amount").alias("amount_original"),
        currency_expr("t_amount").alias("currency_original"),
        pl.col("order_date").dt.strftime("%Y-%m").alias("_month"),
    )

    tabela = fx.rename(
        {"month": "_month", "currency": "currency_original", "rate_to_brl": "_rate"}
    )
    convertido = com_valores.join(tabela, on=["_month", "currency_original"], how="left")

    return (
        convertido.with_columns(
            (pl.col("amount_original") * pl.col("_rate")).round(2).alias("amount_brl")
        )
        # o join nao promete preservar a ordem; source_index promete
        .sort("source_index")
        .drop("_month", "_rate")
    )
```

Três decisões que valem explicar:

**A tabela é renomeada antes do join, em vez de usar `left_on`/`right_on`.** Com
chaves de nomes diferentes, versões de Polars divergem sobre manter ou não as
colunas do lado direito (`month_right`, `currency_right`). Renomear torna as
chaves idênticas e o resultado não depende dessa política.

**`.sort("source_index")` depois do join.** Um join não promete preservar a
ordem do lado esquerdo. Sem esse `sort`, a ordem das linhas — e portanto o
desempate por índice de origem em `duplicates` — dependeria do plano de execução
do Polars. Determinismo não pode depender de detalhe de implementação.

**`_rate` é descartado, `amount_original` e `currency_original` ficam (D8).**
Guardar a taxa em cada linha seria denormalizar a tabela versionada dentro do
dataset; guardar o valor e a moeda originais é o que permite recalcular a
conversão sem reprocessar tudo.

- [ ] **Step 5: Rodar os testes até passarem**

Run: `uv run pytest tests/clean/test_currency.py -v`
Expected: todos PASS.

- [ ] **Step 6: Commit**

```bash
git add data/fx_rates.csv src/messy_csv/clean/currency.py tests/clean/test_currency.py
git commit -m "feat: conversao monetaria por tabela de cambio mensal versionada"
```

---

## Task 8: Transformador 4 — categorias

Normalização (minúsculas, sem acento, sem espaço extra) seguida de lookup em
dicionário **explícito** (§5.2). O lookup não é fuzzy de propósito: um match
aproximado que acerta 95% das vezes erra 5% em silêncio, e não há como saber
quais.

**Files:**
- Create: `src/messy_csv/clean/categories.py`
- Test: `tests/clean/test_categories.py`

**Interfaces:**
- Consumes: coluna `t_category` (`String`)
- Produces:
  - `CANONICAL_MAP: dict[str, str]`
  - `normalize_expr(column: str) -> pl.Expr` → `String`
  - `canonical_expr(column: str) -> pl.Expr` → `String` (nulo quando irrecuperável)
  - `apply(df: pl.DataFrame) -> pl.DataFrame` — adiciona `category` (`String`)

- [ ] **Step 1: Escrever os testes que falham**

`tests/clean/test_categories.py`:

```python
from __future__ import annotations

import polars as pl
import pytest

from messy_csv import contract
from messy_csv.clean import categories


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Eletrônicos", "Eletrônicos"),
        ("eletronicos", "Eletrônicos"),
        ("ELETRONICOS", "Eletrônicos"),
        ("Eletrônico", "Eletrônicos"),
        ("eletro", "Eletrônicos"),
        ("Moda", "Moda"),
        ("MODA", "Moda"),
        ("Modas", "Moda"),
        ("vestuario", "Moda"),
        ("Casa", "Casa"),
        ("Casa e Decoração", "Casa"),
        ("casa_decoracao", "Casa"),
        ("Livros", "Livros"),
        ("LIVRO", "Livros"),
        ("livraria", "Livros"),
        ("Esporte", "Esporte"),
        ("Esportes", "Esporte"),
        ("ESPORTE", "Esporte"),
        ("diversos", None),
        ("outros", None),
        ("misc", None),
        (None, None),
    ],
)
def test_mapa_canonico(entrada: str | None, esperado: str | None) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    assert df.select(categories.canonical_expr("valor")).to_series().to_list() == [esperado]


def test_diversos_e_irrecuperavel_de_proposito() -> None:
    """Spec §5.2: sem uma categoria irrecuperavel a quarentena nunca seria exercitada."""
    df = pl.DataFrame({"valor": ["diversos"]}, schema={"valor": pl.String()})

    assert df.select(categories.canonical_expr("valor")).to_series().null_count() == 1


def test_todo_valor_canonico_pertence_ao_contrato() -> None:
    assert set(categories.CANONICAL_MAP.values()) <= set(contract.CATEGORIES)


def test_nao_informado_nao_e_produzido_aqui() -> None:
    """Imputacao e responsabilidade de missing.py, e roda depois (§6.1)."""
    assert "Não informado" not in categories.CANONICAL_MAP.values()


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Casa e Decoração", "casa e decoracao"),
        ("casa_decoracao", "casa decoracao"),
        ("  ELETRÔNICOS  ", "eletronicos"),
        ("Esportes", "esportes"),
    ],
)
def test_normalizacao_remove_acento_caixa_e_separador(entrada: str, esperado: str) -> None:
    df = pl.DataFrame({"valor": [entrada]}, schema={"valor": pl.String()})

    assert df.select(categories.normalize_expr("valor")).to_series().to_list() == [esperado]


def test_apply_adiciona_category_sem_remover_o_texto() -> None:
    df = pl.DataFrame({"t_category": ["ELETRONICOS", "misc"]})

    resultado = categories.apply(df)

    assert resultado["category"].to_list() == ["Eletrônicos", None]
    assert resultado["t_category"].to_list() == ["ELETRONICOS", "misc"]
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/clean/test_categories.py -v`
Expected: FAIL com `ImportError: cannot import name 'categories'`.

- [ ] **Step 3: Escrever `categories.py`**

```python
"""Transformador 4: cadastro livre virou variante; o mapa canonico e explicito (§5.2)."""

from __future__ import annotations

import polars as pl

# Chaves ja normalizadas: minusculas, sem acento, separadores virados espaco.
CANONICAL_MAP: dict[str, str] = {
    "eletronicos": "Eletrônicos",
    "eletronico": "Eletrônicos",
    "eletro": "Eletrônicos",
    "moda": "Moda",
    "modas": "Moda",
    "vestuario": "Moda",
    "casa": "Casa",
    "casa e decoracao": "Casa",
    "casa decoracao": "Casa",
    "livros": "Livros",
    "livro": "Livros",
    "livraria": "Livros",
    "esporte": "Esporte",
    "esportes": "Esporte",
}

_ACCENTED = "áàâãäéèêëíìîïóòôõöúùûüçñ"
_PLAIN = "aaaaaeeeeiiiiooooouuuucn"


def normalize_expr(column: str) -> pl.Expr:
    return (
        pl.col(column)
        .str.to_lowercase()
        .str.replace_many(list(_ACCENTED), list(_PLAIN))
        .str.replace_all(r"[_\-]+", " ")
        .str.replace_all(r"\s+", " ")
        .str.strip_chars()
    )


def canonical_expr(column: str) -> pl.Expr:
    """Nulo quando o rotulo e irrecuperavel: a decisao de rejeitar e do contrato."""
    return normalize_expr(column).replace_strict(
        CANONICAL_MAP, default=None, return_dtype=pl.String
    )


def apply(df: pl.DataFrame) -> pl.DataFrame:
    return df.with_columns(canonical_expr("t_category").alias("category"))
```

**Por que `to_lowercase()` vem antes de `replace_many`.** Só as vogais acentuadas
minúsculas estão na tabela. Baixar a caixa primeiro reduz 48 substituições a 24
e elimina a chance de esquecer um `Ô`. Fazer o inverso exigiria manter as duas
metades em sincronia para sempre.

**`replace_strict` com `default=None`, não `replace`.** `replace` deixaria passar
intacto o valor não mapeado, e `"diversos"` chegaria ao contrato como se fosse
uma categoria. `replace_strict` obriga a decidir o que fazer com o desconhecido —
e a decisão aqui é `null`, que o contrato traduz em `categoria desconhecida`.

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/clean/test_categories.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add src/messy_csv/clean/categories.py tests/clean/test_categories.py
git commit -m "feat: normalizacao de categorias com mapa canonico explicito"
```

---

## Task 9: Transformador 5 — deduplicação

Roda em quinto porque precisa dos nulos **reais** para escolher a linha mais
completa (§6.1). Também é aqui que `order_id` vira `Int64` (L5).

Conforme L3, a linha perdedora não é destruída: recebe a marca
`is_duplicate_loser`, e o contrato a manda para a quarentena com motivo próprio.

**Files:**
- Create: `src/messy_csv/clean/duplicates.py`
- Test: `tests/clean/test_duplicates.py`

**Interfaces:**
- Consumes: `source_index`, `t_order_id`, e as colunas materializadas pelos transformadores 2 a 4
- Produces:
  - `COMPLETENESS_COLUMNS: tuple[str, ...]`
  - `null_count_expr() -> pl.Expr` → `Int32`
  - `apply(df: pl.DataFrame) -> pl.DataFrame` — adiciona `order_id` (`Int64`) e `is_duplicate_loser` (`Boolean`), preservando a ordem por `source_index`

- [ ] **Step 1: Escrever os testes que falham**

`tests/clean/test_duplicates.py`:

```python
from __future__ import annotations

import datetime as dt

import polars as pl

from messy_csv.clean import duplicates

_SCHEMA: dict[str, pl.DataType] = {
    "source_index": pl.UInt32(),
    "t_order_id": pl.String(),
    "order_date": pl.Date(),
    "t_customer": pl.String(),
    "category": pl.String(),
    "amount_original": pl.Float64(),
    "currency_original": pl.String(),
    "amount_brl": pl.Float64(),
}

_COMPLETA: dict[str, object] = {
    "t_order_id": "7",
    "order_date": dt.date(2024, 3, 10),
    "t_customer": "Ana Souza",
    "category": "Moda",
    "amount_original": 100.0,
    "currency_original": "BRL",
    "amount_brl": 100.0,
}


def _frame(*linhas: dict[str, object]) -> pl.DataFrame:
    registros = [{"source_index": indice, **_COMPLETA, **linha} for indice, linha in enumerate(linhas)]
    return pl.DataFrame(registros, schema=_SCHEMA)


def test_vence_a_linha_com_menos_nulos() -> None:
    df = _frame({"category": None}, {})  # indice 0 tem um nulo, indice 1 nenhum

    resultado = duplicates.apply(df)

    assert resultado["is_duplicate_loser"].to_list() == [True, False]


def test_empate_e_resolvido_pelo_menor_indice_de_origem() -> None:
    df = _frame({"category": None}, {"t_customer": None})  # um nulo cada

    resultado = duplicates.apply(df)

    assert resultado["is_duplicate_loser"].to_list() == [False, True]


def test_linha_sem_duplicata_nunca_e_marcada() -> None:
    df = _frame({"t_order_id": "7"}, {"t_order_id": "8"})

    assert duplicates.apply(df)["is_duplicate_loser"].to_list() == [False, False]


def test_ids_ilegiveis_nao_sao_tratados_como_duplicatas_entre_si() -> None:
    """Sem esta guarda, todo id invalido cairia no mesmo grupo nulo e viraria duplicata."""
    df = _frame({"t_order_id": "ORD-1023"}, {"t_order_id": ""}, {"t_order_id": None})

    resultado = duplicates.apply(df)

    assert resultado["order_id"].to_list() == [None, None, None]
    assert resultado["is_duplicate_loser"].to_list() == [False, False, False]


def test_order_id_vira_inteiro() -> None:
    df = _frame({"t_order_id": "7"}, {"t_order_id": "0"})

    resultado = duplicates.apply(df)

    assert resultado["order_id"].to_list() == [7, 0]
    assert resultado.schema["order_id"] == pl.Int64


def test_ordem_original_e_restaurada() -> None:
    """A ordenacao por nulos e interna; quem sai daqui sai na ordem do arquivo."""
    df = _frame({"category": None}, {}, {"t_order_id": "9"})

    resultado = duplicates.apply(df)

    assert resultado["source_index"].to_list() == [0, 1, 2]


def test_tres_copias_deixam_apenas_uma_vencedora() -> None:
    df = _frame({"category": None}, {"t_customer": None}, {})

    assert duplicates.apply(df)["is_duplicate_loser"].to_list() == [True, True, False]


def test_nenhuma_linha_e_removida() -> None:
    """D6: o transformador marca, nunca descarta."""
    df = _frame({"category": None}, {}, {})

    assert duplicates.apply(df).height == 3
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/clean/test_duplicates.py -v`
Expected: FAIL com `ImportError: cannot import name 'duplicates'`.

- [ ] **Step 3: Escrever `duplicates.py`**

```python
"""Transformador 5: retry de integracao com o marketplace (spec §5.4).

Marca a copia perdedora em vez de descarta-la: nenhum dado e destruido (D6), e
o contrato transforma a marca no motivo `order_id duplicado irreconciliavel`.
"""

from __future__ import annotations

import polars as pl

# So faz sentido contar nulos depois que dates, currency e categories rodaram:
# antes disso nada foi parseado e todas as linhas pareceriam igualmente completas.
COMPLETENESS_COLUMNS: tuple[str, ...] = (
    "order_date",
    "t_customer",
    "category",
    "amount_original",
    "currency_original",
    "amount_brl",
)


def null_count_expr() -> pl.Expr:
    return pl.sum_horizontal(
        pl.col(nome).is_null().cast(pl.Int32) for nome in COMPLETENESS_COLUMNS
    )


def apply(df: pl.DataFrame) -> pl.DataFrame:
    com_id = df.with_columns(
        pl.col("t_order_id").cast(pl.Int64, strict=False).alias("order_id"),
        null_count_expr().alias("_nulls"),
    )

    # Menos nulos primeiro; empate pelo menor indice de origem (spec §5.4).
    ordenado = com_id.sort("_nulls", "source_index")

    marcado = ordenado.with_columns(
        pl.when(pl.col("order_id").is_null())
        .then(pl.lit(False))
        .otherwise(pl.col("source_index").cum_count().over("order_id") > 1)
        .alias("is_duplicate_loser")
    )
    return marcado.sort("source_index").drop("_nulls")
```

**A guarda do `order_id` nulo não é detalhe.** Sem ela, `.over("order_id")`
agruparia todos os ids ilegíveis num único grupo nulo, e a partir do segundo
todos virariam "duplicatas irreconciliáveis" — um motivo de rejeição errado
substituindo o motivo certo (`order_id inválido`) em dezenas de linhas.

**`sort` interno, `sort("source_index")` no fim.** A ordenação por nulos existe
só para que `cum_count` encontre a vencedora na primeira posição do grupo. Deixar
o frame nessa ordem propagaria uma reordenação arbitrária para o CSV final.

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/clean/test_duplicates.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add src/messy_csv/clean/duplicates.py tests/clean/test_duplicates.py
git commit -m "feat: deduplicacao que marca a perdedora em vez de descartar"
```

---

## Task 10: Transformador 6 — ausências

O menor dos seis, e é isso que D7 quer dizer. Imputar só é aceitável quando o
rótulo substituto declara a própria ignorância: `Não informado` faz isso; um
valor monetário ou um nome inventado, não — eles se passam por dado real.

**Files:**
- Create: `src/messy_csv/clean/missing.py`
- Test: `tests/clean/test_missing.py`

**Interfaces:**
- Consumes: colunas `category` e `t_category`
- Produces:
  - `UNKNOWN_CATEGORY: str`
  - `apply(df: pl.DataFrame) -> pl.DataFrame` — reescreve `category`

- [ ] **Step 1: Escrever os testes que falham**

`tests/clean/test_missing.py`:

```python
from __future__ import annotations

import polars as pl

from messy_csv.clean import missing

_SCHEMA: dict[str, pl.DataType] = {
    "t_category": pl.String(),
    "category": pl.String(),
    "t_customer": pl.String(),
    "amount_original": pl.Float64(),
}


def _frame(t_category: str | None, category: str | None) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "t_category": [t_category],
            "category": [category],
            "t_customer": [None],
            "amount_original": [None],
        },
        schema=_SCHEMA,
    )


def test_categoria_ausente_vira_nao_informado() -> None:
    resultado = missing.apply(_frame(None, None))

    assert resultado["category"].to_list() == ["Não informado"]


def test_categoria_desconhecida_continua_nula() -> None:
    """"misc" nao e ausencia, e rotulo irrecuperavel: quem decide e o contrato."""
    resultado = missing.apply(_frame("misc", None))

    assert resultado["category"].to_list() == [None]


def test_categoria_valida_nao_e_tocada() -> None:
    resultado = missing.apply(_frame("moda", "Moda"))

    assert resultado["category"].to_list() == ["Moda"]


def test_dinheiro_nunca_e_imputado() -> None:
    """D7: valor monetario inventado corrompe analise financeira."""
    resultado = missing.apply(_frame(None, None))

    assert resultado["amount_original"].to_list() == [None]


def test_cliente_nunca_e_imputado() -> None:
    """D7: sem identificacao nao ha pedido rastreavel."""
    resultado = missing.apply(_frame(None, None))

    assert resultado["t_customer"].to_list() == [None]


def test_nao_ha_coluna_de_flag_de_imputacao() -> None:
    """D7: com uma unica imputacao no projeto, a flag poluiria o contrato."""
    resultado = missing.apply(_frame(None, None))

    assert resultado.columns == ["t_category", "category", "t_customer", "amount_original"]
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/clean/test_missing.py -v`
Expected: FAIL com `ImportError: cannot import name 'missing'`.

- [ ] **Step 3: Escrever `missing.py`**

```python
"""Transformador 6: a unica imputacao do projeto (D7).

Roda por ultimo, depois que a disputa de duplicatas ja foi decidida (§6.1).
"""

from __future__ import annotations

import polars as pl

UNKNOWN_CATEGORY = "Não informado"


def apply(df: pl.DataFrame) -> pl.DataFrame:
    # Celula vazia vira rotulo honesto; rotulo irrecuperavel continua nulo para
    # que o contrato o rejeite como `categoria desconhecida`.
    return df.with_columns(
        pl.when(pl.col("category").is_null() & pl.col("t_category").is_null())
        .then(pl.lit(UNKNOWN_CATEGORY))
        .otherwise(pl.col("category"))
        .alias("category")
    )
```

A condição dupla (`category` nulo **e** `t_category` nulo) é o que separa os dois
casos que chegam aqui com `category` nulo: a célula que veio vazia e o rótulo
`"misc"` que o mapa canônico recusou. Sem a segunda metade da condição,
`"misc"` viraria `Não informado` e a quarentena por categoria ficaria sempre
vazia — o caminho que a spec fez questão de exercitar (§5.2).

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/clean/test_missing.py -v`
Expected: todos PASS.

- [ ] **Step 5: Commit**

```bash
git add src/messy_csv/clean/missing.py tests/clean/test_missing.py
git commit -m "feat: imputacao apenas de categoria, com rotulo que declara ignorancia"
```

---

## Task 11: Pipeline — carga, orquestração e artefatos

Fecha a Etapa 7. Aqui a ordem dos seis vira código, e o teste mais importante do
projeto entra: o que prova que trocar dois passos muda o resultado.

**Files:**
- Create: `src/messy_csv/pipeline.py`
- Test: `tests/test_pipeline.py`
- Generated: `data/clean/orders.csv`, `data/rejects/rejects.csv`

**Interfaces:**
- Consumes: `contract.validate`, os seis módulos de `clean/`, `currency.load_fx_rates`
- Produces:
  - `RAW_PATH`, `CLEAN_PATH`, `REJECTS_PATH: Path`
  - `load_raw(path: Path) -> pl.DataFrame`
  - `transform(df: pl.DataFrame, fx: pl.DataFrame) -> pl.DataFrame` — os seis na ordem fixa, sem validar
  - `clean_frame(df: pl.DataFrame, fx: pl.DataFrame, today: dt.date) -> tuple[pl.DataFrame, pl.DataFrame]`
  - `write_outputs(accepted: pl.DataFrame, rejected: pl.DataFrame, clean_path: Path, rejects_path: Path) -> None`
  - `run(today: dt.date, ...) -> tuple[pl.DataFrame, pl.DataFrame]`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_pipeline.py`:

```python
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
        {},                     # indice 1: completa
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
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: FAIL com `ImportError: cannot import name 'pipeline'`.

- [ ] **Step 3: Escrever `pipeline.py`**

```python
"""Carga do CSV sujo, orquestracao dos seis transformadores e escrita dos artefatos."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl

from messy_csv import contract
from messy_csv.clean import categories, currency, dates, duplicates, missing, whitespace

RAW_PATH = Path("data/raw/orders_dirty.csv")
CLEAN_PATH = Path("data/clean/orders.csv")
REJECTS_PATH = Path("data/rejects/rejects.csv")


def load_raw(path: Path = RAW_PATH) -> pl.DataFrame:
    """Le tudo como texto (§4.1) e ancora a ordem de origem em source_index."""
    bruto = pl.read_csv(path, infer_schema=False)
    renomeado = bruto.rename({nome: f"raw_{nome}" for nome in contract.RAW_COLUMNS})
    return renomeado.with_row_index("source_index")


def transform(df: pl.DataFrame, fx: pl.DataFrame) -> pl.DataFrame:
    """A ordem e fixa e significativa (§6.1): trocar dois passos muda o resultado.

    Devolve o frame largo — raw_*, t_* e as colunas tipadas lado a lado — porque
    o relatorio precisa do antes e do depois na mesma linha (Task 13).
    """
    frame = whitespace.apply(df)
    frame = dates.apply(frame)
    frame = currency.apply(frame, fx)
    frame = categories.apply(frame)
    frame = duplicates.apply(frame)
    frame = missing.apply(frame)
    return frame


def clean_frame(
    df: pl.DataFrame, fx: pl.DataFrame, today: dt.date
) -> tuple[pl.DataFrame, pl.DataFrame]:
    return contract.validate(transform(df, fx), today)


def write_outputs(
    accepted: pl.DataFrame,
    rejected: pl.DataFrame,
    clean_path: Path = CLEAN_PATH,
    rejects_path: Path = REJECTS_PATH,
) -> None:
    for caminho, frame in ((clean_path, accepted), (rejects_path, rejected)):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        frame.write_csv(caminho, line_terminator="\n")


def run(
    today: dt.date,
    raw_path: Path = RAW_PATH,
    fx_path: Path = currency.FX_PATH,
    clean_path: Path = CLEAN_PATH,
    rejects_path: Path = REJECTS_PATH,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    accepted, rejected = clean_frame(
        load_raw(raw_path), currency.load_fx_rates(fx_path), today
    )
    write_outputs(accepted, rejected, clean_path, rejects_path)
    return accepted, rejected
```

A função se chama `clean_frame`, não `clean`, porque `clean` já é o nome do
pacote dos transformadores. Um módulo que importa de `messy_csv.clean` e também
define `clean` é uma fonte de confusão silenciosa — o tipo de coisa que só morde
seis meses depois.

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: todos PASS. Se `test_todos_os_motivos_aparecem_no_dataset_real` falhar,
o motivo faltante indica uma taxa de geração de L2 pequena demais — ajuste a taxa
em `generate.py`, não a lista de motivos.

- [ ] **Step 5: Rodar a suíte inteira e a cobertura dos caminhos exigidos**

Run: `uv run pytest --cov=messy_csv --cov-report=term-missing`
Then: `uv run coverage report --include="*/messy_csv/contract.py,*/messy_csv/clean/*" --fail-under=90`
Expected: ambos passam.

- [ ] **Step 6: Gerar e versionar os artefatos limpos**

```bash
uv run python -c "import datetime as dt; from messy_csv import pipeline; a, r = pipeline.run(dt.date.today()); print(a.height, r.height)"
```

Expected: duas contagens que somam 5000.

- [ ] **Step 7: Commit**

```bash
git add src/messy_csv/pipeline.py tests/test_pipeline.py data/clean/orders.csv data/rejects/rejects.csv
git commit -m "feat: pipeline com a ordem fixa dos seis transformadores"
```

---

## Task 12: Profiling e métricas before/after

Cobre a Etapa 6 (deslocada por L1) e a metade analítica da Etapa 8.

O ponto central está em `view_from_clean`: o dataset limpo é **renderizado de
volta** à forma textual de cinco colunas antes de ser medido. Parece um rodeio,
mas é o que garante que "antes" e "depois" passem pela mesma régua. A
alternativa — duas funções de medição, uma para texto e outra para tipado —
começa idêntica e diverge na primeira manutenção, e aí a melhora reportada
passa a incluir a diferença entre os dois códigos.

**Files:**
- Create: `src/messy_csv/profile.py`, `src/messy_csv/metrics.py`
- Test: `tests/test_profile.py`, `tests/test_metrics.py`

**Interfaces:**
- Consumes: `clean.dates.parse_date_expr`, `clean.dates.is_in_range_expr`, `clean.currency.amount_expr`, `clean.currency.currency_expr`, `clean.categories.canonical_expr`, `clean.whitespace.is_clean_text_expr`
- Produces:
  - `profile.VIEW_COLUMNS`, `profile.DIMENSION_LABELS: dict[str, str]`
  - `profile.ProfileResult` (dataclass congelada, com `.dimensions`, `.score`, `.to_dict()`)
  - `profile.view_from_raw(df) -> pl.DataFrame`, `profile.view_from_clean(df) -> pl.DataFrame`
  - `profile.profile(view, today) -> ProfileResult`
  - `profile.dirt_counts(view) -> list[dict[str, object]]`
  - `metrics.DimensionDelta`, `metrics.Comparison`, `metrics.compare(before, after, rows_quarantined) -> Comparison`

- [ ] **Step 1: Escrever os testes de profiling que falham**

`tests/test_profile.py`:

```python
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
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/test_profile.py -v`
Expected: FAIL com `ImportError: cannot import name 'profile'`.

- [ ] **Step 3: Escrever `profile.py`**

```python
"""As seis dimensoes de qualidade do §7, medidas com a regua dos transformadores.

Nao ha um segundo parser aqui: `dates`, `currency`, `categories` e `whitespace`
exportam suas expressoes e este modulo as consome. Se "data valida" fosse
definida duas vezes, o before/after compararia reguas diferentes e a melhora
reportada incluiria a divergencia entre os dois codigos.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import polars as pl

from messy_csv import contract
from messy_csv.clean import categories, currency, dates, whitespace

VIEW_COLUMNS: tuple[str, ...] = ("order_id", "order_date", "customer", "category", "amount")
TEXT_COLUMNS: tuple[str, ...] = ("customer", "category")

DIMENSION_LABELS: dict[str, str] = {
    "completeness": "Completude",
    "uniqueness": "Unicidade",
    "temporal_validity": "Validade temporal",
    "category_consistency": "Consistência de categoria",
    "currency_normalization": "Normalização monetária",
    "text_cleanliness": "Limpeza textual",
}


@dataclass(frozen=True)
class ProfileResult:
    rows: int
    completeness: float
    uniqueness: float
    temporal_validity: float
    category_consistency: float
    currency_normalization: float
    text_cleanliness: float

    @property
    def dimensions(self) -> dict[str, float]:
        return {chave: float(getattr(self, chave)) for chave in DIMENSION_LABELS}

    @property
    def score(self) -> float:
        """Media aritmetica das seis: pesos iguais sao escolha deliberada (§7)."""
        valores = list(self.dimensions.values())
        return round(sum(valores) / len(valores) * 100, 1)

    def to_dict(self) -> dict[str, float | int]:
        return {"rows": self.rows, **self.dimensions, "score": self.score}


def view_from_raw(df: pl.DataFrame) -> pl.DataFrame:
    """Aceita o frame carregado pelo pipeline (raw_*) ou o CSV cru."""
    if "raw_order_id" in df.columns:
        return df.select(pl.col(f"raw_{nome}").alias(nome) for nome in VIEW_COLUMNS)
    return df.select(VIEW_COLUMNS)


def view_from_clean(df: pl.DataFrame) -> pl.DataFrame:
    """Renderiza o dataset limpo de volta a forma textual medida no raw.

    E o que torna antes e depois comparaveis por construcao, e nao por duas
    implementacoes parecidas que se espera que continuem parecidas.
    """
    valor = pl.col("amount_original").round(2).cast(pl.String)
    return df.select(
        pl.col("order_id").cast(pl.String).alias("order_id"),
        pl.col("order_date").dt.to_string("%Y-%m-%d").alias("order_date"),
        pl.col("customer"),
        pl.col("category").cast(pl.String).alias("category"),
        pl.when(pl.col("currency_original") == "USD")
        .then(pl.format("USD {}", valor))
        .otherwise(pl.format("R$ {}", valor.str.replace(r"\.", ",")))
        .alias("amount"),
    )


def profile(view: pl.DataFrame, today: dt.date) -> ProfileResult:
    linhas = view.height
    if linhas == 0:
        raise ValueError("dataset vazio nao tem qualidade a medir")

    enriquecido = view.with_columns(
        dates.parse_date_expr("order_date").alias("_date"),
        currency.amount_expr("amount").alias("_amount"),
        _category_ok_expr().alias("_category_ok"),
    )

    preenchidas = sum(int(enriquecido[nome].is_not_null().sum()) for nome in VIEW_COLUMNS)
    datas_validas = int(
        enriquecido.select(
            (pl.col("_date").is_not_null() & dates.is_in_range_expr("_date", today)).sum()
        ).item()
    )

    textos = enriquecido.select(
        whitespace.is_clean_text_expr(nome).alias(nome) for nome in TEXT_COLUMNS
    )
    textos_limpos = sum(int(textos[nome].sum() or 0) for nome in TEXT_COLUMNS)
    textos_preenchidos = sum(int(textos[nome].count()) for nome in TEXT_COLUMNS)

    return ProfileResult(
        rows=linhas,
        completeness=preenchidas / (linhas * len(VIEW_COLUMNS)),
        uniqueness=enriquecido["order_id"].drop_nulls().n_unique() / linhas,
        temporal_validity=datas_validas / linhas,
        category_consistency=int(enriquecido["_category_ok"].sum()) / linhas,
        currency_normalization=int(enriquecido["_amount"].is_not_null().sum()) / linhas,
        # denominador so com celulas preenchidas: ausencia ja pesa em completude
        text_cleanliness=(textos_limpos / textos_preenchidos) if textos_preenchidos else 1.0,
    )


def _category_ok_expr() -> pl.Expr:
    """Linha em categoria canonica (§7).

    Duas formas contam: o rotulo que o mapa canonico reconhece, e o rotulo que
    ja e um valor do contrato. A segunda existe por causa de `Nao informado`,
    que missing.py produz e que de proposito nao esta no mapa canonico (D7).
    """
    canonica = categories.canonical_expr("category").is_not_null()
    ja_no_contrato = pl.col("category").str.strip_chars().is_in(list(contract.CATEGORIES))
    return (canonica | ja_no_contrato).fill_null(False)


def dirt_counts(view: pl.DataFrame) -> list[dict[str, object]]:
    """Linhas afetadas por cada sujeira do catalogo §5, para a tabela do relatorio."""
    enriquecido = view.with_columns(
        categories.canonical_expr("category").alias("_category"),
        currency.currency_expr("amount").alias("_currency"),
    )
    texto_sujo = pl.any_horizontal(
        ~whitespace.is_clean_text_expr(nome).fill_null(True) for nome in VIEW_COLUMNS
    )
    id_numerico = pl.col("order_id").str.strip_chars().str.contains(r"^\d+$")

    return [
        {
            "sujeira": "Whitespace",
            "causa": "Digitação manual no painel",
            "linhas": enriquecido.filter(texto_sujo).height,
        },
        {
            "sujeira": "Datas inconsistentes",
            "causa": "Três sistemas integrados",
            "linhas": enriquecido.filter(
                ~pl.col("order_date").str.contains(r"^\d{4}-\d{2}-\d{2}$").fill_null(False)
            ).height,
        },
        {
            "sujeira": "IDs duplicados",
            "causa": "Retry de integração com marketplace",
            "linhas": enriquecido.filter(id_numerico & pl.col("order_id").is_duplicated()).height,
        },
        {
            "sujeira": "Valores ausentes",
            "causa": "Falha parcial de importação",
            "linhas": enriquecido.filter(
                pl.any_horizontal(pl.col(nome).is_null() for nome in VIEW_COLUMNS)
            ).height,
        },
        {
            "sujeira": "Moedas mistas",
            "causa": "Loja vende para fora do Brasil",
            "linhas": enriquecido.filter(pl.col("_currency") == "USD").height,
        },
        {
            "sujeira": "Categorias inconsistentes",
            "causa": "Cadastro livre, sem enum",
            "linhas": enriquecido.filter(
                pl.col("_category").is_null()
                | (pl.col("_category") != pl.col("category").str.strip_chars())
            ).height,
        },
    ]
```

Duas escolhas de medição que mudam o número reportado e por isso precisam ficar
explícitas:

**Limpeza textual mede só células preenchidas.** Uma célula vazia já foi contada
em completude. Contá-la de novo aqui puniria o mesmo defeito duas vezes e faria
o score global cair mais do que a realidade justifica.

**Unicidade usa ids distintos não nulos sobre o total de linhas.** Um id
ilegível não é "mais um valor distinto"; contá-lo como tal inflaria a unicidade
justamente no dataset mais sujo.

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/test_profile.py -v`
Expected: todos PASS. Se `test_dataset_limpo_pontua_cem` falhar, a causa é quase
sempre `view_from_clean` produzindo um texto que o próprio parser não relê —
verifique o vaivém do separador decimal em BRL.

- [ ] **Step 5: Escrever os testes de métricas que falham**

`tests/test_metrics.py`:

```python
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
```

- [ ] **Step 6: Escrever `metrics.py`**

```python
"""Comparacao before/after entre dois ProfileResult."""

from __future__ import annotations

from dataclasses import dataclass

from messy_csv.profile import DIMENSION_LABELS, ProfileResult


@dataclass(frozen=True)
class DimensionDelta:
    key: str
    label: str
    before: float
    after: float

    @property
    def delta(self) -> float:
        return self.after - self.before


@dataclass(frozen=True)
class Comparison:
    before: ProfileResult
    after: ProfileResult
    rows_quarantined: int

    @property
    def dimensions(self) -> list[DimensionDelta]:
        antes = self.before.dimensions
        depois = self.after.dimensions
        return [
            DimensionDelta(chave, rotulo, antes[chave], depois[chave])
            for chave, rotulo in DIMENSION_LABELS.items()
        ]

    @property
    def score_delta(self) -> float:
        return round(self.after.score - self.before.score, 1)

    @property
    def rows_kept(self) -> int:
        return self.after.rows

    @property
    def quarantine_rate(self) -> float:
        return self.rows_quarantined / self.before.rows


def compare(
    before: ProfileResult, after: ProfileResult, rows_quarantined: int
) -> Comparison:
    return Comparison(before=before, after=after, rows_quarantined=rows_quarantined)
```

`compare` é uma linha e poderia ser dispensada em favor do construtor. Ela existe
porque o nome documenta a direção da comparação: `Comparison(a, b)` não diz qual
é o antes, e trocar os dois por engano produziria um relatório coerente e errado.

- [ ] **Step 7: Rodar os testes até passarem**

Run: `uv run pytest tests/test_metrics.py tests/test_profile.py -v`
Expected: todos PASS.

- [ ] **Step 8: Commit**

```bash
git add src/messy_csv/profile.py src/messy_csv/metrics.py tests/test_profile.py tests/test_metrics.py
git commit -m "feat: seis dimensoes de qualidade medidas com a regua dos transformadores"
```

---

## Task 13: Relatório HTML — dados, template e renderização

Fecha a metade visual da Etapa 8. As métricas já existem (Task 12); o que falta é
transformá-las em uma página que um recrutador entende em cinco minutos, sem
servidor e sem rede.

Uma decisão de composição aparece aqui e vale ser dita antes do código: o
relatório **não** é montado a partir dos dois CSVs finais. Ele consome o frame
largo devolvido por `pipeline.transform` — aquele em que `raw_*` e as colunas
tipadas convivem na mesma linha. É a única forma de a seção "antes e depois"
mostrar a mesma linha dos dois lados. Reconstruir esse pareamento a partir de
`orders_dirty.csv` e `orders.csv` exigiria um join por `order_id`, que é
justamente a coluna que a limpeza consertou — juntar pela chave suja para provar
que a chave suja foi consertada é circular.

**Files:**
- Create: `src/messy_csv/report.py`, `src/messy_csv/templates/report.html.j2`
- Test: `tests/test_report.py`
- Generated: `docs/index.html`

**Interfaces:**
- Consumes: `pipeline.transform`, `contract.validate`, `contract.RAW_COLUMNS`,
  `contract.REJECT_REASON_SEPARATOR`, `contract.reject_reason_expr`,
  `profile.profile`, `profile.view_from_raw`, `profile.view_from_clean`,
  `profile.dirt_counts`, `metrics.compare`
- Produces:
  - `SAMPLE_SIZE: int`, `TEMPLATE_DIR: Path`, `TEMPLATE_NAME: str`, `REPORT_PATH: Path`
  - `format_brl(value: float) -> str`
  - `SampleRow`, `QuarantineGroup`, `ReportData` (dataclasses congeladas)
  - `build_samples(transformed: pl.DataFrame, today: dt.date, limit: int = SAMPLE_SIZE) -> list[SampleRow]`
  - `group_quarantine(rejected: pl.DataFrame) -> list[QuarantineGroup]`
  - `build(raw, transformed, accepted, rejected, today) -> ReportData`
  - `render(data: ReportData) -> str`
  - `write(data: ReportData, path: Path = REPORT_PATH) -> Path`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_report.py`:

```python
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
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/test_report.py -v`
Expected: FAIL com `ImportError: cannot import name 'report' from 'messy_csv'`.

- [ ] **Step 3: Escrever `report.py`**

```python
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
```

- [ ] **Step 4: Escrever o template `src/messy_csv/templates/report.html.j2`**

```jinja
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Messy CSV Challenge — Relatório de qualidade</title>
<style>
:root {
  color-scheme: light dark;
  --bg: #fbfbfd; --surface: #ffffff; --border: #e3e3ea;
  --text: #17171c; --muted: #5b5b6b;
  --up: #0b7a4b; --down: #b3261e; --accent: #3350d8;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f0f13; --surface: #18181f; --border: #2b2b35;
    --text: #ececf1; --muted: #a2a2b2;
    --up: #4bd991; --down: #ff8f85; --accent: #93a6ff;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 1.5rem 1rem 4rem; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  font-size: 16px; line-height: 1.55;
}
main { max-width: 62rem; margin: 0 auto; }
h1 { font-size: 1.55rem; margin: 0 0 .25rem; letter-spacing: -.01em; }
h2 { font-size: 1.1rem; margin: 2.75rem 0 .75rem; }
h3 { font-size: .8rem; font-weight: 600; color: var(--muted); margin: 0 0 .35rem; }
p.lead { color: var(--muted); margin: 0 0 2rem; font-size: .92rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: .65rem; padding: .9rem; }
.scores { display: flex; flex-wrap: wrap; gap: .75rem; }
.scores .card { flex: 1 1 9rem; text-align: center; }
.scores b { display: block; font-size: 2.1rem; font-variant-numeric: tabular-nums; line-height: 1.15; }
.grid { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(13rem, 1fr)); }
.bar { height: .35rem; border-radius: 999px; background: var(--border); overflow: hidden; margin-top: .55rem; }
.bar i { display: block; height: 100%; background: var(--accent); }
.up { color: var(--up); } .down { color: var(--down); }
del, ins { text-decoration: none; }
del { color: var(--down); } ins { color: var(--up); }
.scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; background: var(--surface);
        border: 1px solid var(--border); border-radius: .65rem; font-size: .9rem; }
th, td { padding: .5rem .7rem; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--muted); font-weight: 600; white-space: nowrap; }
tr:last-child td { border-bottom: 0; }
.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.sample { margin-bottom: .75rem; }
.sample table { font-size: .85rem; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .85em; word-break: break-word; }
.empty { color: var(--muted); font-style: italic; }
footer { color: var(--muted); font-size: .85rem; margin-top: 3.5rem; border-top: 1px solid var(--border); padding-top: 1rem; }
</style>
</head>
<body>
<main>

<h1>Messy CSV Challenge — relatório de qualidade</h1>
<p class="lead">
  Dataset sintético de {{ data.comparison.before.rows }} pedidos, gerado sujo de
  propósito, medido, limpo e medido de novo com a mesma régua.
  Execução de {{ data.generated_at.strftime("%d/%m/%Y") }}.
</p>

<section id="sumario">
<h2>Sumário executivo</h2>
<div class="scores">
  <div class="card">
    <h3>Score antes</h3>
    <b>{{ "%.1f"|format(data.comparison.before.score) }}</b>
  </div>
  <div class="card">
    <h3>Score depois</h3>
    <b class="up">{{ "%.1f"|format(data.comparison.after.score) }}</b>
  </div>
  <div class="card">
    <h3>Variação</h3>
    <b class="{{ 'up' if data.comparison.score_delta >= 0 else 'down' }}">{{ "%+.1f"|format(data.comparison.score_delta) }}</b>
  </div>
  <div class="card">
    <h3>Linhas aprovadas</h3>
    <b>{{ data.comparison.rows_kept }}</b>
  </div>
  <div class="card">
    <h3>Quarentena</h3>
    <b>{{ data.comparison.rows_quarantined }}</b>
    <span class="mono">{{ "%.1f"|format(data.comparison.quarantine_rate * 100) }}%</span>
  </div>
</div>
</section>

<section id="dimensoes">
<h2>As seis dimensões</h2>
<div class="grid">
  {% for d in data.comparison.dimensions %}
  <div class="card">
    <h3>{{ d.label }}</h3>
    <del>{{ "%.1f"|format(d.before * 100) }}%</del>
    →
    <ins>{{ "%.1f"|format(d.after * 100) }}%</ins>
    <div class="bar"><i style="width: {{ "%.1f"|format(d.after * 100) }}%"></i></div>
  </div>
  {% endfor %}
</div>
</section>

<section id="sujeiras">
<h2>Catálogo de sujeiras no dado bruto</h2>
<div class="scroll">
<table>
  <thead><tr><th>Sujeira</th><th>Causa simulada</th><th class="num">Linhas afetadas</th></tr></thead>
  <tbody>
  {% for item in data.dirt %}
    <tr>
      <td>{{ item["sujeira"] }}</td>
      <td>{{ item["causa"] }}</td>
      <td class="num">{{ item["linhas"] }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
</section>

<section id="amostras">
<h2>Antes e depois, linha a linha</h2>
{% for amostra in data.samples %}
<div class="sample scroll">
<table>
  <thead><tr><th>Campo</th><th>Antes</th><th>Depois</th></tr></thead>
  <tbody>
  {% for coluna in data.columns %}
    <tr>
      <td>{{ coluna }}</td>
      <td class="mono">{% if amostra.before[coluna] %}{{ amostra.before[coluna] }}{% else %}<span class="empty">vazio</span>{% endif %}</td>
      <td class="mono">{{ amostra.after[coluna] }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% endfor %}
</section>

<section id="quarentena">
<h2>Quarentena por motivo</h2>
{% if data.quarantine %}
<div class="scroll">
<table>
  <thead><tr><th>Motivo</th><th class="num">Linhas</th><th>Exemplo do dado original</th></tr></thead>
  <tbody>
  {% for grupo in data.quarantine %}
    <tr>
      <td>{{ grupo.reason }}</td>
      <td class="num">{{ grupo.rows }}</td>
      <td class="mono">{{ grupo.example.values()|join(" | ") }}</td>
    </tr>
  {% endfor %}
  </tbody>
</table>
</div>
{% else %}
<p class="empty">Nenhuma linha rejeitada.</p>
{% endif %}
</section>

<section id="metodologia">
<h2>Nota metodológica</h2>
<p>
  As seis dimensões têm <strong>peso igual</strong>. Qualquer ponderação seria
  arbitrária sem um consumidor real do dado dizendo qual delas dói mais.
</p>
<p>
  O score do "depois" é medido sobre o dataset limpo <strong>renderizado de volta
  à forma textual de cinco colunas</strong> do dado bruto. É um rodeio deliberado:
  garante que antes e depois passem pelo mesmo código de medição. Duas funções de
  medição — uma para texto, outra para dado tipado — começariam idênticas e
  divergiriam na primeira manutenção, e a melhora reportada passaria a incluir a
  diferença entre os dois códigos.
</p>
<p>
  <strong>Limpeza textual</strong> mede só células preenchidas: uma célula vazia
  já pesa em completude, e contá-la duas vezes puniria o mesmo defeito em
  duplicidade. <strong>Unicidade</strong> divide os <code>order_id</code>
  distintos e não nulos pelo total de linhas — um id ilegível não é "mais um
  valor distinto".
</p>
<p>
  Linhas que violam o contrato vão para <strong>quarentena</strong>, nunca para o
  lixo, e são gravadas exatamente como chegaram. Uma linha pode acumular mais de
  um motivo, então a soma da coluna "Linhas" acima pode ultrapassar o total
  rejeitado.
</p>
<p>
  <strong>Dinheiro nunca é imputado.</strong> Valor ausente ou ilegível rejeita a
  linha. A única imputação do pipeline é a categoria ausente, que vira
  <code>Não informado</code> — um rótulo que declara a ausência em vez de
  escondê-la. As taxas de câmbio são fictícias, porém plausíveis, e vêm de uma
  tabela mensal versionada no repositório: uma API de cotação em tempo real
  tornaria o resultado irreproduzível amanhã.
</p>
</section>

<footer>
  Gerado por <code>messy-csv report</code> — HTML e CSS próprios, sem framework,
  sem requisição externa e sem JavaScript.
</footer>

</main>
</body>
</html>
```

- [ ] **Step 5: Rodar os testes até passarem**

Run: `uv run pytest tests/test_report.py -v`
Expected: todos PASS.

Duas falhas prováveis e o que elas significam:

- `TemplateNotFound: report.html.j2` — o diretório `templates/` não foi criado
  dentro de `src/messy_csv/`, ou o arquivo ficou com outro nome. `FileSystemLoader`
  resolve por caminho de disco, então não há instalação a consertar.
- `test_amostras_sao_linhas_que_realmente_mudaram` com lista vazia — significa que
  `build_samples` não encontrou nenhuma linha aprovada com diferença. Confira se
  `raw_*` sobreviveu até o fim do frame largo: se `whitespace.apply` estivesse
  sobrescrevendo as colunas originais em vez de criar `t_*`, o "antes" seria igual
  ao "depois" por construção.

- [ ] **Step 6: Verificar a página com os próprios olhos**

A CLI só existe na Task 14. Gere o HTML direto:

```bash
uv run python -c "import datetime as dt; from messy_csv import contract, pipeline, report; from messy_csv.clean import currency; bruto = pipeline.load_raw(pipeline.RAW_PATH); fx = currency.load_fx_rates(currency.FX_PATH); t = pipeline.transform(bruto, fx); a, r = contract.validate(t, dt.date.today()); print(report.write(report.build(bruto, t, a, r, dt.date.today())))"
```

Expected: imprime `docs\index.html`. Abra o arquivo no navegador e confirme os
três itens que teste nenhum verifica: (1) a página está legível com a janela
estreitada a 375px, (2) o modo escuro do sistema muda as cores, (3) o console do
navegador não acusa erro.

- [ ] **Step 7: Rodar as verificações de qualidade**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: as três passam. Se o mypy reclamar dos acessos a `linha[...]`, lembre
que `to_dicts()` devolve `list[dict[str, Any]]` — os `str(...)`, `int(...)` e
`float(...)` explícitos existem exatamente para satisfazer `warn_return_any`.

- [ ] **Step 8: Commit**

```bash
git add src/messy_csv/report.py src/messy_csv/templates/report.html.j2 tests/test_report.py docs/index.html
git commit -m "feat: relatorio HTML estatico com before/after, quarentena e nota metodologica"
```

---

## Task 14: CLI — os cinco comandos e a fronteira do relógio

Fecha a tabela de comandos da spec (§6, "CLI") e entrega o critério de sucesso 4:
`uv run messy-csv run` a partir de um repositório limpo produz os quatro
artefatos. O entrypoint `messy-csv = "messy_csv.cli:main"` já está declarado no
`pyproject.toml` desde a Task 1 — até aqui ele apontava para um módulo
inexistente.

Este módulo é **o único lugar do projeto que pode chamar `dt.date.today()`**.
Toda função de domínio recebe `today` por parâmetro (§12.5); é aqui, na
composição, que o valor entra no sistema. O flag `--today` existe para que o
teste injete uma data fixa em vez de depender do relógio do runner.

**Files:**
- Create: `src/messy_csv/cli.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `generate.write_dirty_dataset`, `pipeline.load_raw`,
  `pipeline.transform`, `pipeline.run`, `contract.validate`,
  `currency.load_fx_rates`, `profile.profile`, `profile.view_from_raw`,
  `profile.view_from_clean`, `report.build`, `report.write`
- Produces:
  - `DATA_DIR: Path`, `DOCS_DIR: Path`
  - `Layout` (dataclass congelada com `.raw`, `.clean`, `.rejects`, `.fx`, `.report`)
  - `build_parser() -> argparse.ArgumentParser`
  - `main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Escrever os testes que falham**

`tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Rodar os testes para confirmar que falham**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL com `ImportError: cannot import name 'cli' from 'messy_csv'`.

- [ ] **Step 3: Escrever `cli.py`**

```python
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

    sub.add_parser("clean", parents=[comum], help="limpa, valida e grava os dois CSVs").set_defaults(
        handler=cmd_clean
    )
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
    except FileNotFoundError as erro:
        print(f"arquivo nao encontrado: {erro.filename}", file=sys.stderr)
        return 2
```

Uma nota sobre `cmd_run`: ele reexecuta a limpeza duas vezes — uma em `cmd_clean`,
para gravar os CSVs, e outra dentro de `_build_report`, para o antes e depois
pareado. É desperdício consciente. A alternativa seria `cmd_run` chamar as peças
diretamente e passar o frame largo adiante, o que economizaria dois segundos e
faria `run` deixar de ser a composição literal dos três comandos que o usuário
pode rodar à mão. Num dataset de 5.000 linhas, a legibilidade vale mais.

- [ ] **Step 4: Rodar os testes até passarem**

Run: `uv run pytest tests/test_cli.py -v`
Expected: todos PASS.

Se `test_clean_sem_dataset_bruto_falha_com_mensagem` falhar com uma exceção do
Polars em vez de `FileNotFoundError`, é porque a versão instalada embrulha o erro
de I/O. Nesse caso troque o `except FileNotFoundError` por:

```python
    except (FileNotFoundError, pl.exceptions.ComputeError) as erro:
        print(f"arquivo nao encontrado ou ilegivel: {erro}", file=sys.stderr)
        return 2
```

e ajuste a asserção do teste para procurar `orders_dirty.csv` na mensagem
completa. Não troque a asserção por um `assert codigo == 2` isolado: a mensagem
é o que diferencia um erro útil de um traceback.

- [ ] **Step 5: Provar que o entrypoint instalado funciona**

```bash
uv run messy-csv --help
uv run messy-csv run
```

Expected: o `--help` lista os cinco comandos; o `run` imprime três linhas
(gerado, aprovados/quarentena, relatório com os dois scores) e termina em 0.

- [ ] **Step 6: Rodar a suíte inteira e as verificações de qualidade**

Run: `uv run pytest --cov=messy_csv --cov-report=term-missing`
Then: `uv run ruff check . && uv run ruff format --check . && uv run mypy src`
Expected: tudo passa.

- [ ] **Step 7: Commit**

```bash
git add src/messy_csv/cli.py tests/test_cli.py data docs/index.html
git commit -m "feat: cli com generate, profile, clean, report e run"
```

---

## Task 15: README, publicação no GitHub Pages e fechamento

Fecha a Etapa 9 e a spec inteira. Aqui o repositório deixa de ser um projeto que
funciona na máquina e vira uma peça que alguém abre em cinco minutos: relatório
publicado, badge verde, README que explica a tese sem exigir leitura de código.

Esta é também a única tarefa que precisa da rede e de uma conta. Se o `gh` não
estiver autenticado, os Steps 5 a 8 pedem intervenção sua — o resto roda sozinho.

**Files:**
- Create: `README.md`, `docs/.nojekyll`
- Modify: `.github/workflows/ci.yml` (acrescentar o job ponta a ponta)

**Interfaces:**
- Consumes: tudo. É a tarefa de fechamento.
- Produces: repositório publicado, `docs/index.html` no ar, badge de CI no README

- [ ] **Step 1: Desligar o Jekyll no diretório publicado**

O GitHub Pages roda Jekyll por padrão e ignora diretórios que começam com
underscore. Nosso `docs/` hoje não tem nenhum, mas `docs/superpowers/` vai junto
para o site, e um arquivo vazio elimina uma classe inteira de surpresa futura.

```bash
touch docs/.nojekyll
```

- [ ] **Step 2: Acrescentar o job ponta a ponta ao CI**

Adicione ao final de `.github/workflows/ci.yml`, no mesmo nível de `quality:`:

```yaml
  pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Instalar uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Sincronizar o ambiente
        run: uv sync --locked

      - name: Cadeia completa
        run: uv run messy-csv run

      - name: Os quatro artefatos existem
        run: |
          test -f data/raw/orders_dirty.csv
          test -f data/clean/orders.csv
          test -f data/rejects/rejects.csv
          test -f docs/index.html

      - name: Os dados versionados sao reproduziveis
        run: git diff --exit-code -- data/
```

O último passo é o que transforma "determinístico" de afirmação em fato
verificado: se qualquer mudança futura alterar uma linha de `orders.csv`, o CI
reprova o pull request. `docs/index.html` fica **fora** dessa checagem de propósito
— ele carrega a data de execução, então mudaria todo dia por um motivo que não é
regressão. O determinismo dos dados é o que importa; a data no cabeçalho do
relatório é ruído.

- [ ] **Step 3: Escrever o `README.md`**

Dois valores só existem depois de rodar, e o Step 4 os substitui: `SCORE_ANTES` e
`SCORE_DEPOIS`. O slug do repositório entra no Step 6.

````markdown
# Messy CSV Challenge

[![CI](https://github.com/SEU-USUARIO/messy-csv-challenge/actions/workflows/ci.yml/badge.svg)](https://github.com/SEU-USUARIO/messy-csv-challenge/actions/workflows/ci.yml)

Um dataset de 5.000 pedidos gerado **sujo de propósito**, medido, limpo por um
pipeline testado e medido de novo com a mesma régua.

**Score de qualidade: SCORE_ANTES → SCORE_DEPOIS.**

📊 **[Relatório completo, com o antes e o depois](https://SEU-USUARIO.github.io/messy-csv-challenge/)**

---

## A tese

O tema aparente é limpeza de dados. O tema real é **processo**.

O repositório foi construído na ordem correta de iniciação, e o `git log` é a
prova: o primeiro commit contém apenas a spec de design, o segundo o ambiente, o
terceiro as barreiras de qualidade — ruff, mypy strict, pre-commit e CI — **antes
do primeiro módulo de domínio**. Uma barreira instalada depois só reprova código
que já existe, e a tentação passa a ser afrouxar a barreira em vez de consertar o
código. Instalada antes, ela nunca teve nada a perdoar.

Os dois documentos que geraram tudo estão versionados:

- [Spec de design](docs/superpowers/specs/2026-08-24-messy-csv-design.md) — decisões e o porquê de cada uma
- [Plano de implementação](docs/superpowers/plans/2026-08-25-messy-csv-implementation.md) — as tarefas, na ordem em que foram executadas

## Rodando

```bash
uv sync
uv run messy-csv run
```

Isso produz os quatro artefatos: `data/raw/orders_dirty.csv`,
`data/clean/orders.csv`, `data/rejects/rejects.csv` e `docs/index.html`.

| Comando | Efeito |
|---|---|
| `uv run messy-csv generate` | Gera o CSV sujo (seed 42, 5.000 linhas) |
| `uv run messy-csv profile <path>` | Imprime o profiling em JSON — aceita o CSV sujo e o limpo |
| `uv run messy-csv clean` | Limpa, valida e grava o aprovado e a quarentena |
| `uv run messy-csv report` | Gera `docs/index.html` |
| `uv run messy-csv run` | A cadeia inteira |

Todo comando aceita `--today YYYY-MM-DD`. É a única leitura de relógio do
projeto, e ela fica na CLI: nenhuma função de domínio chama `date.today()`, o que
torna cada teste independente da data em que roda.

## Como funciona

```
generate  ->  data/raw/orders_dirty.csv
                  |
        profile(raw) ------------------+
                  |                    |
        clean (6 transformadores)      |
                  |                    |
        contract.validate              |
            |-> data/clean/orders.csv  |
            +-> data/rejects/rejects.csv
                  |                    |
        profile(clean) ----------------+
                                       |
                          metrics -> report -> docs/index.html
```

Seis transformadores puros `DataFrame -> DataFrame`, em ordem fixa:

`whitespace` → `dates` → `currency` → `categories` → `duplicates` → `missing`

A ordem é significativa. A dependência mais sutil é a de `duplicates` para
`missing`: se a imputação rodasse antes da deduplicação, a categoria ausente já
teria virado `Não informado`, aquela linha deixaria de contar um nulo e poderia
vencer a disputa contra a linha originalmente completa. A regra "mantém a mais
completa" seria silenciosamente corrompida. [Um teste dedicado cobre exatamente
essa inversão.](tests/test_pipeline.py)

## Quatro decisões que definem o projeto

**Transformadores não rejeitam; o contrato rejeita.** Cada módulo de `clean/`
transforma e nada mais. `contract.py` é o único lugar onde "limpo" está definido.
Se a regra de aceitação estivesse espalhada pelos seis, mudá-la significaria
caçar seis arquivos e torcer.

**Quarentena, não descarte.** Linha que viola o contrato vai para
`rejects.csv` com o motivo, gravada exatamente como chegou. Um pipeline que
descarta em silêncio esconde o tamanho do próprio problema.

**Dinheiro nunca é imputado.** Valor ausente ou ilegível rejeita a linha. A única
imputação é a categoria, que vira `Não informado` — um rótulo que declara a
ausência em vez de escondê-la.

**Câmbio por tabela mensal versionada.** As taxas são fictícias, porém
plausíveis, e moram em `data/fx_rates.csv`. Uma API de cotação em tempo real
tornaria o resultado de hoje irreproduzível amanhã.

O raciocínio completo, incluindo as alternativas descartadas, está na
[spec](docs/superpowers/specs/2026-08-24-messy-csv-design.md).

## Qualidade

```bash
uv run pytest --cov=messy_csv --cov-report=term-missing
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

Cobertura mínima de 90% em `contract.py` e em `clean/` — verificada no CI com um
limiar por caminho, não global. Um limiar global de 90% seria satisfeito por
testes concentrados no gerador enquanto o contrato ficasse descoberto, que é
exatamente o inverso do que importa.

`mypy` roda em modo **strict**. `pre-commit` reproduz as três verificações antes
de cada commit local.

## Stack

Python 3.13 · [uv](https://docs.astral.sh/uv/) · [Polars](https://pola.rs)
(eager) · Jinja2 · pytest · ruff · mypy · GitHub Actions · GitHub Pages

Sem banco de dados, sem orquestrador, sem Docker e sem dashboard interativo — as
[exclusões estão justificadas uma a uma na spec](docs/superpowers/specs/2026-08-24-messy-csv-design.md).

## Limites declarados

O dataset é sintético e não reproduz a distribuição estatística de um e-commerce
real: serve para exercitar regras, não para inferir comportamento de mercado. As
taxas de câmbio são inventadas. Timezone é ignorado — datas com hora são
truncadas para data.
````

- [ ] **Step 4: Substituir os dois scores pelos números reais**

```bash
uv run messy-csv report
```

O comando imprime `score X -> Y`. Substitua:

```bash
sed -i "s/SCORE_ANTES/X/; s/SCORE_DEPOIS/Y/" README.md
```

Verify: `grep -n "SCORE_" README.md` não retorna nada.

- [ ] **Step 5: Criar o repositório remoto**

```bash
gh repo create messy-csv-challenge --public --source=. --remote=origin
```

Se o `gh` não estiver autenticado, rode `gh auth login` antes (é interativo — no
Claude Code, prefixe com `!` para rodar no seu terminal).

- [ ] **Step 6: Substituir o slug do repositório no README**

```bash
SLUG=$(gh repo view --json nameWithOwner -q .nameWithOwner)
USUARIO=${SLUG%%/*}
sed -i "s|SEU-USUARIO|$USUARIO|g" README.md
```

Verify: `grep -n "SEU-USUARIO" README.md` não retorna nada, e as três URLs do
topo apontam para o seu usuário.

- [ ] **Step 7: Commit e push**

```bash
git add README.md docs/.nojekyll .github/workflows/ci.yml
git commit -m "docs: readme com a tese, o mapa do pipeline e o link do relatorio"
git push -u origin main
```

- [ ] **Step 8: Ligar o GitHub Pages**

```bash
gh api -X POST "repos/$(gh repo view --json nameWithOwner -q .nameWithOwner)/pages" \
  -f "source[branch]=main" -f "source[path]=/docs"
```

Se a API responder `409 Conflict`, o Pages já estava ligado — siga. Pela
interface: **Settings → Pages → Source: Deploy from a branch → main → /docs**.

Não há workflow de deploy porque não é preciso: `docs/index.html` está versionado,
e publicar direto do branch é uma peça a menos para quebrar.

- [ ] **Step 9: Confirmar que a página está no ar**

```bash
gh browse --no-browser
curl -sSI "https://$(gh repo view --json owner -q .owner.login).github.io/messy-csv-challenge/" | head -1
```

Expected: `HTTP/2 200`. A primeira publicação leva um a dois minutos; um `404`
imediato depois do Step 8 é normal — espere e repita.

- [ ] **Step 10: Percorrer os oito critérios de sucesso da spec**

Rode um a um e confirme cada saída. Este é o gate final do projeto: nenhum deles
depende de julgamento.

```bash
uv run pytest                                                              # 1
uv run coverage report --include="*/messy_csv/contract.py,*/messy_csv/clean/*" --fail-under=90   # 1
uv run ruff check . && uv run ruff format --check .                        # 2
uv run mypy src                                                            # 3
uv run messy-csv run                                                       # 4
```

| # | Critério | Como confirmar |
|---|---|---|
| 1 | Suíte passa com 90% em `contract.py` e `clean/` | os dois comandos acima terminam em 0 |
| 2 | ruff sem violação | idem |
| 3 | mypy strict sem erro | idem |
| 4 | `run` produz os quatro artefatos | `ls data/raw data/clean data/rejects docs/index.html` |
| 5 | Duas execuções de `generate` dão o mesmo SHA-256 | rodar `generate` duas vezes e comparar o hash do CSV |
| 6 | 100% de `orders.csv` conforme ao contrato | `test_dataset_aprovado_satisfaz_cem_por_cento_do_contrato` passou no item 1 |
| 7 | CI verde | `gh run list --limit 1` mostra `completed success` para os dois jobs |
| 8 | Página legível em 375px e em dark mode, sem erro de console | abrir a URL publicada e conferir com as ferramentas do navegador |

Para o critério 5, no PowerShell:

```powershell
uv run messy-csv generate; $a = (Get-FileHash data/raw/orders_dirty.csv -Algorithm SHA256).Hash
uv run messy-csv generate; $b = (Get-FileHash data/raw/orders_dirty.csv -Algorithm SHA256).Hash
if ($a -eq $b) { "determinismo OK: $a" } else { "FALHOU" }
```

- [ ] **Step 11: Commit final e marcação da versão**

```bash
git add -A
git commit -m "chore: artefatos da execucao final"
git tag -a v1.0.0 -m "Ciclo completo: gerar, medir, limpar, validar e publicar"
git push origin main --tags
```

---

## Cobertura da spec

Mapa de cada seção da spec para a tarefa que a implementa. Serve para conferir,
na hora de executar, que nada ficou sem dono.

| Spec | Tarefa |
|---|---|
| §4.1 Entrada suja | Task 4 (gerador), Task 11 (`load_raw`, `infer_schema=False`) |
| §4.2 Saída limpa | Task 3 (`clean_schema`), Task 11 (artefato) |
| §4.3 Quarentena | Task 3 (nove motivos), Task 13 (agrupamento no relatório) |
| §5 Catálogo de sujeiras | Task 4 (produção), Task 12 (`dirt_counts`) |
| §5.1 Formatos de data | Task 6 |
| §5.2 Mapa de categorias | Task 8 |
| §5.3 Formatos monetários | Task 7 |
| §5.4 Regra de deduplicação | Task 9 |
| §6 Arquitetura | Tasks 5–11 |
| §6.1 Ordem dos transformadores | Task 11 (`transform` e o teste da inversão) |
| §6 CLI | Task 14 |
| §7 Métricas | Task 12 |
| §8 Estratégia de testes | distribuída; cobertura verificada nas Tasks 2, 11 e 15 |
| §9 Relatório | Task 13 |
| §10 Ambiente e ferramental | Tasks 1 e 2 |
| §11 Critérios de sucesso | Task 15, Step 10 |
| §13 Etapas 1–9 | Tasks 1–15 (§13.6 deslocada por L1) |
