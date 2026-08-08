import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDot,
  Copy,
  KeyRound,
  LogOut,
  Plus,
  Radio,
  RefreshCw,
  Server,
  ShieldCheck,
  Trash2,
  Webhook,
  X,
} from 'lucide-react'
import { FormEvent, useEffect, useMemo, useState } from 'react'
import { api, ApiError, auth } from './api'
import type { Application, Delivery } from './types'

function Login({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const tokens = await api.login(email, password)
      auth.save(tokens.access_token)
      onAuthenticated()
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Não foi possível entrar.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="login-page">
      <section className="login-story">
        <a className="brand brand-light" href="/" aria-label="WebhookHub">
          <span className="brand-mark"><Webhook size={20} /></span>
          WebhookHub
        </a>
        <div className="story-copy">
          <p className="kicker">ENTREGAS SOB CONTROLE</p>
          <h1>Veja cada evento.<br />Entenda cada destino.</h1>
          <p>Um espaço operacional para acompanhar webhooks em tempo real, investigar falhas e manter suas integrações saudáveis.</p>
        </div>
        <div className="signal-card">
          <span className="live-dot" />
          <div><strong>Operação monitorada</strong><small>API, fila e workers conectados</small></div>
          <Activity size={18} />
        </div>
      </section>
      <section className="login-panel">
        <form className="login-form" onSubmit={submit}>
          <p className="kicker">ACESSO OPERACIONAL</p>
          <h2>Bem-vindo de volta</h2>
          <p className="form-intro">Entre com sua conta para acessar organizações e aplicações.</p>
          <label>E-mail<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="voce@empresa.com" autoComplete="email" required /></label>
          <label>Senha<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Sua senha" autoComplete="current-password" required /></label>
          {error && <p className="form-error">{error}</p>}
          <button className="primary-button login-button" disabled={loading}>{loading ? 'Entrando…' : 'Entrar'}<ArrowRight size={18} /></button>
          <p className="security-note"><ShieldCheck size={15} /> Sessão protegida por token de acesso</p>
        </form>
      </section>
    </main>
  )
}

function StatusPill({ delivery }: { delivery: Delivery }) {
  const label = delivery.status === 'succeeded' ? 'Entregue' : delivery.status === 'dead' ? 'Falhou' : 'Pendente'
  return <span className={`status-pill ${delivery.status}`}><CircleDot size={12} />{label}</span>
}

type DialogType = 'application' | 'api-key' | 'endpoint'
type ViewType = 'overview' | 'events' | 'endpoints' | 'alerts'

