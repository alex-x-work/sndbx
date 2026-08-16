FROM ubuntu:26.10

ENV DEBIAN_FRONTEND=noninteractive

RUN apt update && apt upgrade -y && apt install -y --no-install-recommends \
  curl ca-certificates git openssh-client jq iputils-ping \
  nodejs npm ruby python3 python3-pip \
  chromium-browser node-playwright libglib2.0-0t64 libnspr4 libnss3 \
  && rm -rf /var/lib/apt/lists/*

RUN npm install -g npm@latest pnpm
