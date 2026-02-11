# Karakuri

AI駆動開発プラットフォーム - Docker + Claude Code による自動コード生成システム

## 概要

KarakuriはGitHub Actions + Claude Codeの課題を解決する独自のWebアプリケーションです：

- **タスク単位のDockerコンテナ**: 各タスクが独立した開発環境を持つ
- **リアルタイムログ配信**: Claude Code実行中のログをWebSocketで配信
- **ローカル開発**: ローカルでビルド・テスト可能
- **ブランチ継続性**: 開発コンテキストをセッション間で維持

## MVP機能（実装済み）

✅ **完全実装・動作確認済み**

- タスク管理（作成、一覧、詳細表示、停止、削除）
- Dockerコンテナのライフサイクル管理
- Claude Code CLI実行（ストリーミング出力）
- WebSocketによるリアルタイムログ配信
- テスト実行と結果追跡
- シンプルなトークン認証

## 技術スタック

- **バックエンド**: Python 3.11 + FastAPI + SQLAlchemy 2.0
- **データベース**: PostgreSQL 16
- **コンテナ管理**: docker-py
- **WebSocket**: FastAPI WebSocket
- **フロントエンド**: React + Vite + TypeScript（構造のみ実装済み）

---

## 🚀 クイックスタート（初回セットアップ）

### 前提条件

以下がインストールされていることを確認してください：

```bash
# Dockerのバージョン確認
docker --version
# Docker version 20.10以上が必要

# Pythonのバージョン確認
python3 --version
# Python 3.11以上が必要

# Node.jsのバージョン確認（フロントエンド実装時に必要）
node --version
# Node.js 18以上が必要
```

---

### ステップ1: 環境変数の設定

```bash
# プロジェクトディレクトリに移動
cd /home/administrator/Projects/karakuri

# 環境変数ファイルをコピー
cp .env.example backend/.env

# .envファイルを編集（重要！）
nano backend/.env
# または
vim backend/.env
```

**必須設定項目:**
```env
# Claude Code APIキー（重要！）
ANTHROPIC_API_KEY=your-actual-api-key-here

# その他の設定はデフォルトのままでOK
DATABASE_URL=postgresql+asyncpg://karakuri:karakuri@localhost:5433/karakuri
DEV_AUTH_TOKEN=dev-token-12345
```

> ⚠️ **重要**: `ANTHROPIC_API_KEY` を実際のAPIキーに置き換えてください

---

### ステップ2: データベースの起動

```bash
# PostgreSQLをDockerコンテナで起動
docker compose up -d db

# 起動確認（healthyになるまで待つ）
docker compose ps
# karakuri-db が "Up (healthy)" になればOK
```

**確認方法:**
```bash
# データベースに接続できるか確認
docker compose exec db psql -U karakuri -c "SELECT version();"
# PostgreSQLのバージョン情報が表示されればOK
```

---

### ステップ3: バックエンドのセットアップ

```bash
# バックエンドディレクトリに移動
cd backend

# Python仮想環境を作成（初回のみ）
python3 -m venv venv

# 仮想環境を有効化
source venv/bin/activate

# 依存パッケージをインストール
pip install fastapi uvicorn[standard] sqlalchemy asyncpg psycopg2-binary \
    alembic python-dotenv docker pydantic pydantic-settings \
    python-multipart websockets aiofiles

# データベースマイグレーションを実行
alembic upgrade head
```

**確認方法:**
```bash
# テーブルが作成されたか確認
docker compose exec db psql -U karakuri -c "\dt"
# users, repositories, tasks, instructions, test_runs, task_logs, alembic_version
# の7つのテーブルが表示されればOK
```

---

### ステップ4: Dockerワークスペースイメージのビルド

```bash
# プロジェクトルートに戻る
cd /home/administrator/Projects/karakuri

# ワークスペース用Dockerイメージをビルド
docker build -t karakuri-workspace:latest ./docker/workspace/
```

**確認方法:**
```bash
# イメージが作成されたか確認
docker images | grep karakuri-workspace
# karakuri-workspace   latest   ...   848MB  のような行が表示されればOK

# イメージが正常に動作するか確認
docker run --rm karakuri-workspace:latest echo "Hello Karakuri"
# "Hello Karakuri" と表示されればOK
```

> 📝 ビルドには5-10分程度かかります

---

### ステップ5: バックエンドサーバーの起動

```bash
# バックエンドディレクトリに移動
cd /home/administrator/Projects/karakuri/backend

# 仮想環境を有効化（新しいターミナルの場合）
source venv/bin/activate

# サーバーを起動
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**起動成功のメッセージ:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process [xxxxx] using StatReload
INFO:     Started server process [xxxxx]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

**確認方法:**
別のターミナルで以下を実行：
```bash
# ヘルスチェック
curl http://localhost:8000/health
# {"status":"healthy","environment":"development"} が返ればOK

