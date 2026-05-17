#!/usr/bin/env bash
set -euo pipefail

REPO="rachartier/capsule"
BIN_DIR="${HOME}/.local/bin"
BIN_NAME="capsule"

detect_platform() {
    local os arch

    case "$(uname -s)" in
        Linux)  os="linux" ;;
        Darwin) os="macos" ;;
        *)      echo "Unsupported OS: $(uname -s)" >&2; exit 1 ;;
    esac

    case "$(uname -m)" in
        x86_64)          arch="amd64" ;;
        aarch64 | arm64) arch="arm64" ;;
        *)               echo "Unsupported architecture: $(uname -m)" >&2; exit 1 ;;
    esac

    echo "${os}-${arch}"
}

latest_version() {
    curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
        | grep '"tag_name"' \
        | sed 's/.*"tag_name": *"\(.*\)".*/\1/'
}

main() {
    local platform version download_url

    platform=$(detect_platform)
    version=$(latest_version)

    download_url="https://github.com/${REPO}/releases/download/${version}/${BIN_NAME}-${platform}"

    echo "Installing capsule ${version} (${platform}) to ${BIN_DIR}..."

    mkdir -p "${BIN_DIR}"
    curl -fsSL "${download_url}" -o "${BIN_DIR}/${BIN_NAME}"
    chmod +x "${BIN_DIR}/${BIN_NAME}"

    echo "Installed: ${BIN_DIR}/${BIN_NAME}"

    if [[ ":${PATH}:" != *":${BIN_DIR}:"* ]]; then
        echo "Warning: ${BIN_DIR} is not in your PATH. Add the following to your shell profile:"
        echo "  export PATH=\"\${HOME}/.local/bin:\${PATH}\""
    fi
}

main
