import {useMemo} from 'react';
import {useSearchParams} from 'react-router-dom';
import type {Form} from './instrument';
import {Viewer,type MorphologySample} from './MorphologyLab';
export function LiveMorphology({form}:{form:Form}){
 const [params,setParams]=useSearchParams();const anatomical=params.get('view')==='anatomy';const m=form.morphology!;
 const displayId=form.id.match(/-n(\d+)$/)?.[1];
 const genome=useMemo(()=>form.genome,[form.hash]);
 const sample=useMemo<MorphologySample>(()=>({id:form.id,parent:form.parents[0],morphology_genome:m.morphology_genome,morphology_hash:m.morphology_hash,phenotype_hash:m.phenotype_hash,phenotype:m.phenotype,fuel:m.development_fuel,truncated:m.truncated}),[form.id,m.morphology_hash,m.phenotype_hash]);
 return <section className="live-morphology" aria-label={`Форма ${displayId?`№ ${displayId}`:form.id}`}><div className="morph-tabs" role="group" aria-label="Представление программы"><button aria-pressed={!anatomical} onClick={()=>setParams(p=>{const q=new URLSearchParams(p);q.set('view','appearance');return q;},{replace:true})}>Облик</button><button aria-pressed={anatomical} onClick={()=>setParams(p=>{const q=new URLSearchParams(p);q.set('view','anatomy');return q;},{replace:true})}>Анатомия</button></div><div className="live-form-title"><strong>{displayId?`Вариант № ${displayId}`:'Выбранная форма'}</strong><span>{anatomical?'Цветные группы стоят у тех же опорных точек формы, что и соответствующие части тела. Линии показывают реальные связи команд и памяти. Угол поворота общий для обоих видов.':'Это форма, созданная наследуемой программой развития. Вращайте и приближайте модель: тот же угол сохранится в анатомии.'}</span></div><Viewer sample={sample} anatomy={anatomical} genome={genome} live/></section>;
}
