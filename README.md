<p align="center">
    <img width="220" height="220" aligh="center" alt="image" src="https://github.com/user-attachments/assets/6033bc0a-5cb0-4e9b-92a6-5e2bfdecfd38" />
</p>


# Capsule

A CLI to manage [devcontainer](https://containers.dev) templates from one place. Add a template once, run it in any project with a single command.
<p align="center">
    <img width="840" alt="capsule_demo(1)" src="https://github.com/user-attachments/assets/d23ae0a3-2dc6-4cb0-b0b6-d511f437c849" />
</p>

```sh
cd ~/projects/myapp
capsule run python    # start the stored "python" template, open a shell inside
```

Need project-specific tweaks? Fork the template into the project in one step:

```sh
capsule init python   # copy "python" into ./.devcontainer/
capsule run           # local .devcontainer/ takes precedence
```

## Contents

- [Installation](#installation)
- [Quick start](#quick-start)
- [How `capsule run` works](#how-capsule-run-works)
- [Configuration](#configuration)
- [Command reference](#command-reference)
- [Troubleshooting](#troubleshooting)

## Installation

### Pre-built binary (recommended)

Linux and macOS (auto-detects OS and architecture, installs to `~/.local/bin`):

```sh
curl -fsSL https://raw.githubusercontent.com/rachartier/capsule/main/install.sh | bash
```

Or download manually from the [releases page](https://github.com/rachartier/capsule/releases).

Then install the devcontainer CLI:

```sh
npm install -g @devcontainers/cli
```

### From source

```sh
uv tool install --editable /path/to/capsule
npm install -g @devcontainers/cli
```

Requires Python 3.13+, [uv](https://github.com/astral-sh/uv), and the [devcontainer CLI](https://github.com/devcontainers/cli).

## Quick start

Pull all shipped templates:

```sh
capsule add gh:rachartier/capsule/templates
```

Then run one from any project directory (in this example a python project):

```sh
capsule run python
```

### Adding individual templates

Point at a single template directory (local, shorthand, or full URL):

```sh
capsule add gh:rachartier/capsule/templates/python
capsule add https://github.com/rachartier/capsule/tree/main/templates/rust
capsule add templates/python                              # local path
capsule add ~/projects/myapp/.devcontainer --name myapp  # local, custom name
```

For generic git remotes use `--subpath` and `--ref`:

```sh
capsule add git@mygitlab.com:team/devcontainers.git --subpath python --ref stable
```

Authentication uses your existing git setup (SSH keys, credential helpers, netrc). No token configuration needed.

## How `capsule run` works

If a `.devcontainer/devcontainer.json` exists in the current directory, it is used. Otherwise the named template is used directly from the store, with no copy step.

```sh
capsule run python                   # use stored template
capsule run                          # use local .devcontainer/
capsule run --rebuild                # destroy and recreate the container after edits
```

Under the hood Capsule calls `devcontainer up` to start the container and run its lifecycle hooks, then `devcontainer exec` to drop you into an interactive shell. Mounts and env from `config.toml` are passed through as flags. Subsequent runs reuse the existing container.

## Configuration

Capsule reads `~/.config/capsule/config.toml` (or `$XDG_CONFIG_HOME/capsule/config.toml`). Generate the file with defaults:

```sh
capsule config init
```

The file is optional; all settings have defaults.

`$VAR` references in `[env]` values and mount source paths are expanded from the host shell at runtime. `~` in source paths is also expanded.

Templates are stored in `~/.config/capsule/templates/`. Logs go to `~/.config/capsule/capsule.log`.

```toml
[dotfiles]
# Personal config files mounted into every container.
# Format: "host_path:container_path[:options]"
# ~ and $VAR in host_path are expanded at runtime.
# Microsoft devcontainer images use /home/vscode; root-based images use /root.
mounts = [
    # "~/.bashrc:/root/.bashrc:ro",
    # "~/.gitconfig:/root/.gitconfig:ro",
    # "~/.ssh:/root/.ssh:ro",
]

[volumes]
# Additional bind mounts applied to every container.
# Format: "host_path:container_path[:options]"
mounts = []

[env]
# Environment variables injected into every container.
# $VAR values are expanded from the host shell at runtime.
# TERM = "xterm-256color"
# DISPLAY = "$DISPLAY"

[run]
# Shell launched inside the container by `capsule run`.
shell = "/bin/bash"
# Suppress devcontainer output while starting (spinner shown instead).
# Output is always printed on failure regardless of this setting.
quiet = false
```

### `[dotfiles]`

Mounts applied to every container for personal config files. Kept separate from `[volumes]` so they are not confused with project data.

```toml
[dotfiles]
mounts = [
    "~/.bashrc:/root/.bashrc:ro",
    "~/.gitconfig:/root/.gitconfig:ro",
    "~/.ssh:/root/.ssh:ro",
]
```

Format: `"host_path:container_path[:options]"`. The container path must match the container user's home directory. Microsoft devcontainer images use `/home/vscode`; root-based images use `/root`.

Default: `[]`

### `[volumes]`

Additional bind mounts applied to every container, separate from dotfiles.

```toml
[volumes]
mounts = [
    "/data:/data:ro",
]
```

Same format as `[dotfiles]`. Both lists are merged and passed to `devcontainer up` as bind mounts.

Default: `[]`

### `[env]`

Environment variables injected into every container. Accepts any key-value pairs.

```toml
[env]
TERM = "xterm-256color"
DISPLAY = "$DISPLAY"
```

Values are shell-expanded at runtime, so `"$DISPLAY"` forwards whatever the launching shell carries.

Default: none

### `[run]`

```toml
[run]
shell = "/bin/bash"
quiet = false
```

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `shell` | string | `/bin/bash` | Shell launched inside the container by `capsule run`. |
| `quiet` | bool | `false` | Suppress `devcontainer up` output while starting. A spinner is shown instead. If the command fails, the captured output is printed so the error is always visible.

## Command reference

### Template management

| Command | What it does |
| --- | --- |
| `capsule list` | List stored templates with description and last modified date. |
| `capsule add <source> [--name <n>] [--ref <ref>] [--subpath <dir>]` | Store a template from a local directory, `gh:owner/repo[/subpath]`, or any git URL. `--ref` overrides branch/tag, `--subpath` selects a subdirectory. |
| `capsule view <template>` | Pretty-print a template's `devcontainer.json`. |
| `capsule edit <template>` | Open a template's `devcontainer.json` in `$EDITOR`. |
| `capsule meta <template> [--description <d>] [--author <a>]` | View or set metadata (description, author) for a template. |
| `capsule search <keyword>` | Case-insensitive search across all templates' `devcontainer.json`. |
| `capsule update <path> [--name <n>]` | Replace the `devcontainer.json` in a stored template from a folder. |
| `capsule rename <old> <new>` | Rename a stored template. |
| `capsule delete <template> [--force]` | Delete a stored template. |
| `capsule export <template> [--output <dir>]` | Export a template as a `.zip` archive. |
| `capsule pull <template>` | Re-fetch a template from its recorded git source and replace it in the store. |

### Running containers

| Command | What it does |
| --- | --- |
| `capsule init <template> [--output <dir>] [--force]` | Copy a template into the current project as `.devcontainer/`. |
| `capsule run [<template>] [--shell <sh>] [--rebuild] [--dry-run]` | Start the devcontainer and open a shell. `--dry-run` prints the commands without executing. |
| `capsule exec [<template>] <command...> [--rebuild]` | Run a one-shot command in the devcontainer. Uses local `.devcontainer/` if present, otherwise the first positional is the template name. |
| `capsule ps` | List all capsule devcontainers (running and stopped). |
| `capsule stop [<workspace>] [--force] [--rm]` | Stop the devcontainer for the current directory or given workspace path. `--force` skips confirmation, `--rm` removes the container. |

### Configuration and diagnostics

| Command | What it does |
| --- | --- |
| `capsule config` | Show resolved config from `config.toml`. |
| `capsule config init [--force]` | Generate a default `config.toml` in the capsule config directory. |
| `capsule doctor` | Check that the environment is healthy: devcontainer CLI, container runtime, all stored templates, and `config.toml` validity. |

### Template metadata

Annotate stored templates with a description and author:

```sh
capsule meta python --description "Python 3.12 with uv" --author "Alice"
capsule meta python       # view current metadata
capsule list              # description column shown in the listing
```

Metadata is stored in `capsule.toml` inside the template directory alongside git provenance.

### Dry-run mode

Preview the `devcontainer` commands that `capsule run` would execute without starting anything:

```sh
capsule run python --dry-run
```

## Troubleshooting

### X11 graphics on WSL2

Add the X11 socket mount and set `DISPLAY` in `~/.config/capsule/config.toml`.

**WSLg** (Windows 11, built-in X server, `DISPLAY` is always `:0`):

```toml
[volumes]
mounts = ["/tmp/.X11-unix:/tmp/.X11-unix"]

[env]
DISPLAY = ":0"
WAYLAND_DISPLAY = "wayland-0"
XDG_RUNTIME_DIR = "/mnt/wslg/runtime-dir"
```

**Legacy WSL2** (VcXsrv, X410, `DISPLAY` is a dynamic Windows host IP):

```toml
[volumes]
mounts = ["/tmp/.X11-unix:/tmp/.X11-unix"]

[env]
DISPLAY = "$DISPLAY"
```
