"""
auth.py
Login simple basado en usuario/contraseña guardados en Supabase.
No usa OAuth ni servicios externos: es un hash con sal (PBKDF2-SHA256),
suficiente para un MVP personal, no para una app con muchos usuarios
ni datos sensibles.
"""

import hashlib
import secrets as secrets_lib
from typing import Optional

import db


def crear_hash(password: str) -> str:
    """Genera 'sal$hash' para guardar en la columna password_hash."""
    sal = secrets_lib.token_hex(16)
    hash_resultado = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), sal.encode("utf-8"), 100_000
    ).hex()
    return f"{sal}${hash_resultado}"


def verificar_password(password: str, hash_guardado: str) -> bool:
    try:
        sal, hash_esperado = hash_guardado.split("$", 1)
    except (ValueError, AttributeError):
        return False
    hash_calculado = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), sal.encode("utf-8"), 100_000
    ).hex()
    return hash_calculado == hash_esperado


def registrar_usuario(username: str, password: str) -> tuple[Optional[dict], Optional[str]]:
    username = username.strip()
    if not username or not password:
        return None, "Usuario y contraseña no pueden estar vacíos."
    if len(password) < 4:
        return None, "La contraseña debe tener al menos 4 caracteres."

    existente = db.obtener_usuario_por_username(username)
    if existente:
        return None, "Ese nombre de usuario ya existe."

    password_hash = crear_hash(password)
    usuario = db.crear_usuario(username, password_hash)
    return usuario, None


def iniciar_sesion(username: str, password: str) -> tuple[Optional[dict], Optional[str]]:
    username = username.strip()
    usuario = db.obtener_usuario_por_username(username)
    if not usuario:
        return None, "Usuario no encontrado."
    if not verificar_password(password, usuario["password_hash"]):
        return None, "Contraseña incorrecta."
    return usuario, None
