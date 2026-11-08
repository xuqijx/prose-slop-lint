"""Heuristic rules for padded, AI-flavored prose.

Each rule is a regular expression plus a mechanical rewrite. A match is a
phrase to review, not a verdict that a model wrote the sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

Replacer = Callable[[re.Match[str]], str]


def match_case(sample: str, replacement: str) -> str:
    """Copy the capitalization of the first letter when it is obvious."""
    if not replacement or not sample:
        return replacement
    if sample.isupper():
        return replacement.upper()
    if sample[0].isupper():
        return replacement[0].upper() + replacement[1:]
    return replacement


def fixed(replacement: str) -> Replacer:
    def _replace(match: re.Match[str]) -> str:
        return match_case(match.group(0), replacement)

    return _replace


def verbs(mapping: dict[str, str]) -> Replacer:
    def _replace(match: re.Match[str]) -> str:
        word = match.group("verb")
        return match_case(word, mapping[word.lower()])

    return _replace


def replace_cutting_edge(match: re.Match[str]) -> str:
    text = match.group(0).lower()
    replacement = "current" if "state" in text else "new"
    return match_case(match.group(0), replacement)


def replace_game_changer(match: re.Match[str]) -> str:
    text = match.group(0).lower()
    forms = {
        "revolutionize": "change",
        "revolutionizes": "changes",
        "revolutionized": "changed",
        "revolutionizing": "changing",
        "revolutionise": "change",
        "revolutionises": "changes",
        "revolutionised": "changed",
        "revolutionising": "changing",
    }
    if text in forms:
        return match_case(match.group(0), forms[text])
    if "groundbreaking" in text:
        return match_case(match.group(0), "new")
    if text.replace(" ", "-").rstrip("s").endswith("changer") and text.endswith("s"):
        return match_case(match.group(0), "big changes")
    return match_case(match.group(0), "big change")


def replace_testament(match: re.Match[str]) -> str:
    text = match.group(0).lower()
    if text.startswith(("stand", "serve", "is ", "was ")):
        return match_case(match.group(0), "shows")
    return match_case(match.group(0), "evidence of")


def replace_not_only(match: re.Match[str]) -> str:
    body = match.group("body").strip(" ,")
    body = re.sub(r"^(?:does|do|can|will)\s+", "", body, flags=re.IGNORECASE)
    return f"{body} and"


def replace_deep_dive(match: re.Match[str]) -> str:
    text = match.group(0).lower()
    if "deep" in text:
        replacement = "closer look"
    elif "let" in text:
        replacement = "here are the details"
    else:
        replacement = "start"
    return match_case(match.group(0), replacement)


def replace_nestled(match: re.Match[str]) -> str:
    if re.search(r"\bin$", match.group(0), flags=re.IGNORECASE):
        return match_case(match.group(0), "in")
    return match_case(match.group(0), "located")


def replace_plethora(match: re.Match[str]) -> str:
    return match_case(match.group(0), "many")


@dataclass(frozen=True)
class Rule:
    rule_id: str
    why: str
    pattern: re.Pattern[str]
    replace: Replacer


def _rule(rule_id: str, why: str, pattern: str, replace: Replacer) -> Rule:
    return Rule(
        rule_id=rule_id,
        why=why,
        pattern=re.compile(pattern, re.IGNORECASE),
        replace=replace,
    )


# Order is the order used when several rules match the same line.
RULES: tuple[Rule, ...] = (
    _rule(
        "delve",
        '"Delve" is a stock verb in generated prose. Name the action, usually "look at" or "explain".',
        r"\b(?P<verb>delve|delves|delving|delved)(?:\s+into)?\b",
        verbs(
            {
                "delve": "look at",
                "delves": "looks at",
                "delving": "looking at",
                "delved": "looked at",
            }
        ),
    ),
    _rule(
        "tapestry",
        'Calling a collection a "tapestry" adds a metaphor and no detail. Name the collection.',
        r"\b(?:rich\s+)?tapestry\b",
        fixed("mix"),
    ),
    _rule(
        "landscape-metaphor",
        'Phrases like "digital landscape" fill a sentence without saying where or what. Name the place, or drop the metaphor.',
        r"\b(?:ever[- ]evolving|digital|modern|today'?s|current|competitive|fast[- ]paced)\s+landscape\b",
        fixed("field"),
    ),
    _rule(
        "leverage-verb",
        '"Leverage" as a verb almost always means "use". Say use.',
        r"\b(?P<verb>leverage|leverages|leveraged|leveraging)\b",
        verbs(
            {
                "leverage": "use",
                "leverages": "uses",
                "leveraged": "used",
                "leveraging": "using",
            }
        ),
    ),
    _rule(
        "seamless",
        '"Seamless" claims the rough edges are gone without showing how. Say what the person does.',
        r"\b(?P<verb>seamlessly|seamless)\b",
        verbs({"seamless": "simple", "seamlessly": "simply"}),
    ),
    _rule(
        "unlock-potential",
        '"Unlock the potential" is a slogan. Say what the reader can do now.',
        r"\b(?P<verb>unlock|unlocks|unlocking|unlocked)(?:\s+the)?(?:\s+full)?\s+(?:potential|power|possibilities)(?:\s+of)?\b",
        verbs(
            {
                "unlock": "use",
                "unlocks": "uses",
                "unlocking": "using",
                "unlocked": "used",
            }
        ),
    ),
    _rule(
        "game-changer",
        '"Game-changer", "revolutionize", and "groundbreaking" announce importance instead of describing the change.',
        r"\b(?:game[- ]changers?|revolutionize|revolutionizes|revolutionized|revolutionizing|revolutionise|revolutionises|revolutionised|revolutionising|groundbreaking)\b",
        replace_game_changer,
    ),
    _rule(
        "throat-clearing",
        'Openers such as "it is worth noting" delay the point. Start with the fact.',
        r"\b(?:it(?:['’]s| is) worth noting(?: that)?|it(?:['’]s| is) important to note(?: that)?|it is essential to (?:note|remember|understand)(?: that)?|needless to say(?:,| that)?)\b[,:]?\s*",
        fixed(""),
    ),
    _rule(
        "not-only-but-also",
        'The "not only / but also" frame is a common generated cadence. State both facts directly.',
        r"\bnot only\b(?P<body>.{0,160}?),?\s*\bbut also\b",
        replace_not_only,
    ),
    _rule(
        "testament",
        '"Testament to" praises a thing without evidence. Say what it shows.',
        r"\b(?:(?:stands|serves)\s+as\s+a\s+testament\s+to|(?:is|was)\s+a\s+testament\s+to|a\s+testament\s+to|testament\s+to)\b",
        replace_testament,
    ),
    _rule(
        "embark-journey",
        '"Embark on a journey" is a ceremonial way to say "start".',
        r"\b(?P<verb>embark|embarks|embarked|embarking)\s+on(?:\s+(?:a|an|your|this|the))?(?:\s+\w+){0,4}\s+journey\b",
        verbs(
            {
                "embark": "start",
                "embarks": "starts",
                "embarked": "started",
                "embarking": "starting",
            }
        ),
    ),
    _rule(
        "nestled",
        '"Nestled" is a travel-brochure verb. Say where the thing is.',
        r"\bnestled(?:\s+in)?\b",
        replace_nestled,
    ),
    _rule(
        "empower",
        '"Empower" hides the actor and the action. Say who can do what.',
        r"\b(?P<verb>empower|empowers|empowered|empowering)\b",
        verbs(
            {
                "empower": "help",
                "empowers": "helps",
                "empowered": "helped",
                "empowering": "helping",
            }
        ),
    ),
    _rule(
        "cutting-edge",
        '"Cutting-edge" and "state-of-the-art" are novelty claims. Say what is new, or say "new".',
        r"\b(?:cutting[- ]edge|state[- ]of[- ]the[- ]art)\b",
        replace_cutting_edge,
    ),
    _rule(
        "deep-dive",
        '"Dive in" and "deep dive" are presentation filler. Start the explanation.',
        r"\b(?:let['’]?s\s+dive\s+in|dive\s+in|deep\s+dive)\b",
        replace_deep_dive,
    ),
    _rule(
        "multifaceted",
        '"Multifaceted" says there is more than one part without naming a part.',
        r"\bmultifaceted\b",
        fixed("varied"),
    ),
    _rule(
        "plethora",
        '"A plethora of" and "myriad" are dressed-up ways to say "many". Use a number, or "many".',
        r"\b(?:a\s+)?plethora\s+of\b|\bmyriad(?:\s+of)?\b",
        replace_plethora,
    ),
    _rule(
        "utilize",
        '"Utilize" is a stiff stand-in for "use".',
        r"\b(?P<verb>utilize|utilizes|utilized|utilizing|utilise|utilises|utilised|utilising)\b",
        verbs(
            {
                "utilize": "use",
                "utilizes": "uses",
                "utilized": "used",
                "utilizing": "using",
                "utilise": "use",
                "utilises": "uses",
                "utilised": "used",
                "utilising": "using",
            }
        ),
    ),
    _rule(
        "holistic",
        '"Holistic" gestures at the whole thing without saying what is included.',
        r"\b(?P<verb>holistically|holistic)\b",
        verbs({"holistic": "broad", "holistically": "broadly"}),
    ),
    _rule(
        "crucial-role",
        '"Plays a crucial role" labels importance. Say what the thing does.',
        r"\b(?P<verb>play|plays)\s+an?\s+(?:crucial|vital|key|important|pivotal)\s+role\b",
        verbs({"play": "matter", "plays": "matters"}),
    ),
    _rule(
        "persona-opener",
        '"Whether you are a X or a Y" is a stock audience hook. Address the reader directly, or delete it.',
        r"\bwhether\s+you(?:['’]re|\s+are)\s+(?:a|an)\s+[^,.\n]{1,40}\s+or\s+(?:a|an)\s+[^,.\n]{1,40},?\s*",
        fixed(""),
    ),
    _rule(
        "in-conclusion",
        '"In conclusion" and "in summary" are speech-ending habits. Say the last fact.',
        r"\b(?:in\s+conclusion|in\s+summary|to\s+summarize|all\s+in\s+all)\b[,:]?\s*",
        fixed(""),
    ),
    _rule(
        "foster",
        '"Foster" is a vague verb in generated prose. Say support, build, or encourage, and name the object.',
        r"\b(?P<verb>foster|fosters|fostered|fostering)\b",
        verbs(
            {
                "foster": "encourage",
                "fosters": "encourages",
                "fostered": "encouraged",
                "fostering": "encouraging",
            }
        ),
    ),
    _rule(
        "elevate",
        '"Elevate" promises a rise in quality without a concrete change. Say what improves.',
        r"\b(?P<verb>elevate|elevates|elevated|elevating)\b",
        verbs(
            {
                "elevate": "improve",
                "elevates": "improves",
                "elevated": "improved",
                "elevating": "improving",
            }
        ),
    ),
    _rule(
        "vibrant",
        '"Vibrant" is a mood word that generated intros use instead of a fact.',
        r"\bvibrant\b",
        fixed("active"),
    ),
)
