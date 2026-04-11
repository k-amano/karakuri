# karakuri → xolvien 名前変更 引継ぎ手順

このドキュメントは、プロジェクト名を karakuri から xolvien に変更するための作業手順書です。
新しいセッションで続きから作業を始めてください。

## 前提

- 新しい GitHub リポジトリ: https://github.com/k-amano/xolvien
- 取得済みドメイン: xolvien.com
- ディレクトリ移動は **このセッションを終了してから** ターミナルで行う

---

## ステップ①：ディレクトリ移動（セッション終了後にターミナルで実行）

```bash
mv ~/Projects/karakuri ~/Projects/xolvien
cd ~/Projects/xolvien
```

その後、`~/Projects/xolvien` に移動した状態で Claude Code を再起動する。

---

## ステップ②：git リモート URL の変更

```bash
git remote set-url origin git@github.com:k-amano/xolvien.git
git remote -v  # 確認
```

---

## ステップ③：コード・設定ファイルの置換

以下のファイルを編集する。置換パターンは2種類：

- `karakuri` → `xolvien`
- `Karakuri` → `Xolvien`

### docker-compose.yml

| 変換前 | 変換後 |
|---|---|
| `container_name: karakuri-db` | `container_name: xolvien-db` |
| `POSTGRES_USER: karakuri` | `POSTGRES_USER: xolvien` |
| `POSTGRES_PASSWORD: karakuri` | `POSTGRES_PASSWORD: xolvien` |
| `POSTGRES_DB: karakuri` | `POSTGRES_DB: xolvien` |
| `pg_isready -U karakuri` | `pg_isready -U xolvien` |
| `container_name: karakuri-backend` | `container_name: xolvien-backend` |
| `postgresql+asyncpg://karakuri:karakuri@db:5432/karakuri` | `postgresql+asyncpg://xolvien:xolvien@db:5432/xolvien` |
| `karakuri-workspace:latest` | `xolvien-workspace:latest` |
| `container_name: karakuri-frontend` | `container_name: xolvien-frontend` |

### .env.example

| 変換前 | 変換後 |
|---|---|
| `postgresql+asyncpg://karakuri:karakuri@localhost:5433/karakuri` | `postgresql+asyncpg://xolvien:xolvien@localhost:5433/xolvien` |
| `POSTGRES_USER=karakuri` | `POSTGRES_USER=xolvien` |
| `POSTGRES_PASSWORD=karakuri` | `POSTGRES_PASSWORD=xolvien` |
| `POSTGRES_DB=karakuri` | `POSTGRES_DB=xolvien` |
| `WORKSPACE_IMAGE=karakuri-workspace:latest` | `WORKSPACE_IMAGE=xolvien-workspace:latest` |
| `TASK_DATA_PATH=/tmp/karakuri/tasks` | `TASK_DATA_PATH=/tmp/xolvien/tasks` |

### backend/.env（ローカルの実環境設定ファイル）

`.env.example` と同じ置換を適用する。

### docker/workspace/Dockerfile

| 変換前 | 変換後 |
|---|---|
| `RUN useradd -m -s /bin/bash karakuri` | `RUN useradd -m -s /bin/bash xolvien` |
| `chown karakuri:karakuri ${WORKSPACE_DIR}` | `chown xolvien:xolvien ${WORKSPACE_DIR}` |
| コメント行の `karakuri` | `xolvien` |

### backend/app/services/docker_service.py

| 変換前 | 変換後 |
|---|---|
| `f"karakuri-task-{task_id}"` | `f"xolvien-task-{task_id}"` |
| `f"karakuri-task-{task_id}-data"` | `f"xolvien-task-{task_id}-data"` |
| `"GIT_USER_NAME": "Karakuri Bot"` | `"GIT_USER_NAME": "Xolvien Bot"` |
| `"GIT_USER_EMAIL": "bot@karakuri.local"` | `"GIT_USER_EMAIL": "bot@xolvien.com"` |
| `"chown -R karakuri:karakuri /workspace/repo ..."` | `"chown -R xolvien:xolvien /workspace/repo ..."` |

### backend/app/services/claude_service.py

`_RUNNER_SCRIPT_AGENT` 内の `karakuri` ユーザー参照：

| 変換前 | 変換後 |
|---|---|
| `pwd.getpwnam('karakuri')` | `pwd.getpwnam('xolvien')` |

### frontend/package.json

| 変換前 | 変換後 |
|---|---|
| `"name": "karakuri-frontend"` | `"name": "xolvien-frontend"` |

### frontend/src/pages/Dashboard.tsx、TaskDetail.tsx、TaskCreate.tsx

表示テキスト内の `Karakuri` → `Xolvien`

### backend/app/main.py

タイトル・コメント内の `Karakuri` → `Xolvien`

### CLAUDE.md

プロジェクト説明内の `Karakuri` / `karakuri` を置換。

---

## ステップ④：ドキュメントの置換

以下のファイル内の `karakuri` / `Karakuri` を `xolvien` / `Xolvien` に一括置換する。
（git clone URL の `k-amano/karakuri.git` → `k-amano/xolvien.git` も忘れずに）

