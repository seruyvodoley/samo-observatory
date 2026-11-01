"""Trusted task generation and prequential commit/reveal evaluation.

Only prefixes cross predict()'s boundary. Seeds and generators never enter the VM.
"""
import copy
import hashlib
import random
import time
from collections import defaultdict
from .genome import digest, predict

VERSION = 'prequential-1'
FAMILIES = ('constant', 'arithmetic', 'periodic', 'recurrence', 'switch', 'random')
TRANSFER = ('quadratic', 'xor')


def sequence(family, rng, length=24):
    a, b = rng.randrange(256), rng.randrange(1, 16)
    if family == 'constant':
        return [a] * length
    if family == 'arithmetic':
        return [(a + b * i) % 65536 for i in range(length)]
    if family == 'periodic':
        p = [rng.randrange(256) for _ in range(rng.randrange(2, 6))]
        return [p[i % len(p)] for i in range(length)]
    if family == 'quadratic':
        return [(a + b * i * i) % 65536 for i in range(length)]
    if family == 'switch':
        return [(a + b * i if i < 17 else a - b * i) % 65536 for i in range(length)]
    if family == 'random':
        return [rng.randrange(65536) for _ in range(length)]
    result = [a, b]
    for _ in range(length - 2):
        result.append(((result[-1] ^ result[-2]) if family == 'xor'
                       else result[-1] + result[-2]) % 65536)
    return result


def tasks(seed, families=FAMILIES, repeats=2):
    rng = random.Random(seed)
    return [(f'{family}-{n}', family, sequence(family, rng))
            for family in families for n in range(repeats)]


def task_stream(master_seed, index, families=FAMILIES, repeats=1):
    """Counter-based deterministic task arrivals with no terminal index."""
    if type(index) is not int or index < 0:
        raise ValueError('task stream index')
    material = f'samo-task-stream-v1:{master_seed}:{index}'.encode()
    seed = int.from_bytes(hashlib.sha256(material).digest()[:8], 'big')
    return seed, tasks(seed, families, repeats)


def strong_baseline(h):
    # Frozen rule-based expert: period matching, second differences, recurrence.
    for p in range(1, min(7, len(h) // 2) + 1):
        if all(h[i] == h[i-p] for i in range(p, len(h))):
            return h[-p]
    if len(h) >= 6:
        if all(h[i] == (h[i-1] + h[i-2]) % 65536 for i in range(2, len(h))):
            return (h[-1] + h[-2]) % 65536
        if all(h[i] == (h[i-1] ^ h[i-2]) for i in range(2, len(h))):
            return h[-1] ^ h[-2]
        ds = [(h[i] - h[i-1]) % 65536 for i in range(1, len(h))]
        dds = [(ds[i] - ds[i-1]) % 65536 for i in range(1, len(ds))]
        if len(set(dds)) == 1:
            return (h[-1] + ds[-1] + dds[-1]) % 65536
    return h[-1]


def evaluate(genome, task_list, split, fuel_limit=10**9, raw=True, baseline=None, deterministic=False):
    total = correct = fuel = failures = 0
    error = 0.0
    rows = []
    per_family = defaultdict(lambda: [0, 0])
    behavior = []
    started = time.process_time()
    for task_id, family, values in task_list:
        local = copy.deepcopy(genome)
        for index in range(12, len(values)):
            if fuel >= fuel_limit:
                return {'accuracy': correct / total if total else 0, 'mae': error / max(total, 1),
                        'fuel': fuel, 'total': total, 'failures': failures,
                        'status': 'budget', 'rows': rows, 'families': {},
                        'behavior_hash': digest(behavior), 'cpu_seconds': time.process_time() - started}
            history = values[:index]
            if baseline:
                prediction = strong_baseline(history) if baseline == 'expert' else history[-1]
                used, status = 1, None  # Python cost is measured separately; not VM-fuel equivalent.
            else:
                prediction, used, status, memory = predict(local, history, min(128, fuel_limit - fuel), wall_seconds=None if deterministic else 0.25)
                local['memory'] = memory
            fuel += used
            # Commit before accessing values[index]. A replay checker verifies each commitment.
            commitment = digest({'task_id': task_id, 'index': index,
                                 'prediction': prediction, 'prefix_hash': digest(history)})
            target = values[index]
            hit = prediction is not None and prediction == target
            total += 1
            correct += int(hit)
            failures += int(status is not None)
            error += abs(prediction - target) / 65535 if prediction is not None else 1
            per_family[family][0] += int(hit)
            per_family[family][1] += 1
            behavior.append(prediction)
            if raw:
                rows.append({'task_id': task_id, 'family': family, 'split': split,
                             'index': index, 'prediction': prediction, 'target': target,
                             'prefix': history, 'commitment': commitment,
                             'correct': hit, 'status': status or 'ok', 'fuel': used})
    return {'accuracy': correct / max(total, 1), 'mae': error / max(total, 1),
            'fuel': fuel, 'total': total, 'failures': failures, 'status': 'ok',
            'rows': rows, 'families': {k: v[0] / v[1] for k, v in per_family.items()},
            'behavior_hash': digest(behavior), 'cpu_seconds': time.process_time() - started}
