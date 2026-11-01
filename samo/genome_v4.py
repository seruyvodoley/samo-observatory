"""Heritable bytecode, search, dialect semantics, routing and active memory."""
import copy
import hashlib
import json
import time
from .vm_v4 import ins, validate_code, OPS, MAX_CODE, execute, Meter, Trap


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def ancestor():
    # Search emits four random fields per edit. Its bytecode, including loop structure,
    # is itself editable; the external edit ABI stays immutable.
    search = []
    for _ in range(2):
        for _ in range(4):
            search += [ins('RAND'), ins('EMIT')]
    return {'abi': 1, 'modules': [[ins('HIST')],
                                [ins('HIST'), ins('HIST'), ins('HIST', 1), ins('SUB'), ins('ADD')]],
            'router': [ins('CONST')], 'search': search,
            'dialect': [[ins('HIST')], [ins('HIST'), ins('CONST', 1), ins('ADD')],
                        [ins('LEN')], [ins('MEM')]], 'memory': [0] * 16}


def validate(g):
    if not isinstance(g, dict) or set(g) != {'abi', 'modules', 'router', 'search', 'dialect', 'memory'}:
        raise ValueError('genome fields')
    if type(g['abi']) is not int or g['abi'] != 1:
        raise ValueError('ABI')
    if not isinstance(g['modules'], list) or not 1 <= len(g['modules']) <= 8:
        raise ValueError('module limit')
    if not isinstance(g['dialect'], list) or len(g['dialect']) != 4:
        raise ValueError('dialect limit')
    for code in g['modules'] + g['dialect'] + [g['router'], g['search']]:
        validate_code(code)
    if not isinstance(g['memory'], list) or len(g['memory']) > 64:
        raise ValueError('memory limit')
    if any(type(x) is not int or not 0 <= x <= 65535 for x in g['memory']):
        raise ValueError('memory word')
    if len(canonical(g)) > 32768:
        raise ValueError('genome bytes')
    return g


# Version-4 edit and reproduction ABI lives exclusively in search_v4.

def recombine(a, b, rng):
    """Bounded, auditable single-point recombination over heritable components."""
    validate(a); validate(b)
    child = copy.deepcopy(a)
    changed = []
    for key in ('modules', 'router', 'search', 'dialect', 'memory'):
        if not rng.getrandbits(1):
            continue
        donor, own = b[key], child[key]
        if key in ('modules', 'dialect', 'memory'):
            if not donor:
                continue
            cut = rng.randrange(min(len(own), len(donor)) + 1)
            value = copy.deepcopy(own[:cut] + donor[cut:])
            if key == 'modules':
                value = (value[:8] or [copy.deepcopy(donor[0])])
            elif key == 'dialect':
                value = (value + copy.deepcopy(a[key]))[:4]
            else:
                value = value[:64]
        else:
            if not donor:
                continue
            cut = rng.randrange(min(len(own), len(donor)) + 1)
            value = copy.deepcopy(own[:cut] + donor[cut:])[:96]
        child[key] = value
        if value != a[key]:
            changed.append(key)
    validate(child)
    return child, changed


def predict(g, history, fuel=128, wall_seconds=0.25):
    meter = Meter(fuel, deadline=float('inf') if wall_seconds is None else time.monotonic()+wall_seconds)
    memory = list(g['memory'])
    try:
        route, _, memory = execute(g['router'], history, memory, g['dialect'], meter=meter)
        value, _, memory = execute(g['modules'][route % len(g['modules'])], history,
                                   memory, g['dialect'], meter=meter)
        return value, meter.used, None, memory
    except (Trap, ValueError) as e:
        return None, meter.used, str(e), memory
