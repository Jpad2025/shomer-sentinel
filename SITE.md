# Hotel Ópera — Configuración de sitio (NO va a git)

Documento local del servidor `shomer-hotelopera` (`192.168.0.250`).  
Actualizado: **8 jul 2026** (~12:35 COT) — verificación en vivo.

---

## Estado operativo (8 jul 2026)

| Métrica | Valor |
|---------|-------|
| Servicios | Guardian ✅ · Poller ✅ · Agente ✅ |
| Infra (activos) | **50 online** / **2 offline** (`.148`, `.243`) |
| Guardian APs | **29 online** / **1 offline** (HAB 103 `.148`) |
| Pulse EWMA | ✅ activo — 22 equipos; **`.58` IMP SCOCINA en degradando** (71 ticks) |
| Blips logs poller | **3 / 24 h** · **56 / 7 días** |
| Blips tabla `infra_blip_events` | 0 en 24 h (persistencia desde sesión 66) |
| RX dropped `eno1` | Acum. **~14,69 M** — delta 24 h pendiente 2ª muestra horaria |
| Telegram 3 días | **138** total — bot 49 · VPN 33 · infra equipos 17 · snmp 16 · service 8 · printer 7 |

### Offline / crónicos (verificado ahora)

| IP | Equipo | Estado | Notas |
|-----|--------|--------|-------|
| `.148` | AP HAB 103 | **Offline** | Guardian + Infra — crónico |
| `.57` | IMP Recepción | **Offline** (desde 10 jun) | `active=0` en Infra — no entra al poll; sigue caído |
| `.243` | Bixolon POS | **Offline** | Nuevo 8 jul — antes intermitente |

### Inestables — mejoraron (vigilar)

| IP | Equipo | Estado 8 jul |
|-----|--------|--------------|
| `.189` | AP OFC-MANTENIMIENTO | Online |
| `.133` | SW Amalfi | Online |
| `.52` | Cámara sin identificar | Online (2 eventos offline 24 h) |
| `.136` | Terminal Ingenico | Online (3 eventos offline 24 h) |
| `.58` | IMP SCOCINA | Online — **Pulse degradando** — revisar cable/impresora |

### Switches — errores SNMP (online, hardware sospechoso)

| IP | Puerto | Errores `in_errors` |
|-----|--------|---------------------|
| `.168` SW1-P50 | **GE49** | ~95.534 |
| `.216` SW-POE-OFC | Port 7 | ~2.860 |

### MikroTik — VPN OpenVPN
- Desde **8 jul 2026:** Telegram **solo conexiones** (`INFRA_VPN_ALERT_DISCONNECT=0`).
- Los 33 msgs VPN en 3 días incluyen desconexiones **anteriores** al cambio.

### Blips Shomer (`host_network_blip`)
- Investigación abierta — prioridad **campo:** cable/puerto switch del servidor `.250` / `eno1`.
- Software: resumen diario 07:00 + registro RX dropped activo (sesión 66).

---

## ✅ Hecho en software (sesiones 64–66)

| Qué | Cuándo |
|-----|--------|
| Hunter mensajes legibles (firmas ET → español) | Sesión 64 |
| Doc revisión sitio `REVISION-EN-SITIO-OPERA.md` | Sesión 64 |
| **Pulse Correlate** — oleada LAN + blip Shomer | Sesión 65 |
| **Pulse EWMA** — degradando antes de offline | Sesión 65 |
| IA diagnóstico cooldown 6 h | Sesión 65 |
| Debounce puertos SNMP (2 polls) | Sesión 65 |
| **Resumen blip diario + delta RX dropped `eno1`** | Sesión 66 |
| **VPN solo conexiones** (sin desconexiones Telegram) | Sesión 66 |
| Perfiles Infra, poller fast/snmp, blip suppressor | Sesión 62–63 |

**Descartado / no prioritario:** cambiar SNMP `public` → `shomer2026`.

---

## 🔴 Pendientes activos — 8 jul 2026

### Campo (único que arregla caídas reales)

| # | Qué | Estado | Quién |
|---|-----|--------|-------|
| 1 | **AP HAB 103** `.148` | Offline crónico | Cristian/Ricardo |
| 2 | **IMP Recepción** `.57` | Offline desde 10 jun | Cristian/Ricardo |
| 3 | **Bixolon** `.243` | Offline 8 jul | Campo si persiste |
| 4 | **Cable/puerto switch Shomer** `.250` / `eno1` (blips) | 3 blips/24h · 56/7d | Campo |
| 5 | Switch `.168` puerto **GE49** (~95k errores) | Online, hardware | Campo |
| 6 | Switch `.216` puerto 7 (~2,8k errores) | Online, hardware | Campo |
| 7 | **IMP SCOCINA** `.58` — Pulse degradando | Online inestable | Campo |

Checklist detallado: `docs/campo/REVISION-EN-SITIO-OPERA.md`

### USB / operación (no campo)

| # | Qué | Prioridad |
|---|-----|-----------|
| 8 | Sync código sesiones 64–66 → `.205` / GitHub | ✅ 8 jul — `7db0383` sentinel · `0a74849` agent |
| 9 | Rotar token Telegram (expuesto sesión antigua) | Media |
| 10 | Observar Pulse EWMA 2–3 días (`.58` ya en degradando) | Baja |

### Producto — opcional / backlog

| # | Qué | Notas |
|---|-----|-------|
| 11 | Topología `network_links` + “switch padre” en oleada | Opcional |
| 12 | Syslog MikroTik, SNMP traps, NetFlow | Backlog multi-cliente |

### Histórico (no urgente — no hacer ahora)

- Failover WAN ETB automático MikroTik
- Credenciales `.\sistemas` en `.41`, `.142`, `.170`
- Deep scan nocturno Tracker
- Medición 7 días debounce OFC-COCINA
- Plantilla genérica `REVISION-EN-SITIO-TEMPLATE.md`

---

## ¿Hay más que hacer en software para monitoreo?

**No bloqueante.** Stack actual cubre ping, SNMP, oleadas, EWMA, blips, resumen diario.

Lo que **sigue generando Telegram** hoy:
1. **Equipos realmente caídos o inestables** (campo)
2. **VPN USB** — solo conexiones desde 8 jul
3. **Hunter bloqueos** (correcto)
