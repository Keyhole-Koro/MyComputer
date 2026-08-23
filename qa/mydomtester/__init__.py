"""MyDOMTester: Playwright-style UI automation for MyKernel (MYOS-004).

Not a browser: this drives a headless MyEmulator over its
`--control-stdio` JSON Lines protocol (see
runtime/MyEmulator/src/control_stdio.rs) and queries the MyKernel DOM /
accessibility tree (system/MyOS/src/ui/dom.mln) instead of an HTML DOM.
Locators are role/name/text based, matching the ticket's target API:

    page = launch("build/firmware_linked.mbin", disk="build/disk.img")
    page.get_by_role("button", name="CLICK ME").click()
    expect(page.get_by_text("clicks: 1")).to_be_visible()
    page.close()

Non-goals (see the ticket): CSS selectors, full Playwright API parity,
HTML DOM compatibility, multiple pages/contexts.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.project_paths import MYEMULATOR_DIR  # noqa: E402

DEFAULT_MYEMU = MYEMULATOR_DIR / "target" / "release" / "myemu"

# Wall-clock budgets for round trips to the guest. Generous because a cold
# boot (wait_for_boot in control_stdio.rs) is the slow part, not any single
# command once the shell is up.
LAUNCH_TIMEOUT_S = 15.0
COMMAND_TIMEOUT_S = 5.0


class MyDOMTesterError(RuntimeError):
    """Raised when the emulator process misbehaves or a command fails."""


def launch(
    binary_path,
    disk: Optional[str] = None,
    myemu_path: Optional[str] = None,
    extra_args: Optional[list] = None,
) -> "Page":
    """Start `myemu --control-stdio` against `binary_path` and wait for boot."""
    myemu = Path(myemu_path) if myemu_path else DEFAULT_MYEMU
    if not myemu.exists():
        raise MyDOMTesterError(
            f"myemu not found at {myemu}; build it first (make -C runtime/MyEmulator)"
        )

    cmd = [str(myemu), "-i", str(binary_path), "--control-stdio"]
    if disk:
        cmd += ["--disk", str(disk)]
    if extra_args:
        cmd += list(extra_args)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # line-buffered
    )
    page = Page(proc)
    page._wait_ready()
    return page


class Page:
    def __init__(self, proc: subprocess.Popen):
        self._proc = proc
        self._log: list = []  # every line read from the guest, for debugging

    # --- low-level protocol -------------------------------------------------

    def _send(self, cmd: dict) -> None:
        if self._proc.poll() is not None:
            raise MyDOMTesterError(
                f"myemu exited (code {self._proc.returncode}) before command {cmd!r}; "
                f"last output:\n" + "\n".join(self._log[-20:])
            )
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(cmd) + "\n")
        self._proc.stdin.flush()

    def _read_response(self, timeout: float = COMMAND_TIMEOUT_S) -> dict:
        """Read lines until one parses as a control response ({"ok": ...}).

        Everything else is the guest's own serial output (boot log, shell
        prompt, debug prints) interleaved on the same stream; skip it. See
        control_stdio.rs's module doc for why a leading blank line always
        precedes a real response.
        """
        assert self._proc.stdout is not None
        deadline = time.monotonic() + timeout
        while True:
            if time.monotonic() >= deadline:
                raise MyDOMTesterError(
                    "timed out waiting for a control-stdio response; last output:\n"
                    + "\n".join(self._log[-20:])
                )
            line = self._proc.stdout.readline()
            if line == "":
                if self._proc.poll() is not None:
                    raise MyDOMTesterError(
                        f"myemu exited (code {self._proc.returncode}) while waiting for a "
                        f"response; last output:\n" + "\n".join(self._log[-20:])
                    )
                continue
            line = line.rstrip("\n")
            self._log.append(line)
            stripped = line.strip()
            if not stripped.startswith("{"):
                continue
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and "ok" in parsed:
                if not parsed.get("ok", False):
                    raise MyDOMTesterError(
                        f"control-stdio command failed: {parsed.get('error')}"
                    )
                return parsed

    def _command(self, cmd: dict, timeout: float = COMMAND_TIMEOUT_S) -> dict:
        self._send(cmd)
        return self._read_response(timeout)

    def _wait_ready(self) -> None:
        self._read_response(timeout=LAUNCH_TIMEOUT_S)

    # --- DOM/accessibility queries -------------------------------------------

    def dom_snapshot(self) -> list:
        """Return the current DOM tree as a flat list of node dicts."""
        return self._command({"cmd": "dom.snapshot"})["nodes"]

    def get_by_role(self, role: str, name: Optional[str] = None) -> "Locator":
        return Locator(self, role=role, name=name)

    def get_by_text(self, text: str) -> "Locator":
        return Locator(self, text=text)

    # --- input injection ------------------------------------------------------

    def mouse_move(self, x: int, y: int) -> None:
        self._command({"cmd": "mouse.move", "x": int(x), "y": int(y)})

    def mouse_down(self, button: str = "left") -> None:
        self._command({"cmd": "mouse.down", "button": button})

    def mouse_up(self, button: str = "left") -> None:
        self._command({"cmd": "mouse.up", "button": button})

    def frame_wait(self) -> None:
        self._command({"cmd": "frame.wait"})

    def screenshot(self, path: str) -> None:
        self._command({"cmd": "screenshot", "path": str(path)})

    # --- lifecycle --------------------------------------------------------

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()

    def __enter__(self) -> "Page":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class Locator:
    """A query, re-resolved against a fresh DOM snapshot on every use --
    matches Playwright's locators-are-lazy behaviour, so `expect(...)` can
    poll a locator across UI state changes instead of matching a stale node.
    """

    def __init__(self, page: Page, role: Optional[str] = None,
                 name: Optional[str] = None, text: Optional[str] = None):
        self._page = page
        self._role = role
        self._name = name
        self._text = text

    def __repr__(self) -> str:
        parts = []
        if self._role:
            parts.append(f"role={self._role!r}")
        if self._name:
            parts.append(f"name={self._name!r}")
        if self._text:
            parts.append(f"text={self._text!r}")
        return f"Locator({', '.join(parts)})"

    def _matches(self, node: dict) -> bool:
        if self._role is not None and node.get("role") != self._role:
            return False
        if self._name is not None and node.get("name") != self._name:
            return False
        if self._text is not None and node.get("text") != self._text:
            return False
        return True

    def resolve(self) -> Optional[dict]:
        """Return the first matching node from a fresh snapshot, or None."""
        for node in self._page.dom_snapshot():
            if self._matches(node):
                return node
        return None

    def is_visible(self) -> bool:
        node = self.resolve()
        return bool(node and node.get("visible"))

    def click(self) -> None:
        node = self.resolve()
        if node is None:
            raise MyDOMTesterError(f"{self!r}: no matching node in the current DOM")
        cx = node["x"] + node["w"] // 2
        cy = node["y"] + node["h"] // 2
        self._page.mouse_move(cx, cy)
        self._page.mouse_down()
        self._page.mouse_up()
        self._page.frame_wait()


class _Expect:
    def __init__(self, locator: Locator):
        self._locator = locator

    def to_be_visible(self, timeout: float = 2.0) -> None:
        deadline = time.monotonic() + timeout
        last_node = None
        while time.monotonic() < deadline:
            last_node = self._locator.resolve()
            if last_node is not None and last_node.get("visible"):
                return
            time.sleep(0.05)
        if last_node is None:
            raise AssertionError(f"{self._locator!r}: expected visible, found no matching node")
        raise AssertionError(f"{self._locator!r}: expected visible, node was {last_node}")


def expect(locator: Locator) -> _Expect:
    return _Expect(locator)
