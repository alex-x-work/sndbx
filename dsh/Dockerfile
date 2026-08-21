FROM ubuntu-build:latest

RUN git clone https://github.com/deepseek-ai/deepseek-harness ~/dsh

WORKDIR ${HOME}/dsh

COPY 0001-Remove-0.0.0.0-check.patch ./

RUN git apply 0001-Remove-0.0.0.0-check.patch \
  && export ARG DSH_CLIENT_COMMIT_HASH=$(git rev-parse --short HEAD)
RUN pnpm install \
  && pnpm run build

EXPOSE 3080/tcp

CMD [ "pnpm", "dsh", "web", "--no-open", "--host", "0.0.0.0" ]
