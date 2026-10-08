FROM sndbx:base

RUN npm install -g @openai/codex \
  && ~/.local/bin/mise reshim

ENV CODEX_HOME=${HOME}/.codex

WORKDIR /workspace

CMD ["codex"]
