#!/usr/bin/env python3
"""Check dependencies among contracts, MyStdLib, MyAppFramework and MyOS."""

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = (REPO_ROOT / "contracts").resolve()
CONTRACTS_IO = CONTRACTS / "io"
CONTRACTS_UI = CONTRACTS / "ui"
CONTRACTS_PROCESS = CONTRACTS / "process"
CONTRACTS_MYOS = CONTRACTS / "myos"
CONTRACTS_MYAPP = CONTRACTS / "myapp"
STDLIB = (REPO_ROOT / "toolchain" / "MyStdLib").resolve()
STDLIB_HOSTED = STDLIB / "hosted"
STDLIB_PLATFORM = STDLIB / "platform"
SHARED_FS_ERROR = CONTRACTS_IO / "fs.contract.mln"
SHARED_UI_ERROR = CONTRACTS_UI / "widget.contract.mln"
FRAMEWORK = (REPO_ROOT / "system" / "MyAppFramework").resolve()
FRAMEWORK_SRC = FRAMEWORK / "src"
MYOS = (REPO_ROOT / "system" / "MyOS").resolve()
MYOS_SRC = MYOS / "src"
MYOS_APPS = MYOS_SRC / "apps"
MYOS_SYSCALL = MYOS_SRC / "syscall"
MYOS_IPC = MYOS_SRC / "ipc"
MYOS_DOMAINS = tuple(MYOS_SRC / name for name in ("ui", "fs", "shell", "proc"))
MYOS_PROTOCOL_ENDPOINTS = (
    MYOS_SRC / "ui" / "protocol.mln",
    MYOS_SRC / "ui" / "protocol_elements.mln",
    MYOS_SRC / "shell" / "protocol.mln",
    MYOS_SRC / "fs" / "syscall.mln",
    MYOS_SRC / "proc" / "syscall.mln",
)
MYKERNEL = (REPO_ROOT / "system" / "MyKernel").resolve()

REMOVED_BOUNDARY_FILES = (
    FRAMEWORK_SRC / "fs.mln",
    FRAMEWORK_SRC / "console.mln",
    FRAMEWORK_SRC / "protocol" / "services.mln",
    FRAMEWORK_SRC / "protocol" / "message.mln",
    FRAMEWORK_SRC / "protocol" / "ui.mln",
    FRAMEWORK_SRC / "protocol" / "app.mln",
    FRAMEWORK_SRC / "os" / "syscall.masm",
    FRAMEWORK_SRC / "os" / "uiproto.mln",
    STDLIB / "io" / "fs.mln",
    STDLIB / "platform" / "myos" / "services.mln",
    MYOS_SRC / "proc" / "os_calls.mln",
    MYOS_SRC / "apps" / "shell.mln",
    MYOS_SRC / "ui" / "ui_channel.mln",
    MYOS_SRC / "ui" / "ui_events.mln",
    MYOS_SRC / "ui" / "ui_server.mln",
    MYOS_SRC / "ui" / "elements_server.mln",
    MYOS_SRC / "services" / "router.mln",
    MYOS_SRC / "services" / "user_memory.mln",
    MYOS_SRC / "services" / "fs.mln",
    MYOS_SRC / "services" / "process.mln",
    MYOS_SRC / "services" / "transport" / "gateway.mln",
    MYOS_SRC / "services" / "transport" / "channel.mln",
    MYOS_SRC / "services" / "transport" / "events.mln",
    MYOS_SRC / "services" / "ui" / "server.mln",
    MYOS_SRC / "services" / "ui" / "elements.mln",
    MYOS_SRC / "services" / "app" / "server.mln",
)

IMPORT_RE = re.compile(r'^\s*import\b.*\bfrom\s+"([^"]+)"\s*;')
FS_ERROR_RE = re.compile(r'^\s*export\s+enum\s+FsError\b', re.MULTILINE)
UI_ERROR_RE = re.compile(r'^\s*export\s+enum\s+UiError\b', re.MULTILINE)
NONE_TO_NEGATIVE_RE = re.compile(r'\bNone\s*->\s*-\d+')
FUNCTION_BODY_RE = re.compile(r'^\s*(?:export\s+)?[A-Za-z_][^;{}]*\([^;{}]*\)\s*\{', re.MULTILINE)


def is_within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def is_myos_boundary(path: Path) -> bool:
    return (
        is_within(path, MYOS_SYSCALL)
        or is_within(path, MYOS_IPC)
        or path in MYOS_PROTOCOL_ENDPOINTS
    )


def imports(source: Path):
    for line_number, line in enumerate(source.read_text().splitlines(), 1):
        match = IMPORT_RE.match(line)
        if match:
            yield line_number, match.group(1), (source.parent / match.group(1)).resolve()


