# Messy CSV Challenge — Design

**Data:** 2026-08-24
**Status:** aprovado para planejamento
**Autor:** Ronaldo Philippe (com Claude)

---

## 1. Objetivo

Construir uma peça de portfólio que demonstre o ciclo completo de qualidade de
dados: gerar um dataset propositalmente sujo, medir o estrago, corrigi-lo com um
pipeline testado e publicar um relatório que prove a melhoria com números.

O tema aparente é limpeza de dados. O tema real é **processo**: o projeto é
construído na ordem correta de iniciação, sem etapas puladas e sem retrofit.

### Público

Recrutadores técnicos e engenheiros de dados avaliando o repositório em ~5
minutos. A primeira coisa que veem é o relatório publicado; a segunda é o README;
a terceira é a estrutura de `src/`.

---

## 2. Escopo

### Dentro

- Gerador determinístico de dataset sujo (pedidos de e-commerce)
- Profiling de qualidade (antes e depois)
- Pipeline de limpeza modular e testado
- Validação contra contrato explícito, com quarentena
- Relatório HTML estático com métricas before/after
- Ferramental completo de qualidade de código e CI

### Fora

| Item | Motivo |
|---|---|
| API de cotação em tempo real | Quebra determinismo e reprodutibilidade |
| Banco de dados | CSV basta; DB adicionaria infra sem servir à tese |
| Dashboard interativo | HTML estático publica de graça e não expira |
| Orquestrador (Airflow/Dagster) | Escala que o projeto não tem |
| Property-based testing (Hypothesis) | Casos tabelados cobrem as regras; adiciona curva sem retorno proporcional |
| Docker | `uv` já garante reprodutibilidade |
| Dados reais | Sujeira precisa ser controlada para ser medida |

---

## 3. Decisões arquiteturais

### D1 — Python + Jinja2 para HTML estático

Pipeline em Python gera um relatório HTML com template e CSS próprios.

**Por quê:** liberdade visual total sem um segundo stack. Saída estática publica
no GitHub Pages de graça, sem servidor, e o link não expira.

**Descartado:** Streamlit (layout preso ao tema, exige servidor); frontend
Next.js separado (dobra escopo e desloca o foco de dados para frontend);
notebook (não testável, diff ilegível, execução não reproduzível).

### D2 — Polars, não pandas

**Por quê:** o padrão `pl.coalesce(...str.strptime(..., strict=False))` declara
explicitamente cada formato de data aceito e converte falha em `null`
auditável — que vira métrica direta no relatório. O equivalente em pandas
(`format="mixed"`) infere linha a linha: conveniente, mas não auditável.
Somam-se tipagem que o mypy entende e ausência de `SettingWithCopyWarning`.

**Custo aceito:** pandas aparece mais em descrições de vaga. Mitigado por uma
seção do README explicando a escolha.

### D3 — DataFrame eager, não LazyFrame

**Por quê:** o dataset tem ~5.000 linhas. Lazy não traz ganho mensurável nessa
escala e afasta o erro do ponto que o causou (a exceção surge no `.collect()`).

**Quando mudaria:** acima de ~1.000.000 de linhas, ou se o pipeline passasse a
ler de múltiplas fontes. Registrado no README como decisão consciente.

### D4 — Câmbio por tabela mensal versionada

`data/fx_rates.csv` com colunas `month,currency,rate_to_brl`. A conversão faz
join pela competência do pedido.

**Por quê:** uma taxa única converteria um pedido de 2023 com cotação de 2024 —
erro conceitual. A tabela separa dado de código e corrige a dimensão temporal.

**Descartado:** API de cotação (não-determinística, quebra CI offline).

### D5 — Transformadores não rejeitam; o validador rejeita

| Camada | Faz | Nunca faz |
|---|---|---|
| `clean/*.py` | Conserta o que dá; deixa `null` no que não dá | Rejeita linha |
| `contract.py` | Valida uma vez, separa aprovados/rejeitados, acumula motivos | Transforma dado |

**Por quê:** validação espalhada tornaria "por que esta linha foi rejeitada?"
uma pergunta de seis arquivos, e o primeiro transformador a rejeitar encerraria
o assunto — impossibilitando motivos múltiplos. Centralizar mantém o contrato
como único lugar onde "limpo" está definido.

### D6 — Quarentena, não descarte

