# Integração: `campinas-news-scraper` → `clipping-tv`

Documento de arquitetura da fusão dos dois projetos em um acervo único com
painel de três abas (TV / Rádio / Sites).

---

## 1. Decisão de arquitetura

**Um banco PostgreSQL, dois schemas.**

```
PostgreSQL (VPS Contabo)
├── public.*          ← acervo TV/Rádio (já existe no clipping-tv)
│   ├── programs      (edição: canal, kind=tv|radio, recorded_at)
│   ├── blocks        (matéria: título, resumo, texto, categoria, matched)
│   ├── clips         (mídia cortada)
│   ├── keywords      (catálogo de termos, kind=tv|radio|site)
│   ├── block_keywords
│   ├── users / user_keywords / notifications / deliveries
│   └── app_state
└── sites.*           ← acervo de portais (novo)
    ├── sources       (os 6 portais)
    ├── articles      (matéria web: título, corpo, autor, published_at)
    ├── article_revisions
    ├── scrape_runs / scrape_run_items / source_health
    └── article_keywords  (espelho de block_keywords)
```

**Por que não dois bancos:** o painel precisa de uma lista unificada por data,
busca textual cruzada e o mesmo motor de notificação. Com dois schemas no mesmo
banco, um `UNION ALL` resolve a aba "Tudo" e o `notify_worker` passa a enxergar
as duas fontes com uma única query.

**Por que não migrar `articles` para `blocks`:** `blocks` é indexado por
`program_id` e tem `start_s`/`end_s` (tempo de gravação). Uma matéria web não
tem programa nem offset. Forçar isso criaria `programs` sintéticos e poluiria o
modelo. Schemas separados + uma **view de compatibilidade** é mais honesto.

---

## 2. Contrato de dados unificado

A view `public.feed_unificado` normaliza as duas fontes no formato que o painel
já consome (`FeedItem`):

| Campo do painel | `blocks` (TV/Rádio) | `sites.articles` |
|---|---|---|
| `id` | `b.id` | `-a.id` (negativo, evita colisão) |
| `kind` | `p.kind` (`tv`/`radio`) | `'site'` |
| `title` | `b.title` | `a.title` |
| `summary` | `b.summary` | `a.summary` |
| `text` | `b.text` | `a.body_text` |
| `program_date` | `p.program_date` | `a.local_day` |
| `channel` | `p.channel` | `s.name` (nome do portal) |
| `program_name` | `p.name` | `s.name` |
| `start_s` / `end_s` | reais | `0` |
| `recorded_at` | `p.recorded_at` | `a.published_at` |
| `categoria` | `b.categoria` | `a.section` |
| `tags` | `b.tags` | `array_to_string(a.tags, ',')` |
| `matched` | `b.matched` | `a.matched` |
| `has_clip` | existe clip verificado | `false` |
| `source_url` | `null` | `a.url` (link para o original) |
| `image_url` | `null` | `a.image_url` |

O `id` negativo é a chave da solução: o painel continua chamando
`/api/blocks/{id}` e o backend roteia `id < 0` para `sites.articles`.

---

## 3. Mudanças no `clipping-tv`

### 3.1 Migração `0018_sites_schema.py`

Cria o schema `sites`, as tabelas e a view `feed_unificado`. Idempotente
(`IF NOT EXISTS`), segura para rodar em produção.

### 3.2 `clipping/api.py`

- `GET /api/feed?tipo=site` → consulta `sites.articles`.
- `GET /api/feed?tipo=` (vazio) → consulta a view unificada.
- `GET /api/blocks/{id}` com `id < 0` → devolve a matéria web.
- `GET /api/filters?tipo=site` → datas/canais dos portais.
- `POST /api/articles/{id}/send` → envia matéria web por WhatsApp/Telegram
  (texto + link, sem mídia).

### 3.3 `clipping/notify_worker.py`

- `KIND` ganha `"site": "Site"`.
- `build()` aceita matéria web: sem `veiculo(channel)` de emissora, usa o nome
  do portal; sem `_when(recorded_at, start_s)`, usa `published_at`.
- A query de clips ganha um `UNION` com `sites.articles` (matéria web não tem
  clipe, então o "gate de mídia" é desligado para `kind='site'`).

### 3.4 `clipping/models_pg.py`

