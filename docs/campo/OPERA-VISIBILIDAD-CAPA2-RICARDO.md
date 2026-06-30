# Hotel Ópera — Visibilidad de red (Capa 2/3)  
## Guía para Ricardo Gómez — acciones en sitio

**Documento:** USB Ingeniería / Shomer Sentinel  
**Fecha:** 13 jun 2026  
**Para:** Ricardo Gómez (soporte en hotel)  
**Contacto USB:** Juan Pablo  
**Sitio:** Hotel Ópera — Shomer `192.168.0.250` — panel `https://192.168.0.250:8443`

---

## RESUMEN RÁPIDO — léelo primero (5 minutos)

### ¿De qué va esto?

A veces **muchos WiFi (APs) caen a la vez** unos segundos y vuelven solos.  
Shomer **ya avisa** por Telegram cada AP — eso **está bien y no lo vamos a quitar**.

Lo que **falta** es que Shomer también diga:  
**“El problema parece estar en el SWITCH del piso X”** — no solo “cayeron 15 APs”.

Para eso hay que **prender una opción de lectura** en los switches (se llama **SNMP**).  
Es como darle al Shomer “ojos” para ver los puertos del switch — **solo mirar, no cambiar nada**.

---

### ¿Qué tienes que hacer tú, Ricardo oun tecnico o lo pudo haceryo con las credeciales ? (3 cosas)

| # | Qué | ¿Difícil? | Tiempo |
|---|-----|-----------|--------|
| **1** | **Encender SNMP** en los switches del hotel (lista abajo) | Media — entras a cada switch y activas SNMP | ~1 hora |
| **2** | **Decirnos** dónde está el **UniFi Controller** (IP o si es nube) + usuario de consulta | Fácil — un mensaje a Juan Pablo | 10 min |
| **3** | *(Opcional)* Anotar qué AP va conectado a qué switch | Fácil — Excel o mensaje | Cuando puedas |

**Lo más importante es el paso 1.** Sin eso, seguimos adivinando.

---

### ¿Cómo se hace el paso 1? (SNMP — versión corta)

En **cada switch** de la tabla de la sección 3:

1. Entras al switch (UniFi Network o web del equipo).
2. Buscas **SNMP** → lo **activas**.
3. Pones comunidad: **`shomer2026`**
4. Permites solo la IP: **`192.168.0.250`** (el Shomer).
5. Guardas.
6. Nos avisas por Telegram: *“SNMP listo en switch .212”*

**No reinicies el switch.** Solo activar SNMP y guardar.

---

### ¿Hay riesgo?

| Pregunta | Respuesta |
|----------|-----------|
| ¿Se cae el WiFi? | **No** — SNMP solo lee, no toca la red |
| ¿Hay que tocar los APs? | **No** — ya están en el sistema |
| ¿Cuándo hacerlo? | **Madrugada o mañana temprano** (pocos huéspedes) |

---

### ¿Qué hace USB mientras tú avanzas?

Juan Pablo y el equipo **programan el Shomer** para usar esa información.  
Tú configuras los switches; nosotros el software. **Van en paralelo.**

---

### ¿No entiendes algo?

Llama o escribe a **Juan Pablo**.  
El resto del documento tiene **detalle paso a paso** — úsalo cuando vayas a hacer el trabajo en el rack.

---

## 1. Para qué es esto (en una frase)

Hoy Shomer **sabe cuando un AP o una impresora deja de responder**, pero **no sabe si el problema es el cable, el switch, el PoE o el uplink**.  
Con los pasos de este documento, el sistema podrá decir cosas como: *“Cayeron 8 APs del piso 3 — revisar switch SW Piso 3 (.129), puerto uplink”* en lugar de solo *“muchos APs offline”*.

**Importante:** Las alertas **individuales por AP en Telegram no se quitan**. Siguen siendo útiles para reaccionar rápido. Lo nuevo es un **resumen inteligente** y **visibilidad de switches**.

