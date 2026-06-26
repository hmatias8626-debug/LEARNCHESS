// features.js — Timer, guardar racha, ranking, compartir

const TIMER_SEGUNDOS = 7;
let timerInterval = null;
let timerRestante = 0;
let rachaCortada = 0;

// ---------- Timer ----------

function iniciarTimer() {
    detenerTimer();
    timerRestante = TIMER_SEGUNDOS;
    actualizarTimerUI();
    timerInterval = setInterval(() => {
        timerRestante--;
        actualizarTimerUI();
        if (timerRestante <= 0) {
            detenerTimer();
            responder(respuestaCorrecta === 'a' ? 'b' : 'a');
        }
    }, 1000);
}

function detenerTimer() {
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
}

function actualizarTimerUI() {
    const el = document.getElementById('timer-countdown');
    if (!el) return;
    el.textContent = timerRestante;
    el.className = 'timer-countdown' + (timerRestante <= 3 ? ' urgente' : '');
    const arc = document.getElementById('timer-arc');
    if (arc) {
        const circum = 2 * Math.PI * 26;
        arc.style.strokeDasharray = circum;
        arc.style.strokeDashoffset = circum * (1 - timerRestante / TIMER_SEGUNDOS);
        arc.style.stroke = timerRestante <= 3 ? '#e94560' : '#2ecc71';
    }
}

// ---------- Wrappers ----------

const _origMostrarPregunta = mostrarPregunta;
window.mostrarPregunta = function () {
    _origMostrarPregunta();
    iniciarTimer();
};

const _origResponder = responder;
window.responder = function (elegida) {
    detenerTimer();
    if (elegida !== respuestaCorrecta) rachaCortada = racha;
    _origResponder(elegida);
};

const _origMostrarResultado = mostrarResultado;
window.mostrarResultado = function (esCorrecta, p) {
    _origMostrarResultado(esCorrecta, p);

    const guardarDiv = document.getElementById('guardar-racha');
    const compartirBtn = document.getElementById('btn-compartir');

    if (!esCorrecta && rachaCortada >= 3) {
        document.getElementById('racha-a-guardar').textContent = rachaCortada;
        document.getElementById('input-nombre').value = '';
        const form = guardarDiv.querySelector('.guardar-racha-form');
        if (form) form.style.display = '';
        const oldOk = guardarDiv.querySelector('.guardado-ok');
        if (oldOk) oldOk.remove();
        guardarDiv.classList.remove('oculto');
        compartirBtn.dataset.racha = rachaCortada;
        compartirBtn.classList.remove('oculto');
    } else {
        guardarDiv.classList.add('oculto');
        const showShare = racha >= 3;
        compartirBtn.classList[showShare ? 'remove' : 'add']('oculto');
        if (showShare) compartirBtn.dataset.racha = racha;
    }
};

document.getElementById('btn-volver').addEventListener('click', detenerTimer);

// ---------- Guardar nombre ----------

document.getElementById('btn-guardar-nombre').addEventListener('click', () => {
    const nombre = document.getElementById('input-nombre').value.trim();
    if (!nombre) { alert('Ingresá tu nombre.'); return; }
    const r = parseInt(document.getElementById('racha-a-guardar').textContent, 10);
    guardarEnRanking(nombre, r);
    const guardarDiv = document.getElementById('guardar-racha');
    const form = guardarDiv.querySelector('.guardar-racha-form');
    if (form) form.style.display = 'none';
    const ok = document.createElement('p');
    ok.className = 'guardado-ok';
    ok.textContent = '✅ ¡Guardado en el ranking!';
    guardarDiv.appendChild(ok);
    setTimeout(() => {
        guardarDiv.classList.add('oculto');
        if (form) form.style.display = '';
        ok.remove();
    }, 2000);
});

document.getElementById('btn-compartir').addEventListener('click', () => {
    compartirRacha(parseInt(document.getElementById('btn-compartir').dataset.racha, 10) || racha);
});

// ---------- Ranking ----------

const RANKING_KEY = 'quien_primero_ranking';

function obtenerRanking() {
    try { return JSON.parse(localStorage.getItem(RANKING_KEY)) || []; } catch { return []; }
}

function guardarEnRanking(nombre, rachaVal) {
    const ranking = obtenerRanking();
    ranking.push({ nombre, racha: rachaVal, fecha: new Date().toLocaleDateString('es-AR') });
    ranking.sort((a, b) => b.racha - a.racha);
    ranking.splice(5);
    localStorage.setItem(RANKING_KEY, JSON.stringify(ranking));
    mostrarRanking();
}

function mostrarRanking() {
    const lista = document.getElementById('ranking-lista');
    if (!lista) return;
    const ranking = obtenerRanking();
    if (ranking.length === 0) {
        lista.innerHTML = '<p class="ranking-vacio">Todavía no hay registros. ¡Llegá a una racha de 3!</p>';
        return;
    }
    const medallas = ['🥇', '🥈', '🥉'];
    lista.innerHTML = ranking.map((e, i) =>
        '<div class="ranking-item">' +
        '<span class="ranking-pos">' + (medallas[i] || (i + 1) + '.') + '</span>' +
        '<span class="ranking-nombre">' + e.nombre + '</span>' +
        '<span class="ranking-racha">' + e.racha + '</span>' +
        '<span class="ranking-fecha">' + e.fecha + '</span>' +
        '</div>'
    ).join('');
}

// ---------- Compartir ----------

function compartirRacha(rachaVal) {
    const texto = '¡Llegué a una racha de ' + rachaVal + ' en "¿Quién lo hizo primero?"! 🏆 ¿Podés superarme?';
    if (navigator.share) {
        navigator.share({ text: texto }).catch(() => {});
    } else {
        navigator.clipboard.writeText(texto)
            .then(() => alert('¡Texto copiado! Podés pegarlo donde quieras.'))
            .catch(() => alert(texto));
    }
}

// Init
mostrarRanking();
