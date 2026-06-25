"""
db.py
Capa de acceso a datos: toda la comunicación con Supabase vive acá.
El resto de la app (app.py, auth.py, bot_logic.py) no debería importar
el cliente de Supabase directamente, sino usar estas funciones.
"""

import os
from typing import Optional

import streamlit as st
from supabase import create_client, Client


# ---------------------------------------------------------------------------
# Conexión
# ---------------------------------------------------------------------------

def get_supabase_client() -> Client:
    """
    Crea (una sola vez por sesión) el cliente de Supabase.
    Busca las credenciales primero en st.secrets y, si no están,
    en variables de entorno (útil para correr local sin secrets.toml).
    """
    if "supabase_client" in st.session_state:
        return st.session_state["supabase_client"]

    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        raise RuntimeError(
            "Faltan las credenciales de Supabase. Definí SUPABASE_URL y "
            "SUPABASE_KEY en .streamlit/secrets.toml o como variables de entorno."
        )

    client = create_client(url, key)
    st.session_state["supabase_client"] = client
    return client


# ---------------------------------------------------------------------------
# Usuarios / estado del bot
# ---------------------------------------------------------------------------

def crear_usuario(username: str, password_hash: str) -> dict:
    sb = get_supabase_client()
    resp = sb.table("usuarios").insert({
        "username": username,
        "password_hash": password_hash,
    }).execute()
    usuario = resp.data[0]
    # Fila de preferencias por defecto para que siempre exista.
    sb.table("preferencias_bot").insert({"usuario_id": usuario["id"]}).execute()
    return usuario


def obtener_usuario_por_username(username: str) -> Optional[dict]:
    sb = get_supabase_client()
    resp = sb.table("usuarios").select("*").eq("username", username).execute()
    return resp.data[0] if resp.data else None


def actualizar_estado_bot(usuario_id: str, modo_bot: str, nivel_bot: int,
                           racha_victorias_usuario: int, racha_victorias_bot: int) -> None:
    sb = get_supabase_client()
    sb.table("usuarios").update({
        "modo_bot": modo_bot,
        "nivel_bot": nivel_bot,
        "racha_victorias_usuario": racha_victorias_usuario,
        "racha_victorias_bot": racha_victorias_bot,
    }).eq("id", usuario_id).execute()


# ---------------------------------------------------------------------------
# Preferencias
# ---------------------------------------------------------------------------

def obtener_preferencias(usuario_id: str) -> dict:
    sb = get_supabase_client()
    resp = sb.table("preferencias_bot").select("*").eq("usuario_id", usuario_id).execute()
    if resp.data:
        return resp.data[0]
    # Si por algún motivo no existía la fila, la creamos al vuelo.
    sb.table("preferencias_bot").insert({"usuario_id": usuario_id}).execute()
    return {"usuario_id": usuario_id, "color_preferido": "aleatorio", "tiempo_analisis_seg": 0.3}


def guardar_preferencias(usuario_id: str, color_preferido: str, tiempo_analisis_seg: float) -> None:
    sb = get_supabase_client()
    sb.table("preferencias_bot").update({
        "color_preferido": color_preferido,
        "tiempo_analisis_seg": tiempo_analisis_seg,
    }).eq("usuario_id", usuario_id).execute()


# ---------------------------------------------------------------------------
# Partidas / movimientos
# ---------------------------------------------------------------------------

def guardar_partida(usuario_id: str, pgn: str, resultado: str, color_usuario: str,
                     modo_bot: str, nivel_bot: int) -> str:
    sb = get_supabase_client()
    resp = sb.table("partidas").insert({
        "usuario_id": usuario_id,
        "pgn": pgn,
        "resultado": resultado,
        "color_usuario": color_usuario,
        "modo_bot": modo_bot,
        "nivel_bot": nivel_bot,
    }).execute()
    return resp.data[0]["id"]


def guardar_movimientos(partida_id: str, movimientos: list[dict]) -> None:
    if not movimientos:
        return
    sb = get_supabase_client()
    filas = [{**m, "partida_id": partida_id} for m in movimientos]
    sb.table("movimientos").insert(filas).execute()


def obtener_historial_partidas(usuario_id: str, limite: int = 20) -> list[dict]:
    sb = get_supabase_client()
    resp = (
        sb.table("partidas")
        .select("*")
        .eq("usuario_id", usuario_id)
        .order("creada_en", desc=True)
        .limit(limite)
        .execute()
    )
    return resp.data


# ---------------------------------------------------------------------------
# Errores frecuentes / lecciones
# ---------------------------------------------------------------------------

def guardar_errores(usuario_id: str, partida_id: str, errores: list[dict]) -> None:
    if not errores:
        return
    sb = get_supabase_client()
    filas = [{**e, "usuario_id": usuario_id, "partida_id": partida_id} for e in errores]
    sb.table("errores_frecuentes").insert(filas).execute()


def obtener_errores_recientes(usuario_id: str, limite: int = 50) -> list[dict]:
    sb = get_supabase_client()
    resp = (
        sb.table("errores_frecuentes")
        .select("*")
        .eq("usuario_id", usuario_id)
        .order("creado_en", desc=True)
        .limit(limite)
        .execute()
    )
    return resp.data


def guardar_leccion(usuario_id: str, partida_id: Optional[str], titulo: str, contenido: str) -> dict:
    sb = get_supabase_client()
    resp = sb.table("lecciones").insert({
        "usuario_id": usuario_id,
        "partida_id": partida_id,
        "titulo": titulo,
        "contenido": contenido,
    }).execute()
    return resp.data[0]


def obtener_lecciones(usuario_id: str, limite: int = 20) -> list[dict]:
    sb = get_supabase_client()
    resp = (
        sb.table("lecciones")
        .select("*")
        .eq("usuario_id", usuario_id)
        .order("creada_en", desc=True)
        .limit(limite)
        .execute()
    )
    return resp.data


def marcar_leccion_leida(leccion_id: int) -> None:
    sb = get_supabase_client()
    sb.table("lecciones").update({"leida": True}).eq("id", leccion_id).execute()