Linha reprovada vai para `data/rejects/rejects.csv` com a coluna
`reject_reason` (motivos separados por ponto e vírgula). Nenhum dado é destruído.

### D7 — Dinheiro nunca é imputado

| Campo ausente | Destino | Motivo |
|---|---|---|
| `amount` | Quarentena | Valor monetário inventado corrompe análise financeira |
| `customer` | Quarentena | Sem identificação não há pedido rastreável |
| `category` | Vira `Não informado` | Rótulo honesto, não falseia fato |

**Por quê:** imputar só é aceitável quando o rótulo substituto declara a própria
ignorância. `Não informado` faz isso; um valor monetário ou um nome inventado,
não — eles se passam por dado real.

**Sem colunas de flag de imputação:** com uma única imputação no projeto, uma
coluna extra poluiria o contrato para carregar um bit que o relatório já
reporta de forma agregada.

### D8 — Procedência preservada

O dataset limpo mantém `amount_original` e `currency_original` ao lado de
`amount_brl`. Descartar o original impediria auditar ou recalcular a conversão.

---

## 4. Contrato de dados

### 4.1 Entrada suja (`data/raw/orders_dirty.csv`)

Cinco colunas, todas lidas como texto (`infer_schema=False`):

`order_id, order_date, customer, category, amount`

Ler tudo como texto é deliberado: inferência de schema sobre dado sujo falha ou
adivinha, e adivinhação não é auditável.

### 4.2 Saída limpa (`data/clean/orders.csv`)

| Coluna | Tipo | Regra de validação |
|---|---|---|
| `order_id` | `Int64` | não nulo, único, maior que zero |
| `order_date` | `Date` | não nulo, entre 2023-01-01 e a data de execução |
| `customer` | `String` | não vazio, sem espaço nas pontas, sem espaço duplo interno |
| `category` | `Enum` | Eletrônicos, Moda, Casa, Livros, Esporte ou Não informado |
| `amount_original` | `Float64` | não nulo, maior que zero |
| `currency_original` | `Enum` | BRL ou USD |
| `amount_brl` | `Float64` | não nulo, maior que zero, duas casas decimais |

### 4.3 Quarentena (`data/rejects/rejects.csv`)

Colunas originais mais `reject_reason` com os motivos acumulados.

Motivos possíveis: `order_id inválido`, `order_id duplicado irreconciliável`,
`data inválida`, `data fora do intervalo`, `cliente ausente`,
`categoria desconhecida`, `valor ausente`, `valor inválido`,
`valor não positivo`.

---

## 5. Catálogo de sujeiras

Seed fixa `42`, 5.000 linhas. Cada sujeira tem causa plausível declarada.

| # | Sujeira | Causa na narrativa | Taxa | Tratamento |
|---|---|---|---|---|
| 1 | Whitespace | Digitação manual no painel | 12% dos textos | `strip` mais colapso de espaço interno |
| 2 | Datas inconsistentes | Três sistemas integrados | 40% não-ISO | `coalesce` de formatos declarados |
| 3 | IDs duplicados | Retry de integração com marketplace | 3% das linhas | Mantém a versão mais completa |
| 4 | Valores ausentes | Falha parcial de importação | amount 4%, category 3%, customer 2% | Ver D7 |
| 5 | Moedas mistas | Loja vende para fora do Brasil | 18% em USD | Parse do símbolo mais join de câmbio |
| 6 | Categorias inconsistentes | Cadastro livre, sem enum | 30% variantes | Normalização mais mapa canônico |

### 5.1 Formatos de data aceitos

Tentados nesta ordem, via `pl.coalesce`:

| Formato | Exemplo | Proporção |
|---|---|---|
| `%Y-%m-%d` | `2024-03-15` | 60% |
| `%d/%m/%Y` | `15/03/2024` | 25% |
| `%b %d %Y` | `Mar 16 2024` | 8% |
| `%Y-%m-%d %H:%M:%S` | `2024-03-15 10:30:00` | 5% |
| inválida | `2024-13-02` | 2%, vai para quarentena |

### 5.2 Mapa canônico de categorias

Normalização: minúsculas, remoção de acentos, `strip`, colapso de espaço.
Depois, lookup em dicionário explícito.

