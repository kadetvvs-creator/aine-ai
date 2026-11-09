#!/usr/bin/env python3
# -*- coding: utf-8 -*-
P = "<AINE_HOME>/vokivon/aine/ail.py"
s = open(P, encoding="utf-8").read()

# 1) JUNK_PATTERNS + _is_junk после BARRIER_RULES
old1 = "    ('перезагрузи', 'перезагрузка сервера запрещена'),\n]"
new1 = old1 + '''

JUNK_PATTERNS = [
    "привет", "пожалуйста", "изучи прикрепленный", "рамбер",
    "российская газета", "последние новости", "новости россии и мира",
    "свежие новости", "лента.ру", "рбк", "тасс", "риа новости",
]


def _is_junk(cond: str) -> bool:
    """Авто-гигиена: мусорные условия (запросы/заголовки) не сохраняем."""
    c = (cond or "").lower()
    return any(j in c for j in JUNK_PATTERNS)'''
assert old1 in s, "BARRIER_RULES end not found"
s = s.replace(old1, new1, 1)

# 2) фильтр на входе в add_pollen
old2 = '''                   origin: str = 'seed') -> str:
        """Добавить пыльцу агенту (заражение: origin=infection)."""
        agent = self._agent(archetype)'''
new2 = '''                   origin: str = 'seed') -> str:
        """Добавить пыльцу агенту (заражение: origin=infection)."""
        if _is_junk(condition):
            return ""  # авто-гигиена: мусор не сохраняем
        agent = self._agent(archetype)'''
assert old2 in s, "add_pollen not found"
s = s.replace(old2, new2, 1)

# 3) GC в evolve (удалить мусор + дубли)
old3 = '''        """Цикл эволюции: усиленные уже выросли; слабые угасают."""
        decayed = 0'''
new3 = '''        """Цикл эволюции: усиленные уже выросли; слабые угасают."""
        # GC: удалить мусор + дубликаты условий
        for _agent in self.agents.values():
            _seen = set()
            _kept = []
            for _p in _agent.pollen:
                if _is_junk(_p.condition):
                    continue
                _k = (_p.condition or "").lower().strip()
                if _k in _seen:
                    continue
                _seen.add(_k)
                _kept.append(_p)
            _agent.pollen = _kept
        decayed = 0'''
assert old3 in s, "evolve not found"
s = s.replace(old3, new3, 1)

open(P, "w", encoding="utf-8").write(s)
import ast
ast.parse(open(P, encoding="utf-8").read())
print("ail.py: авто-гигиена (фильтр на входе + GC в evolve) добавлена")
