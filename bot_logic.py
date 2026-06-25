"""
bot_logic.py
Lógica de aprendizaje mutuo:
- El bot aprende cuando el usuario le gana 5 veces seguidas
  (Stockfish analiza los errores del bot y sube su nivel)
- El usuario recibe una lección cuando el bot le gana 3 veces seguidas
  (el bot le muestra los errores del usuario)
"""

import io

import chess
import chess.pgn

from chess_engine import MotorAjedrez

UMBRAL_ERROR_CP = 150
RACHA_USUARIO_PARA_MEJORAR_BOT = 5   # usuario gana 5 seguidas → bot aprende y sube nivel
RACHA_BOT_PARA_LECCION_USUARIO  = 3  # bot gana 3 seguidas → usuario recibe lección


# ---------------------------------------------------------------------------
# Análisis post-partida
# ---------------------------------------------------------------------------

def analizar_partida(pgn_text: str, motor: MotorAjedrez, color_usuario: str,
                     tiempo_analisis: float = 0.3) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Recorre la partida y evalúa cada posición con Stockfish.
    Devuelve:
      - movimientos_info : para la tabla `movimientos`
      - errores_usuario  : errores cometidos por el usuario
      - errores_bot      : errores cometidos por el bot (usados cuando el bot "aprende")
    """
    juego = chess.pgn.read_game(io.StringIO(pgn_text))
    tablero = juego.board()
    color_bot = "negras" if color_usuario == "blancas" else "blancas"

    movimientos_info: list[dict] = []
    errores_usuario:  list[dict] = []
    errores_bot:      list[dict] = []

    eval_anterior = motor.evaluar_posicion(tablero, tiempo_analisis) or 0
    numero_jugada = 1

    for jugada in juego.mainline_moves():
        color_que_mueve = "blancas" if tablero.turn == chess.WHITE else "negras"
        san = tablero.san(jugada)
        uci = jugada.uci()
        fen_antes = tablero.fen()

        mejor_jugada_san = None
        mejor = motor.mejor_jugada(tablero, tiempo_analisis)
        if mejor is not None:
            mejor_jugada_san = tablero.san(mejor)

        tablero.push(jugada)
        eval_actual = motor.evaluar_posicion(tablero, tiempo_analisis)
        if eval_actual is None:
            eval_actual = eval_anterior

        if color_que_mueve == "blancas":
            perdida_cp = eval_anterior - eval_actual
        else:
            perdida_cp = eval_actual - eval_anterior

        es_error = perdida_cp >= UMBRAL_ERROR_CP

        movimientos_info.append({
            "numero_jugada": numero_jugada,
            "color": color_que_mueve,
            "san": san,
            "uci": uci,
            "eval_centipawns": eval_actual,
            "es_error": bool(es_error),
        })

        if es_error:
            entrada = {
                "tipo_error": "error_tactico" if perdida_cp < 300 else "error_grave",
                "fen": fen_antes,
                "san_jugado": san,
                "san_mejor": mejor_jugada_san,
                "perdida_centipawns": int(perdida_cp),
            }
            if color_que_mueve == color_usuario:
                errores_usuario.append(entrada)
            elif color_que_mueve == color_bot:
                errores_bot.append(entrada)

        eval_anterior = eval_actual
        if color_que_mueve == "negras":
            numero_jugada += 1

    return movimientos_info, errores_usuario, errores_bot


# ---------------------------------------------------------------------------
# Rachas y nivel
# ---------------------------------------------------------------------------

def actualizar_rachas_y_modo(estado_usuario: dict, resultado: str, color_usuario: str) -> dict:
    """
    Reglas:
      - Usuario gana 5 seguidas → bot sube nivel (aprendió de sus errores con Stockfish).
      - Bot gana 3 seguidas     → se genera lección para el usuario.
    """
    nivel       = estado_usuario["nivel_bot"]
    racha_usuario = estado_usuario["racha_victorias_usuario"]
    racha_bot     = estado_usuario["racha_victorias_bot"]

    gano_usuario = (resultado == "1-0" and color_usuario == "blancas") or (
                   resultado == "0-1" and color_usuario == "negras")
    gano_bot     = (resultado == "1-0" and color_usuario == "negras") or (
                   resultado == "0-1" and color_usuario == "blancas")

    if gano_usuario:
        racha_usuario += 1
        racha_bot = 0
    elif gano_bot:
        racha_bot += 1
        racha_usuario = 0
    else:
        racha_usuario = 0
        racha_bot = 0

    generar_leccion_usuario = False
    generar_leccion_bot     = False

    if racha_bot >= RACHA_BOT_PARA_LECCION_USUARIO:
        generar_leccion_usuario = True
        racha_bot = 0

    if racha_usuario >= RACHA_USUARIO_PARA_MEJORAR_BOT:
        nivel = min(20, nivel + 1)
        generar_leccion_bot = True
        racha_usuario = 0

    return {
        "nivel_bot": nivel,
        "racha_victorias_usuario": racha_usuario,
        "racha_victorias_bot": racha_bot,
        "generar_leccion_usuario": generar_leccion_usuario,
        "generar_leccion_bot": generar_leccion_bot,
    }


# ---------------------------------------------------------------------------
# Generación de lecciones
# ---------------------------------------------------------------------------

def generar_contenido_leccion_usuario(errores: list[dict]) -> str:
    """Lección para el usuario tras 3 victorias consecutivas del bot."""
    if not errores:
        return (
            "El bot ganó 3 veces seguidas pero no encontró errores tácticos claros. "
            "Probá mejorar tus aperturas y controlar el centro desde el principio."
        )

    top = sorted(errores, key=lambda e: e["perdida_centipawns"], reverse=True)[:3]
    lineas = ["El bot ganó 3 partidas seguidas. Estos fueron tus errores más costosos:", ""]
    for i, err in enumerate(top, 1):
        mejor = err.get("san_mejor") or "(sin sugerencia)"
        lineas.append(
            f"{i}. Jugaste **{err['san_jugado']}** (−{err['perdida_centipawns']} cp). "
            f"La mejor jugada era **{mejor}**.\n"
            f"   Posición: `{err['fen']}`"
        )
    lineas += ["", "Consejo: antes de mover revisá si tu pieza queda atacada y si hay capturas disponibles para el rival."]
    return "\n".join(lineas)


def generar_contenido_leccion_bot(errores_bot: list[dict], nivel_nuevo: int) -> str:
    """Mensaje para el usuario mostrando qué aprendió el bot tras 5 derrotas consecutivas."""
    lineas = [
        f"¡Ganaste 5 partidas seguidas! Stockfish analizó los errores del bot y lo entrenó. "
        f"Ahora juega en **nivel {nivel_nuevo}**.",
        ""
    ]
    if not errores_bot:
        lineas.append("El bot no cometió errores tácticos claros, pero igual sube de nivel por tu racha.")
        return "\n".join(lineas)

    top = sorted(errores_bot, key=lambda e: e["perdida_centipawns"], reverse=True)[:3]
    lineas.append("Estos fueron los peores errores del bot que Stockfish le señaló:")
    lineas.append("")
    for i, err in enumerate(top, 1):
        mejor = err.get("san_mejor") or "(sin sugerencia)"
        lineas.append(
            f"{i}. El bot jugó **{err['san_jugado']}** (−{err['perdida_centipawns']} cp). "
            f"Debería haber jugado **{mejor}**."
        )
    lineas += ["", "El bot intentará no repetir estos errores."]
    return "\n".join(lineas)
