# WebhookHub

Plataforma SaaS multi-tenant para recebimento, processamento e entrega confiável de
webhooks. O projeto está sendo desenvolvido incrementalmente como demonstração de
engenharia backend Python, arquitetura orientada a eventos e operação em produção.

## Estado atual

Entregas 1 a 6 — fundação, identidade, aplicações, ingestão, entrega e operação:

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
- painel administrativo responsivo em `/admin/`, com gestão de aplicações, chaves e endpoints;
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
- GNU Make opcional no Windows.

## Execução local com Python

```powershell
uv sync --project backend --group dev
copy .env.example .env
uv run --project backend uvicorn webhookhub.main:app --reload
```

A API estará em `http://localhost:8000`; a documentação OpenAPI, em `/docs`.
O painel administrativo estará em `http://localhost:8000/admin/`.

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

## Qualidade e testes

```powershell
uv run --project backend ruff check backend
uv run --project backend ruff format --check backend
uv run --project backend mypy backend/src backend/tests
uv run --project backend pytest backend/tests
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

## Organização inicial

```text
backend/                  API e futuros workers Python
  src/webhookhub/
    bootstrap/            composição e configuração
    shared/presentation/  recursos HTTP transversais
  tests/                  testes automatizados
deploy/docker/            imagens da aplicação
.github/workflows/        integração contínua
```

Os módulos de negócio serão introduzidos quando receberem comportamento real, cada um
separado em `domain`, `application`, `infrastructure` e `presentation`.

## Próximas entregas

1. assinaturas HMAC, replay manual e alertas operacionais.
