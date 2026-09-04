#!/usr/bin/env python3
"""Generate ActuatorHub README screenshots + tour GIF from live API data."""

from __future__ import annotations

import json
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "media"
MEDIA.mkdir(exist_ok=True)
API = "http://127.0.0.1:8788"

BG = (6, 11, 16)
SURFACE = (16, 26, 36)
SURFACE2 = (22, 34, 48)
BORDER = (36, 52, 70)
TEAL = (46, 196, 182)
AMBER = (240, 162, 2)
DANGER = (255, 77, 109)
TEXT = (231, 238, 246)
MUTED = (139, 160, 181)
OK = (61, 214, 140)


def api(path: str, user: str = "u-ops", method: str = "GET", body: dict | None = None) -> object:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API}{path}",
        data=data,
        method=method,
        headers={"X-User-Id": user, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode())


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded(draw: ImageDraw.ImageDraw, xy, fill, radius=14, outline=None, width=1):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def chip(draw, xy, label, fg=MUTED, bg=SURFACE2, outline=BORDER):
    x, y = xy
    f = font(14)
    tw = draw.textlength(label, font=f)
    rounded(draw, (x, y, x + tw + 18, y + 24), fill=bg, radius=12, outline=outline)
    draw.text((x + 9, y + 4), label, fill=fg, font=f)
    return int(tw + 26)


def paint_chrome(
    img: Image.Image,
    title: str,
    role: str,
    stats: dict,
    active_tab: str = "Fleet",
    estop: bool = False,
) -> ImageDraw.ImageDraw:
    draw = ImageDraw.Draw(img)
    # ambient glow
    for i in range(8):
        alpha = 18 - i * 2
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        g = ImageDraw.Draw(glow)
        g.ellipse((520 - i * 30, -80 - i * 20, 1180 + i * 30, 420 + i * 20), fill=(46, 196, 182, max(alpha, 2)))
        img.alpha_composite(glow)
    draw = ImageDraw.Draw(img)

    # brand
    rounded(draw, (36, 28, 84, 76), fill=(20, 48, 52), radius=14, outline=(46, 196, 182, 120))
    draw.text((48, 38), "AH", fill=TEAL, font=font(18, True))
    draw.text((98, 30), "ActuatorHub", fill=TEXT, font=font(30, True))
    draw.text((98, 64), title, fill=MUTED, font=font(15))

    # stats
    x = 780
    for label, value in stats.items():
        rounded(draw, (x, 28, x + 100, 76), fill=SURFACE, radius=12, outline=BORDER)
        draw.text((x + 12, 34), label.upper(), fill=MUTED, font=font(11))
        draw.text((x + 12, 50), str(value), fill=TEXT, font=font(18, True))
        x += 110

    # role + estop
    rounded(draw, (x, 28, x + 190, 76), fill=SURFACE, radius=12, outline=BORDER)
    draw.text((x + 12, 34), "ACTIVE ROLE", fill=MUTED, font=font(11))
    draw.text((x + 12, 50), role[:22], fill=TEXT, font=font(15, True))
    x += 200
    estop_bg = (80, 40, 20) if estop else (70, 20, 35)
    estop_fg = AMBER if estop else DANGER
    rounded(draw, (x, 28, x + 170, 76), fill=estop_bg, radius=12, outline=estop_fg)
    draw.text((x + 18, 46), "CLEAR E-STOP" if estop else "EMERGENCY STOP", fill=estop_fg, font=font(13, True))

    # tabs
    tabs = ["Fleet", "Approvals", "Audit", "Sensor Rules"]
    tx = 36
    for tab in tabs:
        active = tab == active_tab
        bg = (20, 55, 52) if active else SURFACE
        outline = TEAL if active else BORDER
        w = chip(draw, (tx, 100), tab, fg=TEXT if active else MUTED, bg=bg, outline=outline)
        tx += w + 8

    return draw