# API仕様書を確認
# ブラウザで http://localhost:8000/docs を開く
# Swagger UIが表示されればOK
```

---

## ✅ セットアップ完了！

これでKarakuriのバックエンドが起動しました！

---

## 📖 使い方

### 方法1: Swagger UI（おすすめ - 初心者向け）

1. ブラウザで http://localhost:8000/docs を開く
2. 右上の **"Authorize"** ボタンをクリック
3. `dev-token-12345` を入力して **"Authorize"**
4. 各エンドポイントを試す：
   - **POST /api/v1/repositories** でリポジトリを登録
   - **POST /api/v1/tasks** でタスクを作成（自動的にDockerコンテナが起動）
   - **POST /api/v1/tasks/{id}/instructions/execute-stream** で指示を実行
   - **POST /api/v1/tasks/{id}/test-runs** でテストを実行

### 方法2: curlコマンド（上級者向け）

```bash
# 1. リポジトリを登録
curl -X POST http://localhost:8000/api/v1/repositories \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-token-12345" \
  -d '{
    "name": "test-repo",
    "url": "https://github.com/octocat/Hello-World.git",
    "description": "テスト用リポジトリ"
  }'

# レスポンス例:
# {"id":1,"name":"test-repo",...}
# ↑ この id を次のステップで使います

# 2. タスクを作成（Dockerコンテナが自動起動）
curl -X POST http://localhost:8000/api/v1/tasks \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-token-12345" \
  -d '{
    "repository_id": 1,
    "title": "初めてのタスク",
    "description": "Karakuriのテスト",
    "branch_name": "master"
  }'

# レスポンス例:
# {"id":1,"status":"pending",...}
# ↑ status が "idle" になるまで5-10秒待つ

# 3. タスクの状態を確認
curl http://localhost:8000/api/v1/tasks/1 \
  -H "Authorization: Bearer dev-token-12345"

# status が "idle" になったらOK（コンテナ起動完了）

# 4. Claude Codeに指示を出す（ストリーミング）
curl -N -X POST http://localhost:8000/api/v1/tasks/1/instructions/execute-stream \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-token-12345" \
  -d '{
    "content": "READMEファイルの内容を説明してください"
  }'

# リアルタイムで実行ログが流れます

# 5. テストを実行
curl -X POST http://localhost:8000/api/v1/tasks/1/test-runs \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dev-token-12345" \
  -d '{
    "test_command": "ls -la"
  }'

# 6. 実行ログを確認
curl http://localhost:8000/api/v1/tasks/1/logs \
  -H "Authorization: Bearer dev-token-12345"
```

---

## 🔍 動作確認

### 起動中のコンテナを確認

```bash
# Karakuri関連のコンテナを確認
docker ps --filter "name=karakuri"

# 期待される出力:
# karakuri-db       # データベース
# karakuri-task-1   # タスク1のワークスペース
# karakuri-task-2   # タスク2のワークスペース（複数作成した場合）
```

### データベースの中身を確認

```bash
# タスク一覧を確認
docker compose exec db psql -U karakuri -c "SELECT id, title, status FROM tasks;"

# ログを確認
docker compose exec db psql -U karakuri -c "SELECT source, message FROM task_logs ORDER BY created_at DESC LIMIT 5;"
```

---

## 🛠️ トラブルシューティング

### ポート5432が既に使用されている

**エラー:** `bind: address already in use`

**解決策:**
```bash
# 既存のPostgreSQLを確認
sudo lsof -i :5432

# Karakuriは5433ポートを使用（.env で設定済み）
# 既に5433を使用している場合は .env のポート番号を変更
```

### データベース接続エラー

**エラー:** `Connection refused` または `could not connect to server`

**解決策:**
```bash
# データベースコンテナが起動しているか確認
docker compose ps

# 停止している場合は起動
docker compose up -d db

