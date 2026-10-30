const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/app.js'), 'utf8');
const code = source.slice(source.indexOf('function attackTimeText('), source.indexOf('function weatherTimeText('));
function render(now, value, stay = 60) {
  const NativeDate = Date;
  class FixedDate extends NativeDate {
    constructor(...args) { super(...(args.length ? args : [now])); }
  }
  const context = vm.createContext({Date: FixedDate});
  vm.runInContext(code, context);
  return context.attackTimeText(value, stay, 'Ушёл');
}
test('game schedule stays UTC+3 in winter and summer in every browser timezone', () => {
  const previous = process.env.TZ;
  try {
    for (const tz of ['UTC', 'Europe/Chisinau', 'Europe/Moscow', 'America/New_York']) {
      process.env.TZ = tz;
      for (const day of ['2026-10-30', '2026-07-15']) {
        assert.equal(render(`${day}T10:00:00Z`, `${day}T15:00:00Z`), '18:00');
        assert.equal(render(`${day}T10:00:00Z`, `${day}T15:00:00`), '18:00');
        assert.equal(render(`${day}T10:00:00Z`, `${day}T18:00:00+03:00`), '18:00');
      }
    }
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
});
test('date suffix uses game midnight and event duration uses elapsed time', () => {
  assert.equal(render('2026-10-30T20:00:00Z', '2026-10-30T21:30:00Z'), '00:30 · 31.10');
  assert.equal(render('2026-10-30T21:00:00Z', '2026-10-30T21:30:00Z'), '00:30');
  assert.equal(render('2026-10-30T16:00:00Z', '2026-10-30T15:00:00Z'), 'Ушёл');
  assert.equal(render('2026-10-30T16:00:00Z', '2026-10-30T15:00:00Z', 90), '18:00');
  assert.equal(render('2026-10-30T16:30:00Z', '2026-10-30T15:00:00Z', 90), 'Ушёл');
  assert.equal(render('2026-10-30T10:00:00Z', 'bad'), 'Ожидаем новое время');
});
