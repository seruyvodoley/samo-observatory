import {OPS, type Genome} from './data';

export type GeometryPart='module'|'router'|'search'|'dialect'|'memory';
export type Vec3={x:number;y:number;z:number};
export type ComponentRef={part:GeometryPart;index:number;code:number[][];name:string;center:Vec3};
export type InstructionRef={part:GeometryPart;partIndex:number;index:number;opcode:number;argument:number;position:Vec3;shape:number;rotation:number};
export type MemoryRef={index:number;value:number;position:Vec3;scale:number};
export type GenomeGeometry={components:ComponentRef[];instructions:InstructionRef[];memory:MemoryRef[];orderEdges:[Vec3,Vec3][];branchEdges:[Vec3,Vec3][];dialectCalls:{from:Vec3;to:Vec3;dialect:number}[];possibleRoutes:[Vec3,Vec3][];instructionCount:number};

const GOLDEN=2.399963229728653;
const TAU=Math.PI*2;
const opName=(op:number)=>OPS[op]||'UNKNOWN';
const category=(op:number)=>op===0?0:op===1||op===2||op===16?1:op>=3&&op<=7?2:op>=8&&op<=10?3:op===11||op===12?4:op===13?5:op===14||op===15?6:7;
function hashUnit(text:string):number{let h=2166136261;for(let i=0;i<text.length;i++){h^=text.charCodeAt(i);h=Math.imul(h,16777619);}return (h>>>0)/4294967295;}
function add(a:Vec3,b:Vec3):Vec3{return{x:a.x+b.x,y:a.y+b.y,z:a.z+b.z};}
function moduleCenter(index:number,count:number):Vec3{
 const y=1-(2*(index+.5))/Math.max(1,count);const r=Math.sqrt(Math.max(0,1-y*y));const a=index*GOLDEN;
 return{x:Math.cos(a)*r*1.32,y:y*1.32,z:Math.sin(a)*r*1.32};
}
function componentCenter(part:GeometryPart,index:number,moduleCount:number):Vec3{
 if(part==='module')return moduleCenter(index,moduleCount);
 if(part==='router')return{x:0,y:0,z:-1.55};
 if(part==='search')return{x:0,y:0,z:1.55};
 if(part==='dialect'){
  const a=(index/4)*TAU-Math.PI/4;
  return{x:Math.cos(a)*1.55,y:.52+((index%2)*.24),z:Math.sin(a)*1.55};
 }
 return{x:0,y:-1.8,z:0};
}
function pointFor(center:Vec3,part:GeometryPart,partIndex:number,index:number,op:number,arg:number,length:number):Vec3{
 const col=index%12,row=Math.floor(index/12);const u=(col-5.5)/11;const v=(row-(Math.ceil(length/12)-1)/2)*.15;
 const angle=u*1.65;const r=.64+row*.018;
 return{x:center.x+Math.sin(angle)*r,y:center.y+v,z:center.z+(1-Math.cos(angle))*.46+((op%3)-1)*.035};
}
function jsModulo(n:number,m:number):number{return ((n%m)+m)%m;}

