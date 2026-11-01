"""Capability-free 16-bit VM. Every instruction, including dialect calls, shares fuel."""
import time
from dataclasses import dataclass, field
from typing import List, Optional

OPS = ('CONST', 'HIST', 'MEM', 'ADD', 'SUB', 'MUL', 'XOR', 'MOD', 'DUP',
       'DROP', 'SWAP', 'JMP', 'JZ', 'RAND', 'EMIT', 'CALL', 'LEN', 'STORE', 'HALT')
MAX_CODE = 96
MASK = 65535


class Trap(Exception):
    pass


@dataclass
class Meter:
    remaining: int
    deadline: float = field(default_factory=lambda: time.monotonic() + 0.25)
    used: int = 0

    def tick(self):
        if self.remaining <= 0:
            raise Trap('fuel')
        self.remaining -= 1
        self.used += 1
        if self.used % 32 == 0 and time.monotonic() > self.deadline:
            raise Trap('deadline')


def validate_code(code):
    if not isinstance(code, list) or len(code) > MAX_CODE:
        raise ValueError('invalid code length')
    for ins in code:
        if not isinstance(ins, list) or len(ins) != 2:
            raise ValueError('instruction must be [opcode, integer]')
        if type(ins[0]) is not int or not 0 <= ins[0] < len(OPS):
            raise ValueError('invalid opcode')
        if type(ins[1]) is not int or not -65535 <= ins[1] <= 65535:
            raise ValueError('invalid operand')


def execute(code, history=(), memory=None, dialect=(), rng=None,
            meter=None, initial=(), semantic=False):
    """No host objects are exposed. Return stack top, bounded emissions, local memory."""
    validate_code(code)
    if len(history) > 256 or len(initial) > 128:
        raise Trap('input limit')
    if any(type(x) is not int for x in history):
        raise Trap('noninteger input')
    mem = list([0] * 16 if memory is None else memory)
    if len(mem) > 64 or any(type(x) is not int for x in mem):
        raise Trap('memory limit')
    stack = [x & MASK for x in initial]
    out = []
    meter = meter or Meter(128)
    pc = 0

    def pop():
        if not stack:
            raise Trap('stack underflow')
        return stack.pop()

    while 0 <= pc < len(code):
        meter.tick()
        op, arg = code[pc]
        pc += 1
        if op == 0:
            stack.append(arg & MASK)
        elif op == 1:
            index = pop() if arg < 0 else arg
            stack.append(history[-1 - (index % len(history))] if history else 0)
        elif op == 2:
            index = pop() if arg < 0 else arg
            stack.append(mem[index % len(mem)] if mem else 0)
        elif op in (3, 4, 5, 6, 7):
            b, a = pop(), pop()
            if op == 3: value = a + b
            elif op == 4: value = a - b
            elif op == 5: value = a * b
            elif op == 6: value = a ^ b
            else: value = a % b if b else 0
            stack.append(value & MASK)
        elif op == 8:
            a = pop()
            stack.extend((a, a))
        elif op == 9:
            pop()
        elif op == 10:
            b, a = pop(), pop()
            stack.extend((b, a))
        elif op == 11:
            pc = arg % (len(code) + 1)
        elif op == 12:
            if pop() == 0:
                pc = arg % (len(code) + 1)
        elif op == 13:
            if rng is None:
                raise Trap('random capability absent')
            stack.append(rng.randrange(65536))
        elif op == 14:
            if len(out) >= 64:
                raise Trap('output limit')
            out.append(pop())
        elif op == 15:
            if semantic or not dialect:
                raise Trap('nested or absent dialect')
            value, _, mem = execute(dialect[arg % len(dialect)], history, mem,
                                    (), rng, meter, stack, semantic=True)
            stack = [value]
        elif op == 16:
            stack.append(len(history))
        elif op == 17:
            if mem:
                index = pop() if arg < 0 else arg
                mem[index % len(mem)] = pop()
            else:
                pop()
        elif op == 18:
            break
        if len(stack) > 128:
            raise Trap('stack limit')
    return (stack[-1] if stack else 0), out, mem


def ins(name, arg=0):
    return [OPS.index(name), arg]
