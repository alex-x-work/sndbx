# sbx

Docker images for running coding agents in a sandbox, plus `sbx`, a small wrapper around `docker run`.

| Image      | Directory             | Config on host | Config in container             |
| ---------- | --------------------- | -------------- | ------------------------------- |
| `claude`   | `images/claude-code/` | `~/.claude`    | `/home/ubuntu/.claude`          |
| `opencode` | `images/opencode/`    | `~/.opencode`  | `/home/ubuntu/.config/opencode` |
| `dsh`      | `images/dsh/`         | `~/.dsh`       | `/home/ubuntu/.dsh` (port 3080) |

All three are built `FROM ubuntu-build:latest`, the base image in `images/base/` (Ubuntu with node, ruby and python via mise, postgres and Playwright dependencies).

## Build

Build the base image first, then the others:

```sh
docker build --no-cache -t ubuntu-build:latest ./images/base

docker build -t claude ./images/claude-code
docker build -t opencode ./images/opencode
docker build -t dsh ./images/dsh
```

## Run with docker

Each command mounts the current directory at `/workspace` and the image's config directory from the table above.

```sh
docker run --rm -it \
  -v ".:/workspace" \
  -v "$HOME/.claude:/home/ubuntu/.claude" \
  claude

docker run --rm -it \
  -v ".:/workspace" \
  -v "$HOME/.opencode:/home/ubuntu/.config/opencode" \
  opencode

docker run --rm -it \
  -p 3080:3080 \
  -v ".:/workspace" \
  -v "$HOME/.dsh:/home/ubuntu/.dsh" \
  dsh
```

## Run with sbx

`sbx` does the same with less typing. It:

- mounts the current directory, or each `-v DIR`, at `/workspace/<basename>`
- mounts the image's config directory at `/home/<user>/<config_target>`
- publishes the image's `ports` plus each `-p PORT`

### Install

Put `bin` on `PATH` and source the bash completions, or copy both files wherever you keep them:

```sh
export PATH="/path/to/sbx/bin:$PATH"
source /path/to/sbx/completions/_sbx
```

### Configure

Images are listed in `~/.config/sbx/settings.yml`. The first run creates an example to edit.

```yaml
images:
  - name: claude
    alias: claude:latest # optional, defaults to name
    user: ubuntu
    config_dir: ~/.claude # optional, defaults to ~/.config/sbx/<name>
    config_target: .claude # optional, relative to the user's home, defaults to .<name>
  - name: opencode
    user: ubuntu
    config_dir: ~/.opencode
    config_target: .config/opencode
  - name: dsh
    user: ubuntu
    config_dir: ~/.dsh
    ports: ["3080"] # optional, always published; quote them, YAML reads 8080:22 as a number
```

### Use

```sh
sbx claude                               # mount the current directory
sbx claude -v ../api -v ../web           # mount several, start in the last one
sbx claude -v ../api -v ../web -w api    # mount several, start in api
sbx claude -p 3000 -p 8080:80            # publish ports, 3000 means 3000:3000
sbx --list                               # print configured image names
sbx --version
```
