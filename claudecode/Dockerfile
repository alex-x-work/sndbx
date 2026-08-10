FROM ubuntu:26.04

SHELL ["/bin/bash", "-c"]

ARG USER=ubuntu
ARG NODE_VERSION=24

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
  curl ca-certificates git openssh-client sudo bash jq iputils-ping \
  && rm -rf /var/lib/apt/lists/*

USER ${USER}
WORKDIR /home/${USER}
ENV HOME=/home/${USER}

RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.6/install.sh | bash
RUN source /home/ubuntu/.nvm/nvm.sh \
  && nvm install ${NODE_VERSION}

ENV CLAUDE_CONFIG_DIR=/home/${USER}/.claude
ENV PATH=/home/${USER}/.local/bin:$PATH

WORKDIR /workspace
