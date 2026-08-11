# HOW TO RUN

## Build the image
docker build -t claude:latest .

## Run from a working directory. In this case the session is stored in ~/.claude_docker
docker run --rm -it -v ".:/workspace" -v "$HOME/.claude_docker:/home/ubuntu/.claude" claude:latest claude
