FROM mcr.microsoft.com/devcontainers/python:3.13

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libegl1 \
    libegl-mesa0 \
    libxcb-xinerama0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-xkb1 \
    libxkbcommon-x11-0 \
    libxcb-shape0 \
    libxcb-cursor0 \
    libdbus-1-3 \
    && rm -rf /var/lib/apt/lists/*
