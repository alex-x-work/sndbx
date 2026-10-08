FROM sndbx:base

RUN git clone --depth 1 https://github.com/deepseek-ai/deepseek-harness ~/dsh

WORKDIR ${HOME}/dsh

COPY 0001-Remove-0.0.0.0-check.patch ./

RUN git apply 0001-Remove-0.0.0.0-check.patch
RUN pnpm install \
  && pnpm run build

EXPOSE 3080/tcp

WORKDIR /workspace

CMD exec node ~/dsh/apps/cli/lib/bin.js web --no-open --host 0.0.0.0
