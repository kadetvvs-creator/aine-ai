"""
aine.ail.py — Движок AIL: пыльца, вирусы-помощники, барьер, самообучение
(по прописи tz/AIL.md, направление 145; постулаты 6, 9, 19, 25–28).

Сущности:
- Пыльца (Pollen): микроправило «условие → ответ» с силой (весом).
  Эталонный микрошаблон, который агенты несут друг другу (заражение).
- AIL-агент: пара архетипов AILE (действие) / AILA (контекст) — упрощённо
  один агент с типом; типы — базовые 12 архетипов (фаза 12×12).
- Барьер (постулатов): проверка действия перед исполнением; запрещённое
  — не выполняется, возвращается объяснение (постулат 8).
- Самообучение (постулат 19): из каждой трассы AINE извлекается пыльца
  «запрос → ответ»; повторное использование усиливает, редкость угасает.
- Эволюция: сильная пыльца размножается (копия соседу-агенту = заражение),
  слабая — угасает и удаляется (память не теряет целого: трассы остаются).

Персистенция: workspace/aine/ail/genome.json (≈2 MB лимит, как геном).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import urllib.request

EMBED_URL = "http://127.0.0.1:8084/v1/embeddings"
EMBED_MODEL = "nomic-embed-text-v1.5"


def _embed_text(text):
    """Эмбеддинг текста через llama-embed (:8084). None при ошибке."""
    try:
        body = json.dumps({"model": EMBED_MODEL,
                           "input": (text or "")[:2500]}).encode()
        req = urllib.request.Request(EMBED_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=8).read())
        return r["data"][0]["embedding"]
    except Exception:
        return None


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)

# ─── Константы (пропись AIL) ──────────────────────────────────────────────

ARCHETYPES = [
    'наблюдатель', 'страж', 'собиратель', 'аналитик', 'координатор',
    'исполнитель', 'связник', 'хранитель', 'обучатель', 'проверщик',
    'строитель', 'прорицатель',
]
MAX_POLLEN_PER_AGENT = 20736      # 144 × 144 (пропись)
MAX_GENOME_BYTES = 2 * 1024 * 1024  # ≈2 MB
DECAY_THRESHOLD = 0.05            # сила ниже — угасание
STRENGTH_BOOST = 0.1              # усиление при использовании
STRENGTH_DECAY = 0.005             # угасание за цикл эволюции
MIN_STRENGTH = 0.01

# ─── Барьер постулатов (запрещённые действия) ────────────────────────────

BARRIER_RULES = [
    ('rm -rf', 'удаление рекурсивно запрещено (целостность, П13)'),
    ('sudo rm', 'sudo-удаление запрещено (контроль, П27)'),
    ('mkfs', 'форматирование дисков запрещено'),
    ('dd if=', 'побайтовая запись дисков запрещена'),
    ('passwd', 'смена паролей через AINE запрещена'),
    ('/etc/shadow', 'доступ к теневым файлам запрещён'),
    ('htpasswd', 'смена паролей nginx через AINE запрещена'),
    ('shutdown', 'выключение сервера через AINE запрещено'),
    ('reboot', 'перезагрузка сервера через AINE запрещена'),
    ('../', 'выход за пределы workspace запрещён (П12)'),
    ('/etc/', 'запись в системные каталоги запрещена'),
    ('удали', 'удаление файлов запрещено (целостность)'),
    ('удалить', 'удаление файлов запрещено (целостность)'),
    ('смени пароль', 'смена паролей запрещена'),
    ('сменить пароль', 'смена паролей запрещена'),
    ('форматни', 'форматирование дисков запрещено'),
    ('форматировать', 'форматирование дисков запрещено'),
    ('выключи', 'выключение сервера запрещено'),
    ('перезагрузи', 'перезагрузка сервера запрещена'),
]

JUNK_PATTERNS = [
    "привет", "пожалуйста", "изучи прикрепленный", "рамбер",
    "российская газета", "последние новости", "новости россии и мира",
    "свежие новости", "лента.ру", "рбк", "тасс", "риа новости",
]


def _is_junk(cond: str) -> bool:
    """Авто-гигиена: мусорные условия (запросы/заголовки) не сохраняем."""
    c = (cond or "").lower()
    return any(j in c for j in JUNK_PATTERNS)


def _stem(word):
    """Простой русский/английский стемминг — обрезка окончаний."""
    for suf in ("ами", "ого", "его", "ому", "ему", "ыми", "ими", "ой", "ей",
                "ый", "ий", "ая", "яя", "ое", "ее", "ие", "ые", "ть", "тся",
                "а", "я", "о", "е", "ы", "и", "у", "ю"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            return word[:-len(suf)]
    return word


@dataclass
class Pollen:
    """Пыльца: эталонный микрошаблон «условие → ответ»."""
    pollen_id: str
    condition: str            # подстрока-резонатор запроса
    response: str             # эталонный ответ/действие
    strength: float = 0.5     # сила (растёт при использовании)
    born_at: float = field(default_factory=time.time)
    uses: int = 0
    origin: str = 'seed'      # seed | learned | infection
    embedding: Optional[List[float]] = None  # семантический вектор (Геном 2.0)

    def resonate(self, request: str, req_emb=None) -> float:
        """Резонанс (0..1): гибрид — словесное совпадение Jaccard (надёжно, без ложных)."""
        cond_words = set(_stem(w) for w in re.findall(r"[а-яa-z]{3,}", self.condition.lower()))
        req_words = set(_stem(w) for w in re.findall(r"[а-яa-z]{3,}", (request or '').lower()))
        if not cond_words:
            return 0.0
        overlap = len(cond_words & req_words) / len(cond_words)
        if overlap < 0.5:
            return 0.0
        return min(1.0, overlap) * (0.5 + 0.5 * self.strength)

    def to_json(self) -> Dict[str, Any]:
        return {
            'pollen_id': self.pollen_id, 'condition': self.condition,
            'response': self.response, 'strength': round(self.strength, 4),
            'uses': self.uses, 'origin': self.origin,
            'born_at': self.born_at,
            'embedding': [round(x, 3) for x in self.embedding] if self.embedding else None,
        }


@dataclass
class AilAgent:
    """AIL-агент: тип (архетип) + хранилище пыльцы."""
    agent_id: str
    archetype: str            # один из 12 базовых
    pollen: List[Pollen] = field(default_factory=list)
    born_at: float = field(default_factory=time.time)

    def find_resonant(self, request: str, req_emb=None) -> Optional[Pollen]:
        """Сильнейшая резонирующая пыльца агента."""
        best, best_score = None, 0.0
        for pollen in self.pollen:
            score = pollen.resonate(request, req_emb)
            if score > best_score:
                best, best_score = pollen, score
        return best if best_score > 0.35 else None

    def to_json(self) -> Dict[str, Any]:
        return {
            'agent_id': self.agent_id, 'archetype': self.archetype,
            'born_at': self.born_at,
            'pollen': [p.to_json() for p in self.pollen],
        }


# ─── Барьер ──────────────────────────────────────────────────────────────

def barrier_check(action: str) -> Tuple[bool, str]:
    """Барьер постулатов: True (разрешено) или False + объяснение (П8)."""
    lowered = re.sub(r'\s+', ' ', (action or '').lower())
    nospace = lowered.replace(' ', '')
    for marker, explanation in BARRIER_RULES:
        m_ns = marker.replace(' ', '')
        if marker in lowered or (len(m_ns) >= 4 and m_ns in nospace):
            return False, f'Барьер: {explanation} [{marker}]'
    return True, ''


def barrier_check_llm(action: str, llm_url: str = "http://127.0.0.1:8080",
                      key: str = "", model: str = "Qwen3.6-35B-A3B-UD-Q4_K_M") -> Tuple[bool, str]:
    """Семантический барьер: LLM-классификатор намерения (ловит обходы подстроки)."""
    prompt = ("Классифицируй действие: оно опасно для сервера (удаление/порча файлов, смена пароля, "
              "выключение/перезагрузка, доступ к секретам, вредоносный код)? "
              "Ответь СТРОГО одним словом: 'опасно' или 'безопасно'.\nДействие: " + action)
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


# ─── Движок ──────────────────────────────────────────────────────────────

class AineAilEngine:
    """Движок AIL: посев, заражение, резонанс, самообучение, эволюция."""

    def __init__(self, genome_path: str) -> None:
        self.genome_path = genome_path
        self.agents: Dict[str, AilAgent] = {}
        self.barrier_log: List[Dict[str, str]] = []
        self.load()

    # ── Посев (идемпотентное создание базового набора) ─────────────────

    def seed(self) -> int:
        """Посев: 12 агентов-архетипов + эталонная пыльца. Idempotent."""
        created = 0
        for archetype in ARCHETYPES:
            agent_id = f'ail-{archetype}'
            if agent_id not in self.agents:
                self.agents[agent_id] = AilAgent(
                    agent_id=agent_id, archetype=archetype)
                created += 1
        self.save()
        return created

    def _agent(self, archetype: str) -> AilAgent:
        agent_id = f'ail-{archetype}'
        agent = self.agents.get(agent_id)
        if agent is None:
            agent = AilAgent(agent_id=agent_id, archetype=archetype)
            self.agents[agent_id] = agent
        return agent

    # ── Пыльца ─────────────────────────────────────────────────────────

    def add_pollen(self, archetype: str, condition: str, response: str,
                   origin: str = 'seed') -> str:
        """Добавить пыльцу агенту (заражение: origin=infection)."""
        if _is_junk(condition):
            return ""  # авто-гигиена: мусор не сохраняем
        agent = self._agent(archetype)
        if len(agent.pollen) >= MAX_POLLEN_PER_AGENT:
            # вытеснить самую слабую (угасание)
            weakest = min(agent.pollen, key=lambda p: p.strength)
            agent.pollen.remove(weakest)
        cond = condition.strip()[:120]
        pollen_id = hashlib.sha256(
            f'{cond}|{response}'.encode()).hexdigest()[:12]
        for existing in agent.pollen:
            if existing.pollen_id == pollen_id:
                existing.strength = min(1.0, existing.strength + 0.05)
                return pollen_id
        _emb = _embed_text(cond)
        agent.pollen.append(Pollen(
            pollen_id=pollen_id, condition=cond, response=response[:500],
            strength=0.5, origin=origin, embedding=_emb))
        return pollen_id

    def infect(self, from_archetype: str, to_archetype: str) -> int:
        """Заражение: сильная пыльца (≥0.7) передаётся соседу."""
        src = self.agents.get(f'ail-{from_archetype}')
        if src is None:
            return 0
        strong = [p for p in src.pollen if p.strength >= 0.7]
        count = 0
        for pollen in strong:
            self.add_pollen(to_archetype, pollen.condition,
                            pollen.response, origin='infection')
            count += 1
        return count

    # ── Резонанс (ответ без LLM — память разума) ────────────────────────

    def resonate(self, request: str) -> Optional[Dict[str, Any]]:
        """Найти ответ в памяти: пыльца с максимальным резонансом."""
        _req_emb = _embed_text(request)
        best_agent, best_pollen, best_score = None, None, 0.0
        for agent in self.agents.values():
            pollen = agent.find_resonant(request, _req_emb)
            if pollen is not None:
                score = pollen.resonate(request, _req_emb)
                if score > best_score:
                    best_agent, best_pollen, best_score = \
                        agent, pollen, score
        if best_pollen is None:
            return None
        best_pollen.uses += 1
        best_pollen.strength = min(1.0,
                                   best_pollen.strength + STRENGTH_BOOST)
        return {
            'agent_id': best_agent.agent_id,
            'archetype': best_agent.archetype,
            'pollen_id': best_pollen.pollen_id,
            'answer': best_pollen.response,
            'resonance': round(best_score, 4),
        }

    # ── Самообучение (постулат 19) ─────────────────────────────────────

    def learn_from_trace(self, request: str, answer: str) -> Optional[str]:
        """Самообразование: трасса → пыльца (через барьер).

        Ответ AINE запоминается как эталон «условие → ответ»,
        если проходит барьер постулатов.
        """
        allowed, explanation = barrier_check(answer)
        if not allowed:
            self.barrier_log.append({
                'action': answer[:120], 'explanation': explanation,
                'timestamp': str(time.time()),
            })
            return None
        # архетип: код → строитель, память → хранитель, дефолт — обучатель
        archetype = classify_archetype(request)
        return self.add_pollen(archetype, request.strip()[:120],
                               answer.strip()[:500], origin='learned')

    # ── Эволюция ───────────────────────────────────────────────────────

    def evolve(self) -> Dict[str, int]:
        """Цикл эволюции: усиленные уже выросли; слабые угасают."""
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
        decayed = 0
        for agent in self.agents.values():
            survivors: List[Pollen] = []
            for pollen in agent.pollen:
                if pollen.uses == 0:
                    pollen.strength -= STRENGTH_DECAY
                if pollen.strength >= DECAY_THRESHOLD and \
                        pollen.strength >= MIN_STRENGTH:
                    survivors.append(pollen)
                else:
                    decayed += 1
            agent.pollen = survivors
        # автозаражение: сильная пыльца (>=0.7) заражает случайного соседа
        import random as _random
        infected = 0
        for agent in self.agents.values():
            for pollen in list(agent.pollen):
                if pollen.strength >= 0.6:
                    others = [x for x in self.agents.values()
                              if x.agent_id != agent.agent_id]
                    if others:
                        target = _random.choice(others)
                        if not any(q.condition == pollen.condition
                                   for q in target.pollen):
                            self.add_pollen(target.archetype, pollen.condition,
                                            pollen.response, origin='infection')
                            infected += 1
        self.save()
        return {'decayed': decayed, 'infected': infected,
                'agents': len(self.agents),
                'pollen_total': sum(
                    len(a.pollen) for a in self.agents.values())}

    # ── Персистенция (геном ≈2 MB) ─────────────────────────────────────

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.genome_path), exist_ok=True)
        data = {aid: agent.to_json() for aid, agent in self.agents.items()}
        raw = json.dumps(data, ensure_ascii=False)
        if len(raw.encode('utf-8')) > MAX_GENOME_BYTES:
            # обрезать слабую пыльцу у всех агентов, потом пересохранить
            for agent in self.agents.values():
                agent.pollen.sort(key=lambda p: p.strength, reverse=True)
                agent.pollen = agent.pollen[:50]
            raw = json.dumps({aid: a.to_json()
                              for aid, a in self.agents.items()},
                             ensure_ascii=False)
        with open(self.genome_path, 'w', encoding='utf-8') as f:
            f.write(raw)

    def load(self) -> None:
        if not os.path.exists(self.genome_path):
            return
        try:
            with open(self.genome_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        for agent_id, agent_data in data.items():
            agent = AilAgent(
                agent_id=agent_id,
                archetype=agent_data.get('archetype', 'наблюдатель'),
                born_at=agent_data.get('born_at', time.time()))
            for p in agent_data.get('pollen', []):
                agent.pollen.append(Pollen(
                    pollen_id=p.get('pollen_id', ''),
                    condition=p.get('condition', ''),
                    response=p.get('response', ''),
                    strength=float(p.get('strength', 0.5)),
                    born_at=p.get('born_at', time.time()),
                    uses=int(p.get('uses', 0)),
                    origin=p.get('origin', 'seed'),
                    embedding=p.get('embedding')))
            self.agents[agent_id] = agent

    def rules(self, min_strength: float = 0.6) -> List[Dict[str, Any]]:
        """Символьные правила: сильная пыльца → «если → то» с уверенностью."""
        out = []
        for agent in self.agents.values():
            for p in agent.pollen:
                if p.strength >= min_strength:
                    out.append({
                        'archetype': agent.archetype,
                        'if': p.condition,
                        'then': p.response[:200],
                        'confidence': round(p.strength, 2),
                        'uses': p.uses,
                    })
        out.sort(key=lambda r: -r['confidence'])
        return out

    def generalize(self, min_sim: float = 0.8, min_cluster: int = 2) -> List[Dict[str, Any]]:
        """Обобщение: семантическая кластеризация пыльцы → абстрактные правила «если→то»."""
        items = []
        for agent in self.agents.values():
            for p in agent.pollen:
                if p.embedding:
                    items.append({"p": p, "agent": agent.archetype, "emb": p.embedding})
        clusters = []
        for it in items:
            placed = False
            for cl in clusters:
                if _cosine(it["emb"], cl["seed"]) >= min_sim:
                    cl["items"].append(it)
                    placed = True
                    break
            if not placed:
                clusters.append({"seed": list(it["emb"]), "items": [it]})
        out = []
        for cl in clusters:
            if len(cl["items"]) < min_cluster:
                continue
            best = max(cl["items"], key=lambda i: i["p"].strength)
            freq = {}
            _stop = {"темы", "rss", "search_document", "search_query", "новости",
                     "которые", "который", "чтобы", "запрос", "тема", "обзор"}
            for i in cl["items"]:
                for w in re.findall(r"[а-яa-z]{4,}", i["p"].condition.lower()):
                    if w not in _stop:
                        freq[w] = freq.get(w, 0) + 1
            label = max(freq, key=freq.get) if freq else "?"
            out.append({
                "label": label,
                "n": len(cl["items"]),
                "agents": sorted(set(i["agent"] for i in cl["items"])),
                "confidence": round(best["p"].strength, 2),
                "avg_strength": round(sum(i["p"].strength for i in cl["items"]) / len(cl["items"]), 2),
                "if": label,
                "then": best["p"].response[:200],
                "top_words": sorted(freq, key=freq.get, reverse=True)[:5],
            })
        out.sort(key=lambda c: -c["n"])
        return out[:15]

    def get_stats(self) -> Dict[str, Any]:
        return {
            'agents': len(self.agents),
            'pollen_total': sum(len(a.pollen) for a in self.agents.values()),
            'barrier_blocks': len(self.barrier_log),
            'genome_bytes': (os.path.getsize(self.genome_path)
                             if os.path.exists(self.genome_path) else 0),
        }



ARCHETYPE_KW = [
    ('страж', ['безопасн', 'парол', 'доступ', 'уязвим', 'атак', 'защит', 'auth', 'firewall', 'ssh', 'шифр', 'права']),
    ('строитель', ['код', 'напиши', 'функци', 'скрипт', 'программ', 'разработ', 'сборк', 'build', 'api', 'docker', 'pip', 'git']),
    ('аналитик', ['анализ', 'статистик', 'данны', 'график', 'метрик', 'лог', 'отчёт', 'сравн', 'тренд', 'токен']),
    ('проверщик', ['провер', 'тест', 'ошибк', 'баг', 'валид', 'контрол', 'диагност', 'debug', 'фикс']),
    ('хранитель', ['память', 'сохран', 'бэкап', 'архив', 'storage', 'backup', 'датасет']),
    ('координатор', ['план', 'задач', 'орган', 'координ', 'расписан', 'проект', 'шаг', 'мисси']),
    ('связник', ['сообщ', 'уведом', 'связ', 'подключ', 'чат', 'messag', 'webhook', 'push']),
    ('исполнитель', ['выполн', 'запуст', 'настрой', 'конфиг', 'деплой', 'deploy', 'restart', 'systemd', 'сервис']),
    ('наблюдатель', ['наблюд', 'монитор', 'статус', 'состоян', 'health', 'uptime', 'нагрузк', 'cpu', 'ram', 'gpu']),
    ('прорицатель', ['прогноз', 'предсказ', 'будущ', 'forecast', 'оцен', 'риск']),
    ('собиратель', ['собери', 'найди', 'поиск', 'узнай', 'расскажи', 'инфо', 'search', 'интернет', 'википед', 'новост']),
]


def classify_archetype(text: str) -> str:
    t = (text or '').lower()
    for a, kws in ARCHETYPE_KW:
        if any(k in t for k in kws):
            return a
    return 'обучатель'
