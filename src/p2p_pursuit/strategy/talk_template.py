"""Zero-token banter: canned free-language templates (the default provider).

The move never depends on this layer; templates keep the whole series at
zero token cost while honoring free natural language and the word cap.
"""

from __future__ import annotations

import random

from ..domain.hints import clip_words, landmark_for

TEMPLATES = (
    "Slipping quietly past {place}, try to keep up.",
    "You will find nothing but shadows near {place}.",
    "Holed up around {place} for now, come and look.",
    "Heading toward {place}, catch me if you can.",
    "The trail goes cold by {place}, officer.",
    "Closing in from {place}, nowhere left to run.",
    "Patrolling {place} - every exit is watched.",
)


class TemplateTalk:
    """Provider contract: produce(region, map_area, max_words, rng) -> (text, tokens)."""

    name = "template"

    def produce(self, region: str, map_area: str, max_words: int,
                rng: random.Random) -> tuple[str, int]:
        use_landmark = rng.random() < 0.5
        place = landmark_for(region, map_area, rng.randrange(4)) if use_landmark \
            else f"the {region}"
        text = rng.choice(TEMPLATES).format(place=place)
        return clip_words(text, max_words), 0
