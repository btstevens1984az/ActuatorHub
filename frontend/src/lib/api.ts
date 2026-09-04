export type Role = 'viewer' | 'operator' | 'approver' | 'admin'
export type DeviceKind = 'relay' | 'fan' | 'pdu' | 'lock' | 'sensor' | 'environmental'
export type DeviceState = 'on' | 'off' | 'open' | 'locked' | 'unlocked' | 'unknown' | 'fault'
export type CommandAction =
  | 'turn_on'
  | 'turn_off'
  | 'toggle'
  | 'lock'
  | 'unlock'
  | 'set_speed'
  | 'outlet_on'
  | 'outlet_off'
  | 'reboot_outlet'
  | 'e_stop'

export interface User {
  id: string
  name: string
  role: Role
  site: string
}

export interface Device {
  id: string
  name: string
  kind: DeviceKind
  site: string
  rack?: string | null
  mqtt_topic: string
  state: DeviceState
  online: boolean
  requires_approval: boolean
  meta: Record<string, unknown>
  last_seen: string
  tags: string[]
}

export interface CommandRequest {
  id: string
  device_id: string
  action: CommandAction
  payload: Record<string, unknown>
  requested_by: string
  requested_at: string
  status: string
  reason: string
  approved_by?: string | null
  decided_at?: string | null
  decision_note?: string | null
  requires_approval: boolean
}

export interface AuditEvent {
  id: string
  ts: string
  actor: string
  action: string
  target: string
  detail: string
  severity: 'info' | 'warning' | 'critical'
}

export interface SensorRule {
  id: string
  name: string
  sensor_id: string
  metric: string
  operator: string
  threshold: number
  target_device_id: string
  target_action: CommandAction
  enabled: boolean
  cooldown_seconds: number
  last_fired?: string | null
}

export interface HubStatus {
  emergency_stop: boolean
  mqtt_connected: boolean
  mqtt_mode: 'live' | 'simulated'
  devices_online: number
  pending_approvals: number
  version: string
}

let userId = localStorage.getItem('ah_user') || 'u-ops'

export function setUserId(id: string) {
  userId = id
  localStorage.setItem('ah_user', id)
}

export function getUserId() {
  return userId
}

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId,
      ...(init?.headers || {}),
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || res.statusText)
  }
  return res.json()
}

export const hubApi = {
  users: () => api<User[]>('/api/users'),
  status: () => api<HubStatus>('/api/status'),
  devices: () => api<Device[]>('/api/devices'),
  commands: (status?: string) =>
    api<CommandRequest[]>(status ? `/api/commands?status=${status}` : '/api/commands'),
  audit: () => api<AuditEvent[]>('/api/audit'),
  rules: () => api<SensorRule[]>('/api/rules'),
  createCommand: (body: {
    device_id: string
    action: CommandAction
    payload?: Record<string, unknown>
    reason?: string
  }) =>
    api<CommandRequest>('/api/commands', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  decide: (id: string, approve: boolean, note = '') =>
    api<CommandRequest>(`/api/commands/${id}/decide`, {
      method: 'POST',
      body: JSON.stringify({ approve, note }),
    }),
  emergencyStop: (engage: boolean) =>
    api<HubStatus>(`/api/emergency-stop?engage=${engage}`, { method: 'POST' }),
  sensorReading: (sensor_id: string, metric: string, value: number) =>
    api<{ accepted: boolean; fired_commands: CommandRequest[] }>('/api/sensors/reading', {
      method: 'POST',
      body: JSON.stringify({ sensor_id, metric, value }),
    }),
  toggleRule: (id: string) =>
    api<SensorRule>(`/api/rules/${id}/toggle`, { method: 'POST' }),
}
