const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const Mini=require('../static/wekings/mini-engine.js');
const source=fs.readFileSync(require.resolve('../static/wekings/arcade.js'),'utf8');
const axe=source.slice(source.indexOf('function mountAxe(life){'),source.indexOf('function mountSnake(life){'));
const handlers=new Map(),nodes=new Map();
const paint=new Proxy({createLinearGradient:()=>({addColorStop(){}})},{get(o,key){return o[key]??(()=>{});}});
function node(id){if(!nodes.has(id))nodes.set(id,{id,textContent:'',disabled:false,hidden:false,open:false,getContext:()=>paint});return nodes.get(id);}
let frame,stamp=0;
const document={hidden:false,activeElement:{tagName:'BODY'}};
const life={on(el,type,fn){handlers.set((el.id||'document')+':'+type,fn);},frame(fn){frame=fn;}};
const ctx={Mini,document,$:node,layout:()=>{},status:(t)=>node('status').textContent=t,best:(k,v)=>v,Math};
vm.createContext(ctx);vm.runInContext(axe+';mountAxe(life)',vm.createContext({...ctx,life}));
function click(id){handlers.get(id+':click')();}
function advance(){for(let i=0;i<12;i++){stamp+=70;frame(stamp);}}
frame(1);advance();
click('axe-pause');click('throw');assert.equal(node('axe-round').textContent,'1 / 10');click('axe-pause');
for(let i=0;i<10;i++){click('throw');assert.equal(node('throw').disabled,true);click('throw');advance();assert.equal(node('axe-round').textContent,Math.min(10,i+2)+' / 10');}
assert.match(node('status').textContent,/Серия завершена:/);assert.equal(node('throw').disabled,true);assert.equal(node('axe-pause').disabled,true);
const total=node('axe-points').textContent;click('throw');advance();assert.equal(node('axe-points').textContent,total);
click('restart');assert.equal(node('axe-round').textContent,'1 / 10');assert.equal(node('axe-points').textContent,'0');assert.equal(node('throw').disabled,false);
console.log('PASS axe: pause, flight lock, exactly ten throws, final result and restart');
