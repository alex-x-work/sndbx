# sndbx

Docker images for running coding agents in a sandbox, plus `sndbx`, a small wrapper around `docker run`.

| Image      | Directory          | Config on host | Config in container             |
| ---------- | ------------------ | -------------- | ------------------------------- |
| `claude`   | `images/claude/`   | `~/.claude`    | `/home/ubuntu/.claude`          |
| `opencode` | `images/opencode/` | `~/.opencode`  | `/home/ubuntu/.config/opencode` |
| `codex`    | `images/codex/`    | `~/.codex`     | `/home/ubuntu/.codex`           |
| `dsh`      | `images/dsh/`      | `~/.dsh`       | `/home/ubuntu/.dsh` (port 3080) |

The host paths are the ones the `docker run` examples below mount. `sndbx` mounts `~/.config/sndbx/<name>` unless an image sets `config_dir`.

`images/opencode/opencode/config.json` is an example opencode config that uses Ollama running on the host. The image doesn't include it, so copy it into opencode's config directory on the host to use it. The examples below pass `--add-host=host.docker.internal:host-gateway` so the container can reach the host on Linux too, where Ollama must also listen beyond loopback, e.g. `OLLAMA_HOST=0.0.0.0 ollama serve`.

All of them are built `FROM sndbx:base`, the base image in `images/base/` (Ubuntu with node, ruby and python via mise, postgres and Playwright dependencies).

The `dsh` image patches out dsh's refusal to listen on `0.0.0.0`, the check upstream added because it "would expose remote code execution to the network". The server has to listen on all interfaces inside the container for a published port to reach it, so publish the port on `127.0.0.1` only, as the examples below do. A plain `-p 3080:3080` lets anyone on your network control the agent.

## Build

`bin/build IMAGE` builds `images/IMAGE/`, always with `--no-cache`. Every image is tagged `sndbx:<directory name>`, e.g. `sndbx:base`, `sndbx:claude`.

```sh
bin/build claude    # build/rebuild sndbx:claude, and sndbx:base first if it doesn't exist yet
bin/build base      # build/rebuild sndbx:base
bin/build --all     # build/rebuild sndbx:base, then every other image
```

`bin/build claude` won't rebuild an existing `sndbx:base`. To pick up base changes, run `bin/build base` before it.

To add an image, create `images/<name>/Dockerfile` starting with `FROM sndbx:base`.

## Run with docker

Each command mounts the current directory at `/workspace` and the image's config directory from the table above.

```sh
docker run --rm -it \
  -v ".:/workspace" \
  -v "$HOME/.claude:/home/ubuntu/.claude" \
  sndbx:claude

docker run --rm -it \
  --add-host=host.docker.internal:host-gateway \
  -v ".:/workspace" \
  -v "$HOME/.opencode:/home/ubuntu/.config/opencode" \
  sndbx:opencode

docker run --rm -it \
  -v ".:/workspace" \
  -v "$HOME/.codex:/home/ubuntu/.codex" \
  sndbx:codex

docker run --rm -it \
  -p 127.0.0.1:3080:3080 \
  -v ".:/workspace" \
  -v "$HOME/.dsh:/home/ubuntu/.dsh" \
  sndbx:dsh
```

## Run with sndbx

`sndbx` does the same with less typing. It:

- mounts the current directory, or each `-v DIR`, at `/workspace/<basename>`
- mounts the image's config directory at `/home/<user>/<config_target>`
- publishes the image's `ports` plus each `-p PORT`

### Install

Put `bin` on `PATH` and source the bash completions, or copy both files wherever you keep them:

```sh
export PATH="/path/to/sndbx/bin:$PATH"
source /path/to/sndbx/completions/_sndbx
```

### Configure

Images are listed in `~/.config/sndbx/settings.yml`. The first run creates an example to edit.

```yaml
images:
  - name: claude
    alias: my-claude:latest # optional, defaults to sndbx:<name>
    user: ubuntu
    config_dir: ~/.claude # optional, defaults to ~/.config/sndbx/<name>
    config_target: .claude # optional, relative to the user's home, defaults to .<name>
    docker_args: ["--memory=8g"] # optional, extra docker run arguments
  - name: opencode
    user: ubuntu
    config_target: .config/opencode
    docker_args: ["--add-host=host.docker.internal:host-gateway"]
  - name: codex
    user: ubuntu
  - name: dsh
    user: ubuntu
    ports: ["127.0.0.1:3080:3080"] # optional, always published; quote them, YAML reads 8080:22 as a number
```

### Use

```sh
sndbx claude                               # mount the current directory
sndbx claude -v ../api -v ../web           # mount several, start in the last one
sndbx claude -v ../api -v ../web -w api    # mount several, start in api
sndbx claude -p 3000 -p 8080:80            # publish ports, 3000 means 3000:3000
sndbx --list                               # print configured image names
sndbx --version
```
