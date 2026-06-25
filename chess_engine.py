"""
chess_engine.py
Encapsula toda la interacción con el binario de Stockfish a través de
python-chess. El resto de la app no debería importar chess.engine
directamente.
"""

import chess
import chess.engine

# Rutas típicas donde puede estar instalado Stockfish, según el sistema.
RUTAS_CANDIDATAS = [
    "/usr/games/stockfish",   # Debian/Ubuntu (apt install stockfish)
    "/usr/bin/stockfish",
    "/usr/local/bin/stockfish",
    "stockfish",              # si está en el PATH
]


def localizar_stockfish(ruta_personalizada: str | None = None) -> str:
    """Devuelve la primera ruta de Stockfish que efectivamente arranca."""
    candidatos = [ruta_personalizada] if ruta_personalizada else []
    candidatos += RUTAS_CANDIDATAS

    for ruta in candidatos:
        if not ruta:
            continue
        try:
            motor = chess.engine.SimpleEngine.popen_uci(ruta)
            motor.quit()
            return ruta
        except Exception:
            continue

    raise FileNotFoundError(
        "No se encontró el binario de Stockfish. Instalalo con "
        "'sudo apt install stockfish' (Linux) o indicá la ruta completa "
        "en st.secrets['STOCKFISH_PATH']."
    )


def nivel_a_parametros_motor(nivel: int) -> dict:
    """
    Traduce el 'nivel del bot' (entero 1..20, simple e interpretable)
    a parámetros de Stockfish: Skill Level (0-20) + límite de tiempo.
    Niveles altos piensan un poquito más, además de jugar mejor.
    """
    skill = max(0, min(20, nivel))
    tiempo = round(0.1 + skill * 0.03, 2)
    return {"skill_level": skill, "time_limit": tiempo}


class MotorAjedrez:
    """Una instancia = un proceso de Stockfish abierto. Reutilizar, no recrear por jugada."""

    def __init__(self, ruta_stockfish: str | None = None):
        self.ruta = ruta_stockfish or localizar_stockfish()
        self.motor = chess.engine.SimpleEngine.popen_uci(self.ruta)

    def jugada_bot(self, tablero: chess.Board, nivel: int) -> chess.Move:
        """Devuelve la jugada que elige el bot, según su nivel actual."""
        params = nivel_a_parametros_motor(nivel)
        self.motor.configure({"Skill Level": params["skill_level"]})
        resultado = self.motor.play(tablero, chess.engine.Limit(time=params["time_limit"]))
        return resultado.move

    def evaluar_posicion(self, tablero: chess.Board, tiempo: float = 0.3) -> int | None:
        """Evaluación en centipawns desde la perspectiva de las blancas (None si hay mate)."""
        info = self.motor.analyse(tablero, chess.engine.Limit(time=tiempo))
        return info["score"].white().score(mate_score=100_000)

    def mejor_jugada(self, tablero: chess.Board, tiempo: float = 0.3) -> chess.Move | None:
        info = self.motor.analyse(tablero, chess.engine.Limit(time=tiempo))
        pv = info.get("pv")
        return pv[0] if pv else None

    def cerrar(self) -> None:
        try:
            self.motor.quit()
        except Exception:
            pass
