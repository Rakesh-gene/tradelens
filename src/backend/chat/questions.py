"""Legacy provider name extraction; unmatched wording is never rejected."""
import re

_TARGET = r"(?P<target>[a-z0-9&._'() -]{1,120}?)"
_PATTERNS = (
    rf"(?:what (?:is|are) (?:the )?(?:current )?setups?|show (?:me )?(?:the )?(?:current )?setups?) (?:in|for|of|on) {_TARGET}(?: today)?",
    rf"what setups? (?:does|do) {_TARGET} have(?: today)?",
    rf"(?:tell me|show me) (?:the )?setups? (?:in|for|of) {_TARGET}(?: today)?",
)


def setup_question_target(message):
    text = " ".join(message.lower().strip().rstrip("?.!").split())
    if text in {"what is the setup this equity has today", "what setup does this equity have today", "what is the setup today", "what is the setup for this equity today"}:
        return None
    for pattern in _PATTERNS:
        match = re.fullmatch(pattern, text)
        if match:
            target = match.group("target").strip()
            return None if target in {"this equity", "this stock", "this company"} else target
    return None
