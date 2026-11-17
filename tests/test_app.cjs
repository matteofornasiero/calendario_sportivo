const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
assert.equal(html, fs.readFileSync(path.join(root, 'calendario_sportivo.html'), 'utf8'), 'I due ingressi devono restare identici');
const code = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
const element = id => {
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', style: {}, attributes: {}, dataset: {}, listeners: {},
        addEventListener(type, listener) { this.listeners[type] = listener; },
        classList: { add() {}, remove() {}, toggle() {} },
        setAttribute(name, value) { this.attributes[name] = value; },
        getAttribute(name) { return this.attributes[name] || null; },
        removeAttribute(name) { delete this.attributes[name]; }, remove() {}, appendChild() {} });
    return elements.get(id);
};
const themeChoices = ['sabbia', 'ink', 'scura'].map(theme => {
    const choice = element('theme-choice-' + theme);
    choice.setAttribute('data-theme-choice', theme);
    return choice;
});
const storage = new Map();
const document = { readyState: 'loading', hidden: false, getElementById: element,
    documentElement: element('documentElement'), querySelector: () => element('metaThemeColor'),
    querySelectorAll: selector => selector === '[data-theme-choice]' ? themeChoices : [],
    addEventListener() {}, createElement: () => element('script'),
    head: { appendChild(script) { script.onload(); } } };
const sandbox = { document, window: { addEventListener() {},
    localStorage: {
        getItem(key) { return storage.get(key) || null; },
        setItem(key, value) { storage.set(key, value); }
    }, navigator: { clipboard: { writeText: async value => { sandbox.lastCopied = value; } } },
        location: { href: 'https://matteofornasiero.github.io/calendario_sportivo/' }
    }, URL, URLSearchParams, Intl, Date,
    setTimeout, clearTimeout, setInterval: () => 1, clearInterval() {}, console };
const context = vm.createContext(sandbox);
vm.runInContext(code, context);
const run = expression => vm.runInContext(expression, context);

// Cambiare tema non richiede una rete o un account; persiste anche con preferenze locali.
assert.equal(run('currentTheme'), 'ink');
assert.equal(run("setTheme('sabbia')"), true);
assert.equal(run('currentTheme'), 'sabbia');
assert.equal(storage.get('sport-os-theme'), 'sabbia');
assert.equal(document.documentElement.getAttribute('data-theme'), 'sabbia');
assert.equal(element('metaThemeColor').getAttribute('content'), '#999794');
assert.equal(themeChoices[0].getAttribute('aria-pressed'), 'true');
assert.equal(themeChoices[1].getAttribute('aria-pressed'), 'false');
assert.equal(run("setTheme('non-esiste')"), false);
assert.equal(run('currentTheme'), 'sabbia');
run("setTheme('scura')");
assert.equal(storage.get('sport-os-theme'), 'scura');
assert.equal(element('metaThemeColor').getAttribute('content'), '#141518');
assert.equal(themeChoices[2].getAttribute('aria-pressed'), 'true');
run("setTheme('ink')");
assert.equal(storage.get('sport-os-theme'), 'ink');
assert.equal(element('metaThemeColor').getAttribute('content'), '#222327');
assert.equal(themeChoices[1].getAttribute('aria-pressed'), 'true');

// Verifica numericamente il contrasto WCAG AA del testo in tutte le palette.
const css = html.match(/<style>([\s\S]*?)<\/style>/)[1];
const themeBlock = theme => {
    const pattern = theme === 'ink'
        ? /:root\s*\{([^}]+)\}/
        : new RegExp(':root\\[data-theme="' + theme + '"\\]\\s*\\{([^}]+)\\}');
    const found = css.match(pattern);
    assert.ok(found, 'CSS tema assente: ' + theme);
    return found[1];
};
const themeColor = (theme, key) => {
    const block = themeBlock(theme);
    const found = block.match(new RegExp('--' + key + ':\\s*([^;]+);'));
    assert.ok(found, 'Colore assente: ' + theme + ' / ' + key);
    const value = found[1].trim();
    const reference = value.match(/^var\(--([a-z-]+)\)$/);
    if (reference) return themeColor(theme, reference[1]);
    assert.match(value, /^#[0-9a-fA-F]{6}$/, 'Colore non esadecimale: ' + key);
    return value;
};
const linear = channel => {
    const x = channel / 255;
    return x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
};
const luminance = hex => [1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16))
    .map(linear).reduce((sum, value, i) => sum + value * [0.2126, 0.7152, 0.0722][i], 0);
