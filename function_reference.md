# Function reference

A file-by-file and alphabetical map of the code in this repository. Each chapter
is a standalone package, so some modules intentionally appear more than once
(for example `path_policy.py` in chapters 1–5). When a reference and the
implementation disagree, the implementation and its tests win.

## Where to start

1. Read `ch05/mini_harness/agent.py` for the loop.
2. Read `ch05/mini_harness/toolbox.py` for the dispatch point.
3. Read `ch02/mini_harness/sandbox.py` for the file contract.
4. Read `ch01/mini_harness/path_policy.py` for path containment.
5. Read `ch04/mini_harness/docker_runner.py` for the container recipe.

## File map

### `ch00/mini_harness/unsafe.py`

The intentionally broken fence. Do not reuse.

| Name | Contract |
|---|---|
| `read_file(root, relative) -> str` | Joins and `abspath`s, checks a string prefix, reads all bytes as text. Allows symlink and prefix-sibling escapes. |
| `list_files(root, relative=".") -> list[str]` | Same naive check; returns sorted entry names. |
| `run_shell(root, command, timeout=None)` | `subprocess.run(..., shell=True)`, inherited env, no default timeout, unbounded output. |
| `_naive_inside(root, candidate)` | The bug in isolation: `candidate.startswith(root)`. |
| `_join(root, relative)` | `os.path.abspath(os.path.join(root, relative))`. |

### `ch01/mini_harness/path_policy.py`

| Name | Contract |
|---|---|
| `PolicyError(message, requested=None)` | Stable `code = "PATH"`; `str()` renders `PATH: reason`. |
| `ResolvedPath(requested, absolute, relative)` | Frozen result. `absolute` is canonical; `relative` uses `/`. |
| `expand_variables(text, env=None)` | Expands `~`, `%VAR%`, `$VAR`/`${VAR}` textually. Validation happens afterwards. |
| `PathPolicy(root, create=True)` | Creates/canonicalises the root; stores `root` and `real_root`. |
| `PathPolicy.resolve_read(requested)` | Allows absolute names inside the root; resolves symlinks; returns `ResolvedPath`. |
| `PathPolicy.resolve_write(requested)` | Requires a relative name; refuses symlink targets and the root; returns `ResolvedPath`. |
| `PathPolicy.is_inside(path)` | Canonical containment test. |
| `PathPolicy.relative(absolute)` | Model-facing path with forward slashes. |
| `realpath_best(path)` | Public wrapper for resolve-deepest-existing-ancestor. |

Internal helpers: `_realpath_best`, `_check_reserved_name`,
`_normalise_separators`, `_is_absolute_text`, `_comparison_form`.

### `ch02/mini_harness/sandbox.py`

| Name | Contract |
|---|---|
| `SandboxError(code, message, path=None)` | Stable code: `PATH`, `NOT_FOUND`, `IS_DIR`, `NOT_DIR`, `TOO_LARGE`, `EXISTS`, `NO_MATCH`, `AMBIGUOUS`, `IO`. |
| `Limits(max_read_bytes=2MiB, max_write_bytes=1MiB, max_dir_entries=500, max_line_bytes=4000)` | Frozen policy caps. |
| `DirEntry(name, kind, size)` | `kind` is `file`, `dir`, `link` or `other`. |
| `Sandbox(root, limits=None)` | Wraps `PathPolicy`; exposes `root` and `limits`. |
| `Sandbox.read_text(relative)` | `stat` size check, byte read, UTF-8 replace; refuses directories. |
| `Sandbox.list_dir(relative=".")` | Sorted, capped listing; does not follow entry links. |
| `Sandbox.write_text(relative, content, overwrite=True)` | Size check, parent creation, temp file + fsync + `os.replace`; create-only option. |
| `Sandbox.edit_text(relative, old, new, count=1)` | Unique-match by default; `count=0` replaces all. |
| `Sandbox.delete_file(relative)` | Regular files only; refuses directories and non-regular files. |

### `ch02/mini_harness/file_tools.py`

