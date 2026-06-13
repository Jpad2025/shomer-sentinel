from app.backend.router_http_manager import RouterHTTPManager
import sys

def main():
    ip = input("Ingresa la IP del router a reiniciar: ")
    username = input("Ingresa el usuario: ")
    password = input("Ingresa la contraseña: ")
    brand = input("Ingresa la marca (tplink/netgear/auto): ")
    
    print(f"Intentando reiniciar {ip}...")
    manager = RouterHTTPManager(timeout=10, authorization_level=2)
    success, message = manager.reboot_device(ip, username, password, brand)
    
    if success:
        print(f"¡Éxito! {message}")
    else:
        print(f"Error: {message}")

if __name__ == "__main__":
    main()
