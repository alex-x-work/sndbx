FROM ubuntu-build:26.08.17

RUN mkdir ~/.config
RUN curl -fsSL https://opencode.ai/install | bash

ENV PATH=${HOME}/.opencode/bin:$PATH

WORKDIR /workspace
