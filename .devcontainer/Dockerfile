FROM mcr.microsoft.com/devcontainers/base:debian

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    gdb \
    git \
    python3 \
    python3-pip \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*
