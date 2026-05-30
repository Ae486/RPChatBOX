"""RP setup_agent-domain models (stage, workspace, handoff, truth index, drafts, agent).

Back-compat: ``rp.models.setup_agent`` was a flat module whose symbols now live in
``rp.models.setup_agent.agent``. The package name shadows any old-path shim module,
so a PEP 562 ``__getattr__`` lazily re-exports those symbols with a deprecation
nudge. Submodule access is resolved first so it never warns or recurses.
"""
from __future__ import annotations

import importlib
import warnings
from typing import Any


def __getattr__(name: str) -> Any:
    # Submodule access (e.g. `from rp.models.setup_agent import stage`) resolves
    # via the import system; never warn for these.
    try:
        return importlib.import_module(f"{__name__}.{name}")
    except ModuleNotFoundError:
        pass
    # Legacy symbol that used to live in the flat `rp.models.setup_agent` module.
    agent = importlib.import_module(f"{__name__}.agent")
    try:
        value = getattr(agent, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    warnings.warn(
        "rp.models.setup_agent.<symbol> is deprecated and will be removed next release; "
        "import from rp.models.setup_agent.agent instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    return value
