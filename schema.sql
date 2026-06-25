-- ============================================================
-- ChessLearnerBot · Esquema de Supabase (PostgreSQL)
-- Ejecutar en: Supabase Dashboard -> SQL Editor -> New query
-- ============================================================

create extension if not exists pgcrypto; -- para gen_random_uuid()

-- ---------------------------------------------------------------
-- USUARIOS
-- Guarda credenciales + el "estado del bot" para ese usuario:
-- modo actual, nivel, y rachas de victorias.
-- ---------------------------------------------------------------
create table if not exists usuarios (
    id                          uuid primary key default gen_random_uuid(),
    username                    text unique not null,
    password_hash               text not null,
    creado_en                   timestamptz not null default now(),

    modo_bot                    text not null default 'learning'
                                    check (modo_bot in ('learning', 'coaching')),
    nivel_bot                   integer not null default 1
                                    check (nivel_bot between 1 and 20),
    racha_victorias_usuario     integer not null default 0,
    racha_victorias_bot         integer not null default 0
);

-- ---------------------------------------------------------------
-- PREFERENCIAS DEL BOT (por usuario)
-- Separado de "usuarios" para poder ampliar sin tocar esa tabla.
-- ---------------------------------------------------------------
create table if not exists preferencias_bot (
    usuario_id          uuid primary key references usuarios(id) on delete cascade,
    color_preferido      text not null default 'aleatorio'
                            check (color_preferido in ('blancas', 'negras', 'aleatorio')),
    tiempo_analisis_seg  numeric not null default 0.3,
    actualizado_en       timestamptz not null default now()
);

-- ---------------------------------------------------------------
-- PARTIDAS
-- Una fila por partida terminada. El PGN completo queda guardado
-- para poder reproducir/revisar la partida desde cualquier dispositivo.
-- ---------------------------------------------------------------
create table if not exists partidas (
    id            uuid primary key default gen_random_uuid(),
    usuario_id    uuid not null references usuarios(id) on delete cascade,
    pgn           text not null,
    resultado     text not null check (resultado in ('1-0', '0-1', '1/2-1/2')),
    color_usuario text not null check (color_usuario in ('blancas', 'negras')),
    modo_bot      text not null,
    nivel_bot     integer not null,
    creada_en     timestamptz not null default now()
);

create index if not exists idx_partidas_usuario on partidas(usuario_id, creada_en desc);

-- ---------------------------------------------------------------
-- MOVIMIENTOS
-- Detalle jugada por jugada de cada partida (para análisis y replay).
-- ---------------------------------------------------------------
create table if not exists movimientos (
    id               bigserial primary key,
    partida_id       uuid not null references partidas(id) on delete cascade,
    numero_jugada    integer not null,
    color            text not null check (color in ('blancas', 'negras')),
    san              text not null,
    uci              text not null,
    eval_centipawns  integer,
    es_error         boolean not null default false
);

create index if not exists idx_movimientos_partida on movimientos(partida_id, numero_jugada);

-- ---------------------------------------------------------------
-- ERRORES FRECUENTES
-- Cada blunder/error táctico detectado por Stockfish después de la
-- partida. Sirve de insumo para las lecciones.
-- ---------------------------------------------------------------
create table if not exists errores_frecuentes (
    id                  bigserial primary key,
    usuario_id          uuid not null references usuarios(id) on delete cascade,
    partida_id          uuid references partidas(id) on delete set null,
    tipo_error          text not null default 'error_tactico',
    fen                 text not null,
    san_jugado          text not null,
    san_mejor           text,
    perdida_centipawns  integer not null,
    creado_en           timestamptz not null default now()
);

create index if not exists idx_errores_usuario on errores_frecuentes(usuario_id, creado_en desc);

-- ---------------------------------------------------------------
-- LECCIONES
-- Texto generado tras una racha de 5 derrotas seguidas (modo coaching).
-- ---------------------------------------------------------------
create table if not exists lecciones (
    id          bigserial primary key,
    usuario_id  uuid not null references usuarios(id) on delete cascade,
    partida_id  uuid references partidas(id) on delete set null,
    titulo      text not null,
    contenido   text not null,
    leida       boolean not null default false,
    creada_en   timestamptz not null default now()
);

create index if not exists idx_lecciones_usuario on lecciones(usuario_id, creada_en desc);

-- ---------------------------------------------------------------
-- NOTA sobre seguridad (RLS):
-- Este MVP usa la "service_role key" de Supabase desde el backend
-- de Streamlit (no se expone al navegador), por lo que Row Level
-- Security puede quedar desactivado por ahora. Si en el futuro se
-- llama a Supabase desde el cliente (browser) hay que activar RLS
-- y políticas por usuario_id = auth.uid().
-- ---------------------------------------------------------------
