# Messy CSV Challenge

[![CI](https://github.com/RPdatascience819/messy-csv-challenge/actions/workflows/ci.yml/badge.svg)](https://github.com/RPdatascience819/messy-csv-challenge/actions/workflows/ci.yml)

Um dataset de 5.000 pedidos gerado **sujo de propósito**, medido, limpo por um
pipeline testado e medido de novo com a mesma régua.

**Score de qualidade: 95.0 → 100.0.**

📊 **[Relatório completo, com o antes e o depois](https://rpdatascience819.github.io/messy-csv-challenge/)**

---

## A tese

O tema aparente é limpeza de dados. O tema real é **processo**.

O repositório foi construído na ordem correta de iniciação, e o `git log` é a
prova: o primeiro commit contém apenas a spec de design, o segundo o ambiente, o
terceiro as barreiras de qualidade — ruff, mypy strict, pre-commit e CI — **antes
do primeiro módulo de domínio**. Uma barreira instalada depois só reprova código
que já existe, e a tentação passa a ser afrouxar a barreira em vez de consertar o
código. 

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

## Como verificar

A barreira de qualidade mais abaixo prova que o **código** faz o que os testes
esperam. Ela não diz nada sobre os CSVs versionados — eles poderiam estar
editados à mão. Quem quiser desconfiar de verdade roda estes dois comandos:

```bash
uv run messy-csv run
git diff --exit-code -- data/
```

O primeiro sobrescreve os artefatos e manda o código gerá-los do zero; o segundo
exige que voltem **idênticos** ao que está commitado. Foi essa checagem que,
durante a construção, pegou um hook de pre-commit comendo os espaços finais que
o gerador injeta de propósito. Os testes estavam todos verdes.

O `git status` vai acusar `M docs/index.html` depois de rodar, e a diferença é de
**1 byte**: o newline final que o `end-of-file-fixer` acrescenta ao commitar e que
o `render()` não emite — `git diff --ignore-all-space -- docs/index.html` sai
vazio. O relatório fica fora do `--exit-code` de propósito, porque carrega a data
de execução e mudaria todo dia por um motivo que não é regressão.

### Duvide da suíte

Teste verde prova que o código passa, não que o teste protege. As duas mutações
abaixo levam um minuto e reprovam em exatamente um lugar cada:

| Mutação | O que quebra |
|---|---|
| Inverter `duplicates` e `missing` em `pipeline.transform()` | 1 teste: `test_ordem_dos_transformadores_decide_a_linha_vencedora` |
| Trocar um valor à mão em `data/clean/orders.csv` | 1 teste: `test_artefatos_versionados_batem_com_o_pipeline`, apontando o byte divergente |

A primeira é a mais reveladora. Com a ordem invertida, o pipeline ainda entrega
4.237 aprovados, 763 em quarentena e score 100,0 — e os CSVs saem **byte a byte
idênticos**. A regra "mantém a linha mais completa" está corrompida e nenhum
artefato denuncia, porque o gerador sempre emite a linha íntegra antes do clone
degradado, e o desempate por ordem de origem acaba escolhendo certo por acidente.
Só o caso forjado expõe a regra. É por isso que ele existe.

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
procurar seis arquivos.

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

**Por que Polars, não pandas.** O padrão `pl.coalesce(...str.strptime(...,
strict=False))` declara explicitamente cada formato de data aceito e converte
falha em `null` auditável, que vira métrica direta no relatório. O equivalente
em pandas (`format="mixed"`) infere linha a linha: conveniente, mas não
auditável. Custo aceito: pandas aparece mais em descrições de vaga — esta seção
é a mitigação combinada com a decisão.

**Por que eager, não lazy.** O dataset tem ~5.000 linhas; `LazyFrame` não traz
ganho mensurável nessa escala e afasta o erro do ponto que o causou (a exceção
só apareceria no `.collect()`, longe de onde nasceu). Mudaria de decisão acima
de ~1.000.000 de linhas, ou se o pipeline passasse a ler de múltiplas fontes —
registrado aqui como escolha consciente, não como esquecimento.

Sem banco de dados, sem orquestrador, sem Docker e sem dashboard interativo — as
[exclusões estão justificadas uma a uma na spec](docs/superpowers/specs/2026-08-24-messy-csv-design.md).

## Limites declarados

O dataset é sintético e não reproduz a distribuição estatística de um e-commerce
real: serve para exercitar regras, não para inferir comportamento de mercado. As
taxas de câmbio são inventadas. Timezone é ignorado — datas com hora são
truncadas para data. O limite superior de data válida não é literalmente "hoje":
é o menor entre `--today` e a última competência coberta por
`data/fx_rates.csv` (hoje, 2024-12) — uma data sem taxa de câmbio cadastrada não
tem como virar `amount_brl` e vai para quarentena em vez de derrubar o processo.
