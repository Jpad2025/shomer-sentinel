# Auditoría técnica: `_poll_once()` — Inframonitor

**Archivo auditado:** `app/api/shomer_inframonitor.py` (función `_poll_once`, líneas ~665–880)  
**Fecha auditoría:** 24 jun 2026  
**Contexto:** ciclo cada 30 s; en Hotel Ópera ~52 equipos activos, ~9 con SNMP; poller standalone (`app/scripts/inframonitor_poller.py`) o embebido en Guardian si no hay `shomer-inframonitor-poller.service`.  
**Estado:** solo informe — **sin cambios de código aplicados** en el momento de redactar este documento.

**Documento ampliado:** ver `AUDITORIA_POLLERS_CONSOLIDADA.md` — auditoría de `inframonitor_poller.py`, `_poller_tick()`, Redis, offline, 24/7, arquitectura y **plan de cambios completo** (Fases A–F).

---

## 1. Resumen ejecutivo

`_poll_once()` está bien estructurado en fases (lectura → red en paralelo → escritura), con mejoras reales respecto a versiones anteriores:

- Pool de hilos ampliado (`INFRA_THREAD_WORKERS=48`)
- Ping de 3 paquetes + estado `degraded` (Sesión 61 / §BC)
- Detección `host_network_blip` (corte transitorio del propio host)
- `record_status_event(conn=)` para evitar auto-contención SQLite (Sesión 60 / §BB)

Aun así, concentra riesgos de estabilidad y rendimiento:

- Operaciones síncronas de SQLite y Redis dentro de una coroutine `async`
- Transacción de escritura larga (un `commit` al final de N equipos)
- Saturación del thread pool cuando N equipos ≫ workers (ping+tcp en paralelo = 2×N tareas)
- Duración del ciclo que puede superar ampliamente los 30 s previstos
- Fase de escritura sin `try/except` → pérdida silenciosa de todo el ciclo ante una excepción

---

## 2. Flujo del ciclo (referencia)

```
1. Lectura SQLite (sync, sin to_thread)
2. ping ∥ tcp  → asyncio.gather (hasta 2×N tareas en thread pool)
3. Detección host_network_blip (get_config → SQLite sync)
4. MAC lookups (paralelo, solo online/degraded)
5. SNMP polls (paralelo, solo con comunidad)
6. Escritura SQLite + Redis (sync, transacción única, bucle N equipos)
7. create_task(Telegram) en transiciones offline reales (opcional, INFRA_TELEGRAM_PANEL=1)
```

**Archivos relacionados:**

| Archivo | Rol |
|---------|-----|
| `app/api/shomer_inframonitor.py` | `_poll_once`, helpers red/SNMP, `_poller_loop` |
| `app/scripts/inframonitor_poller.py` | Runner standalone con compensación de intervalo |
| `app/api/shomer_common.py` | `get_db()`, `get_redis()`, `get_config()` |
| `app/api/shomer_status_events.py` | `record_status_event()` |
| `app/api/main.py` | Arranque poller embebido si no hay servicio externo |

---

## 3. Hallazgos críticos

### C1 — Escritura SQLite síncrona y transacción larga (riesgo de bloqueo / contención)

**Ubicación:** bloque `with get_db() as conn:` líneas ~769–880.

- Una sola transacción recorre **todos** los equipos antes de `commit`.
- Por equipo: `UPSERT` en `infra_status`, posible `INSERT` en `infra_events`, `record_status_event()` → `status_events`, hasta **3 `redis.setex`**.
- SQLite WAL: un solo escritor; Guardian, Hunter, Protector y el poller comparten `network_monitor.db` (`busy_timeout=10` vía `get_db()`).
- Oleadas de transiciones (reales o falsas) alargan la ventana de lock y pueden afectar `/health`, autobloqueo Hunter, etc. (patrón documentado en Sesiones 58–60, CLAUDE.md §AT–§BB).

**Impacto:** bloqueo del event loop si el poller va embebido en Guardian; contención SQLite en cualquier despliegue.

---

### C2 — Lectura SQLite inicial síncrona dentro de `async def` (sin `to_thread`)

**Ubicación:** líneas ~667–676.

