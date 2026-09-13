# Pendientes lab (recordatorio operativo)

Actualizado: **13 sep 2026** · Dueño: Juan Pablo (único operador)

> Reescrito el 13 sep 2026: el historial completo (sesiones 69-77, checklists de
> verificación ya cumplidos, tablas de tokens ya corregidas) se archivó en
> `CLAUDE_historico.md`. Esto es solo lo que sigue genuinamente pendiente hoy.

---

## Genuinamente sin resolver

1. **Causa de las caídas sincronizadas en Ópera (Sesión 70, nunca cerrado).**
   20-21 equipos de Inframonitor —switches, cámaras, terminales de pago—
   caían exactamente en el mismo segundo, varias veces por semana. Se
   descartó la NIC de gestión del servidor (es ruido L2 normal: tramas RRCP
   de loop-detection entre switches + 802.1Q sin VLAN configurada, no la
   tarjeta fallando). **Nunca se encontró la causa real.** Próximo paso
   sugerido y no iniciado: ver si coincide en el tiempo con algún proceso
   periódico del propio servidor (backup, scan, ciclo del poller).

2. **DNS intermitente del contenedor `shomer-agent`** (Sesión 69) —
   `httpx.ConnectError` al mandar a Telegram, visto varias veces en agosto.
   27 mensajes en 40 días nunca llegaron (`sent_ok=0`). Nunca se investigó
   la causa (resolv.conf del contenedor, systemd-resolved del host, o DNS
   del hotel).

3. **Reinicios del contenedor sin explicar** (Sesión 69) — 42 en 40 días, en
   ráfagas, sin distinguir si era OOM, watchdog, o reinicio manual de una
   sesión de desarrollo. No investigado.

4. **`git filter-repo` pendiente** — un commit viejo (`16be896`) metió BDs al
   historial; ya se sacaron del árbol actual pero siguen en el historial
   remoto. Requiere tu autorización explícita + force-push — no es urgente
   para operar, pero sigue expuesto en el historial de GitHub.

5. **3 hallazgos menores de la Sesión 77, sin reverificar hoy:**
   `/config/save_nodos` (existe la ruta, no se confirmó si el bug reportado
   sigue); 3 rutas proxy sin autenticación propia (mitigadas por firewall,
   no removido el riesgo de fondo); `/tracker/credentials` accesible a
   cualquier operador, no solo admin.

## Ya resuelto (verificar aquí antes de reabrir)

- Puerta trasera de `root` (Sesión 79) — confirmado en código el 13 sep, ya no se autorecrea.
- 4 bots y 4 grupos de Telegram separados por sitio (Tarea pendiente 2, 2 sep) — vigente.
- Reconciliación de IP por MAC (Sesión 73) — además generalizada el 12 sep (ya no depende de una red fija, ver `CLAUDE.md`).
- Sync de flota Ópera↔labs — reemplazado por `tools/fleet_estado.py` + `tools/fleet_sync_core.sh`/`fleet_sync.sh` (12-13 sep), que verifican en cada corrida — el WIP sin commitear que tenían los labs en agosto ya no aplica.
- Regla de firewall Hunter reactivada (11 sep), verificada sana el 13 sep (107→111 IPs bloqueadas, ninguna crítica).

## Referencia rápida que sigue vigente

- **Maestro del código:** Ópera. `tools/fleet_sync_core.sh` (core) / `tools/fleet_sync.sh` (agente).
- **Nunca `git add -A` en ningún sitio** — puede meter `.db`/backups locales. `git status` antes de cada push.
- **NOC:** `/noc` es display, no canal de operación — no inventar alertas ni reintroducir "semáforo rojo" sin pedido explícito.
