export type Code = [number, number][];
export interface Genome { abi:number; modules:Code[]; router:Code; search:Code; dialect:Code[]; memory:number[] }
export interface Score { accuracy:number; mae:number; fuel:number; total:number; failures:number; status:string; families:Record<string,number>; behavior_hash:string; cpu_seconds:number; evidence_id?:string }
export interface Run { id:string; seed:number; condition:string; protocol_id:string; protocol_hash:string; source_hash:string; started_at:string; observed_at:string; status:string; fuel_ceiling:number; fuel:number; attempts:number; accepted:number; regressions:number; active_id:string|null; active_hash:string; best_accuracy:number; latest_score:Score|null; confirm?:Score; transfer?:Score; validation?:Score; baselines?:Record<string,Score>; cpu_seconds?:number; wall_seconds?:number; peak_rss_bytes?:number }
export interface Event { id:string; run_id:string; ordinal:number; generation:number; parent_ids:string[]; observed_at:string; snapshot_hash:string; runtime_hash:string; search_hash:string; memory_hash:string; operator_hash:string; changes:string[]; accepted:boolean; status:string; search_fuel:number; score:Score; evidence_id:string; protocol_hash:string }
export interface Evidence { id:string; run_id:string; snapshot_hash:string; protocol_hash:string; split:string; evaluator_version:string; result:Score }
export interface Snapshot { schema_version:number; generated_at:string; latest_observation_at:string|null; snapshot_hash:string; source_status:string; archive_complete:boolean; truncated:boolean; runs:Run[]; events:Event[]; artifacts:Record<string,Genome>; evidence:Evidence[]; claims:unknown[]; protocols:Record<string,unknown>[]; budget:{cpu_fraction:number;memory_bytes:number;organism_storage_bytes:number;archive_bytes:number;os_enforced:boolean}; limitations:string[] }

const hash = /^[a-f0-9]{64}$/;
function object(v:unknown):v is Record<string,unknown> { return typeof v==='object' && v!==null && !Array.isArray(v); }
function score(v:unknown):boolean { return object(v) && typeof v.accuracy==='number' && v.accuracy>=0 && v.accuracy<=1 && typeof v.fuel==='number' && Number.isFinite(v.fuel) && typeof v.failures==='number' && object(v.families); }
function code(v:unknown):boolean { return Array.isArray(v) && v.length<=96 && v.every(i=>Array.isArray(i)&&i.length===2&&Number.isInteger(i[0])&&i[0]>=0&&i[0]<19&&Number.isInteger(i[1])&&Math.abs(i[1])<=65535); }
export function validateSnapshot(v:unknown):Snapshot {
  if (!object(v)||v.schema_version!==1||!Array.isArray(v.runs)||v.runs.length>200||!Array.isArray(v.events)||v.events.length>2000||!object(v.artifacts)||!Array.isArray(v.evidence)||v.evidence.length>2500||!Array.isArray(v.protocols)||!object(v.budget)||typeof v.snapshot_hash!=='string'||!hash.test(v.snapshot_hash)||typeof v.generated_at!=='string'||!['empty','stopped','running'].includes(String(v.source_status))) throw Error('Неподдерживаемая схема снимка');
  const ids = new Set<string>(); const runIds=new Set<string>();
  for(const r of v.runs) { if(!object(r)||typeof r.id!=='string'||typeof r.seed!=='number'||typeof r.condition!=='string'||!['fixed','random','gp','meta','samo'].includes(r.condition)||typeof r.active_hash!=='string'||!hash.test(r.active_hash)||typeof r.status!=='string'||!score(r.latest_score)||typeof r.best_accuracy!=='number'||typeof r.fuel!=='number'||typeof r.fuel_ceiling!=='number'||typeof r.observed_at!=='string'||!Number.isFinite(Date.parse(r.observed_at))||runIds.has(r.id))throw Error('Повреждён запуск'); runIds.add(r.id); for(const s of ['confirm','transfer','validation'])if(r[s]!==undefined&&!score(r[s]))throw Error('Повреждено измерение'); }
  for(const e of v.events) { if(!object(e)||typeof e.id!=='string'||ids.has(e.id)||typeof e.run_id!=='string'||!runIds.has(e.run_id)||typeof e.snapshot_hash!=='string'||!hash.test(e.snapshot_hash)||!Array.isArray(e.parent_ids)||e.parent_ids.some(p=>typeof p!=='string'||!ids.has(p))||!Array.isArray(e.changes)||e.changes.some(c=>typeof c!=='string'||c.length>100)||typeof e.accepted!=='boolean'||!score(e.score)||typeof e.evidence_id!=='string'||!Number.isInteger(e.ordinal)||!Number.isInteger(e.generation))throw Error('Повреждена родословная'); ids.add(e.id); }
  for(const [key,g] of Object.entries(v.artifacts)){if(!hash.test(key)||!object(g)||g.abi!==1||!Array.isArray(g.modules)||g.modules.length<1||g.modules.length>8||!g.modules.every(code)||!code(g.router)||!code(g.search)||!Array.isArray(g.dialect)||g.dialect.length!==4||!g.dialect.every(code)||!Array.isArray(g.memory)||g.memory.length>64||g.memory.some(x=>!Number.isInteger(x)||x<0||x>65535))throw Error('Повреждён артефакт');}
  for(const r of v.runs) if(!v.artifacts[r.active_hash as string])throw Error('Нет активного артефакта');
  for(const e of v.events) if(!v.artifacts[e.snapshot_hash as string])throw Error('Нет артефакта события');
  for(const e of v.evidence)if(!object(e)||typeof e.id!=='string'||typeof e.run_id!=='string'||!runIds.has(e.run_id)||typeof e.split!=='string'||!score(e.result))throw Error('Повреждено доказательство');
  return v as unknown as Snapshot;
}
export async function loadSnapshot(signal:AbortSignal):Promise<Snapshot>{
  const response=await fetch('/data/snapshot.json',{signal,credentials:'omit'});
  if(!response.ok)throw Error(`Архив недоступен (HTTP ${response.status}). Попробуйте обновить страницу.`);
  const reader=response.body?.getReader(); if(!reader)throw Error('Пустой ответ архива');
  const chunks:Uint8Array[]=[]; let size=0;
  while(true){const {value,done}=await reader.read();if(done)break;size+=value.byteLength;if(size>4_000_000){await reader.cancel();throw Error('Архив превышает допустимый размер');}chunks.push(value);}
  const buffer=new Uint8Array(size);let offset=0;for(const c of chunks){buffer.set(c,offset);offset+=c.length;}
  return validateSnapshot(JSON.parse(new TextDecoder().decode(buffer)));
}
export const OPS=['CONST','HIST','MEM','ADD','SUB','MUL','XOR','MOD','DUP','DROP','SWAP','JMP','JZ','RAND','EMIT','CALL','LEN','STORE','HALT'];
