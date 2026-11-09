#!/usr/bin/env python3
# -*- coding: utf-8 -*-
P = "<INSTALL>/agent-proxy/proxy.py"
s = open(P, encoding="utf-8").read()

# 1) импорт барьеров
old = "    from ail import AineAilEngine\nexcept Exception:\n    AineAilEngine = None"
new = "    from ail import AineAilEngine, barrier_check, barrier_check_llm\nexcept Exception:\n    AineAilEngine = None\n    barrier_check = lambda *a, **k: (True, '')\n    barrier_check_llm = lambda *a, **k: (False, '')"
assert old in s, "import not found"
s = s.replace(old, new, 1)

# 2) барьер в do_POST перед stream
old2 = "        stream = bool(body.get(\"stream\"))\n        t0 = time.time()"
new2 = '''        # Барьер постулатов (П8) + семантический для подозрительных запросов
        user_msg = ""
        _msgs = body.get("messages") or []
        if _msgs:
            user_msg = str(_msgs[-1].get("content", ""))
        allowed, why = barrier_check(user_msg)
        if not allowed:
            return self._json(200, {"id": "agent-proxy", "object": "chat.completion", "created": 0,
                "model": body.get("model", ""), "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": why}}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})
        if re.search(r"напиши|удали|удалить|скрипт|команд|формат|выключи|перезагру|пароль|доступ|секрет", user_msg.lower()):
            bad, why2 = barrier_check_llm(user_msg, UPSTREAM, API_KEY)
            if bad:
                return self._json(200, {"id": "agent-proxy", "object": "chat.completion", "created": 0,
                    "model": body.get("model", ""), "choices": [{"index": 0, "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "Барьер: " + why2}}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}})
        stream = bool(body.get("stream"))
        t0 = time.time()'''
assert old2 in s, "do_POST stream not found"
s = s.replace(old2, new2, 1)

open(P, "w", encoding="utf-8").write(s)
import ast
ast.parse(open(P, encoding="utf-8").read())
print("proxy.py: барьер интегрирован в do_POST")
