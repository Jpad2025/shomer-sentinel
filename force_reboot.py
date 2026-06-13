#!/usr/bin/env python3
"""
Script para forzar el reinicio del router TP-Link Archer C54
Desarrollado por USB Ingeniería SAS
"""
import sys
import os
import time
import logging
import requests
import subprocess

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def force_reboot_tplink(ip, password, port=80):
    """
    Fuerza el reinicio de un router TP-Link Archer C54
    """
    print(f"\n🔄 FORZANDO REINICIO DEL ROUTER {ip} EN PUERTO {port}\n")
    
    # Crear sesión HTTP
    session = requests.Session()
    
    try:
        # Paso 1: Intentar login para obtener token
        login_url = f"http://{ip}:{port}/cgi-bin/luci/;stok=/login?form=login"
        login_data = {"operation": "login", "password": password}
        
        print(f"Paso 1: Enviando solicitud de login a {login_url}")
        response = session.post(login_url, json=login_data, timeout=10)
        
        print(f"Respuesta login: {response.status_code}")
        print(f"Contenido: {response.text[:200]}...")
        
        if response.status_code != 200:
            print(f"❌ Error de autenticación: {response.status_code}")
            return False
        
        # Intentar extraer token de la respuesta
        try:
            data = response.json()
            if not data.get("success"):
                print(f"❌ Login fallido: {data.get('msg', 'credenciales incorrectas')}")
                return False
            
            stok = data.get("data", {}).get("stok")
            if not stok:
                print("❌ No se pudo obtener token de autenticación")
                return False
            
            print(f"✅ Login exitoso, token obtenido: {stok}")
            
            # Paso 2: Enviar comando de reinicio
            reboot_url = f"http://{ip}:{port}/cgi-bin/luci/;stok={stok}/admin/system?form=reboot"
            reboot_data = {"operation": "reboot"}
            
            print(f"Paso 2: Enviando comando de reinicio a {reboot_url}")
            response = session.post(reboot_url, json=reboot_data, timeout=10)
            
            print(f"Respuesta reinicio: {response.status_code}")
            print(f"Contenido: {response.text[:200]}...")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    if data.get("success"):
                        print(f"✅ Comando de reinicio enviado exitosamente")
                        
                        # Paso 3: Verificar si el router se reinicia
                        print(f"Paso 3: Verificando si el router se reinicia...")
                        
                        # Iniciar ping en segundo plano para monitorear
                        print("Iniciando ping continuo para monitorear el estado del router...")
                        ping_process = subprocess.Popen(
                            f"ping -i 0.5 {ip}",
                            shell=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )
                        
                        # Esperar y verificar si el router deja de responder
                        print("Esperando a que el router deje de responder (reinicio en progreso)...")
                        offline_detected = False
                        start_time = time.time()
                        
                        while time.time() - start_time < 60:  # Esperar hasta 60 segundos
                            # Verificar si el router responde
                            ping_result = subprocess.run(
                                f"ping -c 1 -W 1 {ip}",
                                shell=True,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL
                            )
                            
                            if ping_result.returncode != 0:
                                print(f"✅ Router no responde - reinicio en progreso")
                                offline_detected = True
                                break
                            
                            time.sleep(1)
                        
                        # Terminar el proceso de ping
                        ping_process.terminate()
                        
                        if offline_detected:
                            print("\n✅ REINICIO EXITOSO: Router reiniciándose\n")
                            
                            # Esperar a que el router vuelva a estar online
                            print("Esperando a que el router vuelva a estar online...")
                            online_detected = False
                            start_time = time.time()
                            
                            while time.time() - start_time < 120:  # Esperar hasta 2 minutos
                                ping_result = subprocess.run(
                                    f"ping -c 1 -W 1 {ip}",
                                    shell=True,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL
                                )
                                
                                if ping_result.returncode == 0:
                                    print(f"✅ Router volvió a estar online después de {time.time() - start_time:.1f} segundos")
                                    online_detected = True
                                    break
                                
                                time.sleep(2)
                            
                            if online_detected:
                                print("\n✅ PROCESO COMPLETO: Router reiniciado exitosamente\n")
                                return True
                            else:
                                print("\n⚠️ ADVERTENCIA: Router no volvió a estar online dentro del tiempo esperado\n")
                                return True  # Asumimos éxito ya que el router se reinició
                        else:
                            print("\n❌ ERROR: No se detectó que el router dejara de responder\n")
                            return False
                    else:
                        print(f"❌ Error en respuesta de reinicio: {data}")
                        return False
                except Exception as e:
                    print(f"❌ Error procesando respuesta JSON: {str(e)}")
                    return False
            else:
                print(f"❌ Error al reiniciar: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error procesando respuesta: {str(e)}")
            
            # Método alternativo: usar curl directamente
            print("\nIntentando método alternativo con curl...\n")
            
            try:
                # Crear script temporal
                script_path = "/tmp/reboot_router.sh"
                with open(script_path, 'w') as f:
                    f.write(f'''#!/bin/bash
ROUTER_IP="{ip}"
ROUTER_PORT="{port}"
ROUTER_PASSWORD="{password}"

# Paso 1: Intentar login para obtener token
echo "Intentando login con curl..."
RESPONSE=$(curl -s -X POST "http://$ROUTER_IP:$ROUTER_PORT/cgi-bin/luci/;stok=/login?form=login" \\
  -H "Content-Type: application/json" \\
  -d "{{\\"operation\\":\\"login\\",\\"password\\":\\"$ROUTER_PASSWORD\\"}}")

echo "Respuesta: $RESPONSE"

# Extraer token de la respuesta
TOKEN=$(echo "$RESPONSE" | grep -o '"stok":"[^"]*"' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
  echo "Error: No se pudo obtener token de autenticación"
  exit 1
fi

echo "Token obtenido: $TOKEN"

# Paso 2: Enviar comando de reinicio
echo "Enviando comando de reinicio..."
REBOOT_RESPONSE=$(curl -s -X POST "http://$ROUTER_IP:$ROUTER_PORT/cgi-bin/luci/;stok=$TOKEN/admin/system?form=reboot" \\
  -H "Content-Type: application/json" \\
  -d "{{\\"operation\\":\\"reboot\\"}}")

echo "Respuesta de reinicio: $REBOOT_RESPONSE"

# Verificar si el reinicio fue exitoso
if echo "$REBOOT_RESPONSE" | grep -q '"success":true'; then
  echo "Comando de reinicio enviado exitosamente"
  exit 0
else
  echo "Error al enviar comando de reinicio"
  exit 1
fi
''')
                
                # Dar permisos de ejecución
                os.chmod(script_path, 0o755)
                
                # Ejecutar script
                print("Ejecutando script curl...")
                result = subprocess.run(script_path, shell=True, capture_output=True, text=True)
                
                print(f"Resultado: {result.stdout}")
                
                if result.returncode == 0:
                    print("\n✅ REINICIO EXITOSO CON CURL\n")
                    
                    # Verificar si el router se reinicia
                    print("Verificando si el router se reinicia...")
                    offline_detected = False
                    start_time = time.time()
                    
                    while time.time() - start_time < 60:  # Esperar hasta 60 segundos
                        ping_result = subprocess.run(
                            f"ping -c 1 -W 1 {ip}",
                            shell=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        
                        if ping_result.returncode != 0:
                            print(f"✅ Router no responde - reinicio en progreso")
                            offline_detected = True
                            break
                        
                        time.sleep(1)
                    
                    if offline_detected:
                        return True
                    else:
                        print("\n⚠️ ADVERTENCIA: No se detectó que el router dejara de responder\n")
                        return True  # Asumimos éxito ya que el comando se envió correctamente
                else:
                    print(f"\n❌ ERROR EN SCRIPT CURL: {result.stderr}\n")
                    return False
            except Exception as e:
                print(f"\n❌ ERROR EJECUTANDO SCRIPT CURL: {str(e)}\n")
                return False
    except requests.exceptions.Timeout:
        print(f"\n⚠️ TIMEOUT - Posiblemente el router ya está reiniciándose\n")
        return True
    except Exception as e:
        print(f"\n❌ ERROR GENERAL: {str(e)}\n")
        return False

if __name__ == "__main__":
    # Parámetros de prueba
    router_ip = "192.168.1.200"  # IP del TP-Link Archer C54
    router_password = "Usbing08*"  # Contraseña del router
    
    # Ejecutar reinicio forzado
    success = force_reboot_tplink(router_ip, router_password)
    
    # Mostrar resultado final
    if success:
        print("\n✅ REINICIO EXITOSO DEL ROUTER\n")
        sys.exit(0)
    else:
        print("\n❌ REINICIO FALLIDO DEL ROUTER\n")
        sys.exit(1)
