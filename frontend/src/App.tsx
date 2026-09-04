import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  AlertOctagon,
  Check,
  CircuitBoard,
  ClipboardList,
  Fan,
  Lock,
  Power,
  Radio,
  ShieldCheck,
  Thermometer,
  X,
  Zap,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import {
  type AuditEvent,
  type CommandAction,
  type CommandRequest,
  type Device,
  type HubStatus,
  type SensorRule,
  type User,
  getUserId,
  hubApi,
  setUserId,
} from './lib/api'

type Tab = 'fleet' | 'approvals' | 'audit' | 'rules'

const KIND_ICON = {
  relay: CircuitBoard,
  fan: Fan,
  pdu: Power,
  lock: Lock,
  sensor: Thermometer,
  environmental: Activity,
} as const

function actionsFor(device: Device): { action: CommandAction; label: string; danger?: boolean }[] {
  switch (device.kind) {
    case 'relay':
      return [
        { action: 'turn_on', label: 'Energize' },
        { action: 'turn_off', label: 'De-energize', danger: true },
        { action: 'toggle', label: 'Toggle' },
      ]
    case 'fan':
      return [
        { action: 'set_speed', label: 'Boost 100%' },
        { action: 'turn_off', label: 'Stop', danger: true },
        { action: 'turn_on', label: 'Start 50%' },
      ]
    case 'pdu':
      return [
        { action: 'outlet_on', label: 'Outlet 6 ON' },
        { action: 'outlet_off', label: 'Outlet 6 OFF', danger: true },
        { action: 'reboot_outlet', label: 'Reboot outlet 1', danger: true },
      ]
    case 'lock':
      return [
        { action: 'unlock', label: 'Unlock', danger: true },
        { action: 'lock', label: 'Lock' },
      ]
    default:
      return []
  }
}

function payloadFor(device: Device, action: CommandAction): Record<string, unknown> {
  if (device.kind === 'fan' && action === 'set_speed') return { speed_pct: 100 }
  if (device.kind === 'fan' && action === 'turn_on') return { speed_pct: 50 }
  if (device.kind === 'pdu') return { outlet: action === 'reboot_outlet' ? 1 : 6 }
  return {}
}