const contrast = (a, b) => {
    const x = luminance(a), y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};
for (const theme of ['sabbia', 'ink', 'scura']) {
    const bg = themeColor(theme, 'bg');
    const card = themeColor(theme, 'compact-bg');
    const shared = themeColor(theme, 'card-bg');
    const main = themeColor(theme, 'text-main');
    const sub = themeColor(theme, 'text-sub');
    const muted = themeColor(theme, 'text-muted');
    const selected = themeColor(theme, 'selected-bg');
    const selectedText = themeColor(theme, 'selected-text');
    const featured = themeColor(theme, 'featured-bg');
    const featuredText = themeColor(theme, 'featured-text');
    assert.equal(card, shared, theme + ': schede evento non uniformi');
    assert.equal(featured, shared, theme + ': hero più chiara o scura delle altre card');
    assert.ok(contrast(bg, main) >= 4.5, theme + ' testo principale non leggibile');
    assert.ok(contrast(card, main) >= 4.5, theme + ' testo card non leggibile');
    assert.ok(contrast(bg, sub) >= 4.5, theme + ' testo secondario non leggibile');
    assert.ok(contrast(bg, muted) >= 4.5, theme + ' testo attenuato non leggibile');
    assert.ok(contrast(selected, selectedText) >= 4.5, theme + ' selezione poco leggibile');
    assert.ok(contrast(featured, featuredText) >= 4.5, theme + ' card in evidenza poco leggibile');
    assert.ok(contrast(bg, card) <= 2.5, theme + ' card normali troppo staccate dal fondo');
}

// Le squadre contano: stemmi grandi e nome in evidenza, senza sfumature
// decorative. Hero e partite dell'elenco usano ESATTAMENTE la stessa superficie.
const napoliTorino = { sport: 'seriea', title: 'Napoli - Torino', home: 'Napoli', away: 'Torino' };
const accentByTheme = { sabbia: '#70253b', ink: '#f48daa', scura: '#f48daa' };
for (const theme of ['ink', 'scura', 'sabbia']) {
    run("setTheme('" + theme + "')");
    const match = run('getTopMatchTheme(' + JSON.stringify(napoliTorino) + ')');
    assert.equal(match.color, accentByTheme[theme], 'Accento leggibile in ' + theme);
    assert.equal(match.bg, 'var(--card-bg)', 'Niente sfumatura sulla card: ' + theme);
    assert.equal(match.border, '1px solid var(--border)');
    assert.equal(match.isAway, true);
    assert.ok(contrast(themeColor(theme, 'card-bg'), match.color) >= 4.5,
        'Colore della squadra leggibile sulla superficie: ' + theme);
}
run("setTheme('ink')");
assert.equal(run("getTopMatchTheme({sport:'nfl', title:'Broncos - Raiders', home:'Broncos', away:'Raiders'}).bg"), 'var(--card-bg)');
assert.equal(run("isFeaturedTeam('Torino', getTopMatchTheme({sport:'seriea', title:'Napoli - Torino', home:'Napoli', away:'Torino'}))"), true);
assert.equal(run("isFeaturedTeam('Napoli', getTopMatchTheme({sport:'seriea', title:'Napoli - Torino', home:'Napoli', away:'Torino'}))"), false);
assert.ok(html.includes('DA SEGUIRE') && html.includes('Apri partita'), 'Partita protagonista presente');
assert.ok(html.includes('.hero-crest { width: 59px; height: 59px;'), 'Stemmi grandi nel primo piano');
assert.ok(html.includes('min-height: 116px; margin: 0 0 13px;'), 'Sfida centrata, non vuota');
const awayHeroStart = html.indexOf('<div class="hero-team away">');
assert.ok(awayHeroStart >= 0);
assert.ok(html.indexOf('class="hero-crest"', awayHeroStart)
    < html.indexOf('class="hero-team-name', awayHeroStart), 'Stemma sopra nome anche in trasferta');