| Variantes na entrada | Canônico |
|---|---|
| `eletronicos`, `ELETRONICOS`, `Eletrônico`, `eletro` | Eletrônicos |
| `moda`, `MODA`, `Modas`, `vestuario` | Moda |
| `casa`, `Casa e Decoração`, `casa_decoracao` | Casa |
| `livros`, `LIVRO`, `livraria` | Livros |
| `esporte`, `Esportes`, `ESPORTE` | Esporte |
| `diversos`, `outros`, `misc` | nenhum, vai para quarentena |

O valor `diversos` existe deliberadamente para provar que a quarentena funciona:
sem uma categoria irrecuperável, `rejects.csv` por categoria ficaria sempre
vazio e o caminho não estaria testado com dado real.

### 5.3 Formatos monetários

| Entrada | Moeda | Valor |
|---|---|---|
| `R$ 1.299,90` | BRL | 1299.90 |
| `1.299,90` | BRL por padrão | 1299.90 |
| `$ 249.00` | USD | 249.00 |
| `USD 249.00` | USD | 249.00 |
| vazio, `-`, `n/a` | nenhuma | quarentena |

Ausência de símbolo assume BRL — suposição documentada, coerente com uma loja
brasileira.

### 5.4 Regra de deduplicação

1. Agrupar por `order_id`
2. Manter a linha com **menos campos nulos**
3. Empate resolve pelo menor índice de origem (estável e determinístico)

Se após a escolha a linha ainda violar o contrato, vai para quarentena com o
motivo `order_id duplicado irreconciliável`.

---

## 6. Arquitetura

```
src/messy_csv/
├─ contract.py     # schema alvo, validação, separação aprovados/rejeitados
├─ generate.py     # dataset sujo determinístico (seed 42)
├─ profile.py      # mede um dataset e devolve ProfileResult
├─ clean/
│  ├─ whitespace.py
│  ├─ dates.py
│  ├─ currency.py
│  ├─ categories.py
│  ├─ duplicates.py
│  └─ missing.py
├─ metrics.py      # compara dois ProfileResult e produz o before/after
├─ report.py       # ProfileResult mais métricas viram HTML via Jinja2
└─ cli.py          # entrypoint
```

Cada módulo de `clean/` expõe uma função `DataFrame -> DataFrame`, pura e sem
efeito colateral, com um arquivo de teste correspondente.

### 6.1 Ordem dos transformadores

A ordem é significativa e fixa. Trocá-la muda o resultado:

| # | Transformador | Depende de | Por que nesta posição |
|---|---|---|---|
| 1 | `whitespace` | nada | Todo parse posterior assume texto já aparado; `" 15/03/2024 "` não casa com formato de data |
| 2 | `dates` | whitespace | Produz `order_date`, de onde sai a competência mensal |
| 3 | `currency` | dates | O join da tabela de câmbio usa o mês do pedido |
| 4 | `categories` | whitespace | O mapa canônico compara texto normalizado |
| 5 | `duplicates` | 1 a 4 | Precisa dos nulos **reais** para escolher a linha mais completa |
| 6 | `missing` | duplicates | Imputa por último, depois que a disputa já foi decidida |

A dependência mais sutil é a de 5 para 6. Se `missing` rodasse antes de
`duplicates`, a categoria ausente já teria virado `Não informado` e aquela linha
deixaria de contar um nulo — podendo vencer a disputa contra a linha
originalmente completa. A regra "mantém a mais completa" seria silenciosamente
corrompida, e o defeito só apareceria na inspeção manual dos dados finais.

Um teste dedicado cobre essa inversão: um par duplicado em que a ordem errada
elege a linha errada.

### Fluxo

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

### CLI

| Comando | Efeito |
|---|---|
| `messy-csv generate` | Gera o CSV sujo |
| `messy-csv profile <path>` | Imprime o profiling em JSON |
| `messy-csv clean` | Limpa, valida e grava limpo mais rejeitados |
| `messy-csv report` | Gera `docs/index.html` |
| `messy-csv run` | Executa a cadeia inteira |

---

## 7. Métricas de qualidade

Seis dimensões, cada uma uma razão entre 0 e 1, medidas antes e depois:

| Dimensão | Fórmula |
|---|---|
| Completude | células não nulas dividido pelo total de células |
| Unicidade | `order_id` distintos dividido pelo total de linhas |
| Validade temporal | datas parseáveis e no intervalo dividido pelo total |
| Consistência de categoria | linhas em categoria canônica dividido pelo total |
| Normalização monetária | valores parseáveis com moeda identificada dividido pelo total |
| Limpeza textual | textos sem whitespace anômalo dividido pelo total |

