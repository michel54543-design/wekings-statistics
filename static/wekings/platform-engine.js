(function(root){'use strict';
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const overlap=(a,b)=>a.x<b.x+b.w&&a.x+a.w>b.x&&a.y<b.y+b.h&&a.y+a.h>b.y;
const approach=(a,b,d)=>a<b?Math.min(b,a+d):Math.max(b,a-d);
const themes=[{name:'Лес гоблинов',subtitle:'Следы ведут через старый лес',width:4400,ground:[[0,650],[760,500],[1370,720],[2200,600],[2910,650],[3670,730]],checks:[1500,3050],chests:[440,1780,3250]},
 {name:'Ледяной перевал',subtitle:'Север испытывает твою стойкость',width:4800,ground:[[0,560],[690,600],[1420,570],[2120,640],[2890,620],[3640,700],[4460,340]],checks:[1550,3760],chests:[360,2400,4000]},
 {name:'Логово дракона',subtitle:'Верни драккар из огненной гавани',width:5200,ground:[[0,630],[750,700],[1570,680],[2370,700],[3190,650],[3960,1240]],checks:[1700,4120],chests:[440,1780,4180]}];
function level(index){const t=themes[index];if(!t)throw Error('Неизвестный уровень');
const platforms=t.ground.map(([x,w],i)=>({id:'ground'+i,x,y:450,w,h:160,ice:index===1,ground:true}));
for(const [i,[x,w]] of t.ground.entries()){if(i<t.ground.length-1)platforms.push({id:'ledge'+i,x:x+Math.min(220,w*.45),y:342,w:145,h:24,ice:index===1});}
if(index===1)platforms.push({id:'moving',x:2015,baseX:2015,y:392,w:105,h:22,amp:54,period:3.4,moving:true,ice:true});
if(index===2)platforms.push({id:'fragile',x:2240,y:450,w:140,h:23,fragile:true,breakTime:0,restore:0});
const coins=[];for(const p of platforms){if(p.moving||p.fragile)continue;const count=p.ground?Math.max(3,Math.floor(p.w/115)):3;for(let i=0;i<count;i++)coins.push({x:p.x+45+i*(p.w-85)/Math.max(1,count-1),y:p.y-42,r:8,taken:false});}
const enemies=t.ground.slice(1,index===2?-1:undefined).map(([x,w],i)=>({id:i,x:x+w*.48,y:404,w:34,h:46,vx:((i%2)?-1:1)*(index===1?65:52),min:x+45,max:x+w-80,hp:2,maxHp:2,hit:0,dead:0,pose:'idle',poseTime:0,lastAttack:-1}));
const traps=t.ground.slice(0,-1).map(([x,w],i)=>({x:x+Math.floor(w*.55),y:432,w:44,h:18,type:index===2?'flame':'spikes',phase:i*.67}));
const icicles=index===1?t.ground.slice(1).map(([x,w])=>({x:x+w*.72,y:50,w:16,h:44,state:'idle',clock:0})):[];
return {index,...t,platforms,coins,enemies,traps,icicles,chests:t.chests.map((x,i)=>({x,y:420,w:32,h:30,kind:['axes','shield','heal'][i],open:false})),checkpoints:t.checks.map(x=>({x,y:450,active:false})),boss:index===2?{x:4730,y:330,w:180,h:120,hp:10,maxHp:10,hit:0,cycle:0,pose:'idle',poseTime:0,lastAttack:-1}:null,exit:{x:t.width-100,y:350,w:75,h:100}};
}
class Engine{
 constructor(index=0){this.coins=0;this.score=0;this.deaths=0;this.time=0;this.attackId=0;this.events=[];this.load(index);}
 load(index){this.world=level(index);this.level=index;this.hero={x:65,y:390,w:32,h:58,vx:0,vy:0,hp:5,maxHp:5,facing:1,onGround:false,groundId:null,coyote:0,jumpBuffer:0,invulnerable:0,attack:0,cooldown:0,throwCooldown:0,ammo:0,shield:0};this.checkpoint={x:65,y:390};this.bullets=[];this.particles=[];this.clock=0;this.wasJump=false;this.mode='ready';this.message='Найди путь к драккару';this.events=[];this.levelStartScore=this.score;this.levelStartCoins=this.coins;}
 emit(text,type='info'){this.message=text;this.events.push({text,type});}
 start(){if(this.mode==='ready'||this.mode==='paused')this.mode='playing';else if(this.mode==='dead')this.respawn();else if(this.mode==='complete')this.load(this.level+1);}
 pause(){if(this.mode==='playing')this.mode='paused';}
 restartLevel(){this.score=this.levelStartScore;this.coins=this.levelStartCoins;this.load(this.level);}
 respawn(){const p=this.hero;Object.assign(p,{x:this.checkpoint.x,y:this.checkpoint.y,vx:0,vy:0,hp:5,onGround:false,groundId:null,invulnerable:1.5,attack:0,cooldown:0,throwCooldown:0,jumpBuffer:0,coyote:0});p.ammo=Math.max(3,p.ammo);this.bullets=[];this.wasJump=false;this.mode='playing';this.emit('Сага продолжается с контрольной точки.');}
 die(text='Викинг пал. Вернись к контрольной точке.'){if(this.mode!=='playing')return;this.deaths++;this.score=Math.max(0,this.score-50);this.mode='dead';this.hero.hp=0;this.emit(text,'danger');}
 hurt(direction=0){const p=this.hero;if(this.mode!=='playing'||p.invulnerable>0)return false;p.invulnerable=1.3;if(p.shield){p.shield=0;this.emit('Щит принял удар!');return true;}p.hp--;p.vx=direction*150;p.vy=-210;if(p.hp<=0)this.die();else this.emit('Осторожно! Потеряно здоровье.','danger');return true;}
 strike(target,damage){if(target.hp<=0)return;target.hp=Math.max(0,target.hp-damage);target.hit=.25;target.pose=target.hp?'hit':'death';target.poseTime=0;if(!target.hp){this.score+=target===this.world.boss?300:25;target.dead=.7;this.emit(target===this.world.boss?'Дракон повержен! Драккар ждёт в гавани.':'Гоблин повержен.','good');}}
 update(dt,input={}){if(this.mode!=='playing')return;dt=clamp(dt,0,.05);if(!dt)return;const count=Math.ceil(dt/(1/120));for(let i=0;i<count;i++){if(this.mode!=='playing')break;this.step(dt/count,input);} }
 step(dt,input){const p=this.hero,w=this.world;this.clock+=dt;this.time+=dt;
for(const platform of w.platforms){platform.dx=0;if(platform.moving){const old=platform.x;platform.x=platform.baseX+Math.sin(this.clock*Math.PI*2/platform.period)*platform.amp;platform.dx=platform.x-old;}if(platform.restore>0){platform.restore=Math.max(0,platform.restore-dt);if(platform.restore===0)platform.breakTime=0;}else if(platform.breakTime>0){platform.breakTime+=dt;if(platform.breakTime>.8){platform.restore=2.5;if(p.groundId===platform.id){p.onGround=false;p.groundId=null;}}}}
const standing=w.platforms.find(a=>a.id===p.groundId&&!a.restore);if(p.onGround&&standing)p.x+=standing.dx;
p.invulnerable=Math.max(0,p.invulnerable-dt);p.attack=Math.max(0,p.attack-dt);p.cooldown=Math.max(0,p.cooldown-dt);p.throwCooldown=Math.max(0,p.throwCooldown-dt);p.coyote=p.onGround ? .11 :Math.max(0,p.coyote-dt);p.jumpBuffer=Math.max(0,p.jumpBuffer-dt);
if(input.jump&&!this.wasJump)p.jumpBuffer=.13;this.wasJump=!!input.jump;
const move=(input.right?1:0)-(input.left?1:0);if(move)p.facing=move;
const accel=p.onGround&&standing?.ice?620:p.onGround?2300:1200;const friction=p.onGround&&standing?.ice?220:1800;p.vx=approach(p.vx,move*235,(move?accel:friction)*dt);
if(p.jumpBuffer>0&&p.coyote>0){p.vy=-720;p.onGround=false;p.groundId=null;p.coyote=0;p.jumpBuffer=0;}
if(input.attack&&p.cooldown===0){p.attack=.23;p.cooldown=.38;this.attackId++;}
if(input.throw&&p.throwCooldown===0&&p.ammo>0){p.ammo--;p.throwCooldown=.45;this.bullets.push({x:p.x+(p.facing>0?p.w:0),y:p.y+20,w:15,h:15,vx:p.facing*600,vy:-80,life:1.1,kind:'axe'});}
const oldBottom=p.y+p.h;p.x+=p.vx*dt;p.x=clamp(p.x,0,w.width-p.w);for(const platform of w.platforms){if(platform.restore||platform.h<40)continue;if(overlap(p,platform)&&oldBottom>platform.y+10){if(p.vx>0)p.x=platform.x-p.w;else if(p.vx<0)p.x=platform.x+platform.w;p.vx=0;}}
p.vy=Math.min(950,p.vy+1800*dt);p.y+=p.vy*dt;p.onGround=false;p.groundId=null;
if(p.vy>=0){let landed=null;for(const a of w.platforms){if(a.restore)continue;if(p.x+p.w>a.x+2&&p.x<a.x+a.w-2&&oldBottom<=a.y+6&&p.y+p.h>=a.y){if(!landed||a.y<landed.y)landed=a;}}if(landed){p.y=landed.y-p.h;p.vy=0;p.onGround=true;p.groundId=landed.id;if(landed.fragile&&!landed.breakTime)landed.breakTime=dt;}}
if(p.y>650){this.die('Падение в пропасть. Контрольная точка сохранена.');return;}
for(const flag of w.checkpoints)if(!flag.active&&p.x>=flag.x){flag.active=true;this.checkpoint={x:flag.x+15,y:flag.y-p.h};p.hp=Math.min(p.maxHp,p.hp+2);this.emit('Контрольная точка! +2 здоровья.','good');}
for(const coin of w.coins)if(!coin.taken&&overlap(p,{x:coin.x-8,y:coin.y-8,w:16,h:16})){coin.taken=true;this.coins++;this.score+=10;}
for(const chest of w.chests)if(!chest.open&&overlap(p,chest)){chest.open=true;if(chest.kind==='axes'){p.ammo+=6;this.emit('Сундук: 6 метательных топоров!','good');}else if(chest.kind==='shield'){p.shield=1;this.emit('Сундук: щит защитит от одного удара.','good');}else{p.hp=p.maxHp;this.emit('Сундук: здоровье восстановлено.','good');}}
for(const trap of w.traps){const cycle=(this.clock+trap.phase)%3;trap.active=trap.type==='spikes'||cycle>1.4&&cycle<2.4;trap.warning=trap.type==='flame'&&cycle>1&&cycle<=1.4;if(trap.active&&overlap(p,{...trap,y:trap.type==='flame'?390:trap.y,h:trap.type==='flame'?60:trap.h}))this.hurt(p.x<trap.x?-1:1);}
for(const icicle of w.icicles){icicle.clock+=dt;if(icicle.state==='idle'&&Math.abs(p.x-icicle.x)<130){icicle.state='warning';icicle.clock=0;}if(icicle.state==='warning'&&icicle.clock>.7){icicle.state='falling';icicle.clock=0;}if(icicle.state==='falling'){icicle.y+=720*dt;if(overlap(p,icicle))this.hurt(p.x<icicle.x?-1:1);if(icicle.y>540){icicle.state='rest';icicle.clock=0;}}if(icicle.state==='rest'&&icicle.clock>4){icicle.y=50;icicle.state='idle';}}
const attackBox={x:p.facing>0?p.x+p.w-4:p.x-65,y:p.y-4,w:69,h:p.h+8};
for(const enemy of w.enemies){enemy.poseTime+=dt;enemy.hit=Math.max(0,enemy.hit-dt);if(enemy.hp<=0){enemy.dead=Math.max(0,enemy.dead-dt);continue;}enemy.x+=enemy.vx*dt;if(enemy.x<enemy.min){enemy.x=enemy.min;enemy.vx=Math.abs(enemy.vx);}if(enemy.x>enemy.max){enemy.x=enemy.max;enemy.vx=-Math.abs(enemy.vx);}if(p.attack>0&&enemy.lastAttack!==this.attackId&&overlap(attackBox,enemy)){enemy.lastAttack=this.attackId;this.strike(enemy,1);}if(enemy.hp>0&&overlap(p,enemy)){if(p.vy>80&&oldBottom<=enemy.y+16){this.strike(enemy,1);p.vy=-440;p.onGround=false;}else{enemy.pose='attack';enemy.poseTime=0;this.hurt(p.x<enemy.x?-1:1);}}}
const boss=w.boss;if(boss){boss.poseTime+=dt;boss.hit=Math.max(0,boss.hit-dt);if(boss.hp>0&&p.x>boss.x-720){boss.cycle+=dt;boss.pose=boss.cycle>1.35?'attack':'idle';if(boss.cycle>2.25){const originX=p.x<boss.x?boss.x:boss.x+boss.w,dx=p.x-originX,dy=p.y+20-(boss.y+70),len=Math.hypot(dx,dy)||1;this.bullets.push({x:originX,y:boss.y+70,w:24,h:24,vx:dx/len*245,vy:dy/len*245,life:4,kind:'fire'});boss.cycle=0;boss.poseTime=0;}if(p.attack>0&&boss.lastAttack!==this.attackId&&overlap(attackBox,boss)){boss.lastAttack=this.attackId;this.strike(boss,1);}if(boss.hp>0&&overlap(p,boss))this.hurt(p.x<boss.x?-1:1);}else if(boss.hp<=0)boss.dead=Math.max(0,boss.dead-dt);}
for(const b of this.bullets){b.life-=dt;if(b.life<=0)continue;b.x+=b.vx*dt;b.y+=b.vy*dt;if(b.kind==='axe'){b.vy+=300*dt;for(const target of [...w.enemies,...(boss?[boss]:[])])if(target.hp>0&&overlap(b,target)){this.strike(target,2);b.life=0;break;}}else if(overlap(p,b)){this.hurt(b.vx>0?1:-1);b.life=0;}}
this.bullets=this.bullets.filter(b=>b.life>0&&b.y<650&&b.x>-100&&b.x<w.width+100);
if(overlap(p,w.exit)&&(!boss||boss.hp<=0)){this.score+=500;this.mode=this.level===2?'won':'complete';this.emit(this.mode==='won'?'Драккар возвращён! Сага завершена.':'Уровень пройден. Север зовёт дальше!','good');}
 }
}
const api={Engine,level,themes,overlap,clamp};root.Drakkar=api;if(typeof module!=='undefined')module.exports=api;
})(globalThis);
