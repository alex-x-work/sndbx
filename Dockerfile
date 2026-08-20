FROM ubuntu:26.10

ARG USER=ubuntu
ARG NVM_VERSION=v0.40.7
ARG NODE_VERSION=v26.7.0

SHELL ["/bin/bash", "-c"]

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
  curl ca-certificates git openssh-client jq iputils-ping gcc \
  ruby python3 python3-pip \
  libglib2.0-0t64 libnspr4 libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 \
  libxkbcommon0 libasound2t64 libgbm1 libxcomposite1 libxdamage1 \
  libxfixes3 libxrandr2 libatspi2.0-0t64 librsvg2-bin \
  && rm -rf /var/lib/apt/lists/*

USER ${USER}
ENV HOME=/home/${USER}

RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh | bash

RUN source ${HOME}/.nvm/nvm.sh \
  && nvm install ${NODE_VERSION} \
  && nvm alias default ${NODE_VERSION} \
  && npm install -g npm@latest pnpm chromium playwright

ENV PATH=${HOME}/.nvm/versions/node/${NODE_VERSION}/bin:$PATH

WORKDIR ${HOME}
