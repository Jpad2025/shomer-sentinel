# Auditoría consolidada — Pollers Inframonitor y Guardian

**Fecha:** 24 jun 2026  
**Alcance:** `inframonitor_poller.py`, `_poll_once()`, `_poller_tick()`, Redis, lógica offline, arquitectura 24/7  
**Estado:** informe + plan de cambios propuesto — **sin implementar en código**  
**Documento relacionado:** `docs/AUDITORIA_POLL_ONCE_INFRAMONITOR.md` (auditoría profunda solo de `_poll_once` + plan mínimo v1)

---

## Índice

1. [Resumen ejecutivo](#1-resumen-ejecutivo)
2. [Infra: `inframonitor_poller.py`](#2-infra-inframonitor_pollerpy)
3. [Guardian: `_poller_tick()`](#3-guardian-_poller_tick)
4. [Redis — pollers](#4-redis--pollers)
5. [Lógica `offline`](#5-lógica-offline)
6. [Async / threads / procesos](#6-async--threads--procesos)
7. [Operación 24/7](#7-operación-247)
8. [Arquitectura](#8-arquitectura)
9. [Plan de cambios propuesto (resolver hallazgos)](#9-plan-de-cambios-propuesto-resolver-hallazgos)
10. [Orden de implementación y pruebas](#10-orden-de-implementación-y-pruebas)
11. [Historial](#11-historial)

---

## 1. Resumen ejecutivo

| Área | Veredicto | Riesgo principal |
|------|-----------|------------------|
| Infra standalone | Viable 24/7 con monitoreo | Ciclo &gt; 30 s, hang sin watchdog de app |
| Infra `_poll_once` | Funcional, deuda sync | SQLite/Redis en event loop; 2×N tareas ping+tcp |
| Guardian `_poller_tick` | **Riesgo alto a escala** | Bucle **secuencial** + `_run_ssh_reboot` **síncrono en el loop** |
| Redis | Namespaces OK | `KEYS`, sin TTL en `status:*`, ops bloqueantes |
| Offline | Bien diferenciado Infra vs Guardian | FP por cola hilos (Infra); FN SNMP no config (Guardian) |

**Prioridad absoluta:** sacar reboot y sondeo pesado del event loop de Guardian; persistencia Infra en hilo dedicado.

---

## 2. Infra: `inframonitor_poller.py`

### Cómo se ejecuta el ciclo

```
asyncio.run(main())
  → _init_tables() [sync, una vez]
  → while not stop:
       t0 = now
       _sync_guardian_aps()     [sync SQLite]
       await _poll_once()
       wait = max(0.1, 30 - elapsed)
       await wait_for(_stop_event, timeout=wait)
```

- Proceso dedicado; no levanta FastAPI.
- `SIGTERM`/`SIGINT` → parada limpia.

### Hallazgos

| ID | Hallazgo | Severidad |
|----|----------|-----------|
| I1 | `_sync_guardian_aps` + fases sync de `_poll_once` bloquean el event loop del proceso | Medio (aislado del panel) |
| I2 | Sin watchdog de aplicación; hang → proceso vivo, datos stale | Alto |
| I3 | `except` por ciclo OK; `_poll_once` escritura sin try interno → pierde ciclo entero | Medio |
| I4 | systemd `Restart=on-failure` — no reinicia hangs | Medio |
| I5 | No hay solapamiento concurrente de `_poll_once` | OK |
| I6 | Si `elapsed > 30 s` → siguiente ciclo en ~0,1 s (intervalo inestable) | Medio |
| I7 | Poller embebido en Guardian **no compensa** intervalo (`sleep(30)` fijo) | Medio |

---

## 3. Guardian: `_poller_tick()`

### Hallazgos

| ID | Hallazgo | Severidad |
|----|----------|-----------|
| G1 | **`_run_ssh_reboot(ip)` síncrono en event loop** — hasta ~15–20 s freeze | **Crítico** |
| G2 | Bucle `for dev in devices` **secuencial** — 30 nodos × ~8–15 s = minutos por tick | **Crítico** |
| G3 | `r.keys("status:*")` cada tick — O(N), bloquea Redis | Alto |
| G4 | `get_db()` sync en limpieza huérfanos en el loop | Alto |
| G5 | `record_status_event()` sin `conn=` — escritura SQLite extra por transición | Medio |
| G6 | `send_telegram_safe()` sync en el loop | Medio |
| G7 | Si `get_redis()` → `None`, tick **retorna sin sondear** | Alto |
| G8 | `await sleep(10)` sin compensar duración del tick | Medio |
| G9 | `record_status_event` falla → `logger.debug` silencioso | Menor |

### Timeouts verificados

| Función | Timeout subprocess |
|---------|------------------|
| `_ping_metrics` | `max(count*2+2, 5)` s |
| `_ssh_health_probes` | SSH 15 s |
| `_snmp_health_probes` | 8 s (+3) |
| `_run_ssh_reboot` | 10–15 s |

---

## 4. Redis — pollers

### Claves Infra (escritura en `_poll_once`)

| Clave | TTL | Notas |
|-------|-----|-------|
| `infra:{ip}:status` | 120 s (`30×4`) | OK si ciclo ≤ 30 s |
| `infra:{ip}:latency` | 120 s | |
| `infra:{ip}:data` | 120 s | Sin `snmp_data` completo |
| `infra_alert_cooldown:{ip}` | 300 s | Solo panel `INFRA_TELEGRAM_PANEL=1` |

### Claves Guardian (escritura en `_poller_tick`)

| Clave | TTL |
|-------|-----|
| `status:{ip}` | **Ninguno** |
| `failures:{ip}` | Hasta DELETE en online |
| `last_reboot:{ip}` | Ninguno |
| `degraded_streak:{ip}` | `max(cooldown, 60)` |
| `degraded_notified:{ip}` | ~1800 s |
| `node:{ip}` | Sin TTL (hash) |
| `shomer:wan_status` | `interval×3` (server health) |

### Hallazgos Redis

| ID | Hallazgo | Severidad |
|----|----------|-----------|
| R1 | Sin colisión `infra:` vs `status:` | OK |
| R2 | `infra:{ip}:*` huérfanas expiran en 120 s; no DELETE explícito al borrar equipo | Menor |
| R3 | `get_redis()` nuevo cliente + `ping()` cada uso; sin `socket_timeout` en ops | Alto |
| R4 | Infra: 3×N `setex` síncronos por ciclo | Alto |
| R5 | Guardian: `KEYS` en camino caliente | Alto |

---

## 5. Lógica `offline`

### Inframonitor (ICMP)

| Pérdida ping (3 pkt) | Estado |
|----------------------|--------|
| 100 % | `offline` — **1 ciclo** (~30 s) |
| ≥ 60 % y &lt; 100 % | `degraded` |
| &lt; 60 % | `online` |

- **SNMP/TCP no definen** online/offline.
- **`host_network_blip`:** omite persistir offline masivo si gateway cae + ≥8 equipos nuevos offline (mismo ciclo).
- **Bot:** alerta Telegram tras 2 chequeos `watch_infra` (~4 min); BD/Redis del poller no esperan.

### Guardian

| Condición | Estado | Reboot |
|-----------|--------|--------|
| 100 % loss ICMP | `offline` | Tras `fail_threshold` ticks (default **2** × 10 s) |
| Router SSH + WAN ping fail | `no-internet` | Igual |
| SNMP AP colgado / radio down | `no-internet` | Igual |
| Pérdida/RTT alta | `degraded` | **No** (persist 3 ticks antes de marcar degraded) |

- Estado en Redis: **inmediato** en tick 1; reboot retrasado por `failures:{ip}`.

---

## 6. Async / threads / procesos

| Componente | Modelo |
|------------|--------|
| Infra standalone | 1 proceso, asyncio + `ThreadPoolExecutor(48)` |
| Infra embebido | Mismo código en proceso Guardian |
| Guardian poller | asyncio; ping/SSH/SNMP en `to_thread`; **reboot y Redis sync en loop** |
| Semáforos | Solo `INFRA_THREAD_WORKERS`; **ninguno en Guardian** |

**Mezcla peligrosa:** SQLite + Redis síncronos en `async def` (Infra); reboot + `KEYS` + bucle secuencial (Guardian).

---

## 7. Operación 24/7

| Riesgo | Infra | Guardian |
|--------|-------|----------|
| Fugas memoria | Bajo | Bajo |
| Ciclos más largos con más equipos | Sí (paralelo) | **Sí (secuencial)** |
| Freeze | SQLite/subprocess hang | **Alto** (reboot sync) |
| Crash sin reinicio | systemd (standalone) | watchdog reinicia todo el servicio |
| Excepciones silenciosas | Lectura DB `return`; escritura sin try | `record_status_event` debug |

---

## 8. Arquitectura

```
shomer-guardian (:8000, 1 worker)
  ├─ FastAPI + /health
  ├─ _poller_loop Guardian (10s)     ← bloquea API
  ├─ server_health, Hunter autoblock, retention…
  └─ [fallback] _poller_loop Infra

shomer-inframonitor-poller.service (proceso aparte)
  └─ _poll_once ~30s

        network_monitor.db (SQLite WAL)     Redis 127.0.0.1
```

**Acoplamiento:** `_sync_guardian_aps`, SQLite compartido, dos tablas infra (`infra_devices` vs `infra_nodes`).

**SPOF:** BD única, Redis local, proceso Guardian monolítico.

---

## 9. Plan de cambios propuesto (resolver hallazgos)

### Fase A — Crítico Guardian (G1, G2, G3)

#### A.1 — Reboot fuera del event loop

**Archivo:** `app/api/shomer_guardian_nodes.py`

**Cambio:**
```python
# Antes:
ok, msg = _run_ssh_reboot(ip)

# Después:
ok, msg = await asyncio.to_thread(_run_ssh_reboot, ip)
```

**Resuelve:** G1 — freeze de 15–20 s en autoreboot.  
**Riesgo:** bajo. **Prueba:** reboot manual de nodo de lab durante carga en `/health`.

---

#### A.2 — Sondeo paralelo con límite

**Archivo:** `app/api/shomer_guardian_nodes.py`

**Cambio:** extraer cuerpo del `for dev in devices` a `_poll_single_node(dev, r, health_cfg, threshold, cooldown, batch_id)` (sync o async) y ejecutar:

```python
_SEM = asyncio.Semaphore(int(os.environ.get("GUARDIAN_POLL_CONCURRENCY", "8")))

async def _poll_one_wrapped(dev):
    async with _SEM:
        return await _poll_single_node_async(dev, ...)

results = await asyncio.gather(
    *[_poll_one_wrapped(d) for d in devices],
    return_exceptions=True,
)
# Consolidar tick_results; reboots ya en to_thread dentro de cada nodo
```

**Parámetro env:** `GUARDIAN_POLL_CONCURRENCY` default **8** (Ópera ~30 nodos → ~4 oleadas vs 30 secuenciales).

**Resuelve:** G2 — tick de minutos → objetivo &lt; 30–45 s.  
**Riesgo:** medio — más carga ICMP simultánea; ajustar concurrencia por sitio.  
**Nota:** cada tarea debe usar su propia lógica Redis; Redis es single-threaded pero rápido vs subprocess.

---

#### A.3 — Reemplazar `KEYS` por `SCAN`

**Archivo:** `app/api/shomer_guardian_nodes.py` (y `/nodes`, `shomer_system_status.py` si aplica)

**Cambio:**
```python
def _iter_status_keys(r):
    cursor = 0
    while True:
        cursor, keys = r.scan(cursor, match="status:*", count=100)
        for key in keys:
            yield key
        if cursor == 0:
            break
```

O mantener `SADD shomer:guardian:ips` al alta/baja de nodo y limpiar solo ese set.

**Resuelve:** G3, R5.  
**Riesgo:** bajo.

---

### Fase B — Infra `_poll_once` (I1, I3, I6, I7 + auditoría previa)

*Detalle ampliado en `AUDITORIA_POLL_ONCE_INFRAMONITOR.md` §10.*

#### B.1 — TCP solo si ping OK (C4 / M6)

**Archivo:** `app/api/shomer_inframonitor.py`

1. `await gather(ping_tasks)`
2. TCP solo si `status in (online, degraded)` y `tcp_port`
3. `await gather(tcp_tasks)`

**Resuelve:** saturación 2×N tareas.

---

#### B.2 — Persistencia en `to_thread`

**Archivo:** `app/api/shomer_inframonitor.py`

- `_load_poll_context()` sync: lectura `infra_devices` + `infra_status`
- `_persist_poll_results(...)` sync: bucle en memoria + un `commit` + Redis pipeline
- `_poll_once`: solo orquesta `to_thread` para red + `to_thread` para persistir

**Resuelve:** I1, bloqueo si poller embebido en Guardian.

---

#### B.3 — Redis pipeline + timeout

**Archivo:** `app/api/shomer_common.py` (o helper nuevo `shomer_redis.py`)

```python
_redis_client = None

def get_redis_pooled():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=..., port=...,
            socket_connect_timeout=2,
            socket_timeout=3,
            decode_responses=True,
        )
    try:
        _redis_client.ping()
        return _redis_client
    except Exception:
        return None
```

En persistencia Infra:
```python
pipe = redis.pipeline()
for row in ...:
    pipe.setex(f"infra:{ip}:status", ttl, status)
    ...
pipe.execute()
```

**Resuelve:** R3, R4.

---

#### B.4 — `try/except` en persistencia + métrica

**Archivo:** `app/api/shomer_inframonitor.py`

- Envolver `_persist_poll_results` con log ERROR + traceback
- Opcional: `SET infra:poller:last_ok` / `infra:poller:last_error`

**Resuelve:** I3, I2 (parcial).

---

#### B.5 — Logging duración por fase

```python
logger.info(
    "infra poll: read=%dms ping=%dms mac=%dms snmp=%dms write=%dms total=%dms devices=%d",
    ...
)
```

Si `total > POLL_INTERVAL_SEC` → `logger.warning`.

**Resuelve:** I6 observabilidad.

---

#### B.6 — Compensar intervalo embebido

**Archivo:** `app/api/shomer_inframonitor.py` — `_poller_loop`

Igual que `inframonitor_poller.py`:
```python
t0 = loop.time()
...
await asyncio.sleep(max(0.1, POLL_INTERVAL_SEC - (loop.time() - t0)))
```

**Resuelve:** I7.

---

#### B.7 — WAN/maint una vez por ciclo (M3)

**Archivos:** `shomer_status_events.py`, `shomer_inframonitor.py`

- `record_status_event(..., wan_snapshot=..., maintenance=...)` opcional
- Una llamada `_context_snapshots()` al inicio de persistencia

---

### Fase C — Guardian tick restante (G4–G9)

#### C.1 — `record_status_event` con batch

Acumular eventos en lista durante el tick; una función `_flush_status_events(conn, events)` al final en `to_thread`, o pasar `conn` si se abre una transacción por tick en hilo.

**Resuelve:** G5.

---

#### C.2 — Limpieza huérfanos en `to_thread`

```python
await asyncio.to_thread(_cleanup_orphan_redis_keys, r)
```

**Resuelve:** G4.

---

#### C.3 — Redis obligatorio — degradar con log CRITICAL

Si `get_redis()` es `None`:
```python
logger.critical("Guardian poller: Redis no disponible — tick omitido")
```
Y opcional: escribir en SQLite `infra_nodes` desde ping aunque Redis falle (modo degradado).

**Resuelve:** G7.

---

#### C.4 — Compensar intervalo Guardian

```python
t0 = time.monotonic()
await _poller_tick()
await asyncio.sleep(max(0.1, _POLL_INTERVAL_SEC - (time.monotonic() - t0)))
```

**Resuelve:** G8.

---

#### C.5 — Telegram en `to_thread`

```python
await asyncio.to_thread(send_telegram_safe, msg)
```

**Resuelve:** G6.

---

### Fase D — Watchdog y 24/7 (I2, I4)

#### D.1 — Heartbeat Redis por poller

| Clave | Valor | TTL |
|-------|-------|-----|
| `infra:poller:last_ok` | ISO timestamp | 300 s |
| `infra:poller:last_duration_ms` | entero | 300 s |
| `guardian:poller:last_ok` | ISO timestamp | 120 s |
| `guardian:poller:last_duration_ms` | entero | 120 s |

Monitor externo (agente `watch_services` o script): si `last_ok` expirado → alerta.

**Resuelve:** I2, hang silencioso.

---

#### D.2 — Timeout global por ciclo Infra

**Archivo:** `inframonitor_poller.py`

```python
try:
    await asyncio.wait_for(_poll_once(), timeout=int(os.environ.get("INFRA_POLL_TIMEOUT_SEC", "120")))
except asyncio.TimeoutError:
    logger.error("infra poll: timeout global — ciclo abortado")
```

**Resuelve:** hang indefinido (parcial; subprocess huérfanos pueden quedar en hilos).

---

#### D.3 — Poller embebido: reinicio de task

**Archivo:** `shomer_inframonitor.py` — `start_inframonitor_poller`

```python
def _poller_done(task):
    logger.error("Infra poller task terminó: %s", task.exception())
    global _poller_running
    _poller_running = False
    start_inframonitor_poller()  # o solo log si standalone activo

_poller_task.add_done_callback(_poller_done)
```

Guardar referencia a `_poller_task`; no relanzar si `shomer-inframonitor-poller.service` activo.

**Resuelve:** muerte silenciosa task embebida.

---

### Fase E — Redis higiene (R2)

#### E.1 — DELETE al eliminar equipo Infra

**Archivo:** `shomer_inframonitor.py` — `remove_device`

```python
if redis:
    redis.delete(f"infra:{ip}:status", f"infra:{ip}:latency", f"infra:{ip}:data")
```

#### E.2 — TTL de seguridad en `status:{ip}` (opcional)

`SET status:{ip} ... EX 604800` (7 días) renovado cada tick — red de seguridad si falla limpieza.

---

### Fase F — Arquitectura (largo plazo)

| Cambio | Beneficio | Esfuerzo |
|--------|-----------|----------|
| **Proceso `shomer-guardian-poller.service`** (como Infra) | API aislada del sondeo | Alto |
| Unificar `infra_nodes` → vista de `infra_devices` o eliminar duplicado | Menos escrituras SQLite | Medio |
| `get_config` cache en memoria 30 s en pollers | Menos locks SQLite | Bajo |
| Semáforo SNMP Infra (`INFRA_SNMP_CONCURRENCY=8`) | Evita 9× walk simultáneos | Bajo |

**Recomendación:** Fase A–D en lab `.205`; Fase F.1 (Guardian poller standalone) planificar tras validar A.2 en Ópera con autorización.

---

## 10. Orden de implementación y pruebas

### Orden sugerido (lab primero)

| Paso | Fase | Archivos | Esfuerzo |
|------|------|----------|----------|
| 1 | A.1 | `shomer_guardian_nodes.py` | 15 min |
| 2 | A.3 | `shomer_guardian_nodes.py` | 30 min |
| 3 | B.1, B.5, B.6 | `shomer_inframonitor.py`, `inframonitor_poller.py` | 1 h |
| 4 | B.2, B.3, B.4 | `shomer_inframonitor.py`, `shomer_common.py` | 2–3 h |
| 5 | C.1–C.5 | `shomer_guardian_nodes.py` | 1–2 h |
| 6 | A.2 | `shomer_guardian_nodes.py` | 2–3 h |
| 7 | D.1–D.3 | pollers + agente opcional | 1 h |
| 8 | B.7, E.1 | varios | 45 min |

### Pruebas obligatorias

1. **Guardian:** `/health` responde &lt; 5 s durante tick completo con 30 nodos (simulados o reales).
2. **Guardian:** autoreboot en lab — no freeze panel.
3. **Infra:** log `total_ms` &lt; 45 s con inventario Ópera-like (52 equipos).
4. **Redis:** `redis-cli KEYS 'infra:*' | wc -l` estable; pipeline sin error.
5. **Offline:** desconectar 1 switch — estado en panel en &lt; 2 ciclos Infra.
6. **Blip:** no regresión `host_network_blip`.
7. **24h soak:** `last_duration_ms` sin tendencia creciente (comparar hora 1 vs hora 12).
8. `unittest tests.test_smoke_api -v`

### Deploy

| Entorno | Procedimiento |
|---------|---------------|
| `.205` lab | Implementar + pruebas |
| `.245` / `.243` | `bash tools/deploy.sh` |
| **Ópera** | Solo con OK explícito + `SHOMER_DEPLOY_AUTHORIZED=1` + `systemctl restart shomer-inframonitor-poller` |

---

## 11. Historial

| Fecha | Versión | Contenido |
|-------|---------|-----------|
| 24 jun 2026 | 1.0 | `AUDITORIA_POLL_ONCE_INFRAMONITOR.md` — solo `_poll_once` |
| 24 jun 2026 | 2.0 | Este documento — auditoría consolidada + plan de cambios |
| — | 3.0 | Pendiente: segunda auditoría externa / post-implementación |

---

## Referencias código

| Archivo | Función |
|---------|---------|
| `app/scripts/inframonitor_poller.py` | Runner standalone |
| `app/api/shomer_inframonitor.py` | `_poll_once`, `_poller_loop`, `_ping`, `_snmp_poll` |
| `app/api/shomer_guardian_nodes.py` | `_poller_tick`, `_poller_loop` |
| `app/api/shomer_guardian_health_checks.py` | `classify_health`, `_ping_metrics` |
| `app/api/shomer_common.py` | `get_db`, `get_redis` |
| `/etc/systemd/system/shomer-inframonitor-poller.service` | Restart, MemoryMax |
