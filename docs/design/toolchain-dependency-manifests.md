# Toolchain dependency manifests

Source dependency discovery belongs to the tool that parses the source format.
The build runner must not scan MyLang or MyAssembly syntax itself.

## Ownership

- `mlc` resolves MyLang `import ... from` paths, including project aliases.
- `myas` resolves MyAssembly `import ... from` paths relative to the assembly
  source file.
- `build_toolchain.py` consumes dependency manifests, schedules the discovered
  sources, and invokes the tools.
- `mllinker` receives object files and resolves symbols. It does not locate or
  parse source files.

Both source tools accept `--depfile <path>` and write direct dependencies only.
The build runner computes the transitive closure with a canonical-path work
queue, which also removes duplicates and terminates cycles.

## `MYDEPS 1` format

The manifest is UTF-8 text:

```text
MYDEPS 1
mln<TAB>/absolute/canonical/module.mln
masm<TAB>/absolute/canonical/runtime.masm
```

The first line is the format/version marker. Each remaining line is a kind,
one literal tab (`<TAB>` above), and an absolute canonical path. Supported
kinds are `mln` and `masm`.
Paths containing tabs or newlines are rejected.

The manifest is a build artifact: absolute paths are intentional and are not
stored in distributable objects. Object files contain symbols and relocations,
not source dependencies.

Directory enumeration and `--exclude` remain build-runner concerns. Exclusion
applies to roots found by directory enumeration; a dependency explicitly
imported by a root is still built.
