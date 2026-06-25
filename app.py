"""
app.py
ChessLearnerBot — MVP online con Streamlit + Supabase + Stockfish.

Ejecutar con:  streamlit run app.py
"""

import random

import chess
import chess.pgn
import chess.svg
import streamlit as st

import auth
import db
import bot_logic
from chess_engine import MotorAjedrez

st.set_page_config(page_title="ChessLearnerBot", page_icon="♟️", layout="centered")


# ---------------------------------------------------------------------------
# Utilidades de sesión
# ---------------------------------------------------------------------------

def obtener_motor() -> MotorAjedrez:
    """Una sola instancia de Stockfish por sesión de navegador."""
    if "motor" not in st.session_state:
        try:
            st.session_state["motor"] = MotorAjedrez()
        except FileNotFoundError as e:
            st.error(str(e))
            st.stop()
    return st.session_state["motor"]


def iniciar_partida_nueva(color_usuario: str) -> None:
    st.session_state["tablero"] = chess.Board()
    st.session_state["color_usuario"] = color_usuario
    st.session_state["historial_san"] = []  # para reconstruir el PGN al terminar
    st.session_state["partida_terminada"] = False
    st.session_state["ultima_leccion"] = None


def color_usuario_es_blancas() -> bool:
    return st.session_state["color_usuario"] == "blancas"


def turno_del_usuario(tablero: chess.Board) -> bool:
    return (tablero.turn == chess.WHITE) == color_usuario_es_blancas()


def construir_pgn(tablero: chess.Board) -> str:
    juego = chess.pgn.Game()
    juego.headers["Event"] = "ChessLearnerBot"
    nodo = juego
    tablero_replay = chess.Board()
    for san in st.session_state["historial_san"]:
        jugada = tablero_replay.parse_san(san)
        nodo = nodo.add_variation(jugada)
        tablero_replay.push(jugada)
    juego.headers["Result"] = tablero.result()
    return str(juego)


def jugar_movimiento_usuario(jugada: chess.Move) -> None:
    tablero = st.session_state["tablero"]
    san = tablero.san(jugada)
    tablero.push(jugada)
    st.session_state["historial_san"].append(san)


def jugar_movimiento_bot(usuario: dict) -> None:
    motor = obtener_motor()
    tablero = st.session_state["tablero"]
    jugada = motor.jugada_bot(tablero, nivel=usuario["nivel_bot"])
    san = tablero.san(jugada)
    tablero.push(jugada)
    st.session_state["historial_san"].append(san)


def finalizar_partida(usuario: dict) -> None:
    """Se llama una sola vez cuando termina la partida: guarda, analiza y actualiza estado."""
    tablero = st.session_state["tablero"]
    resultado = tablero.result()  # '1-0', '0-1', '1/2-1/2', o '*'
    if resultado == "*":
        resultado = "1/2-1/2"  # fallback defensivo, no debería pasar si game_over() es True

    pgn_text = construir_pgn(tablero)
    color_usuario = st.session_state["color_usuario"]

    partida_id = db.guardar_partida(
        usuario_id=usuario["id"],
        pgn=pgn_text,
        resultado=resultado,
        color_usuario=color_usuario,
        modo_bot=usuario["modo_bot"],
        nivel_bot=usuario["nivel_bot"],
    )

    motor = obtener_motor()
    prefs = db.obtener_preferencias(usuario["id"])
    tiempo_analisis = prefs.get("tiempo_analisis_seg", 0.3)

    movimientos_info, errores_usuario = bot_logic.analizar_partida(
        pgn_text, motor, color_usuario=color_usuario, tiempo_analisis=tiempo_analisis
    )
    db.guardar_movimientos(partida_id, movimientos_info)
    db.guardar_errores(usuario["id"], partida_id, errores_usuario)

    nuevo_estado = bot_logic.actualizar_rachas_y_modo(usuario, resultado, color_usuario)
    db.actualizar_estado_bot(
        usuario["id"],
        modo_bot=nuevo_estado["modo_bot"],
        nivel_bot=nuevo_estado["nivel_bot"],
        racha_victorias_usuario=nuevo_estado["racha_victorias_usuario"],
        racha_victorias_bot=nuevo_estado["racha_victorias_bot"],
    )

    leccion = None
    if nuevo_estado["generar_leccion"]:
        contenido = bot_logic.generar_contenido_leccion(errores_usuario)
        leccion = db.guardar_leccion(
            usuario["id"], partida_id, titulo="Lección: el bot ganó 5 veces seguidas", contenido=contenido
        )

    # Reflejamos el nuevo estado en la sesión sin tener que recargar de la DB.
    st.session_state["usuario"].update({
        "modo_bot": nuevo_estado["modo_bot"],
        "nivel_bot": nuevo_estado["nivel_bot"],
        "racha_victorias_usuario": nuevo_estado["racha_victorias_usuario"],
        "racha_victorias_bot": nuevo_estado["racha_victorias_bot"],
    })
    st.session_state["partida_terminada"] = True
    st.session_state["ultima_leccion"] = leccion


