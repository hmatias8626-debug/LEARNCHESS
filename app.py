"""
app.py
ChessLearnerBot — MVP online con Streamlit + Supabase + Stockfish.

Ejecutar con:  streamlit run app.py
"""

import base64
import io
import random

import cairosvg
import chess
import chess.pgn
import chess.svg
import streamlit as st
from PIL import Image

import auth
import db
import bot_logic
from chess_engine import MotorAjedrez, elo_aproximado

st.set_page_config(page_title="ChessLearnerBot", page_icon="♟️", layout="centered")

SQ = 50  # píxeles por casilla (tablero = SQ*8 x SQ*8)

# ---------------------------------------------------------------------------
# Componente canvas — highlight instantáneo sin round-trip al servidor
# Archivo: static/chess_board.html  (servido por enableStaticServing)
# ---------------------------------------------------------------------------

@st.cache_resource
def _get_chess_component():
    # HTML autónomo en GitHub, servido por jsDelivr (sin dependencias externas)
    url = "https://cdn.jsdelivr.net/gh/hmatias8626-debug/LEARNCHESS@main/chess_component/index.html"
    return st.components.v1.declare_component("chess_click", url=url)


# ---------------------------------------------------------------------------
# Utilidades de tablero
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _render_png(fen: str, flip: bool) -> bytes:
    """PNG cacheado por posición."""
    orientation = chess.BLACK if flip else chess.WHITE
    svg = chess.svg.board(chess.Board(fen), size=SQ * 8, orientation=orientation, coordinates=False)
    return cairosvg.svg2png(bytestring=svg.encode())


def board_to_pil(tablero: chess.Board, flip: bool) -> Image.Image:
    return Image.open(io.BytesIO(_render_png(tablero.fen(), flip)))


def board_to_b64(tablero: chess.Board, flip: bool) -> str:
    return base64.b64encode(_render_png(tablero.fen(), flip)).decode()


