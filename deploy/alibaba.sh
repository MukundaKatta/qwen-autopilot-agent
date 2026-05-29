#!/usr/bin/env bash
# Build, run, and push the qwen-autopilot-agent backend image for Alibaba Cloud.
#
#   ./deploy/alibaba.sh build
#   DASHSCOPE_API_KEY=sk-... ./deploy/alibaba.sh run
#   ACR_REGISTRY=registry.<region>.aliyuncs.com ACR_NAMESPACE=<ns> \
#     ACR_USERNAME=<user> ./deploy/alibaba.sh push
#
# After push, create a Function Compute (container) function or an SAE app from
# the pushed image, set DASHSCOPE_API_KEY as a secret, and route to port 8080.
set -euo pipefail

IMAGE="${IMAGE:-qwen-autopilot-agent}"
TAG="${TAG:-latest}"
cmd="${1:-help}"

case "$cmd" in
  build)
    docker build -t "$IMAGE:$TAG" .
    ;;
  run)
    docker run --rm -p 8080:8080 \
      -e DASHSCOPE_API_KEY="${DASHSCOPE_API_KEY:?set DASHSCOPE_API_KEY}" \
      "$IMAGE:$TAG"
    ;;
  push)
    : "${ACR_REGISTRY:?set ACR_REGISTRY (e.g. registry.cn-hangzhou.aliyuncs.com)}"
    : "${ACR_NAMESPACE:?set ACR_NAMESPACE}"
    : "${ACR_USERNAME:?set ACR_USERNAME}"
    docker login --username="$ACR_USERNAME" "$ACR_REGISTRY"
    remote="$ACR_REGISTRY/$ACR_NAMESPACE/$IMAGE:$TAG"
    docker tag "$IMAGE:$TAG" "$remote"
    docker push "$remote"
    echo "pushed $remote"
    echo "next: create an Alibaba Cloud Function Compute (container) function or SAE app from this image, set DASHSCOPE_API_KEY, route to :8080"
    ;;
  *)
    echo "usage: $0 {build|run|push}"
    exit 1
    ;;
esac
