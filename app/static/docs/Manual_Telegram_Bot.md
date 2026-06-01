# Manual de Configuración — Bot Telegram Shomer

**Para quién:** Juan Pablo (lo que hace él) y el técnico/cliente (lo que hace en campo)  
**Versión:** 23 mayo 2026

---

## Cómo funciona el sistema de Telegram en Shomer

Shomer usa **dos cosas distintas** en Telegram:

| Componente | Quién lo crea | Para qué |
|-----------|--------------|---------|
| **Bot** | Juan Pablo — una vez por cliente | Es el "número de teléfono" del sistema. Cada cliente tiene su propio bot con su propio nombre |
| **Chat ID** | El técnico/cliente — en campo | Es el "destino" donde llegan las alertas. Puede ser un grupo o un chat personal |

---

# PARTE 1 — LO QUE HACE JUAN PABLO (una sola vez por cliente)

## Paso 1 — Crear el bot en BotFather

BotFather es el bot oficial de Telegram para crear y administrar bots.

1. Abrir Telegram y buscar: **@BotFather**
2. Escribir: `/newbot`
3. BotFather pregunta el **nombre del bot** (el nombre visible):
   ```
   Hotel Plaza Bogotá
   ```
   Este nombre aparece en el chat cuando el bot manda mensajes. Usar el nombre del cliente.

4. BotFather pregunta el **username del bot** (el identificador único, sin espacios, termina en `bot`):
   ```
   ShomerHotelPlazaBot
   ```
   ⚠️ El username es único en todo Telegram — si ya existe, elegir otro. Sugerencias:
   - `ShomerHotelPlazaBot`
   - `ShomerEmpresaABCBot`
   - `ShomerHotelRealBogotaBot`

5. BotFather responde con el **token**. Se ve así:
   ```
   7412589630:AAHxyz_ejemplo_token_aqui_no_real_abc123
   ```
   ⚠️ **Guardar este token de inmediato** — es la "contraseña" del bot. Si se pierde, hay que crear otro bot.

## Paso 2 — Configurar descripción y foto del bot (opcional pero recomendado)

En BotFather:
```
/setdescription → seleccionar el bot → escribir:
"Asistente de red Shomer Sentinel — monitoreo, alertas y soporte técnico"

/setuserpic → seleccionar el bot → enviar el logo de USB Ingeniería
```

## Paso 3 — Guardar el token en el servidor

El token se guarda en el archivo `.env` del agente Shomer en el servidor del cliente:

```bash
# Conectarse al servidor del cliente
ssh usb_admin@[IP-del-servidor]

# Editar el archivo de variables
sudo nano /storage/shomer-agent/.env

# Línea a completar:
TELEGRAM_BOT_TOKEN=7412589630:AAHxyz_tu_token_real_aqui
SITE_NAME=Hotel Plaza Bogotá
```

## Paso 4 — Anotar el token en el registro del cliente

Guardar en la hoja de datos del cliente:
```
Bot name: Hotel Plaza Bogotá
Bot username: @ShomerHotelPlazaBot
Token: 7412589630:AAHxyz...
Fecha creación: 22 mayo 2026
```

## Paso 5 — OpenAI para chat inteligente (opcional, recomendado)

El bot funciona **sin costo** solo con Groq (monitores + fallback). Para que las **preguntas en lenguaje natural** del técnico respondan mejor, se puede activar OpenAI:

