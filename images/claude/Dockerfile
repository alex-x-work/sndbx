ARG TAG_PREFIX=sndbx
FROM ${TAG_PREFIX}:base

RUN curl -fsSL https://claude.ai/install.sh | bash

ENV CLAUDE_CONFIG_DIR=${HOME}/.claude
ENV PATH=${HOME}/.local/bin:$PATH

WORKDIR /workspace

CMD ["claude"]
