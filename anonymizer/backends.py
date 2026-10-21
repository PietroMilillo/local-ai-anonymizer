"""Where the sanitized prompt goes. Only this module talks to anything off the machine."""
from __future__ import annotations

import subprocess
from pathlib import Path

PROMPT_TEMPLATE = """{task}

The document below has been pseudonymized. Tokens in square brackets such as [PERSON_1],
[ORG_2] or [DATE_1] stand for real values; the same token always means the same thing.
Keep every token exactly as written in your answer (square brackets included) and do not
guess what it stands for.

<document>
{document}
</document>"""


def build_prompt(task: str, sanitized: str) -> str:
    return PROMPT_TEMPLATE.format(task=task.strip(), document=sanitized.strip())


def send(prompt: str, backend: str, outgoing: Path, response: Path | None = None,
         model: str | None = None, timeout: int = 600) -> str | None:
    """Return the response text, or None when the backend only writes the prompt."""
    outgoing.write_text(prompt)
    if backend in ("dry-run", "file"):
        # dry-run: stop here. file: someone (a person, or a chat session) answers
        # the prompt and saves the reply; reidentify reads it later.
        return None
    if backend == "claude-cli":
        cmd = ["claude", "-p", "--no-session-persistence", "--output-format", "text",
               "--disallowedTools", "Bash,Edit,Write,Read,WebFetch,WebSearch,Agent"]
        if model:
            cmd += ["--model", model]
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError(f"claude -p failed: {r.stderr[:500]}")
        if response:
            response.write_text(r.stdout)
        return r.stdout
    raise ValueError(f"unknown backend {backend!r}")