# ---------------------------------------------------------------------------
# Pantalla de login / registro
# ---------------------------------------------------------------------------

def pantalla_login() -> None:
    st.title("♟️ ChessLearnerBot")
    st.caption("Tu progreso se guarda en la nube: podés seguir jugando desde el celu, la notebook o la PC.")

    tab_login, tab_registro = st.tabs(["Iniciar sesión", "Crear cuenta"])

    with tab_login:
        with st.form("form_login"):
            username = st.text_input("Usuario", key="login_user")
            password = st.text_input("Contraseña", type="password", key="login_pass")
            enviado = st.form_submit_button("Entrar")
        if enviado:
            usuario, error = auth.iniciar_sesion(username, password)
            if error:
                st.error(error)
            else:
                st.session_state["usuario"] = usuario
                st.rerun()

    with tab_registro:
        with st.form("form_registro"):
            username = st.text_input("Elegí un usuario", key="reg_user")
            password = st.text_input("Elegí una contraseña", type="password", key="reg_pass")
            enviado = st.form_submit_button("Crear cuenta")
        if enviado:
            usuario, error = auth.registrar_usuario(username, password)
            if error:
                st.error(error)
            else:
                st.success("Cuenta creada. Ya podés iniciar sesión desde la otra pestaña.")


# ---------------------------------------------------------------------------
# Sidebar: estado del bot, lecciones, historial
# ---------------------------------------------------------------------------

def panel_lateral(usuario: dict) -> None:
    st.sidebar.title(f"Hola, {usuario['username']} 👋")

    modo_legible = "🧠 Aprendizaje" if usuario["modo_bot"] == "learning" else "🎓 Entrenador (coaching)"
    st.sidebar.metric("Modo del bot", modo_legible)
    st.sidebar.metric("Nivel del bot", usuario["nivel_bot"])
    col1, col2 = st.sidebar.columns(2)
    col1.metric("Tu racha", usuario["racha_victorias_usuario"])
    col2.metric("Racha del bot", usuario["racha_victorias_bot"])

    if usuario["modo_bot"] == "coaching":
        st.sidebar.info(
            "El bot está en modo entrenador: el nivel queda congelado hasta que "
            "ganes 3 partidas seguidas."
        )

    with st.sidebar.expander("📚 Lecciones"):
        lecciones = db.obtener_lecciones(usuario["id"])
        if not lecciones:
            st.write("Todavía no se generó ninguna lección.")
        for lec in lecciones:
            st.markdown(f"**{lec['titulo']}**")
            st.markdown(lec["contenido"])
            st.divider()

    with st.sidebar.expander("📜 Historial de partidas"):
        historial = db.obtener_historial_partidas(usuario["id"])
        if not historial:
            st.write("Todavía no jugaste ninguna partida.")
        for p in historial:
            st.write(f"{p['creada_en'][:10]} · {p['color_usuario']} · {p['resultado']} · nivel {p['nivel_bot']}")

    if st.sidebar.button("Cerrar sesión"):
        for clave in ["usuario", "tablero", "historial_san", "color_usuario", "partida_terminada", "ultima_leccion"]:
            st.session_state.pop(clave, None)
        st.rerun()


