# notebooklm-mcp-cli Remote API Container

`notebooklm-mcp-cli` を LAN 内からリモート実行するための最小 API サーバです。  
n8n などのワークフローから `nlm` を同期実行する用途を想定しています。

## 特徴
- 最小API構成（`/health`, `/exec`, `/artifacts/download`）
- すべて同期実行
- `nlm` は `bash -lc` 経由で実行
- noVNC 経由の手動ログイン運用に対応
- base イメージ分離でビルド時間を短縮可能

## 仕様
- API仕様: `docs/spec_api.md`
- コンテナ仕様: `docs/spec_container.md`

## セットアップ
1. 環境変数を準備
```bash
cp .env.example .env
```

2. （依存更新時のみ）base イメージを作成
```bash
docker build -f Dockerfile.base -t nlm-api-base:latest .
```

3. コンテナ起動
```bash
docker compose up -d --build
```

## 初回ログイン
- noVNC: `http://<host>:6080/vnc.html`
- コンテナ内で `nlm login` を実施し、認証状態は volume (`/root/.notebooklm-mcp-cli`) に永続化されます。

## APIの使い方（例）
### ヘルスチェック
```bash
curl -sS http://127.0.0.1:8080/health
```

### スクリプト実行
```bash
curl -sS -X POST http://127.0.0.1:8080/exec \
  -H "Content-Type: application/json" \
  -d '{
    "script":"set -euo pipefail\nnlm login --check\nnlm notebook list --json",
    "timeout_seconds": 600
  }'
```

### 成果物ダウンロード
```bash
curl -L "http://127.0.0.1:8080/artifacts/download?notebook_id=<NOTEBOOK_ID>&artifact_id=<ARTIFACT_ID>&kind=audio" -o artifact.bin
```

### n8nからの実行例（`/exec` に渡す script）
```bash
# 入力パラメータ
ARXIV_URL="{{ $json.url }}"
NOTEBOOK_TITLE="{{ $json.notebookTitle }}"
FOCUS=$(cat <<EOF
私の興味がある領域は以下である。

AI の「頭の中」に関することなら興味がある。
- AIの知識構造、認識、推論、相互作用に関するもの
- AI の思考過程を扱うもの
- データセットの構造・特性に関するもの
- ハルシネーションや推論精度を扱うもの

AI が「何を見せるか」や「社会問題」は興味がない。
- 表現系（画像・音声・UI・資料作成）
- 社会的問題（公平性・バイアス・個人情報・フェイクニュース）
- 生物学／物理学などAIの思考構造に無関係な領域
- 単純アルゴリズム（経路計算など）
EOF
)

# 0. 認証確認
set -euo pipefail
nlm login --check || nlm login

# 1. ノートブックを作成し、JSONからIDを取得
echo "=== Step 1: Creating Notebook ==="
nlm notebook create "$NOTEBOOK_TITLE"
NOTEBOOK_ID=$(nlm notebook list --json | jq -r --arg title "$NOTEBOOK_TITLE" '.[] | select(.title == $title) | .id' | head -n 1)
echo "Notebook ID: $NOTEBOOK_ID"

# 2. ソース(URL)を追加し、処理完了まで待機 (--wait)
echo "=== Step 2: Adding Source & Waiting ==="
nlm source add $NOTEBOOK_ID --url "$ARXIV_URL" --wait

# 3. 音声生成 (日本語、短く、Deep Dive)
# --language ja: 日本語
# --length short: 短く
# --format deep_dive: ディープダイブ
echo "=== Step 3: Requesting Audio Generation ==="
nlm audio create $NOTEBOOK_ID \
  --format deep_dive \
  --length short \
  --language ja \
  --focus """$FOCUS"""
  --confirm

nlm create slides $NOTEBOOK_ID --format detailed_deck --length default --language ja --focus """$FOCUS""" --confirm

nlm create infographic $NOTEBOOK_ID --orientation landscape --detail detailed --language ja --focus """$FOCUS""" --confirm
```

ファイルを与える場合は以下。

```
cat <<EOF > tmp_google_alerts.txt
{{ $json.text }}
EOF
```

```
# 2. ソースを追加し、処理完了まで待機 (--wait)
echo "=== Step 2: Adding Source & Waiting ==="
nlm source add $NOTEBOOK_ID --file tmp_google_alerts.txt --wait
```