- `README.md`
- `docs/getting-started.md`
- `docs/basic-design (1).md`
- `docs/requirements (8).md`

---

## ステップ⑤：Docker イメージの再ビルド

Dockerfile のユーザー名が変わるため再ビルドが必要。

```bash
docker build -t xolvien-workspace:latest ./docker/workspace/
```

---

## ステップ⑥：データベースのリセット

DB名・ユーザー名が変わるため、既存コンテナとデータを破棄して作り直す。

```bash
docker compose down -v        # データごと削除
docker compose up -d db       # 新しい設定で起動
cd backend
source venv/bin/activate
alembic upgrade head          # マイグレーション再実行
cd ..
```

---

## ステップ⑦：既存の karakuri タスクコンテナ・ボリュームの削除

古い名前のコンテナ・ボリュームが残っている場合は削除する。

```bash
docker ps -a --filter "name=karakuri" --format "{{.Names}}" | xargs -r docker rm -f
docker volume ls --filter "name=karakuri" --format "{{.Name}}" | xargs -r docker volume rm
```

---

## ステップ⑧：動作確認

```bash
docker compose up -d db
cd backend && source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 別ターミナルで
cd frontend && npm run dev
```

ブラウザで `http://localhost:5173` を開き、画面に `Xolvien` と表示されれば完了。

---

## ステップ⑨：コミット＆プッシュ

```bash
git add -A
git commit -m "feat: rename project from karakuri to xolvien"
git push origin main
```

---

## 作業後に削除してよいファイル

この引継ぎドキュメント自体（`RENAME_TO_XOLVIEN.md`）は作業完了後に削除してください。

---

# アプリ改修の引継ぎ事項

名前変更とは独立した、アプリの未解決事項・既知の問題です。

---

## 【バグ】TypeScript コンパイルエラー（未修正）

**ファイル：** `frontend/src/services/api.ts` の `createTask()` 関数

**問題：** `branch_name` の型が `string`（必須）になっているが、`TaskCreate.tsx` では `undefined` を渡している。

```ts
// api.ts（現状）
export async function createTask(data: {
  branch_name: string   // ← string 必須になっている
  ...
})

// TaskCreate.tsx（呼び出し側）
branch_name: branchName.trim() || undefined   // ← undefined を渡している → TS エラー
```

**修正方法：** `api.ts` の `branch_name` を `string | undefined` または `branch_name?: string` に変更する。

---

## 【未実装】`POST /instructions`（非ストリーミング）エンドポイント

**ファイル：** `backend/app/api/instructions.py` の `create_instruction()` 関数

**問題：** 指示レコードを作るだけで実行はしない。コメントに `# For now, just create the instruction record` とある。現在 UI はストリーミングエンドポイント（`/execute-stream`）のみ使用しており実害はないが、API の仕様として不完全。

**対処方針：** このエンドポイントを削除するか、`/execute-stream` にリダイレクトするか、将来的に非同期ジョブキューを実装する際の入口として残すかを判断する。

---

## 【既知の制限】ストリーミングのブロッキング問題

**ファイル：** `backend/app/services/docker_service.py`

**問題：** `execute_command_stream()` は docker-py の同期 API を `asyncio.sleep(0.01)` で疑似的に非同期化している。複数タスクを同時実行すると他のリクエストが遅延する。

**対処方針：** README の設計決定事項に記載済み。マルチユーザー対応時に `run_in_executor` でスレッドプールへ移譲する。現状はシングルユーザー用途のため許容。

---

## 【優先度：中】今後実装予定の機能

README に記載済み。新しいセッションで着手する際の参考に：

1. **自動テスト → 失敗時の自動修正ループ**
   - テスト実行（`TestService`）は実装済み。失敗時に Claude へ自動フィードバックして再実行するループが未実装。

2. **GitHub Issue 連携**
   - Webhook 受信 → タスク自動作成・実行。認証・セキュリティ設計が必要。

3. **PR 自動作成**
   - `git push` 後に GitHub API で PR を自動作成する。`gh` CLI またはGitHub REST API を使う想定。

---

## 【参考】主要ファイルのマップ

```
backend/app/
├── api/
│   ├── instructions.py   # /clarify, /generate-prompt, /execute-stream エンドポイント
│   ├── tasks.py          # タスク CRUD + /git/push
│   └── repositories.py   # リポジトリ CRUD
├── services/
│   ├── claude_service.py # clarify_requirements(), generate_prompt(), execute_instruction()
│   ├── docker_service.py # コンテナ作成・コマンド実行・ストリーミング
│   └── test_service.py   # テスト実行・結果パース
└── models/               # Task, Instruction, TaskLog, Repository

frontend/src/
├── pages/
│   ├── TaskDetail.tsx    # メイン画面（要件確認UI・ログ・指示入力）
│   ├── TaskCreate.tsx    # タスク作成フォーム
│   └── Dashboard.tsx     # タスク一覧
└── services/
    └── api.ts            # バックエンド API 呼び出し関数
```
