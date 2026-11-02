"""Bounded mutation diversity diagnostic, not population telemetry."""
import random,json,collections
from pathlib import Path
from samo.search_v4 import founder,edit
from samo.genome_v4 import digest
rng=random.Random(88431);g=founder();targets=collections.Counter();kinds=collections.Counter();opcodes=collections.Counter();changes=collections.Counter();hashes=set();noop=0
for _ in range(3000):
 words=[rng.randrange(65536) for _ in range(5)];targets[words[0]%6]+=1;kinds[words[2]%3]+=1;opcodes[words[3]%19]+=1;c=edit(g,words);hashes.add(digest(c));noop+=c==g
 for k in ('modules','router','search','dialect','memory'):changes[k]+=c[k]!=g[k]
result=dict(samples=3000,target_counts=dict(targets),kind_counts=dict(kinds),opcode_counts=dict(opcodes),changed_fields=dict(changes),distinct_genotypes=len(hashes),noops=noop,notes='Uniform emitted words, one generic edit from the same founder. Boundaries and empty components cause honest no-ops; this is not a scientific discovery test. Architecture operation at minimum module count can grow the structure rather than produce an invalid empty architecture.')
Path('output/core-v4/mutation-distribution.json').write_text(json.dumps(result,indent=2));print(result)
