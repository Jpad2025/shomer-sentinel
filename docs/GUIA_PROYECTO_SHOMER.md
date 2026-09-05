# Guía de Proyecto — Shomer Sentinel

> **Corregido 4 sep 2026** — esta guía describía un plan de repos/cuentas GitHub
> y unos scripts (`deploy-all.sh`, `sync-from-opera.sh`) que ya no existen. El
> proyecto evolucionó a un esquema distinto: git vive directamente en los 4
> servidores, bajo una sola cuenta. Ver `CLAUDE.md` (network_monitor) y
> `CHANGELOG.md` (shomer-agent) para el detalle sesión por sesión.

## Resumen (estado real, 4 sep 2026)

| Elemento | Detalle |
|----------|---------|
| Producción | Hotel Ópera — `shomer-hotelopera` (Tailscale `100.103.148.119`) |
| Labs | `shomer205`, `shomer245`, `shomer243` — futuras instalaciones de clientes reales |
| Panel (network_monitor) | `/opt/network_monitor/` en los 4 servidores |
| Bot Telegram (shomer-agent) | `/storage/shomer-agent/` en los 4 servidores |
| Cuenta GitHub | `Jpad2025` (Juan Pablo) — dueño de ambos repos |
| Repo panel | `git@github.com:Jpad2025/shomer-sentinel.git` |
| Repo bot | `git@github.com:jpad2025/shomer-agent.git` |

**Los 4 servidores tienen git configurado directamente** (panel y bot), todos apuntando a la misma cuenta. No hay un servidor "maestro sin copias" — cualquiera puede tener cambios locales, por eso el flujo de trabajo diario es explícito (ver abajo).

## Comandos de trabajo diario

| Acción | Cómo |
|--------|------|
| Cambio en shomer-agent (bot) | Editar en el host → `git commit` + `git push` → `docker restart shomer-agent` (en ese host) → `bash tools/fleet_sync.sh` desde Ópera para propagar a los 3 labs |
| Cambio en network_monitor (panel) | Editar en Ópera → `git commit` + `git push` → `sudo systemctl restart shomer-guardian` → `bash tools/deploy.sh` (excluye producción por defecto; requiere `SHOMER_DEPLOY_AUTHORIZED=1` para incluir Ópera) |
| Ver estado real de un servidor | `ssh <host> "systemctl is-active shomer-guardian shomer-tools; sudo docker ps --filter name=shomer-agent"` |

## Reglas

- **NO** subir `.env`, bases de datos, ni credenciales/tokens de clientes.
- **NO** hacer push a `main` de producción sin avisar.
- Commits en español, mensajes claros.
- Antes de afirmar el estado de un servidor ("le falta X", "está pendiente Y"), **verificar en vivo por SSH** — la documentación puede estar desactualizada (misma lección aprendida en `EQUIPOS.md`).
