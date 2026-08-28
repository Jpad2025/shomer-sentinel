"""
Gestor HTTP para reinicio de routers
Desarrollado por USB Ingeniería SAS
"""
import requests
import logging
import time
import re
from typing import Tuple, Dict, Any, List, Optional

# Configurar logging
logger = logging.getLogger(__name__)

class RouterHTTPManager:
    """Gestor de reinicio de routers mediante HTTP"""
    
    def __init__(self, timeout=10, authorization_level=1):
        """
        Inicializar gestor con timeout y nivel de autorización
        """
        self.timeout = timeout
        self.authorization_level = authorization_level
        self.session = requests.Session()
        self.session.verify = False
        
        # Deshabilitar advertencias SSL
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except:
            pass
    
    def detect_admin_port(self, ip, ports=[80, 2222, 8080, 8443]):
        """Detecta automáticamente el puerto de administración del router"""
        logger.info(f"Detectando puerto de administración para {ip}")
        for port in ports:
            try:
                url = f"http://{ip}:{port}/"
                response = self.session.get(url, timeout=2)
                if response.status_code == 200:
                    logger.info(f"Puerto de administración detectado: {port}")
                    return port
            except Exception as e:
                logger.debug(f"Puerto {port} no disponible: {str(e)}")
        logger.warning(f"No se pudo detectar puerto de administración para {ip}")
        return None
    
    def reboot_device(self, ip, username, password, brand="auto"):
        """
        Reinicia un dispositivo de red usando el método apropiado según la marca
        
        Args:
            ip: Dirección IP del dispositivo
            username: Nombre de usuario para autenticación
            password: Contraseña para autenticación
            brand: Marca del dispositivo (tplink, netgear, auto)
            
        Returns:
            Tuple[bool, str]: (éxito, mensaje)
        """
        brand = brand.lower() if brand else "auto"
        logger.info(f"Intentando reiniciar {ip} (marca: {brand})")
        
        # Caso especial para TP-Link Archer C54
        if brand in ["tplink", "tp-link", "auto"]:
            success, message = self.reboot_tplink_archer_c54(ip, password)
            if success:
                return True, message
            
            if brand != "auto":
                return False, message
        
        # Caso especial para Netgear
        if brand in ["netgear", "auto"]:
            success, message = self.reboot_netgear(ip, username, password)
            if success:
                return True, message
            
            if brand != "auto":
                return False, message
        
        # Método genérico como último recurso
        if brand == "auto":
            success, message = self.reboot_generic(ip, username, password)
            if success:
                return True, message
        
        return False, "No se pudo reiniciar el dispositivo con ningún método"
    
    def reboot_tplink_archer_c54(self, ip, password):
        """
        Reiniciar TP-Link Archer C54
        """
        try:
            # Detectar puerto de administración
            admin_port = self.detect_admin_port(ip) or 80
            logger.info(f"Usando puerto {admin_port} para {ip}")
            
            # Crear URL base con el puerto correcto
            base_url = f"http://{ip}:{admin_port}"
            login_url = f"{base_url}/cgi-bin/luci/;stok=/login?form=login"
            
            # Intentar login
            login_data = {"operation": "login", "password": password}
            
            logger.info(f"Enviando solicitud de login a {login_url}")
            response = self.session.post(login_url, json=login_data, timeout=self.timeout)
            
            if response.status_code != 200:
                return False, f"Error de autenticación: {response.status_code}"
            
            # Extraer token de la respuesta
            try:
                data = response.json()
                if not data.get("success"):
                    return False, f"Login fallido: {data.get('msg', 'credenciales incorrectas')}"
                
                stok = data.get("data", {}).get("stok")
                if not stok:
                    return False, "No se pudo obtener token de autenticación"
                
                logger.info(f"Login exitoso, token obtenido: {stok}")
                
                # Enviar comando de reinicio
                reboot_url = f"{base_url}/cgi-bin/luci/;stok={stok}/admin/system?form=reboot"
                reboot_data = {"operation": "reboot"}
                
                logger.info(f"Enviando comando de reinicio a {reboot_url}")
                response = self.session.post(reboot_url, json=reboot_data, timeout=self.timeout)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if data.get("success"):
                            logger.info(f"Reinicio exitoso para {ip}")
                            return True, "Reinicio exitoso"
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
            logger.info(f"Timeout en {ip} - posiblemente reiniciando")
            return True, "Reinicio iniciado (timeout esperado)"
        except Exception as e:
            logger.error(f"Error en método TP-Link {ip}: {str(e)}")
            return False, str(e)
    
    def reboot_netgear(self, ip, username, password):
        """
        Reiniciar router Netgear
        """
        try:
            # Detectar puerto de administración
            admin_port = self.detect_admin_port(ip) or 80
            
            # Crear URL base con el puerto correcto
            base_url = f"http://{ip}:{admin_port}"
            
            # Intentar login
            login_url = f"{base_url}/login.cgi"
            login_data = {
                "username": username,
                "password": password
            }
            
            response = self.session.post(login_url, data=login_data, timeout=self.timeout)
            
            if response.status_code != 200:
                return False, f"Error de autenticación: {response.status_code}"
            
            # Buscar token en la respuesta
            token_match = re.search(r'id="session_token" value="([^"]+)"', response.text)
            if not token_match:
                return False, "No se pudo obtener token de sesión"
            
            token = token_match.group(1)
            
            # Enviar comando de reinicio
            reboot_url = f"{base_url}/apply.cgi?/reboot.htm timestamp={int(time.time())}"
            reboot_data = {
                "submit_button": "reboot",
                "yes": "yes",
                "session_token": token
            }
            
            response = self.session.post(reboot_url, data=reboot_data, timeout=self.timeout)
            
            if response.status_code in [200, 302]:
                return True, "Reinicio exitoso"
            else:
                return False, f"Error al reiniciar: {response.status_code}"
        except requests.exceptions.Timeout:
            # El timeout puede indicar que el reinicio fue exitoso
            return True, "Reinicio iniciado (timeout esperado)"
        except Exception as e:
            logger.error(f"Error en método Netgear {ip}: {str(e)}")
            return False, str(e)
    
    def reboot_generic(self, ip, username, password):
        """
        Intenta reiniciar un router usando métodos genéricos
        """
        try:
            # Detectar puerto de administración
            admin_port = self.detect_admin_port(ip) or 80
            
            # Lista de URLs de reinicio comunes
            reboot_urls = [
                f"http://{ip}:{admin_port}/reboot.cgi",
                f"http://{ip}:{admin_port}/apply.cgi?submit_button=Reboot",
                f"http://{ip}:{admin_port}/admin/reboot",
                f"http://{ip}:{admin_port}/system_reboot.asp"
            ]
            
            # Probar cada URL
            for url in reboot_urls:
                try:
                    response = self.session.get(url, timeout=self.timeout)
                    if response.status_code in [200, 302]:
                        return True, f"Reinicio posiblemente exitoso con URL: {url}"
                except requests.exceptions.Timeout:
                    # Timeout puede indicar reinicio exitoso
                    return True, f"Reinicio posiblemente exitoso (timeout en {url})"
                except Exception as e:
                    logger.debug(f"Error con URL {url}: {str(e)}")
            
            return False, "Ninguna URL de reinicio funcionó"
        except Exception as e:
            logger.error(f"Error en método genérico {ip}: {str(e)}")
            return False, str(e)