/** Stable, bounded layout. Every instruction and memory cell is present once. No random state. */
export function buildGenomeGeometry(genome:Genome):GenomeGeometry{
 const components:ComponentRef[]=[];
 genome.modules.forEach((code,index)=>components.push({part:'module',index,code,name:`Основная программа · модуль ${index+1}`,center:componentCenter('module',index,genome.modules.length)}));
 components.push({part:'router',index:0,code:genome.router,name:'Выбор модуля',center:componentCenter('router',0,genome.modules.length)});
 components.push({part:'search',index:0,code:genome.search,name:'Создание новых вариантов',center:componentCenter('search',0,genome.modules.length)});
 genome.dialect.forEach((code,index)=>components.push({part:'dialect',index,code,name:`Собственные правила команд · ${index+1}`,center:componentCenter('dialect',index,genome.modules.length)}));
 const instructions:InstructionRef[]=[],orderEdges:[Vec3,Vec3][]=[],branchEdges:[Vec3,Vec3][]=[],dialectCalls:{from:Vec3;to:Vec3;dialect:number}[]=[];
 let instructionCount=0;
 for(const c of components){
  c.code.forEach(([opcode,argument],index)=>{
   const point=pointFor(c.center,c.part,c.index,index,opcode,argument,c.code.length);
   instructions.push({part:c.part,partIndex:c.index,index,opcode,argument,position:point,shape:category(opcode),rotation:hashUnit(`${opcode}:${argument}:rotation`)*TAU});
   instructionCount++;
   if(index+1<c.code.length){const [nextOp,nextArg]=c.code[index+1];const next=pointFor(c.center,c.part,c.index,index+1,nextOp,nextArg,c.code.length);orderEdges.push([point,next]);}
   if(opcode===11||opcode===12){const target=jsModulo(argument,c.code.length+1);if(target<c.code.length&&target!==index+1){const [targetOp,targetArg]=c.code[target];branchEdges.push([point,pointFor(c.center,c.part,c.index,target,targetOp,targetArg,c.code.length)]);}}
   if(opcode===15&&genome.dialect.length){const dialect=jsModulo(argument,genome.dialect.length);dialectCalls.push({from:point,to:componentCenter('dialect',dialect,genome.modules.length),dialect});}
  });
 }
 const memory=genome.memory.map((value,index)=>{
  const row=Math.floor(index/8),col=index%8;
  return{index,value,position:{x:(col-3.5)*.22,y:-1.95-row*.19+(value/65535)*.14,z:.17*Math.sin(col*.55+row)},scale:.55+(.9*value/65535)};
 });
 const router=components.find(x=>x.part==='router')!;
 const routeCodeEnd=router.code.length?pointFor(router.center,'router',0,router.code.length-1,router.code.at(-1)![0],router.code.at(-1)![1],router.code.length):router.center;
 const possibleRoutes=genome.modules.map((_,index):[Vec3,Vec3]=>[routeCodeEnd,moduleCenter(index,genome.modules.length)]);
 return{components,instructions,memory,orderEdges,branchEdges,dialectCalls,possibleRoutes,instructionCount};
}

export function genomeSummary(g:Genome):string{
 const geometry=buildGenomeGeometry(g);
 const instructionsByPart=(part:GeometryPart)=>geometry.instructions.filter(x=>x.part===part).length;
 const count=(n:number,forms:[string,string,string])=>{const m=n%100,unit=n%10;return `${n} ${m>=11&&m<=14?forms[2]:unit===1?forms[0]:unit>=2&&unit<=4?forms[1]:forms[2]}`;};
 return `${count(g.modules.length,['модуль','модуля','модулей'])}; ${count(instructionsByPart('module'),['команда','команды','команд'])} в основной программе; ${count(instructionsByPart('search'),['команда','команды','команд'])} создания вариантов; ${count(instructionsByPart('dialect'),['команда','команды','команд'])} в собственном языке; ${count(instructionsByPart('router'),['команда','команды','команд'])} выбора; ${count(g.memory.length,['ячейка памяти','ячейки памяти','ячеек памяти'])}`;
}
export function describeInstruction(op:number,arg:number):string{
 const meanings:Record<string,string>={CONST:'взять число',HIST:'прочитать предыдущее число ряда',MEM:'прочитать ячейку памяти',ADD:'сложить два числа',SUB:'вычесть одно число из другого',MUL:'умножить два числа',XOR:'выполнить операцию с битами',MOD:'найти остаток от деления',DUP:'повторить число',DROP:'убрать число',SWAP:'поменять числа местами',JMP:'перейти к другой команде',JZ:'перейти, если число равно нулю',RAND:'получить случайное число',EMIT:'передать изменение программы',CALL:'выполнить собственное правило',LEN:'узнать длину ряда',STORE:'записать число в память',HALT:'завершить вычисление'};
 return `${meanings[opName(op)]||'команда'} · число ${arg}`;
}
