FROM ubuntu-build:26.08.18

RUN mkdir -p ~/.config ~/.local/share
RUN curl -fsSL https://opencode.ai/install | bash

ENV PATH=${HOME}/.opencode/bin:$PATH

WORKDIR /workspace
