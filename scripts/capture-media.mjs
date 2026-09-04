import { chromium } from 'playwright'
import { mkdirSync, rmSync } from 'fs'
import { join, dirname } from 'path'
import { fileURLToPath } from 'url'
import { execSync } from 'child_process'

const __dirname = dirname(fileURLToPath(import.meta.url))
const media = join(__dirname, '..', 'media')
mkdirSync(media, { recursive: true })

const base = process.env.AH_URL || 'http://127.0.0.1:5173'
const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
await page.goto(base, { waitUntil: 'networkidle' })
await page.waitForTimeout(1200)

// Fleet overview
await page.screenshot({ path: join(media, '01-fleet.png') })

// Request a critical command as operator (default)
const cage = page.locator('article').filter({ hasText: 'Cage Door Lock B' })
await cage.getByPlaceholder('Change reason (CAB / ticket)').fill('CAB-4412: escorted access')
await cage.getByRole('button', { name: 'Unlock' }).click()
await page.waitForTimeout(700)

// Approvals tab
await page.getByRole('button', { name: /Approvals/ }).click()
await page.waitForTimeout(600)
await page.screenshot({ path: join(media, '02-approvals.png') })

// Switch to approver and approve
await page.getByLabel('Active role').selectOption({ label: /Jordan Lee/ })
await page.waitForTimeout(500)
const approveBtn = page.getByRole('button', { name: /Approve/ }).first()
if (await approveBtn.count()) {
  await approveBtn.click()
  await page.waitForTimeout(700)
}

// Audit
await page.getByRole('button', { name: /Audit/ }).click()
await page.waitForTimeout(600)
await page.screenshot({ path: join(media, '03-audit.png') })

// Sensor rules + simulate
await page.getByRole('button', { name: /Sensor Rules/ }).click()
await page.waitForTimeout(500)
await page.getByLabel('Active role').selectOption({ label: /Sam Patel/ })
await page.waitForTimeout(400)
await page.locator('input[type="number"]').fill('29.5')
await page.getByRole('button', { name: /Push reading/ }).click()
await page.waitForTimeout(700)
await page.screenshot({ path: join(media, '04-sensor-rules.png') })

// GIF frames — control flow tour
const framesDir = join(media, '_frames')
rmSync(framesDir, { recursive: true, force: true })
mkdirSync(framesDir, { recursive: true })

const steps = [
  async () => {
    await page.getByRole('button', { name: /^Fleet$/ }).click()
    await page.waitForTimeout(400)
  },
  async () => {
    const pdu = page.locator('article').filter({ hasText: 'Smart PDU Rack 12' })
    await pdu.getByPlaceholder('Change reason (CAB / ticket)').fill('Ticket INC-9921 cold reboot')
    await pdu.getByRole('button', { name: /Reboot outlet 1/ }).click()
    await page.waitForTimeout(600)
  },
  async () => {
    await page.getByRole('button', { name: /Approvals/ }).click()
    await page.waitForTimeout(500)
  },
  async () => {
    await page.getByLabel('Active role').selectOption({ label: /Alex Rivera/ })
    await page.waitForTimeout(400)
    const btn = page.getByRole('button', { name: /Approve/ }).first()
    if (await btn.count()) await btn.click()
    await page.waitForTimeout(600)
  },
  async () => {
    await page.getByRole('button', { name: /Audit/ }).click()
    await page.waitForTimeout(500)
  },
  async () => {
    await page.getByRole('button', { name: /EMERGENCY STOP|Clear E-Stop/ }).click()
    await page.waitForTimeout(700)
  },
  async () => {
    await page.getByRole('button', { name: /^Fleet$/ }).click()
    await page.waitForTimeout(500)
  },
]

for (let i = 0; i < steps.length; i++) {
  await steps[i]()
  await page.screenshot({ path: join(framesDir, `frame-${String(i).padStart(2, '0')}.png`) })
}

await browser.close()

execSync(
  `ffmpeg -y -framerate 1.1 -i "${framesDir}/frame-%02d.png" -vf "scale=1200:-1:flags=lanczos,fps=6" -loop 0 "${join(media, 'actuatorhub-tour.gif')}"`,
  { stdio: 'inherit' },
)
console.log('Media captured → media/')
