# VEntregaz

SaaS platform for Amazon FBA sellers — track orders, calculate real profitability, manage FBA inventory and automate pricing decisions. Built with Flask and PostgreSQL.

[![CI](https://github.com/vitormendes4072/projetoV/actions/workflows/ci.yml/badge.svg)](https://github.com/vitormendes4072/projetoV/actions/workflows/ci.yml)
[![Live Demo](https://img.shields.io/badge/demo-online-brightgreen?style=flat&logo=render)](https://ventregaz.onrender.com)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1.1-000000?style=flat&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-3ECF8E?style=flat&logo=supabase&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.x-38B2AC?style=flat&logo=tailwind-css&logoColor=white)
[![codecov](https://codecov.io/gh/vitormendes4072/projetov/branch/main/graph/badge.svg)](https://codecov.io/gh/vitormendes4072/projetov)

---

## Demo Online

**[ventregaz.onrender.com](https://ventregaz.onrender.com)**

Clique em **"Entrar como Demo"** na tela de login para acessar instantaneamente com dados sintéticos pré-carregados — sem precisar criar conta.

> **Cold start:** o Render Free tier hiberna instâncias após 15 min de inatividade. O primeiro acesso pode levar ~50 segundos para acordar o servidor. Aguarde a página carregar — é comportamento esperado do plano gratuito.

**Limitações da demo:**
- Sync Amazon SP-API desativado — requer credenciais reais da SP-API, que o usuário demo não possui. Os dados de pedidos exibidos são sintéticos.
- Worker RQ não roda no Free tier — tarefas assíncronas (importação de pedidos em background) não estão disponíveis.

---

## Screenshots

| Login | Menu Principal |
|-------|----------------|
| ![Login](docs/screenshots/login.jpeg) | ![Menu](docs/screenshots/menu.jpeg) |

| Dashboard Analítico | Calculadora FBA |
|---------------------|------------------|
| ![Dashboard](docs/screenshots/dashboard.jpeg) | ![Calculator](docs/screenshots/calculator.jpeg) |

| Gestão de Produtos | Configurações da Conta |
|--------------------|------------------------|
| ![Products](docs/screenshots/products.jpeg) | ![Settings](docs/screenshots/settings.jpeg) |

| Custos Fixos | Alertas Financeiros |
|--------------|---------------------|
| ![Custos Fixos](docs/screenshots/custos_fixos.jpeg) | ![Alertas](docs/screenshots/alertas.jpeg) |

| Integração Amazon — Pedidos (visão geral) | Integração Amazon — Pedidos (detalhe) |
|--------------------------------------------|----------------------------------------|
| ![Amazon Orders 1](docs/screenshots/amazon_orders1.png) | ![Amazon Orders 2](docs/screenshots/amazon_orders2.png) |

---

## Funcionalidades

- **Autenticação completa** — registro com confirmação por e-mail, login com rate limiting (5 req/min), recuperação de senha com token JWT (30 min TTL)
- **Dashboard analítico** — KPIs em tempo real: total de produtos, simulações, margem média, ROI médio, alertas de estoque baixo e histórico de atividades
- **Calculadora de Preços (FBA)** — simulação de lucro líquido com FBA fee, referral fee, imposto e marketing; persiste histórico por usuário
- **Gestão de Produtos** — CRUD completo com rastreio de SKU (ASIN opcional), controle de estoque e trilha de auditoria por produto
- **Custos Fixos** — cadastro de despesas recorrentes, vencimentos, histórico de pagamentos e categorização
- **Alertas Financeiros** — sistema de notificações configurável (e-mail) para custos vencidos, estoque baixo e margem abaixo do alvo
- **Integração Amazon SP-API** — importação de pedidos, link SKU↔ASIN, snapshot de inventário e finance events (com mocks para dev)
- **Multi-tenancy** — cada usuário vê apenas seus próprios dados; SKU único por usuário, não globalmente
- **Configurações de conta** — troca de nome/e-mail (com confirmação por token) e senha com validação

---

## Destaques Técnicos

### Segurança

| Mecanismo | Implementação |
|-----------|---------------|
| CSRF | Flask-WTF em todos os formulários POST |
| Rate Limiting | Flask-Limiter (5 tentativas/min no login) |
| Content Security Policy | Flask-Talisman com CSP configurado para produção |
| Open Redirect | Validação de `netloc` no parâmetro `next` via `urlsplit` |
| Timing Attack | `time.sleep()` normaliza resposta de reset de senha para ~3s independente de o usuário existir |
| Senhas | Werkzeug `generate_password_hash` / `check_password_hash` |

### Arquitetura

- **App Factory Pattern** (`create_app()`) — separa criação da aplicação da configuração, facilita testes
- **Blueprint por domínio** — `auth`, `main`, `produtos`, `precificacao`, `settings`, `financeiro`, `amazon` completamente desacoplados
- **Migrations versionadas** — Alembic via Flask-Migrate (sem `db.create_all()` em produção)
- **Camada de serviço** — `services/profit_calc.py`, `services/audit_custos_fixos.py` separam regras de negócio das views
- **E-mail assíncrono** — `Thread` em background evita bloquear o response enquanto o SMTP envia
- **Multi-tenancy por linha** — `UniqueConstraint('user_id', 'sku')` garante isolamento de SKU por conta sem vazar informação entre usuários
- **Audit trail** — `ProductHistory` e `CustoFixoHistory` registram toda alteração com timestamp e autor
- **Credenciais criptografadas** — tokens da Amazon SP-API são criptografados em repouso via `app/utils/crypto.py` (Fernet)
- **Configuração por ambiente** — `DevelopmentConfig` / `ProductionConfig` via `APP_ENV` (com fallback `FLASK_ENV`)

### Banco de Dados (visão simplificada)

```
users
 ├── products (1:N) ── product_history (1:N)
 ├── pricing_history (1:N)
 ├── custos_fixos (1:N)
 │    ├── custos_fixos_history (1:N)
 │    └── custos_fixos_pagamentos (1:N)
 ├── notification_settings (1:1)
 ├── notification_recipients (1:N)
 ├── notification_log (1:N)
 └── amazon_credentials (1:1, criptografado)
      ├── amazon_orders (1:N)
      ├── amazon_inventory (1:N)
      ├── amazon_finances (1:N)
      └── amazon_sku_links (1:N)
```

---

## Decisões Arquiteturais

Cada escolha abaixo foi feita com trade-offs explícitos — não por familiaridade ou default.

### Flask em vez de FastAPI

**Decisão:** framework síncrono com Jinja2 para renderização server-side.

Alternativas consideradas: FastAPI, Django.

Flask foi escolhido porque o produto é majoritariamente server-side rendered — não há SPA separado, e o custo de manter um frontend React/Vue apenas para consumir uma API FastAPI não se justifica para o escopo. O ecossistema Flask-Login, Flask-WTF (CSRF), Flask-Limiter e Flask-Smorest (OpenAPI) integra sem adaptadores. FastAPI seria a escolha certa se o produto evoluísse para uma API pública ou um frontend desacoplado — e a camada REST já existe em `/api/v1` via Flask-Smorest para essa transição.

---

### RQ em vez de Celery

**Decisão:** Redis Queue (RQ) para tarefas assíncronas (sync com Amazon SP-API).

Alternativas consideradas: Celery, Dramatiq.

Há exatamente um caso de uso assíncrono no sistema: disparar o job de sincronização de pedidos Amazon sem bloquear o response HTTP. RQ é Redis-nativo, tem zero configuração de broker, e um worker sobe com `rq worker`. Celery para esse único caso adicionaria: configuração de broker separado (ou Redis com serialização explícita), `CELERY_TASK_SERIALIZER`, workers multi-processo e overhead de monitoramento (Flower). RQ é a ferramenta certa quando o problema é simples — Celery é melhor quando há múltiplas filas, rate limiting por tarefa e retry policies complexas.

---

### Supabase em vez de PostgreSQL self-hosted

**Decisão:** PostgreSQL gerenciado via Supabase no free tier.

Alternativas consideradas: Railway, Render PG, Neon, VPS com Docker.

Supabase entrega PostgreSQL completo com connection pooler já configurado (Transaction Pooler na porta 6543 — necessário com Flask-SQLAlchemy que abre várias conexões por request em dev). O dashboard de inspeção de dados acelera debugging sem precisar de psql. O free tier é suficiente para portfólio e a migração para qualquer outro host PostgreSQL é trivial: trocar a `DATABASE_URL`. Não há lock-in de features proprietárias — nenhuma linha do código usa a API REST do Supabase.

---

### Fernet em vez de JWT para credenciais Amazon

**Decisão:** criptografia simétrica (Fernet) para armazenar `lwa_client_secret`, `refresh_token` e `aws_secret` no banco.

Alternativas consideradas: JWT, AES-GCM direto, Vault.

JWT é um formato de token de autenticação para transmissão — não para dados em repouso num banco. Fernet resolve exatamente o problema: criptografia autenticada e simétrica de blobs arbitrários, com `CREDENTIALS_ENCRYPTION_KEY` no ambiente. AES-GCM direto seria equivalente, mas exigiria gerenciar IV, tag de autenticação e padding manualmente — o que a biblioteca `cryptography` já encapsula no Fernet. Vault seria over-engineering para um produto de portfólio sem secrets rotation.

---

### Multi-tenancy por linha em vez de schema-per-tenant

**Decisão:** `user_id` como FK em todas as tabelas + filtro obrigatório nas queries.

Alternativas consideradas: schema-per-tenant (um schema PostgreSQL por usuário), banco-por-tenant.

Schema-per-tenant garante isolamento total, mas torna Alembic migrations um pesadelo (cada migration precisa rodar N vezes), o connection pooling do Supabase não suporta bem e o SQLAlchemy `schema=` dinâmico por request é complexo. Multi-tenancy por linha funciona bem quando: (1) as queries sempre filtram por `user_id` — garantido pela camada de serviço; (2) há `UniqueConstraint('user_id', 'sku')` para evitar colisões; (3) o volume por tenant não exige particionamento. Para o porte deste produto, row-level tenancy é a escolha correta.

---

### Tailwind CLI standalone em vez de pipeline Node.js

**Decisão:** binário pré-compilado do Tailwind CSS (sem Node.js, sem npm).

Alternativas consideradas: npm + PostCSS + autoprefixer, CDN, Bootstrap.

O binário standalone (39 MB) já inclui PostCSS, autoprefixer e os plugins `@tailwindcss/forms` e `@tailwindcss/container-queries`. Contribuidores não precisam instalar Node.js — `pip install -r requirements.txt` é suficiente para rodar o projeto. O CSS buildado é versionado (`app/static/css/tailwind.css`, 29 KB minificado), então a CI/CD também não precisa do binário. CDN seria mais simples, mas impediria purging de classes não usadas e violaria a CSP configurada com `nonce`. Bootstrap foi descartado por impor visual opinativo e dificultar customização de componentes complexos (modais, tabelas aninhadas, gráficos).

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Framework | Flask 3.1.1 |
| ORM | Flask-SQLAlchemy 3.1.1 + SQLAlchemy 2.0 |
| Migrations | Alembic via Flask-Migrate |
| Banco | PostgreSQL via Supabase |
| Auth | Flask-Login 0.6.3 |
| Formulários | Flask-WTF 1.2.2 + WTForms 3.2 |
| E-mail | Flask-Mail + Gmail SMTP |
| Segurança | Flask-Talisman (CSP/HTTPS) + Flask-Limiter |
| Criptografia | cryptography (Fernet) para tokens Amazon |
| Tokens | itsdangerous 2.2 (URLSafeTimedSerializer) |
| Integração externa | Amazon SP-API (com mocks de finance events para dev) |
| Frontend | Tailwind CSS 3 (build local via CLI standalone) |
| Rate limit (prod) | Redis (opcional via `REDIS_URL`, cai para in-memory se ausente) |
| Deploy | Supabase (PostgreSQL) + qualquer WSGI host |

---

## Setup Local

### Pré-requisitos

- Python 3.11+
- Conta no [Supabase](https://supabase.com) (PostgreSQL gratuito)
- Conta Gmail com [App Password](https://myaccount.google.com/apppasswords) habilitada (2FA necessário)

### 1. Clone e ambiente virtual

```bash
git clone <url-do-repo>
cd projetoV1

python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Variáveis de ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
# Flask
FLASK_ENV=development
SECRET_KEY=sua-chave-secreta-longa-e-aleatoria

# Banco de dados (Supabase → Settings → Database → Connection string → URI)
# Use a porta 6543 (Transaction Pooler) para compatibilidade
DATABASE_URL=postgresql://postgres.[ref]:[senha]@aws-0-[region].pooler.supabase.com:6543/postgres

# E-mail (Gmail + App Password)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=seu-email@gmail.com
MAIL_PASSWORD=xxxx-xxxx-xxxx-xxxx
MAIL_DEFAULT_SENDER=seu-email@gmail.com
```

> **Nota sobre App Password:** Acesse [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), crie um app "Mail", copie os 16 caracteres **sem espaços**.

### 3. Rodar

```bash
python run.py
```

Acesse: `http://127.0.0.1:5000`

Antes da primeira execução, aplique as migrations Alembic:

```bash
flask --app run.py db upgrade
```

### 4. (Opcional) Rebuildar o CSS

O CSS do Tailwind já vem versionado em `app/static/css/tailwind.css` (29KB minificado). Você só precisa rebuildá-lo se editar templates com classes novas.

**Setup do binário (uma vez):**

```bash
# Windows
mkdir tools
curl -L -o tools/tailwindcss.exe https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-windows-x64.exe

# Linux
curl -L -o tools/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v3.4.17/tailwindcss-linux-x64
chmod +x tools/tailwindcss
```

**Build de produção:**

```bash
tools/tailwindcss.exe -i app/static/src/input.css -o app/static/css/tailwind.css --minify
```

**Modo watch (desenvolvimento):**

```bash
tools/tailwindcss.exe -i app/static/src/input.css -o app/static/css/tailwind.css --watch
```

Sem Node.js, sem `npm install` — o binário standalone (39MB) já inclui PostCSS, autoprefixer e os plugins `@tailwindcss/forms` e `@tailwindcss/container-queries`.

---

## Estrutura do Projeto

```
projetoV1/
├── app/
│   ├── __init__.py             # App Factory, extensões, blueprints, CSP, migrate
│   ├── commands.py             # CLI commands (Flask)
│   ├── emailer.py              # Helper de e-mail assíncrono
│   ├── models/
│   │   ├── user.py             # User + flask-login loader
│   │   ├── product.py          # Product, ProductHistory, UniqueConstraint
│   │   ├── pricing.py          # PricingHistory
│   │   ├── custo_fixo.py       # CustoFixo + history + pagamentos
│   │   ├── notification_*.py   # Settings, recipients, log de notificações
│   │   └── amazon_*.py         # Credentials (criptografados), orders, inventory, finances
│   ├── auth/                   # register, login, logout, reset, confirm
│   ├── main/                   # index, menu (10 tools), dashboard (KPIs)
│   ├── precificacao/           # Simulador FBA + histórico
│   ├── produtos/               # CRUD produtos + audit trail
│   ├── settings/               # Perfil, troca de senha (com confirmação)
│   ├── financeiro/             # Custos fixos + alertas
│   │   ├── routes.py
│   │   └── alerts_custos_fixos.py
│   ├── integrations/amazon/    # SP-API: orders, inventory, finances, SKU links
│   ├── services/               # profit_calc, audit_custos_fixos
│   ├── utils/                  # crypto (Fernet)
│   ├── static/                 # CSS/JS (Tailwind buildado, JS modular do financeiro)
│   └── templates/              # Jinja2 (base, menu, dashboard, financeiro/, amazon/, emails/)
├── migrations/                 # Alembic (9 versions)
├── scripts/send_alerts.bat     # Job de envio de alertas
├── tools/tailwindcss.exe       # CLI standalone (gitignored, baixar via README)
├── config.py                   # DevelopmentConfig, ProductionConfig
├── tailwind.config.js
├── run.py                      # Entry point
├── requirements.txt
└── docs/screenshots/
```

---

## Variáveis de Ambiente — Referência Completa

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `SECRET_KEY` | Sim | Chave para assinar sessões e tokens. Em produção, ausência levanta `RuntimeError`. |
| `DATABASE_URL` | Sim | URI PostgreSQL completa (`postgresql://...`). Supabase usa porta 6543 (pooler). |
| `CREDENTIALS_ENCRYPTION_KEY` | Em prod | Chave Fernet para criptografar tokens Amazon. Gere com `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Obrigatória em produção. |
| `APP_ENV` / `FLASK_ENV` | Não | `development` (padrão) ou `production`. |
| `REDIS_URL` | Não | Storage do rate limiter em produção. Sem isso, cai para in-memory. |
| `MAIL_SERVER` | Para e-mail | Ex: `smtp.gmail.com` |
| `MAIL_PORT` | Para e-mail | Ex: `587` (TLS) |
| `MAIL_USE_TLS` | Para e-mail | `True` para Gmail |
| `MAIL_USERNAME` | Para e-mail | Endereço Gmail |
| `MAIL_PASSWORD` | Para e-mail | App Password de 16 dígitos |
| `MAIL_DEFAULT_SENDER` | Não | Remetente exibido. Se omitido, usa `MAIL_USERNAME`. |

---

## Licença

Projeto de portfólio. Todos os direitos reservados.
