# Operação na VPS (Contabo `vmi3639791`)

Estado do deploy da integração `clipping-tv` + `campinas-news-scraper`.

---

## 1. Onde está cada coisa

| Item | Caminho / endereço |
|---|---|
| Painel público | **https://newstube.com.br** |
| Repo do clipping-tv | `/root/projetos/clipping-tv` (branch `feature/horario-eleitoral`) |
| Repo do scraper | `/root/projetos/campinas-news-scraper` (branch `main`) |
| Banco | container `clipping-postgres`, db `clipping`, user `clipping` |
| Rede Docker compartilhada | `clipping-tv_default` |
| Backups | `/root/backups/clipping_full_*.dump` |

> ⚠️ `tv.parquetsistemas.com.br` **não** está configurado no nginx do host
> (só `newstube.com.br` e `media.newstube.com.br`). O domínio resolve no
> Cloudflare mas não tem origem → HTTP 522. Use `newstube.com.br`.

---

## 2. Containers

```bash
# clipping-tv
cd /root/projetos/clipping-tv && docker compose ps

# scraper (usa o banco do clipping, sem Postgres próprio)
cd /root/projetos/campinas-news-scraper && docker compose ps
```

Esperado:

```
clipping-api        Up (healthy)
clipping-web        Up
clipping-postgres   Up (healthy)
clipping-notify     Up
campinas-news-worker Up (healthy)
```

---

## 3. Comandos do dia a dia

### Coleta manual

```bash
cd /root/projetos/campinas-news-scraper
docker compose run --rm worker collect
docker compose run --rm worker stats
```

### Recalcular palavras-chave

Depois de criar/alterar keywords `kind='site'` no painel:

```bash
docker compose run --rm worker rematch
# ou só um dia:
docker compose run --rm worker rematch --day 2026-11-23
```

### Ver o que entrou

```bash
cd /root/projetos/clipping-tv
docker compose exec postgres psql -U clipping -d clipping -c \
  "SELECT source_slug, count(*) FROM sites.articles GROUP BY 1 ORDER BY 1;"
```

### Logs

```bash
docker compose logs -f worker          # scraper
docker compose logs -f api notify      # clipping-tv
```

---

## 4. Agendamento

O worker do scraper roda:

- **diário às 06:30** (America/Sao_Paulo)
- **a cada 120 min** (intraday)

Configurado em `/root/projetos/campinas-news-scraper/.env`:

```env
SCHEDULE_DAILY_AT=06:30
SCHEDULE_INTRADAY_MINUTES=120
SCHEDULE_RUN_ON_START=false
```

Para mudar, edite o `.env` e `docker compose up -d --force-recreate worker`.

---

## 5. Portais bloqueados — resolvido com proxy automático

| Portal | Status | Observação |
|---|---|---|
| G1 Campinas | ✅ ok | direto |
| A Cidade On | ✅ ok | direto |
| Sampi Campinas | ✅ ok | direto |
| Diário Campineiro | ✅ ok | direto |
| Hora Campinas | ✅ ok | **via proxy** (bloqueia o IP da VPS) |
| CBN Campinas | ✅ ok | **via proxy** (bloqueia o IP da VPS) |

Hora Campinas e CBN retornam **403 inclusive na home page**, com User-Agent
de navegador completo — é bloqueio por IP/ASN, não por header. Retry direto
não resolve.

### Como funciona o fallback

Implementado em [`scraping/proxy.py`](../src/campinas_news/scraping/proxy.py:1)
e integrado ao [`Fetcher`](../src/campinas_news/scraping/fetcher.py:1):

1. Requisição direta. Se vier **403/451**, o host é marcado como bloqueado.
2. Baixa a lista pública do **ProxyScrape** (sem API key).
3. Testa os candidatos em paralelo contra o **próprio feed alvo** — exige
   HTTP 200 e corpo com `<rss`/`<feed`/`<?xml`.
4. Usa até 4 proxies distintos; cada falha remove o proxy do pool.
5. O pool tem TTL de 30 min e é reconstruído quando esvazia.
6. Hosts não bloqueados **não pagam custo nenhum** — o pool só é construído
   quando o 403 acontece.

Sem proxy disponível, cai para conexão direta (best-effort) e a coleta segue
em modo `partial` — nunca falha por causa do proxy.

### Custo observado

Os dois portais via proxy levam mais tempo (CBN ~5 min, Hora ~6,5 min) porque
proxies gratuitos são lentos e instáveis. Os outros quatro seguem rápidos.
A coleta completa leva ~6,5 min.

### Alternativas (se o proxy gratuito incomodar)

1. **Proxy residencial pago** — preencher `SCRAPER_PROXY_URL` no `.env`:
   ```env
   SCRAPER_PROXY_URL=http://user:pass@host:port
   ```
   Quando definido, o `Fetcher` usa esse proxy para **todas** as requisições.
2. **Rodar o scraper em outra máquina** (IP não bloqueado) apontando para o
   mesmo banco via `POSTGRES_HOST=<ip-da-vps>`.
3. **Contatar os portais** para liberar o IP da agência.

---

## 6. Rollback

```bash
# remove a view e o schema sites (não toca no acervo TV/Rádio)
cd /root/projetos/clipping-tv
docker compose run --rm api alembic downgrade 0017

# parar o scraper
cd /root/projetos/campinas-news-scraper
docker compose down
```

Restaurar o banco a partir do backup:

```bash
docker compose exec -T postgres pg_restore -U clipping -d clipping --clean \
  < /root/backups/clipping_full_20261123_180219.dump
```

---

## 7. Migrações: dois projetos, duas tabelas de versão

| Projeto | Tabela de versão | Versão atual |
|---|---|---|
| clipping-tv | `public.alembic_version` | `0018` |
| scraper | `sites.alembic_version` | `0001_initial` |

O scraper **não** roda `alembic upgrade` no entrypoint quando o schema já
existe (as tabelas foram criadas pela migração `0018` do clipping-tv). Se
precisar recriar do zero, rode `alembic stamp head` no scraper.

---

## 8. Checklist de saúde

```bash
# 1. containers
cd /root/projetos/clipping-tv && docker compose ps
cd /root/projetos/campinas-news-scraper && docker compose ps

# 2. API
curl -s https://newstube.com.br/api/healthz

# 3. dados
docker compose exec postgres psql -U clipping -d clipping -c \
  "SELECT origem, count(*) FROM feed_unificado GROUP BY 1;"

# 4. saúde das fontes
docker compose exec postgres psql -U clipping -d clipping -c \
  "SELECT source_slug, consecutive_failures, last_success_at FROM sites.source_health ORDER BY 1;"
```