**Score global** é a média aritmética das seis dimensões multiplicada por 100 e
arredondada a uma casa decimal.

Pesos iguais são uma escolha deliberada: qualquer ponderação seria arbitrária
sem um consumidor real do dado definindo qual dimensão dói mais.

---

## 8. Estratégia de testes

TDD: o teste de cada transformador é escrito antes da implementação.

| Nível | O que verifica |
|---|---|
| Unitário (`clean/`) | Um arquivo por transformador, casos tabelados incluindo os limites da seção 5 |
| Contrato | Dataset limpo satisfaz 100% das regras da seção 4.2 |
| Determinismo | Gerar duas vezes com seed 42 produz o mesmo hash SHA-256 |
| Quarentena | Cada motivo da seção 4.3 é produzido por ao menos um caso |
| Métricas | Score sobe do raw para o clean; toda dimensão fica entre 0 e 1 |
| Relatório | HTML gerado contém todas as seções esperadas |

Cobertura mínima: **90%** em `contract.py` e em `clean/`.

---

## 9. Relatório

Página única, HTML e CSS próprios, sem framework.

Seções: sumário executivo com score antes e depois, cards das seis dimensões,
tabela por sujeira com contagens, amostras before/after lado a lado, quarentena
agrupada por motivo e nota metodológica.

Requisitos: legível a partir de 375px, dark e light via `prefers-color-scheme`,
nenhuma requisição externa (CSS local ou inline) e tipografia com fallback de
sistema.

---

## 10. Ambiente e ferramental

| Ferramenta | Função |
|---|---|
| Python 3.13 | Runtime mínimo |
| uv | Ambiente, dependências e lockfile |
| Polars | DataFrame |
| Jinja2 | Template do relatório |
| pytest com pytest-cov | Testes e cobertura |
| ruff | Lint e format |
| mypy em modo strict | Type check |
| pre-commit | Barreira local antes do commit |
| GitHub Actions | CI em push e pull request |

---

## 11. Critérios de sucesso

Verificáveis por comando, sem julgamento subjetivo:

1. `uv run pytest` passa inteiro, com cobertura de no mínimo 90% em
   `contract.py` e `clean/`
2. `uv run ruff check .` e `uv run ruff format --check .` sem violação
3. `uv run mypy src` sem erro em modo strict
4. `uv run messy-csv run` a partir de repositório limpo produz os quatro
   artefatos: `orders_dirty.csv`, `orders.csv`, `rejects.csv` e `index.html`
5. Duas execuções de `generate` produzem o mesmo SHA-256
6. Teste de contrato confirma 100% das linhas de `orders.csv` conformes
7. CI verde no GitHub Actions
8. `docs/index.html` abre sem erro de console, legível em 375px e em dark mode

---

## 12. Suposições declaradas

1. As taxas de câmbio são fictícias, porém plausíveis; a própria tabela declara
   isso.
2. O dataset sintético não reproduz a distribuição estatística de um e-commerce
   real. Serve para exercitar regras, não para inferir comportamento de mercado.
3. Timezone é ignorado: datas com hora são truncadas para data.
4. Valor sem símbolo monetário assume BRL.
5. O intervalo válido de datas termina na data de execução, o que torna o teste
   de limite superior dependente do relógio. Aceito, e neutralizado nos testes
   com data injetada.

---

## 13. Etapas de implementação

| # | Etapa | Critério de conclusão |
|---|---|---|
| 1 | Repositório e Git | `git log` mostra a spec como primeiro commit |
| 2 | Ambiente com uv | `uv sync` reproduz o ambiente; lockfile versionado |
| 3 | Qualidade automatizada | ruff, mypy, pre-commit e CI rodando em repositório ainda vazio |
| 4 | Contrato de dados | `contract.py` com testes; nenhum pipeline ainda |
| 5 | Gerador do dataset sujo | Determinismo provado por hash |
| 6 | Profiling | Score do raw calculado e reproduzível |
| 7 | Pipeline de limpeza com TDD | Seis transformadores, cada um com teste próprio |
| 8 | Relatório e before/after | `docs/index.html` gerado |
| 9 | README e publicação | GitHub Pages no ar e badge de CI verde |

O plano de implementação detalhado é produzido a partir desta spec.
