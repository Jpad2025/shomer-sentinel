# Reporte técnico — Caídas recurrentes de datáfonos y POS

**Sitio:** Hotel Ópera
**Fecha:** 12 de septiembre de 2026
**Período analizado:** últimos 30 días
**Elaborado por:** Shomer Sentinel (análisis automatizado, verificado)

---

## Resumen para quien decide

Los datáfonos y las impresoras de punto de venta figuran como los equipos que
más se "caen" del hotel: **128 caídas en 30 días entre 4 equipos**. Sin embargo,
la evidencia indica que **la red del hotel no es la causa** y que **buena parte
de esas caídas no son fallas reales**, sino un efecto de cómo se están
monitoreando esos equipos.

Hay **una acción concreta y de bajo costo** que debería reducirlas de forma
inmediata (punto 4), y **una verificación de campo pendiente** para descartar un
problema eléctrico o de cableado en dos datáfonos (punto 5).

---

## 1. Qué se observó

Caídas registradas en 30 días, por tipo de equipo:

| Tipo de equipo | Equipos | Caídas | Promedio por equipo |
|---|---:|---:|---:|
| **Datáfonos / POS** | 4 | **128** | **32** |
| Cámaras | 3 | 34 | 11 |
| Servidores | 2 | 18 | 9 |
| Access Points (WiFi) | 30 | 94 | 3,1 |
| Switches | 8 | 24 | 3,0 |
| Impresoras (con puerto configurado) | 2 | 4 | 2,0 |
| **Router / gateway** | 1 | **0** | **0** |

Los equipos más afectados:

| Equipo | Caídas | Tiempo típico hasta volver |
|---|---:|---|
| Terminal pago Ingenico .136 | 41 | ~30 segundos |
| Terminal pago Ingenico .143 | 38 | ~30 segundos |
| AP Oficina Cocina | 33 | ~1,7 minutos |
| Impresora POS Bixolon .243 | 30 | ~30 segundos |

---

## 2. Por qué la red del hotel no es la causa

Tres hechos lo sostienen:

1. **El router del hotel no se cayó ni una sola vez** en 30 días.
2. **Los switches y los access points casi no fallan**: 3 caídas por equipo en un
   mes, contra 32 de los POS. Si el problema fuera la red compartida, todos los
   equipos se verían afectados por igual, y no es el caso.
3. **Los equipos vuelven solos en unos 30 segundos**, sin que nadie intervenga.
   Un cable suelto, un puerto dañado o una falla de switch no se arreglan solos
   cada vez.

---

## 3. La causa más probable

**Los cuatro equipos POS se están vigilando únicamente con "ping"**, sin ninguna
comprobación adicional. Las dos impresoras que además tienen configurado un
puerto de servicio y consulta SNMP registran **4 caídas en el mismo período,
frente a 128**.

| Equipos | Cómo se vigilan | Caídas en 30 días |
|---|---|---:|
| 2 impresoras (Cocina, Recepción) | ping + puerto 9100 + SNMP | **4** |
| 4 POS (Ingenico y Bixolon) | **solo ping** | **128** |

Los datáfonos y las impresoras de punto de venta suelen entrar en reposo o
priorizar su tarea de cobro frente a responder mensajes de red. Cuando eso
ocurre, dejan de contestar el ping durante unos segundos y el sistema los
declara caídos, aunque el equipo esté operativo.

Esto explica los tres hechos del punto 2 a la vez.

---

## 4. Acción recomendada (inmediata, bajo costo)

**Configurar la comprobación por puerto de servicio en los cuatro equipos POS**,
igual que ya está en las dos impresoras que no presentan el problema.

Con eso, el sistema dejaría de depender del ping: si el equipo responde en su
puerto de servicio, se considera operativo aunque no conteste el ping.

- **Esfuerzo:** configuración, sin cambios físicos ni de red.
- **Efecto esperado:** eliminar la mayor parte de las 128 caídas registradas.
- **Riesgo:** ninguno. No modifica la red ni los equipos, solo cómo se verifican.
- **Requisito:** confirmar con el proveedor de los datáfonos qué puerto de
  servicio exponen los Ingenico. Las Bixolon normalmente usan el 9100, igual que
  las impresoras que ya funcionan bien.

---

## 5. Verificación de campo pendiente

Hay un hecho que **no queda explicado** por lo anterior y conviene revisar en
sitio:

**Los dos datáfonos Ingenico (.136 y .143) se caen juntos, en el mismo minuto**,
de forma repetida — se registraron 8 episodios simultáneos en los últimos días,
principalmente entre las 9:00 y las 10:00 de la mañana.

Que dos equipos distintos fallen exactamente al mismo tiempo sugiere que
**comparten algo físico**: el mismo switch, el mismo punto de red, la misma toma
eléctrica o el mismo circuito.

**Qué revisar en la próxima visita:**

1. Dónde están instalados físicamente ambos datáfonos (hoy figuran como
   "ubicación por confirmar" en el inventario).
2. Si comparten switch, regleta eléctrica o toma de corriente.
3. Estado del cableado y de las conexiones de ambos.

El horario (9:00–10:00) coincide con el inicio de actividad de la mañana, y la
frecuencia **aumenta los fines de semana** (17 caídas los sábados y 11 los
domingos, contra 7–9 entre semana), cuando el hotel tiene más ocupación. Eso es
compatible tanto con mayor uso de los equipos como con una instalación eléctrica
exigida en horas pico.

---

## 6. Qué NO hacer

- **No reemplazar los datáfonos** por ahora: no hay evidencia de falla del
  equipo, y vuelven a operar solos en segundos.
- **No intervenir la red del hotel**: el router, los switches y los access points
  muestran un comportamiento sano.
- **No enviar un técnico solo a "revisar el cable"** de estos equipos antes de
  aplicar el punto 4: la mayoría de las caídas registradas probablemente
  desaparezcan con la configuración, y eso permitirá ver cuáles eran reales.

---

## 7. Cómo se llegó a estas conclusiones

Todos los datos provienen del registro histórico del propio sistema de
monitoreo, sobre 30 días corridos:

- Registro de transiciones de estado de los 51 equipos monitoreados.
- Comparación de tasas de caída entre tipos de equipo.
- Medición del tiempo que tarda cada equipo en volver (mediana, para que un caso
  aislado no distorsione el resultado).
- Análisis de coincidencia temporal entre equipos, por minuto.
- Comparación de la configuración de monitoreo entre equipos afectados y no
  afectados.

Las conclusiones de los puntos 2 y 3 se apoyan en datos verificados. El punto 5
es una **hipótesis fundada** que requiere comprobación física en sitio.
