FROM ubuntu:26.10

ARG USER=ubuntu

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
  curl ca-certificates git openssh-client jq iputils-ping \
  nodejs npm ruby python3 python3-pip \
  libglib2.0-0t64 libnspr4 libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 \
  libxkbcommon0 libasound2t64 libgbm1 libxcomposite1 libxdamage1 \
  libxfixes3 libxrandr2 libatspi2.0-0t64 \
  && rm -rf /var/lib/apt/lists/*

USER ${USER}
ENV HOME=/home/${USER}
ENV NPM_CONFIG_PREFIX="$HOME/.node_modules"

RUN npm config set prefix ${NPM_CONFIG_PREFIX}
RUN npm install -g npm@latest pnpm chromium playwright

ENV PATH=${NPM_CONFIG_PREFIX}/bin:$PATH

WORKDIR ${HOME}
