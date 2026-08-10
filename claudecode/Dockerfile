FROM ubuntu:26.04

ARG USER=ubuntu

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
  curl ca-certificates git openssh-client sudo bash jq iputils-ping nodejs \
  && rm -rf /var/lib/apt/lists/*

USER ${USER}
WORKDIR /home/${USER}
ENV HOME=/home/${USER}

RUN curl -fsSL https://claude.ai/install.sh | bash

ENV CLAUDE_CONFIG_DIR=/home/${USER}/.claude
ENV PATH=/home/${USER}/.local/bin:$PATH

WORKDIR /workspace
