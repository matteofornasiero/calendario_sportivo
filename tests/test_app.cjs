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
    if (!elements.has(id)) elements.set(id, { textContent: '', innerHTML: '', style: {},
        classList: { add() {}, remove() {}, toggle() {} },
        removeAttribute(name) { delete this[name]; }, remove() {}, appendChild() {} });
    return elements.get(id);
};
const document = { readyState: 'loading', hidden: false, getElementById: element,
    addEventListener() {}, createElement: () => element('script'),
    head: { appendChild(script) { script.onload(); } } };
const sandbox = { document, window: { addEventListener() {} }, URL, URLSearchParams, Intl, Date,
    setTimeout, clearTimeout, setInterval: () => 1, clearInterval() {}, console };
const context = vm.createContext(sandbox);
vm.runInContext(code, context);
const run = expression => vm.runInContext(expression, context);
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
assert.ok(element('dataStatus').textContent.includes('Dati da verificare: NFL'));

(async () => {
    sandbox.window.calendarData = [event];
    sandbox.window.standingsData = {};
    sandbox.window.calendarMeta = { schemaVersion: 2, generatedAt: new Date().toISOString(), sources: {} };
    run('activeSheetEvent = null');
    await run('refreshData()');
    assert.equal(element('btnRefresh').disabled, false);
    assert.ok(element('script').src.startsWith('dati.js?v='));
    assert.ok(element('dataStatus').textContent.includes('Ultimo aggiornamento:'));
    document.head.appendChild = script => script.onerror();
    await run('refreshData()');
    assert.equal(run('allEvents.length'), 1, 'Un errore di rete deve conservare i dati già caricati');
    assert.ok(element('dataStatus').textContent.includes('Ricaricamento fallito'));
    assert.equal(element('btnRefresh').disabled, false);
    console.log('OK: orari, chiavi dettagli, HTML, classifiche, calendario, navigazione e ricaricamento.');
})().catch(error => { console.error(error); process.exitCode = 1; });
