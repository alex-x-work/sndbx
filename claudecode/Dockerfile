FROM ubuntu:26.04

ARG USER=ubuntu
ARG NODE_VERSION=24

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
  curl ca-certificates git openssh-client jq iputils-ping

RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash
RUN apt install -y nodejs chromium-browser \
  && rm -rf /var/lib/apt/lists/*

USER ${USER}
ENV HOME=/home/${USER}

WORKDIR ${HOME}

RUN curl -fsSL https://claude.ai/install.sh | bash

ENV CLAUDE_CONFIG_DIR=${HOME}/.claude
ENV PATH=${HOME}/.local/bin:$PATH

WORKDIR /workspace
