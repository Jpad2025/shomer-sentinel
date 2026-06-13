"""
Script completo para probar reinicio de routers
"""
import sys
import os
import time
import subprocess
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Añadir ruta para importaciones
sys.path.append('/opt/network_monitor/app/backend')

# Importar gestor HTTP
try:
    from router_http_manager import RouterHTTPManager
    manager = RouterHTTPManager(timeout=10)
except Exception as e:
    print(f"❌ Error importando RouterHTTPManager: {str(e)}")
    sys.exit(1)

def ping_device(ip, count=1):
    """Verificar si un dispositivo responde a ping"""
    try:
        result = subprocess.run(
            f"ping -c {count} -W 2 {ip}",
            shell=True,
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception:
        return False

def wait_for_device(ip, timeout=120, interval=5):
    """Esperar a que un dispositivo vuelva a estar online"""
    print(f"Esperando a que {ip} vuelva a estar online (máx {timeout}s)...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        if ping_device(ip):
            elapsed = int(time.time() - start_time)
            print(f"✅ Dispositivo {ip} está online nuevamente después de {elapsed}s")
            return True
        
        # Mostrar progreso
        dots = "." * (int((time.time() - start_time) / interval) % 4)
        print(f"Esperando{dots.ljust(4)}", end="\r")
        
        time.sleep(interval)
    
    print(f"❌ Timeout: {ip} no respondió después de {timeout}s")
    return False

def test_device(name, ip, username, password, brand):
    """Probar reinicio de un dispositivo"""
    print("\n" + "="*60)
    print(f"PROBANDO {name} ({ip})")
    print("="*60)
    
    # 1. Verificar que el dispositivo está online
    print("\n1️⃣ Verificando conectividad inicial...")
    if not ping_device(ip, count=3):
        print(f"❌ ERROR: No se puede hacer ping a {ip}")
        return False
    
    print(f"✅ {name} responde a ping")
    
    # 2. Intentar reiniciar
    print("\n2️⃣ Enviando comando de reinicio...")
    try:
        success, message = manager.reboot_device(
            ip=ip,
            username=username,
            password=password,
            brand=brand
        )
        
        if success:
            print(f"✅ Comando de reinicio enviado: {message}")
        else:
            print(f"❌ Error enviando comando: {message}")
            return False
    except Exception as e:
        print(f"❌ Excepción: {str(e)}")
        return False
    
    # 3. Esperar a que el dispositivo se reinicie
    print("\n3️⃣ Esperando reinicio...")
    time.sleep(10)  # Dar tiempo para que el dispositivo se apague
    
    # 4. Esperar a que vuelva a estar online
    print("\n4️⃣ Esperando a que vuelva a estar online...")
    if wait_for_device(ip, timeout=120):
        print(f"✅ ÉXITO: {name} se reinició correctamente")
        return True
    else:
        print(f"❌ FALLO: {name} no volvió a estar online")
        return False

def main():
    """Función principal"""
    print("\n🧪 PRUEBA DE REINICIO DE ROUTERS")
    print("===============================")
    
    # Definir dispositivos de prueba
    devices = [
        {
            "name": "TP-Link",
            "ip": "192.168.1.200",
            "username": "admin",
            "password": "admin",
            "brand": "tplink"
        },
        {
            "name": "Netgear",
            "ip": "192.168.1.201",
            "username": "admin",
            "password": "password",
            "brand": "netgear"
        }
    ]
    
    # Preguntar qué dispositivo probar
    print("\nDispositivos disponibles:")
    for i, device in enumerate(devices):
        print(f"{i+1}. {device['name']} ({device['ip']})")
    
    choice = input("\n¿Qué dispositivo quieres probar? (1/2/ambos): ").strip().lower()
    
    results = []
    
    if choice == "1" or choice == "ambos":
        print("\nProbando TP-Link...")
        tp_result = test_device(**devices[0])
        results.append((devices[0]["name"], tp_result))
    
    if choice == "2" or choice == "ambos":
        print("\nProbando Netgear...")
        ng_result = test_device(**devices[1])
        results.append((devices[1]["name"], ng_result))
    
    # Mostrar resumen
    print("\n" + "="*60)
    print("RESUMEN DE PRUEBAS")
    print("="*60)
    
    for name, result in results:
        status = "✅ ÉXITO" if result else "❌ FALLO"
        print(f"{name}: {status}")

if __name__ == "__main__":
    main()
