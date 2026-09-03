# Pendientes lab (recordatorio operativo)

Actualizado: **2 sep 2026** · Dueño: Juan Pablo (único operador)

## Sesión 77 (27 ago 2026) — revisión EXHAUSTIVA COMPLETADA: 112/112 archivos de network_monitor

Detalle completo en `CLAUDE.md` §Sesión 77. Resumen ejecutivo:
- Se terminaron los ~64 archivos que quedaban de la Sesión 76. **Los 112 archivos de
  network_monitor quedan revisados, sin excepciones.**
- 🔴 **Seguridad, reportado, NO corregido (decisión de diseño pendiente):** `auth_api.py`
  recrea sola la cuenta de fábrica `root` (password `shomer2026`) cada vez que se usa el panel,
  aunque se borre. Confirmado que existe HOY en la BD de Ópera.
- 🟡 **Seguridad, corregido y desplegado (2 rondas, mismo patrón de Sesión 76):** 4 rutas más
  sin enmascarar en `audit_log` (`/setup/apply`, `/api/topology/config`, `/backups/b2config`,
  `/tracker/asset/*`) — sin exposición histórica confirmada en ninguna.
- 5 hallazgos menores reportados, sin corregir (requieren tu decisión):
  `/config/save_nodos` roto (bajo impacto), 3 rutas proxy sin auth propia (mitigadas por
  firewall), `/tracker/credentials` accesible a cualquier operador (no solo admin), drill
  manual/automático sin mutex compartido, y una corrección: `backend/scripts/discovery.py`
  no es código muerto (se corrigió ese hallazgo de sesiones previas).
- `app/scripts/monitor.py` confirmado dormido (no existe la unidad systemd pese a estar
  documentada en la Parte A de CLAUDE.md).

**Resuelto el mismo día (27 ago, tras confirmar que solo Juan Pablo usa el sistema hoy):**
- Mutex compartido del drill manual/automático — arreglado y desplegado en Ópera + 3 labs.
- Contraseña de `root` cambiada en Ópera (no en labs, no documentada aquí por seguridad).
- Código muerto confirmado (`database.py`, `models.py`, `backend/routes/` completo,
  `ssh_recovery.py`, `reboot_playwright.py`, `router_http_manager.py`, `backup_system.py`)
  movido a `_archivo_obsoleto/` — verificado que los servicios siguen arrancando limpios.

**Para retomar, en orden:**
1. Decidir sobre la puerta trasera `root` en `auth_api.py` — sigue auto-recreándose con la
   contraseña de fábrica original si se borra la cuenta (cambiar la contraseña no arregla esto).
2. Decidir acceso a `/tracker/credentials` (¿solo admin?).
3. Guardar en archivo protegido las credenciales legado extraídas en Sesión 76 (bloqueado por
   el clasificador de seguridad de la sesión de Claude — hacerlo manualmente o ajustar permiso).
4. Rotar las 2 credenciales expuestas desde Sesión 76 — entra en la auditoría de seguridad que
   Juan Pablo hará más adelante.
5. Decidir qué hacer con el código dormido restante (`auto_recovery.py`, `reboot_glinet.py`,
   `inventory_sync.py`, `monitor.py`) — no se movió esta vez, solo el código 100% muerto.
6. Rotar las 2 credenciales expuestas desde Sesión 76 (dominio de red, usuario panel).
7. Tarea pendiente 2/3, solo si se piden.

---

## Sesión 76 (26-27 ago 2026) — revisión EXHAUSTIVA de TODO network_monitor (~48/112 archivos)

Detalle completo de hallazgos en `CLAUDE.md` §Sesión 76. Resumen ejecutivo:
- 🔴 **Seguridad, corregido**: `audit_log` guardaba contraseñas reales en texto plano en 6
  rutas (`/tracker/credentials`, `/backups/devices*`, `/api/router-devices`, `/auth/*`).
  Ya corregido en código + redactadas las 21 (Ópera) + 6 (shomer205) filas históricas
  afectadas, con backup de la BD hecho antes de tocar nada.
- **Pendiente de decisión:** rotar la contraseña de dominio de red y la contraseña de usuario
  del panel que estuvieron expuestas desde junio 2026.