export default function App() {
  const [tab, setTab] = useState<Tab>('fleet')
  const [users, setUsers] = useState<User[]>([])
  const [userId, setUid] = useState(getUserId())
  const [status, setStatus] = useState<HubStatus | null>(null)
  const [devices, setDevices] = useState<Device[]>([])
  const [commands, setCommands] = useState<CommandRequest[]>([])
  const [audit, setAudit] = useState<AuditEvent[]>([])
  const [rules, setRules] = useState<SensorRule[]>([])
  const [reasons, setReasons] = useState<Record<string, string>>({})
  const [toast, setToast] = useState<{ msg: string; kind: 'ok' | 'error' } | null>(null)
  const [busy, setBusy] = useState(false)
  const [simTemp, setSimTemp] = useState(29.5)

  const me = useMemo(() => users.find((u) => u.id === userId), [users, userId])
  const pending = useMemo(
    () => commands.filter((c) => c.status === 'pending_approval'),
    [commands],
  )

  const flash = (msg: string, kind: 'ok' | 'error' = 'ok') => {
    setToast({ msg, kind })
    window.setTimeout(() => setToast(null), 3200)
  }

  const refresh = useCallback(async () => {
    try {
      const [u, s, d, c, a, r] = await Promise.all([
        hubApi.users(),
        hubApi.status(),
        hubApi.devices(),
        hubApi.commands(),
        hubApi.audit(),
        hubApi.rules(),
      ])
      setUsers(u)
      setStatus(s)
      setDevices(d)
      setCommands(c)
      setAudit(a)
      setRules(r)
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Refresh failed', 'error')
    }
  }, [])

  useEffect(() => {
    void refresh()
    const id = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(id)
  }, [refresh, userId])

  const onRoleChange = (id: string) => {
    setUserId(id)
    setUid(id)
  }

  const runCommand = async (device: Device, action: CommandAction) => {
    setBusy(true)
    try {
      const cmd = await hubApi.createCommand({
        device_id: device.id,
        action,
        payload: payloadFor(device, action),
        reason: reasons[device.id] || '',
      })
      flash(
        cmd.status === 'pending_approval'
          ? `Queued for approval: ${action} on ${device.name}`
          : `Dispatched: ${action} on ${device.name}`,
      )
      await refresh()
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Command failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  const decide = async (id: string, approve: boolean) => {
    setBusy(true)
    try {
      await hubApi.decide(id, approve, approve ? 'Approved from console' : 'Rejected from console')
      flash(approve ? 'Command approved & dispatched' : 'Command rejected')
      await refresh()
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Decision failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  const toggleEstop = async () => {
    if (!status) return
    setBusy(true)
    try {
      const next = await hubApi.emergencyStop(!status.emergency_stop)
      setStatus(next)
      flash(next.emergency_stop ? 'EMERGENCY STOP ENGAGED' : 'Emergency stop cleared', next.emergency_stop ? 'error' : 'ok')
      await refresh()
    } catch (err) {
      flash(err instanceof Error ? err.message : 'E-stop failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  const fireSensor = async () => {
    setBusy(true)
    try {
      const res = await hubApi.sensorReading('dev-env-temp', 'celsius', simTemp)
      flash(
        res.fired_commands.length
          ? `Sensor trigger fired ${res.fired_commands.length} command(s)`
          : `Reading accepted (${simTemp}°C) — no rule crossed`,
      )
      await refresh()
    } catch (err) {
      flash(err instanceof Error ? err.message : 'Sensor ingest failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app-shell">
      <div className="hub-glow" aria-hidden />
      <div className="grid-overlay" aria-hidden />

      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            <Zap size={22} strokeWidth={2.4} />
          </div>
          <div>
            <h1>ActuatorHub</h1>
            <p>Audited remote control · relays · PDUs · locks · edge MQTT</p>
          </div>
        </div>

        <div className="top-controls">
          <div className="stat-pill">
            <span>Online</span>
            <strong>{status?.devices_online ?? '—'}</strong>
          </div>
          <div className="stat-pill">
            <span>MQTT</span>
            <strong>{status?.mqtt_mode ?? '—'}</strong>
          </div>
          <div className="stat-pill">
            <span>Pending</span>
            <strong>{status?.pending_approvals ?? 0}</strong>
          </div>
          <select
            className="role-select"
            aria-label="Active role"
            value={userId}
            onChange={(e) => onRoleChange(e.target.value)}
          >
            {users.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name} · {u.role}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={clsx('btn', status?.emergency_stop ? 'btn-amber' : 'btn-danger')}
            onClick={() => void toggleEstop()}
            disabled={busy || !me || me.role === 'viewer'}
          >
            <AlertOctagon size={16} />
            {status?.emergency_stop ? 'Clear E-Stop' : 'EMERGENCY STOP'}
          </button>
        </div>
      </header>

      {status?.emergency_stop && (
        <div className="estop-banner" role="alert">
          <span>Emergency stop is active — actuators forced safe, new commands blocked.</span>
          <button type="button" className="btn btn-amber btn-sm" onClick={() => void toggleEstop()} disabled={busy}>
            Clear
          </button>
        </div>
      )}

      <nav className="tabs" aria-label="Primary">
        {(
          [
            ['fleet', Radio, 'Fleet'],
            ['approvals', ShieldCheck, 'Approvals'],
            ['audit', ClipboardList, 'Audit'],
            ['rules', Thermometer, 'Sensor Rules'],
          ] as const
        ).map(([id, Icon, label]) => (
          <button
            key={id}
            type="button"
            className={clsx('tab', tab === id && 'active')}
            onClick={() => setTab(id)}
          >
            <Icon size={16} />
            {label}
            {id === 'approvals' && pending.length > 0 && <span className="badge">{pending.length}</span>}
          </button>
        ))}
      </nav>

      <main className="main-stage">
        <AnimatePresence mode="wait">
          <motion.div
            key={tab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.2 }}
          >
            {tab === 'fleet' && (
              <div className="device-grid">
                {devices.map((device) => {
                  const Icon = KIND_ICON[device.kind]
                  const actions = actionsFor(device)
                  return (
                    <article
                      key={device.id}
                      className={clsx(
                        'device-card',
                        device.requires_approval && 'critical',
                        !device.online && 'offline',
                        status?.emergency_stop && 'estop',
                      )}
                    >
                      <div className="device-head">
                        <h3>{device.name}</h3>
                        <span className={clsx('state-chip', `state-${device.state}`)}>{device.state}</span>
                      </div>
                      <div className="meta-row">
                        <span className="kind-chip">
                          <Icon size={12} /> {device.kind}
                        </span>
                        <span>{device.site}{device.rack ? ` · ${device.rack}` : ''}</span>
                        {device.requires_approval && <span>approval required</span>}
                      </div>
                      <div className="meta-row">
                        <code>{device.mqtt_topic}</code>
                        {typeof device.meta.speed_pct === 'number' && (
                          <span>Speed {String(device.meta.speed_pct)}%</span>
                        )}
                        {typeof device.meta.value === 'number' && (
                          <span>
                            {String(device.meta.value)}
                            {device.meta.metric === 'celsius' ? '°C' : device.meta.metric === 'rh_pct' ? '% RH' : ''}
                          </span>
                        )}
                        {Array.isArray(device.meta.outlet_states) && (
                          <span>
                            Outlets{' '}
                            {(device.meta.outlet_states as number[]).map((v) => (v ? '■' : '□')).join('')}
                          </span>
                        )}
                      </div>
                      {actions.length > 0 && (
                        <>
                          <div className="action-row">
                            {actions.map((a) => (
                              <button
                                key={a.action}
                                type="button"
                                className={clsx('btn btn-sm', a.danger ? 'btn-amber' : 'btn-teal')}
                                disabled={busy || me?.role === 'viewer' || !!status?.emergency_stop}
                                onClick={() => void runCommand(device, a.action)}
                              >
                                {a.label}
                              </button>
                            ))}
                          </div>
                          <input
                            className="reason-input"
                            placeholder="Change reason (CAB / ticket)"
                            value={reasons[device.id] || ''}
                            onChange={(e) =>
                              setReasons((prev) => ({ ...prev, [device.id]: e.target.value }))
                            }
                          />
                        </>
                      )}
                    </article>
                  )
                })}
              </div>
            )}

            {tab === 'approvals' && (
              <div className="panel">
                <div className="panel-title">
                  <h2>Pending approvals</h2>
                  <span className="kind-chip">{pending.length} waiting</span>
                </div>
                {pending.length === 0 ? (
                  <p className="empty">No commands awaiting approval. Critical PDU / lock / CRAC actions will appear here.</p>
                ) : (
                  <table className="table">
                    <thead>
                      <tr>
                        <th>When</th>
                        <th>Device</th>
                        <th>Action</th>
                        <th>Requester</th>
                        <th>Reason</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {pending.map((c) => {
                        const device = devices.find((d) => d.id === c.device_id)
                        const requester = users.find((u) => u.id === c.requested_by)
                        return (
                          <tr key={c.id}>
                            <td>{new Date(c.requested_at).toLocaleTimeString()}</td>
                            <td>{device?.name || c.device_id}</td>
                            <td><code>{c.action}</code></td>
                            <td>{requester?.name || c.requested_by}</td>
                            <td>{c.reason || '—'}</td>
                            <td>
                              <div className="action-row">
                                <button
                                  type="button"
                                  className="btn btn-sm btn-teal"
                                  disabled={busy || (me?.role !== 'approver' && me?.role !== 'admin')}
                                  onClick={() => void decide(c.id, true)}
                                >
                                  <Check size={14} /> Approve
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-sm btn-danger"
                                  disabled={busy || (me?.role !== 'approver' && me?.role !== 'admin')}
                                  onClick={() => void decide(c.id, false)}
                                >
                                  <X size={14} /> Reject
                                </button>
                              </div>
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {tab === 'audit' && (
              <div className="panel">
                <div className="panel-title">
                  <h2>Immutable audit trail</h2>
                  <span className="kind-chip">{audit.length} events</span>
                </div>
                <table className="table">
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Severity</th>
                      <th>Actor</th>
                      <th>Action</th>
                      <th>Target</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.map((e) => (
                      <tr key={e.id}>
                        <td>{new Date(e.ts).toLocaleString()}</td>
                        <td className={`sev-${e.severity}`}>{e.severity}</td>
                        <td>{users.find((u) => u.id === e.actor)?.name || e.actor}</td>
                        <td><code>{e.action}</code></td>
                        <td>{e.target}</td>
                        <td>{e.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {tab === 'rules' && (
              <div className="two-col">
                <div className="panel">
                  <div className="panel-title">
                    <h2>Sensor → actuator rules</h2>
                  </div>
                  {rules.map((rule) => (
                    <div key={rule.id} className="rule-card">
                      <div>
                        <h3>{rule.name}</h3>
                        <p>
                          When <code>{rule.metric}</code> {rule.operator} {rule.threshold} on{' '}
                          {devices.find((d) => d.id === rule.sensor_id)?.name || rule.sensor_id} →{' '}
                          <code>{rule.target_action}</code> on{' '}
                          {devices.find((d) => d.id === rule.target_device_id)?.name || rule.target_device_id}
                        </p>
                        <p style={{ marginTop: 6 }}>
                          {rule.enabled ? 'Enabled' : 'Disabled'}
                          {rule.last_fired ? ` · last fired ${new Date(rule.last_fired).toLocaleTimeString()}` : ''}
                        </p>
                      </div>
                      <button
                        type="button"
                        className={clsx('btn btn-sm', rule.enabled ? 'btn-amber' : 'btn-teal')}
                        disabled={busy || (me?.role !== 'approver' && me?.role !== 'admin')}
                        onClick={async () => {
                          await hubApi.toggleRule(rule.id)
                          await refresh()
                        }}
                      >
                        {rule.enabled ? 'Disable' : 'Enable'}
                      </button>
                    </div>
                  ))}
                </div>
                <div className="panel">
                  <div className="panel-title">
                    <h2>Simulate sensor reading</h2>
                  </div>
                  <div className="sim-box">
                    <label>
                      Row 3 intake temperature (°C)
                      <input
                        type="number"
                        step="0.1"
                        value={simTemp}
                        onChange={(e) => setSimTemp(Number(e.target.value))}
                      />
                    </label>
                    <p style={{ margin: 0, color: 'var(--muted)', fontSize: '0.85rem' }}>
                      Values above 28°C fire the fan-boost rule (if enabled and cooldown elapsed).
                    </p>
                    <button
                      type="button"
                      className="btn btn-teal"
                      disabled={busy || me?.role === 'viewer'}
                      onClick={() => void fireSensor()}
                    >
                      <Thermometer size={16} /> Push reading
                    </button>
                  </div>
                </div>
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </main>

      <div className="toast-stack" aria-live="polite">
        <AnimatePresence>
          {toast && (
            <motion.div
              className={clsx('toast', toast.kind)}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
            >
              {toast.msg}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  )
}
