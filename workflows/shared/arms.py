"""Which DM subjects are randomised - one definition for every gate.

A subject is randomised unless DM.ARMCD or DM.ARM says screen failure / not
assigned / not randomised (SDTMIG null-arm codes SCRNFAIL, NOTASSGN, and the
spelled-out ARM values), or both are blank. Case, punctuation and parentheses are ignored.

    is_randomised("Pbo", "Placebo") -> True;  is_randomised("Scrnfail", "Screen Failure") -> False
"""

from __future__ import annotations

import re

NOT_RANDOMISED = {"scrnfail", "screenfailure", "notassgn", "notassigned", "notrandomized", "notrandomised"}


def normalise_arm(value: object) -> str:
    text = re.sub(r"\([^)]*\)", "", str(value or "")).lower()
    return re.sub(r"[^a-z0-9]", "", text)


def is_randomised(armcd: object, arm: object) -> bool:
    codes = {normalise_arm(armcd), normalise_arm(arm)}
    if codes & NOT_RANDOMISED:
        return False
    return codes != {""}