# ---------------------------------------------------------------------------
# Pantalla de juego
# ---------------------------------------------------------------------------

def elegir_color_y_empezar(usuario: dict) -> None:
    st.subheader("Nueva partida")
    prefs = db.obtener_preferencias(usuario["id"])
    opciones = {"Blancas": "blancas", "Negras": "negras", "Aleatorio": "aleatorio"}
    default_idx = list(opciones.values()).index(prefs.get("color_preferido", "aleatorio"))
    eleccion = st.radio("¿Con qué color querés jugar?", list(opciones.keys()), index=default_idx, horizontal=True)

    if st.button("Empezar partida", type="primary"):
        color_elegido = opciones[eleccion]
        if color_elegido == "aleatorio":
            color_elegido = random.choice(["blancas", "negras"])
        db.guardar_preferencias(usuario["id"], opciones[eleccion], prefs.get("tiempo_analisis_seg", 0.3))
        iniciar_partida_nueva(color_elegido)
        st.rerun()


def mostrar_tablero(tablero: chess.Board) -> None:
    orientacion_blancas = color_usuario_es_blancas()
    svg = chess.svg.board(tablero, size=400, orientation=chess.WHITE if orientacion_blancas else chess.BLACK)
    st.markdown(f'<div style="display:flex;justify-content:center">{svg}</div>', unsafe_allow_html=True)


def panel_de_juego(usuario: dict) -> None:
    tablero: chess.Board = st.session_state["tablero"]

    mostrar_tablero(tablero)

    if tablero.is_game_over():
        if not st.session_state.get("partida_terminada"):
            finalizar_partida(usuario)
            st.rerun()
        mostrar_resultado_final(usuario)
        return

    if turno_del_usuario(tablero):
        st.write("Es tu turno.")
        legales = list(tablero.legal_moves)
        opciones_san = {tablero.san(m): m for m in legales}
        san_elegido = st.selectbox("Elegí tu jugada", sorted(opciones_san.keys()))
        if st.button("Jugar movimiento", type="primary"):
            jugar_movimiento_usuario(opciones_san[san_elegido])
            st.rerun()
    else:
        st.write("Turno del bot... 🤖")
        jugar_movimiento_bot(usuario)
        st.rerun()


def mostrar_resultado_final(usuario: dict) -> None:
    tablero = st.session_state["tablero"]
    resultado = tablero.result()
    color_usuario = st.session_state["color_usuario"]

    gano_usuario = (resultado == "1-0" and color_usuario == "blancas") or (
        resultado == "0-1" and color_usuario == "negras"
    )
    gano_bot = (resultado == "1-0" and color_usuario == "negras") or (
        resultado == "0-1" and color_usuario == "blancas"
    )

    if resultado == "1/2-1/2":
        st.info("Partida terminada en tablas.")
    elif gano_usuario:
        st.success("¡Ganaste la partida! 🎉")
    elif gano_bot:
        st.warning("Ganó el bot esta vez.")

    leccion = st.session_state.get("ultima_leccion")
    if leccion:
        st.subheader("🎓 Nueva lección desbloqueada")
        st.markdown(leccion["contenido"])

    if st.button("Jugar otra partida"):
        for clave in ["tablero", "historial_san", "color_usuario", "partida_terminada", "ultima_leccion"]:
            st.session_state.pop(clave, None)
        st.rerun()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if "usuario" not in st.session_state:
        pantalla_login()
        return

    usuario = st.session_state["usuario"]
    panel_lateral(usuario)

    st.title("♟️ ChessLearnerBot")

    if "tablero" not in st.session_state:
        elegir_color_y_empezar(usuario)
    else:
        panel_de_juego(usuario)


if __name__ == "__main__":
    main()
