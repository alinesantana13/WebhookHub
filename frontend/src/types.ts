export type Organization = {
  id: string
  name: string
  slug: string
  role: 'owner' | 'admin' | 'member'
}

export type CurrentUser = {
  id: string
  email: string
  name: string
  organizations: Organization[]
}

export type Application = {
  id: string
  organization_id: string
  name: string
  created_at: string
}

export type Endpoint = {
  id: string
  application_id: string
  name: string
  url: string
  enabled: boolean
  created_at: string
}

export type ApiKey = {
  id: string
  name: string
  prefix: string
  created_at: string
  last_used_at: string | null
  revoked_at: string | null
}

export type CreatedApiKey = ApiKey & { key: string }

export type CreatedEndpoint = Endpoint & { signing_secret: string }

export type Delivery = {
  id: string
  endpoint_id: string
  endpoint_name: string | null
  endpoint_url: string | null
  status: 'pending' | 'succeeded' | 'dead'
  attempt_count: number
  last_status_code: number | null
  last_error: string | null
  delivered_at: string | null
}

export type WebhookEvent = {
  id: string
  idempotency_key: string
  payload: Record<string, unknown>
  received_at: string
  deliveries: Delivery[]
}

export type Alert = {
  id: string
  delivery_id: string
  event_id: string | null
  event_idempotency_key: string | null
  endpoint_id: string | null
  endpoint_name: string | null
  endpoint_url: string | null
  message: string
  created_at: string
  acknowledged_at: string | null
}