def shot_fleet(devices: list[dict], status: dict) -> Image.Image:
    img = Image.new("RGBA", (1440, 900), BG + (255,))
    draw = paint_chrome(
        img,
        "Audited remote control · relays · PDUs · locks · edge MQTT",
        "Sam Patel · operator",
        {"Online": status["devices_online"], "MQTT": status["mqtt_mode"], "Pending": status["pending_approvals"]},
        active_tab="Fleet",
    )
    cards = [d for d in devices if d["kind"] not in ("sensor", "environmental")][:6]
    cards += [d for d in devices if d["kind"] in ("sensor", "environmental")][:2]
    for i, d in enumerate(cards[:8]):
        col, row = i % 4, i // 4
        x0, y0 = 36 + col * 345, 160 + row * 340
        x1, y1 = x0 + 330, y0 + 310
        rounded(draw, (x0, y0, x1, y1), fill=SURFACE2, radius=14, outline=BORDER)
        accent = AMBER if d.get("requires_approval") else TEAL
        draw.rectangle((x0, y0 + 12, x0 + 3, y1 - 12), fill=accent)
        draw.text((x0 + 18, y0 + 18), d["name"][:28], fill=TEXT, font=font(18, True))
        state = d["state"]
        state_fg = OK if state in ("on", "locked") else AMBER
        chip(draw, (x0 + 220, y0 + 18), state.upper(), fg=state_fg, bg=SURFACE, outline=state_fg)
        chip(draw, (x0 + 18, y0 + 54), d["kind"].upper(), fg=MUTED, bg=SURFACE, outline=BORDER)
        draw.text((x0 + 18, y0 + 90), f"{d['site']} · {d.get('rack') or '—'}", fill=MUTED, font=font(14))
        draw.text((x0 + 18, y0 + 118), d["mqtt_topic"][:42], fill=(159, 217, 210), font=font(12))
        if d["kind"] in ("relay", "fan", "pdu", "lock"):
            actions = {
                "relay": ["Energize", "De-energize", "Toggle"],
                "fan": ["Boost 100%", "Stop", "Start 50%"],
                "pdu": ["Outlet 6 ON", "Outlet 6 OFF", "Reboot outlet 1"],
                "lock": ["Unlock", "Lock"],
            }[d["kind"]]
            ax = x0 + 18
            for j, label in enumerate(actions):
                danger = j == 1 or "Reboot" in label or label == "Unlock"
                fg = AMBER if danger else TEAL
                bg = (55, 40, 18) if danger else (18, 55, 50)
                tw = draw.textlength(label, font=font(13))
                rounded(draw, (ax, y0 + 160, ax + tw + 20, y0 + 190), fill=bg, radius=10, outline=fg)
                draw.text((ax + 10, y0 + 166), label, fill=fg, font=font(13))
                ax += int(tw + 28)
            rounded(draw, (x0 + 18, y0 + 210, x1 - 18, y0 + 248), fill=BG, radius=10, outline=BORDER)
            draw.text((x0 + 28, y0 + 220), "Change reason (CAB / ticket)", fill=MUTED, font=font(13))
        else:
            val = d.get("meta", {}).get("value", "—")
            metric = d.get("meta", {}).get("metric", "")
            unit = "°C" if metric == "celsius" else ("% RH" if metric == "rh_pct" else "")
            draw.text((x0 + 18, y0 + 170), f"{val}{unit}", fill=TEAL, font=font(36, True))
            draw.text((x0 + 18, y0 + 220), "Live sensor feed", fill=MUTED, font=font(14))
    return img.convert("RGB")


def shot_approvals(commands: list[dict], devices: list[dict], users: list[dict]) -> Image.Image:
    img = Image.new("RGBA", (1440, 900), BG + (255,))
    pending = [c for c in commands if c["status"] == "pending_approval"]
    draw = paint_chrome(
        img,
        "Approvals queue — critical PDU / lock / CRAC actions",
        "Jordan Lee · approver",
        {"Online": 8, "MQTT": "simulated", "Pending": len(pending)},
        active_tab="Approvals",
    )
    # force Approvals tab look
    rounded(draw, (36, 150, 1404, 860), fill=SURFACE, radius=16, outline=BORDER)
    draw.text((56, 170), "Pending approvals", fill=TEXT, font=font(22, True))
    chip(draw, (1280, 172), f"{len(pending)} waiting", fg=AMBER, bg=(55, 40, 18), outline=AMBER)

    headers = ["When", "Device", "Action", "Requester", "Reason", ""]
    xs = [56, 180, 430, 620, 860, 1180]
    for h, x in zip(headers, xs):
        draw.text((x, 230), h.upper(), fill=MUTED, font=font(12, True))
    y = 270
    dev_map = {d["id"]: d["name"] for d in devices}
    user_map = {u["id"]: u["name"] for u in users}
    for c in pending[:6]:
        draw.line((56, y - 12, 1380, y - 12), fill=BORDER)
        draw.text((xs[0], y), c["requested_at"][11:19], fill=TEXT, font=font(14))
        draw.text((xs[1], y), dev_map.get(c["device_id"], c["device_id"])[:28], fill=TEXT, font=font(14))
        draw.text((xs[2], y), c["action"], fill=TEAL, font=font(14))
        draw.text((xs[3], y), user_map.get(c["requested_by"], c["requested_by"]), fill=TEXT, font=font(14))
        draw.text((xs[4], y), (c.get("reason") or "—")[:28], fill=MUTED, font=font(14))
        rounded(draw, (xs[5], y - 4, xs[5] + 90, y + 26), fill=(18, 55, 50), radius=10, outline=TEAL)
        draw.text((xs[5] + 14, y + 2), "Approve", fill=TEAL, font=font(13, True))
        rounded(draw, (xs[5] + 100, y - 4, xs[5] + 180, y + 26), fill=(70, 20, 35), radius=10, outline=DANGER)
        draw.text((xs[5] + 118, y + 2), "Reject", fill=DANGER, font=font(13, True))
        y += 70
    if not pending:
        draw.text((520, 420), "No commands awaiting approval.", fill=MUTED, font=font(18))
    return img.convert("RGB")