assert.ok(html.includes('.modal-sheet:not(.open) { box-shadow: none !important; }'),
    'Nessuna ombra nera in fondo dalla scheda nascosta');
assert.ok(html.indexOf('class="header-tools"') < html.indexOf('id="dataStatus"'),
    'Aggiornamento discreto sotto i comandi');
assert.ok(html.includes('font-size: 9px; font-weight: 450;'), 'Orario aggiornamento minimale');
assert.ok(html.includes('Barlow+Semi+Condensed'), 'Tipografia editoriale presente');
assert.ok(html.includes('SPORT OS / EDITORIAL SCORECARD v2'), 'Sistema visivo editoriale presente');
assert.ok(html.includes('border-bottom: 3px solid transparent'), 'Tab tipografiche');
assert.ok(html.includes('.sport-section-divider::after'), 'Etichette sport coese');
assert.ok(html.includes('.date-strip {') && html.includes('background: transparent !important'),
    'Settimana non vetrata');

// Header compatto, senza logo e mese sopra l'agenda.
assert.ok(!html.includes('class="app-brand"') && !html.includes('class="brand-title"'));
assert.ok(html.includes('class="header-tools"') && html.includes('id="searchContainer"'));
assert.ok(!html.includes('id="monthSelectorGroup"'));
assert.ok(html.includes('class="month-view-navigation"'), 'Navigazione mese solo su desktop nella vista mese');
assert.ok(html.includes('box-shadow: none !important; appearance: none;'), 'Nessuna ombra sul campo ricerca');
assert.ok(!html.includes('Gli orari sono espressi nel fuso italiano.'), 'Impostazioni prolisse');
assert.ok(html.includes('id="calendarSubscriptionsPanel"') && html.includes('id="sourceStatusPanel"'), 'Pannelli nelle impostazioni');

const event = { id: 'fixture-1', date: '2099-10-08', time: '23:30', timeConfirmed: true,
    startUtc: '2099-10-08T21:30:00Z', title: `Torino - L'Aquila "test" <img onerror=alert(1)>`,
    home: 'Torino', away: `L'Aquila`, homeCrest: '', awayCrest: '', sport: 'seriea', status: 'TIMED', isTop: true };
