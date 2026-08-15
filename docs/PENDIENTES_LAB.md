# Pendientes lab (recordatorio operativo)

Actualizado: **14 ago 2026** · Dueño: Juan Pablo (único operador)

## ⭐ TAREA PENDIENTE 2 — rediseñar cuándo interrumpe Shomer al técnico (sin resolver)

**El problema real, en palabras de Juan Pablo:** el técnico tiene Telegram encima todo el
tiempo, pero puede tener 2-3 hoteles a la vez con Shomer cada uno — el ruido de todos se suma
en el mismo chat. "Shomer debe ser una herramienta de ayuda, no de desesperación." Hoy el
sistema trata cada evento igual (manda mensaje), sin distinguir qué de verdad amerita
interrumpir a alguien que reparte su atención entre varias propiedades.

**6 opciones propuestas para la regla de "cuándo interrumpe" (con lo que ya existe hoy en el
sistema), pendientes de que Juan Pablo diga cuáles aplican:**

1. **Por si el auto-reboot de Guardian ya lo intentó arreglar solo** — si funcionó, no
   interrumpe; si falló, sí (hoy esa información se genera pero no se usa para decidir).
2. **Por si es arreglable remoto vs. solo en sitio** — cable/fuente/router del hotel = nadie lo
   arregla desde el teléfono, no interrumpir ya; backup/servicio Shomer/bloqueo de seguridad =
   sí se puede resolver remoto, interrumpir.
3. **Por patrón ya diagnosticado** (`pattern_analysis`, 5+ ocurrencias) — nunca más interrumpe
   en tiempo real, solo aparece en el resumen de la próxima visita.
4. **Por criticidad de negocio del equipo**, no por "cayó" — datáfono/PMS ≠ AP de pasillo vacío.
5. **Backup y seguridad, siempre inmediato** — sin excepción (ya es así hoy, no tocar).
6. **Caída masiva del gateway, un solo mensaje** — ya casi implementado desde Sesión 72/73.

**Estado:** solo conversación/diseño, **nada implementado todavía**. Retomar cuando Juan Pablo
diga "tarea pendiente 2".

## Sesión 73 — resuelto: reconciliación automática de IP por MAC

`app/api/shomer_mac_reconcile.py`, corriendo ya (cada 30 min, junto con `shomer-guardian.service`).
Caso real que lo motivó: AP LOBBY RECEPCION cambió de `.121` a `.137` sin que nadie lo notara —
corregido a mano una vez, y de ahora en adelante el sistema lo hace solo cuando pase de nuevo.
Herramienta manual también disponible: `python3 tools/detectar_cambio_ip.py`. Ver `CLAUDE.md`
§Sesión 73 para el detalle técnico (por qué no se pudo usar `nmap -sn` directamente).

**Resuelto 14 ago:** el equipo Bixolon `.60` (94 caídas en 40 días, ver Sesión 69) no había
cambiado de IP — su MAC no aparece en ningún lado del escaneo en vivo (ni siquiera vía ARP,
que no depende de que el equipo responda ping). Confirmado como desconectado de verdad, no un
falso positivo. **Desactivado** en `infra_devices` (id 27, `active=0`) a pedido de Juan Pablo —
deja de pingearse y de generar alertas. Nota: al desactivarlo también queda fuera del chequeo
de reconciliación por MAC (Sesión 73) — si el equipo físico vuelve a conectarse algún día, no
se va a re-ubicar solo, hay que reactivarlo a mano.

## Sesión 72 (cont.) — causa real de las caídas masivas GRANDES: gateway del hotel

**Encontrado 14 ago, en pausa a pedido de Juan Pablo (retomar después):** el gateway del hotel
(`192.168.0.1`) se cae de verdad con frecuencia — confirmado en el log real (`shomer-inframonitor-poller`,
13 ago 10:20:26: "gateway offline, 100% pérdida" justo cuando cayeron 22/22 equipos de Inframonitor
a la vez). **No es un bug de Shomer — es la red física del hotel** (router/ISP). Ya se detecta y
se silencia bien por `host_network_blip` (mecanismo clásico, no el nuevo de hoy).

**Frecuencia real (tabla `infra_blip_events`):** **509 veces en julio, 125 en lo que va de agosto**
— ~17/día en julio, bajando en agosto. 36 días distintos con al menos una caída de gateway.

**Pendiente de decidir:** esto ya no es un problema de software para seguir investigando por acá —
es candidato a revisión física del router/ISP del hotel. Falta: (a) confirmar con Juan Pablo si
vale la pena escalarlo al hotel/proveedor de internet, (b) separado y sin resolver todavía: el
grupo más chico de caídas masivas (algunos equipos, no todos, con el gateway viendo sano) —
ese es el que Sesión 72 mitigó pero cuya causa de fondo sigue sin identificarse.

## Sesión 72 — mitigado: caída masiva se suprime aunque el gateway se vea sano

Los 5 incidentes de caída masiva de Sesión 70 (8-24 equipos a la vez) nunca activaron el
guardia `host_network_blip` porque exigía que el gateway también se viera mal, y nunca pasaba
(confirmado cruzando `status_events` contra `infra_blip_events`). `tools/analizar_caidas_masivas.py`
(nuevo, solo lectura) los clasifica: los 5 tienen firma de falso positivo (recuperación rápida
y sincronizada). **Fix desplegado:** ahora se suprime igual con umbral puro de caída masiva
(8+/20+/50%), con tope de seguridad de 10 min (`INFRA_BLIP_MASS_MAX_SEC`) para no tapar una
falla ancha genuina si sigue después de eso. Ver `CLAUDE.md` §Sesión 72 para el detalle.
**Falta confirmar en vivo** con la próxima caída masiva real (no se pudo probar sin forzar una).
Causa raíz de fondo (por qué caen juntos) sigue sin identificar — RRCP de los switches del
hotel se investigó y se descartó como explicación (ver addendum §Sesión 71 en `CLAUDE.md`).

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
