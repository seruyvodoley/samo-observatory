import type {Genome} from './data';
export type MorphologyNode={id:string;binding:string;position:number[];scale:number;shape:number;material:number;decorative:boolean};
export type Phenotype={version:string;nodes:MorphologyNode[];edges:string[][]};
export type Morphology={interpreter:string;morphology_genome:unknown;morphology_hash:string;phenotype_hash:string;phenotype:Phenotype;phenotype_payload:string;phenotype_payload_hash:string;development_fuel:number;truncated:boolean;descriptor?:Record<string,number>;niche?:number[]};
export function canonical(x:unknown):string{if(Array.isArray(x))return '['+x.map(canonical).join(',')+']';if(x&&typeof x==='object')return '{'+Object.keys(x).sort().map(k=>JSON.stringify(k)+':'+canonical((x as Record<string,unknown>)[k])).join(',')+'}';return JSON.stringify(x);}
export async function sha(raw:string){const h=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(raw));return [...new Uint8Array(h)].map(x=>x.toString(16).padStart(2,'0')).join('');}
export async function verifyMorphology(m:Morphology,g:Genome){
 if(!m||!['samo-morphogenesis-1','samo-morphogenesis-2','samo-morphogenesis-3'].includes(m.interpreter)||typeof m.phenotype_payload!=='string'||m.phenotype_payload.length>300000||!/^[a-f0-9]{64}$/.test(m.phenotype_hash))throw Error('Неподдерживаемая морфология');
 if(await sha(canonical(m.morphology_genome))!==m.morphology_hash||await sha(m.phenotype_payload)!==m.phenotype_payload_hash)throw Error('Контрольная сумма формы не совпадает');
 const p=JSON.parse(m.phenotype_payload) as Phenotype;
 if(p.version!==m.interpreter||!Array.isArray(p.nodes)||p.nodes.length>256||!Array.isArray(p.edges)||p.edges.length>1024)throw Error('Лимит геометрии');
 const expected=new Set([...g.modules.map((_,i)=>`module:${i}`),'router:0','search:0',...g.dialect.map((_,i)=>`dialect:${i}`),'memory:0']);const anchors=new Set<string>();const ids=new Set<string>();
 for(const n of p.nodes){if(typeof n.id!=='string'||n.id.length>512||ids.has(n.id)||!expected.has(n.binding)||!Array.isArray(n.position)||n.position.length!==3||n.position.some(x=>!Number.isFinite(x)||Math.abs(x)>32)||!Number.isFinite(n.scale)||n.scale<.05||n.scale>3||!Number.isInteger(n.shape)||n.shape<0||n.shape>3||!Number.isFinite(n.material)||n.material<0||n.material>=360||typeof n.decorative!=='boolean')throw Error('Невалидный узел формы');ids.add(n.id);if(!n.decorative){if(anchors.has(n.binding))throw Error('Повтор компонента');anchors.add(n.binding);}}
 if(anchors.size!==expected.size||p.edges.some(e=>!Array.isArray(e)||e.length!==2||e.some(x=>!ids.has(x))))throw Error('Потеря компонента или связи');m.phenotype=p;
}
