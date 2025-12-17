FROM python:3.12-slim

# uvのインストール
RUN pip install uv

# cronのインストール
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# スクリプトをコピー
COPY scripts/ /app/scripts/

# crontabをコピー
COPY crontab /etc/cron.d/scp-jp-scripts
RUN chmod 0644 /etc/cron.d/scp-jp-scripts
RUN crontab /etc/cron.d/scp-jp-scripts


# ログ用ディレクトリ
RUN mkdir -p /var/log/scp-jp-scripts

# 環境変数をcronに渡すためのスクリプト
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
