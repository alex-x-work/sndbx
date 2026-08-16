FROM ubuntu-build:26.08.15

ARG USER=ubuntu

USER ${USER}
ENV HOME=/home/${USER}

WORKDIR ${HOME}

RUN curl -fsSL https://claude.ai/install.sh | bash

ENV CLAUDE_CONFIG_DIR=${HOME}/.claude
ENV PATH=${HOME}/.local/bin:$PATH

WORKDIR /workspace