---

## 2. Qué pasa hoy en Ópera (situación real)

### Lo que Shomer **sí** ve bien

| Qué | Dónde está |
|-----|------------|
| **~30 APs UniFi** — ping cada ~10 s | Panel **Guardian** (IPs y nombres ya cargados) |
| **8 switches + impresoras + POS** — ping cada 30 s | Panel **Infra** |
| **Oleadas de caídas** + resumen Telegram post-incidente | Panel **Estado del sistema** → Historial |
| **Internet del hotel (WAN)** | Shomer confirma MikroTik `.1` y 8.8.8.8 OK |

### Lo que Shomer **no** ve todavía

| Qué falta | Consecuencia |
|-----------|--------------|
| **SNMP en switches** | No ve puertos UP/DOWN ni PoE |
| **UniFi Controller conectado al Shomer** | No ve “AP disconnected” masivo desde UniFi |
| **Mapa AP → switch → puerto** | No correlaciona “estos APs cayeron juntos → mismo switch” |

### Incidentes recientes (patrón)

- **12 y 13 jun 2026:** ráfagas de ~15–30 APs sin ping **20 s – 17 min**, recuperación sola, **WAN OK**.
- Causa probable en campo: **switch admin, PoE o uplink UniFi** — no fallo de internet ni del software Shomer.

---

## 3. Qué hay que hacer en el hotel (checklist Ricardo)

### Tarea A — Activar SNMP en switches (PRIORIDAD ALTA)

**Tiempo estimado:** 45–90 min (todos los switches)  
**Cuándo:** Horario de baja afluencia (madrugada o mañana temprano)

Shomer ya tiene registrados estos switches en **Infra**. Falta que respondan SNMP:

| Nombre en Shomer | IP | Ubicación |
|------------------|-----|-----------|
| SW-POE Principal (EdgeSwitch) | `192.168.0.212` | Switch principal PoE |
| SW-POE OFC-SISTEMAS (EdgeSwitch) | `192.168.0.216` | Oficina Sistemas |
| SW Piso 3 (SW3) | `192.168.0.129` | Switch Piso 3 |
| SW Piso 7 (SW7) | `192.168.0.118` | Switch Piso 7 |
| SW Amalfi (Piso 1) | `192.168.0.133` | Switch Salón Amalfi |
| Switch Cisco .146 | `192.168.0.146` | Confirmar ubicación |
| Switch Cisco .168 | `192.168.0.168` | Confirmar ubicación |
| Switch Cisco .187 | `192.168.0.187` | Confirmar ubicación |

**En cada switch UniFi EdgeSwitch:**

1. Entrar al switch (UniFi Network Application o interfaz web del switch).
2. **Settings → Services → SNMP** (o equivalente).
3. Activar **SNMP v2c**.
4. Comunidad de **solo lectura:** `shomer2026` (acordar con USB si prefieren otro nombre).
5. **Restringir acceso SNMP solo a:** `192.168.0.250` (IP del Shomer).
6. Desactivar o no usar comunidad `public` en producción.
7. Guardar / Apply.

**En switches Cisco (si aplica):**

```
snmp-server community shomer2026 RO
snmp-server host 192.168.0.250 shomer2026
```

**Verificación desde el Shomer (pedir a USB o Cristian por Telegram):**

```bash
snmpget -v2c -c shomer2026 192.168.0.212 1.3.6.1.2.1.1.5.0
```

Debe responder con el hostname del switch.

**Luego en panel Shomer:**

1. Ir a **Infra** → editar cada switch.
2. Campo **Comunidad SNMP:** poner `shomer2026`.
3. Guardar.
4. Clic en botón **SNMP** en la fila → deben aparecer puertos e interfaces.

---

### Tarea B — Confirmar UniFi Controller (PRIORIDAD MEDIA)

Los **30 APs ya están en Guardian** con IP y usuario SSH `admin`. Eso cubre ping y reboot.

