FROM ubuntu:26.04

SHELL ["/bin/bash", "-c"]

ARG USER=ubuntu
ARG NVM_VERSION=v0.40.6
ARG NODE_VERSION=24

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
  curl ca-certificates git openssh-client sudo bash jq iputils-ping \
  && rm -rf /var/lib/apt/lists/*

USER ${USER}
ENV HOME=/home/${USER}

WORKDIR ${HOME}

RUN curl -fsSL https://claude.ai/install.sh | bash
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash
RUN source ${HOME}/.nvm/nvm.sh \
  && nvm install ${NODE_VERSION}

ENV CLAUDE_CONFIG_DIR=${HOME}/.claude
ENV PATH=${HOME}/.local/bin:$PATH

WORKDIR /workspace
