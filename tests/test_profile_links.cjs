const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../static/app.js'), 'utf8');
const helpers = source.slice(source.indexOf('const gameOrigins ='), source.indexOf('function syncMobileNav('));
function setup(saved, blocked = false) {
  const links = [
    {href: 'https://playwekings.mobi/hero/detail?player=666'},
    {href: 'https://wekings.online/hero/detail?player=123'}
  ];
  const storage = new Map(saved ? [['wekings.profileOrigin', saved]] : []);
  const context = vm.createContext({URL, encodeURIComponent,
    localStorage: {
      getItem(key) { if (blocked) throw Error('blocked'); return storage.get(key); },
      setItem(key, value) { if (blocked) throw Error('blocked'); storage.set(key, value); }
    },
    window: {location: {href: 'https://statistics.example/'}},
    document: {querySelectorAll() { return links; }}
  });
  vm.runInContext(helpers, context);
  return {context, links, storage};
}
test('profiles use current default and preserve player ID', () => {
  const {context} = setup();
  assert.equal(context.gameProfileUrl(666), 'https://playwekings.com/hero/detail?player=666');
});
test('each domain updates existing links, future links, and saved preference', () => {
  const {context, links, storage} = setup();
  for (const origin of ["https://playwekings.com", "https://wekings.online", "https://playwekings.mobi", "https://playwekings.ru", "https://proxy.playwekings.ru", "https://wekings.mobi", "http://87.228.3.220"]) {
    context.setGameOrigin(origin);
    assert.equal(links[0].href, `${origin}/hero/detail?player=666`);
    assert.equal(links[1].href, `${origin}/hero/detail?player=123`);
    assert.equal(context.gameProfileUrl(789), `${origin}/hero/detail?player=789`);
    assert.equal(storage.get('wekings.profileOrigin'), origin);
    assert.equal(setup(origin).context.gameProfileUrl(666), `${origin}/hero/detail?player=666`);
  }
});
test('invalid preference is ignored and inaccessible storage does not break navigation', () => {
  const {context} = setup('https://untrusted.example');
  context.setGameOrigin('https://untrusted.example');
  assert.equal(context.gameProfileUrl(666), 'https://playwekings.com/hero/detail?player=666');
  const blocked = setup(null, true);
  blocked.context.setGameOrigin('https://wekings.online');
  assert.equal(blocked.context.gameProfileUrl(666), 'https://wekings.online/hero/detail?player=666');
});