Para ver el estado “Disconnected” masivo desde UniFi, USB necesita registrar el **Controller** en Shomer.

**Ricardo debe confirmar por escrito (WhatsApp/Telegram a Juan Pablo):**

| Dato | Ejemplo | ¿Dónde lo encuentro? |
|------|---------|----------------------|
| ¿Controller local o UniFi Cloud? | Local / Cloud | UniFi Network → Settings → System |
| URL o IP del Controller | `https://192.168.0.X:8443` | Servidor donde corre Network Application |
| Usuario **solo lectura** | `shomer_readonly` | Crear en UniFi o usar cuenta existente de consulta |
| Contraseña | *(enviar por canal seguro, no por email abierto)* | — |

> **Nota:** Si el Controller corre en un servidor del hotel (ej. rack sistemas), anotar IP fija. Si es **UniFi Cloud** (ui.com), indicarlo — USB configura acceso API distinto.

**No hace falta tocar los APs uno por uno** — ya están en Guardian.

---

### Tarea C — SNMP en impresoras de red (PRIORIDAD MEDIA-BAJA)

Impresoras registradas:

| IP | Nombre | Ubicación |
|----|--------|-----------|
| `192.168.0.240` | IMP Recepción WF-M5899 | Recepción / Lobby |
| `192.168.0.58` | IMP SCOCINA | Cocina Scala |

**En panel web de cada impresora Epson:**

1. Red → SNMP → Activar v2c, comunidad lectura `shomer2026`.
2. Permitir solo IP `192.168.0.250`.
3. En Shomer **Infra** → editar impresora → comunidad `shomer2026`.

**Beneficio:** además de “offline”, Shomer podrá avisar **tóner bajo** y **papel** antes de que dejen de imprimir.

---

### Tarea D — Mapa mínimo AP → switch (PRIORIDAD BAJA, puede ser gradual)

No hace falta un diagrama perfecto el día 1. Con **10–15 APs críticos** basta.

**Formato sugerido** (Excel o mensaje a USB):

```
AP LOBBY RECEPCION (.121)  →  SW-POE Principal (.212)
AP HAB 211-212 (.131)      →  SW Piso 3 (.129)
AP REST SCALA (.239)       →  SW Amalfi (.133)
...
```

USB lo cargará en el módulo de topología cuando esté listo.

---

## 4. Ventajas de hacerlo

| Ventaja | Para quién |
|---------|------------|
| **Menos tiempo buscando** en la próxima oleada | Ricardo / Cristian |
| **Ir directo al switch correcto** (piso, PoE, uplink) | Mantenimiento hotel |
| **Menos falsas alarmas** de “todo el WiFi cayó” cuando es un switch | Gerencia / recepción |
| **Impresoras:** aviso de tóner/papel antes del fallo | Restaurante / recepción |
| **Informe automático** post-oleada con checklist de campo | Todos (Telegram) |
| **Historial** en panel para demostrar que el problema es infraestructura física, no Shomer | USB / hotel |

---

## 5. Riesgos y cómo los evitamos

| Riesgo | ¿Es grave? | Mitigación |
|--------|------------|------------|
| SNMP mal configurado abierto a toda la red | Medio | Solo lectura + solo IP `192.168.0.250` |
| Comunidad `public` en producción | Medio | Usar `shomer2026` (o la que acuerden) |
| Reiniciar switch durante configuración | Alto | Hacer en ventana de mantenimiento; avisar `/modo on` en bot Telegram antes |
| Cambiar VLAN o firewall del switch | Bajo | SNMP es UDP 161 desde Shomer → switch; no tocar reglas WAN |
| Credenciales UniFi en texto plano | Medio | Enviar contraseña por Telegram privado; USB guarda en BD cifrada por permisos OS |
| Tocar configuración WiFi de huéspedes | Nulo | Este trabajo **no** cambia SSIDs ni contraseñas WiFi |

