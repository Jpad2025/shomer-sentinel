# NOC — pantalla de operaciones (TV)

Actualizado: **28 jul 2026** (noche)

## URLs

| Ruta | Uso |
|------|-----|
| `/noc?token=…` | Pantalla principal (hotel / TV / operaciones) |
| `/noc/data?token=…` | JSON para el display |
| `/noc/problems/ack` | ACK “Ya lo vi” (POST, token display) |
| `/noc/cliente` | Preview legado (opcional) |

Token: `system_state` clave `noc.display_token` (único por sitio; no compartir entre prod y lab).

## Qué muestra

- KPIs (APs, infra, amenazas externas contenidas, WAN, riesgos)
- Banda Hunter (prestigio / mes)
- **Bloque Shomer IA** — logo `shomer-eyes.png` + feed de avisos (espejo de lo ya enviado a Telegram)
- Problemas activos + historial corto + ACK
- Infra / APs
- **Shomer — soporte USB** — tipografía TV (servicios, CPU/RAM, protección, estado IA)

## Canal vivo (espejo Telegram → NOC)

Los avisos que **ya** se envían a Telegram se copian a Redis `noc:ia_log` y se muestran en el bloque IA.  
**No** genera mensajes Telegram extra.

- Core: `app/scripts/alerts.py` → `mirror_telegram_to_noc()` tras envío OK  
- Agente: `monitor._send` → `log_ia_action(..., type=telegram)` tras envío OK  

Requiere reinicio `shomer-guardian` + contenedor `shomer-agent` tras desplegar código nuevo.

## Qué NO hacer

- No inventar un segundo canal de spam Telegram
- No “arreglar” cooldowns Guardian/Infra/Hunter desde el NOC
- No reintroducir semáforo rojo / `/noc/tecnico` sin pedido explícito

Código: `app/api/shomer_noc.py`, `app/templates/noc.html`, `app/scripts/alerts.py`.
