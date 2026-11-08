"""What the QA runner scripts share: status lines, logged steps and myemu.

run_system.py, run_kernel.py and run_mylang.py run their builds and the
emulator as the steps of one debug session (qa/tools/debug_session.py);
test-all.py prints its status lines the same way.
"""

from __future__ import annotations

import subprocess

from qa.tools.debug_session import DebugSession, run_logged, summarize_failure
from tools.project_paths import MYEMULATOR_DIR, REPO_ROOT

GREEN = "32"
RED = "31"
YELLOW = "33"
CYAN = "36"

MYEMU = MYEMULATOR_DIR / "target" / "release" / "myemu"


def colored(text, color_code):
    return f"\033[{color_code}m{text}\033[0m"


def status_line(label, message, color=CYAN):
    print(colored(f"[{label}]", color), message, flush=True)


class StepRunner:
    """Runs a script's commands from the repository root as the steps of one
    debug session, each logged under the session's steps/.

    A step prints a STEP line; with verbose it prints the command instead and,
    once it is done, its output and OK. A failed step prints FAIL, where to
    look and what went wrong, then raises CalledProcessError.
    """

    def __init__(self, session: DebugSession, verbose: bool = False, summarize_failures: bool = True):
        self.session = session
        self.verbose = verbose
        # A failure points at the step's log and shows the diagnostic that
        # explains it. Without summarize_failures it points at the session and
        # shows the last lines of the output, as run_kernel.py and
        # run_mylang.py always have.
        self.summarize_failures = summarize_failures

    def run(self, cmd, description: str, log_name: str, *, echo_output: bool = False,
            quiet_fail: bool = False) -> str:
        """Run cmd and return its output. echo_output streams the output while
        it runs; quiet_fail leaves reporting a failure to the caller."""
        if self.verbose:
            status_line("RUN", " ".join(str(c) for c in cmd), CYAN)
        else:
            status_line("STEP", description, CYAN)

        try:
            output = run_logged(cmd, REPO_ROOT, description, self.session, log_name, echo_output=echo_output)
        except subprocess.CalledProcessError as exc:
            if not quiet_fail:
                self.report_failure(description, log_name, exc.output)
            raise

        if self.verbose and output and not echo_output:
            print(output, end="")
            status_line("OK", description, GREEN)
        return output

    def report_failure(self, description: str, log_name: str, output: str | None) -> None:
        status_line("FAIL", description, RED)
        if self.summarize_failures:
            status_line("INFO", f"full log: {self.session.path('steps', log_name)}", YELLOW)
            detail = summarize_failure(output or "")
        else:
            status_line("INFO", f"session: {self.session.session_dir}", YELLOW)
            detail = "\n".join((output or "").strip().splitlines()[-20:])
        if detail:
            print(detail, flush=True)


def build_emulator(steps: StepRunner, description: str, log_name: str) -> None:
    """Build myemu, so a run uses the current source. Without cargo, the myemu
    already built is used as it is."""
    try:
        steps.run(["make", "-C", MYEMULATOR_DIR, "all"], description, log_name, quiet_fail=True)
    except subprocess.CalledProcessError as exc:
        if "cargo: not found" not in (exc.output or "") or not MYEMU.exists():
            steps.report_failure(description, log_name, exc.output)
            raise
        status_line("INFO", f"cargo not found; using existing emulator: {MYEMU}", YELLOW)


def emulator_debug_args(args) -> list:
    """The myemu options for a runner's own --trace, --break (dest break_addr),
    --step and --mem, which it passes through as they are."""
    debug_args = []
    if args.trace:
        debug_args.append("--trace")
    if args.break_addr:
        debug_args += ["--break", args.break_addr]
    if args.step:
        debug_args += ["--step", args.step]
    if args.mem:
        debug_args += ["--mem", *args.mem]
    return debug_args


def print_serial_output(session: DebugSession, title: str) -> None:
    """Print what the guest wrote to its serial port: myemu logs it to
    serial.txt in its --log-dir, the session directory."""
    serial = session.path("serial.txt").read_text(encoding="utf-8", errors="replace").strip()
    if serial:
        status_line("PRINT", title, YELLOW)
        print(serial)
