FROM ubuntu:26.10

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
  curl ca-certificates git openssh-client jq iputils-ping \
  chromium-browser nodejs npm \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g npm@latest pnpm
