import type {Form} from './instrument';

export type LineageState='active'|'ancestor'|'displaced'|'ended'|'unknown'|'rejected';

export const LINEAGE_COLORS:Record<LineageState,number>={
 active:0x43b7a3,
 ancestor:0x83b68a,
 displaced:0xd5aa65,
 ended:0xdc806e,
 unknown:0x83939a,
 rejected:0x929397
};

export const LINEAGE_LABELS:Record<LineageState,string>={
 active:'Участвует сейчас',
 ancestor:'Принятая форма, есть потомки',
 displaced:'Выбыл, потомки видны',
 ended:'Эпизод закончился вымиранием',
 unknown:'Продолжение не видно в срезе',
 rejected:'Кандидат не принят'
};

export function lineageStates(forms:Form[],activeForms:Form[],events:{lifecycle:{kind:string;id?:string}[]}[],episodes:{episode:number;reason:string;ended_at:number|null}[]=[]):Map<string,LineageState>{
 const active=new Set(activeForms.map(form=>form.id));
 const children=new Set(forms.flatMap(form=>form.parents));
 const died=new Set(events.flatMap(event=>event.lifecycle.filter(item=>item.kind==='death'&&item.id).map(item=>item.id!)));
 const extinctEpisodes=new Set(episodes.filter(episode=>episode.ended_at!==null&&episode.reason==='extinction').map(episode=>episode.episode));
 return new Map(forms.map(form=>{
  const hasChildren=children.has(form.id),hasDied=died.has(form.id);
  const match=form.id.match(/-e(\d+)-/),episodeEnded=!!match&&extinctEpisodes.has(Number(match[1]));
  const state:LineageState=form.accepted===false?'rejected':active.has(form.id)?'active':hasDied&&hasChildren?'displaced':hasChildren?'ancestor':episodeEnded?'ended':'unknown';
  return [form.id,state];
 }));
}
