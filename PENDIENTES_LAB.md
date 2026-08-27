# Pendientes lab (recordatorio operativo)

Actualizado: **24 ago 2026** · Dueño: Juan Pablo (único operador)

## Sesión 75 (24 ago 2026) — TODO LO HECHO HOY: checklist para verificar que funcionó

Auditoría a fondo de los 28 monitores del bot (por bloques) + `shomer_guardian_nodes.py`
completo del lado network_monitor. Detalle técnico completo de cada uno en `CLAUDE.md`
§Sesión 75 (y sus "cont. 1" a "cont. 6"). Esta lista es solo el checklist de verificación —
qué observar para confirmar que cada fix quedó bien, y con qué commit se hizo.

**Para retomar la próxima sesión, en orden:**
1. Repasar esta lista — marcar qué ya se pudo confirmar en producción real.
2. Seguir el bloque nuevo que quedó abierto: `casador_autoblock_poller.py`,
   `shomer_inframonitor.py` (2230 líneas), `backups.py` (1646 líneas) y el resto de
   `app/api/*.py` de network_monitor — mismo criterio que hoy: un monitor grande a la vez,
   línea por línea, no varios superficiales.
3. Decidir cuándo desactivar el modo mantenimiento (`shomer_maintenance=1`, lo activó Juan
   Pablo a propósito antes del fix de reinicio de Guardian — sigue activo).
4. Tarea pendiente 2/3 (ver más abajo en este archivo) — solo si Juan Pablo las menciona.

**Checklist de verificación — shomer-agent (todos requieren `docker logs shomer-agent`):**

| Fix | Commit | Cómo confirmar que funcionó |
|---|---|---|
| `weekly_backup`/`watch_protector_retry` — `_tick()` faltante | `bc75243` | `/monitores` ya no debe mostrar error pegado ni "sin datos" para estos dos, sobre todo después del próximo domingo 2am (`weekly_backup`) |
| `watch_port_errors` — crash fin de mes | `bc75243` | Revisar que NO haya un error/crash de este monitor el 31 ago 2026 (~07:58) — sería la primera vez que se pone a prueba en producción real |
| `watch_pending_guardian` — fuga de conexión sqlite | `bc75243` | Bajo impacto, sin evidencia observable esperada — solo confirmar que sigue sin errores en `/monitores` |
| 5 monitores agregados a `/monitores` | `bc75243` | Correr `/monitores` en Telegram y confirmar que aparecen `evening_summary`, `watch_infra_pulse`, `watch_pending_guardian`, `watch_memoria_sync`, `watch_pattern_analysis` |
| `core/triage.py` — buffer perdía la etiqueta real | `6283420` | Ya verificado en vivo con simulación — sin pendiente |
| `watch_hunter`/`watch_hunter_verify`/`watch_pipeline` — seed sin reintento | `b663970` | **Ya confirmado en producción real** — log mostró "watch_hunter: 92 IPs pre-existentes cargadas (sin alerta)" tras el deploy |
| `watch_devices` — "recuperado" huérfano en blips | `a3b696e` | Verificado en vivo con simulación — confirmar además que un blip real corto (1-2 min) de algún equipo del agente NO genere un "recuperado" sin su "sin respuesta" antes |
| `daily_summary`/`evening_summary` — fecha día-del-mes + bandera antes de confirmar envío | `8465a6a`, `d28ee65` | Confirmar que el resumen de las 7am y el de las 10pm sigan llegando todos los días sin falta — si alguno falla un día, confirmar que al día siguiente vuelve a intentarlo normal (no se queda "atascado") |
| `watch_log_truncate`/`watch_backups`/`watch_protector_sample`/`weekly_backup` — mismo bug de fecha | `8465a6a` | Sin evidencia observable a corto plazo (requiere >1 mes de uptime sin reinicio para que el bug viejo se manifestara) — no hay nada que revisar pronto |
| `watch_openai` — `_tick()` faltante primeros 10 min de caída | `a27071f` | Solo relevante si `LLM_PROVIDER_INTERACTIVE=openai` está activo (por defecto es Groq) — bajo impacto |
| Modelo Groq retirado del catálogo (`llama-3.3-70b-versatile` → `GROQ_MODEL`) | `82b77c0` | **Revisar que ya NO aparezcan más líneas "model_not_found"/404 en `docker logs shomer-agent`** — antes pasaba cada 15-40 min, ahora no debería pasar nunca más |

**Checklist de verificación — network_monitor (host, `journalctl`/`/var/log/shomer/`):**

