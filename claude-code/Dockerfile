FROM ubuntu-build:latest

RUN curl -fsSL https://claude.ai/install.sh | bash

ENV CLAUDE_CONFIG_DIR=${HOME}/.claude
ENV PATH=${HOME}/.local/bin:$PATH

WORKDIR /workspace