- `with get_db()` + `fetchall` en el hilo del event loop.
- Si choca con otro escritor, puede esperar hasta 10 s bloqueando el loop (crítico si poller embebido en Guardian).

**Nota:** en poller standalone el daño es menor (proceso dedicado), pero retrasa manejo de `SIGTERM` durante locks largos.

---

### C3 — El ciclo puede durar mucho más de 30 s

Estimación peor caso por equipo (un hilo):

| Operación | Timeout / peor caso |
|-----------|---------------------|
| `_ping` (3 pkt, `-W 2`) | `PING_COUNT*2+3` = **9 s** |
| `_tcp_check` | **3 s** |
| `_get_mac` | **3 s** |
| `_snmp_poll` | probe v2c+v1 (~12 s) + walk v2c (14 s) + impresora (6 s) ≈ **32 s** |

Con N equipos y pool de 48 hilos:

- Fase ping+tcp: hasta **2N** tareas simultáneas.
- Con 52 equipos → 104 tareas → ~3 oleadas; ping puede acercarse a **~27 s** si muchos timeouts.
- SNMP añade hasta **~32 s** (equipo SNMP más lento).

**Total realista Ópera:** 40–60 s en condiciones adversas.

| Modo | Comportamiento intervalo |
|------|-------------------------|
| Standalone (`inframonitor_poller.py`) | `wait = max(0.1, 30 - elapsed)` — compensa parcialmente |
| Embebido (`_poller_loop`) | `await asyncio.sleep(30)` **después** del poll — intervalo efectivo **30 + duración_poll** |

---

### C4 — Saturación del thread pool (2N tareas en fase 1)

**Ubicación:** líneas ~689–698.

```python
ping_results, tcp_results = await asyncio.gather(
    asyncio.gather(*ping_tasks, ...),
    asyncio.gather(*tcp_tasks, ...),
)
```

- Ping y TCP corren **a la vez** → hasta **2×N** hilos demandados.
- Con `INFRA_THREAD_WORKERS=48` y N=52, hay cola inevitable.
- Efecto histórico (Sesión 58, §AU): pings en cola → timeouts → falsos `offline` (flapping).

---

### C5 — Fase de escritura sin `try/except` (pérdida silenciosa del ciclo)

- Lectura inicial: `try/except` + `return` si falla.
- Bloque de escritura (~769–880): **sin** envoltorio — cualquier excepción aborta toda la persistencia del ciclo.
- `_poller_loop` / standalone loguean el error, pero ningún equipo se actualiza; Redis puede expirar sin refresh.

---

## 4. Hallazgos medios

### M1 — `get_config()` síncrono en medio del ciclo async

**Ubicación:** línea ~716 (`base.gateway` para `host_network_blip`).

- Abre conexión SQLite en el event loop.
- Si `base.gateway` vacío o gateway no está en `infra_devices`, `host_network_blip` no filtra cortes del propio host.

---

### M2 — Redis: cliente nuevo por ciclo + `setex` síncronos en bucle

- `get_redis()` crea conexión + `ping()` cada ciclo; solo `socket_connect_timeout=2`, **sin `socket_timeout`** en operaciones.
- Hasta **3×N `setex`** síncronos dentro de `async def` en fase de escritura.
- Redis lento/colgado → `setex` puede bloquear indefinidamente (redis-py por defecto).

---

### M3 — `record_status_event()` → `_context_snapshots()` por cada transición

- Cada cambio de estado llama `get_redis()` de nuevo dentro de la transacción SQLite abierta.
- Oleada de 30 equipos → 30 conexiones Redis + 30 ping en el mismo ciclo.

---

### M4 — `asyncio.create_task` sin límite (Telegram panel)

- Solo si `INFRA_TELEGRAM_PANEL=1` (default **0**; alertas reales vía agente `watch_infra`).
- Muchas transiciones simultáneas → ráfaga de tareas sin backpressure.

---

### M5 — SNMP: timeouts anidados y coste alto

- `TIMEOUT=4`, `snmpget -r 0` (sin reintentos SNMP).
- `snmpwalk` ifTable: timeout 14 s (v2c) o 24 s (v1).
- Switches grandes / SNMP apagado: hilos ocupados todo el timeout cada ciclo.