**Lo que NO se hará:**

- No se modifican APs masivamente.
- No se reinician servicios del hotel sin coordinación.
- No se toca red de huéspedes (`10.1.48.0/22`).

---

## 6. Qué hace USB en paralelo (sin esperar a que termines todo)

Mientras Ricardo avanza en sitio, USB desarrolla en laboratorio:

| Módulo | Función |
|--------|---------|
| **`shomer_topology`** (nuevo) | Lee SNMP de switches + UniFi Controller cuando estén configurados |
| **Correlación oleadas** | “N APs offline → mismo switch padre” |
| **Multimarca** | Mismo código sirve para otros hoteles (MikroTik, Cisco, TP-Link) — config por panel, no hardcode |

**Los APs en Guardian no se mueven.** El código nuevo **suma** información, no reemplaza alertas.

---

## 7. Información que ya está en Shomer (no hay que volver a entregar)

### APs UniFi — Panel Guardian (~30 equipos)

Todos con ping activo. Ejemplos:

| IP | Nombre |
|----|--------|
| 192.168.0.121 | AP LOBBY RECEPCION |
| 192.168.0.131 | AP HAB 211-212 |
| 192.168.0.239 | AP REST SCALA |
| … | (lista completa en Guardian) |

Usuario SSH típico en BD: `admin` (reboot manual si aplica).

### Switches — Panel Infra (8 equipos)

IPs en tabla sección 3 — Tarea A.

### Documentación del sitio

Archivo en el servidor: `/opt/network_monitor/SITE.md` (red, MikroTik, VLANs, incidentes).

### Lo único pendiente de confirmar por Ricardo

1. **SNMP activado** en switches (Tarea A) — acción en sitio.  
2. **IP/URL + usuario UniFi Controller** (Tarea B) — si ya se entregó antes, **reconfirmar por Telegram** para registrarlo en Shomer (hoy no está en `SITE.md` ni en la BD del Controller).  
3. **Ubicación física** switches Cisco `.146`, `.168`, `.187` (opcional pero útil).

---

## 8. Orden de trabajo recomendado

```
Día 1 (1–2 h)
  └─ Tarea A: SNMP en SW-POE Principal (.212) y SW Piso 3 (.129)
  └─ Probar botón SNMP en panel Infra
  └─ Enviar a USB: “SNMP OK en .212 y .129”

Día 2
  └─ Tarea A: resto de switches Edge + Cisco
  └─ Tarea B: datos UniFi Controller

Semana 1
  └─ Tarea C: impresoras .240 y .58
  └─ Tarea D: mapa AP→switch (gradual)
```

---

## 9. Cómo avisar que terminó cada paso

Mensaje Telegram al bot Shomer o a Juan Pablo:

```
Ópera — SNMP switch .212 OK — probado desde Shomer
Ópera — UniFi Controller: https://192.168.0.X:8443 usuario shomer_readonly
Ópera — Mapa AP: AP LOBBY (.121) → SW .212
```

USB actualiza panel y activa módulo topología.

---

## 10. Preguntas frecuentes

**¿Esto puede tumbar el WiFi?**  
No. SNMP es solo lectura. No reinicia equipos.

**¿Por qué siguen llegando muchos Telegrams por AP?**  
Es intencional — ayuda a reaccionar. El resumen post-oleada es **adicional**.

**¿Y si no encuentro el UniFi Controller?**  
Preguntar a sistemas del hotel dónde está instalada la “UniFi Network Application” o si usan UniFi Cloud (ui.com).

**¿Shomer puede hacerlo solo sin Ricardo?**  
Parcialmente: ya monitorea APs e impresoras por ping. **SNMP hay que activarlo en cada switch físico** — eso requiere acceso al rack/switch.

---

*Documento generado por USB Ingeniería — Shomer Sentinel 2.0. Versión 1.0 — 13 jun 2026.*
