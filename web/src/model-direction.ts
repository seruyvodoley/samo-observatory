export type ModelDirection=[number,number,number];
const KEY='samo-model-direction-v1';
const EVENT='samo:model-direction';
const BASE:ModelDirection=[.501,.251,.828];
let direction:ModelDirection=load();
let persistTimer=0;
function normalize(value:unknown):ModelDirection|null{
 if(!Array.isArray(value)||value.length!==3||value.some(x=>typeof x!=='number'||!Number.isFinite(x)))return null;
 const [x,y,z]=value as number[],length=Math.hypot(x,y,z);return length<1e-6?null:[x/length,y/length,z/length];
}
function load():ModelDirection{
 try{return normalize(JSON.parse(sessionStorage.getItem(KEY)||'null'))||BASE;}catch{return BASE;}
}
export function getModelDirection():ModelDirection{return [...direction] as ModelDirection;}
export function setModelDirection(value:unknown,source:string){
 const next=normalize(value);if(!next)return;direction=next;
 window.dispatchEvent(new CustomEvent(EVENT,{detail:{direction:[...next],source}}));
 if(persistTimer)window.clearTimeout(persistTimer);
 persistTimer=window.setTimeout(()=>{try{sessionStorage.setItem(KEY,JSON.stringify(direction));}catch{}persistTimer=0;},160);
}
export function modelDirectionEvent():string{return EVENT;}
