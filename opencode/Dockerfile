FROM ubuntu-build:26.08.14

ARG USER=ubuntu

USER ${USER}
ENV HOME=/home/${USER}

WORKDIR ${HOME}

RUN curl -fsSL https://opencode.ai/install | bash

ENV PATH=/home/${USER}/.opencode/bin:$PATH

WORKDIR /workspace
