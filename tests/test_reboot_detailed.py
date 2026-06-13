#!/usr/bin/env python3
import sys
import logging
import time
from app.backend.router_http_manager import RouterHTTPManager

# Configurar logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("test_reboot")

def main():
    print("=== TEST DE REINICIO DE ROUTER ===")
    print("Este script probará diferentes métodos para reiniciar un router.")
    
    ip = input("Ingresa la IP del router a reiniciar: ")
    username = input("Ingresa el usuario: ")
    password = input("Ingresa la contraseña: ")
    brand = input("Ingresa la marca (tplink/netgear/auto): ")
    
    print(f"\nIniciando prueba para {ip} (marca: {brand})...")
    manager = RouterHTTPManager(timeout=10, authorization_level=2)
    
    # Probar método específico primero
    if brand.lower() == "tplink":
        print("\n1. Probando método específico para TP-Link...")
        success, message = manager.reboot_tplink_archer_c54(ip, password)
        print(f"Resultado: {'✅ Éxito' if success else '❌ Error'} - {message}")
    elif brand.lower() == "netgear":
        print("\n1. Probando método específico para Netgear...")
        success, message = manager.reboot_netgear_ac1000(ip, username, password)
        print(f"Resultado: {'✅ Éxito' if success else '❌ Error'} - {message}")
    
    # Probar método general
    print("\n2. Probando método general de reinicio...")
    success, message = manager.reboot_device(ip, username, password, brand)
    print(f"Resultado: {'✅ Éxito' if success else '❌ Error'} - {message}")
    
    # Probar métodos avanzados directamente
    print("\n3. Probando método de sobrecarga TCP...")
    success, message = manager._try_tcp_connection_flood(ip)
    print(f"Resultado: {'✅ Éxito' if success else '❌ Error'} - {message}")
    
    print("\n4. Probando método de sobrecarga HTTP...")
    success, message = manager._try_http_flood(ip)
    print(f"Resultado: {'✅ Éxito' if success else '❌ Error'} - {message}")
    
    print("\nPrueba completada.")

if __name__ == "__main__":
    main()
