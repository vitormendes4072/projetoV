# Avaliação Técnica do Portfólio — VEntregaz / Marketplace Manager

> Avaliação realizada em 2026-05-19 por análise estática completa do repositório.
> Critério: recrutador técnico avaliando para posição de desenvolvedor back-end / full-stack.

---

## Nota Geral: **6,2 / 10**

Projeto funcional, com escopo real e integrações não-triviais. Demonstra capacidade técnica acima da média de portfólios júnior. Perde pontos por problemas de performance visíveis, cobertura de testes parcial, e ausência de algumas práticas que diferenciam projetos de pleno/sênior.

---

## 5 Maiores Pontos Fortes

**1. Integração real com API externa complexa (Amazon SP-API)**
Implementar OAuth/LWA, criptografia de credenciais com Fernet, sync assíncrono via RQ, paginação de resultados e tratamento de erros de API é o que separa projetos de portfólio de projetos reais. A maioria dos candidatos júnior nunca chegou perto disso.

**2. Arquitetura escalável e limpa (App Factory + Blueprints + Service Layer)**
Separação correta entre rotas, serviços e modelos. Uso de App Factory permite múltiplas configurações de ambiente sem gambiarra. Blueprints por domínio (`auth`, `produtos`, `financeiro`, `integrations/amazon`, `api`) demonstra entendimento de separação de responsabilidades.

**3. Segurança não é afterthought**
Flask-Talisman com CSP, rate limiting com Flask-Limiter, criptografia das credenciais Amazon (não apenas hashing), validação com Marshmallow nos endpoints API, cookie seguro nas configurações de produção. Candidatos que pensam em segurança desde o design são raros.

**4. Jobs assíncronos com RQ + Redis**
Em vez de bloquear a thread do servidor com sync lento da Amazon, o projeto enfileira jobs e retorna 202 + job_id imediatamente. O cliente faz polling. Esse padrão é usado em produção em empresas reais e demonstra compreensão de sistemas distribuídos.

**5. Suite de testes com cobertura acima de 60%**
169 testes, 64% de cobertura, todos passando. A estratégia de mock (patch do módulo `db` ao invés de patchear a classe Model) está correta para SQLAlchemy 2.0. Presença de testes de integração (conftest com banco real SQLite) ao lado de testes unitários com mock demonstra maturidade.

---

## 5 Maiores Problemas

**1. N+1 query no dashboard (crítico para performance)**
`app/main/routes.py` carrega produtos do usuário e depois, para cada produto, executa queries individuais para calcular preço/lucratividade. Com 50 produtos = 51 queries por requisição. Sem profiling isso nunca foi detectado. Em produção com carga real isso vai causar timeout ou lentidão perceptível.

**2. Ausência de índices em colunas críticas de filtragem**
`user_id` em todas as tabelas principais (PricingHistory, CustoFixo, AmazonOrder, etc.) é filtrado em praticamente toda query, mas nenhuma migration adiciona `Index('ix_tabela_user_id', 'user_id')`. Com volume de dados isso degrada de O(log n) para O(n) full-scan.

**3. Cobertura zero nos módulos de maior risco**
`app/integrations/amazon/service.py`, `app/integrations/amazon/profit_service.py`, `app/financeiro/alerts_custos_fixos.py` — os módulos com lógica de negócio mais complexa — têm cobertura próxima de zero. Os testes existentes cobrem majoritariamente as rotas HTTP, não a lógica central.

**4. Endpoint de desenvolvimento exposto sem proteção de ambiente**
`app/integrations/amazon/routes_dev.py` existe e é registrado em todos os ambientes. Endpoints de debug (`/sync_full_debug`, rotas dev) deveriam ser registrados apenas quando `app.config["DEBUG"] is True`. Em produção isso é uma superfície de ataque desnecessária.

**5. Falta de paginação/limite em queries de listagem de dados Amazon**
`routes_orders.py` carrega todos os pedidos do usuário sem `LIMIT`. `routes_inventory.py` idem. Se o usuário tiver meses de histórico, uma única requisição pode retornar milhares de registros, carregando tudo na memória antes de renderizar o template.

---

