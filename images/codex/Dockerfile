ARG TAG_PREFIX=sndbx
FROM ${TAG_PREFIX}:base

RUN npm install -g @openai/codex \
  && ~/.local/bin/mise reshim

ENV CODEX_HOME=${HOME}/.codex

WORKDIR /workspace

CMD ["codex"]
