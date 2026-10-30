/* Articulated characters: limbs animate independently, rather than moving a still image. */
(function(root){
function pose(time,moving,face,attack=0){const step=moving?Math.sin(time*11):0;return {step,bob:moving?Math.abs(Math.cos(time*11))*1.7:Math.sin(time*2.4)*.6,side:Math.abs(Math.cos(face))>.65,back:Math.sin(face)<-.55,flip:Math.cos(face)<-.2,swing:attack>0?Math.sin((1-attack/.36)*Math.PI):0};}
function path(c,points,fill,stroke='#18252b',width=1.3){c.beginPath();points.forEach(([x,y],i)=>i?c.lineTo(x,y):c.moveTo(x,y));c.closePath();c.fillStyle=fill;c.fill();if(stroke){c.strokeStyle=stroke;c.lineWidth=width;c.stroke()}}
function oval(c,x,y,rx,ry,fill){c.beginPath();c.ellipse(x,y,rx,ry,0,0,Math.PI*2);c.fillStyle=fill;c.fill()}
function limb(c,x,y,angle,length,color,width=6){c.save();c.translate(x,y);c.rotate(angle);c.lineCap='round';c.strokeStyle='#18252b';c.lineWidth=width+2;c.beginPath();c.moveTo(0,0);c.lineTo(0,length);c.stroke();c.strokeStyle=color;c.lineWidth=width;c.stroke();c.restore()}
function axe(c,x,y,angle){c.save();c.translate(x,y);c.rotate(angle);limb(c,0,-13,0,29,'#815537',3);path(c,[[0,-14],[12,-19],[15,-8],[10,-3],[0,-8]],'#adbfc2');path(c,[[12,-19],[15,-8],[10,-3],[8,-5],[11,-11]],'#edf0df',null);c.restore()}
function character(c,x,y,options){const {time,moving,face,attack=0,enemy=false,boss=false,hurt=0}=options,p=pose(time,moving,face,attack),scale=boss?1.6:1.15;
c.save();c.translate(Math.round(x),Math.round(y));oval(c,0,8,18*scale,6*scale,'#07161c55');c.scale(p.flip?-scale:scale,scale);c.translate(0,-p.bob);if(hurt>0)c.globalAlpha=.65+.35*Math.cos(hurt*40);
const blue=enemy?'#677a68':'#356889',light=enemy?'#9caa84':'#659ab0',skin=enemy?'#b5b8a3':'#e6b17b';
// Boots and legs have alternating footfalls, with knees visible beneath the tunic.
for(const [side,phase] of [[-1,1],[1,-1]]){const stride=p.step*phase;limb(c,side*5,0,stride*.34,11,'#584a3c',6);c.save();c.translate(side*5+stride*2,11-Math.max(0,stride)*3);c.rotate(stride*.12);path(c,[[-4,-4],[3,-4],[5,2],[4,5],[-5,5]],'#44372d');path(c,[[-3,-3],[3,-3],[4,-1],[-3,0]],'#b9a789',null);c.restore()}
// Cloak sways independently of feet.
path(c,[[-11,-24],[10,-24],[13+p.step*2,5],[-13+p.step*2,5]],p.back?'#486579':'#3d4752');
const arm=p.step*.23;limb(c,-11,-20,-.1+arm,17,blue,7);
path(c,[[-10,-24],[9,-24],[12,-5],[9,5],[-10,5],[-12,-6]],blue);path(c,[[-7,-21],[-1,-21],[-3,-2],[-8,1]],light,null);
path(c,[[-12,-24],[-8,-29],[-4,-27],[0,-29],[4,-27],[9,-28],[13,-23],[10,-18],[6,-20],[2,-18],[-3,-20],[-8,-18]],'#b8afa0');
path(c,[[-10,-3],[10,-3],[10,1],[-10,1]],'#64432f');oval(c,0,-1,2.5,2.5,'#d7b76d');
limb(c,11,-20,-arm-p.swing*1.5,17,blue,7);
// Head changes to a rear helmet when walking north.
oval(c,p.side?2:0,-32,p.side?7:8,10,skin);
if(!p.back){path(c,[[-7,-29],[-3,-27],[3,-28],[8,-30],[7,-22],[3,-17],[-3,-19],[-7,-23]],enemy?'#6b6555':'#ad542c');path(c,[[-4,-27],[0,-26],[4,-27],[2,-21],[-1,-20]],enemy?'#8c8169':'#d77f3c',null);oval(c,p.side?5:3,-33,1.1,1.3,'#182832');if(!p.side)oval(c,-3,-33,1.1,1.3,'#182832');}
path(c,[[-9,-34],[-8,-40],[-4,-45],[2,-46],[8,-41],[9,-34]],'#748991');path(c,[[-5,-40],[-2,-43],[0,-43],[-1,-35],[-6,-35]],'#b4c3c3',null);path(c,[[-9,-35],[9,-35],[9,-32],[-9,-32]],'#445661');path(c,[[-1,-45],[2,-45],[3,-32],[0,-32]],'#d4b777',null);
if(p.back){path(c,[[-7,-29],[8,-29],[9,-22],[4,-20],[-6,-22]],'#91502f');}
if(!p.back){c.save();c.translate(-13,-8);c.rotate(-.12+arm*.35);oval(c,0,0,8,12,'#baa16c');oval(c,0,0,6.2,10.2,'#376780');c.strokeStyle='#9bb4b8';c.lineWidth=1;c.beginPath();c.moveTo(0,-9);c.lineTo(0,9);c.stroke();oval(c,0,0,3,3,'#b8c6bf');c.restore();}
axe(c,13+Math.sin(p.swing*2)*13,-6-p.swing*16,-.2-p.swing*2);
if(attack>0){c.save();c.rotate(p.back?-Math.PI/2:face);c.strokeStyle=`rgba(252,222,155,${p.swing*.85})`;c.lineWidth=3;c.beginPath();c.arc(0,-12,38,-1.1+p.swing,1+p.swing);c.stroke();c.restore()}
c.restore();}
function tree(c,x,y,snow,time){c.save();c.translate(x+16,y+21);oval(c,5,12,23,8,'#071c2444');path(c,[[-4,-5],[5,-5],[7,15],[-5,15]],'#68503d');const sway=Math.sin(time*1.3+x*.17+y)*1.2;c.translate(sway,0);for(let i=0;i<3;i++){const top=-49+i*13,w=23-i*3;path(c,[[0,top],[-w,top+29],[-12,top+27],[-w+3,top+34],[w,top+31],[w-8,top+25]],snow?'#729999':'#254f40','#18362f');path(c,[[0,top+2],[-w+7,top+26],[-2,top+21],[w-7,top+27]],snow?'#d4e0db':'#427355',null)}c.restore()}
function ground(c,x,y,type,level,time){const n=(x*371+y*173)>>>0,base=level===0?['#344f39','#38583e','#3b5b40']:level===1?['#a4bbbe','#adc3c4','#a0b8bc']:['#494951','#4d4e55','#505058'];c.fillStyle=type===1?['#193c49','#315768','#302c3c'][level]:type===3?['#8c8162','#a6b2ad','#75665b'][level]:base[n%3];c.fillRect(x,y,32,32);
if(type===1){c.strokeStyle='#8cb9bb35';c.lineWidth=1;for(let i=0;i<2;i++){const shift=Math.sin(time*1.5+y+i)*5;c.beginPath();c.moveTo(x+3+shift,y+8+i*15);c.quadraticCurveTo(x+13+shift,y+5+i*15,x+23+shift,y+8+i*15);c.stroke()}return}
for(let i=0;i<8;i++){const px=x+(n+i*137)%31,py=y+((n>>3)+i*71)%31;c.fillStyle=type===3?'#c7bd9644':level===1?'#e8ede544':'#88a67444';c.fillRect(px,py,type===3?3:1,type===3?1:3)}if(type===0&&n%19===0){oval(c,x+14,y+20,3,1,'#182c3455');oval(c,x+13,y+17,2,3,level===1?'#d7e0dc':'#7c8b7e')}if(type===0&&level===0&&n%11===0){c.fillStyle='#b7ad7c';c.fillRect(x+20,y+18,2,2);c.fillStyle='#7c91ab';c.fillRect(x+23,y+24,2,2)}}
root.VikingArt={pose,character,tree,ground};if(typeof module!=='undefined')module.exports=root.VikingArt;
})(typeof window!=='undefined'?window:globalThis);
