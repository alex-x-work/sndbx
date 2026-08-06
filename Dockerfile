FROM ubuntu:26.04

RUN apt-get update && apt-get install -y --no-install-recommends \
  curl ca-certificates git openssh-client sudo bash jq iputils-ping \
  && rm -rf /var/lib/apt/lists/*

USER ubuntu
WORKDIR /home/ubuntu
ENV HOME=/home/ubuntu

RUN curl -fsSL https://opencode.ai/install | bash

ENV PATH=/home/ubuntu/.opencode/bin:$PATH
