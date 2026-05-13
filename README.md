<p align="center">
    <img width="220" height="220" aligh="center" alt="image" src="https://github.com/user-attachments/assets/f50dadd4-66f2-4402-9ee5-57f2b86d1521" />
</p>


# Capsule

A CLI for managing [devcontainer](https://containers.dev) templates. Save a devcontainer setup once, reuse it in any project.

```sh
cd ~/projects/myapp
capsule run python    # start the stored "python" template, open a shell inside
```

To customize the devcontainer for this project, copy the template into `.devcontainer/` first and edit it:

```sh
capsule init python
$EDITOR .devcontainer/devcontainer.json
capsule run           # picks up the local .devcontainer/ automatically
```

## Install

```sh
uv tool install --editable /path/to/capsule
npm install -g @devcontainers/cli
```

Requires Python 3.13+, [uv](https://github.com/astral-sh/uv), and the [devcontainer CLI](https://github.com/devcontainers/cli).

### Getting templates

The repo ships templates under `templates/`. Add them all at once:

```sh
for d in templates/*/; do capsule add "$d"; done
```

Or add just the ones you need:

```sh
capsule add templates/python
capsule add templates/python-qt
```

To add your own template, point `capsule add` at any directory that contains a `devcontainer.json`:

```sh
capsule add ~/projects/myapp/.devcontainer --name myapp
```

## Configure

Create `~/.config/capsule/config.toml`. A full example lives at [`templates/config.toml`](templates/config.toml).

```toml
[dotfiles]
# Mounted into every container. Editor config, shell rc, git, ssh.
mounts = [
    "~/.bashrc:/root/.bashrc:ro",
    "~/.gitconfig:/root/.gitconfig:ro",
    "~/.ssh:/root/.ssh:ro",
]

[env]
TERM = "xterm-256color"

[run]
shell = "/bin/bash"
```

Templates live in `~/.config/capsule/templates/` (respects `$XDG_CONFIG_HOME`). Logs go to `~/.config/capsule/capsule.log`.

## How `capsule run` works

If a `.devcontainer/devcontainer.json` exists in the current directory, it is used. Otherwise the named template is used directly from the store, with no copy step.

```sh
capsule run python                   # use stored template
capsule run                          # use local .devcontainer/
capsule run --rebuild                # destroy and recreate the container after edits
```

Under the hood it calls `devcontainer up` to start the container and run its lifecycle hooks, then `devcontainer exec` to drop you into an interactive shell. Mounts and env from `config.toml` are passed through as flags. Subsequent runs reuse the existing container.

## Commands

| Command | What it does |
| --- | --- |
| `capsule list` | List stored templates with path and last modified date. |
| `capsule add <path> [--name <n>]` | Store a directory (must contain `devcontainer.json`) as a template. |
| `capsule init <template> [--output <dir>] [--force]` | Copy a template into the current project as `.devcontainer/`. |
| `capsule run [<template>] [--shell <sh>] [--rebuild]` | Start the devcontainer and open a shell. |
| `capsule view <template>` | Pretty-print a template's `devcontainer.json`. |
| `capsule search <keyword>` | Case-insensitive search across all templates' `devcontainer.json`. |
| `capsule update <path> [--name <n>]` | Replace the `devcontainer.json` in a stored template from a folder. |
| `capsule delete <template> [--force]` | Delete a stored template. |
| `capsule export <template> [--output <dir>]` | Export a template as a `.zip` archive. |
| `capsule config` | Show resolved config from `config.toml`. |

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

`$VAR` references in `[env]` values and mount source paths are expanded from the host shell at runtime, so `DISPLAY = "$DISPLAY"` forwards whatever value WSL2 set in the launching shell.

## Examples

```sh
capsule add ./my-devcontainer --name python-custom
capsule init python --force
capsule run python --shell /bin/bash
capsule search ghcr.io
capsule export python --output ~/backups
```

`capsule run` without a template argument uses the local `.devcontainer/` if present. Pass a template name to run directly from the store without copying it into the project first.