- 4 bugs de código reales corregidos: crash de PDF con emoji (`inventory_asset_report_pdf.py`),
  y 3 ocurrencias independientes de "success falso" al recargar Suricata.
- Hallazgo de negocio señalado (no corregido, requiere decisión): `shomer_technician.py` da
  nota perfecta a un técnico sin reinicios en el mes.
- Bastante código muerto/dormido confirmado (ver CLAUDE.md) — no se tocó por no causar daño.

**Para retomar, en orden:**
1. Decidir sobre la rotación de las 2 credenciales expuestas.
2. Continuar la revisión archivo por archivo — **quedan ~64 de 112**:
   `auth_api.py`, `web_ui.py`, `backend/protector.py`, `shomer_config.py`, `shomer_setup.py`,
   `shomer_proxies.py`, `casador_blocking.py`, `shomer_reports.py`, `shomer_audit_network.py`,
   `shomer_noc.py`, `shomer_status_events.py`, `inventory.py` (completo, solo se vio una ruta),
   `inventory_discovery.py`, `inventory_excel_export.py`, `inventory_label_pdf.py`,
   `shomer_guardian_server_health.py` (completo, solo se vio el WAN failsafe),
   `shomer_guardian_health_checks.py` (completo), `shomer_guardian_lib.py` (completo),
   `shomer_system_status.py`, `shomer_incidents.py`, `shomer_host_health.py`,
   `shomer_audit_export.py`, `shomer_topology.py`, `shomer_network_blip.py`,
   `casador_support_firewall.py`, `casador_blocking.py`, `scripts/restore_drill.py` (revisar
   cruce con `shomer_drill.py::_drill_running` — ¿usan el mismo flag de "drill en progreso"?),
   `scripts/scanner.py`, `scripts/monitor.py`, `scripts/tracker/discovery.py`,
   `scripts/tracker/persistence.py`, `scripts/tracker/extractor.py`,
   `scripts/tracker/lldp_helper.py`, `backend/scripts/discovery.py`, y el resto de archivos
   pequeños de `backend/scripts/`. Mismo criterio: uno por uno, sin decidir cuáles importan
   menos.
3. Seguir el checklist de verificación de la Sesión 75 (abajo) — sigue vigente.
4. Decidir cuándo desactivar el modo mantenimiento.
5. Tarea pendiente 2/3, solo si se piden.

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

## ⭐ TAREA PENDIENTE 3 — checkpoint de monitoreo — ✅ CERRADA (2 sep 2026)

Tras el repaso completo de sensibilidad/alertas (Sesión 72-73 + Tarea pendiente 2), Juan Pablo
decidió dejar correr el sistema un tiempo con los arreglos ya desplegados antes de tocar nada
más. Al retomar (2 sep 2026), se corrió el checklist completo:

1. `reporte_alertas_semanal.py --days 19` (desde el 15 ago): 449 mensajes Telegram en 19 días,
   170 caídas agrupadas por `host_network_blip` evitaron ~4085 alertas individuales, 17
   incidentes crónicos agrupados en digest (solo 1 escalado al coordinador). Volumen sano.
2. Revisión de `eventos_filtrados` (network_monitor.db y knowledge.db), 19 días: 3708 eventos
   suprimidos, prácticamente todos `blip_gateway`/`blip_masivo` (caída de gateway o masiva —
   exactamente el caso previsto), repartidos parejo entre equipos (nada indicando que un equipo
   puntual se estuviera ignorando en silencio). **Nada se suprimió mal.**
3. Con el checkpoint sano, se pasó a la Tarea pendiente 2 (ver abajo).

## ⭐ TAREA PENDIENTE 2 — rediseñar cuándo interrumpe Shomer al técnico — parcialmente resuelta (2 sep 2026)

**El problema real, en palabras de Juan Pablo:** el técnico puede atender 2-3 hoteles a la vez,
cada uno con su propio Shomer, y recibe Telegram encima todo el tiempo. "Shomer debe ser una
herramienta de ayuda, no de desesperación." Hoy el sistema trata cada evento igual (manda
mensaje), sin distinguir qué de verdad amerita interrumpir a alguien que reparte su atención
entre varias propiedades.

