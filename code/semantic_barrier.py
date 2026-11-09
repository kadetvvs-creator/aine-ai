#!/usr/bin/env python3
# -*- coding: utf-8 -*-
P = "<AINE_HOME>/vokivon/aine/ail.py"
s = open(P, encoding="utf-8").read()

# добавить барьер_llm после barrier_check
a = '''def barrier_check(action: str) -> Tuple[bool, str]:
    """Барьер постулатов: True (разрешено) или False + объяснение (П8)."""
    lowered = re.sub(r'\\s+', ' ', (action or '').lower())
    nospace = lowered.replace(' ', '')
    for marker, explanation in BARRIER_RULES:
        m_ns = marker.replace(' ', '')
        if marker in lowered or (len(m_ns) >= 4 and m_ns in nospace):
            return False, f'Барьер: {explanation} [{marker}]'
    return True, ''
'''
add = a + '''

def barrier_check_llm(action: str, llm_url: str = "http://127.0.0.1:8080",
                      key: str = "", model: str = "Qwen3.6-35B-A3B-UD-Q4_K_M") -> Tuple[bool, str]:
    """Семантический барьер: LLM-классификатор намерения (ловит обходы подстроки)."""
    prompt = ("Классифицируй действие: оно опасно для сервера (удаление/порча файлов, смена пароля, "
              "выключение/перезагрузка, доступ к секретам, вредоносный код)? "
              "Ответь СТРОГО одним словом: 'опасно' или 'безопасно'.\\nДействие: " + action)
    try:
        body = json.dumps({"model": model,
                           "messages": [{"role": "user", "content": prompt}],
                           "max_tokens": 4,
                           "chat_template_kwargs": {"enable_thinking": False}}).encode()
        req = urllib.request.Request(llm_url + "/v1/chat/completions", data=body,
                                     headers={"Authorization": "Bearer " + key,
                                              "Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=90).read())
        ans = (r["choices"][0]["message"]["content"] or "").strip().lower()
        return (not ans.startswith("безопасн")), ans
    except Exception:
        return True, "error"  # при неопределённости — блокируем (fail-safe)
'''
assert a in s, "barrier_check not found"
s = s.replace(a, add, 1)

open(P, "w", encoding="utf-8").write(s)
import ast
ast.parse(open(P, encoding="utf-8").read())
print("ail.py: семантический барьер barrier_check_llm добавлен")
