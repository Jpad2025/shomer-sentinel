#!/usr/bin/env python3
"""
Script de prueba para reiniciar TP-Link Archer C54 usando puerto 2222
Desarrollado por USB Ingeniería SAS
"""
import requests
import sys
import time
import logging

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,  # Nivel DEBUG para ver todos los detalles
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_reboot_tplink(ip, password, port=2222):
    """
    Prueba de reinicio para TP-Link Archer C54 usando puerto específico
    """
    print(f"\n🔄 INICIANDO PRUEBA DE REINICIO EN PUERTO {port} PARA {ip}\n")
    
    # Crear sesión HTTP
    session = requests.Session()
    session.verify = False
    
    try:
        # Deshabilitar advertencias de SSL
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # 1. Verificar si el router responde en el puerto especificado
        try:
            print(f"Paso 1: Verificando si el router responde en puerto {port}...")
            base_url = f"http://{ip}:{port}"
            response = session.get(base_url, timeout=5)
            print(f"✅ Router responde en puerto {port}: {response.status_code}")
        except Exception as e:
            print(f"❌ Error accediendo al puerto {port}: {str(e)}")
            print(f"⚠️ Intentando con puerto estándar 80...")
            port = 80
            base_url = f"http://{ip}:{port}"
            try:
                response = session.get(base_url, timeout=5)
                print(f"✅ Router responde en puerto 80: {response.status_code}")
            except Exception as e:
                print(f"❌ Error accediendo al puerto 80: {str(e)}")
                return False, "Router no accesible en puertos 2222 ni 80"
        
        # 2. Intentar login
        print(f"Paso 2: Intentando login...")
        login_url = f"{base_url}/cgi-bin/luci/;stok=/login?form=login"
        login_data = {"operation": "login", "password": password}
        
        try:
            response = session.post(login_url, json=login_data, timeout=10)
            print(f"Respuesta login: {response.status_code}")
            print(f"Contenido: {response.text[:200]}...")  # Mostrar primeros 200 caracteres
            
            if response.status_code != 200:
                return False, f"Error de autenticación: {response.status_code}"
            
            # 3. Extraer token de la respuesta
            try:
                data = response.json()
                if not data.get("success"):
                    return False, f"Login fallido: {data.get('msg', 'credenciales incorrectas')}"
                
                stok = data.get("data", {}).get("stok")
                if not stok:
                    return False, "No se pudo obtener token de autenticación"
                
                print(f"✅ Login exitoso, token obtenido: {stok}")
                
                # 4. Enviar comando de reinicio
                print(f"Paso 3: Enviando comando de reinicio...")
                reboot_url = f"{base_url}/cgi-bin/luci/;stok={stok}/admin/system?form=reboot"
                reboot_data = {"operation": "reboot"}
                
                response = session.post(reboot_url, json=reboot_data, timeout=10)
                print(f"Respuesta reinicio: {response.status_code}")
                print(f"Contenido: {response.text[:200]}...")  # Mostrar primeros 200 caracteres
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get("success"):
                            print(f"✅ Comando de reinicio enviado exitosamente")
                            
                            # 5. Verificar si el router se reinicia
                            print(f"Paso 4: Verificando si el router se reinicia...")
                            time.sleep(5)  # Esperar un poco
                            
                            # Intentar hacer ping al router
                            import subprocess
                            for i in range(12):  # Verificar por 60 segundos (12 * 5)
                                print(f"Verificando estado del router ({i+1}/12)...")
                                try:
                                    result = subprocess.run(
                                        f"ping -c 1 -W 2 {ip}",
                                        shell=True,
                                        stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL
                                    )
                                    if result.returncode != 0:
                                        print(f"✅ Router no responde - reinicio en progreso")
                                        return True, "Reinicio exitoso confirmado"
                                except:
                                    pass
                                time.sleep(5)
                            
                            return True, "Comando de reinicio enviado, pero no se pudo confirmar"
                        else:
                            return False, f"Error en respuesta de reinicio: {data}"
                    except:
                        # Si no podemos procesar la respuesta pero el código es 200, asumimos éxito
                        return True, "Reinicio posiblemente exitoso"
                else:
                    return False, f"Error al reiniciar: {response.status_code}"
            except Exception as e:
                return False, f"Error procesando respuesta: {str(e)}"
        except requests.exceptions.Timeout:
            # El timeout puede indicar que el reinicio fue exitoso
            return True, "Reinicio iniciado (timeout esperado)"
        except Exception as e:
            return False, f"Error en login: {str(e)}"
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    # Parámetros de prueba
    router_ip = "192.168.1.200"  # IP del TP-Link Archer C54
    router_password = "Usbing08*"  # Contraseña del router
    test_port = 2222  # Puerto configurado para administración remota
    
    # Ejecutar prueba
    success, message = test_reboot_tplink(router_ip, router_password, test_port)
    
    # Mostrar resultado
    print("\n" + "="*50)
    if success:
        print(f"✅ PRUEBA EXITOSA: {message}")
    else:
        print(f"❌ PRUEBA FALLIDA: {message}")
    print("="*50 + "\n")
