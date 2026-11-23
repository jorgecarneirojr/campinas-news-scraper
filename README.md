# campinas-news-scraper

Coleta diária e estruturada de notícias dos principais portais de **Campinas/SP**, com
persistência em PostgreSQL, worker agendado e stack totalmente dockerizada.

| Fonte | Slug | Estratégia |
|---|---|---|
| G1 Campinas e Região | `g1-campinas` | RSS + HTML |
| Hora Campinas | `hora-campinas` | RSS + HTML |
| A Cidade On Campinas | `acidadeon-campinas` | RSS + HTML |
| Sampi Campinas | `sampi-campinas` | HTML (listagem) |
| CBN Campinas 99,1 FM | `cbn-campinas` | RSS + HTML |
| Diário Campineiro | `diario-campineiro` | RSS + HTML |

---

## Arquitetura

```
┌──────────────┐    ┌────────────────────┐    ┌──────────────┐
│  Scheduler   │───▶│     Collector      │───▶│  PostgreSQL  │
│ (diário +    │    │  (orquestração,    │    │  articles    │
│  intraday)   │    │   isolamento)      │    │  revisions   │
└──────────────┘    └─────────┬──────────┘    │  runs/health │
                              │               └──────────────┘
                    ┌─────────▼──────────┐
                    │   Spiders (6)      │
                    │  discover → parse  │
                    └─────────┬──────────┘
                              │
                    ┌─────────▼──────────┐
                    │      Fetcher       │
                    │ retry · rate-limit │
                    │ cache · HTTP/2     │
                    └────────────────────┘
```

### Decisões de engenharia

- **Configuração 12-factor**: tudo vem de variáveis de ambiente, validadas por
  `pydantic-settings` com *fail-fast*. Segredos nunca entram no código nem no Git.
- **Idempotência**: a chave natural é `(source_slug, url_hash)`, onde `url_hash` é o
  SHA-256 da URL canônica (sem `utm_*`, `fbclid`, fragmento, `www.`). Reexecutar a
  coleta não duplica nada.
- **Histórico de edições**: `article_revisions` guarda um snapshot sempre que o
  `content_hash` (título + corpo) muda — permite auditar alterações pós-publicação.
- **"Dia atual" explícito**: `local_day` é calculado no fuso `America/Sao_Paulo`,
  independentemente do fuso do servidor. Todo instante é armazenado em UTC
  (`timestamptz`).
- **Isolamento de falhas**: cada portal roda em sua própria transação; um site
  quebrado não impede a coleta dos demais. O resultado é registrado em
  `scrape_runs` / `scrape_run_items` / `source_health`.
- **Resiliência HTTP**: retry exponencial com jitter, respeito a `Retry-After`,
  rate-limit por host e cache por execução.
- **Observabilidade**: logs estruturados (JSON em produção) com `run_id` e `site`
  em todas as linhas; `HEALTHCHECK` no container.

---

## Estrutura

```
campinas-news-scraper/
├── src/campinas_news/
│   ├── cli.py                 # Typer: worker, collect, stats, healthcheck…
│   ├── core/                  # config, logging, utilitários de tempo
│   ├── db/                    # modelos ORM, sessão, repositório
│   ├── scraping/
│   │   ├── base.py            # BaseSpider (descoberta + extração)
│   │   ├── feed.py            # parser RSS/Atom
│   │   ├── fetcher.py         # cliente HTTP resiliente
│   │   ├── normalize.py       # texto, URLs, hashing, JSON-LD
│   │   ├── registry.py        # registro de spiders
│   │   └── spiders/           # um módulo por portal
│   └── worker/                # collector + scheduler
├── migrations/                # Alembic
├── tests/                     # pytest + fixtures HTML reais
├── docker/                    # entrypoint e init do Postgres
├── docker-compose.yml
└── Dockerfile
```

---

## Como rodar

### 1. Configurar

```bash
cp .env.example .env
# edite POSTGRES_PASSWORD e demais valores
```

### 2. Subir a stack

```bash
docker compose up -d --build
docker compose logs -f worker
```

O entrypoint aguarda o banco, aplica as migrações e inicia o worker.

### 3. Coleta manual

```bash
docker compose run --rm worker collect
docker compose run --rm worker stats
```

### 4. Banco

```bash
docker compose exec postgres psql -U campinas -d campinas_news
```

---

## Desenvolvimento local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

make lint      # ruff
make type      # mypy --strict
make test      # pytest
make cov       # cobertura
```

Os testes de extração usam fixtures HTML que reproduzem a estrutura real de cada
portal — não dependem de rede.

---

## Modelo de dados

| Tabela | Papel |
|---|---|
| `sources` | cadastro das fontes |
| `articles` | matéria canônica (1 linha por URL) |
| `article_revisions` | histórico de edições |
| `scrape_runs` | execução agregada |
| `scrape_run_items` | resultado por fonte na execução |
| `source_health` | falhas consecutivas por fonte |

Consulta típica — matérias de hoje:

```sql
SELECT source_slug, count(*)
FROM articles
WHERE local_day = (now() AT TIME ZONE 'America/Sao_Paulo')::date
GROUP BY source_slug
ORDER BY 2 DESC;
```

---

## Adicionar um novo portal

1. Crie `src/campinas_news/scraping/spiders/novo_portal.py` herdando de `BaseSpider`.
2. Defina `definition` (`SourceDefinition`) e os seletores de corpo/título/data.
3. Registre a classe em `SPIDER_CLASSES` (`registry.py`).
4. Adicione uma fixture HTML e um teste em `tests/test_spiders.py`.

---

## Operação

- **Agendamento**: `SCHEDULE_DAILY_AT` (padrão `06:30` BRT) e
  `SCHEDULE_INTRADAY_MINUTES` (padrão `120`) para capturar matérias ao longo do dia.
- **Limites**: `SCRAPER_MAX_ARTICLES_PER_SITE`, `SCRAPER_CONCURRENCY`,
  `SCRAPER_MIN_DELAY`/`SCRAPER_MAX_DELAY` — ajuste com respeito aos portais.
- **Proxy**: `SCRAPER_PROXY_URL` caso a VPS precise sair por IP dedicado.

## Licença

MIT.