Modelos `SiteSource`, `SiteArticle` mapeados em `schema="sites"`.

---

## 4. Mudanças no `campinas-news-scraper`

### 4.1 `core/config.py`

- `POSTGRES_SCHEMA=sites` (novo).
- `CLIPPING_INGEST_URL` + `CLIPPING_INGEST_TOKEN` (opcional): quando definidos,
  o worker faz `POST /api/ingest-site` no clipping-tv em vez de escrever direto
  no banco. Útil se o scraper rodar em outro host.

### 4.2 `db/models.py`

- `Base.metadata.schema = "sites"` (via `MetaData(schema="sites")`).
- Nova tabela `article_keywords` (espelho de `block_keywords`).

### 4.3 `worker/collector.py`

- Após o upsert, calcula `matched` contra `public.keywords WHERE kind='site'`
  e grava em `sites.article_keywords` — assim o `notify_worker` do clipping-tv
  encontra as matérias web sem mudança de lógica.

### 4.4 `docker-compose.yml`

- O serviço `worker` aponta para o **mesmo Postgres** do clipping-tv
  (`POSTGRES_HOST=postgres`, mesma rede Docker).
- Migração Alembic do scraper roda com `search_path=sites`.

---

## 5. Redesign do painel (`web/`)

### 5.1 Design system

Tokens em `globals.css` (Tailwind 4 `@theme`):

- Paleta: `ink` (neutros), `brand` (azul-petróleo), `accent` (âmbar).
- Tipografia: `Inter` para UI, `Source Serif` para títulos de matéria.
- Raio, sombra e espaçamento consistentes.
- Modo claro/escuro via `prefers-color-scheme` + toggle.

### 5.2 Layout

```
┌──────────────────────────────────────────────────────────┐
│  Sidebar (desktop)  │  Topbar (mobile: drawer)           │
│  ─ Logo             │  ─ Busca global                    │
│  ─ TV               │  ─ Data / filtros                  │
│  ─ Rádio            │  ─ Perfil                          │
│  ─ Sites            │                                    │
│  ─ Palavras-chave   │  ┌──────────────────────────────┐  │
│  ─ Usuários         │  │  Lista de matérias (cards)   │  │
│                     │  └──────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

- **Desktop ≥1024px**: sidebar fixa 260px + conteúdo.
- **Tablet 768–1023px**: sidebar colapsada em ícones.
- **Mobile <768px**: topbar + drawer; filtros em bottom-sheet.

### 5.3 Abas

| Aba | Fonte | Card | Detalhe |
|---|---|---|---|
| **TV** | `blocks` kind=tv | player de vídeo, canal, horário | vídeo + transcrição |
| **Rádio** | `blocks` kind=radio | player de áudio, emissora | áudio + transcrição |
| **Sites** | `sites.articles` | imagem, portal, data, resumo | texto completo + link original |

### 5.4 Componentes novos

- `AppShell.tsx` — sidebar + topbar + drawer.
- `Tabs.tsx` — abas com contador por tipo.
- `ArticleCard.tsx` — card de matéria web.
- `ArticleDetail.tsx` — detalhe com texto completo e envio.
- `FilterBar.tsx` — busca + data + portal + categoria.
- `EmptyState.tsx`, `Skeleton.tsx`, `Toast.tsx`.

---

## 6. Deploy na VPS

```bash
# 1. clipping-tv: aplicar migração
cd /root/projetos/clipping-tv
git pull --ff-only
docker compose run --rm api alembic upgrade head

# 2. scraper: subir na mesma rede
cd /root/projetos/campinas-news-scraper
cp .env.example .env   # POSTGRES_HOST=postgres, POSTGRES_DB=clipping
docker compose up -d --build

# 3. painel: rebuild
cd /root/projetos/clipping-tv
docker compose up -d --build web
```

O `nginx` do host continua servindo `tv.parquetsistemas.com.br` → `web:3010`
e `/api` → `api:8000`. Nada muda no roteamento.

---

## 7. Ordem de implementação

1. Migração `0018` + view unificada.
2. Endpoints `/api/feed?tipo=site` e `/api/blocks/{id}` negativo.
3. Scraper escrevendo em `sites.*` + `article_keywords`.
4. `notify_worker` com `kind='site'`.
5. Redesign do painel (design system → shell → abas → cards → detalhe).
6. Testes e validação de build.
