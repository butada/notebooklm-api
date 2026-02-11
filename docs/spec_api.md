# NLM リモート実行 API 仕様

## 1. 目的
- n8n から `nlm` を実行するための最小APIを提供する。
- ジョブ管理は行わない。
- すべて同期実行。
- `nlm` は直接実行せず、`bash` 経由で実行する。

## 2. エンドポイント

### `GET /health`
- サーバの生存確認用。
- 必要なら `nlm login --check` の結果も返す。

### `POST /exec`
- 複数行の bash スクリプトを同期実行する。
- 実行形式: `bash -lc "<script>"`

リクエスト:
- `script` (必須, string, 複数行可)
- `timeout_seconds` (任意, int)
- `env` (任意, object)

レスポンス:
- `exit_code`
- `stdout`
- `stderr`
- `duration_ms`
- `started_at`
- `finished_at`
- `timed_out`

### `GET /artifacts/download`
- 成果物を `nlm download` で都度取得し、バイナリ本体を返す。
- ローカルキャッシュは行わない。

リクエスト:
- `notebook_id` (必須, string)
- `artifact_id` (必須, string)
- `kind` (必須, string)
  - 例: `audio`, `infographic`

レスポンスヘッダ:
- `Content-Type` はファイル内容に応じて設定する。
- 対応MIME:
  - PDF: `application/pdf`
  - PNG: `image/png`
  - MP3: `audio/mpeg`
  - M4A: `audio/mp4`
- 判定不能時は `application/octet-stream` を返す。

## 3. ステータスコード
- `200`: 実行結果を返せた（`exit_code != 0` でも `200`）
- `400`: リクエスト不正
- `404`: 成果物が存在しない
- `413`: ボディサイズ超過
- `500`: API内部エラー

## n8nからの呼び出しイメージ
POST /exec に以下のような複数行scriptを送るだけ:

```bash
set -euo pipefail
nlm login --check || nlm login
NOTEBOOK_ID=$(nlm notebook list --json | jq -r '.[0].id')
nlm notebook query "$NOTEBOOK_ID" "要約して"
```
