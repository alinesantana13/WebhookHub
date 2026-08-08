# WebhookHub

Plataforma SaaS multi-tenant para recebimento, processamento e entrega confiável de
webhooks. O projeto reúne uma API e workers em Python com um painel operacional em
React e TypeScript.

## Estado atual

Entregas 1 a 7 — fundação, identidade, aplicações, ingestão, entrega e operação:

- aplicação FastAPI com configuração tipada;
- endpoints `GET /health` e `GET /ready`, com readiness real do PostgreSQL;
- SQLAlchemy 2 assíncrono, `asyncpg` e Alembic;
- cadastro multi-tenant com usuário, organização e vínculo de proprietário;
- login com access token JWT e refresh token rotativo armazenado como hash;
- detecção de reutilização de refresh token e RBAC por organização;
- aplicações por organização, API Keys armazenadas somente como hash e revogação;
- endpoints de destino com proteção contra SSRF (DNS e endereços não públicos);
- ingestão autenticada por API Key, idempotência por aplicação e Transactional Outbox;
- relay da outbox para Kafka e consumo em grupo por workers;
- entrega HTTP com proteção contra SSRF no momento do envio, timeout e redirects desativados;
- retries exponenciais duráveis e Dead Letter Queue no Kafka após o limite de tentativas;
- assinaturas HMAC SHA-256 por endpoint, com timestamp e segredo exibido uma única vez;
- replay manual de entregas e alertas operacionais persistentes com reconhecimento;
- frontend React em `http://localhost:5173`, com login, visão operacional, criação e
  exclusão de aplicações, gestão de chaves e endpoints, eventos, entregas e alertas;
- consulta de eventos e estado de suas entregas pelo painel;
- métricas Prometheus em `/metrics` e logs HTTP estruturados com correlação por request ID;
- propagação segura de `X-Request-ID`;
- testes, Ruff, MyPy e meta mínima de 80% de cobertura;
- imagens e serviços locais para API, PostgreSQL, Redis e Kafka;
- pipeline inicial de qualidade e build no GitHub Actions.

O endpoint `/ready` verifica PostgreSQL, Redis e
Kafka (testes isolados verificam apenas o PostgreSQL).

## Requisitos

- Python 3.13 ou 3.14;
- `uv` 0.11 ou superior;
- Docker 27 ou superior com Docker Compose;
- Node.js 22 ou superior e npm, para executar o frontend fora do Docker;
- GNU Make opcional no Windows.

## Arquitetura

```text
frontend/                  SPA React + TypeScript + Vite
backend/                   API FastAPI, domínio e workers
deploy/docker/             imagens e configuração Nginx
PostgreSQL                 dados transacionais
Kafka                      fila de eventos e entregas
Redis                      infraestrutura de cache/readiness
```

O frontend chama a API por `/api`. No desenvolvimento, o Vite encaminha essas chamadas
para `http://localhost:8000`. No Docker, o Nginx encaminha `/api` para o serviço `api`.

## Execução local

### Backend

```powershell
uv sync --project backend --group dev
copy .env.example .env
uv run --project backend uvicorn webhookhub.main:app --reload
```

A API estará em `http://localhost:8000`; a documentação OpenAPI, em `/docs`.

### Frontend React

Em outro terminal:

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

O painel estará em `http://localhost:5173`. Consulte o
[`frontend/README.md`](frontend/README.md) para detalhes da interface e de seu fluxo de
desenvolvimento.

## Observabilidade

O endpoint `GET /metrics` expõe contadores e duração acumulada das requisições no
formato Prometheus. Configure `WEBHOOKHUB_METRICS_TOKEN` fora do ambiente local para
exigir `Authorization: Bearer <token>` na coleta. Os logs de acesso são emitidos como
JSON e incluem método, rota, status, duração e `request_id`.

## Execução com Docker

```powershell
copy .env.example .env
docker compose up --build
```

Com Docker Compose:

- frontend React: `http://localhost:5173`;
- API FastAPI: `http://localhost:8000`;
- Swagger: `http://localhost:8000/docs`.

## Qualidade e testes

```powershell
uv run --project backend ruff check backend
uv run --project backend ruff format --check backend
uv run --project backend mypy backend/src backend/tests
uv run --project backend pytest backend/tests
```

Frontend:

```powershell
cd frontend
npm run lint
npm run build
```

## Banco de dados e migrations

Com o PostgreSQL do Compose em execução:

```powershell
$env:WEBHOOKHUB_POSTGRES_DSN = "postgresql+asyncpg://webhookhub:webhookhub@localhost:5432/webhookhub"
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini check
```

O primeiro comando aplica migrations; o segundo detecta divergências entre os models e
o schema. Ao executar pelo PowerShell, o PostgreSQL publicado pelo Compose é acessado por
`localhost`. O hostname `postgres` configurado no `.env` é resolvido somente entre os
containers da rede do Compose.

Para incluir o teste de integração local na suíte:

```powershell
$env:WEBHOOKHUB_TEST_POSTGRES_DSN = "postgresql+asyncpg://webhookhub:webhookhub@localhost:5432/webhookhub"
uv run --project backend pytest backend/tests
```

O arquivo `backend/uv.lock` deve ser versionado. O CI e a imagem Docker usam `--frozen`,
portanto falham se o manifesto e o lockfile estiverem fora de sincronia. O `pip` não faz
parte do fluxo de desenvolvimento, build ou CI do projeto.

## Ingestão de webhooks

Envie um objeto JSON usando a API Key criada para a aplicação. A chave de idempotência
é limitada a 128 caracteres e identifica o evento dentro da aplicação:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://localhost:8000/applications/<application-id>/webhooks `
  -Headers @{ "X-API-Key" = "whk_..."; "Idempotency-Key" = "payment-123" } `
  -ContentType "application/json" `
  -Body '{"type":"payment.confirmed","payment_id":"123"}'
```

A gravação do evento e da mensagem em `outbox_messages` ocorre na mesma transação.
Repetir chave e conteúdo retorna o evento original; repetir a chave com outro conteúdo
retorna `409 Conflict`.

## Organização do projeto

```text
backend/                  API e futuros workers Python
  src/webhookhub/
    bootstrap/            composição e configuração
    shared/presentation/  recursos HTTP transversais
  tests/                  testes automatizados
frontend/                 painel React e cliente da API
  src/
    api.ts                autenticação e chamadas HTTP
    App.tsx               login e dashboard inicial
    types.ts              contratos TypeScript da API
deploy/docker/            imagens da aplicação
.github/workflows/        integração contínua
```

Documentação específica:

- [`backend/README.md`](backend/README.md): arquitetura e decisões do backend;
- [`frontend/README.md`](frontend/README.md): execução e estrutura do painel React.

Os módulos de negócio serão introduzidos quando receberem comportamento real, cada um
separado em `domain`, `application`, `infrastructure` e `presentation`.

## Assinaturas, replay e alertas

Cada endpoint recebe um `signing_secret` na criação, exibido apenas nessa resposta. As
entregas incluem `X-Webhook-Timestamp` e `X-Webhook-Signature`, calculada como HMAC
SHA-256 de `<timestamp>.<corpo JSON canônico>` e formatada como `v1=<hex>`.

Administradores podem reenfileirar uma entrega com
`POST /applications/{application_id}/deliveries/{delivery_id}/replay`. Falhas terminais
geram alertas consultáveis em `GET /applications/{application_id}/alerts`, que podem ser
reconhecidos pelo endpoint `POST .../alerts/{alert_id}/acknowledge`.

## Próximas entregas

1. adicionar detalhes de evento, replay e reconhecimento de alertas no novo painel;
2. incluir edição e ativação/desativação de endpoints;
3. retenção configurável, filtros avançados e exportação de auditoria.
