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


# Tabla de configuración por nivel: (Skill Level Stockfish, tiempo en seg, ELO aproximado)
# Nivel 1 = principiante absoluto (~400 ELO), Nivel 20 = jugador fuerte (~2400 ELO)
_NIVEL_CONFIG = [
    (0, 0.01,  400),  # 1
    (0, 0.02,  500),  # 2
    (0, 0.05,  600),  # 3
    (0, 0.10,  700),  # 4
    (1, 0.10,  800),  # 5
    (2, 0.10,  900),  # 6
    (3, 0.15, 1000),  # 7
    (4, 0.15, 1100),  # 8
    (5, 0.20, 1200),  # 9
    (6, 0.20, 1300),  # 10
    (7, 0.25, 1400),  # 11
    (8, 0.25, 1500),  # 12
    (9, 0.30, 1600),  # 13
    (11, 0.35, 1700),  # 14
    (13, 0.40, 1800),  # 15
    (14, 0.50, 1900),  # 16
    (15, 0.60, 2000),  # 17
    (17, 0.80, 2100),  # 18
    (18, 1.20, 2200),  # 19
    (20, 2.00, 2400),  # 20
]


def nivel_a_parametros_motor(nivel: int) -> dict:
    idx = max(0, min(19, nivel - 1))
    skill, tiempo, _ = _NIVEL_CONFIG[idx]
    return {"skill_level": skill, "time_limit": tiempo}


def elo_aproximado(nivel: int) -> int:
    idx = max(0, min(19, nivel - 1))
    return _NIVEL_CONFIG[idx][2]


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