**Corrección de premisa (2 sep 2026):** inicialmente se asumió que el ruido de varios hoteles se
mezclaba en un mismo chat de Telegram — Juan Pablo aclaró que **cada hotel/cliente tiene (o debe
tener) su propio bot y su propio grupo de Telegram, nunca compartido**. Al auditar, se encontró
que en la práctica shomer243 y shomer245 sí compartían el bot de shomer205 (clonado por
`fleet_sync.sh` sin regenerar), y los 4 sitios compartían el mismo chat personal de Juan Pablo —
se corrigió: 4 bots y 4 grupos de Telegram separados (Ópera, 205, 243, 245), cada uno verificado
con mensaje de prueba. Detalle en memoria del asistente (`project_shomer_telegram_por_hotel`).

**6 opciones propuestas para la regla de "cuándo interrumpe":**

1. **Por si el auto-reboot de Guardian ya lo intentó arreglar solo** — si funcionó, no
   interrumpe; si falló, sí. **✅ Implementado 2 sep 2026** (`watch_guardian_nodes`,
   `core/monitor.py`): ya no se manda el aviso inmediato de "reinicio automático"; si a los 3 min
   el equipo sigue caído, ahí sí avisa (crítico), igual que antes. Si vuelve solo, queda
   registrado en `eventos_filtrados` (`motivo=auto_reboot_exitoso`), sin interrumpir.
2. **Por si es arreglable remoto vs. solo en sitio** — cable/fuente/router del hotel = nadie lo
   arregla desde el teléfono; backup/servicio Shomer/bloqueo de seguridad = sí se puede resolver
   remoto. **No se implementó aparte** — se decidió que el hueco real que buscaba cerrar ya queda
   cubierto por las opciones 3+4+6 (abajo), y aplicarla tal cual habría apagado el aviso
   inmediato de un router/gateway caído, que la opción 4 clasifica como crítico y la opción 6 ya
   resuelve con un solo mensaje. Revisar si en el futuro aparece un caso concreto no cubierto.
3. **Por patrón ya diagnosticado** (`pattern_analysis`, 5+ ocurrencias) — nunca más interrumpe en
   tiempo real. **✅ Implementado 2 sep 2026** (`watch_guardian_nodes` y `watch_infra`,
   `core/monitor.py`): antes solo se acortaba el mensaje; ahora, si es patrón crónico, no se
   manda nada en tiempo real — queda registrado (`motivo=patron_cronico`) para el resumen.
4. **Por criticidad de negocio del equipo**, no por "cayó" — datáfono/PMS ≠ AP de pasillo vacío.
   **✅ Implementado 2 sep 2026**, solo en Inframonitor (Guardian/APs no tienen subtipo, todos
   son `access_point`): usa `infra_devices.device_type` — `pos`, `router`, `server`,
   `controller`, `switch` avisan de inmediato; `printer` (no-POS) y `camera` quedan para el
   resumen (`motivo=no_critico`). Tipos configurables por `INFRA_CRITICAL_DEVICE_TYPES` en
   `.env`. La recuperación de un equipo silenciado tampoco avisa (evita el "recuperado" de algo
   que nunca se avisó como caído) — registrado como `motivo=recuperacion_no_avisada`.
5. **Backup y seguridad, siempre inmediato** — sin excepción. Ya era así antes, no se tocó.
6. **Caída masiva del gateway, un solo mensaje** — ya resuelto desde Sesión 72/73, no se tocó.

**Estado:** opciones 1, 3 y 4 desplegadas y verificadas en Ópera + los 3 labs (205/243/245),
commits `0f7fb28` (opciones 1 y 3) y `c9e7e1e` (opción 4) en `shomer-agent`. Opción 2 descartada
por redundante/riesgosa tal como estaba planteada. Opciones 5 y 6 sin cambios (ya correctas).
Pendiente real que queda: ninguna de las 6 sin resolver — solo observar unos días que el volumen
de mensajes bajó de verdad con 3 y 4 activas (repetir el checklist de la Tarea pendiente 3).

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
