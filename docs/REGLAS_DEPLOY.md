# REGLAS DE DEPLOY Y PRODUCCIÓN — OBLIGATORIO

**Violación de estas reglas puede ser fatal en campo** (credenciales cruzadas, IPs de lab en hotel, panel caído en horario operativo).

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
- Normas desarrollo: `CLAUDE.md` §B.3

*USB Ingeniería — regla permanente desde jun 2026.*
