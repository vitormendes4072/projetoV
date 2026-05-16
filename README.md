# Marketplace Manager

SaaS web application for Amazon marketplace sellers to manage products, simulate pricing margins, and track inventory — built with Flask and PostgreSQL.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-3.1.1-000000?style=flat&logo=flask&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Supabase-3ECF8E?style=flat&logo=supabase&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.x-38B2AC?style=flat&logo=tailwind-css&logoColor=white)

---

## Screenshots

| Login | Menu Principal |
|-------|----------------|
| ![Login](docs/screenshots/login.jpeg) | ![Menu](docs/screenshots/menu.jpeg) |

| Dashboard | Calculadora de Preços |
|-----------|----------------------|
| ![Dashboard](docs/screenshots/dashboard.jpeg) | ![Calculator](docs/screenshots/calculator.jpeg) |

| Gestão de Produtos |
|--------------------|
| ![Products](docs/screenshots/products.jpeg) |

---

## Funcionalidades

- **Autenticação completa** — registro com confirmação por e-mail, login com rate limiting (5 req/min), recuperação de senha com token JWT (30 min TTL)
- **Dashboard analítico** — KPIs em tempo real: total de produtos, simulações, margem média, ROI médio, alertas de estoque baixo e histórico de atividades
- **Calculadora de Preços** — simulação de lucro líquido com FBA fee, referral fee, imposto e marketing; persiste histórico por usuário
- **Gestão de Produtos** — CRUD completo com rastreio de SKU (ASIN opcional), controle de estoque e trilha de auditoria por produto
- **Multi-tenancy** — cada usuário vê apenas seus próprios dados; SKU único por usuário, não globalmente
- **Configurações de conta** — troca de senha com validação

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
- **Blueprint por domínio** — `auth`, `main`, `produtos`, `precificacao`, `settings` completamente desacoplados
- **E-mail assíncrono** — `Thread` em background evita bloquear o response enquanto o SMTP envia
- **Multi-tenancy por linha** — `UniqueConstraint('user_id', 'sku')` garante isolamento de SKU por conta sem vazar informação entre usuários
- **Audit trail** — `ProductHistory` registra toda alteração de preço, custo e estoque com timestamp e autor
- **Configuração por ambiente** — `DevelopmentConfig` / `ProductionConfig` via `FLASK_ENV`

### Banco de Dados

```
users
 ├── products (1:N, lazy='dynamic', cascade delete)
 │    └── product_history (1:N, cascade delete-orphan)
 └── pricing_history (1:N)
```

---

## Stack

| Camada | Tecnologia |
|--------|-----------|
| Framework | Flask 3.1.1 |
| ORM | Flask-SQLAlchemy 3.1.1 + SQLAlchemy 2.0 |
| Banco | PostgreSQL via Supabase |
| Auth | Flask-Login 0.6.3 |
| Formulários | Flask-WTF 1.2.2 + WTForms 3.2 |
| E-mail | Flask-Mail + Gmail SMTP |
| Segurança | Flask-Talisman (CSP/HTTPS) + Flask-Limiter |
| Tokens | itsdangerous 2.2 (URLSafeTimedSerializer) |
| Frontend | Tailwind CSS 3 via CDN |
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

O banco é criado automaticamente via `db.create_all()` na primeira execução.

---

## Estrutura do Projeto

```
projetoV1/
├── app/
│   ├── __init__.py          # App Factory, extensões, blueprints, CSP
│   ├── models/
│   │   ├── user.py          # User, hash de senha, flask-login loader
│   │   ├── product.py       # Product, ProductHistory, UniqueConstraint
│   │   └── pricing.py       # PricingHistory (inputs + outputs da simulação)
│   ├── auth/
│   │   ├── routes.py        # register, login, logout, reset, confirm
│   │   └── forms.py         # RegistrationForm, LoginForm, ResetPasswordForm
│   ├── main/
│   │   └── routes.py        # index, menu, dashboard (KPIs + queries)
│   ├── precificacao/
│   │   ├── routes.py        # /calculator GET/POST, histórico
│   │   └── forms.py         # PricingForm com NumberRange validators
│   ├── produtos/
│   │   ├── routes.py        # CRUD produtos, ProductHistory logging
│   │   └── forms.py         # ProductForm com validação SKU por usuário
│   └── settings/
│       ├── routes.py        # troca de senha, perfil
│       └── forms.py         # ChangePasswordForm
├── config.py                # DevelopmentConfig, ProductionConfig
├── run.py                   # Entry point
├── requirements.txt
└── docs/
    └── screenshots/
```

---

## Variáveis de Ambiente — Referência Completa

| Variável | Obrigatório | Descrição |
|----------|-------------|-----------|
| `SECRET_KEY` | Sim | Chave para assinar sessões e tokens. Use valor longo e aleatório em produção. |
| `DATABASE_URL` | Sim | URI PostgreSQL completa (`postgresql://...`). Supabase usa porta 6543 (pooler). |
| `FLASK_ENV` | Não | `development` (padrão) ou `production`. |
| `MAIL_SERVER` | Para e-mail | Ex: `smtp.gmail.com` |
| `MAIL_PORT` | Para e-mail | Ex: `587` (TLS) |
| `MAIL_USE_TLS` | Para e-mail | `True` para Gmail |
| `MAIL_USERNAME` | Para e-mail | Endereço Gmail |
| `MAIL_PASSWORD` | Para e-mail | App Password de 16 dígitos |
| `MAIL_DEFAULT_SENDER` | Não | Remetente exibido. Se omitido, usa `MAIL_USERNAME`. |

---

## Licença

Projeto de portfólio. Todos os direitos reservados.