---

### M6 — TCP en equipos ya `offline`

- `_tcp_check` se lanza para todos con `tcp_port`, aunque ping ya marcó `offline`.
- Desperdicia hilos en fase 1 (contribuye a C4).

---

### M7 — Divergencia poller embebido vs. standalone

| Aspecto | Standalone | Embebido |
|---------|------------|----------|
| Compensación intervalo | Sí | No |
| Aísla bloqueos Guardian | Sí | No |
| Reinicio ante fallo | systemd `Restart=on-failure` | Solo si cae todo `shomer-guardian` |
| `_sync_guardian_aps()` | Sync antes de cada poll | Igual |

---

## 5. Hallazgos menores

| ID | Descripción |
|----|-------------|
| m1 | `_ping` usa solo el primer `time=` del output, no RTT promedio |
| m2 | `_ping` ante cualquier excepción → `offline` sin log diferenciado |
| m3 | `prev["status"]` sin guard si fila existe pero `status` NULL → posible `KeyError` |
| m4 | Blob Redis `infra:{ip}:data` sin `snmp_data` (solo metadatos ligeros) |
| m5 | Sin métricas de duración por fase en logs |
| m6 | `host_network_blip` solo omite `newly_offline_ips`, no refresca estados ya offline |

---

## 6. Riesgos de arquitectura

1. **Un solo SQLite** como bus de estado (Infra, Guardian, Hunter, Protector, `status_events`).
2. **Dos modos de ejecución** (standalone vs. embebido) con semánticas distintas; fallback embebido peligroso en producción.
3. **Redis cache caliente** escrito en camino crítico; TTL 120 s — ciclo lento/fallido → datos stale en NOC/bot.
4. **Alertas duplicadas** si no se mantiene alineación panel (`INFRA_TELEGRAM_PANEL`) vs. agente (`watch_infra`, debounce, `host_network_blip`).
5. **`get_redis()` sin pool/singleton** — patrón repetido en todo el stack.

---

## 7. Riesgos de rendimiento

| Factor | Escala típica Ópera | Efecto |
|--------|---------------------|--------|
| 2×N tareas ping+tcp | 104 / 48 hilos | Cola, alargamiento fase 1 |
| SNMP paralelo | ~9 × 15–32 s peor caso | Fase dominante del ciclo |
| Bucle escritura O(N) | 52 × (SQL + Redis) | Segundos CPU + I/O |
| `json.dumps(snmp_res)` | Switches muchos puertos | Payload grande SQLite |
| `record_status_event` × N transiciones | Oleadas | Multiplica Redis + SQL en transacción |

**Cuello de botella dominante:** fase SNMP + saturación thread pool en ping/tcp (no solo el `commit` SQLite, salvo oleadas de cambios).

---

## 8. Riesgos de estabilidad

1. **Fallo en lectura:** `return` silencioso — ciclo sin actualizar nada.
2. **Poller embebido sin watchdog propio:** `create_task` una vez; si la task muere sin caer Guardian, no hay re-levantamiento del poller Infra.
3. **Redis caído:** ciclo sigue en SQLite; claves `infra:*` expiran → `/infra/status` más lento (fallback SQLite).
4. **Excepciones tragadas en helpers:** `_ping`, `_get_mac`, SNMP → `offline`/vacío sin distinguir causa.
5. **Condición carrera ARP/MAC:** MAC justo tras ping; redes lentas → `mac` NULL hasta siguiente ciclo.

---

## 9. Recomendaciones generales (referencia)

### Prioridad alta (base del plan de cambios — sección 10)

1. Persistencia (lectura + escritura) en `asyncio.to_thread()`.
2. Transacción SQLite corta; Redis después del `commit`.
3. Ping primero; TCP solo si `online|degraded` y hay puerto.
4. Redis pipeline + `socket_timeout`.
5. `try/except` en persistencia con log explícito.
6. Logging duración por fase; warning si `total > POLL_INTERVAL_SEC`.
7. Compensar intervalo en `_poller_loop` embebido.
8. Cache WAN/maint una vez por ciclo para `record_status_event`.

### Prioridad media (fuera del plan mínimo v1)

