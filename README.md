# WebhookHub

Plataforma SaaS multi-tenant para recebimento, processamento e entrega confiável de
webhooks. O projeto está sendo desenvolvido incrementalmente como demonstração de
engenharia backend Python, arquitetura orientada a eventos e operação em produção.

## Estado atual

Entregas 1 e 2 — fundação do backend e identidade:

- aplicação FastAPI com configuração tipada;
- endpoints `GET /health` e `GET /ready`, com readiness real do PostgreSQL;
- SQLAlchemy 2 assíncrono, `asyncpg` e Alembic;
- cadastro multi-tenant com usuário, organização e vínculo de proprietário;
- login com access token JWT e refresh token rotativo armazenado como hash;
- detecção de reutilização de refresh token e RBAC por organização;
- propagação segura de `X-Request-ID`;
- testes, Ruff, MyPy e meta mínima de 80% de cobertura;
- imagens e serviços locais para API, PostgreSQL, Redis e Kafka;
- pipeline inicial de qualidade e build no GitHub Actions.

Mensageria e frontend entram nas próximas entregas. O endpoint `/ready`
já verifica o PostgreSQL; Redis e Kafka serão incluídos quando seus adaptadores forem
implementados.

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
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini check
```

O primeiro comando aplica migrations; o segundo detecta divergências entre os models e
o schema. Ainda não há tabelas de domínio: a primeira migration será criada junto das
entidades de identidade e organizações, evitando schema sem comportamento associado.

Para incluir o teste de integração local na suíte:

```powershell
$env:WEBHOOKHUB_TEST_POSTGRES_DSN = "postgresql+asyncpg://webhookhub:webhookhub@localhost:5432/webhookhub"
uv run --project backend pytest backend/tests
```

O arquivo `backend/uv.lock` deve ser versionado. O CI e a imagem Docker usam `--frozen`,
portanto falham se o manifesto e o lockfile estiverem fora de sincronia. O `pip` não faz
parte do fluxo de desenvolvimento, build ou CI do projeto.

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

1. aplicações, API Keys e endpoints protegidos contra SSRF;
2. ingestão idempotente e Transactional Outbox;
3. Kafka, workers, entrega HTTP, retry e DLQ;
4. observabilidade e frontend administrativo.
