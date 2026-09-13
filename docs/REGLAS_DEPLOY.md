# REGLAS DE DEPLOY Y PRODUCCIÓN — OBLIGATORIO

**Violación de estas reglas puede ser fatal en campo** (credenciales cruzadas, IPs de lab en hotel, panel caído en horario operativo).

> **Corregido 13 sep 2026** — la dirección del deploy cambió desde que se escribió esto:
> hoy **Ópera es el maestro** (produce el código, GitHub, y empuja hacia los 3 labs), no al
> revés. Las herramientas reales son `tools/fleet_sync_core.sh` (core) y
> `tools/fleet_sync.sh` (agente) — verifican salud, corren las pruebas y revierten solas si
> algo falla; después de sincronizar, `tools/fleet_estado.py` confirma que ningún archivo
> quedó fuera de git en ningún sitio. `tools/deploy.sh` (abajo) describe un flujo anterior
> (`.205` como origen) que ya no es el que se usa — se deja como referencia histórica, no
> como instrucción vigente.

---

## 1. Autorización de Juan Pablo

| Acción | Producción (cliente) | Lab (.205, mini PCs) |
|--------|----------------------|----------------------|
| `git commit` en .205 | Libre (repo local) | Libre |
| `deploy.sh` / rsync remoto | **Solo con autorización explícita de Juan Pablo** | Flujo desarrollo normal |
| Reiniciar servicios en hotel | **Solo autorizado + ventana mantenimiento** | Normal en lab |

**Producción hoy:** `shomer-hotelopera` (`100.103.148.119`) — Hotel Ópera, Bogotá.

---

## 2. Deploy = solo código de la aplicación

### ✅ Permitido sincronizar

- `/opt/network_monitor/app/` — panel, APIs, templates, scripts producto.
- Código `/storage/shomer-agent/` — **sin** `.env` ni `data/`.

### ❌ Prohibido sincronizar o sobrescribir

- `/storage/db/network_monitor.db`
- `/storage/db/inventory.db`
- `/opt/network_monitor/SITE.md` del cliente
- Credenciales, subnets, `hunter.*` de un hotel en otro servidor
- `/etc/shomer/shomer-runtime.env` remoto (JWT, CORS, flags por sitio)
- `suricata.yaml`, netplan, reglas de firewall del sitio
- `SHOMER_LAB_NO_SPAN` en producción

---

## 3. Commits

- Commits en `.205` documentan **código**, no config de un hotel concreto.
- No commitear secretos (`.env`, passwords, tokens).
- Config de sitio vive en `SITE.md` **en cada servidor**, no en el repo global como verdad del cliente.

---

## 4. Referencias

- Matriz de equipos: `docs/EQUIPOS.md`
- Script deploy: `tools/deploy.sh` (lee `tools/servers.txt`)
- Sin argumento: despliega lab **243 + 245 + 205**; **omite Ópera** salvo `SHOMER_DEPLOY_AUTHORIZED=1`
- Normas desarrollo: `CLAUDE.md` §B.3

*USB Ingeniería — regla permanente desde jun 2026 · actualizado 16 jun 2026.*

---

## Deploy — dos modos (`tools/deploy.sh`)

| Modo | Comando | Qué hace |
|------|---------|----------|
| **Todos lab** | `bash tools/deploy.sh` | 243 + 245 + 205 — **no** Ópera |
| **Un servidor** | `bash tools/deploy.sh <IP_Tailscale>` | Solo ese equipo |
| **Con Ópera** | `SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh` | Todos en `servers.txt` |

Registro IPs: `tools/servers.txt` · matriz equipos: `docs/EQUIPOS.md`

---

## Seguro Hunter — dos canales (16 jun 2026)

| Canal | Activar / desactivar |
|-------|----------------------|
| **Panel** | Botón **Seguro ON/OFF** (header) o Config → *Habilitado* → Guardar |
| **Telegram** | `/seguro on` · `/seguro off` |

Liberar IP: `/liberar` · `/desbloquear IP`. Guía automática al chat al cambiar estado.
