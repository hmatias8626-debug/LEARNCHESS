# ChessLearnerBot — MVP online (Streamlit + Supabase + Stockfish)

Bot de ajedrez que aprende jugando contra vos. Guarda todo en Supabase
para que puedas seguir tu progreso desde el celular, la notebook o la PC.

## Estructura del proyecto

```
chesslearnerbot/
├── app.py                  # Interfaz Streamlit (login, tablero, flujo de juego)
├── auth.py                 # Login simple (hash de contraseña)
├── db.py                   # Toda la comunicación con Supabase
├── chess_engine.py         # Wrapper de Stockfish
├── bot_logic.py            # Análisis de partidas, rachas, modo, lecciones
├── schema.sql              # Tablas a crear en Supabase
├── requirements.txt        # Dependencias Python
├── packages.txt            # Dependencias de sistema (Stockfish) para Streamlit Cloud
└── .streamlit/
    └── secrets.toml.example
```

## 1. Crear el proyecto en Supabase

1. Entrá a https://supabase.com y creá un proyecto nuevo (gratis).
2. Una vez creado, ir a **SQL Editor → New query**, pegar todo el
   contenido de `schema.sql` y ejecutarlo. Esto crea las tablas:
   `usuarios`, `preferencias_bot`, `partidas`, `movimientos`,
   `errores_frecuentes`, `lecciones`.
3. Ir a **Project Settings → API** y copiar:
   - `Project URL` → va en `SUPABASE_URL`
   - `service_role` key (o `anon` key si vas a activar RLS más adelante)
     → va en `SUPABASE_KEY`

   > Nota de seguridad: este MVP llama a Supabase **desde el servidor de
   > Streamlit**, no desde el navegador del usuario, por eso puede usarse
   > la `service_role` key sin exponerla al cliente. Si en el futuro se
   > llama a Supabase directamente desde JS en el browser, hay que pasar
   > a la `anon` key + activar Row Level Security con políticas por
   > `usuario_id`.

## 2. Configurar las credenciales

Copiá `.streamlit/secrets.toml.example` a `.streamlit/secrets.toml` y
completá con tus datos reales:

```toml
SUPABASE_URL = "https://tu-proyecto.supabase.co"
SUPABASE_KEY = "tu-key"
```

También podés usar variables de entorno (`SUPABASE_URL`, `SUPABASE_KEY`)
en lugar de `secrets.toml`, por ejemplo para correrlo en otro hosting.

## 3. Instalar Stockfish y las dependencias Python

**Local (Linux/Debian/Ubuntu):**
```bash
sudo apt install stockfish
pip install -r requirements.txt
```

**Local (Windows/Mac):** descargar el binario desde
https://stockfishchess.org/download/ y, si no queda en una ruta
estándar, indicar la ruta completa en `secrets.toml`:
```toml
STOCKFISH_PATH = "C:/ruta/a/stockfish.exe"
```

**Streamlit Community Cloud:** el archivo `packages.txt` ya incluye
`stockfish`, así que Streamlit Cloud lo instala solo al desplegar.

## 4. Correr la app

```bash
streamlit run app.py
```

Abrí la URL que te muestra la terminal. Desde cualquier otro
dispositivo (celular, otra PC) iniciás sesión con el mismo usuario y
contraseña, y vas a ver el mismo nivel, mismas rachas y mismas
lecciones: todo vive en Supabase, no en el dispositivo.

Para acceder desde el celular sin desplegar a Streamlit Cloud, basta
con desplegarlo gratis en https://streamlit.io/cloud conectando este
mismo repositorio.

## Cómo funciona el ciclo de aprendizaje (resumen)

- Cada jugada del bot usa el **Skill Level** de Stockfish, calculado a
  partir de `nivel_bot` (1 a 20).
- Al terminar una partida, se analiza jugada por jugada con Stockfish
  y se guarda en `movimientos`. Las jugadas tuyas que pierden 150+
  centipawns quedan registradas en `errores_frecuentes`.
- Si el bot te gana **5 veces seguidas** → modo `coaching`, el nivel
  queda congelado y se genera una lección en base a tus errores de esa
  partida.
- Si vos le ganás **3 veces seguidas** → vuelve a modo `learning` y el
  nivel sube en 1.
- Las lecciones son generadas por reglas simples (ordenar errores por
  centipawns perdidos), sin modelos de lenguaje ni redes neuronales,
  tal como se pidió para este MVP.

## Decisiones de diseño (para que sepas qué asumí)

- **Selección de jugada:** en vez de arrastrar piezas (requiere un
  componente JS custom), elegís tu jugada de una lista desplegable en
  notación SAN. Es la forma más simple y confiable en Streamlit puro.
- **Modo coaching:** el bot sigue jugando partidas igual, pero el nivel
  no se mueve hasta que rompas la racha ganándole 3 veces. "Congelar
  aprendizaje" se interpretó como "no subir/bajar nivel automáticamente
  mientras estás en ese modo".
- **Login:** usuario/contraseña con hash PBKDF2-SHA256 guardado en
  Supabase. Es simple y suficiente para uso personal; no es para una
  app pública con muchos usuarios.

## Próximos pasos posibles (fuera del alcance de este MVP)

- Activar Row Level Security en Supabase si se llama desde el cliente.
- Reemplazar el selectbox de jugadas por un tablero clickeable
  (ej. con `streamlit-chessboard` o un componente custom).
- Mejorar la clasificación de errores (apertura/medio juego/final,
  piezas colgadas vs. errores posicionales) en vez del umbral único de
  centipawns.