## Avaliação por Dimensão

### 1. Proposta e Problema Resolvido — 7,5 / 10

**Nicho claro:** ferramenta de gestão para vendedores brasileiros no Marketplace Amazon, integrando dados de pedidos, financeiro, precificação e custos fixos em um painel único.

**Diferencial real:** a maioria das ferramentas similares no mercado não tem a integração SP-API completa (sync de pedidos + eventos financeiros + inventário) combinada com precificação brasileira (regime tributário, impostos, custo fixo por unidade). O problema existe, o produto teria usuários reais.

**Limitação:** falta de documentação do "porquê" do produto. Um recrutador não consegue entender o valor sem ler o código. README está ausente ou insuficiente.

---

### 2. UX / Experiência do Usuário — 5,0 / 10

**Positivo:**
- Feedback visual presente (flash messages com Bootstrap alerts)
- Modais para ações destrutivas (evita confirmação de página inteira)
- Página 404 personalizada com identidade visual

**Negativo:**
- Sem loading state quando jobs assíncronos são enfileirados — o usuário clica em "sincronizar" e não sabe se algo aconteceu
- Sem indicador de progresso para sync da Amazon (que pode demorar 30-60s)
- Layout não testado para mobile — Bootstrap está presente mas sem viewport responsivo verificado nos templates críticos
- Formulários com erros de validação precisam ser verificados para garantir que reabrem o modal correto (lógica de UX frágil implementada com `account_form.current_password.errors.append(...)`)

---

### 3. Funcionalidades Implementadas — 7,0 / 10

**Implementado e funcional:**
- Autenticação completa (register, login, logout, confirmação de email, troca de email com token)
- Gestão de produtos com precificação (markup, impostos, custo fixo por unidade)
- Sync de pedidos Amazon (async via RQ)
- Sync de eventos financeiros Amazon
- Sync de inventário Amazon
- Análise de lucratividade por pedido
- Custos fixos com pagamentos mensais e histórico
- Alertas por email (toggle, destinatários, scheduler)
- Relatórios com exportação PDF
- REST API documentada com OpenAPI/Swagger (Flask-Smorest)
- Configurações fiscais (regime tributário, alíquota padrão)

**Incompleto / problemático:**
- `routes_dev.py` tem endpoints claramente de desenvolvimento que não deveriam estar em produção
- `sync_orders_only` e `sync_items_batch` são rotas síncronas para operações potencialmente lentas — inconsistência de design
- Sem paginação nos endpoints de listagem da API REST (retorna tudo de uma vez)

---

### 4. Qualidade Técnica do Código — 6,0 / 10

**Positivo:**
- App Factory pattern correto
- Configuração por ambiente (Config/DevelopmentConfig/TestingConfig/ProductionConfig) sem gambiarras
- Service layer separado das rotas (`profit_service.py`, `alerts_custos_fixos.py`, `service.py`)
- SQLAlchemy 2.0 style em 100% das queries (Legacy Query API completamente eliminado)
- Migrations com Flask-Migrate

**Negativo:**
- `app/main/routes.py` ainda mistura lógica de negócio com rota (N+1 + cálculos inline)
- Algumas rotas têm mais de 80 linhas com múltiplos `if/else` aninhados (routes_custos.py)
- Sem tipagem estática (type hints) — não é obrigatório em Flask, mas denota o nível do código
- `from app.integrations.amazon.utils import parse_iso_dt, to_sp` importado dentro de loop em `routes_sync.py` (mau hábito)
- Comentários desnecessários do tipo "# DEBUG: Mostra no terminal" em produção

---

### 5. Banco de Dados / ORM — 6,5 / 10

**Positivo:**
- 16 entidades bem modeladas com relacionamentos `ForeignKey` e `relationship()` corretos
- Uso de `lazy="select"` (SQLAlchemy 2.0 compatível) ao invés de `lazy="dynamic"` depreciado
- `__table_args__` com `schema="public"` nas tabelas Amazon (separação de schema)
- Migrations versionadas com Alembic via Flask-Migrate
- Relacionamentos bidirecionais com `back_populates` onde necessário