def shot_audit(events: list[dict], users: list[dict]) -> Image.Image:
    img = Image.new("RGBA", (1440, 900), BG + (255,))
    draw = paint_chrome(
        img,
        "Immutable audit trail",
        "Alex Rivera · admin",
        {"Online": 8, "MQTT": "simulated", "Pending": 0},
        active_tab="Audit",
    )
    rounded(draw, (36, 150, 1404, 860), fill=SURFACE, radius=16, outline=BORDER)
    draw.text((56, 170), "Immutable audit trail", fill=TEXT, font=font(22, True))
    chip(draw, (1260, 172), f"{len(events)} events", fg=MUTED, bg=SURFACE2, outline=BORDER)
    headers = ["Time", "Severity", "Actor", "Action", "Target", "Detail"]
    xs = [56, 220, 340, 520, 760, 960]
    for h, x in zip(headers, xs):
        draw.text((x, 230), h.upper(), fill=MUTED, font=font(12, True))
    user_map = {u["id"]: u["name"] for u in users}
    y = 270
    for e in events[:10]:
        draw.line((56, y - 12, 1380, y - 12), fill=BORDER)
        sev = e["severity"]
        sev_fg = {"info": TEAL, "warning": AMBER, "critical": DANGER}[sev]
        draw.text((xs[0], y), e["ts"][11:19], fill=TEXT, font=font(14))
        draw.text((xs[1], y), sev, fill=sev_fg, font=font(14, True))
        draw.text((xs[2], y), user_map.get(e["actor"], e["actor"])[:16], fill=TEXT, font=font(14))
        draw.text((xs[3], y), e["action"][:22], fill=TEAL, font=font(13))
        draw.text((xs[4], y), e["target"][:18], fill=MUTED, font=font(13))
        draw.text((xs[5], y), e["detail"][:48], fill=TEXT, font=font(13))
        y += 52
    return img.convert("RGB")


def shot_rules(rules: list[dict], devices: list[dict]) -> Image.Image:
    img = Image.new("RGBA", (1440, 900), BG + (255,))
    draw = paint_chrome(
        img,
        "Sensor → actuator automation",
        "Sam Patel · operator",
        {"Online": 8, "MQTT": "simulated", "Pending": 0},
        active_tab="Sensor Rules",
    )
    rounded(draw, (36, 150, 900, 860), fill=SURFACE, radius=16, outline=BORDER)
    draw.text((56, 170), "Sensor → actuator rules", fill=TEXT, font=font(22, True))
    y = 230
    dev_map = {d["id"]: d["name"] for d in devices}
    for rule in rules:
        rounded(draw, (56, y, 880, y + 110), fill=SURFACE2, radius=12, outline=BORDER)
        draw.text((76, y + 18), rule["name"], fill=TEXT, font=font(17, True))
        detail = (
            f"When {rule['metric']} {rule['operator']} {rule['threshold']} on "
            f"{dev_map.get(rule['sensor_id'], rule['sensor_id'])} → {rule['target_action']} on "
            f"{dev_map.get(rule['target_device_id'], rule['target_device_id'])}"
        )
        draw.text((76, y + 50), detail[:90], fill=MUTED, font=font(13))
        status = "Enabled" if rule["enabled"] else "Disabled"
        chip(draw, (760, y + 40), "Disable" if rule["enabled"] else "Enable", fg=AMBER if rule["enabled"] else TEAL,
             bg=(55, 40, 18) if rule["enabled"] else (18, 55, 50),
             outline=AMBER if rule["enabled"] else TEAL)
        draw.text((76, y + 78), status, fill=OK if rule["enabled"] else MUTED, font=font(13))
        y += 130

    rounded(draw, (960, 150, 1404, 520), fill=SURFACE, radius=16, outline=BORDER)
    draw.text((980, 170), "Simulate sensor reading", fill=TEXT, font=font(20, True))
    draw.text((980, 220), "Row 3 intake temperature (°C)", fill=MUTED, font=font(14))
    rounded(draw, (980, 250, 1360, 300), fill=BG, radius=10, outline=BORDER)
    draw.text((996, 262), "29.5", fill=TEXT, font=font(18, True))
    draw.text((980, 330), "Values above 28°C fire the fan-boost rule", fill=MUTED, font=font(14))
    rounded(draw, (980, 380, 1200, 430), fill=(18, 55, 50), radius=12, outline=TEAL)
    draw.text((1010, 394), "Push reading", fill=TEAL, font=font(16, True))
    return img.convert("RGB")