1. Entrar a [platform.openai.com](https://platform.openai.com) con la cuenta USB (o cuenta del cliente).
2. **API keys** → Create new secret key → copiar (solo se muestra una vez).
3. **Settings → Limits** → Monthly budget → **$5 USD** (tope duro en la web).
4. En el servidor del cliente, editar `/storage/shomer-agent/.env`:

```bash
LLM_PROVIDER_INTERACTIVE=openai
OPENAI_API_KEY=sk-proj-...tu_key...
OPENAI_MODEL=gpt-4o-mini
OPENAI_LIMIT_PER_MESSAGE=2000
OPENAI_LIMIT_PER_USER_DAILY=8000
OPENAI_LIMIT_DAILY=12000
```

5. Reiniciar el agente (`.env` no se recarga con `restart`):

```bash
cd /storage/shomer-agent && sudo docker compose down && sudo docker compose up -d
```

**Costo esperado:** ~$0.05–0.15 USD/mes por Shomer con los caps de código. Los 20 monitores automáticos siguen en Groq gratis.

**Sin OpenAI:** dejar `LLM_PROVIDER_INTERACTIVE=groq` (default) — el bot responde igual, con calidad algo menor en texto libre.

**Lab Utah `.205`:** tiene dos rutas a internet; en producción con una sola NIC (ej. Bogotá) no hace falta configuración extra de red.

---

# PARTE 2 — LO QUE HACE EL TÉCNICO EN CAMPO

## Paso 1 — Crear el grupo de Telegram

El técnico crea un grupo de Telegram donde van a llegar las alertas del sistema.

1. Abrir Telegram → ícono de lápiz (nuevo chat) → **Nuevo grupo**
2. Agregar los participantes del cliente que quieren recibir alertas (gerente, encargado de IT, etc.)
3. Nombre del grupo: algo claro como `Alertas Red Hotel Plaza` o `Shomer Bogotá`
4. Crear el grupo

## Paso 2 — Agregar el bot al grupo

1. En el grupo recién creado → tocar el nombre del grupo arriba → **Agregar miembros**
2. Buscar el username del bot que creó Juan Pablo (ej. `@ShomerHotelPlazaBot`)
3. Agregarlo al grupo
4. Darle permisos de **administrador** al bot (necesario para que pueda mandar mensajes):
   - Tocar el nombre del bot dentro del grupo
   - Seleccionar **Promover a administrador**
   - Activar al menos: "Enviar mensajes" y "Publicar mensajes"

## Paso 3 — Obtener el Chat ID del grupo

El Chat ID es el número que identifica el grupo. El sistema lo necesita para saber a dónde mandar las alertas.

**Método fácil — usando @userinfobot:**

1. En el grupo → buscar y agregar el bot **@userinfobot** (bot oficial de utilidad)
2. Escribir en el grupo: `/start` o `/id`
3. El bot responde con el ID del grupo. Se ve así:
   ```
   Chat ID: -1001234567890
   ```
   ⚠️ Los IDs de grupos empiezan con `-100`. Es normal. Copiar el número completo incluyendo el signo `-`.

**Método alternativo — via URL de Telegram:**

1. En Telegram Web (web.telegram.org), abrir el grupo
2. La URL se ve así: `https://web.telegram.org/k/#-1001234567890`
3. El Chat ID es el número después de `#` (incluyendo el `-`)

## Paso 4 — Configurar el Chat ID en el panel Shomer

1. Abrir el panel Shomer: `https://[IP-del-Shomer]`
2. Ir a **Configuración → Setup** (o la sección de Telegram)
3. Pegar el Chat ID en el campo correspondiente
4. Clic en **Guardar**
5. Clic en **Probar Telegram** — debe llegar un mensaje de prueba al grupo en menos de 10 segundos

Si el mensaje llega → ✅ Telegram configurado correctamente.

---

# PARTE 3 — VERIFICACIÓN FINAL

## Prueba completa desde el bot

Una vez configurado, escribir en el grupo de Telegram:

```
/salud
```

El bot debe responder con el estado de los servicios del servidor. Si responde → todo está funcionando.

```
/verificar
```

El bot hace un checklist completo de la instalación. Cada ítem en verde ✅ es correcto. Los ítems en amarillo ⚠️ indican qué falta completar.

---

# PARTE 4 — SOLUCIÓN DE PROBLEMAS

## El mensaje de prueba no llega

**Verificar 1 — El servidor tiene internet:**
```
https://[IP-del-Shomer]/system-status
```
Ver sección "WAN del servidor" — debe estar en verde.

**Verificar 2 — El Chat ID está correcto:**
- Los grupos tienen ID negativo (ej. `-1001234567890`)
- Los chats personales tienen ID positivo (ej. `123456789`)
- Copiar el número completo incluyendo el signo `-`

**Verificar 3 — El bot está en el grupo:**
- Abrir el grupo → lista de miembros → verificar que el bot aparece
- Si no aparece: agregar el bot al grupo nuevamente

**Verificar 4 — El bot tiene permisos:**
- En el grupo → info del bot → debe decir "Administrador"
- Si dice "Miembro": promoverlo a administrador

## El bot no responde a comandos

```bash
# Ver logs del bot en el servidor
sudo docker compose -f /storage/shomer-agent/docker-compose.yml logs --tail=50

# Reiniciar el bot
sudo systemctl restart shomer-agent
```

## Cambiar el grupo de alertas (nuevo técnico o nuevo chat)

1. Crear el nuevo grupo y agregar el bot (mismo proceso anterior)
2. Obtener el nuevo Chat ID
3. Panel Shomer → Setup → actualizar Chat ID → Guardar
4. Probar con el botón de prueba

El cambio es inmediato — no requiere reiniciar el servidor.

---

# PARTE 5 — REFERENCIA RÁPIDA

## Comandos útiles del bot (para el técnico)

| Comando | Para qué |
|---------|---------|
| `/salud` | Estado del servidor y servicios |
| `/equipos` | Lista de APs monitoreados |
| `/alertas` | Últimas alertas de seguridad |
| `/mantenimiento` | Activar/desactivar pausa de reboots |
| `/verificar` | Checklist completo de la instalación |
| `/usuario` | Cómo crear usuario de servicio en cada OS |
| `/ayuda` | Lista completa de comandos |

## Datos que necesitas por cliente

| Dato | Dónde va |
|------|---------|
| Token del bot | Archivo `.env` del servidor + registro interno |
| Chat ID del grupo | Panel Shomer → Setup → campo Chat ID |
| Nombre del bot | BotFather (ya configurado) |
| Nombre del sitio (SITE_NAME) | Archivo `.env` del servidor |

---

*USB Ingeniería SAS — Manual de Telegram para Shomer Sentinel 2.0*  
*Mayo 2026*
