# Copyright (c) 2024 Igor Kriusov <kriusovia@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
# https://www.gnu.org/licenses/gpl-3.0.html
"""
Нечёткий матчинг команд: rapidfuzz + navec.

Простая логика:
1. Каждое слово текста сравниваем с каждым словом каждой фразы
2. Фраза набирает очки за каждое совпавшее слово
3. Побеждает фраза с лучшим средним score (если > порога)
4. Navec (эмбеддинги) — дополнительный fallback по семантике
"""
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from rapidfuzz import fuzz

THRESHOLD = 65  # порог partial_ratio для пары слов
EMBEDDING_THRESHOLD = 0.65

_NAVEC_MODEL = Path(__file__).resolve().parent.parent.parent / "models" / "navec_hudlit_v1_12B_500K_300d_100q.tar"


@dataclass
class FuzzyMatch:
    action: str
    score: float
    method: str  # "levenshtein" или "embedding"


class FuzzyMatcher:

    def __init__(self, commands: List[Dict[str, Any]]) -> None:
        # action → [phrase_words, ...]
        self._phrases: Dict[str, List[List[str]]] = {}
        for cmd in commands:
            action = cmd.get("action", "")
            phrases = cmd.get("phrases") or []
            self._phrases[action] = [p.lower().split() for p in phrases]

        self._navec = None
        self._phrase_vectors: Dict[str, List[np.ndarray]] = {}
        self._load_navec()

    def _load_navec(self) -> None:
        if not _NAVEC_MODEL.exists():
            print("[FUZZY] Navec не найден, только Левенштейн.", file=sys.stderr)
            return
        try:
            from navec import Navec
            self._navec = Navec.load(str(_NAVEC_MODEL))
            for action, phrases in self._phrases.items():
                vecs = []
                for words in phrases:
                    v = self._words_to_vec(words)
                    if v is not None:
                        vecs.append(v)
                self._phrase_vectors[action] = vecs
            print(f"[FUZZY] Navec загружен.", file=sys.stderr)
        except Exception as e:
            print(f"[FUZZY] Navec: {e}", file=sys.stderr)

    def _words_to_vec(self, words: List[str]) -> Optional[np.ndarray]:
        if not self._navec:
            return None
        vecs = [self._navec[w] for w in words if w in self._navec]
        return np.mean(vecs, axis=0) if vecs else None

    def _cosine(self, a: np.ndarray, b: np.ndarray) -> float:
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def _score_phrase(
        self, text_words: List[str], phrase_words: List[str]
    ) -> float:
        """Оценить насколько текст похож на фразу.

        Для каждого слова фразы ищем лучший partial_ratio среди слов текста.
        Считаем сколько слов фразы матчнулось (score > THRESHOLD).
        Итоговый score = среднее по совпавшим словам.
        Если ни одно не совпало — 0.
        """
        if not phrase_words:
            return 0.0

        matches = []
        for pw in phrase_words:
            # ratio для слов похожей длины, partial_ratio для обрезанных (len отличается > 30%)
            scores = []
            for tw in text_words:
                if abs(len(tw) - len(pw)) <= max(len(tw), len(pw)) * 0.3:
                    scores.append(fuzz.ratio(tw, pw))
                else:
                    scores.append(fuzz.partial_ratio(tw, pw) * 0.85)  # штраф за разную длину
            best = max(scores) if scores else 0.0
            if best >= THRESHOLD:
                matches.append(best)

        if not matches:
            return 0.0

        return sum(matches) / len(matches)

    def match(self, text: str) -> Optional[FuzzyMatch]:
        """Найти лучшую команду через fuzzy."""
        text_words = text.lower().split()
        if not text_words:
            return None

        # Фаза 1: Левенштейн (partial_ratio)
        best: Optional[FuzzyMatch] = None
        for action, phrases in self._phrases.items():
            for phrase_words in phrases:
                score = self._score_phrase(text_words, phrase_words)
                if score >= THRESHOLD and (best is None or score > best.score):
                    best = FuzzyMatch(action=action, score=score, method="levenshtein")

        if best:
            print(
                f"[FUZZY] {best.method}: «{text}» → {best.action} (score={best.score:.0f})",
                file=sys.stderr,
            )
            return best

        # Фаза 2: Эмбеддинги
        if not self._navec or not self._phrase_vectors:
            return None

        text_vec = self._words_to_vec(text_words)
        if text_vec is None:
            return None

        for action, vecs in self._phrase_vectors.items():
            for v in vecs:
                cos = self._cosine(text_vec, v)
                if cos >= EMBEDDING_THRESHOLD and (best is None or cos > best.score):
                    best = FuzzyMatch(action=action, score=cos, method="embedding")

        if best:
            print(
                f"[FUZZY] {best.method}: «{text}» → {best.action} (cosine={best.score:.3f})",
                file=sys.stderr,
            )
        return best
