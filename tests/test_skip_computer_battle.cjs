const fs=require('fs'),vm=require('vm'),assert=require('assert');
const Wekings=require(process.cwd()+'/static/wekings/engine.js');
const source=fs.readFileSync('static/wekings/app.js','utf8');const fn=source.slice(source.indexOf('async function skipComputerBattle(){'),source.indexOf('function mapHealth('));
async function scenario({pending=false,lose=false,online=false,actor=1}={}){
const state=Wekings.create({count:2});state.turn=actor;state.players[actor].pos=16;state.battle={at:16,heroHp:lose?1:18,enemyHp:lose?16:7};
const nodes={result:{},'map-enemy-hp':{}};let dispatches=0;const events=[];
const transport={dispatch:async(s,c)=>{dispatches++;return Wekings.fight(s,'attack',lose?1:6,()=>lose?.999:0);}};
let outcome=pending?await transport.dispatch(state,{}):null;const baseline=dispatches;
const ctx={state,online:online?{}:null,paused:false,skippingAiFight:false,pendingAiFight:pending?{id:1,actor,outcome}:null,epoch:1,busy:pending,skipAiButton:{hidden:false},fieldRoll:{hidden:false},mapBattle:{querySelectorAll:()=>[]},aiSummary:{hidden:true},visualPositions:{},Wekings,transport,focusIndex:actor,follow:true,$:id=>nodes[id]??={},log:t=>events.push(t),render:()=>{},schedule:()=>{},sleep:async()=>{},waitReady:async id=>id===ctx.epoch};vm.createContext(ctx);vm.runInContext(fn,ctx);await ctx.skipComputerBattle();
if(online||actor===0){assert.equal(dispatches,baseline);assert.equal(ctx.epoch,1);return;}
assert.equal(ctx.state.battle,null);assert.equal(ctx.state.turn,0);assert.equal(ctx.busy,false);assert.equal(ctx.skippingAiFight,false);assert.equal(events.length,1);
if(lose){assert.equal(ctx.state.players[1].pos,12);assert.equal(ctx.state.players[1].skip,1);assert.ok(events[0].includes('проиграл'));}else{assert.ok(ctx.state.players[1].cleared.includes(16));assert.equal(dispatches,pending?2:2);assert.ok(events[0].includes('победил'));}
}
(async()=>{await scenario();await scenario({pending:true});await scenario({lose:true,pending:true});await scenario({online:true});await scenario({actor:0});console.log('PASS: victory, existing roll reused, defeat/retreat/skip, online blocked, human blocked');})().catch(e=>{console.error(e);process.exit(1)});