def click_to_square(x: int, y: int, flip: bool) -> chess.Square:
    file_idx = min(7, max(0, x // SQ))
    rank_idx = min(7, max(0, y // SQ))
    if flip:
        return chess.square(7 - file_idx, rank_idx)
    return chess.square(file_idx, 7 - rank_idx)


# ---------------------------------------------------------------------------
# Utilidades de sesión
# ---------------------------------------------------------------------------

def obtener_motor() -> MotorAjedrez:
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
    st.session_state["historial_san"] = []
    st.session_state["partida_terminada"] = False
    st.session_state["ultima_leccion"] = None
    st.session_state.pop("selected_square", None)
    st.session_state.pop("last_click_id", None)


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
    tablero = st.session_state["tablero"]
    resultado = tablero.result()
    if resultado == "*":
        resultado = "1/2-1/2"

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

    movimientos_info, errores_usuario, errores_bot = bot_logic.analizar_partida(
        pgn_text, motor, color_usuario=color_usuario, tiempo_analisis=tiempo_analisis
    )
    db.guardar_movimientos(partida_id, movimientos_info)
    db.guardar_errores(usuario["id"], partida_id, errores_usuario)

    nuevo_estado = bot_logic.actualizar_rachas_y_modo(usuario, resultado, color_usuario)
    db.actualizar_estado_bot(
        usuario["id"],
        modo_bot="learning",
        nivel_bot=nuevo_estado["nivel_bot"],
        racha_victorias_usuario=nuevo_estado["racha_victorias_usuario"],
        racha_victorias_bot=nuevo_estado["racha_victorias_bot"],
    )

    leccion = None
    if nuevo_estado["generar_leccion_usuario"]:
        contenido = bot_logic.generar_contenido_leccion_usuario(errores_usuario)
        leccion = db.guardar_leccion(
            usuario["id"], partida_id,
            titulo="El bot te enseña: corregí tus errores",
            contenido=contenido,
        )
    if nuevo_estado["generar_leccion_bot"]:
        contenido = bot_logic.generar_contenido_leccion_bot(errores_bot, nuevo_estado["nivel_bot"])
        leccion = db.guardar_leccion(
            usuario["id"], partida_id,
            titulo=f"El bot aprendio y subio al nivel {nuevo_estado['nivel_bot']}",
            contenido=contenido,
        )

    st.session_state["usuario"].update({
        "modo_bot": "learning",
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

    st.sidebar.metric("Nivel del bot", f"{usuario['nivel_bot']}  (~{elo_aproximado(usuario['nivel_bot'])} ELO)")

    racha_u = usuario["racha_victorias_usuario"]
    racha_b = usuario["racha_victorias_bot"]
    col1, col2 = st.sidebar.columns(2)
    col1.metric("Tu racha", f"{racha_u}/5", help="Al ganar 5 seguidas, Stockfish entrena al bot y sube de nivel")
    col2.metric("Racha del bot", f"{racha_b}/3", help="Si el bot gana 3 seguidas, te muestra tus errores")

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
        for clave in ["usuario", "tablero", "historial_san", "color_usuario",
                      "partida_terminada", "ultima_leccion", "selected_square", "last_click_id"]:
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


def panel_de_juego(usuario: dict) -> None:
    tablero: chess.Board = st.session_state["tablero"]
    flip = not color_usuario_es_blancas()

    if tablero.is_game_over():
        st.image(board_to_pil(tablero, flip))
        if not st.session_state.get("partida_terminada"):
            finalizar_partida(usuario)
            st.rerun()
        mostrar_resultado_final(usuario)
        return

    # sel_col/sel_row le dicen al componente qué casilla resaltar según el servidor
    selected = st.session_state.get("selected_square")
    if selected is not None:
        _f = chess.square_file(selected)
        _r = chess.square_rank(selected)
        sel_col = (7 - _f) if flip else _f
        sel_row = _r if flip else (7 - _r)
    else:
        sel_col, sel_row = -1, -1

    coords = _get_chess_component()(
        img_b64=board_to_b64(tablero, flip),
        fen=tablero.fen(),
        sq=SQ,
        sel_col=sel_col,
        sel_row=sel_row,
        key="chess_click",
        default=None,
    )

    if turno_del_usuario(tablero):
        st.caption("Es tu turno — hacé clic en una pieza y luego en el destino.")

        if coords:
            click_id = (coords["x"], coords["y"])
            if click_id != st.session_state.get("last_click_id"):
                st.session_state["last_click_id"] = click_id
                sq = click_to_square(coords["x"], coords["y"], flip)

                if selected is None:
                    piece = tablero.piece_at(sq)
                    if piece and piece.color == tablero.turn:
                        st.session_state["selected_square"] = sq
                        # Sin st.rerun(): el tablero no cambió, el script termina solo
                else:
                    st.session_state.pop("selected_square", None)
                    if sq != selected:
                        jugada = chess.Move(selected, sq)
                        if (tablero.piece_type_at(selected) == chess.PAWN
                                and chess.square_rank(sq) in (0, 7)):
                            jugada = chess.Move(selected, sq, promotion=chess.QUEEN)
                        if jugada in tablero.legal_moves:
                            jugar_movimiento_usuario(jugada)
                            # Respuesta del bot en el mismo ciclo: un solo rerun
                            if not tablero.is_game_over() and not turno_del_usuario(tablero):
                                jugar_movimiento_bot(usuario)
                            st.rerun()
                        else:
                            piece = tablero.piece_at(sq)
                            if piece and piece.color == tablero.turn:
                                st.session_state["selected_square"] = sq
                            # Sin st.rerun(): el tablero no cambió
    else:
        st.caption("Turno del bot...")
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
        for clave in ["tablero", "historial_san", "color_usuario", "partida_terminada",
                      "ultima_leccion", "selected_square", "last_click_id"]:
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
