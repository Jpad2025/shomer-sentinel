# Guía de Proyecto — Shomer Sentinel (Lab Utah .205)

## Para: Juan y Laura (Lala)

---

## Resumen

| Elemento | Detalle |
|----------|---------|
| Servidor | Mini PC Utah — `192.168.1.205` / Tailscale `100.100.188.87` |
| Panel Shomer | `/opt/network_monitor/` |
| Bot Telegram | `/storage/shomer-agent/` |
| GitHub dueño | `usbingenieria` (Laura administra) |
| GitHub colaborador | `jpad2025` (Juan) |
| Repo panel | https://github.com/usbingenieria/shomer-sentinel |
| Repo bot | https://github.com/usbingenieria/shomer-agent |

---

## Infraestructura

```
PC Juan (Cursor)
       │ SSH Remote
       ▼
Utah .205 (USB-SHOMER)  ← repos git aquí
       │
       │ deploy-all / sync-from-opera
       ▼
Opera, shomer245, shomer243  ← solo copias, sin git
```

---

## Repositorios GitHub (privados)

Crear en https://github.com/usbingenieria (cuenta Laura):

| Repo | Nombre | Vacío (sin README) |
|------|--------|--------------------|
| Panel | `shomer-sentinel` | Sí |
| Bot | `shomer-agent` | Sí |

Agregar `jpad2025` como colaborador en ambos (Settings → Collaborators).

---

## Llave SSH Utah → GitHub

En Utah (.205), la clave pública está en:

```bash
cat ~/.ssh/id_ed25519_github.pub
```

Subirla en GitHub → Settings → SSH keys → título: **USB-SHOMER-205**

---

## Primer push (desde Utah)

```bash
# Panel
cd /opt/network_monitor
git push -u origin main

# Bot
cd /storage/shomer-agent
git push -u origin main
```

---

## Comandos de trabajo diario

| Acción | Comando |
|--------|---------|
| Cambiaste en Utah | `~/deploy-all.sh` |
| Cambiaste en opera | `~/sync-from-opera.sh` → commit → `~/deploy-all.sh` |
| Guardar en GitHub | `git add -A && git commit -m "..." && git push` |

---

## Reglas (igual que Vultr)

- **NO** subir `.env`, bases de datos, tokens
- **NO** commitear secretos de clientes
- **NO** push a main sin avisar
- Commits en español, mensajes claros

---

## Cuentas GitHub

| Persona | Cuenta | Rol |
|---------|--------|-----|
| Laura | `usbingenieria` | Dueña repos |
| Juan | `jpad2025` | Colaborador |