def check_import(source: Path, target: Path) -> str | None:
    """Return a boundary violation, or None when the import is allowed."""
    if is_within(source, CONTRACTS):
        if is_within(target, CONTRACTS):
            return None
        return "contracts may depend only on other contracts"

    if is_within(source, STDLIB):
        if is_within(target, CONTRACTS):
            if is_within(source, STDLIB_HOSTED) or is_within(source, STDLIB_PLATFORM):
                return None
            return "only hosted/platform MyStdLib modules may depend on contracts"
        if not is_within(target, STDLIB):
            return "MyStdLib may only depend on itself and contracts"
        if not (is_within(source, STDLIB_HOSTED) or is_within(source, STDLIB_PLATFORM)):
            if is_within(target, STDLIB_HOSTED) or is_within(target, STDLIB_PLATFORM):
                return "freestanding MyStdLib modules may not depend on hosted/platform modules"
        if is_within(source, STDLIB_PLATFORM) and is_within(target, STDLIB_HOSTED):
            return "MyStdLib platform ABI may not depend on hosted APIs"
        return None

    if is_within(source, FRAMEWORK):
        if not any(is_within(target, root) for root in (FRAMEWORK, STDLIB, CONTRACTS)):
            return "MyAppFramework may depend only on itself, MyStdLib, and contracts"
        return None

    if is_within(source, MYOS_APPS):
        if is_within(target, FRAMEWORK):
            if target.parent != FRAMEWORK_SRC:
                return "apps may import only the app-facing files at MyAppFramework/src/*.mln"
            return None
        if is_within(target, STDLIB):
            return None
        if is_within(target, CONTRACTS):
            return None
        return "apps may depend only on MyAppFramework's public API, MyStdLib, and contracts"

    if is_within(source, MYOS_SRC):
        if is_within(target, STDLIB_HOSTED):
            return "MyOS implements hosted APIs and may not consume their client stubs"
        if (
            any(is_within(source, root) for root in MYOS_DOMAINS)
            and not is_myos_boundary(source)
            and is_myos_boundary(target)
        ):
            return "MyOS domain code may not depend on syscall, IPC, or protocol endpoints"
        if is_within(target, FRAMEWORK):
            return "MyOS implementation must use contracts, not MyAppFramework"
        if is_within(target, CONTRACTS):
            if (
                is_within(target, CONTRACTS_IO)
                or is_within(target, CONTRACTS_UI)
                or is_within(target, CONTRACTS_PROCESS)
                or is_myos_boundary(source)
            ):
                return None
            return "only MyOS boundary endpoints may depend on wire contracts"
        if not any(is_within(target, root) for root in (MYOS, MYKERNEL, STDLIB)):
            return "MyOS implementation may depend only on MyOS, MyKernel, MyStdLib, and contracts"

    return None


def main() -> int:
    violations = []
    for path in REMOVED_BOUNDARY_FILES:
        if path.exists():
            violations.append(
                f"{path.relative_to(REPO_ROOT)}: obsolete boundary file must not be restored"
            )
    for source in sorted(CONTRACTS.rglob("*.mln")):
        if not source.name.endswith(".contract.mln"):
            violations.append(
                f"{source.relative_to(REPO_ROOT)}: contract source must use the .contract.mln suffix"
            )
        if FUNCTION_BODY_RE.search(source.read_text()):
            violations.append(
                f"{source.relative_to(REPO_ROOT)}: contracts must not contain function implementations"
            )

    for root in (CONTRACTS, STDLIB, FRAMEWORK, MYOS_SRC):
        for source in sorted(root.rglob("*.mln")):
            source_text = source.read_text()
            if source != SHARED_FS_ERROR and FS_ERROR_RE.search(source_text):
                violations.append(
                    f"{source.relative_to(REPO_ROOT)}: FsError must be defined only in "
                    "contracts/io/fs.contract.mln"
                )
            if source != SHARED_UI_ERROR and UI_ERROR_RE.search(source_text):
                violations.append(
                    f"{source.relative_to(REPO_ROOT)}: UiError must be defined only in "
                    "contracts/ui/widget.contract.mln"
                )
            if NONE_TO_NEGATIVE_RE.search(source_text):
                violations.append(
                    f"{source.relative_to(REPO_ROOT)}: do not translate None to a negative sentinel"
                )
            for line_number, import_path, target in imports(source):
                problem = check_import(source, target)
                if problem:
                    relative = source.relative_to(REPO_ROOT)
                    violations.append(
                        f"{relative}:{line_number}: {problem}: {import_path}"
                    )

    if violations:
        print("Layer boundary violations:")
        for violation in violations:
            print(f"  {violation}")
        return 1

    print("Layer boundaries: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
