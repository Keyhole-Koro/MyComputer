from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

TOOLCHAIN_DIR = REPO_ROOT / "toolchain"
RUNTIME_DIR = REPO_ROOT / "runtime"
SYSTEM_DIR = REPO_ROOT / "system"
QA_DIR = REPO_ROOT / "qa"

MYASSEMBLER_DIR = TOOLCHAIN_DIR / "MyAssembler"
MYLANGCOMPILER_DIR = TOOLCHAIN_DIR / "MyLangCompiler"
MYLINKER_DIR = TOOLCHAIN_DIR / "MyLinker"
MYEMULATOR_DIR = RUNTIME_DIR / "MyEmulator"
MYKERNEL_DIR = SYSTEM_DIR / "MyKernel"
MYTESTER_DIR = QA_DIR / "MyTester"
