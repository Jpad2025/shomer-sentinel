# Pendientes lab (recordatorio operativo)

Actualizado: **13 ago 2026** · Dueño: Juan Pablo (único operador)

## Sesión 71 — resuelto: spam Telegram por AP flapeando (OFC-COCINA)

54 mensajes Telegram en 24h, 44 de ellos "Nodo recuperado — AP OFC-COCINA" repetido (ver
`CLAUDE.md` §Sesión 71). Causa: el aviso de recuperación no pasaba por la ventana de
agregación que sí protege el lado de las caídas desde Sesión 69/v1.1.0. **Fix desplegado**
v1.1.1 (`shomer-agent` commit `2bf8202`) — propagado a Ópera + shomer205/243/245 vía
`fleet_sync.sh`. Falta confirmar con datos reales (`memoria.db`) que bajó el volumen.

## Sesión 70 — causa de caídas sincronizadas en Ópera (NO resuelto)

Durante la auditoría de Ópera (ver `CLAUDE.md` §Sesión 70) se confirmó, con datos reales
(no solo conteos), que **20-21 equipos completamente distintos** del hotel — switches,
cámaras, terminales de pago, etc., todos monitoreados por **Inframonitor** — caen
**exactamente en el mismo segundo**, varias veces por semana. Eso descarta 20 fallas
físicas independientes: hay una causa compartida.

**Se investigó y se descartó** la tarjeta de red de gestión del servidor (`eno1`) como
causa: descarta paquetes en vivo (~5-6/s constante) pero sin ninguna señal de tarjeta
fallando (no promiscua, Suricata en NIC USB aparte, `ethtool -S` casi limpio, `fq_codel`
sin descartes). Es más compatible con ruido normal de broadcast/multicast del hotel que
con el evento sincronizado.

**Re-verificado en vivo 13 ago (addendum `CLAUDE.md` §Sesión 71):** el "dropped" de `eno1`
(~5.19 pkt/s medido en vivo, igual que antes) coincide con tramas **RRCP** (loop-detection
propietario Realtek entre switches, sin manejador en Linux → siempre cuenta como drop) desde
5 switches distintos + tramas 802.1Q sin interfaz VLAN configurada en el host. Es ruido L2
normal de los switches del hotel, no la tarjeta fallando. Descartada con más detalle, pero
sigue sin identificarse la causa de la caída sincronizada.

**Sin causa raíz confirmada todavía.** Próximo paso sugerido (no iniciado): revisar si las
caídas simultáneas coinciden en el tiempo con algún proceso periódico del servidor —
backup Protector, algún scan, o el propio ciclo del poller Inframonitor — antes de asumir
causa de red física.

**Separado, y sí confirmado como físico:** 7 equipos con >100 caídas cada uno (incl. 2
switches y 2 terminales Ingenico) — problema de cable/puerto/PoE local a ese hardware de
Ópera, no algo que se replique a otro hotel. **Acción: revisión física de campo.**

## Sesión 69 — pendientes de investigación (no resueltos, solo documentados)

Salieron de un análisis de `memoria_alertas.db` (1535 msgs Telegram, 40 días).
Los fixes de ruido (VPN digest + alertas compactas para flappers) ya están en
`CLAUDE.md` §Sesión 69 y desplegados. Estos tres NO se tocaron:

1. **Bixolon POS `.60`/`.243`** — 94 caídas c/u en 40 días. Confirmado como
   patrón crónico en `patrones_detectados`, no es bug de software. **Acción:
   revisión física de campo** (cable/PoE/firmware) — agregado a `SITE.md`
   Pendientes → Campo #3.
2. **DNS intermitente del contenedor `shomer-agent`** — `Telegram send error:
   httpx.ConnectError: [Errno -3] Temporary failure in name resolution`, visto
   en journalctl el 1, 2 y 5 de agosto. Causa mensajes con `sent_ok=0` en
   `memoria_alertas` (27 en 40 días) — alertas generadas que nunca llegaron a
   Telegram. No se investigó causa raíz (¿resolv.conf del contenedor?
   ¿systemd-resolved del host bajo carga? ¿DNS del hotel intermitente?).
3. **Reinicios del contenedor `shomer-agent`** — 42 reinicios en 40 días, no
   uniformes: ráfagas concentradas (20 entre 29-30 jun, 6 el 30 jun entre
   00h-05h, otras el 8 jul y 17 jul). No se investigó si es OOM, watchdog,
   Docker restart policy reaccionando a un crash, o reinicios manuales de
   sesiones de desarrollo previas — journalctl no distingue el motivo.

## Sync pendiente — labs .245 / .243 (Sesión 69)

