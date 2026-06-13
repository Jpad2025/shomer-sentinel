#!/usr/bin/env python3
"""
Script para probar métodos de reinicio en routers reales
Desarrollado por USB Ingeniería SAS
"""
import sys
import os
import time
import logging
import argparse
import json
import datetime
import subprocess
from typing import Dict, List, Tuple, Any

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("/opt/network_monitor/test_results/reboot_tests.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Importar módulos del sistema
sys.path.append('/opt/network_monitor')
try:
    from app.backend.router_http_manager import RouterHTTPManager
    from app.scripts.advanced_recovery import advanced_recovery
except ImportError as e:
    logger.error(f"Error importando módulos: {str(e)}")
    sys.exit(1)

def ping_device(ip: str, count: int = 1, timeout: int = 2) -> bool:
    """Verificar si un dispositivo responde a ping"""
    try:
        result = subprocess.run(
            f"ping -c {count} -W {timeout} {ip}",
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return result.returncode == 0
    except:
        return False

def wait_for_reboot(ip: str, max_wait: int = 180) -> Tuple[bool, int]:
    """
    Esperar a que un dispositivo se reinicie
    
    Args:
        ip: Dirección IP del dispositivo
        max_wait: Tiempo máximo de espera en segundos
    
    Returns:
        Tuple[bool, int]: (éxito, tiempo_total)
    """
    logger.info(f"Esperando a que {ip} se reinicie...")
    
    # Verificar que el dispositivo está online inicialmente
    if not ping_device(ip):
        logger.warning(f"El dispositivo {ip} no está online inicialmente")
        return False, 0
    
    start_time = time.time()
    offline_detected = False
    
    # Esperar hasta que el dispositivo se vaya offline
    while time.time() - start_time < max_wait:
        if not ping_device(ip):
            logger.info(f"Dispositivo {ip} offline detectado después de {time.time() - start_time:.1f} segundos")
            offline_detected = True
            break
        time.sleep(2)
    
    if not offline_detected:
        logger.warning(f"El dispositivo {ip} nunca se fue offline")
        return False, 0
    
    # Esperar hasta que el dispositivo vuelva online
    while time.time() - start_time < max_wait:
        if ping_device(ip):
            total_time = time.time() - start_time
            logger.info(f"Dispositivo {ip} volvió online después de {total_time:.1f} segundos")
            return True, int(total_time)
        time.sleep(2)
    
    logger.warning(f"El dispositivo {ip} no volvió online dentro del tiempo límite")
    return False, 0

def test_http_method(ip: str, username: str, password: str, brand: str) -> Dict[str, Any]:
    """Probar método HTTP estándar"""
    logger.info(f"Probando método HTTP estándar para {ip} (marca: {brand})...")
    
    result = {
        "method": "http_standard",
        "ip": ip,
        "brand": brand,
        "timestamp": datetime.datetime.now().isoformat(),
        "success": False,
        "reboot_time": 0,
        "message": ""
    }
    
    try:
        # Crear instancia del gestor HTTP
        http_manager = RouterHTTPManager(timeout=10, authorization_level=2)
        
        # Intentar reinicio
        success, message = http_manager.reboot_device(ip, username, password, brand)
        result["message"] = message
        
        if success:
            # Esperar a que el dispositivo se reinicie
            reboot_success, reboot_time = wait_for_reboot(ip)
            result["success"] = reboot_success
            result["reboot_time"] = reboot_time
            
            if reboot_success:
                logger.info(f"Reinicio HTTP exitoso para {ip} en {reboot_time} segundos")
            else:
                logger.warning(f"Reinicio HTTP reportado como exitoso, pero no se detectó reinicio real para {ip}")
        else:
            logger.warning(f"Reinicio HTTP fallido para {ip}: {message}")
    except Exception as e:
        logger.error(f"Error en test_http_method para {ip}: {str(e)}")
        result["message"] = f"Error: {str(e)}"
    
    return result

def test_advanced_recovery(ip: str, username: str, password: str, brand: str) -> Dict[str, Any]:
    """Probar recuperación avanzada"""
    logger.info(f"Probando recuperación avanzada para {ip} (marca: {brand})...")
    
    result = {
        "method": "advanced_recovery",
        "ip": ip,
        "brand": brand,
        "timestamp": datetime.datetime.now().isoformat(),
        "success": False,
        "reboot_time": 0,
        "message": ""
    }
    
    try:
        # Crear dispositivo simulado para la prueba
        device = {
            "id": 999,
            "name": f"Test Device {ip}",
            "ip_address": ip,
            "mac_address": "00:00:00:00:00:00",
            "brand": brand,
            "ssh_user": username,
            "ssh_password": password
        }
        
        # Intentar recuperación
        success, message = advanced_recovery.recover_device(device)
        result["message"] = message
        
        if success:
            # Esperar a que el dispositivo se reinicie
            reboot_success, reboot_time = wait_for_reboot(ip)
            result["success"] = reboot_success
            result["reboot_time"] = reboot_time
            
            if reboot_success:
                logger.info(f"Recuperación avanzada exitosa para {ip} en {reboot_time} segundos")
            else:
                logger.warning(f"Recuperación avanzada reportada como exitosa, pero no se detectó reinicio real para {ip}")
        else:
            logger.warning(f"Recuperación avanzada fallida para {ip}: {message}")
    except Exception as e:
        logger.error(f"Error en test_advanced_recovery para {ip}: {str(e)}")
        result["message"] = f"Error: {str(e)}"
    
    return result

def test_browser_emulation(ip: str, username: str, password: str) -> Dict[str, Any]:
    """Probar emulación de navegador"""
    logger.info(f"Probando emulación de navegador para {ip}...")
    
    result = {
        "method": "browser_emulation",
        "ip": ip,
        "timestamp": datetime.datetime.now().isoformat(),
        "success": False,
        "reboot_time": 0,
        "message": ""
    }
    
    try:
        # Verificar si el script existe
        script_path = "/opt/network_monitor/app/scripts/browser_reboot.py"
        if not os.path.exists(script_path):
            result["message"] = "Script de emulación de navegador no encontrado"
            logger.warning(result["message"])
            return result
        
        # Ejecutar el script
        cmd = f"python {script_path} {ip} --username '{username}' --password '{password}'"
        process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        result["message"] = process.stdout.strip() or process.stderr.strip()
        
        if process.returncode == 0:
            # Esperar a que el dispositivo se reinicie
            reboot_success, reboot_time = wait_for_reboot(ip)
            result["success"] = reboot_success
            result["reboot_time"] = reboot_time
            
            if reboot_success:
                logger.info(f"Emulación de navegador exitosa para {ip} en {reboot_time} segundos")
            else:
                logger.warning(f"Emulación de navegador reportada como exitosa, pero no se detectó reinicio real para {ip}")
        else:
            logger.warning(f"Emulación de navegador fallida para {ip}: {result['message']}")
    except Exception as e:
        logger.error(f"Error en test_browser_emulation para {ip}: {str(e)}")
        result["message"] = f"Error: {str(e)}"
    
    return result

def test_packet_reset(ip: str) -> Dict[str, Any]:
    """Probar reinicio mediante packet crafting"""
    logger.info(f"Probando packet crafting para {ip}...")
    
    result = {
        "method": "packet_reset",
        "ip": ip,
        "timestamp": datetime.datetime.now().isoformat(),
        "success": False,
        "reboot_time": 0,
        "message": ""
    }
    
    try:
        # Verificar si el script existe
        script_path = "/opt/network_monitor/app/scripts/tplink_packet_reset.py"
        if not os.path.exists(script_path):
            result["message"] = "Script de packet crafting no encontrado"
            logger.warning(result["message"])
            return result
        
        # Ejecutar el script
        cmd = f"sudo python {script_path} {ip}"
        process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        result["message"] = process.stdout.strip() or process.stderr.strip()
        
        if process.returncode == 0:
            # Esperar a que el dispositivo se reinicie
            reboot_success, reboot_time = wait_for_reboot(ip)
            result["success"] = reboot_success
            result["reboot_time"] = reboot_time
            
            if reboot_success:
                logger.info(f"Packet crafting exitoso para {ip} en {reboot_time} segundos")
            else:
                logger.warning(f"Packet crafting reportado como exitoso, pero no se detectó reinicio real para {ip}")
        else:
            logger.warning(f"Packet crafting fallido para {ip}: {result['message']}")
    except Exception as e:
        logger.error(f"Error en test_packet_reset para {ip}: {str(e)}")
        result["message"] = f"Error: {str(e)}"
    
    return result

def run_tests(ip: str, username: str, password: str, brand: str, methods: List[str]) -> List[Dict[str, Any]]:
    """Ejecutar pruebas seleccionadas"""
    results = []
    
    # Verificar que el dispositivo está online
    if not ping_device(ip):
        logger.error(f"El dispositivo {ip} no está online. No se pueden ejecutar pruebas.")
        return results
    
    # Ejecutar pruebas seleccionadas
    for method in methods:
        # Esperar un tiempo entre pruebas
        time.sleep(5)
        
        # Verificar que el dispositivo está online antes de cada prueba
        if not ping_device(ip):
            logger.warning(f"El dispositivo {ip} no está online. Esperando recuperación...")
            time.sleep(60)  # Esperar un minuto
            if not ping_device(ip):
                logger.error(f"El dispositivo {ip} sigue offline. Saltando prueba {method}.")
                continue
        
        if method == "http":
            results.append(test_http_method(ip, username, password, brand))
        elif method == "advanced":
            results.append(test_advanced_recovery(ip, username, password, brand))
        elif method == "browser":
            results.append(test_browser_emulation(ip, username, password))
        elif method == "packet":
            results.append(test_packet_reset(ip))
    
    return results

def save_results(results: List[Dict[str, Any]], filename: str) -> None:
    """Guardar resultados en archivo JSON"""
    try:
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        logger.info(f"Resultados guardados en {filename}")
    except Exception as e:
        logger.error(f"Error guardando resultados: {str(e)}")

def main():
    parser = argparse.ArgumentParser(description="Probar métodos de reinicio en routers reales")
    parser.add_argument("ip", help="Dirección IP del router")
    parser.add_argument("--username", default="admin", help="Nombre de usuario")
    parser.add_argument("--password", default="Usbing08*", help="Contraseña")
    parser.add_argument("--brand", default="auto", help="Marca del router (tplink, netgear, auto)")
    parser.add_argument("--methods", default="http,advanced,browser,packet", help="Métodos a probar (separados por comas)")
    
    args = parser.parse_args()
    
    # Convertir métodos a lista
    methods = args.methods.split(',')
    
    # Ejecutar pruebas
    logger.info(f"Iniciando pruebas para {args.ip} (marca: {args.brand})")
    results = run_tests(args.ip, args.username, args.password, args.brand, methods)
    
    # Guardar resultados
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"/opt/network_monitor/test_results/reboot_test_{args.ip.replace('.', '_')}_{timestamp}.json"
    save_results(results, filename)
    
    # Mostrar resumen
    print("\n=== RESUMEN DE PRUEBAS ===")
    for result in results:
        status = "✅ ÉXITO" if result["success"] else "❌ FALLO"
        print(f"{result['method']}: {status} - Tiempo: {result['reboot_time']} segundos - {result['message']}")

if __name__ == "__main__":
    main()
