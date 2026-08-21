# BUILD

Build the base image first, then the claude/opencode images (they're `FROM ubuntu-build:<tag>`).

## 1. Base image

docker build --no-cache -t ubuntu-build:latest .

## 2. Claude / OpenCode images

docker build -t claude ./claude-code
docker build -t opencode ./opencode
docker build -t dsh ./dsh

# USAGE

## CLAUDE-CODE

### Config directory ~/.claude_docker
docker run \
  --rm -it \
  -v ".:/workspace" \
  -v "$HOME/.claude_docker:/home/ubuntu/.claude" \
  claude

## OPENCODE

### Config directory ~/.opencode_docker
docker run \
  --rm -it \
  -v ".:/workspace" \
  -v "$HOME/.opencode_docker:/home/ubuntu/.config/opencode" \
  opencode

## DSH
### Config directory ~/.dsh_docker
docker run \
  --rm -it \
  -p 3080:3080 \
  -v ".:/workspace" \
  -v "$HOME/.dsh_docker:/home/ubuntu/.dsh" \
  dsh