| Name | Contract |
|---|---|
| `ToolSpec(name, description, args)` | Prompt-visible tool contract. |
| `TOOL_SPECS` | `list_files`, `read_file`, `write_file`, `edit_file`, `delete_file`. |
| `tool_names() -> list[str]` | Names in prompt order. |
| `run_tool(sandbox, name, args=None) -> str` | Dispatches; returns `OK...`, `ERROR[CODE]...` or `ERROR[INTERNAL]...`; never raises. |

Argument helpers: `_arg`, `_string_arg`. Rendering: `_format_read` (line
numbers, line cap, truncation marker).

### `ch03/mini_harness/local_runner.py`

| Name | Contract |
|---|---|
| `CommandError(code, message)` | Codes: `DENIED`, `ARGS`, `CWD`, `IO`. |
| `Limits(...)` | Timeout, output cap, arg caps, CPU, memory, file size, fds, processes. |
| `CommandPolicy(allowed)` | Logical name → absolute executable. |
| `CommandPolicy.resolve(program)` | Exact allowlist lookup; missing executable is `IO`. |
| `default_command_policy()` | Allows the running Python as `python` (and `python3` on POSIX). |
| `CommandResult(...)` | `program`, `argv`, `returncode`, `stdout`, `stderr`, `timed_out`, `truncated`, `duration_seconds`, `ok`. |
| `CommandRunner(root, policy=None, limits=None)` | Policy-checked cwd; one command at a time. |
| `CommandRunner.run(program, args=None, cwd=".")` | List argv only; clean env; timeout; tree kill; bounded capture; POSIX rlimits. |
| `resolve_real_executable(program)` | Documentation helper showing what `shutil.which` would return; the runner does **not** use it. |

### `ch03/mini_harness/command_tool.py`

| Name | Contract |
|---|---|
| `format_result(result)` | Status header, stdout/stderr sections, empty markers, truncation flag. |
| `run_command_tool(runner, args)` | Accepts `argv` and optional `cwd`; returns `OK...`, `ERROR[ARGS]`, `ERROR[DENIED]`, `ERROR[CWD]`, `ERROR[TIMEOUT]`, `ERROR[EXIT]`. |

### `ch04/mini_harness/docker_runner.py`

| Name | Contract |
|---|---|
| `DockerError(code, message)` | Codes: `DOCKER_MISSING`, `BUILD_FAILED`, `RUN_FAILED`, `ARGS`, `CWD`, `ENV`, `CONFIG`. Timeouts are returned as a `RunResult` with `timed_out=True`. |
| `DockerConfig(...)` | Image, user, memory, cpus, pids, nofile, timeout, output cap, workspace mode, tmpfs, network, read-only root, init, extra env. |
| `DockerConfig.validate()` | Refuses network other than `none`, writable root, bad user/limits. |
| `RunResult(...)` | `argv`, `container_name`, `returncode`, streams, timeout/truncation flags, duration, `ok`. |
| `DockerRunner(root, config=None, docker=None)` | Resolves CLI and workspace; caches availability. |
| `DockerRunner.check_available() -> bool` | `docker version --format {{.Server.Version}}`. |
| `DockerRunner.require_available()` | Raises `DOCKER_MISSING`. |
| `DockerRunner.build(context, dockerfile=None, tag=None, no_cache=False, timeout=600)` | Explicit image build; returns output. |
| `DockerRunner.image_exists(image=None) -> bool` | `docker image inspect`; no pull. |
| `DockerRunner.build_command(argv, cwd=".", name=None, env=None) -> list[str]` | Pure recipe builder; asserts every hardening flag offline. |
| `DockerRunner.run(argv, cwd=".", env=None, name=None) -> RunResult` | Starts the CLI, captures bounded output, removes the named container on timeout. |

### `ch05/mini_harness/toolbox.py`

| Name | Contract |
|---|---|
| `FILE_TOOL_NAMES` | Derived from `file_tools.TOOL_SPECS`. |
| `Toolbox(sandbox, runner)` | File tools + `run_command`. |
| `Toolbox.specs()` | Combined prompt contract. |
| `Toolbox.run(name, args=None)` | Routes; unknown tool returns `ERROR[UNKNOWN_TOOL]`. |

