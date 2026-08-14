# BUILD

# Base image
docker build --no-cache -t ubuntu-build:YY.MM.DD .


# USAGE

## CLAUDE-CODE

### Config directory ~/.claude_docker
docker run \
  --rm -it \
  -v ".:/workspace" -v "$HOME/.claude_docker:/home/ubuntu/.claude" \
  claude claude

## OPENCODE

### Config directory ~/.opencode_docker
docker run \
  --rm -it \
  -v ".:/workspace" -v "$HOME/.opencode_docker:/home/ubuntu/.config/opencode" \
  opencode opencode