sandbox.fixture = event;
run('allEvents = [fixture]');
run("searchQuery = \"l'aquila\"");
assert.equal(run('getFilteredEvents().length'), 1, 'La ricerca deve gestire gli apostrofi');
run("searchQuery = ''");
const key = run('eventKey(fixture)');
assert.ok(!key.includes("'"));
run('renderHeroBanner()');
assert.ok(element('heroBannerContainer').innerHTML.includes('&lt;img onerror=alert(1)&gt;'));
run("searchQuery = 'torino'");
run('renderHeroBanner()');
assert.equal(element('heroBannerContainer').innerHTML, '', 'La ricerca nasconde la hero non filtrata');
run("searchQuery = ''");
assert.equal(run("eventDurationMinutes({ sport: 'nfl' })"), 210);
assert.equal(run("eventDurationMinutes({ sport: 'f1', title: 'Prove libere 1' })"), 90);
assert.equal(run("eventDurationMinutes({ sport: 'f1', title: 'GARA: Italia' })"), 150);
assert.ok(!element('heroBannerContainer').innerHTML.includes('<img onerror='));
run('openEventSheetByKey(eventKey(fixture))');
assert.equal(element('sheetEventTime').textContent, '23:30');
let params = new URL(element('btnGoogleCalendar').href).searchParams;
assert.equal(params.get('dates'), '20991008T213000Z/20991008T233000Z');
assert.equal(params.get('ctz'), 'Europe/Rome');
assert.equal(params.get('text'), event.title);
run("fixture.startUtc = '2099-10-08T23:30:00Z'; openEventSheetByKey(eventKey(fixture))");
params = new URL(element('btnGoogleCalendar').href).searchParams;
assert.equal(params.get('dates'), '20991008T233000Z/20991009T013000Z');
run("fixture.timeConfirmed = false; fixture.time = ''; fixture.startUtc = null; openEventSheetByKey(eventKey(fixture))");
assert.equal(element('btnGoogleCalendar').style.display, 'none');
assert.equal(element('sheetEventTime').textContent, 'Da definire');
run('updateCountdown(fixture)');
assert.equal(element('heroCountdownTimer').textContent, 'Orario da confermare');
run("fixture.status = 'FINISHED'");
assert.equal(run('getUpcomingHeroMatch()'), null);
assert.equal(run("safeImage('javascript:alert(1)')"), '');
assert.equal(run("safeImage('https://example.com/a.png')"), 'https://example.com/a.png');
run("renderAll = () => {}; currentView = 'month'; currentDate = new Date('2027-01-31T12:00:00'); navigateTime(1)");
assert.equal(run('formatDate(currentDate)'), '2027-02-28');
run("navigateTime(-1)");
assert.equal(run('formatDate(currentDate)'), '2027-01-28');
run("standingsData = { champions: [{ pos: 1, name: 'Torino', played: 5, points: 13 }] }; currentStandingsTab = 'champions'; renderStandings()");
assert.ok(element('standingsContentBox').innerHTML.includes('>13</td>'));
run("standingsData = { nfl: { divisions: { 'AFC West': [{ name: 'Denver', wins: 3, losses: 1, ties: 0 }] } } }; currentStandingsTab = 'nfl'; renderStandings()");
assert.ok(element('standingsContentBox').innerHTML.includes('>3-1</td>'));
run("calendarMeta = { generatedAt: '2020-01-01T00:00:00Z', sources: { nfl: { status: 'ok', updatedAt: '2020-01-01T00:00:00Z' } } }; renderDataStatus()");
assert.ok(element('dataStatus').textContent.includes('1 fonte da verificare'));

