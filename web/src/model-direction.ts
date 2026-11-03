export type ModelDirection=[number,number,number];
const KEY='samo-model-direction-v1';
const EVENT='samo:model-direction';
const BASE:ModelDirection=[.501,.251,.828];
let direction:ModelDirection=load();
let persistTimer=0;
let idleFrame=0;
let idleClients=0;
let lastFrame=0;
let lastManualChange=0;
let lastPersist=0;
const IDLE_SOURCE='samo-idle-rotation';
const IDLE_PAUSE_MS=2200;
const IDLE_TURN_MS=240000;
function normalize(value:unknown):ModelDirection|null{
 if(!Array.isArray(value)||value.length!==3||value.some(x=>typeof x!=='number'||!Number.isFinite(x)))return null;
 const [x,y,z]=value as number[],length=Math.hypot(x,y,z);return length<1e-6?null:[x/length,y/length,z/length];
}
function load():ModelDirection{
 try{return normalize(JSON.parse(sessionStorage.getItem(KEY)||'null'))||BASE;}catch{return BASE;}
}
export function getModelDirection():ModelDirection{return [...direction] as ModelDirection;}
function publish(next:ModelDirection,source:string,manual:boolean){
 direction=next;
 window.dispatchEvent(new CustomEvent(EVENT,{detail:{direction:[...next],source}}));
 if(manual)lastManualChange=performance.now();
 const now=performance.now();
 if(manual&&persistTimer){window.clearTimeout(persistTimer);persistTimer=0;}
 if(!persistTimer&&(manual||now-lastPersist>700)){
  persistTimer=window.setTimeout(()=>{try{sessionStorage.setItem(KEY,JSON.stringify(direction));lastPersist=performance.now();}catch{}persistTimer=0;},manual?180:700);
 }
}
export function setModelDirection(value:unknown,source:string){
 const next=normalize(value);if(!next)return;
 publish(next,source,true);
}
export function modelDirectionEvent():string{return EVENT;}
function rotateDirection(value:ModelDirection,radians:number):ModelDirection{
 const c=Math.cos(radians),s=Math.sin(radians),[x,y,z]=value;
 return normalize([x*c+z*s,y,-x*s+z*c])||value;
}
function animateIdle(now:number){
 idleFrame=0;
 if(!idleClients)return;
 const canMove=document.visibilityState==='visible'&&!matchMedia('(prefers-reduced-motion: reduce)').matches&&now-lastManualChange>=IDLE_PAUSE_MS;
 if(!canMove)lastFrame=now;
 else if(!lastFrame)lastFrame=now;
 else if(now-lastFrame>=32){const elapsed=Math.min(now-lastFrame,100);publish(rotateDirection(direction,elapsed/IDLE_TURN_MS*Math.PI*2),IDLE_SOURCE,false);lastFrame=now;}
 idleFrame=requestAnimationFrame(animateIdle);
}
export function startModelIdleRotation():()=>void{
 idleClients++;
 if(!idleFrame){lastFrame=0;idleFrame=requestAnimationFrame(animateIdle);}
 let active=true;
 return()=>{if(!active)return;active=false;idleClients=Math.max(0,idleClients-1);if(!idleClients&&idleFrame){cancelAnimationFrame(idleFrame);idleFrame=0;lastFrame=0;}};
}
