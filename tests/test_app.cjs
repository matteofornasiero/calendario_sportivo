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
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', style: {}, attributes: {},
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
    } }, URL, URLSearchParams, Intl, Date,
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
assert.equal(element('metaThemeColor').getAttribute('content'), '#baaa91');
assert.equal(themeChoices[0].getAttribute('aria-pressed'), 'true');
assert.equal(themeChoices[1].getAttribute('aria-pressed'), 'false');
assert.equal(run("setTheme('non-esiste')"), false);
assert.equal(run('currentTheme'), 'sabbia');
run("setTheme('scura')");
assert.equal(storage.get('sport-os-theme'), 'scura');
assert.equal(element('metaThemeColor').getAttribute('content'), '#212120');
assert.equal(themeChoices[2].getAttribute('aria-pressed'), 'true');
run("setTheme('ink')");
assert.equal(storage.get('sport-os-theme'), 'ink');
assert.equal(element('metaThemeColor').getAttribute('content'), '#92918d');
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
    const found = block.match(new RegExp('--' + key + ':\\s*(#[0-9a-fA-F]{6})'));
    assert.ok(found, 'Colore assente: ' + theme + ' / ' + key);
    return found[1];
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
    const main = themeColor(theme, 'text-main');
    const sub = themeColor(theme, 'text-sub');
    const muted = themeColor(theme, 'text-muted');
    const selected = themeColor(theme, 'selected-bg');
    const selectedText = themeColor(theme, 'selected-text');
    assert.ok(contrast(bg, main) >= 4.5, theme + ' testo principale non leggibile');
    assert.ok(contrast(card, main) >= 4.5, theme + ' testo card non leggibile');
    assert.ok(contrast(bg, sub) >= 4.5, theme + ' testo secondario non leggibile');
    assert.ok(contrast(bg, muted) >= 4.5, theme + ' testo attenuato non leggibile');
    assert.ok(contrast(selected, selectedText) >= 4.5, theme + ' selezione poco leggibile');
}

// Le card che interessano restano vivaci con nomi leggibili: Torino, Broncos, F1, club italiani.
for (const [sport, title, home, away, expectedAccent] of [
    ['seriea', 'Torino - Roma', 'Torino', 'Roma', '#8d1833'],
    ['nfl', 'Denver Broncos - Raiders', 'Denver Broncos', 'Raiders', '#a94617'],
    ['f1', 'GARA: Monza', '', '', '#af183b'],
    ['champions', 'Juventus - PSG', 'Juventus', 'PSG', 'linear-gradient']
]) {
    const palette = run('getTopMatchTheme(' + JSON.stringify({ sport, title, home, away }) + ')');
    assert.ok(palette.bg.includes(expectedAccent), 'Colore card principale: ' + title);
    const firstHex = palette.bg.match(/#[0-9a-f]{6}/i)[0];
    assert.ok(contrast(firstHex, '#ffffff') >= 4.5, 'Contrasto card evidenziata: ' + title);
}
assert.ok(run("getTopMatchTheme({ sport: 'seriea', title: 'Roma - Torino', home: 'Roma', away: 'Torino' }).border").includes('border-right'), 'Colore a destra in trasferta');


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
    sandbox.window.calendarData = [event];
    sandbox.window.standingsData = {};
    sandbox.window.calendarMeta = { schemaVersion: 2, generatedAt: new Date().toISOString(), sources: {} };
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
    console.log('OK: orari, chiavi dettagli, HTML, classifiche, calendario, navigazione e ricaricamento.');
})().catch(error => { console.error(error); process.exitCode = 1; });
