const {test}=require('node:test');
const assert=require('node:assert/strict');
const {pose}=require('../static/viking/renderer.js');
test('walking alternates leg positions; idle does not walk',()=>{
 const a=pose(Math.PI/22,true,0),b=pose(3*Math.PI/22,true,0);
 assert.ok(a.step>.99);assert.ok(b.step<-.99);
 assert.equal(pose(1,false,0).step,0);
 assert.notEqual(pose(0,false,0).bob,pose(1,false,0).bob);
});
test('direction and axe swing have distinct animation poses',()=>{
 assert.equal(pose(0,false,-Math.PI/2).back,true);
 assert.equal(pose(0,false,Math.PI/2).back,false);
 assert.equal(pose(0,false,Math.PI).flip,true);
 assert.equal(pose(0,false,0).side,true);
 assert.equal(pose(0,false,0,0).swing,0);
 assert.ok(pose(0,false,0,.18).swing>.99);
 assert.ok(pose(0,false,0,.36).swing<.01);
});