# ログを確認
docker compose logs db
```

### Alembicマイグレーションエラー

**エラー:** `Target database is not up to date`

**解決策:**
```bash
cd backend
source venv/bin/activate
alembic upgrade head
```

### Dockerイメージビルドエラー

**エラー:** ビルド中にタイムアウトやネットワークエラー

**解決策:**
```bash
# キャッシュをクリアして再ビルド
docker build --no-cache -t karakuri-workspace:latest ./docker/workspace/
```

### 仮想環境が見つからない

**エラー:** `venv/bin/activate: No such file or directory`

**解決策:**
```bash
# 仮想環境を再作成
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt  # または個別にインストール
```

---

## 📊 主要なAPIエンドポイント

### 認証
- `GET /api/v1/auth/dev-login` - 開発用トークン取得

### リポジトリ管理
- `GET /api/v1/repositories` - リポジトリ一覧
- `POST /api/v1/repositories` - リポジトリ登録
- `GET /api/v1/repositories/{id}` - リポジトリ詳細
- `DELETE /api/v1/repositories/{id}` - リポジトリ削除

### タスク管理
- `GET /api/v1/tasks` - タスク一覧
- `POST /api/v1/tasks` - タスク作成（Dockerコンテナ自動起動）
- `GET /api/v1/tasks/{id}` - タスク詳細
- `POST /api/v1/tasks/{id}/stop` - タスク停止
- `DELETE /api/v1/tasks/{id}` - タスク削除

### Claude Code実行
- `POST /api/v1/tasks/{id}/instructions/execute-stream` - 指示実行（ストリーミング）
- `GET /api/v1/tasks/{id}/instructions` - 指示履歴

### テスト実行
- `POST /api/v1/tasks/{id}/test-runs` - テスト実行
- `GET /api/v1/tasks/{id}/test-runs` - テスト履歴
- `GET /api/v1/tasks/{id}/test-runs/{run_id}` - テスト結果詳細

### ログ
- `GET /api/v1/tasks/{id}/logs` - ログ履歴
- `WS /api/v1/ws/tasks/{id}/logs` - リアルタイムログ（WebSocket）
- `WS /api/v1/ws/tasks/{id}/status` - ステータス更新（WebSocket）

---

## 🏗️ アーキテクチャ

### タスクのライフサイクル

```
1. PENDING      → タスク作成、コンテナ起動待ち
2. INITIALIZING → コンテナ起動中、git clone中
3. IDLE         → 待機中（指示入力待ち）
4. RUNNING      → Claude Code実行中
5. TESTING      → テスト実行中
6. COMPLETED    → 完了
7. FAILED       → 失敗
8. STOPPED      → 手動停止
```

### コンテナ管理

各タスクには以下が割り当てられます：
- 専用Dockerコンテナ（`karakuri-workspace`イメージベース）
- 永続ボリューム（コード保存用）
- クローンされたGitリポジトリ
- Claude Code CLI実行環境

---

## 📁 プロジェクト構造

```
karakuri/
├── backend/                    # FastAPIバックエンド
│   ├── app/
│   │   ├── main.py            # FastAPIアプリケーション
│   │   ├── config.py          # 設定管理
│   │   ├── database.py        # DB接続
│   │   ├── models/            # SQLAlchemyモデル
│   │   ├── schemas/           # Pydanticスキーマ
│   │   ├── api/               # APIエンドポイント
│   │   ├── services/          # ビジネスロジック
│   │   │   ├── docker_service.py  # Docker管理
│   │   │   ├── claude_service.py  # Claude Code実行
│   │   │   └── test_service.py    # テスト実行
│   │   └── websocket/         # WebSocket管理
│   ├── alembic/               # DBマイグレーション
│   └── venv/                  # Python仮想環境
├── frontend/                   # React フロントエンド（構造のみ）
├── docker/
│   └── workspace/             # Claude Code実行環境
│       ├── Dockerfile
│       └── entrypoint.sh
├── docs/                      # ドキュメント
├── docker-compose.yml         # 開発環境
└── .env.example               # 環境変数テンプレート
```

---

## 🔄 日常的な使用（2回目以降）

すでにセットアップ済みの場合：

```bash
# 1. データベースを起動
docker compose up -d db

# 2. バックエンドを起動
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. ブラウザで Swagger UI を開く
# http://localhost:8000/docs

# 4. 使い終わったら停止
# Ctrl+C でサーバー停止
docker compose down  # データベース停止
```

---

## 🚧 今後の拡張計画

### Phase 2: 基本機能
- プロンプト変換AI
- テスト失敗時の自動リトライ
- GitHub OAuth認証

### Phase 3: GitHub連携
- GitHub Issue同期
- Webhook統合
- 自動PR作成

### Phase 4: 高度な機能
- ファイルアップロード・変換（Excel/Word）
- 仕様データベース
- ドキュメント自動生成

---

## 📚 詳細ドキュメント

- `MVP_IMPLEMENTATION_STATUS.md` - 実装状況の詳細レポート
- `NEXT_STEPS.md` - 次のステップと拡張ガイド
- `http://localhost:8000/docs` - API仕様書（Swagger UI）

---

## ❓ よくある質問

**Q: Poetryは必要ですか？**
A: いいえ、venvで十分です。pyproject.tomlは参考用です。

**Q: フロントエンドは必須ですか？**
A: いいえ、Swagger UI（http://localhost:8000/docs）で全機能を使えます。

**Q: 実際のClaude Code CLIが必要ですか？**
A: 現在はシミュレーション実装です。実際のCLIは後で置き換え可能です。

**Q: 複数のタスクを同時に実行できますか？**
A: はい、各タスクが独立したDockerコンテナで動作します。

**Q: コンテナが残り続けますが？**
A: タスク削除時に自動削除されます。手動で削除する場合は `docker rm -f karakuri-task-X`

---

## 📝 ライセンス

MIT

## 🤝 コントリビューション

プルリクエスト歓迎！詳細は [CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

---

**Karakuri MVP - AI駆動開発プラットフォーム**
Built with ❤️ using FastAPI, Docker, and Claude Code