(async () => {
    // Abbonamento dal catalogo pubblico, con URL stabili e selettore squadra/competizione.
    element('subscriptionKind').value = 'teams';
    sandbox.fetch = async () => ({ ok: true, json: async () => ({
        schemaVersion: 1,
        teams: [{ name: 'Torino', path: 'calendari/squadra/torino.ics', count: 40 },
            { name: '<script>bad</script>', path: 'https://evil.example/calendar.ics' }],
        competitions: [{ name: 'Serie A', path: 'calendari/competizione/seriea.ics', count: 380 }]
    }) });
    await run('loadSubscriptionsCatalog()');
    assert.equal(run('subscriptionCatalog.teams.length'), 1, 'Escludi URL non validi');
    assert.equal(element('subscriptionChoice').disabled, false);
    assert.equal(element('subscriptionUrl').value, 'https://matteofornasiero.github.io/calendario_sportivo/calendari/squadra/torino.ics');
    assert.equal(element('subscriptionCopy').disabled, false);
    assert.equal(element('subscriptionOpen').href, 'webcal://matteofornasiero.github.io/calendario_sportivo/calendari/squadra/torino.ics');
    await run('copySubscriptionLink()');
    assert.equal(sandbox.lastCopied, element('subscriptionUrl').value);
    element('subscriptionKind').value = 'competitions';
    run('renderSubscriptionOptions()');
    assert.equal(element('subscriptionUrl').value, 'https://matteofornasiero.github.io/calendario_sportivo/calendari/competizione/seriea.ics');
    sandbox.window.calendarData = [event];
    sandbox.window.standingsData = {};
    sandbox.window.calendarMeta = { schemaVersion: 2, generatedAt: new Date().toISOString(), sources: {} };
    // Una competizione sola: etichetta in linea con la data, senza contatori.
    run("searchQuery = ''; currentView = 'agenda'; currentDate = new Date('2099-10-08T12:00:00'); selectedDateStr = '2099-10-08'; allEvents = [fixture];");
    run('renderAgendaFeed()');
    assert.ok(element('agendaFeed').innerHTML.includes('day-inline-sport'), 'Sport accanto al giorno');
    assert.ok(!element('agendaFeed').innerHTML.includes('1 evento'), 'Contatore eventi rimosso');
    assert.ok(!element('agendaFeed').innerHTML.includes('sport-section-divider'), 'Non ripetere unica competizione');
    run("allEvents.push({id:'f1-late',sport:'f1',date:'2099-10-08',time:'18:00',title:'Prove libere: GP',loc:'Circuito',timeConfirmed:true,startUtc:'2099-10-08T16:00:00Z',status:'TIMED'});");
    run('renderAgendaFeed()');
    assert.ok(element('agendaFeed').innerHTML.includes('sport-section-divider'), 'Più sport mostrati come piccole etichette');
    assert.ok(!element('agendaFeed').innerHTML.includes('2 eventi'), 'Contatore non ricompare');
    // La settimana rimane sfogliabile dopo la rimozione delle frecce.
    run('installWeekNavigation()');
    const weekNav = element('dateStripWrapper');
    assert.ok(weekNav.listeners.touchstart && weekNav.listeners.touchend && weekNav.listeners.keydown);
    weekNav.listeners.touchstart({ touches: [{clientX: 200, clientY: 100}] });
    weekNav.listeners.touchend({ changedTouches: [{clientX: 80, clientY: 102}] });
    assert.equal(run('formatDate(currentDate)'), '2099-10-15', 'Swipe verso sinistra: settimana successiva');
    weekNav.listeners.keydown({key:'ArrowLeft',preventDefault(){}});
    assert.equal(run('formatDate(currentDate)'), '2099-10-08', 'Freccia da tastiera: settimana precedente');
    // Quando Web Animations è disponibile, entrambe le settimane si spostano
    // in orizzontale; nei browser ridotti o vecchi resta il cambio immediato.
    const animatedStrip = element('dateStrip');
    let animationCalls = 0;
    animatedStrip.offsetTop = 13;
    animatedStrip.offsetLeft = 14;
    animatedStrip.getBoundingClientRect = () => ({width: 290});
    animatedStrip.cloneNode = () => ({
        style: {}, setAttribute() {}, removeAttribute() {},
        querySelectorAll: () => [], remove() { this.removed = true; },
        animate() { return {finished: Promise.resolve()}; }
    });
    animatedStrip.animate = frames => {
        animationCalls++;
        assert.ok(frames[0].transform.includes('translateX(100%)'));
        return {finished: Promise.resolve()};
    };
    run('animateWeekShift(1)');
    assert.equal(run('formatDate(currentDate)'), '2099-10-15');
    assert.equal(animationCalls, 1, 'L' + "'animazione deve essere reale'");
    await Promise.resolve();
    assert.equal(run('weekShiftInProgress'), false, 'Animazione pulita dopo la fine');
    sandbox.window.matchMedia = () => ({matches: true});
    run('animateWeekShift(-1)');
    assert.equal(run('formatDate(currentDate)'), '2099-10-08', 'Accessibilità: movimento ridotto');
    assert.equal(animationCalls, 1, 'Nessuna animazione con reduce motion');
    delete sandbox.window.matchMedia;
    run('allEvents = [fixture]');
    run('activeSheetEvent = null');
    await run('refreshData()');
    assert.equal(element('btnRefresh').disabled, false);
    assert.ok(element('script').src.startsWith('dati.js?v='));
    assert.ok(element('dataStatus').textContent.includes('Aggiornato:'));
    document.head.appendChild = script => script.onerror();
    await run('refreshData()');
    assert.equal(run('allEvents.length'), 1, 'Un errore di rete deve conservare i dati già caricati');
    assert.ok(element('dataStatus').textContent.includes('Ricaricamento fallito'));
    assert.equal(element('btnRefresh').disabled, false);
    console.log('OK: gerarchia editoriale, contrasti, team highlight, orari, classifiche, calendari e rete.');
})().catch(error => { console.error(error); process.exitCode = 1; });