- Semáforo concurrencia SNMP (8–12).
- Singleton Redis a nivel módulo.
- RTT promedio en `_ping`.
- Clave Redis `infra:poller:last_ok` / `last_error`.
- Documentar en SITE.md: gateway debe estar en `infra_devices` para `host_network_blip`.

### Prioridad baja

- Persistencia parcial por equipo si falla a mitad de bucle.
- Health endpoint dedicado del poller.

---

## 10. Plan de cambios mínimos propuestos

**Objetivo:** reducir bloqueos, acortar ciclo efectivo y evitar pérdida total del poll **sin rediseñar** el módulo.  
**Alcance:** principalmente `shomer_inframonitor.py`; ajuste menor opcional en `shomer_status_events.py`.  
**Principio:** un ciclo = recolectar en paralelo (hilos) → persistir en un bloque síncrono corto (hilo). El event loop solo orquesta.

---

### Cambio 1 — Fase de persistencia en `to_thread` (mitiga C1, C2, M2)

**Qué:**

- Extraer bloque ~769–880 a función sync `_persist_poll_results(...)`.
- Llamar: `await asyncio.to_thread(_persist_poll_results, ...)`.
- Mover también lectura inicial (~667–676) a `_load_poll_context()` en `to_thread` al inicio del ciclo.

**Riesgo:** bajo. Misma lógica, otro hilo. **Reversible:** sí.

---

### Cambio 2 — Transacción corta: preparar en memoria, escribir rápido (mitiga C1)

**Qué:**

1. Bucle Python: calcular `status`, `latency`, `loss_pct`, `tcp_ok`, `mac`, `snmp_*`, transiciones, payloads Redis.
2. Una transacción SQLite: batch `UPSERT` `infra_status`, `INSERT` `infra_events` donde aplique, `record_status_event(..., conn=conn)`, **un solo `commit`**.
3. Redis **después** del `commit` (si Redis falla, SQLite ya consistente).

**Riesgo:** bajo-medio. Validar orden `infra_events` / `status_events` / Redis en prueba con 5+ transiciones en un ciclo.

---

### Cambio 3 — Ping primero, TCP solo si aplica (mitiga C4, M6)

**Qué:**

```
1. await gather(ping_tasks)
2. tcp_tasks solo para filas con tcp_port AND status in (online, degraded)
3. await gather(tcp_tasks) → mapa ip → tcp_ok
```

**Riesgo:** muy bajo. Comportamiento igual para equipos online.

---

### Cambio 4 — Redis: una conexión + pipeline por ciclo (mitiga M2)

**Qué:**

- En fase persistencia (hilo sync): un cliente por ciclo con `socket_timeout=2` (o 3).
- `pipe = redis.pipeline()` → acumular `setex` → `pipe.execute()` al final.

**Riesgo:** bajo. Fallo en `execute()` → log; siguiente ciclo reintenta.

---

### Cambio 5 — `try/except` en persistencia (mitiga C5)

**Qué:**

- Envolver `_persist_poll_results` con `try/except` → log `ERROR` + traceback + `devices=N`.
- Opcional: `infra:poller:last_error` en Redis con timestamp.

**v1:** sin persistencia parcial (evita rollback complejo).

**Riesgo:** ninguno.

---

### Cambio 6 — Logging duración por fase (observabilidad)

**Qué:**

```text
logger.info("infra poll: read=%dms ping=%dms mac=%dms snmp=%dms write=%dms total=%dms devices=%d", ...)
```

Si `total > POLL_INTERVAL_SEC` → `logger.warning(...)`.

**Riesgo:** ninguno.

---

### Cambio 7 — Compensar intervalo en poller embebido (mitiga M7)

**Qué:** en `_poller_loop`, igual que standalone:

```python
t0 = loop.time()
# ... poll ...
elapsed = loop.time() - t0
await asyncio.sleep(max(0.1, POLL_INTERVAL_SEC - elapsed))
```

**Riesgo:** bajo.

---

### Cambio 8 — Snapshots WAN/maint una vez por ciclo (mitiga M3, opcional mismo PR)

**Qué:**

- Al inicio de persistencia: `wan_snap, maint = _context_snapshots()` una vez.
- Extender `record_status_event(..., wan_snapshot=..., maintenance=...)` para no llamar `get_redis()` por transición.

