# Frontend do WebhookHub

Interface operacional construída com React, TypeScript e Vite. Ela consome a API do
WebhookHub e permite administrar aplicações, chaves de API, endpoints, eventos,
entregas e alertas.

## Requisitos

- Node.js 22 ou superior;
- npm;
- API do WebhookHub disponível em `http://localhost:8000`.

## Executar em desenvolvimento

```powershell
cd frontend
copy .env.example .env
npm install
npm run dev
```

Acesse `http://localhost:5173`. Durante o desenvolvimento, chamadas para `/api` são
encaminhadas pelo Vite para `http://localhost:8000`.

## Variáveis de ambiente

`VITE_API_URL` define o prefixo usado pelo cliente HTTP. O valor local recomendado é:

```env
VITE_API_URL=/api
```

## Validação

```powershell
npm run lint
npm run build
```

O build de produção é gerado em `frontend/dist/`, que não deve ser versionado.

## Estrutura principal

```text
src/
  App.tsx          telas, navegação e ações do painel
  api.ts           autenticação e integração com a API
  types.ts         contratos TypeScript
  styles.css       estilos gerais e layout
  actions.css      formulários, diálogos e ações
  navigation.css   navegação e responsividade
  menu.css         estados visuais do menu lateral
```

No Docker Compose, o frontend é servido pelo Nginx em `http://localhost:5173`, e o
próprio Nginx encaminha `/api` para o container da API.
