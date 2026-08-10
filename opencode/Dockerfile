FROM ubuntu:26.04

ARG USER=ubuntu

RUN apt-get update && apt-get install -y --no-install-recommends \
  curl ca-certificates git openssh-client sudo bash jq iputils-ping \
  && rm -rf /var/lib/apt/lists/*

USER ${USER}
WORKDIR /home/${USER}
ENV HOME=/home/${USER}

RUN curl -fsSL https://opencode.ai/install | bash

ENV PATH=/home/${USER}/.opencode/bin:$PATH