function CreateDialog({ type, busy, onClose, onSubmit }: { type: DialogType; busy: boolean; onClose: () => void; onSubmit: (name: string, url?: string) => Promise<void> }) {
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const labels = {
    application: ['Nova aplicação', 'Nome da aplicação'],
    'api-key': ['Nova chave de API', 'Nome da chave'],
    endpoint: ['Novo endpoint', 'Nome do endpoint'],
  }
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form className="modal" onSubmit={async (event) => { event.preventDefault(); await onSubmit(name, url) }} onMouseDown={(event) => event.stopPropagation()}>
    <div className="modal-heading"><div><p className="kicker">CONFIGURAÇÃO</p><h2>{labels[type][0]}</h2></div><button type="button" className="icon-button dark-icon" onClick={onClose} aria-label="Fechar"><X size={19} /></button></div>
    <label>{labels[type][1]}<input value={name} onChange={(event) => setName(event.target.value)} autoFocus required maxLength={120} /></label>
    {type === 'endpoint' && <label>URL pública<input type="url" value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://seu-dominio.com/webhook" required /></label>}
    <div className="modal-actions"><button type="button" className="ghost-button" onClick={onClose}>Cancelar</button><button className="primary-button" disabled={busy}>{busy ? 'Salvando…' : 'Criar'}</button></div>
  </form></div>
}

function SecretDialog({ title, value, onClose }: { title: string; value: string; onClose: () => void }) {
  return <div className="modal-backdrop"><section className="modal secret-modal"><div className="modal-heading"><div><p className="kicker">EXIBIÇÃO ÚNICA</p><h2>{title}</h2></div><button className="icon-button dark-icon" onClick={onClose} aria-label="Fechar"><X size={19} /></button></div><p>Copie agora. Por segurança, este valor não será exibido novamente.</p><div className="secret-value"><code>{value}</code><button className="icon-button dark-icon" onClick={() => navigator.clipboard.writeText(value)} title="Copiar"><Copy size={18} /></button></div><button className="primary-button" onClick={onClose}>Concluído</button></section></div>
}

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const queryClient = useQueryClient()
  const [organizationId, setOrganizationId] = useState('')
  const [applicationId, setApplicationId] = useState('')
  const [dialog, setDialog] = useState<DialogType | null>(null)
  const [secret, setSecret] = useState<{ title: string; value: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [activeView, setActiveView] = useState<ViewType>(() => {
    const value = window.location.hash.replace('#', '')
    return ['events', 'endpoints', 'alerts'].includes(value) ? value as ViewType : 'overview'
  })
  const me = useQuery({ queryKey: ['me'], queryFn: api.me })

  useEffect(() => {
    if (!organizationId && me.data?.organizations[0]) setOrganizationId(me.data.organizations[0].id)
  }, [me.data, organizationId])

  const applications = useQuery({
    queryKey: ['applications', organizationId],
    queryFn: () => api.applications(organizationId),
    enabled: Boolean(organizationId),
  })

  useEffect(() => {
    if (!applications.data?.some((item) => item.id === applicationId)) {
      setApplicationId(applications.data?.[0]?.id ?? '')
    }
  }, [applications.data, applicationId])

  const endpoints = useQuery({ queryKey: ['endpoints', applicationId], queryFn: () => api.endpoints(applicationId), enabled: Boolean(applicationId) })
  const keys = useQuery({ queryKey: ['api-keys', applicationId], queryFn: () => api.apiKeys(applicationId), enabled: Boolean(applicationId) })
  const events = useQuery({ queryKey: ['events', applicationId], queryFn: () => api.events(applicationId), enabled: Boolean(applicationId), refetchInterval: 15_000 })
  const alerts = useQuery({ queryKey: ['alerts', applicationId], queryFn: () => api.alerts(applicationId), enabled: Boolean(applicationId), refetchInterval: 15_000 })
  const selectedApp = applications.data?.find((item) => item.id === applicationId)
  const deliveries = useMemo(() => events.data?.flatMap((event) => event.deliveries) ?? [], [events.data])
  const successful = deliveries.filter((delivery) => delivery.status === 'succeeded').length
  const failed = deliveries.filter((delivery) => delivery.status === 'dead').length
  const successRate = deliveries.length ? Math.round((successful / deliveries.length) * 100) : 100
  const refreshing = events.isFetching || endpoints.isFetching || alerts.isFetching || keys.isFetching

  function changeView(view: ViewType) {
    setActiveView(view)
    window.history.replaceState(null, '', `#${view}`)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  async function refreshData() {
    setNotice('')
    await Promise.all([events.refetch(), endpoints.refetch(), alerts.refetch(), keys.refetch()])
    setNotice('Dados atualizados.')
  }

  async function acknowledgeAlert(alertId: string) {
    try {
      await api.acknowledgeAlert(applicationId, alertId)
      await queryClient.invalidateQueries({ queryKey: ['alerts', applicationId] })
    } catch (cause) { setNotice(cause instanceof ApiError ? cause.message : 'Falha ao reconhecer alerta.') }
  }

  async function createResource(name: string, url?: string) {
    setBusy(true)
    setNotice('')
    try {
      if (dialog === 'application') {
        const created = await api.createApplication(organizationId, name)
        await queryClient.invalidateQueries({ queryKey: ['applications', organizationId] })
        setApplicationId(created.id)
      } else if (dialog === 'api-key') {
        const created = await api.createApiKey(applicationId, name)
        await queryClient.invalidateQueries({ queryKey: ['api-keys', applicationId] })
        setSecret({ title: 'Chave de API criada', value: created.key })
      } else if (dialog === 'endpoint') {
        const created = await api.createEndpoint(applicationId, name, url ?? '')
        await queryClient.invalidateQueries({ queryKey: ['endpoints', applicationId] })
        setSecret({ title: 'Segredo de assinatura criado', value: created.signing_secret })
      }
      setDialog(null)
    } catch (cause) {
      setNotice(cause instanceof ApiError ? cause.message : 'Não foi possível concluir a operação.')
    } finally {
      setBusy(false)
    }
  }

  async function removeApplication() {
    if (!selectedApp || !confirm(`Excluir a aplicação "${selectedApp.name}" e todos os seus dados?`)) return
    try {
      await api.deleteApplication(selectedApp.id)
      setApplicationId('')
      await queryClient.invalidateQueries({ queryKey: ['applications', organizationId] })
      setNotice('Aplicação excluída.')
    } catch (cause) { setNotice(cause instanceof ApiError ? cause.message : 'Falha ao excluir aplicação.') }
  }

  async function revokeKey(keyId: string) {
    if (!confirm('Revogar esta chave? Ela deixará de autenticar novos webhooks.')) return
    try {
      await api.revokeApiKey(applicationId, keyId)
      await queryClient.invalidateQueries({ queryKey: ['api-keys', applicationId] })
    } catch (cause) { setNotice(cause instanceof ApiError ? cause.message : 'Falha ao revogar chave.') }
  }

  async function removeKey(keyId: string) {
    if (!confirm('Excluir permanentemente esta chave revogada?')) return
    try {
      await api.deleteApiKey(applicationId, keyId)
      await queryClient.invalidateQueries({ queryKey: ['api-keys', applicationId] })
    } catch (cause) { setNotice(cause instanceof ApiError ? cause.message : 'Falha ao excluir chave.') }
  }

  async function removeEndpoint(endpointId: string) {
    if (!confirm('Excluir este endpoint e seu histórico de entregas relacionado?')) return
    try {
      await api.deleteEndpoint(applicationId, endpointId)
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['endpoints', applicationId] }),
        queryClient.invalidateQueries({ queryKey: ['events', applicationId] }),
        queryClient.invalidateQueries({ queryKey: ['alerts', applicationId] }),
      ])
    } catch (cause) { setNotice(cause instanceof ApiError ? cause.message : 'Falha ao excluir endpoint.') }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand brand-light" href="/"><span className="brand-mark"><Webhook size={20} /></span>WebhookHub</a>
        <nav>
          <button className={`nav-item ${activeView === 'overview' ? 'active' : ''}`} onClick={() => changeView('overview')}><Activity size={18} />Visão geral</button>
          <button className={`nav-item ${activeView === 'events' ? 'active' : ''}`} onClick={() => changeView('events')}><Radio size={18} />Eventos</button>
          <button className={`nav-item ${activeView === 'endpoints' ? 'active' : ''}`} onClick={() => changeView('endpoints')}><Server size={18} />Endpoints</button>
          <button className={`nav-item ${activeView === 'alerts' ? 'active' : ''}`} onClick={() => changeView('alerts')}><AlertTriangle size={18} />Alertas</button>
        </nav>
        <div className="sidebar-footer">
          <div className="avatar">{me.data?.name?.slice(0, 2).toUpperCase() ?? 'WH'}</div>
          <div><strong>{me.data?.name ?? 'Carregando'}</strong><small>{me.data?.email}</small></div>
          <button className="icon-button" onClick={onLogout} title="Sair"><LogOut size={17} /></button>
        </div>
      </aside>
      <main className="workspace">
        <header className="topbar">
          <div><p className="kicker">CENTRAL DE OPERAÇÕES</p><h1>{selectedApp?.name ?? 'Suas aplicações'}</h1></div>
          <div className="topbar-actions"><div className="selectors">
            <label>Organização<select value={organizationId} onChange={(e) => setOrganizationId(e.target.value)}>{me.data?.organizations.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label>
            <label>Aplicação<select value={applicationId} onChange={(e) => setApplicationId(e.target.value)}>{applications.data?.map((app: Application) => <option key={app.id} value={app.id}>{app.name}</option>)}</select></label>
          </div><div className="action-bar"><button className="ghost-button" onClick={() => setDialog('application')}><Plus size={16} />Aplicação</button><button className="danger-button" onClick={removeApplication} disabled={!selectedApp}><Trash2 size={16} />Excluir aplicação</button></div></div>
        </header>

        {notice && <div className="notice"><span>{notice}</span><button className="icon-button dark-icon" onClick={() => setNotice('')}><X size={16} /></button></div>}

        {activeView === 'overview' && <section className="metrics-grid" id="overview">
          <article className="metric-card highlight"><span className="metric-icon"><CheckCircle2 /></span><div><small>Taxa de sucesso</small><strong>{successRate}%</strong><p>{successful} de {deliveries.length} entregas</p></div></article>
          <article className="metric-card"><span className="metric-icon"><Radio /></span><div><small>Eventos recentes</small><strong>{events.data?.length ?? 0}</strong><p>Últimos eventos recebidos</p></div></article>
          <article className="metric-card"><span className="metric-icon"><Server /></span><div><small>Destinos ativos</small><strong>{endpoints.data?.filter((item) => item.enabled).length ?? 0}</strong><p>Endpoints configurados</p></div></article>
          <article className="metric-card danger-metric"><span className="metric-icon"><AlertTriangle /></span><div><small>Falhas definitivas</small><strong>{failed}</strong><p>{alerts.data?.filter((item) => !item.acknowledged_at).length ?? 0} alertas abertos</p></div></article>
        </section>}

        <section className={`content-grid view-${activeView}`}>
          <article className="surface events-surface" id="events">
            <div className="section-heading"><div><p className="kicker">FLUXO RECENTE</p><h2>Entregas por evento</h2></div><button className={`refresh-button ${refreshing ? 'refreshing' : ''}`} onClick={refreshData} disabled={refreshing} title="Atualizar dados"><RefreshCw size={18} /></button></div>
            <div className="event-list">
              {events.isLoading && <p className="empty-state">Carregando eventos…</p>}
              {events.data?.map((event) => <div className="event-row" key={event.id}>
                <div className="event-main"><span className="event-symbol"><Webhook size={17} /></span><div><strong>{event.idempotency_key}</strong><small>{new Date(event.received_at).toLocaleString('pt-BR')}</small></div></div>
                <div className="delivery-list">{event.deliveries.map((delivery) => <div className="delivery-row" key={delivery.id}><div><strong>{delivery.endpoint_name ?? 'Endpoint'}</strong><small>{delivery.last_status_code ? `HTTP ${delivery.last_status_code}` : delivery.endpoint_url}</small></div><StatusPill delivery={delivery} /></div>)}</div>
              </div>)}
              {!events.isLoading && !events.data?.length && <p className="empty-state">Nenhum evento recebido nesta aplicação.</p>}
            </div>
          </article>
          <aside className="right-column">
            <article className="surface key-surface" id="api-keys"><div className="section-heading"><div><p className="kicker">CREDENCIAIS</p><h2>Chaves de API</h2></div><button className="small-action" onClick={() => setDialog('api-key')} disabled={!applicationId}><Plus size={14} />Nova</button></div><div className="compact-list">{keys.data?.map((key) => <div className="compact-row managed-row" key={key.id}><span className={`key-icon ${key.revoked_at ? 'revoked' : ''}`}><KeyRound size={15} /></span><div><strong>{key.name}</strong><small>{key.prefix}… · {key.revoked_at ? 'Revogada' : 'Ativa'}</small></div><div className="row-actions">{key.revoked_at ? <button className="danger-icon" onClick={() => removeKey(key.id)} title="Excluir chave"><Trash2 size={15} /></button> : <button className="text-action" onClick={() => revokeKey(key.id)}>Revogar</button>}</div></div>)}{!keys.data?.length && <p className="empty-state">Nenhuma chave criada.</p>}</div></article>
            <article className="surface endpoint-surface" id="endpoints"><div className="section-heading"><div><p className="kicker">DESTINOS</p><h2>Endpoints</h2></div><button className="small-action" onClick={() => setDialog('endpoint')} disabled={!applicationId}><Plus size={14} />Novo</button></div><div className="compact-list">{endpoints.data?.map((endpoint) => <div className="compact-row managed-row" key={endpoint.id}><span className={`health-dot ${endpoint.enabled ? 'healthy' : ''}`} /><div><strong>{endpoint.name}</strong><small>{endpoint.url}</small></div><button className="danger-icon" onClick={() => removeEndpoint(endpoint.id)} title="Excluir endpoint"><Trash2 size={15} /></button></div>)}{!endpoints.data?.length && <p className="empty-state">Nenhum endpoint.</p>}</div></article>
            <article className="surface alert-surface" id="alerts"><div className="section-heading"><div><p className="kicker">ATENÇÃO</p><h2>Alertas operacionais</h2></div><span className="count-badge">{alerts.data?.filter((alert) => !alert.acknowledged_at).length ?? 0} abertos</span></div><div className="compact-list">{alerts.data?.map((alert) => <div className={`compact-row alert-row ${alert.acknowledged_at ? 'acknowledged' : ''}`} key={alert.id}><span className="alert-icon"><AlertTriangle size={15} /></span><div><strong>{alert.acknowledged_at ? 'Reconhecido' : 'Requer atenção'} · {alert.endpoint_name ?? 'Entrega com falha'}</strong><small>Evento: {alert.event_idempotency_key ?? alert.event_id ?? 'não identificado'}</small><small>Destino: {alert.endpoint_url ?? 'não identificado'}</small><small>{alert.message}</small><small>{new Date(alert.created_at).toLocaleString('pt-BR')}</small>{!alert.acknowledged_at && <button className="acknowledge-button" onClick={() => acknowledgeAlert(alert.id)}>Reconhecer</button>}</div></div>)}{!alerts.data?.length && <p className="empty-state">Nenhum alerta operacional.</p>}</div></article>
          </aside>
        </section>
      </main>
      {dialog && <CreateDialog type={dialog} busy={busy} onClose={() => setDialog(null)} onSubmit={createResource} />}
      {secret && <SecretDialog title={secret.title} value={secret.value} onClose={() => setSecret(null)} />}
    </div>
  )
}

export default function App() {
  const queryClient = useQueryClient()
  const [authenticated, setAuthenticated] = useState(Boolean(auth.token()))

  function logout() {
    auth.clear()
    queryClient.clear()
    setAuthenticated(false)
  }

  if (!authenticated) return <Login onAuthenticated={() => setAuthenticated(true)} />
  return <Dashboard onLogout={logout} />
}
