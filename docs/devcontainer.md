# Devcontainer Setup

This repository uses multiple C/C++ submodules plus Python-based test tooling. A devcontainer keeps
compiler/toolchain versions aligned and makes it easy to initialize submodules.

## Recommended layout
Create a `.devcontainer/` folder at the repository root with the following files:
- `.devcontainer/devcontainer.json`
- (optional) `.devcontainer/Dockerfile`


If you prefer a Dockerfile, install the build toolchain and CMake:
- `build-essential`
- `cmake`
- `gdb`
- `python3`

## Typical build commands
Run these from the repository root:
- `make -C MyAssembler`
- `make -C MyCC`
- `make -C MyEmulator`

## Notes
- The top-level repo is a thin wrapper around submodules. Keep `git submodule update --init --recursive`
  in `postCreateCommand` so fresh containers are ready to build.
- If you add new submodules, update `.gitmodules` and re-run submodule sync.
