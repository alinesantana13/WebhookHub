# WebhookHub

Plataforma SaaS multi-tenant para recebimento, processamento e entrega confiável de
webhooks. O projeto está sendo desenvolvido incrementalmente como demonstração de
engenharia backend Python, arquitetura orientada a eventos e operação em produção.

## Estado atual

Entrega 1 — fundação do backend:

- aplicação FastAPI com configuração tipada;
- endpoints `GET /health` e `GET /ready`;
- propagação segura de `X-Request-ID`;
- testes, Ruff, MyPy e meta mínima de 80% de cobertura;
- imagens e serviços locais para API, PostgreSQL, Redis e Kafka;
- pipeline inicial de qualidade e build no GitHub Actions.

Persistência, autenticação, mensageria e frontend entram nas próximas entregas. Neste
momento, `/ready` confirma somente que o processo HTTP iniciou; as verificações reais de
PostgreSQL, Redis e Kafka serão adicionadas junto com os respectivos adaptadores.

## Requisitos

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

1. persistência assíncrona com PostgreSQL, SQLAlchemy 2 e Alembic;
2. identidade, sessões rotativas e RBAC;
3. aplicações, API Keys e endpoints protegidos contra SSRF;
4. ingestão idempotente e Transactional Outbox;
5. Kafka, workers, entrega HTTP, retry e DLQ;
6. observabilidade e frontend administrativo.
