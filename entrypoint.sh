#!/bin/bash

# 環境変数をcronで使えるようにファイルに書き出す
printenv | grep -E '^(WIKIDOT_|DISCORD_)' > /app/.env

# cronをフォアグラウンドで起動
cron -f
