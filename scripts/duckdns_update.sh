#!/usr/bin/env bash
# DuckDNS DDNS 更新脚本：把 suicardgame.duckdns.org 指向本机当前公网 IP
# token 从同目录下的 token 文件读取（600 权限），不硬编码在命令行。
set -euo pipefail

DOMAIN="suicardgame"
TOKEN_FILE="/home/suicardgame/.duckdns_token"

if [[ ! -f "$TOKEN_FILE" ]]; then
    echo "token 文件不存在: $TOKEN_FILE" >&2
    exit 1
fi
TOKEN="$(tr -d '[:space:]' < "$TOKEN_FILE")"

# 获取当前公网 IP（若已有缓存则用缓存，避免频繁外呼）
IP="${1:-}"
if [[ -z "$IP" ]]; then
    IP="$(curl -fsS --max-time 15 https://api.ipify.org 2>/dev/null || curl -fsS --max-time 15 http://ifconfig.me 2>/dev/null || true)"
fi
if [[ -z "$IP" ]]; then
    echo "无法获取公网 IP" >&2
    exit 1
fi

# 调用 DuckDNS update API；返回 "OK" 即成功
RESULT="$(curl -fsS --max-time 15 "https://www.duckdns.org/update?domains=${DOMAIN}&token=${TOKEN}&ip=${IP}" 2>/dev/null || true)"
echo "$(date '+%Y-%m-%d %H:%M:%S') duckdns update ip=${IP} result=${RESULT:-EMPTY}"