**Negativo:**
- Ausência de `Index` explícito em `user_id` nas tabelas principais — crítico para performance
- Ausência de `Index` em `amazon_order_id` (coluna de join frequente)
- Sem constraints `UniqueConstraint` em pares que deveriam ser únicos (ex: `user_id + amazon_order_id`)
- `raw_json = db.Column(db.JSON)` sem documentação de schema — dificulta manutenção

---

### 6. Segurança — 7,0 / 10

**Positivo:**
- Flask-Talisman com Content-Security-Policy configurado
- Rate limiting nos endpoints de autenticação (Flask-Limiter)
- Credenciais Amazon criptografadas com Fernet (não apenas hashadas)
- `SECRET_KEY` sem fallback inseguro em produção (corrigido neste projeto)
- Validação de input com Marshmallow nos endpoints da API REST
- `WTForms` com CSRF em formulários HTML
- Multi-tenancy: todas as queries filtram por `user_id=current_user.id`

**Negativo:**
- Endpoints de dev expostos em produção (ver problema #4)
- Sem auditoria de acesso (quem acessou o quê, quando) — presente em custos fixos (`CustoFixoHistory`) mas não no resto
- Sem proteção contra enumeração de usuários no endpoint de registro (retorna erro diferente se email já existe)

---

### 7. Performance — 4,0 / 10

Esta é a dimensão mais fraca. Um recrutador técnico que perguntar "como você garante que o dashboard carrega rápido com 1000 produtos?" não vai receber uma boa resposta com o código atual.

**Problemas:**
- N+1 no dashboard (crítico)
- Zero caching (sem Flask-Caching, sem Redis cache)
- Sem lazy loading de JavaScript ou paginação incremental nas listagens
- `sync_orders_only` executa queries individuais por pedido em loop síncrono
- Relatório PDF gera documento inteiro em memória antes de enviar resposta

**Positivo isolado:**
- Jobs assíncronos com RQ para operações lentas (sync Amazon) — esse padrão é correto e atenua o problema nos endpoints de sync

---

### 8. Design / Frontend — 5,0 / 10

**Positivo:**
- Bootstrap 5 para responsividade base
- Componentes consistentes (cards, modais, badges)
- Ícones com Bootstrap Icons
- Separação de templates por módulo (`templates/amazon/`, `templates/financeiro/`, etc.)

**Negativo:**
- Sem identidade visual própria — poderia ser qualquer aplicação Bootstrap
- Sem dark mode ou customização de tema
- JavaScript inline nos templates (misturado com HTML) ao invés de arquivos `.js` separados
- Sem feedback de loading (spinners) para operações assíncronas
- 21 templates sem componentes reutilizáveis (Jinja2 macros) — código HTML repetido

---

### 9. Potencial para Portfólio / LinkedIn — 7,5 / 10

**Por que vale mostrar:**
- Integração com API externa real (Amazon SP-API) com autenticação OAuth — diferencial concreto
- Jobs assíncronos com Redis/RQ — demonstra conhecimento além de CRUD
- API REST documentada com OpenAPI/Swagger — detalhe que poucos portfólios têm
- Suite de testes real (169 testes, 64% cobertura) — raríssimo em portfólios
- Problema de negócio real (não é "to-do list" ou "blog")

**Como posicionar:**
- Para vagas de back-end Python/Flask: 8/10
- Para vagas de full-stack júnior a pleno: 7/10
- Para vagas sênior: não é suficiente sozinho (falta escala, falta observabilidade, falta containerização completa)

**O que vai ser perguntado em entrevista:**
- "Como você resolveria o N+1 no dashboard?" (precisa ter resposta)
- "Como você escalaria isso para múltiplos usuários simultâneos?" (precisa ter resposta)
- "Por que escolheu Flask ao invés de FastAPI/Django?" (precisa ter resposta)

---

### 10. Roadmap de Melhorias — Próximos Passos Objetivos

Ordenados por impacto vs. esforço (alto impacto primeiro):

**Curto prazo (1-2 semanas) — corrigem falhas críticas:**

1. **Corrigir N+1 no dashboard** — usar `db.session.scalars(db.select(PricingHistory).where(...).options(joinedload(...)))` ou reescrever a query com `join` + `group_by` para calcular tudo em uma única query SQL.

2. **Adicionar índices nas migrations** — uma migration Alembic que adiciona `Index('ix_pricing_history_user_id', 'user_id')` em todas as tabelas principais. 30 minutos de trabalho, impacto de performance em produção.

3. **Desabilitar rotas de dev fora do modo debug** — no `__init__.py`, registrar `routes_dev` apenas se `app.config["DEBUG"]`.

4. **Adicionar paginação nas listagens Amazon** — `db.paginate(db.select(AmazonOrder)..., page=page, per_page=50)` nas rotas que retornam listas sem limite.

**Médio prazo (2-4 semanas) — elevam o nível técnico:**

5. **Aumentar cobertura dos módulos críticos** — escrever testes unitários para `profit_service.py` e `alerts_custos_fixos.py`. Estes são os módulos com mais lógica de negócio e zero cobertura.

6. **Adicionar indicador de progresso para jobs** — o frontend já enfileira e recebe `job_id`. Implementar polling com JavaScript e exibir spinner/barra de progresso enquanto o job não termina.

7. **Type hints nos módulos de serviço** — `def compute_order_profit(conn: AmazonConnection, order_id: str) -> dict[str, Any]:` melhora legibilidade e permite `mypy`.

8. **README profissional** — arquitetura, como rodar localmente, variáveis de ambiente necessárias, print de telas. É a primeira coisa que um recrutador vê.

**Longo prazo (1-2 meses) — transformam o projeto:**

9. **Containerização completa com Docker Compose** — `docker-compose.yml` com Flask + PostgreSQL + Redis + RQ worker. Permite `docker compose up` e o projeto roda. Muito valorizado por recrutadores.

10. **Observabilidade básica** — logging estruturado (JSON logs com `python-json-logger`) e um endpoint `/health` com status do banco e do Redis. Demonstra mentalidade de produção.

---

## Descrição Melhorada para Portfólio

**Versão atual (presumida):** _"Sistema de gestão para vendedores Amazon"_

**Versão recomendada:**

> **VEntregaz — Plataforma de Gestão para Vendedores Amazon Brasil**
>
> Aplicação web full-stack desenvolvida em Python/Flask para gestão operacional e financeira de vendedores no marketplace Amazon Brasil. Integra diretamente com a Amazon SP-API via OAuth/LWA para sincronização automática de pedidos, itens, eventos financeiros e inventário.
>
> **Stack:** Python 3.11 · Flask 3.1 · SQLAlchemy 2.0 · PostgreSQL · Redis · RQ · Docker
>
> **Destaques técnicos:**
> - Sync assíncrono de dados Amazon via Redis Queue (RQ) com polling de status em tempo real
> - Criptografia de credenciais OAuth com Fernet (sem exposição de tokens em texto plano)
> - REST API documentada com OpenAPI 3.0 / Swagger UI (Flask-Smorest + Marshmallow)
> - 169 testes automatizados com 64% de cobertura (pytest + SQLite in-memory)
> - Segurança: CSP headers via Flask-Talisman, rate limiting, CSRF protection, multi-tenancy
> - Módulo de precificação com cálculo de margem, impostos e custo fixo por unidade vendida
> - Sistema de alertas por email com agendamento e gestão de destinatários

---

## Resumo Executivo

O projeto demonstra que o desenvolvedor sabe construir aplicações web reais — não tutoriais. A integração com Amazon SP-API, a arquitetura com App Factory e Blueprints, os jobs assíncronos e a preocupação com segurança colocam este portfólio acima da média.

Os problemas encontrados (N+1, ausência de índices, cobertura parcial nos módulos críticos) não são bloqueadores para aprovação em vagas júnior a pleno, mas serão perguntados em entrevistas técnicas. O candidato precisa conhecê-los e ter resposta sobre como resolveria.

Para vagas sênior, o projeto por si só não é suficiente — precisaria de containerização completa, observabilidade, e demonstração de decisões de escala. Para o nível atual, é um portfólio honesto e relevante.

**Nota final: 6,2 / 10**
