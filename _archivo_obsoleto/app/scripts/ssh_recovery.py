#!/usr/bin/env python3
"""
Módulo de recuperación SSH REAL usando paramiko
Desarrollado por USB Ingeniería SAS
"""
import paramiko
import logging

logger = logging.getLogger("ssh_recovery")

def ssh_reboot(ip, username, password, port=22, timeout=10):
    """Reiniciar dispositivo por SSH"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
        
        logger.info(f"Conectando a {ip}:{port} como {username}")
        client.connect(
            hostname=ip,
            username=username,
            password=password,
            port=port,
            timeout=timeout,
            look_for_keys=False,
            allow_agent=False
        )
        
        logger.info(f"Ejecutando comando 'reboot' en {ip}")
        stdin, stdout, stderr = client.exec_command('reboot', timeout=5)
        client.close()
        
        logger.info(f"Comando reboot enviado exitosamente a {ip}")
        return True, f"Dispositivo {ip} reiniciado exitosamente"
        
    except paramiko.AuthenticationException:
        msg = f"Error de autenticación SSH en {ip}"
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"Error conectando a {ip}: {str(e)}"
        logger.error(msg)
        return False, msg

def test_ssh_connection(ip, username, password, port=22):
    """Probar conexión SSH"""
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
        client.connect(
            hostname=ip,
            username=username,
            password=password,
            port=port,
            timeout=10,
            look_for_keys=False,
            allow_agent=False
        )
        stdin, stdout, stderr = client.exec_command('uptime')
        output = stdout.read().decode('utf-8')
        client.close()
        return True, f"Conexión SSH exitosa. Uptime: {output.strip()}"
    except Exception as e:
        return False, f"Error: {str(e)}"
