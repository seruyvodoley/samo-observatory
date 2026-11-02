import {createContext,useContext,useEffect,useMemo,useState,useRef,startTransition,type ReactNode} from 'react';
import {useLocation,useSearchParams} from 'react-router-dom';
import type {Genome} from './data';
import {verifyMorphology,sha} from './morphology-data';
import {checkGenome,type Form} from './instrument';
import {VisitorInfo,VisitorViews} from './visitor';
export type EcoEvent={index:number;episode:number;kind:string;family:string;family_accuracy?:Record<string,number>;accepted?:boolean;accuracy?:number;changes?:string[];lifecycle:{kind:string;id?:string;reason?:string;source?:{kind:string}}[]};
export type Eco={schema:number;protocol:string;arm?:string;generated_at:string;observation:{observed_at:string;status:string;environment?:string;storage_fraction?:number};step:number;episode:number;attempts:number;births:number;deaths:number;recolonizations:number;fuel:number;population:Form[];events:EcoEvent[];retention:{pruned_records:number;root:string};history?:Form[];snapshot_id?:string;published_at?:string;long_term?:unknown;claims:unknown[];morphology?:{active_unique_forms:number;occupied_active_niches:number;bounded_archive_niches:number;morphology_births:number;morphology_changes:number;neutral_morphology_changes:number;phenotype_effects:number;sphere_returns:number;max_structural_retention_steps:number;morphology_fuel:number;morphology_cpu_ns:number};telemetry?:{morphology_changes?:number;morphology_effects?:number;morphology_neutral?:number;active_unique_forms?:number;occupied_active_niches?:number;sphere_returns?:number;unique_genomes:number;genotype_changes:number;behavior_changes:number;search_errors:number;stagnant_attempts:number;search_workability?:number;active_search_observations?:{population:number;tested:number;last_success:number;unknown:number};independent_accuracy:number|null};infrastructure?:{checked_at:string;organism:string;detail:string;technical_restarts:number|null};interventions?:{kind:string;at_attempt?:number;reason:string}[];episodes?:{episode:number;started_at:number;ended_at:number|null;reason:string;sources:{id:string;source:{kind:string;id?:string}}[]}[];episode_retention?:{pruned:number}};
function canonical(x:unknown):string{if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';if(x&&typeof x==='object')return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical((x as Record<string,unknown>)[k])).join(',')+'}';return JSON.stringify(x);}
function validate(x:unknown):Eco{
 if(!x||typeof x!=='object')throw Error('snapshot');const v=x as Eco;
 if((v.history&&(!Array.isArray(v.history)||v.history.length>160))||v.schema!==1||!['samo-ecology-v2','samo-ecology-v4','samo-ecology-v5-morphology','samo-ecology-v6-morphology'].includes(v.protocol)||!Number.isSafeInteger(v.step)||!Array.isArray(v.population)||v.population.length>8||!Array.isArray(v.events)||v.events.length>1024||!v.observation||!Number.isFinite(Date.parse(v.observation.observed_at))||!v.retention)throw Error('Несовместимая схема или протокол: пилот автоматически не подставляется');
 for(const x of [...v.population,...(v.history||[])])if(typeof x.id!=='string'||x.id.length>80||!x.id.length||typeof x.hash!=='string'||!(/^[a-f0-9]{64}$/).test(x.hash)||!Number.isSafeInteger(x.born)||x.born<0||!Array.isArray(x.parents)||x.parents.length>2||x.parents.some(p=>typeof p!=='string'||p.length>80))throw Error('Invalid program identity');
 if(new Set(v.population.map(x=>x.id)).size!==v.population.length)throw Error('Duplicate active identity');
 for(const e of v.events)if(!Number.isSafeInteger(e.index)||typeof e.kind!=='string'||!Array.isArray(e.lifecycle))throw Error('event');
 return v;
}
async function read(signal:AbortSignal,etag?:string){
 const headers:Record<string,string>={};if(etag)headers['If-None-Match']=etag;
 const r=await fetch('/data/ecosystem.json',{signal,credentials:'omit',cache:'no-store',headers});if(r.status===304)return null;if(!r.ok)throw Error('unavailable');
 const reader=r.body?.getReader();if(!reader)throw Error('empty');let size=0;const chunks:Uint8Array[]=[];
 while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>4_000_000){await reader.cancel();throw Error('size');}chunks.push(value);}
 const all=new Uint8Array(size);let at=0;for(const c of chunks){all.set(c,at);at+=c.length;}const data=validate(JSON.parse(new TextDecoder().decode(all)));const identities=new Map<string,string>();for(const x of [...data.population,...(data.history||[])]){checkGenome(x.genome);if(identities.has(x.id)&&identities.get(x.id)!==x.hash)throw Error('ID/hash conflict');identities.set(x.id,x.hash);const h=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(x.genome)));const hex=[...new Uint8Array(h)].map(v=>v.toString(16).padStart(2,'0')).join('');if(hex!==x.hash)throw Error('Хеш отображаемого генома не совпадает с данными');if(data.protocol.startsWith('samo-ecology-v5-')||data.protocol==='samo-ecology-v6-morphology'){if(!x.morphology)throw Error('Нет наследуемой формы');}if(x.morphology){await verifyMorphology(x.morphology,x.genome);if(await sha(canonical([x.hash,x.morphology.morphology_hash,x.morphology.interpreter]))!==x.identity_hash)throw Error('Идентичность формы не совпадает');}}return {data,etag:r.headers.get('ETag')||undefined};
}
const sessionForms=new Map<string,Form>();
let sessionProtocol="";
type EcologyState={data:Eco|null;unavailable:boolean;issue:string;forms:Form[];lineage:Form[]};
const EcologyContext=createContext<EcologyState|null>(null);
export function EcologyProvider({children}:{children:ReactNode}){
 const [data,setData]=useState<Eco|null>(null),[unavailable,setUnavailable]=useState(false),[issue,setIssue]=useState(''),[cache,setCache]=useState<Form[]>(()=>[...sessionForms.values()]);const known=useRef(new Map<string,string>());
 useEffect(()=>{const controller=new AbortController();let busy=false,etag:string|undefined;const update=async()=>{if(busy||document.hidden)return;busy=true;try{const result=await read(controller.signal,etag);if(result){etag=result.etag;const fresh=result.data;const protocolChanged=sessionProtocol!==fresh.protocol;if(protocolChanged){sessionProtocol=fresh.protocol;sessionForms.clear();known.current.clear();}for(const x of [...fresh.population,...(fresh.history||[])]){if(known.current.has(x.id)&&known.current.get(x.id)!==(x.identity_hash||x.hash))throw Error('ID/genome conflict');known.current.set(x.id,x.identity_hash||x.hash);}while(known.current.size>2048)known.current.delete(known.current.keys().next().value!);startTransition(()=>{setData(old=>old&&old.protocol===fresh.protocol&&old.step>fresh.step?old:fresh);for(const x of [...(fresh.history||[]),...fresh.population])sessionForms.set(x.id,x);while(sessionForms.size>160)sessionForms.delete(sessionForms.keys().next().value!);setCache(old=>{const map=new Map([...(protocolChanged?[]:old),...(fresh.history||[]),...fresh.population].map(x=>[x.id,x]));return [...map.values()].slice(-160)});});}setUnavailable(false);setIssue('');}catch(e){if(!controller.signal.aborted){setUnavailable(true);setIssue(e instanceof Error?e.message:'ошибка');}}finally{busy=false;}};void update();const timer=setInterval(update,15000);document.addEventListener('visibilitychange',update);window.addEventListener('focus',update);window.addEventListener('pageshow',update);return()=>{document.removeEventListener('visibilitychange',update);window.removeEventListener('focus',update);window.removeEventListener('pageshow',update);controller.abort();clearInterval(timer);};},[]);
 const forms=useMemo(()=>[...new Map([...cache,...(data?.history||[]),...(data?.population||[])].map(x=>[x.id,x])).values()], [cache,data]);
 const lineage=useMemo(()=>[...new Map([...(data?.history||[]),...(data?.population||[])].map(x=>[x.id,x])).values()], [data]);
 return <EcologyContext.Provider value={{data,unavailable,issue,forms,lineage}}>{children}</EcologyContext.Provider>;
}
export function useEcology(){const value=useContext(EcologyContext);if(!value)throw new Error('EcologyProvider is missing');return value;}
// The landing view represents a current participant; archive views may retain historical forms.
// Share this rule with WebGL so the label and the dominant model can never diverge.
export function selectObservedForm(data:Eco|null,forms:Form[],requested:string|null|undefined,route:string):Form|undefined{
 const active=[...(data?.population||[])].sort((a,b)=>b.born-a.born||b.id.localeCompare(a.id));
 // The Life page is a live view, never a bookmark to an individual organism.
 // Ignore legacy ?eco= links there so a dead/archived form cannot blank the scene.
 if(route==='/')return active[0];
 if(requested)return forms.find(x=>x.id===requested);
 return active[0]||forms.at(-1);
}
export function Ecosystem(){
 const {data,unavailable,issue,forms}=useEcology();const location=useLocation();const [params,setParams]=useSearchParams();
 const route=location.pathname.startsWith('/organism/')?'/organism':location.pathname.startsWith('/lab/')?'/lab':location.pathname;
 const routeId=location.pathname.match(/^\/organism\/([^/]+)$/)?.[1];const requested=route==='/'?null:(params.get('eco')||routeId);const selected=selectObservedForm(data,forms,requested,route);
 useEffect(()=>{if(route==='/'&&params.has('eco')){const next=new URLSearchParams(params);next.delete('eco');setParams(next,{replace:true});}},[route,params,setParams]);
 if(!data){if(route==='/about'||route==='/science')return <VisitorInfo page={route.slice(1) as 'about'|'science'}/>;return <section className="visitor atlas-loading"><p className="eyebrow">САМО · обсерватория</p><h1 tabIndex={-1}>{unavailable?'Снимок пока недоступен':'Загружаем последнее наблюдение'}</h1><p role={unavailable?'alert':'status'}>{unavailable?'Не удалось загрузить или проверить актуальный снимок. Здесь не подставляются данные из старого пилота.':'Проверяем сохранённый геном и подпись его контрольной суммы.'}</p>{unavailable&&<><button className="atlas-button" onClick={()=>window.location.reload()}>Попробовать ещё раз</button><details><summary>Причина для исследователей</summary><p>{issue}</p></details></>}</section>;}
 const stale=unavailable||Date.now()-Date.parse(data.observation.observed_at)>300000;
 return <VisitorViews data={data} route={route} forms={forms} selected={selected} requestedId={requested} stale={stale} issue={issue} onSelect={id=>{const next=new URLSearchParams(params);next.set('eco',id);setParams(next)}}/>;
}
