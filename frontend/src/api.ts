import type {
  Alert,
  ApiKey,
  Application,
  CreatedApiKey,
  CreatedEndpoint,
  CurrentUser,
  Endpoint,
  WebhookEvent,
} from './types'

const API_URL = import.meta.env.VITE_API_URL ?? '/api'
const TOKEN_KEY = 'webhookhub_access_token'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message)
  }
}

export const auth = {
  token: () => sessionStorage.getItem(TOKEN_KEY),
  save: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = auth.token()
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(body.detail ?? 'Não foi possível concluir a operação.', response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  login: (email: string, password: string) =>
    request<{ access_token: string; refresh_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  me: () => request<CurrentUser>('/auth/me'),
  applications: (organizationId: string) =>
    request<Application[]>(`/organizations/${organizationId}/applications`),
  createApplication: (organizationId: string, name: string) =>
    request<Application>(`/organizations/${organizationId}/applications`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  deleteApplication: (applicationId: string) =>
    request<void>(`/applications/${applicationId}`, { method: 'DELETE' }),
  apiKeys: (applicationId: string) =>
    request<ApiKey[]>(`/applications/${applicationId}/api-keys`),
  createApiKey: (applicationId: string, name: string) =>
    request<CreatedApiKey>(`/applications/${applicationId}/api-keys`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  revokeApiKey: (applicationId: string, keyId: string) =>
    request<void>(`/applications/${applicationId}/api-keys/${keyId}/revoke`, {
      method: 'POST',
    }),
  deleteApiKey: (applicationId: string, keyId: string) =>
    request<void>(`/applications/${applicationId}/api-keys/${keyId}`, { method: 'DELETE' }),
  endpoints: (applicationId: string) =>
    request<Endpoint[]>(`/applications/${applicationId}/endpoints`),
  createEndpoint: (applicationId: string, name: string, url: string) =>
    request<CreatedEndpoint>(`/applications/${applicationId}/endpoints`, {
      method: 'POST',
      body: JSON.stringify({ name, url }),
    }),
  deleteEndpoint: (applicationId: string, endpointId: string) =>
    request<void>(`/applications/${applicationId}/endpoints/${endpointId}`, {
      method: 'DELETE',
    }),
  events: (applicationId: string) =>
    request<WebhookEvent[]>(`/applications/${applicationId}/events`),
  alerts: (applicationId: string) =>
    request<Alert[]>(`/applications/${applicationId}/alerts`),
  acknowledgeAlert: (applicationId: string, alertId: string) =>
    request<Alert>(`/applications/${applicationId}/alerts/${alertId}/acknowledge`, {
      method: 'POST',
    }),
}
