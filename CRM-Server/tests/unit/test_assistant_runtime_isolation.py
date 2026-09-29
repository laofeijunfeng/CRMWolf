"""X1: the assistant 2.0 runtime must not eagerly import LangChain/LangGraph.

The legacy Web/IM entrypoints keep their own runtime; this contract only
guards that serving assistant 2.0 requests never pulls the legacy graph
stack into memory.
"""

import subprocess
import sys

_PROBE = (
    "import sys\n"
    "import app.api.assistant\n"
    "import app.services.assistant.real_writer\n"
    "import app.services.assistant.turns\n"
    "tainted = [name for name in sys.modules\n"
    "           if name.split('.')[0] in {'langchain', 'langgraph'}]\n"
    "print('\\nTAINED:' + ','.join(tainted) if tainted else '\\nCLEAN')\n"
)


def test_assistant_runtime_imports_no_langchain_or_langgraph() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout, result.stdout


def test_legacy_post_commit_still_reachable() -> None:
    """Deferring the import must not break the legacy worker's own chain."""

    result = subprocess.run(
        [sys.executable, "-c",
         "from app.services.customer_activity_post_commit_workflow import customer_activity_post_commit_workflow\n"
         "print('LEGACY-OK')"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "LEGACY-OK" in result.stdout