### `ch05/mini_harness/docker_tools.py`

| Name | Contract |
|---|---|
| `DockerToolSpec(name, description, args)` | Prompt-visible command contract. |
| `RUN_COMMAND_SPEC` | The `run_command` spec (`argv`, `cwd`). |
| `format_result(result)` | Same presentation shape as ch03, with container status. |
| `run_command_tool(runner, args)` | Validates `argv`/`cwd`; runs `DockerRunner.run(argv, cwd=...)`; maps errors to observations. |

### `ch05/mini_harness/audit.py`

| Name | Contract |
|---|---|
| `AuditError` | Malformed log, chain failure, or append failure. |
| `AuditLog(path)` | Creates parent; loads and verifies an existing tail before appending. |
| `AuditLog.record(action, outcome, detail=None) -> dict` | Appends one event, computes `prev`/`hash`, fsyncs. |
| `AuditLog.events() -> list[dict]` | Reads JSONL; malformed line raises. |
| `AuditLog.verify() -> bool` | Recomputes the sequence and hash chain. |
| `_redact(value, key=None)` | Masks secret-looking keys and truncates long strings. |

### `ch05/mini_harness/agent.py`

| Name | Contract |
|---|---|
| `ModelReply(kind, text="", tool=None, args={})` | `kind` is `final` or `tool`. |
| `ModelReply.final(text)` / `ModelReply.call(tool, args=None)` | Constructors. |
| `Model` | Protocol: `reply(messages, tools) -> ModelReply`. |
| `ScriptedModel(replies)` | Consumes a list; returns a final answer when empty; `calls` counts. |
| `AgentResult(text, steps, stopped, transcript, observations)` | Stop reason is `final`, `max_steps` or `error`. |
| `Agent(toolbox, model, audit, max_steps=8)` | Runs the loop. |
| `Agent.run(task) -> AgentResult` | Audits start, calls, results, final/max-step/error. |

### `ch05/mini_harness/cli.py`

| Name | Contract |
|---|---|
| `_parser()` | `--demo`, `--build`, `--workspace`, `--max-steps`. |
| `run_demo(workspace, build=False, max_steps=8) -> int` | Build (optional), run the scripted scenario, print transcript and audit verification. |
| `main(argv=None) -> int` | Uses a temporary workspace by default; returns 0 on a normal demo. |

### `ch00`–`ch05` demos

Each `mini_harness/demo.py` is a runnable walkthrough, not part of the public
API. Run it with `python -m mini_harness.demo` or directly with
`uv run mini_harness/demo.py`. Stage 5 uses `mini_harness/__main__.py` instead.

### `ch00/mini_harness/ui.py` (identical in every chapter)

| Name | Contract |
|---|---|
| `Theme(accent, success, warning, error, info, muted, title, box_name, icons)` | Frozen palette. Load presets and environment overrides with `Theme.from_env(accent=...)`. |
| `Theme.from_env(accent=None)` | Supports `MINI_HARNESS_THEME=dark\|light\|mono` and the `MINI_HARNESS_*` colour variables. |
| `UI(theme=None, accent=None, title=None, console=None)` | Wraps a Rich `Console`; per-chapter accent wins over the environment. |
| `UI.header(title=None, subtitle=None, badge=None)` | Chapter banner panel. |
| `UI.section(title)` | Coloured rule between demo sections. |
| `UI.note(label, message, kind="info", icon=None)` | Coloured card for notes, warnings, skips and errors. |
| `UI.result(label, text, kind=None)` | Observation card; infers `OK`, `ERROR`, `TIMEOUT` and `SKIP`. |
| `UI.explain(title, what, why, kind="accent")` | Teaching card after each output section: what happened and why it matters. |
| `UI.command(argv, cwd=None, title="command")` | Wrapped command panel with display-safe quoting. |
| `UI.table(title, headers, rows)` | Compact table using the shared palette. |
| `UI.done(message)` | Closing success card. |

## Alphabetical index

