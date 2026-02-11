# NLM リモート実行 コンテナ仕様

## 1. 目的
- `nlm` をリモート実行するための API サーバ実行基盤をコンテナで提供する。
- APIの仕様・使い方は `docs/spec_api.md` を参照する（本書では重複記載しない）。

## 2. 構成要素
- APIサーバプロセス（HTTP: `:8080`）
- `nlm` CLI
- `bash`（`bash -lc` 実行用）
- Chromium（`nlm login` 用）
- GUIログイン補助（任意）:
  - Xvfb
  - x11vnc
  - noVNC（`:6080`）

## 3. 永続化
- 認証状態は `/root/.notebooklm-mcp-cli` を volume で永続化する。

## 4. 起動方針
- 初回認証は noVNC 経由で手動ログインする。
- 必要なら Chromium を事前起動し、利用不能なら fail-fast で終了する。

## 5. ビルド方針（baseイメージ分離）
- ビルド時間短縮のため、重い依存は `Dockerfile.base` に分離する。
- `Dockerfile.base` で固定する対象:
  - apt依存（Chromium/noVNC/Xvfb など）
  - `uv` と `notebooklm-mcp-cli` 導入
  - Python依存（`requirements.txt`）
- 通常の `Dockerfile` は API アプリ差分のみをビルドする。
- 運用:
  1. 依存更新時のみ base を再ビルド
  2. 日常開発は通常 `Dockerfile` のみ再ビルド

## 6. ネットワーク方針
- 利用範囲は家庭内 LAN 前提。
- 公開ポートは最小化する:
  - `8080`（API）
  - `6080`（noVNC、必要時のみ）

## 7. 最小環境変数
- `PORT`（既定: `8080`）
- `EXEC_TIMEOUT_SECONDS_DEFAULT`
- `EXEC_MAX_TIMEOUT_SECONDS`
- `HEALTH_AUTH_CHECK_ENABLED`（`0|1`）

## 8. ログ
- 標準出力/標準エラーに出力する。
- 最低限、実行結果（終了コード・所要時間）が追えること。

## 9. ビルド運用例
```bash
# 依存更新時のみ
docker build -f Dockerfile.base -t nlm-api-base:latest .

# 日常更新
docker compose build nlm-api
docker compose up -d
```

## 10. compose 例（最小）
```yaml
services:
  nlm-api:
    build: .
    ports:
      - "192.168.1.10:8080:8080"
      - "192.168.1.10:6080:6080"
    environment:
      - PORT=8080
      - EXEC_TIMEOUT_SECONDS_DEFAULT=600
      - EXEC_MAX_TIMEOUT_SECONDS=1800
      - HEALTH_AUTH_CHECK_ENABLED=1
    volumes:
      - nlm_state:/root/.notebooklm-mcp-cli
    shm_size: "1gb"
    init: true
    restart: unless-stopped

volumes:
  nlm_state:
```
