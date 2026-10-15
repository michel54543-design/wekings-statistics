const W=require('../static/wekings/engine.js');
const tests=[];
for(const mode of ['classic','adventure','quick'])for(let pos=0;pos<100;pos++)for(const value of [1,3,6])for(const r of [0,.4,.99]){const state=W.create({mode});Object.assign(state.players[0],{pos,shield:pos%3===0,skip:pos%17===0?1:0});tests.push({kind:'roll',state,value,r,result:W.resolve(state,value,()=>r)});}
for(const at of Object.keys(W.enemies).map(Number))for(const stance of ['attack','guard'])for(const value of [1,3,6])for(const hp of [1,18])for(const r of [0,.99]){const state=W.create();state.players[0].pos=at;state.players[0].shield=value===3;state.battle={at,heroHp:hp,enemyHp:Math.min(value+1,W.enemies[at].hp)};tests.push({kind:'fight',state,stance,value,r,result:W.fight(state,stance,value,()=>r)});}
process.stdout.write(JSON.stringify(tests));