| Name | Chapter | Kind |
|---|---|---|
| `Agent` | 5 | class |
| `AgentResult` | 5 | dataclass |
| `AuditError` | 5 | exception |
| `AuditLog` | 5 | class |
| `CommandError` | 3 | exception |
| `CommandPolicy` | 3 | dataclass |
| `CommandResult` | 3 | dataclass |
| `CommandRunner` | 3 | class |
| `DirEntry` | 2 | dataclass |
| `DockerConfig` | 4 | dataclass |
| `DockerError` | 4 | exception |
| `DockerRunner` | 4 | class |
| `DockerToolSpec` | 5 | dataclass |
| `Limits` | 2, 3 | frozen dataclass |
| `Model` | 5 | protocol |
| `ModelReply` | 5 | frozen dataclass |
| `PathPolicy` | 1–5 | class |
| `PolicyError` | 1–5 | exception |
| `ResolvedPath` | 1–5 | frozen dataclass |
| `RunResult` | 4 | frozen dataclass |
| `RUN_COMMAND_SPEC` | 5 | constant |
| `Sandbox` | 2, 5 | class |
| `SandboxError` | 2, 5 | exception |
| `ScriptedModel` | 5 | class |
| `Theme` | 0–5 | frozen dataclass |
| `ToolSpec` | 2, 5 | frozen dataclass |
| `Toolbox` | 5 | class |
| `TOOL_SPECS` | 2, 5 | constant |
| `UI` | 0–5 | class |
| `default_command_policy()` | 3 | function |
| `expand_variables(text, env=None)` | 1–5 | function |
| `format_result(result)` | 3, 5 | function |
| `realpath_best(path)` | 1–5 | function |
| `resolve_real_executable(program)` | 3 | function |
| `run_command_tool(runner, args)` | 3, 5 | function |
| `run_demo(workspace, ...)` | 5 | function |
| `run_shell(root, command, timeout=None)` | 0 | unsafe function |
| `run_tool(sandbox, name, args=None)` | 2, 5 | function |
| `tool_names()` | 2, 5 | function |

## Observation vocabulary

| Prefix | Meaning |
|---|---|
| `OK` | The tool completed and the result is in the text. |
| `ERROR[ARGS]` | Missing, wrong-typed or malformed tool arguments. |
| `ERROR[PATH]` | The path policy refused the target. |
| `ERROR[NOT_FOUND]` | The file or folder does not exist. |
| `ERROR[IS_DIR]` / `ERROR[NOT_DIR]` | Wrong file type for the operation. |
| `ERROR[TOO_LARGE]` | A byte or entry cap was exceeded. |
| `ERROR[EXISTS]` | Create-only write hit an existing file. |
| `ERROR[NO_MATCH]` / `ERROR[AMBIGUOUS]` | Edit text missing or repeated. |
| `ERROR[DENIED]` | The command program is not allowlisted. |
| `ERROR[CWD]` | The working directory is outside the workspace or missing. |
| `ERROR[TIMEOUT]` | The command exceeded its wall-clock limit. |
| `ERROR[EXIT]` | The command ran and returned non-zero. |
| `ERROR[DOCKER_MISSING]` | The Docker CLI/daemon or image is unavailable. |
| `ERROR[EXIT]` (Docker) | The container command returned non-zero. |
| `ERROR[UNKNOWN_TOOL]` | No tool with that name. |
| `ERROR[INTERNAL]` | An unexpected tool bug was caught at the boundary. |

## Constants worth knowing

| Constant | Where | Value / purpose |
|---|---|---|
| `_WINDOWS_RESERVED` | path policy | `CON`, `PRN`, `AUX`, `NUL`, `COM1-9`, `LPT1-9` |
| `MAX_VALUE_CHARS` | audit | 500-character audit truncation |
| `FILE_TOOL_NAMES` | toolbox | derived file-tool dispatch set |
| `RUN_COMMAND_SPEC` | docker tools | the command tool contract |
| `CHAPTER_DIR` / `DOCKER_DIR` | cli | `ch05` / `ch05/docker` |
