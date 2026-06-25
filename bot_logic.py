"""
bot_logic.py
"Cerebro" simple del bot, sin IA avanzada ni redes neuronales:
- analiza una partida jugada con Stockfish y detecta los errores del usuario
- actualiza rachas, modo (learning/coaching) y nivel del bot
- genera el contenido de una lección en base a los errores detectados
"""

import io

import chess
import chess.pgn

from chess_engine import MotorAjedrez

UMBRAL_ERROR_CP = 150       # pérdida de centipawns a partir de la cual consideramos "error"
RACHA_BOT_PARA_COACHING = 5  # 5 derrotas seguidas del usuario -> modo entrenador
RACHA_USUARIO_PARA_LEARNING = 3  # 3 victorias seguidas del usuario -> vuelve a aprendizaje + sube nivel


# ---------------------------------------------------------------------------
# Análisis post-partida
# ---------------------------------------------------------------------------

def analizar_partida(pgn_text: str, motor: MotorAjedrez, color_usuario: str,
                      tiempo_analisis: float = 0.3) -> tuple[list[dict], list[dict]]:
    """
    Recorre la partida jugada moviendo un tablero desde el inicio,
    evalúa cada posición con Stockfish y devuelve:
      - movimientos_info: lista para guardar en la tabla `movimientos`
      - errores_usuario: lista de errores del USUARIO (no del bot) para
        guardar en `errores_frecuentes`, con la mejor jugada alternativa.
    """
    juego = chess.pgn.read_game(io.StringIO(pgn_text))
    tablero = juego.board()

    movimientos_info: list[dict] = []
    errores_usuario: list[dict] = []

    eval_anterior = motor.evaluar_posicion(tablero, tiempo_analisis) or 0
    numero_jugada = 1

    for jugada in juego.mainline_moves():
        color_que_mueve = "blancas" if tablero.turn == chess.WHITE else "negras"
        san = tablero.san(jugada)
        uci = jugada.uci()
        fen_antes = tablero.fen()

        # Si la jugada fue del usuario, guardamos la mejor alternativa
        # ANTES de jugar, para poder mostrarla en la lección.
        mejor_jugada_san = None
        if color_que_mueve == color_usuario:
            mejor = motor.mejor_jugada(tablero, tiempo_analisis)
            if mejor is not None:
                mejor_jugada_san = tablero.san(mejor)

        tablero.push(jugada)
        eval_actual = motor.evaluar_posicion(tablero, tiempo_analisis)
        if eval_actual is None:  # posición de mate u otra rareza puntual
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

        if es_error and color_que_mueve == color_usuario:
            errores_usuario.append({
                "tipo_error": "error_tactico" if perdida_cp < 300 else "error_grave",
                "fen": fen_antes,
                "san_jugado": san,
                "san_mejor": mejor_jugada_san,
                "perdida_centipawns": int(perdida_cp),
            })

        eval_anterior = eval_actual
        if color_que_mueve == "negras":
            numero_jugada += 1

    return movimientos_info, errores_usuario


# ---------------------------------------------------------------------------
# Rachas, modo y nivel
# ---------------------------------------------------------------------------

def actualizar_rachas_y_modo(estado_usuario: dict, resultado: str, color_usuario: str) -> dict:
    """
    estado_usuario: dict con modo_bot, nivel_bot, racha_victorias_usuario,
    racha_victorias_bot (tal cual vienen de la tabla `usuarios`).
    resultado: '1-0' | '0-1' | '1/2-1/2'
    color_usuario: 'blancas' | 'negras'

    Devuelve un nuevo dict con el estado actualizado más la clave
    'generar_leccion' (bool) para saber si hay que crear una lección.

    Reglas (las pedidas):
      - Bot gana 5 seguidas  -> modo='coaching', nivel se congela, se genera lección.
      - Usuario gana 3 seguidas -> modo='learning', nivel +1 (sube "levemente").
      - Mientras está en modo 'coaching', el nivel no cambia salvo por la
        regla de arriba (eso es "congelar aprendizaje").
    """
    modo = estado_usuario["modo_bot"]
    nivel = estado_usuario["nivel_bot"]
    racha_usuario = estado_usuario["racha_victorias_usuario"]
    racha_bot = estado_usuario["racha_victorias_bot"]

    gano_usuario = (resultado == "1-0" and color_usuario == "blancas") or (
        resultado == "0-1" and color_usuario == "negras"
    )
    gano_bot = (resultado == "1-0" and color_usuario == "negras") or (
        resultado == "0-1" and color_usuario == "blancas"
    )

    if gano_usuario:
        racha_usuario += 1
        racha_bot = 0
    elif gano_bot:
        racha_bot += 1
        racha_usuario = 0
    else:  # tablas: no suman racha de nadie
        racha_usuario = 0
        racha_bot = 0

    generar_leccion = False

    if racha_bot >= RACHA_BOT_PARA_COACHING:
        modo = "coaching"
        generar_leccion = True
        racha_bot = 0  # reiniciamos el contador para no disparar de nuevo en cada partida

    if racha_usuario >= RACHA_USUARIO_PARA_LEARNING:
        modo = "learning"
        nivel = min(20, nivel + 1)  # sube "levemente": de a 1 nivel, con techo en 20
        racha_usuario = 0

    return {
        "modo_bot": modo,
        "nivel_bot": nivel,
        "racha_victorias_usuario": racha_usuario,
        "racha_victorias_bot": racha_bot,
        "generar_leccion": generar_leccion,
    }


# ---------------------------------------------------------------------------
# Generación de lecciones (basada en reglas, sin IA avanzada)
# ---------------------------------------------------------------------------

def generar_contenido_leccion(errores: list[dict]) -> str:
    """
    Texto simple basado en los errores detectados en la partida que
    disparó el modo coaching. No usa modelos de lenguaje: es una
    plantilla que ordena los errores por gravedad.
    """
    if not errores:
        return (
            "Esta partida no tuvo errores tácticos claros según Stockfish, "
            "pero el bot viene ganando seguido: probá variar tus aperturas "
            "y prestar atención a piezas que queden sin defensa."
        )

    errores_ordenados = sorted(errores, key=lambda e: e["perdida_centipawns"], reverse=True)
    top = errores_ordenados[:3]

    lineas = ["Estos fueron tus momentos más débiles en la partida que disparó el modo entrenador:", ""]
    for i, err in enumerate(top, start=1):
        mejor = err.get("san_mejor") or "(sin sugerencia)"
        lineas.append(
            f"{i}. Jugaste **{err['san_jugado']}**, que perdió aproximadamente "
            f"{err['perdida_centipawns']} centipawns. La jugada recomendada era **{mejor}**.\n"
            f"   FEN antes de la jugada: `{err['fen']}`"
        )

    lineas.append("")
    lineas.append(
        "Consejo general: antes de mover, revisá si tu pieza queda atacada y "
        "si hay alguna captura o jaque inmediato disponible para el rival."
    )
    return "\n".join(lineas)
