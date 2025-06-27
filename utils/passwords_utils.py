import os
import hashlib
import hmac
import base64

# Parámetros de configuración
SALT_LENGTH = 16  # bytes
ITERATIONS = 100_000  # número de iteraciones para PBKDF2


def hash_password(password: str) -> str:
    """
    Hashea la contraseña con PBKDF2-HMAC-SHA256 y un salt aleatorio.
    Devuelve una cadena codificada en base64 que contiene salt + hash.
    """
    # Generar un salt aleatorio
    salt = os.urandom(SALT_LENGTH)
    # Derivar la clave usando PBKDF2-HMAC-SHA256
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    # Concatenar salt + hash y codificar en base64
    hashed = base64.b64encode(salt + dk).decode('utf-8')
    return hashed


def verify_password(password: str, hashed: str) -> bool:
    """
    Verifica si la contraseña proporcionada coincide con el hash almacenado.
    """
    # Decodificar la cadena base64 para obtener salt + hash
    data = base64.b64decode(hashed.encode('utf-8'))
    salt = data[:SALT_LENGTH]
    dk_stored = data[SALT_LENGTH:]
    # Derivar la clave de la contraseña proporcionada usando el mismo salt
    dk_new = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, ITERATIONS)
    # Comparar de forma segura
    return hmac.compare_digest(dk_new, dk_stored)