**Archivos:** `shomer_status_events.py` (parámetros opcionales) + `shomer_inframonitor.py`.

**Riesgo:** bajo si parámetros opcionales mantienen comportamiento por defecto.

---

### Orden de implementación sugerido

| Paso | Cambio | Esfuerzo estimado | Impacto |
|------|--------|-------------------|---------|
| 1 | TCP condicional (3) | ~30 min | Alto en cola hilos |
| 2 | Logging duración (6) | ~15 min | Diagnóstico |
| 3 | Persistencia en `to_thread` (1) | ~1 h | Aísla bloqueos |
| 4 | Redis pipeline (4) | ~30 min | Menos I/O |
| 5 | Transacción corta (2) | ~1–2 h | Menos lock SQLite |
| 6 | try/except persistencia (5) | ~15 min | Estabilidad |
| 7 | Intervalo embebido (7) | ~10 min | Timing |
| 8 | WAN/maint cache (8) | ~45 min | Menos Redis en oleadas |

**Total estimado:** ~4–5 h lab + prueba en `.205`.

---

### Explícitamente fuera del plan mínimo v1

- Semáforo SNMP / límite concurrencia.
- Refactor global de `get_redis()`.
- Cambios en bot `watch_infra`.
- Deploy Ópera (autorización aparte).
- Persistencia parcial por equipo.

---

## 11. Plan de pruebas (lab `.205` antes de Ópera)

1. **Smoke:** `systemctl is-active shomer-inframonitor-poller` + un ciclo con log de duración.
2. **Carga:** 50+ IPs en `infra_devices` — verificar `total_ms` sin `infra poll: DB error`.
3. **Transición:** desconectar equipo físico → `infra_events` + Redis `infra:{ip}:data` en &lt;2 ciclos.
4. **Blip:** sin regresión `host_network_blip` (gateway en BD + `base.gateway` configurado).
5. **Embebido:** parar poller standalone, reiniciar guardian — `/health` no debe colgar &gt;5 s durante poll.
6. **Tests:** `PYTHONPATH=/opt/network_monitor ./venv/bin/python -m unittest tests.test_smoke_api -v`.

---

## 12. Deploy propuesto (cuando se autorice)

1. Lab `.205` — implementar + pruebas §11.
2. `shomer245` / `shomer243` — `bash tools/deploy.sh` (sin Ópera).
3. **Hotel Ópera** — solo con OK explícito: `SHOMER_DEPLOY_AUTHORIZED=1 bash tools/deploy.sh` + **reinicio manual** `sudo systemctl restart shomer-inframonitor-poller` (deploy.sh no reinicia ese servicio).

---

## 13. Criterios de éxito post-implementación

| Métrica | Objetivo |
|---------|----------|
| `total_ms` ciclo típico (Ópera, ~52 equipos) | &lt; 45 s en condiciones normales; warning si &gt; 30 s |
| Transiciones falsas masivas (mismo ciclo) | No aumentar vs. baseline post-§BC |
| `/health` durante poll (embebido) | Respuesta &lt; 5 s (watchdog 12 s) |
| Ciclo fallido | Log ERROR explícito; no silencio |
| Redis | Un pipeline por ciclo; sin bloqueo indefinido |

---

## 14. Historial del documento

| Fecha | Acción |
|-------|--------|
| 24 jun 2026 | Auditoría inicial + plan de cambios mínimos (sin código aplicado) |
| 24 jun 2026 | Ampliado en `AUDITORIA_POLLERS_CONSOLIDADA.md` (v2.0) |
| — | Pendiente: segunda auditoría / post-implementación |

---

## 15. Referencias en manifiesto

- CLAUDE.md §AS — poller independiente, Redis-first, WAL
- CLAUDE.md §AU — pool hilos, debounce bot, saturación poller Ópera
- CLAUDE.md §BB — `record_status_event(conn=)`, guards `_init_tables`
- CLAUDE.md §BC — ping 3 paquetes, `degraded`, `host_network_blip`
- `docs/AUDITORIA_ASYNC_BLOQUEANTE.md` — patrón async + SQLite bloqueante
