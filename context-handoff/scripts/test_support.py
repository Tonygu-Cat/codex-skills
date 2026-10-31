"""Synthetic documents only; no production task identities."""
from pathlib import Path
from validate_handoff import REQUIRED_SECTIONS

CARD = "- Goal: synthetic fixture only.\n- Out of scope: any real task or workspace."
WIP = "- Unfinished work: none\n- Background jobs: none\n- Workspace changes: none"


def document(path, task="fixture-root-001", state="Synthetic current state.", revision=1,
             card=CARD, wip=WIP):
    path = Path(path).resolve()
    identity = ("- Project: `isolated-fixture`\n"
                "- Task or thread: `%s`\n"
                "- Canonical document: `%s`\n"
                "- Handoff revision: `%d`\n"
                "- Updated at: `2026-09-26T23:00:00+08:00`\n"
                "- Status: `active`" % (task, path.as_posix(), revision))
    bodies = {"Identity": identity, "Current state": state, "Direction card": card, "Work in progress": wip,
              "Next exact actions": "1. [agent] Continue synthetic fixture only.\n- User action now: none."}
    order = REQUIRED_SECTIONS[:1] + ("Direction card",) + REQUIRED_SECTIONS[1:3] + ("Work in progress",) + REQUIRED_SECTIONS[3:]
    return "# Project Handoff\n\n" + "\n\n".join(
        "## " + section + "\n\n" + bodies.get(section, "Preserved fixture requirement/evidence.")
        for section in order if bodies.get(section, True) is not None) + "\n"
