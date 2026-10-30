/* Deterministic maps and collision rules; independent of the statistics application. */
(function(root){
const W=76,H=60,T=32;
const zones=[{name:'I · Берег туманов',ground:'#426b47',shade:'#36573d',water:'#214650',enemy:'#84976d'},{name:'II · Ледяной перевал',ground:'#a8bfc1',shade:'#8da8b0',water:'#365a71',enemy:'#7395b4'},{name:'III · Крепость пепла',ground:'#666065',shade:'#504e57',water:'#382e39',enemy:'#a27572'}];
function makeMap(level){let seed=937+level*719;const rand=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296};const tiles=Array.from({length:H},(_,y)=>Array.from({length:W},(_,x)=> x<2||y<2||x>=W-2||y>=H-2?1:rand()<.14?2:0));
// Broad, connected trails guarantee access to all objectives.
for(let y=2;y<H-2;y++)for(let x=2;x<W-2;x++)if(Math.abs(x-38)<3||Math.abs(y-49)<3||Math.abs(y-30)<3||Math.abs(y-12)<3||Math.abs(x-12)<3||Math.abs(x-63)<3)tiles[y][x]=3;
const point=(x,y)=>({x:(x+.5)*T,y:(y+.5)*T});
const objects=[{...point(38,49),type:'fire'},{...point(12,30),type:'rune',id:0},{...point(63,30),type:'rune',id:1},{...point(12,12),type:'rune',id:2},{...point(63,49),type:'chest',id:0},{...point(63,12),type:'chest',id:1},{...point(38,5),type:'gate'}];
const enemies=[[25,49],[50,49],[12,40],[63,39],[22,30],[53,30],[12,21],[63,22],[24,12],[52,12],[38,14]].map(([x,y],i)=>({...point(x,y),homeX:(x+.5)*T,homeY:(y+.5)*T,hp:i===10?120+level*30:45+level*15,maxHp:i===10?120+level*30:45+level*15,boss:i===10,cooldown:0}));
return {tiles,objects,enemies,start:point(38,53),level};}
function blocked(map,x,y,r=10){for(const dx of [-r,r])for(const dy of [-r,r]){const t=map.tiles[Math.floor((y+dy)/T)]?.[Math.floor((x+dx)/T)];if(t===undefined||t===1||t===2)return true}return false}
function move(map,p,dx,dy){if(!blocked(map,p.x+dx,p.y))p.x+=dx;if(!blocked(map,p.x,p.y+dy))p.y+=dy}
const api={W,H,T,zones,makeMap,blocked,move};root.VikingEngine=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