| Fix | Commit | Cómo confirmar que funcionó |
|---|---|---|
| `watch_wan_outage` — `UnboundLocalError` | `58eb9b6` (shomer-agent) | Verificado con reproducción aislada + bytecode — falta ver una caída REAL de 2+ grupos/nodos y confirmar que llega "Conectividad WAN"/"Red interna" sin crash |
| `watch_security` → `security_watch.py` movido al host | `9272696`, `c380bfc`, `3556e89` | **2 rondas de ruido real ya encontradas y corregidas** (24-26 ago): (1) `deploy.sh` marcado como "copia sensible" — corregido con `_has_trusted_ancestor()`, confirmado con un deploy real sin alertas y la cadena de procesos verificada vía `/proc`; (2) login SSH diario de las 03:00 desde `127.0.0.1` marcado como "horario inusual" — corregido ignorando IPs loopback. **Sigue en observación** — dado el patrón de 2 rondas seguidas, no darlo por estable todavía, revisar de nuevo la próxima vez que se retome |
| Logging sin formato (`logging_setup.py`) | `c3688a6` | **Revisar que la próxima vez que salga un `logger.warning()` real en `api.log`/`tools_api.log`, aparezca con formato `fecha [NIVEL] nombre: mensaje`** en vez de la línea pelada de antes |
| `shomer_guardian_nodes.py` — reinicio antes de confirmar offline | `b32ef48` | Verificado con 3 simulaciones directas — sin cambio de comportamiento mientras `guardian.fail_threshold` (hoy: 3) siga >= `offline_persist_ticks` (hoy: 3, por defecto). Solo importa si alguien baja el threshold del panel en el futuro |
| `security_watch.py` — falso positivo login SSH localhost 03:00 diario | `3556e89` | Verificado en vivo (loopback ignorado, IP externa sigue alertando) — confirmar que ya no aparezca la alerta diaria de las 03:00 |
| `shomer_inframonitor.py` — cooldown de `_send_infra_alert` bloqueaba "recuperado" | `a926b39` | Código inactivo hoy (`INFRA_TELEGRAM_PANEL` no configurado) — sin nada que observar en producción a menos que se active esa variable en el futuro |
| `backups.py` — staging SSH (`_backup_linux`) nunca se limpiaba entre corridas | `59fc71b` | Código inactivo hoy (sin equipos Linux/macOS configurados para backup) — verificar que el directorio de staging quede vacío después de cada corrida el día que se configure el primer equipo Linux |

## Sesión 74 (cont.) — reportes 07:00/22:00 unificados, falta ver el primero en vivo

`watch_docker`/`watch_network_audit`/`watch_port_errors` ya no mandan mensaje suelto -- anotan
en una libreta compartida (`notas_reporte`, `knowledge.db`) que dos reportes leen y vacían:
07:00 (completo) y 22:00 (liviano, o "sin novedades"). Ver `CLAUDE.md` §Sesión 74 (cont.).

**Pendiente real:** no se pudo confirmar en vivo porque no dio tiempo de esperar a que llegaran
las 07:00/22:00 reales durante la sesión. Revisar mañana que el de las 07:00 salió bien (con las
notas si hubo alguna) y esta noche que el de las 22:00 también.

## Sesión 74 — resuelto: un solo canal de Telegram (Opción 2), falta probar el respaldo

Juan Pablo detectó a mano una diferencia real entre mensajes vistos (~130 un día) y registrados
(23) — causa: el canal directo de Guardian, sin filtros ni registro. **Implementado y verificado
en vivo con un evento real:** Guardian ya no manda directo, encola para que el bot lo releve con
formato/auditoría consistente; si el bot no contesta en 60s, Guardian manda directo como
respaldo. Ver `CLAUDE.md` §Sesión 74 para el detalle técnico completo.

**Pendiente real:** el camino de respaldo (bot caído → Guardian manda directo) nunca se probó en
vivo — hay que apagar el bot a propósito, dejar pasar un evento, y confirmar que igual llega.
No se hizo el 24 ago para no interferir con la comparación de conteos en curso.

**Pendiente separado:** confirmar con unos días más de `telegram_enviados.db` que el conteo del
sistema por fin coincide con lo que Juan Pablo cuenta a mano en su Telegram — la comparación en
vivo del 23-24 ago cerró mucho la brecha (14 vs 18, contra 23 vs 130 de antes) pero no exacto.

## ⭐ TAREA PENDIENTE 3 — monitorear unos días antes de seguir (checkpoint)

Tras el repaso completo de sensibilidad/alertas (Sesión 72-73 + Tarea pendiente 2), Juan Pablo
decidió **dejar correr el sistema un par de días con los arreglos ya desplegados antes de tocar
nada más** — en vez de seguir agregando cambios sin ver primero si los de hoy funcionan solos.

**Evaluación honesta que quedó como base para retomar (no repetir, solo releer):**
- Los filtros de hoy SÍ mejoran la eficacia — verificado con datos reales del 15 ago (582 eventos
  reales, solo 41 mensajes, sin nada que quedara caído de verdad sin avisar).
- Cada supresión tiene una salvaguarda pensada (tope de 10min en caída masiva, el patrón crónico
  nunca se calla del todo, la recuperación repetida nunca oculta la falla original, y desde hoy
  **nada se borra de verdad** — todo lo suprimido queda en `eventos_filtrados` para auditar).
- **El hueco honesto que sigue abierto:** no existe todavía una capa de "esto es crítico de
  negocio" (datáfono ≠ AP de pasillo vacío) — un patrón crónico en un equipo importante se trata
  igual que uno sin importancia. Es la opción 4 de la Tarea pendiente 2, sin implementar.

**Al retomar, revisar en este orden:**
1. `python3 tools/reporte_alertas_semanal.py --days N` (N = días transcurridos desde el 15 ago)
   — confirmar que el volumen de mensajes se mantuvo bajo y razonable.
2. Revisar `eventos_filtrados` (network_monitor.db y knowledge.db) — ¿algo se suprimió que en
   retrospectiva no debió suprimirse? Con el registro nuevo ya se puede responder esto con datos.
3. Si todo se ve bien → seguir con **Tarea pendiente 2**, priorizando la capa de criticidad de
   negocio (opción 4), que es la que más directamente cierra la preocupación de Juan Pablo.

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