def shot_estop(devices: list[dict]) -> Image.Image:
    img = Image.new("RGBA", (1440, 900), BG + (255,))
    draw = paint_chrome(
        img,
        "Emergency stop engaged — actuators forced safe",
        "Alex Rivera · admin",
        {"Online": 8, "MQTT": "simulated", "Pending": 0},
        active_tab="Fleet",
        estop=True,
    )
    rounded(draw, (36, 150, 1404, 210), fill=(70, 20, 35), radius=14, outline=DANGER)
    draw.text((56, 170), "Emergency stop is active — actuators forced safe, new commands blocked.", fill=(255, 214, 222), font=font(16, True))
    for i, d in enumerate(devices[:4]):
        x0 = 36 + i * 345
        rounded(draw, (x0, 240, x0 + 330, 520), fill=SURFACE2, radius=14, outline=DANGER)
        draw.rectangle((x0, 252, x0 + 3, 508), fill=DANGER)
        draw.text((x0 + 18, 260), d["name"][:26], fill=TEXT, font=font(17, True))
        chip(draw, (x0 + 18, 300), "OFF" if d["kind"] != "lock" else "LOCKED", fg=OK, bg=SURFACE, outline=OK)
        draw.text((x0 + 18, 360), "Forced safe by E-Stop", fill=DANGER, font=font(14, True))
        draw.text((x0 + 18, 400), d["mqtt_topic"][:40], fill=(159, 217, 210), font=font(12))
    return img.convert("RGB")


def main() -> None:
    users = api("/api/users")
    status = api("/api/status")
    devices = api("/api/devices")
    # seed an approval for the approvals shot
    try:
        api(
            "/api/commands",
            user="u-ops",
            method="POST",
            body={
                "device_id": "dev-lock-cage",
                "action": "unlock",
                "reason": "CAB-4412: escorted access",
                "payload": {},
            },
        )
        api(
            "/api/commands",
            user="u-ops",
            method="POST",
            body={
                "device_id": "dev-pdu-r12",
                "action": "reboot_outlet",
                "reason": "INC-9921 cold reboot",
                "payload": {"outlet": 1},
            },
        )
    except Exception as exc:  # noqa: BLE001
        print("seed commands:", exc)

    commands = api("/api/commands")
    audit = api("/api/audit")
    rules = api("/api/rules")

    frames: list[Path] = []
    shots = [
        ("01-fleet.png", shot_fleet(devices, status)),
        ("02-approvals.png", shot_approvals(commands, devices, users)),
        ("03-audit.png", shot_audit(audit, users)),
        ("04-sensor-rules.png", shot_rules(rules, devices)),
    ]
    for name, im in shots:
        path = MEDIA / name
        im.save(path, "PNG")
        print("wrote", path)

    # tour frames
    frame_dir = MEDIA / "_frames"
    frame_dir.mkdir(exist_ok=True)
    tour = [
        shot_fleet(devices, status),
        shot_approvals(commands, devices, users),
        shot_audit(audit, users),
        shot_rules(rules, devices),
    ]
    # engage estop for last frames
    try:
        api("/api/emergency-stop?engage=true", user="u-admin", method="POST")
        devices2 = api("/api/devices", user="u-admin")
        tour.append(shot_estop(devices2))
        api("/api/emergency-stop?engage=false", user="u-admin", method="POST")
    except Exception as exc:  # noqa: BLE001
        print("estop frames:", exc)
        tour.append(shot_estop(devices))

    for i, im in enumerate(tour):
        p = frame_dir / f"frame-{i:02d}.png"
        im.save(p, "PNG")
        frames.append(p)

    gif = MEDIA / "actuatorhub-tour.gif"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            "1.0",
            "-i",
            str(frame_dir / "frame-%02d.png"),
            "-vf",
            "scale=1200:-1:flags=lanczos,fps=6",
            "-loop",
            "0",
            str(gif),
        ],
        check=True,
    )
    print("wrote", gif)


if __name__ == "__main__":
    main()