Al sincronizar el fix de Sesión 69 se encontró que `.245` y `.243` tienen
`core/` con cambios **sin commitear** que van más allá de su propio HEAD de git
(`1cc8222` — varios commits atrás de `main`): diffs en `bot.py`,
`groq_helper.py`, `monitor.py` (307 líneas), `pattern_analysis.py`,
`pulse_correlate.py`, `shomer_api.py`, `tools.py`, `ui_notify.py`,
`docker-compose.yml`. No se tocó ninguno de los dos para no arriesgar ese
trabajo en progreso sin entender qué es. **Antes de sincronizar Sesión 69 ahí:**
revisar con Juan Pablo qué es ese WIP, commitearlo (o descartarlo a propósito),
y recién entonces hacer `git pull` limpio como se hizo en `.205`.

## Tokens Telegram lab (SIN conflicto ahora)

| Host | Bot | Token |
|------|-----|-------|
| Ópera | ON | producción (exclusivo) |
| .245 (`shomer245`) | ON | token lab actual |
| .205 | OFF / disabled | ⏳ crear token BotFather propio |
| .243 | OFF / disabled | ⏳ crear token BotFather propio |

**Regla:** un token = un poller. No compartir. No usar el de Ópera en labs.

**Cuando lo hagas (más tarde):**
1. BotFather → nuevo bot por host
2. Poner `TELEGRAM_BOT_TOKEN` (+ chat) en `/storage/shomer-agent/.env` de ese host
3. `sudo systemctl enable --now shomer-agent.service`
4. Verificar: `docker exec shomer-agent date` (Bogotá) y 0 Conflicts en logs

## Memoria `/guardar` → decisiones (siguiente nivel)

Ya existe `knowledge_decision()` (consejo en alertas/IA, no piloto auto).

Mejoras posibles (priorizar cuando digas adelante):
1. Botón rápido "Falso positivo Hunter" / "Fue cable/PoE" (tags limpios sin depender del texto libre)
2. Resumen diario: bloque "lo que aprendimos esta semana" desde knowledge.db
3. Regla suave: si 3+ reinicios resolvieron el mismo AP → sugerir `no_reboot` o mantenimiento (solo sugerencia)
4. Chat IA: tool explícita `consultar_memoria(ip)` siempre inyectada al diagnosticar
5. Export `/bitacora` + knowledge a CSV mensual para el hotel

## Sync código

- Maestro: Ópera
- Agente: git `shomer-agent` (push desde Ópera OK)
- Core `/opt/network_monitor`: sync rsync **sin** `--delete`, **sin** SITE.md / .env / *.db
- Nunca `git add -A` a ciegas en labs (puede meter BDs locales)
- **28 jul:** sync NOC (`noc.html`, `shomer_noc.py`, `alerts.py`) + bloque IA + tipografía soporte USB + docs Ópera → `.205` / `.245` / `.243` + push GitHub (`shomer-sentinel` / `shomer-agent`)

## NOC (pantalla)

- `/noc` = TV / operaciones (misma plantilla en labs; token local por sitio)
- No inventar alertas Telegram nuevas desde el NOC (Guardian/Infra/Hunter ya alertan)
- No reintroducir vista “semáforo rojo” / `/noc/tecnico` sin pedido explícito

## Limpieza git (seguridad)

Commit `16be896` metió BDs/backups por error; `de79dcd` los quitó del árbol actual.
⏳ Pendiente (requiere tu OK + force-push): `git filter-repo` para borrarlos del historial remoto.

## Push seguro (git)

- **Nunca** `git add -A` en labs: puede meter `*.db` / backups locales.
- Antes de push: `git status` — solo código/docs; 0 archivos `.db` / `.tar.gz`.
- `SITE.md` y `.env` no van a git.
- HEAD actual sin BDs trackeados. Historial antiguo (`16be896`) aún tiene blobs hasta filter-repo (requiere OK + force-push; no urgente para operar).

## Pruebas pendientes (dejar correr; recordar)

Cuando pruebes a mano (Ópera / Telegram):

1. **Tags memoria:** tras reboot o alerta → botones Reinicio resolvió / Cable/PoE / Falso positivo
2. **Chat IA:** preguntar por una IP y verificar que use `consultar_memoria` (antecedente/consejo)
3. **Horarios Bogotá:** mañana ~08:00 — resumen diario + informe puertos (mismo briefing)
4. **Noche sin spam:** mant. logs / preventivo / backup semanal — Telegram solo si fallan
5. **Tokens lab (más tarde):** BotFather propio para .205 y .243; hasta entonces bot OFF

No es urgente. Sistema en marcha.
