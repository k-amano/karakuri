# Xolvien — 基本設計書

## 1. 設計概要

### 1.1 本書の範囲

本書ではXolvienの基本設計として以下の10の領域を定義する。

1. 設計概要（システム全体構成図）
2. API設計（バックエンドエンドポイント一覧）
3. データベース設計（テーブル定義・ER関係）
4. 画面遷移設計（画面一覧・遷移図・レイアウト構成）
5. Docker設計（イメージ構成・Compose構成）
6. 主要処理シーケンス（タスク作成→実行→テスト→完了の流れ等）
7. ファイル変換処理設計
8. 仕様データベース処理設計
9. 外部連携設計（GitHub API、Anthropic API、Cloudflare Tunnel）
10. セキュリティ設計（認証・暗号化・通信）

### 1.2 システム全体構成図

```
┌─────────────────────────────────────────────────────────┐
│                     ブラウザ (React / Vite)               │
│  ┌──────┐ ┌────────┐ ┌──────┐ ┌──────┐ ┌──────┐        │
│  │ダッシュ│ │タスク作成│ │作業画面│ │設定  │ │ドキュメ│        │
│  │ボード │ │画面    │ │      │ │画面  │ │ント生成│        │
│  └──┬───┘ └──┬─────┘ └──┬───┘ └──┬───┘ └──┬───┘        │
│     └─────────┴──────────┴────────┴─────────┘            │
│                    HTTP / WebSocket                      │
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│              バックエンド (FastAPI)                       │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐              │
│  │REST API   │  │WebSocket │  │Webhook    │              │
│  │エンドポイント│  │ストリーミング│  │エンドポイント│←── GitHub  │
│  └────┬─────┘  └────┬─────┘  └─────┬─────┘              │
│       └──────────────┴─────────────┘                     │
│                      │                                   │
│  ┌─────────┐  ┌──────┴─────┐  ┌───────────┐             │
│  │Celery   │  │Docker管理   │  │ファイル変換 │             │
│  │タスクキュー│  │(docker-py) │  │(LibreOffice)│             │
│  └─────────┘  └──────┬─────┘  └───────────┘             │
│                      │                                   │
│  ┌───────────┐  ┌────┴────┐  ┌───────────┐              │
│  │PostgreSQL │  │Docker   │  │Cloudflare │              │
│  │(メインDB) │  │Engine   │  │Tunnel     │              │
│  └───────────┘  └────┬────┘  └───────────┘              │
└──────────────────────┼──────────────────────────────────┘
                       │
    ┌──────────────────┼──────────────────────┐
    │           Docker Composeタスク群          │
    │                                          │
    │  ┌─ タスクA ──────────────────────────┐  │
    │  │ workspace / db / redis / app       │  │
    │  └────────────────────────────────────┘  │
    │  ┌─ タスクB ──────────────────────────┐  │
    │  │ workspace / db / redis / app       │  │
    │  └────────────────────────────────────┘  │
    │  ┌─ タスクC ──────────────────────────┐  │
    │  │ workspace / db / redis / app       │  │
    │  └────────────────────────────────────┘  │
    └──────────────────────────────────────────┘
```

---

## 2. API設計

### 2.1 設計方針

- RESTful APIを基本とし、リアルタイム性が必要な箇所にWebSocketを使用する
- 認証はGitHub OAuthによるセッションベース（JWTトークン）
- レスポンス形式はすべてJSON
- エラーレスポンスは統一フォーマットで返却する

### 2.2 共通仕様

**ベースURL**

```
http://localhost:8000/api/v1
```

**認証ヘッダー**

```
Authorization: Bearer {jwt_token}
```

**エラーレスポンス形式**

```json
{
  "error": {
    "code": "TASK_NOT_FOUND",
    "message": "指定されたタスクが見つかりません",
    "details": {}
  }
}
```

**ページネーション**

```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "total_pages": 8
  }
}
```

### 2.3 認証 API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /auth/github | GitHub OAuthフロー開始（リダイレクト） |
| GET | /auth/github/callback | GitHub OAuthコールバック（トークン発行） |
| POST | /auth/logout | ログアウト（セッション破棄） |
| GET | /auth/me | 現在のログインユーザー情報取得 |

### 2.4 タスク API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /tasks | タスク一覧取得（フィルタ: status, repository_id） |
| POST | /tasks | タスク新規作成（コンテナ起動） |
| GET | /tasks/{task_id} | タスク詳細取得 |
| PUT | /tasks/{task_id} | タスク情報更新 |
| DELETE | /tasks/{task_id} | タスク削除（コンテナ破棄） |
| POST | /tasks/{task_id}/pause | タスク一時停止 |
| POST | /tasks/{task_id}/resume | タスク再開 |
| POST | /tasks/{task_id}/stop | タスク停止 |

**POST /tasks リクエスト**

```json
{
  "repository_id": 1,
  "branch": "feature/login-validation",
  "branch_action": "create",
  "assignee_id": 1,
  "github_issue": {
    "create": true,
    "title": "ログイン画面バリデーション追加",
    "body": "メールアドレスとパスワードのバリデーションを追加",
    "labels": ["ai-task"]
  },
  "initial_instruction": "ログイン画面にバリデーションを追加してください",
  "file_ids": [1, 2]
}
```

**GET /tasks/{task_id} レスポンス**

```json
{
  "id": 1,
  "status": "running",
  "repository": { "id": 1, "name": "my-app", "url": "..." },
  "branch": "feature/login-validation",
  "assignee": { "id": 1, "name": "田中太郎", "email": "tanaka@example.com" },
  "github_issue_number": 42,
  "container_id": "abc123...",
  "current_phase": "unit_test",
  "retry_count": 0,
  "created_at": "2026-02-11T10:00:00Z",
  "updated_at": "2026-02-11T10:30:00Z"
}
```

### 2.5 指示（Instruction）API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /tasks/{task_id}/instructions | 指示履歴一覧取得 |
| POST | /tasks/{task_id}/instructions | 新規指示送信（プロンプト変換を実行） |
| GET | /tasks/{task_id}/instructions/{id} | 指示詳細取得 |
| PUT | /tasks/{task_id}/instructions/{id}/prompt | 変換後プロンプトの編集 |
| POST | /tasks/{task_id}/instructions/{id}/confirm | プロンプト確定（Claude Code実行開始） |
| POST | /tasks/{task_id}/instructions/{id}/regenerate | プロンプト再変換 |

**POST /tasks/{task_id}/instructions リクエスト**

```json
{
  "text": "ログイン画面にバリデーションを追加してください",
  "file_ids": [3],
  "spec_changes": []
}
```

**レスポンス（プロンプト変換結果）**

```json
{
  "id": 5,
  "status": "pending_confirmation",
  "original_text": "ログイン画面にバリデーションを追加してください",
  "converted_prompt": "以下の仕様に基づいてログイン画面にバリデーションを追加してください...",
  "spec_changes": [
    {
      "entity_type": "screen_element",
      "entity_id": "S001-email",
      "change_type": "update",
      "field": "validation",
      "old_value": null,
      "new_value": "メール形式チェック"
    }
  ],
  "referenced_files": ["src/pages/Login.tsx", "src/api/auth.ts"]
}
```

### 2.6 ファイル API

| メソッド | パス | 説明 |
|---|---|---|
| POST | /files/upload | ファイルアップロード（変換処理を実行） |
| GET | /files/{file_id} | ファイル情報取得 |
| GET | /files/{file_id}/preview | 変換後プレビュー取得（HTML） |
| PUT | /files/{file_id}/converted | 変換後テキストの手動修正 |
| DELETE | /files/{file_id} | ファイル削除 |
| GET | /tasks/{task_id}/files | タスクに紐づくファイル一覧 |
| POST | /tasks/{task_id}/files/{file_id}/attach | タスクにファイルを紐付け |

**POST /files/upload レスポンス**

```json
{
  "id": 3,
  "original_name": "画面仕様書.xlsx",
  "file_type": "xlsx",
  "file_size": 1024000,
  "conversion_status": "completed",
  "converted_html_path": "/files/3/preview",
  "extracted_images": [
    { "id": 10, "name": "image001.png", "path": "/files/10/raw" }
  ],
  "uploaded_at": "2026-02-11T10:00:00Z"
}
```

### 2.7 テスト API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /tasks/{task_id}/test-runs | テスト実行履歴一覧 |
| GET | /tasks/{task_id}/test-runs/{run_id} | テスト実行結果詳細 |
| POST | /tasks/{task_id}/test-runs | 手動テスト実行（テスト種別を指定） |
| GET | /tasks/{task_id}/test-runs/{run_id}/screenshots | E2Eスクリーンショット一覧 |
| GET | /tasks/{task_id}/test-runs/{run_id}/report | Playwrightレポート取得 |

**GET /tasks/{task_id}/test-runs/{run_id} レスポンス**

```json
{
  "id": 12,
  "task_id": 1,
  "instruction_id": 5,
  "status": "failed",
  "retry_number": 1,
  "phases": [
    { "type": "lint", "status": "passed", "duration_ms": 3200, "command": "npm run lint" },
    { "type": "unit", "status": "passed", "duration_ms": 8500, "command": "npm test -- --unit" },
    { "type": "build", "status": "passed", "duration_ms": 15000, "command": "npm run build" },
    { "type": "integration", "status": "failed", "duration_ms": 12000, "command": "npm test -- --integration",
      "error": { "test_name": "auth.test.ts > login > should reject invalid email", "message": "Expected 400 but got 200", "stdout": "...", "stderr": "..." }
    },
    { "type": "e2e", "status": "skipped" }
  ],
  "started_at": "2026-02-11T10:30:00Z",
  "finished_at": "2026-02-11T10:31:15Z"
}
```

### 2.8 リポジトリ API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /repositories | リポジトリ一覧取得 |
| POST | /repositories | リポジトリ登録 |
| GET | /repositories/{id} | リポジトリ詳細取得 |
| PUT | /repositories/{id} | リポジトリ設定更新 |
| DELETE | /repositories/{id} | リポジトリ削除 |
| GET | /repositories/{id}/branches | ブランチ一覧取得（GitHub APIから） |
| PUT | /repositories/{id}/test-config | テストコマンド・サービス設定の更新 |
| PUT | /repositories/{id}/policy | 自動実行ポリシー設定の更新 |

**POST /repositories リクエスト**

```json
{
  "url": "https://github.com/user/my-app",
  "is_private": true,
  "github_token_id": 1,
  "test_config": {
    "services": [
      { "name": "postgres", "image": "postgres:16", "port": 5432, "env": { "POSTGRES_DB": "test_db" } }
    ],
    "app_server": {
      "build_command": "npm run build",
      "start_command": "npm run dev",
      "port": 3000,
      "health_check": "http://localhost:3000/health"
    },
    "test_commands": [
      { "name": "リント", "command": "npm run lint", "type": "lint", "required": true, "order": 1 },
      { "name": "単体テスト", "command": "npm test -- --unit", "type": "unit", "required": true, "order": 2 },
      { "name": "ビルド", "command": "npm run build", "type": "build", "required": true, "order": 3 },
      { "name": "結合テスト", "command": "npm test -- --integration", "type": "integration", "required": true, "order": 4, "depends_on": ["postgres"] },
      { "name": "E2E", "command": "npx playwright test", "type": "e2e", "required": false, "order": 5, "depends_on": ["app"] }
    ]
  },
  "policy": {
    "mode": "auto",
    "required_label": "ai-task",
    "allowed_users": []
  }
}
```

### 2.9 仕様データベース API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /repositories/{id}/specs | 仕様データベース全体取得（ツリー構造） |
| POST | /repositories/{id}/specs/init | 仕様データベース初期構築（ファイルから自動抽出） |
| GET | /repositories/{id}/specs/features | 機能一覧取得 |
| POST | /repositories/{id}/specs/features | 機能追加 |
| GET | /repositories/{id}/specs/features/{fid} | 機能詳細取得（画面・API・テーブル含む） |
| PUT | /repositories/{id}/specs/features/{fid} | 機能更新 |
| DELETE | /repositories/{id}/specs/features/{fid} | 機能削除 |
| GET | /repositories/{id}/specs/history | 仕様変更履歴取得 |
| POST | /repositories/{id}/specs/apply-changes | 仕様変更を一括適用（指示確定時に呼ばれる） |

### 2.10 ドキュメント生成 API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /repositories/{id}/templates | テンプレート一覧取得 |
| POST | /repositories/{id}/templates | テンプレートアップロード |
| PUT | /repositories/{id}/templates/{tid} | テンプレート更新（マッピング設定含む） |
| DELETE | /repositories/{id}/templates/{tid} | テンプレート削除 |
| POST | /repositories/{id}/documents/generate | ドキュメント生成実行 |
| GET | /repositories/{id}/documents | 生成済みドキュメント一覧 |
| GET | /repositories/{id}/documents/{did} | ドキュメントダウンロード |
| GET | /repositories/{id}/documents/{did}/preview | ドキュメントプレビュー |

**POST /repositories/{id}/documents/generate リクエスト**

```json
{
  "template_id": 1,
  "document_type": "unit_test_report",
  "scope": {
    "feature_ids": ["F001", "F002"],
    "test_run_ids": [10, 11, 12]
  }
}
```

### 2.11 テストデータ API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /repositories/{id}/test-data | テストデータファイル一覧 |
| POST | /repositories/{id}/test-data | テストデータアップロード |
| DELETE | /repositories/{id}/test-data/{file_id} | テストデータ削除 |
| GET | /repositories/{id}/env-vars | 環境変数一覧取得 |
| PUT | /repositories/{id}/env-vars | 環境変数一括更新 |

### 2.12 GitHub連携 API

| メソッド | パス | 説明 |
|---|---|---|
| POST | /webhooks/github | GitHub Webhookエンドポイント（署名検証付き） |
| GET | /tasks/{task_id}/github/comments | GitHub Issueコメント一覧 |
| POST | /tasks/{task_id}/github/pr | PR作成 |
| POST | /tasks/{task_id}/github/close-issue | Issue クローズ |

### 2.13 通知 API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /notifications | 通知一覧取得（未読/既読フィルタ） |
| PUT | /notifications/{id}/read | 通知を既読にする |
| PUT | /notifications/read-all | 全通知を既読にする |
| POST | /notifications/subscribe | ブラウザプッシュ通知の購読登録 |

### 2.14 システム API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /system/status | サーバーリソース状況取得（CPU、メモリ、ディスク） |
| GET | /system/logs | システムログ取得 |
| GET | /system/queue | タスクキュー状況取得 |

### 2.15 設定 API

| メソッド | パス | 説明 |
|---|---|---|
| GET | /settings | 全体設定取得 |
| PUT | /settings | 全体設定更新（同時実行上限、タイムアウト、リトライ上限等） |
| GET | /settings/assignees | 担当者一覧取得 |
| POST | /settings/assignees | 担当者追加 |
| PUT | /settings/assignees/{id} | 担当者更新 |
| DELETE | /settings/assignees/{id} | 担当者削除 |
| GET | /settings/credentials | 認証情報一覧取得（マスク表示） |
| POST | /settings/credentials | 認証情報登録（GitHub PAT、Anthropic APIキー等） |
| PUT | /settings/credentials/{id} | 認証情報更新 |
| DELETE | /settings/credentials/{id} | 認証情報削除 |

### 2.16 WebSocket エンドポイント

| パス | 説明 |
|---|---|
| /ws/tasks/{task_id}/logs | タスクの実行ログをリアルタイムストリーミング |
| /ws/tasks/{task_id}/status | タスクのステータス変更をリアルタイム通知 |
| /ws/notifications | 通知のリアルタイム配信 |

**ログストリーミングのメッセージ形式**

```json
{
  "type": "log",
  "timestamp": "2026-02-11T10:30:15.123Z",
  "source": "claude_code",
  "level": "info",
  "message": "ファイル src/pages/Login.tsx を修正中..."
}
```

**ステータス変更の メッセージ形式**

```json
{
  "type": "status_change",
  "timestamp": "2026-02-11T10:30:20.000Z",
  "old_status": "running",
  "new_status": "unit_test",
  "phase": "unit",
  "detail": "単体テスト実行中 (3/15)"
}
```

---

## 3. データベース設計

### 3.1 設計方針

- PostgreSQLを使用し、バックエンドアプリケーション用のメインDBとする
- テーブル名はスネークケース、複数形
- 全テーブルに id（主キー）、created_at、updated_at を付与
- 論理削除は使用せず物理削除とする（ドキュメント等の履歴は別テーブルで管理）
- 外部キーにはインデックスを付与

### 3.2 ER図（概要）

```
users ─────────────┐
                    │
repositories ──────┤
  │                │
  ├─ repo_test_configs    │
  ├─ repo_test_services   │
  ├─ repo_policies        │
  ├─ repo_env_vars        │
  ├─ templates            │
  ├─ test_data_files      │
  │                │
  ├─ spec_features        │
  │   ├─ spec_screens     │
  │   │   └─ spec_elements│
  │   ├─ spec_endpoints   │
  │   │   └─ spec_params  │
  │   ├─ spec_tables      │
  │   │   └─ spec_columns │
  │   └─ spec_rules       │
  │                │
  └─ tasks ────────┤
      ├─ instructions     │
      │   └─ spec_changes │
      ├─ task_files       │
      ├─ test_runs        │
      │   ├─ test_phases  │
      │   └─ screenshots  │
      ├─ task_logs        │
      └─ generated_docs   │
                    │
notifications ──────┘
credentials
assignees
system_settings
```

### 3.3 テーブル定義

#### users（ユーザー）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| github_id | INTEGER | UNIQUE, NOT NULL | GitHubユーザーID |
| github_login | VARCHAR(255) | NOT NULL | GitHubユーザー名 |
| github_avatar_url | TEXT | | アバターURL |
| display_name | VARCHAR(255) | | 表示名 |
| session_token | VARCHAR(512) | | JWTトークン |
| session_expires_at | TIMESTAMP | | セッション有効期限 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### repositories（リポジトリ）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| name | VARCHAR(255) | NOT NULL | リポジトリ名 |
| url | TEXT | NOT NULL | GitHubリポジトリURL |
| is_private | BOOLEAN | NOT NULL DEFAULT true | 公開/非公開 |
| default_branch | VARCHAR(255) | DEFAULT 'main' | デフォルトブランチ |
| credential_id | INTEGER | FK → credentials.id | GitHub認証情報 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### credentials（認証情報）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| name | VARCHAR(255) | NOT NULL | 表示名（例: "GitHub PAT - main"） |
| type | VARCHAR(50) | NOT NULL | github_pat / anthropic_api_key |
| encrypted_value | TEXT | NOT NULL | 暗号化された値 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### assignees（担当者）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| name | VARCHAR(255) | NOT NULL | コミット用の名前 |
| email | VARCHAR(255) | NOT NULL | コミット用のメールアドレス |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### tasks（タスク）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| assignee_id | INTEGER | FK → assignees.id | |
| status | VARCHAR(50) | NOT NULL DEFAULT 'pending' | pending / starting / running / testing / retrying / paused / completed / failed / stopped |
| current_phase | VARCHAR(50) | | lint / unit / build / integration / e2e |
| branch | VARCHAR(255) | NOT NULL | ブランチ名 |
| github_issue_number | INTEGER | | GitHub Issue番号 |
| container_id | VARCHAR(255) | | Docker コンテナID |
| compose_project | VARCHAR(255) | | Docker Compose プロジェクト名 |
| retry_count | INTEGER | NOT NULL DEFAULT 0 | 現在のリトライ回数 |
| last_activity_at | TIMESTAMP | | 最終操作日時（タイムアウト判定用） |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**statusの状態遷移**

```
pending → starting → running → testing → completed
                       ↑          │
                       │          ↓
                       │       retrying → running（リトライ）
                       │          │
                       │          ↓
                       │        failed
                       │
                    paused（一時停止から再開）
                       │
                    stopped（停止）
```

#### instructions（指示）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| task_id | INTEGER | FK → tasks.id, NOT NULL | |
| original_text | TEXT | NOT NULL | ユーザーの元の指示テキスト |
| converted_prompt | TEXT | | 変換後のプロンプト |
| confirmed_prompt | TEXT | | 確定されたプロンプト（編集後） |
| status | VARCHAR(50) | NOT NULL DEFAULT 'converting' | converting / pending_confirmation / confirmed / executing / completed / failed |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### instruction_files（指示に紐づくファイル）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| instruction_id | INTEGER | FK → instructions.id, NOT NULL | |
| file_id | INTEGER | FK → files.id, NOT NULL | |

#### files（アップロードファイル）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| task_id | INTEGER | FK → tasks.id | タスクに紐付く場合 |
| original_name | VARCHAR(255) | NOT NULL | 元のファイル名 |
| file_type | VARCHAR(50) | NOT NULL | xlsx / docx / pdf / png / md 等 |
| file_size | INTEGER | NOT NULL | バイト数 |
| storage_path | TEXT | NOT NULL | サーバー上の保存パス |
| conversion_status | VARCHAR(50) | NOT NULL DEFAULT 'pending' | pending / processing / completed / failed / not_required |
| converted_html_path | TEXT | | 変換後HTMLのパス |
| converted_text | TEXT | | 抽出されたテキスト（補助用） |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### extracted_images（抽出された画像）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| file_id | INTEGER | FK → files.id, NOT NULL | 元ファイル |
| image_name | VARCHAR(255) | NOT NULL | 画像ファイル名 |
| storage_path | TEXT | NOT NULL | 保存パス |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### test_runs（テスト実行）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| task_id | INTEGER | FK → tasks.id, NOT NULL | |
| instruction_id | INTEGER | FK → instructions.id | |
| status | VARCHAR(50) | NOT NULL | running / passed / failed |
| retry_number | INTEGER | NOT NULL DEFAULT 0 | |
| trigger_type | VARCHAR(50) | NOT NULL | auto / manual |
| started_at | TIMESTAMP | NOT NULL | |
| finished_at | TIMESTAMP | | |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### test_phases（テストフェーズ結果）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| test_run_id | INTEGER | FK → test_runs.id, NOT NULL | |
| type | VARCHAR(50) | NOT NULL | lint / unit / build / integration / e2e |
| status | VARCHAR(50) | NOT NULL | running / passed / failed / skipped |
| command | TEXT | NOT NULL | 実行コマンド |
| duration_ms | INTEGER | | 実行時間（ミリ秒） |
| stdout | TEXT | | 標準出力 |
| stderr | TEXT | | 標準エラー出力 |
| error_summary | TEXT | | エラー要約 |
| execution_order | INTEGER | NOT NULL | 実行順序 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### screenshots（E2Eテストスクリーンショット）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| test_run_id | INTEGER | FK → test_runs.id, NOT NULL | |
| test_phase_id | INTEGER | FK → test_phases.id | |
| name | VARCHAR(255) | NOT NULL | スクリーンショット名 |
| storage_path | TEXT | NOT NULL | 保存パス |
| is_failure | BOOLEAN | NOT NULL DEFAULT false | 失敗時の自動撮影か |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### repo_test_configs（テストコマンド設定）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | テスト名 |
| command | TEXT | NOT NULL | 実行コマンド |
| type | VARCHAR(50) | NOT NULL | lint / unit / build / integration / e2e |
| required | BOOLEAN | NOT NULL DEFAULT true | 必須フラグ |
| execution_order | INTEGER | NOT NULL | 実行順序 |
| depends_on | JSONB | DEFAULT '[]' | 依存サービス名の配列 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### repo_test_services（テストサービス設定）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | サービス名（postgres, redis等） |
| image | VARCHAR(255) | NOT NULL | Dockerイメージ |
| port | INTEGER | | ポート番号 |
| env | JSONB | DEFAULT '{}' | 環境変数 |
| init_script | VARCHAR(255) | | 初期化スクリプトファイル名 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### repo_app_server（アプリサーバー設定）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, UNIQUE, NOT NULL | |
| build_command | TEXT | | ビルドコマンド |
| start_command | TEXT | NOT NULL | 起動コマンド |
| port | INTEGER | NOT NULL | ポート番号 |
| health_check | TEXT | | ヘルスチェックURL |
| depends_on | JSONB | DEFAULT '[]' | 依存サービス名の配列 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### repo_policies（自動実行ポリシー）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, UNIQUE, NOT NULL | |
| mode | VARCHAR(50) | NOT NULL DEFAULT 'approval' | auto / approval |
| required_label | VARCHAR(255) | DEFAULT 'ai-task' | 必須ラベル |
| allowed_users | JSONB | DEFAULT '[]' | 許可ユーザーリスト |
| reject_unknown_users | BOOLEAN | NOT NULL DEFAULT true | 不明ユーザーを拒否 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### repo_env_vars（環境変数）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | 環境変数名 |
| encrypted_value | TEXT | NOT NULL | 暗号化された値 |
| is_secret | BOOLEAN | NOT NULL DEFAULT false | 秘匿情報フラグ |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_features（仕様: 機能）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| feature_code | VARCHAR(50) | NOT NULL | 機能コード（F001等） |
| name | VARCHAR(255) | NOT NULL | 機能名 |
| description | TEXT | | 概要 |
| status | VARCHAR(50) | DEFAULT 'draft' | draft / in_progress / completed / changed |
| related_issue | INTEGER | | 関連Issue番号 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_screens（仕様: 画面）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| feature_id | INTEGER | FK → spec_features.id, NOT NULL | |
| screen_code | VARCHAR(50) | NOT NULL | 画面コード（S001等） |
| name | VARCHAR(255) | NOT NULL | 画面名 |
| url_path | VARCHAR(255) | | URLパス |
| auth_required | BOOLEAN | DEFAULT false | 認証要否 |
| transitions | JSONB | DEFAULT '[]' | 遷移先画面コードの配列 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_elements（仕様: 画面要素）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| screen_id | INTEGER | FK → spec_screens.id, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | 要素名 |
| element_type | VARCHAR(50) | NOT NULL | text_input / button / table / dropdown 等 |
| validation | TEXT | | バリデーション条件 |
| action | TEXT | | 操作時の動作 |
| display_condition | TEXT | | 表示条件 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_endpoints（仕様: API）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| feature_id | INTEGER | FK → spec_features.id, NOT NULL | |
| endpoint_code | VARCHAR(50) | NOT NULL | APIコード（A001等） |
| method | VARCHAR(10) | NOT NULL | GET / POST / PUT / DELETE |
| path | VARCHAR(255) | NOT NULL | エンドポイントパス |
| auth_type | VARCHAR(50) | | 認証方式 |
| description | TEXT | | 説明 |
| response_success | TEXT | | 正常時レスポンス定義 |
| response_error | TEXT | | 異常時レスポンス定義 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_params（仕様: APIパラメータ）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| endpoint_id | INTEGER | FK → spec_endpoints.id, NOT NULL | |
| direction | VARCHAR(10) | NOT NULL | request / response |
| name | VARCHAR(255) | NOT NULL | パラメータ名 |
| data_type | VARCHAR(50) | NOT NULL | string / integer / boolean / object 等 |
| required | BOOLEAN | NOT NULL DEFAULT false | |
| description | TEXT | | 説明 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_tables（仕様: テーブル）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| feature_id | INTEGER | FK → spec_features.id, NOT NULL | |
| table_name | VARCHAR(255) | NOT NULL | テーブル名 |
| description | TEXT | | 説明 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_columns（仕様: カラム）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| table_id | INTEGER | FK → spec_tables.id, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | カラム名 |
| data_type | VARCHAR(50) | NOT NULL | データ型 |
| constraints | TEXT | | 制約（NOT NULL, UNIQUE等） |
| is_primary_key | BOOLEAN | NOT NULL DEFAULT false | |
| foreign_key | TEXT | | 外部キー参照先 |
| description | TEXT | | 説明 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_rules（仕様: ビジネスロジック）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| feature_id | INTEGER | FK → spec_features.id, NOT NULL | |
| rule_code | VARCHAR(50) | NOT NULL | ルールコード（R001等） |
| name | VARCHAR(255) | NOT NULL | ルール名 |
| condition | TEXT | | 条件 |
| process | TEXT | | 処理内容 |
| exception_handling | TEXT | | 例外処理 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### spec_change_history（仕様変更履歴）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| instruction_id | INTEGER | FK → instructions.id | 変更元の指示 |
| entity_type | VARCHAR(50) | NOT NULL | feature / screen / element / endpoint 等 |
| entity_id | INTEGER | NOT NULL | 対象レコードのID |
| change_type | VARCHAR(50) | NOT NULL | create / update / delete |
| field_name | VARCHAR(255) | | 変更されたフィールド名 |
| old_value | TEXT | | 変更前の値 |
| new_value | TEXT | | 変更後の値 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### templates（ドキュメントテンプレート）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | テンプレート名 |
| document_type | VARCHAR(50) | NOT NULL | requirements / basic_design / detailed_design / db_design / screen_design / unit_test_spec / unit_test_report / integration_test_report / e2e_test_report |
| file_format | VARCHAR(10) | NOT NULL | xlsx / docx |
| storage_path | TEXT | NOT NULL | テンプレートファイルの保存パス |
| field_mapping | JSONB | NOT NULL DEFAULT '{}' | 差し込みフィールドのマッピング定義 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### generated_documents（生成済みドキュメント）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| template_id | INTEGER | FK → templates.id, NOT NULL | |
| document_type | VARCHAR(50) | NOT NULL | ドキュメント種別 |
| name | VARCHAR(255) | NOT NULL | 生成ファイル名 |
| storage_path | TEXT | NOT NULL | 保存パス |
| scope | JSONB | NOT NULL | 生成対象範囲 |
| generated_at | TIMESTAMP | NOT NULL | |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### notifications（通知）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| user_id | INTEGER | FK → users.id, NOT NULL | |
| type | VARCHAR(50) | NOT NULL | task_completed / test_failed / approval_pending / error / warning / container_crash |
| title | VARCHAR(255) | NOT NULL | 通知タイトル |
| message | TEXT | NOT NULL | 通知メッセージ |
| task_id | INTEGER | FK → tasks.id | 関連タスク |
| is_read | BOOLEAN | NOT NULL DEFAULT false | |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### push_subscriptions（プッシュ通知購読）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| user_id | INTEGER | FK → users.id, NOT NULL | |
| endpoint | TEXT | NOT NULL | プッシュ通知エンドポイント |
| auth_key | TEXT | NOT NULL | 認証キー |
| p256dh_key | TEXT | NOT NULL | 暗号化キー |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### test_data_files（テストデータファイル）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| repository_id | INTEGER | FK → repositories.id, NOT NULL | |
| name | VARCHAR(255) | NOT NULL | ファイル名 |
| storage_path | TEXT | NOT NULL | 保存パス |
| file_size | INTEGER | NOT NULL | バイト数 |
| description | TEXT | | 説明 |
| created_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

#### system_settings（システム設定）

| カラム | 型 | 制約 | 説明 |
|---|---|---|---|
| id | SERIAL | PK | |
| key | VARCHAR(255) | UNIQUE, NOT NULL | 設定キー |
| value | TEXT | NOT NULL | 設定値 |
| updated_at | TIMESTAMP | NOT NULL DEFAULT NOW() | |

**初期値**

| key | value | 説明 |
|---|---|---|
| max_concurrent_tasks | 3 | 同時実行上限 |
| pause_timeout_minutes | 60 | 一時停止タイムアウト（分） |
| warning_timeout_hours | 24 | 警告通知タイムアウト（時間） |
| stop_timeout_days | 7 | 停止タイムアウト（日） |
| destroy_timeout_days | 30 | 破棄タイムアウト（日） |
| max_retry_count | 3 | 自動修正リトライ上限 |
| session_expiry_hours | 24 | セッション有効期限（時間） |

### 3.4 インデックス

主要なクエリパターンに対するインデックスを定義する。

```sql
CREATE INDEX idx_tasks_repository_id ON tasks(repository_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_last_activity ON tasks(last_activity_at);
CREATE INDEX idx_instructions_task_id ON instructions(task_id);
CREATE INDEX idx_files_task_id ON files(task_id);
CREATE INDEX idx_test_runs_task_id ON test_runs(task_id);
CREATE INDEX idx_test_phases_test_run_id ON test_phases(test_run_id);
CREATE INDEX idx_notifications_user_id_is_read ON notifications(user_id, is_read);
CREATE INDEX idx_spec_features_repository_id ON spec_features(repository_id);
CREATE INDEX idx_spec_screens_feature_id ON spec_screens(feature_id);
CREATE INDEX idx_spec_elements_screen_id ON spec_elements(screen_id);
CREATE INDEX idx_spec_endpoints_feature_id ON spec_endpoints(feature_id);
CREATE INDEX idx_spec_change_history_repository_id ON spec_change_history(repository_id);
CREATE INDEX idx_generated_documents_repository_id ON generated_documents(repository_id);
```

---

## 4. 画面遷移設計

### 4.1 画面一覧

| No | 画面ID | 画面名 | パス | 認証 |
|---|---|---|---|---|
| 1 | LOGIN | ログイン画面 | /login | 不要 |
| 2 | DASHBOARD | ダッシュボード | / | 必要 |
| 3 | TASK_CREATE | タスク作成画面 | /tasks/new | 必要 |
| 4 | TASK_WORK | タスク作業画面 | /tasks/{id} | 必要 |
| 5 | APPROVAL | 承認画面 | /approvals | 必要 |
| 6 | DOCS_GEN | ドキュメント生成画面 | /repositories/{id}/documents | 必要 |
| 7 | SPEC_VIEW | 仕様データベース画面 | /repositories/{id}/specs | 必要 |
| 8 | SETTINGS | 設定画面 | /settings | 必要 |
| 9 | REPO_SETTINGS | リポジトリ設定画面 | /settings/repositories/{id} | 必要 |

### 4.2 画面遷移図

```
                    ┌────────┐
                    │ LOGIN  │
                    └───┬────┘
                        │ GitHub OAuth認証成功
                        ↓
    ┌───────────────────────────────────────────┐
    │              DASHBOARD                     │
    │  ┌─────────────────────────────────────┐  │
    │  │ タスク一覧 / キュー / 承認待ち       │  │
    │  │ リソース状況 / 通知                  │  │
    │  └─────────────────────────────────────┘  │
    └──┬──────┬──────┬──────┬──────┬──────┬─────┘
       │      │      │      │      │      │
       ↓      │      │      │      │      ↓
  TASK_CREATE  │      │      │      │   SETTINGS
       │      │      │      │      │      │
       │      ↓      │      │      ↓      ↓
       │  TASK_WORK   │   APPROVAL  │  REPO_SETTINGS
       │      │      │      │      │
       │      │      ↓      │      │
       │      │   DOCS_GEN  │      │
       │      │      │      │      │
       │      │      ↓      │      │
       │      │  SPEC_VIEW  │      │
       │      │             │      │
       └──────┴─────────────┴──────┘
              （すべてDAHSBOARDに戻れる）
```

### 4.3 各画面のレイアウト構成

#### 共通レイアウト

```
┌───────────────────────────────────────────────────┐
│ ヘッダー                                           │
│  [Xolvien ロゴ] [ダッシュボード] [設定]  🔔(3) [👤] │
├───────────────────────────────────────────────────┤
│                                                    │
│  メインコンテンツ領域                                │
│                                                    │
│                                                    │
│                                                    │
└───────────────────────────────────────────────────┘
```

#### DASHBOARD（ダッシュボード）

```
┌───────────────────────────────────────────────────┐
│ ヘッダー                                           │
├───────────────────────────────────────────────────┤
│                                                    │
│  [+ 新規タスク作成]                                 │
│                                                    │
│  ── アクティブなタスク ──────────────────────────   │
│  ┌─────────────────────────────────────────────┐  │
│  │ #1 ログイン画面バリデーション   [E2Eテスト中]  │  │
│  │    my-app / feature/login  田中太郎          │  │
│  ├─────────────────────────────────────────────┤  │
│  │ #2 ユーザー管理API           [実行中]        │  │
│  │    my-app / feature/user-api  佐藤花子       │  │
│  ├─────────────────────────────────────────────┤  │
│  │ #3 メール通知機能            [一時停止]       │  │
│  │    my-app / feature/email  田中太郎          │  │
│  └─────────────────────────────────────────────┘  │
│                                                    │
│  ── 承認待ち (2件) ────────────────────────────    │
│  ┌─────────────────────────────────────────────┐  │
│  │ Issue #55 "検索機能の改善"  user123          │  │
│  │   [承認] [却下]                              │  │
│  └─────────────────────────────────────────────┘  │
│                                                    │
│  ── サーバーリソース ──────────────────────────    │
│  CPU: ████████░░ 78%  MEM: ██████░░░░ 55%         │
│  DISK: ███░░░░░░░ 32%  タスク: 3/5                 │
│                                                    │
└───────────────────────────────────────────────────┘
```

#### TASK_CREATE（タスク作成画面）

```
┌───────────────────────────────────────────────────┐
│ ヘッダー                                           │
├───────────────────────────────────────────────────┤
│                                                    │
│  タスク作成                                        │
│                                                    │
│  リポジトリ:   [▼ my-app                     ]     │
│  ブランチ:     ○ 既存 [▼ main            ]         │
│               ● 新規 [feature/___________]         │
│  担当者:       [▼ 田中太郎               ]         │
│                                                    │
│  ── GitHub Issue ──────────────────────────────    │
│  ☑ GitHub Issueを作成する                          │
│  タイトル:     [________________________________]  │
│  本文:         [________________________________]  │
│                [________________________________]  │
│  ラベル:       [ai-task]  [+追加]                   │
│                                                    │
│  ── 指示 ──────────────────────────────────────    │
│  [                                              ]  │
│  [   指示内容を入力してください                   ]  │
│  [                                              ]  │
│                                                    │
│  ── ファイル ──────────────────────────────────    │
│  [📎 ファイルをドラッグ&ドロップ、またはクリック]     │
│  画面仕様書.xlsx (変換完了 ✓)                       │
│                                                    │
│                         [キャンセル] [作成して開始]  │
│                                                    │
└───────────────────────────────────────────────────┘
```

#### TASK_WORK（タスク作業画面）

この画面は複数のパネルで構成される。

```
┌───────────────────────────────────────────────────────────┐
│ ヘッダー   タスク #1 ログイン画面バリデーション [E2Eテスト中] │
├──────────────────────────┬────────────────────────────────┤
│                          │                                │
│  ── 指示入力 ──────────  │  ── タブ ────────────────────  │
│  [                    ]  │  [ログ] [差分] [テスト] [ファイル]│
│  [  新しい指示を入力  ]  │   [仕様書] [スクリーンショット] │
│  [                    ]  │                                │
│  [📎 ファイル追加]       │  （ログタブの場合）             │
│  [指示を送信]            │  10:30:15 ファイル修正中...     │
│                          │  10:30:18 Login.tsx 更新       │
│  ── 指示履歴 ──────────  │  10:30:20 テスト実行開始       │
│  #5 バリデーション追加   │  10:30:23 リント... ✓          │
│    [確認中]              │  10:30:28 単体テスト... ✓      │
│  #4 デザイン修正         │  10:30:35 ビルド... ✓          │
│    [完了 ✓]              │  10:30:42 結合テスト... ✓      │
│  #3 初期実装             │  10:30:50 E2Eテスト... 実行中  │
│    [完了 ✓]              │                                │
│                          │  （テストタブの場合）           │
│  ── プロンプト確認 ────  │  ✓ リント         3.2s         │
│  ┌────────────────────┐  │  ✓ 単体テスト     8.5s         │
│  │変換後プロンプト    │  │  ✓ ビルド        15.0s         │
│  │                    │  │  ✓ 結合テスト    12.0s         │
│  │(編集可能)          │  │  ● E2Eテスト     実行中...     │
│  ├────────────────────┤  │                                │
│  │仕様変更点          │  │  リトライ: 0/3                 │
│  │ S001: validation   │  │                                │
│  │  追加             │  │                                │
│  ├────────────────────┤  │                                │
│  │[再変換] [確定実行] │  │                                │
│  └────────────────────┘  │                                │
│                          │                                │
│  ── 操作 ──────────────  │                                │
│  [手動テスト▼] [コミット]│                                │
│  [push] [PR作成]         │                                │
│                          │                                │
├──────────────────────────┴────────────────────────────────┤
│ ステータスバー: E2Eテスト実行中 (3/10) | リトライ 0/3       │
└───────────────────────────────────────────────────────────┘
```

#### SETTINGS（設定画面）

```
┌───────────────────────────────────────────────────┐
│ ヘッダー                                           │
├─────────────┬─────────────────────────────────────┤
│             │                                      │
│ サイドバー   │  メインコンテンツ                     │
│             │                                      │
│ ▶ プロフィール│ （プロフィールの場合）                │
│   リポジトリ │  名前:  [_________________]          │
│   認証情報  │  メール: [_________________]          │
│   全体設定  │                    [保存]             │
│             │                                      │
│             │ （リポジトリ一覧の場合）               │
│             │  ┌───────────────────────────────┐   │
│             │  │ my-app (private) [設定] [削除] │   │
│             │  │ my-lib (public)  [設定] [削除] │   │
│             │  └───────────────────────────────┘   │
│             │  [+ リポジトリ追加]                    │
│             │                                      │
│             │ （全体設定の場合）                     │
│             │  同時実行上限:    [3    ]              │
│             │  リトライ上限:    [3    ]              │
│             │  一時停止タイムアウト: [60  ] 分       │
│             │                    [保存]             │
│             │                                      │
└─────────────┴─────────────────────────────────────┘
```

#### REPO_SETTINGS（リポジトリ設定画面）

```
┌───────────────────────────────────────────────────┐
│ ヘッダー                                           │
├─────────────┬─────────────────────────────────────┤
│             │                                      │
│ サイドバー   │  my-app リポジトリ設定                │
│             │                                      │
│ ▶ 基本情報  │ （テストコマンドの場合）               │
│   テストコマンド│                                    │
│   テストサービス│  1. リント                          │
│   アプリサーバー│     コマンド: [npm run lint      ]   │
│   実行ポリシー│    種別: [▼ lint] 必須: [✓]         │
│   テストデータ│                                     │
│   環境変数  │  2. 単体テスト                        │
│   テンプレート│     コマンド: [npm test -- --unit ]   │
│             │     種別: [▼ unit] 必須: [✓]         │
│             │                                      │
│             │  [+ コマンド追加]       [保存]         │
│             │                                      │
│             │ （テストサービスの場合）               │
│             │  1. postgres                          │
│             │     イメージ: [postgres:16       ]    │
│             │     ポート:   [5432]                  │
│             │     環境変数: POSTGRES_DB=[test_db]   │
│             │                                      │
│             │  [+ サービス追加]       [保存]         │
│             │                                      │
└─────────────┴─────────────────────────────────────┘
```

### 4.4 主要な画面遷移シナリオ

**シナリオ1: Web UIからタスク作成→完了**

```
DASHBOARD → TASK_CREATE → TASK_WORK → DASHBOARD
  [新規タスク]  [作成して開始]  [プロンプト確認→確定]
                              [自動実行... 完了通知]
                              [PR作成]
```

**シナリオ2: GitHub Webhook経由のタスク**

```
(GitHub Issue作成) → DASHBOARD(承認待ちに表示) → APPROVAL
  → [承認] → TASK_WORK → (自動実行)
```

**シナリオ3: ドキュメント生成**

```
DASHBOARD → DOCS_GEN → (プレビュー確認) → ダウンロード
```

---

## 5. Docker設計

### 5.1 イメージ構成

Xolvienでは3つのDockerイメージを使用する。

#### xolvien-backend（バックエンドサーバー）

```dockerfile
FROM python:3.12-slim

# システム依存
RUN apt-get update && apt-get install -y \
    libreoffice-core \
    libreoffice-calc \
    libreoffice-writer \
    libreoffice-impress \
    tesseract-ocr \
    tesseract-ocr-jpn \
    && rm -rf /var/lib/apt/lists/*

# Python依存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# 主要パッケージ:
#   fastapi, uvicorn, celery, docker, asyncpg,
#   sqlalchemy, alembic, python-jose (JWT),
#   openpyxl, python-docx, pymupdf,
#   anthropic, httpx, python-multipart

COPY ./app /app
WORKDIR /app

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### xolvien-workspace（タスク用ワークスペース）

```dockerfile
FROM mcr.microsoft.com/playwright:v1.40.0-jammy

# Node.js（Playwrightイメージに含まれる）
# Python（テスト環境用）
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    git curl \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI
RUN npm install -g @anthropic/claude-code

# Playwright ブラウザのインストール
RUN npx playwright install --with-deps chromium firefox webkit

# 作業ディレクトリ
RUN mkdir -p /workspace/repo /workspace/docs /workspace/test-data /workspace/test-results
WORKDIR /workspace

# デフォルトはシェルを起動（バックエンドからコマンドを実行するため）
CMD ["tail", "-f", "/dev/null"]
```

#### xolvien-frontend（フロントエンド）

```dockerfile
FROM node:20-slim AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### 5.2 開発環境の Docker Compose構成（Xolvien自体）

```yaml
# docker-compose.yml（Xolvien本体の開発・運用構成）
version: "3.9"

services:
  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend

  backend:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://xolvien:xolvien@db:5432/xolvien
      - REDIS_URL=redis://redis:6379/0
      - GITHUB_CLIENT_ID=${GITHUB_CLIENT_ID}
      - GITHUB_CLIENT_SECRET=${GITHUB_CLIENT_SECRET}
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock  # Docker-in-Docker
      - xolvien-data:/data       # テストデータ・テンプレート等
      - xolvien-files:/files     # アップロードファイル
    depends_on:
      - db
      - redis

  celery-worker:
    build: ./backend
    command: celery -A worker worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://xolvien:xolvien@db:5432/xolvien
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - xolvien-data:/data
      - xolvien-files:/files
    depends_on:
      - db
      - redis

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: xolvien
      POSTGRES_PASSWORD: xolvien
      POSTGRES_DB: xolvien
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  redis:
    image: redis:7
    ports:
      - "6379:6379"

  cloudflared:
    image: cloudflare/cloudflared:latest
    command: tunnel --config /etc/cloudflared/config.yml run
    volumes:
      - ./cloudflared:/etc/cloudflared
    depends_on:
      - backend

volumes:
  pgdata:
  xolvien-data:
  xolvien-files:
```

### 5.3 タスク用 Docker Compose構成（動的生成）

バックエンドがタスクごとに動的にDocker Compose設定を生成し、起動する。

```yaml
# 動的生成される docker-compose-task-{task_id}.yml の例
version: "3.9"

services:
  workspace:
    image: xolvien-workspace
    container_name: xolvien-task-{task_id}-workspace
    volumes:
      - task-{task_id}-repo:/workspace/repo
      - /data/{repo_name}/test-data:/workspace/test-data:ro
      - /files/tasks/{task_id}/docs:/workspace/docs
      - task-{task_id}-results:/workspace/test-results
    environment:
      - ANTHROPIC_API_KEY={encrypted_key}
      - GIT_AUTHOR_NAME={assignee_name}
      - GIT_AUTHOR_EMAIL={assignee_email}
      - GIT_COMMITTER_NAME={assignee_name}
      - GIT_COMMITTER_EMAIL={assignee_email}
    networks:
      - task-{task_id}-net

  # 以下はテスト実行時のみ起動
  db:
    image: postgres:16
    container_name: xolvien-task-{task_id}-db
    environment:
      POSTGRES_DB: test_db
      POSTGRES_PASSWORD: test
    volumes:
      - /data/{repo_name}/test-data/seed.sql:/docker-entrypoint-initdb.d/seed.sql
    networks:
      - task-{task_id}-net
    profiles:
      - test  # テスト実行時のみ起動

  redis:
    image: redis:7
    container_name: xolvien-task-{task_id}-redis
    networks:
      - task-{task_id}-net
    profiles:
      - test

  app:
    build: /workspace/repo
    container_name: xolvien-task-{task_id}-app
    command: "npm run dev"
    ports:
      - "3000"
    depends_on:
      - db
      - redis
    networks:
      - task-{task_id}-net
    profiles:
      - test

networks:
  task-{task_id}-net:
    driver: bridge

volumes:
  task-{task_id}-repo:
  task-{task_id}-results:
```

### 5.4 Docker操作のフロー

```
タスク作成
  ↓
バックエンドが docker-compose-task-{id}.yml を動的生成
  ↓
docker compose -f docker-compose-task-{id}.yml up workspace
  → workspaceコンテナのみ起動
  ↓
workspaceコンテナ内で git clone / checkout
  ↓
指示実行時:
  docker exec workspace claude-code "{prompt}"
  ↓
テスト実行時:
  docker compose -f ... --profile test up -d db redis
    → テスト用サービスを起動
  docker exec workspace npm test -- --unit
  docker exec workspace npm test -- --integration
  docker compose -f ... --profile test up -d app
    → アプリサーバーを起動
  docker exec workspace npx playwright test
  docker compose -f ... --profile test down
    → テスト用サービスを停止
  ↓
タスク完了/削除時:
  docker compose -f docker-compose-task-{id}.yml down -v
    → 全コンテナ・ボリュームを破棄
```

### 5.5 ネットワーク隔離

各タスクは独立したDockerネットワークで隔離される。タスクAのコンテナからタスクBのコンテナにはアクセスできない。

```
xolvien-network（Xolvien本体）
  ├─ frontend
  ├─ backend
  ├─ db (PostgreSQL)
  └─ redis

task-1-net（タスク1専用）
  ├─ workspace
  ├─ db (テスト用)
  ├─ redis (テスト用)
  └─ app

task-2-net（タスク2専用）
  ├─ workspace
  ├─ db (テスト用)
  └─ app
```

### 5.6 ボリュームとデータの永続化

| ボリューム | 用途 | ライフサイクル |
|---|---|---|
| pgdata | Xolvien本体のPostgreSQLデータ | 永続 |
| xolvien-data | テストデータ、テンプレート等の共有ファイル | 永続 |
| xolvien-files | アップロードファイル | 永続 |
| task-{id}-repo | タスクのリポジトリ作業領域 | タスク削除時に破棄 |
| task-{id}-results | テスト結果・スクリーンショット | タスク削除時に破棄 |

### 5.7 リソース制限

各タスクのコンテナにはリソース制限を設定する。

```yaml
services:
  workspace:
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
        reservations:
          cpus: "0.5"
          memory: 1G
  db:
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 1G
  app:
    deploy:
      resources:
        limits:
          cpus: "1.0"
          memory: 2G
```

---

## 6. 主要処理シーケンス

### 6.1 タスク作成→完了の全体シーケンス

```
ユーザー          フロントエンド      バックエンドAPI     Celeryワーカー     Docker           GitHub
  │                │                │                │                │               │
  │ タスク作成      │                │                │                │               │
  ├───────────────→│ POST /tasks    │                │                │               │
  │                ├───────────────→│                │                │               │
  │                │                │ タスクをDBに保存 │                │               │
  │                │                │ Celeryにキュー  │                │               │
  │                │                ├───────────────→│                │               │
  │                │                │                │ compose up      │               │
  │                │                │                │ workspace       │               │
  │                │                │                ├───────────────→│               │
  │                │                │                │ git clone       │               │
  │                │                │                │ git checkout    │               │
  │                │                │                ├───────────────→│               │
  │                │  タスク作成完了 │                │                │               │
  │                │←───────────────┤                │                │               │
  │                │                │                │                │ Issue作成      │
  │                │                │                │                ├──────────────→│
  │ 指示を入力     │                │                │                │               │
  ├───────────────→│ POST           │                │                │               │
  │                │ /instructions  │                │                │               │
  │                ├───────────────→│                │                │               │
  │                │                │ Anthropic API   │                │               │
  │                │                │ プロンプト変換   │                │               │
  │                │                │ 仕様変更点抽出   │                │               │
  │                │                │                │                │               │
  │ プロンプト確認  │ 変換結果返却    │                │                │               │
  │←───────────────┤←───────────────┤                │                │               │
  │                │                │                │                │               │
  │ 確定ボタン     │                │                │                │               │
  ├───────────────→│ POST /confirm  │                │                │               │
  │                ├───────────────→│                │                │               │
  │                │                │ 仕様DB更新      │                │               │
  │                │                │ Celeryにキュー  │                │               │
  │                │                ├───────────────→│                │               │
  │                │                │                │ docker exec     │               │
  │                │                │                │ claude-code     │               │
  │                │                │                ├───────────────→│               │
  │                │                │                │                │               │
  │  ログ          │  WS: ログ      │                │  stdout/stderr │               │
  │←───────────────┤←───────────────┤←───────────────┤←───────────────┤               │
  │  ストリーミング │  ストリーミング │  ストリーミング │                │               │
  │                │                │                │                │               │
  │                │                │                │ テスト実行      │               │
  │                │                │                │ (後述6.2)       │               │
  │                │                │                │                │               │
  │                │                │                │ 全テスト成功    │               │
  │                │                │                │ git commit      │               │
  │                │                │                │ git push        │               │
  │                │                │                ├───────────────→│               │
  │                │                │                │                ├──────────────→│
  │  完了通知      │  WS: 完了      │                │                │  Issueコメント│
  │←───────────────┤←───────────────┤←───────────────┤                ├──────────────→│
  │  プッシュ通知  │                │                │                │               │
```

### 6.2 テスト実行→自動修正ループのシーケンス

```
Celeryワーカー          workspaceコンテナ      テストサービス群      バックエンドAPI
  │                      │                    │                   │
  │ ① リント実行          │                    │                   │
  ├─────────────────────→│                    │                   │
  │ docker exec lint     │                    │                   │
  │←─────────────────────┤                    │                   │
  │ 結果取得              │                    │                   │
  │                      │                    │                   │
  │ リント成功 → 次のフェーズへ                  │                   │
  │ リント失敗 → 自動修正ループへ（6.3）          │                   │
  │                      │                    │                   │
  │ ② 単体テスト実行     │                    │                   │
  ├─────────────────────→│                    │                   │
  │←─────────────────────┤                    │                   │
  │                      │                    │                   │
  │ ③ ビルド確認         │                    │                   │
  ├─────────────────────→│                    │                   │
  │←─────────────────────┤                    │                   │
  │                      │                    │                   │
  │ ④ テストサービス起動   │                    │                   │
  │ compose --profile     │                    │                   │
  │ test up db redis     │                    │                   │
  ├──────────────────────────────────────────→│                   │
  │                      │                    │                   │
  │ ヘルスチェック待ち     │                    │                   │
  ├──────────────────────────────────────────→│                   │
  │                      │                    │                   │
  │ ⑤ 結合テスト実行     │                    │                   │
  ├─────────────────────→│                    │                   │
  │ docker exec          │ DB接続             │                   │
  │ integration test     ├───────────────────→│                   │
  │←─────────────────────┤                    │                   │
  │                      │                    │                   │
  │ ⑥ アプリサーバー起動  │                    │                   │
  │ compose up app       │                    │                   │
  ├──────────────────────────────────────────→│                   │
  │                      │                    │                   │
  │ ⑦ E2Eテスト実行      │                    │                   │
  ├─────────────────────→│                    │                   │
  │ docker exec          │ http://app:3000    │                   │
  │ playwright test      ├───────────────────→│                   │
  │←─────────────────────┤                    │                   │
  │                      │                    │                   │
  │ ⑧ テストサービス停止  │                    │                   │
  │ compose --profile    │                    │                   │
  │ test down            │                    │                   │
  ├──────────────────────────────────────────→│                   │
  │                      │                    │                   │
  │ 全フェーズの結果をDB保存                     │                   │
  ├──────────────────────────────────────────────────────────────→│
```

### 6.3 自動修正ループのシーケンス

```
Celeryワーカー          workspaceコンテナ      バックエンドAPI
  │                      │                   │
  │ テスト失敗検知        │                   │
  │ retry_count < 3?     │                   │
  │ Yes                  │                   │
  │                      │                   │
  │ フィードバック構築    │                   │
  │ ├ エラーメッセージ    │                   │
  │ ├ 失敗テスト名       │                   │
  │ └ スクリーンショット  │                   │
  │   (E2E失敗時)        │                   │
  │                      │                   │
  │ Claude Code実行      │                   │
  │ 「以下のテストが失敗  │                   │
  │  しました。修正して   │                   │
  │  ください。残りN回」  │                   │
  ├─────────────────────→│                   │
  │                      │                   │
  │ ログストリーミング    │                   │
  │←─────────────────────┤                   │
  ├──────────────────────────────────────────→│ WS: ログ配信
  │                      │                   │
  │ 修正完了             │                   │
  │←─────────────────────┤                   │
  │                      │                   │
  │ retry_count++        │                   │
  │ テスト再実行（6.2に戻る）                  │
  │                      │                   │
  │ ─── retry_count >= 3 の場合 ───           │
  │                      │                   │
  │ 失敗通知             │                   │
  ├──────────────────────────────────────────→│ 通知作成
  │                      │                   │ プッシュ通知
  │                      │                   │ Issue コメント
```

### 6.4 GitHub Webhook受信→タスク起動のシーケンス

```
GitHub             バックエンドAPI                    DB
  │                  │                               │
  │ Webhook送信      │                               │
  │ (issue opened)   │                               │
  ├─────────────────→│                               │
  │                  │ ① 署名検証（HMAC-SHA256）      │
  │                  │    失敗 → 403返却、処理終了     │
  │                  │                               │
  │                  │ ② リポジトリ特定               │
  │                  ├──────────────────────────────→│
  │                  │←──────────────────────────────┤
  │                  │                               │
  │                  │ ③ ラベルチェック                │
  │                  │    ai-taskラベルなし → 無視     │
  │                  │                               │
  │                  │ ④ ユーザーチェック              │
  │                  │    許可リスト外 → 無視          │
  │                  │                               │
  │                  │ ⑤ ポリシー判定                 │
  │                  │    mode=auto → タスク即時作成   │
  │                  │    mode=approval →             │
  │                  │      承認待ちとしてDB保存       │
  │                  ├──────────────────────────────→│
  │                  │                               │
  │                  │      通知: 承認待ちIssue       │
  │                  │      （ユーザーが承認するまで待機）│
  │                  │                               │
  │  200 OK          │                               │
  │←─────────────────┤                               │
```

### 6.5 ドキュメント生成のシーケンス

```
ユーザー          フロントエンド      バックエンドAPI              Anthropic API
  │                │                │                          │
  │ 生成要求       │ POST           │                          │
  │ (種別+範囲)    │ /documents     │                          │
  ├───────────────→│ /generate      │                          │
  │                ├───────────────→│                          │
  │                │                │ ① 仕様DBからデータ取得    │
  │                │                │ ② テスト結果データ取得    │
  │                │                │ ③ テンプレート読み込み    │
  │                │                │                          │
  │                │                │ ④ 文章生成（所見・総括）  │
  │                │                ├─────────────────────────→│
  │                │                │←─────────────────────────┤
  │                │                │                          │
  │                │                │ ⑤ テンプレートに差し込み  │
  │                │                │    openpyxl / python-docx │
  │                │                │                          │
  │                │                │ ⑥ ファイル保存            │
  │                │                │                          │
  │ プレビュー表示  │ プレビュー返却  │                          │
  │←───────────────┤←───────────────┤                          │
  │                │                │                          │
  │ （必要に応じて文章を手動修正）    │                          │
  │                │                │                          │
  │ ダウンロード   │ GET /documents │                          │
  ├───────────────→│ /{id}          │                          │
  │                ├───────────────→│                          │
  │ Excel/Word     │←───────────────┤                          │
  │←───────────────┤                │                          │
```

### 6.6 プロンプト変換のシーケンス

```
バックエンドAPI                  workspaceコンテナ      Anthropic API
  │                              │                    │
  │ リポジトリ構造取得            │                    │
  │ docker exec ls -R            │                    │
  ├─────────────────────────────→│                    │
  │←─────────────────────────────┤                    │
  │                              │                    │
  │ git log取得                   │                    │
  │ docker exec git log          │                    │
  ├─────────────────────────────→│                    │
  │←─────────────────────────────┤                    │
  │                              │                    │
  │ プロンプト変換リクエスト構築   │                    │
  │ ├ ユーザーの元の指示          │                    │
  │ ├ リポジトリ構造              │                    │
  │ ├ git log                    │                    │
  │ ├ アップロードファイル（HTML）  │                    │
  │ ├ 仕様DBの現在の状態          │                    │
  │ └ 過去の指示履歴              │                    │
  │                              │                    │
  │ Claude API呼び出し            │                    │
  ├──────────────────────────────────────────────────→│
  │                              │                    │
  │ レスポンス:                   │                    │
  │ ├ 変換後プロンプト            │                    │
  │ ├ 仕様DB変更点               │                    │
  │ └ 参照ファイル一覧            │                    │
  │←──────────────────────────────────────────────────┤
  │                              │                    │
  │ DBに保存（pending_confirmation）                    │
```

---

## 7. ファイル変換処理設計

### 7.1 変換処理の全体フロー

```
ファイルアップロード（multipart/form-data）
  │
  ├─ バックエンドで受信
  │   ├─ 原本をストレージに保存（/files/originals/{file_id}/）
  │   └─ DBにfileレコード作成（conversion_status = 'pending'）
  │
  ├─ Celeryタスクとして変換処理をキュー
  │
  └─ 変換処理（ワーカー）
      │
      ├─ ファイル種別の判定（拡張子 + MIMEタイプ）
      │
      ├─ [Excel/Word/PowerPoint] → LibreOffice変換パイプライン（7.2）
      ├─ [PDF] → PDF変換パイプライン（7.3）
      ├─ [画像] → そのまま保存（7.4）
      └─ [テキスト系] → そのまま保存（7.4）
```

### 7.2 LibreOffice変換パイプライン（Excel/Word/PowerPoint）

```python
# 処理の疑似コード

def convert_office_file(file_path: str, file_id: int):
    output_dir = f"/files/converted/{file_id}"
    os.makedirs(output_dir, exist_ok=True)

    # ① LibreOfficeでHTML変換
    subprocess.run([
        "libreoffice", "--headless", "--convert-to", "html",
        "--outdir", output_dir,
        file_path
    ], timeout=120)

    html_path = find_html_file(output_dir)

    # ② 埋め込み画像を抽出・リネーム
    images = extract_and_rename_images(output_dir, file_id)
    #   LibreOfficeが出力した画像ファイル群を
    #   {original_name}_image001.png 形式にリネーム

    # ③ HTML内の画像パスを修正
    fix_image_paths(html_path, images)
    #   相対パスをAPI経由のURLに書き換え
    #   例: src="image001.png" → src="/api/v1/files/{img_id}/raw"

    # ④ 補助テキスト抽出（検索・プロンプト用）
    text_content = extract_text_from_html(html_path)
    save_as_markdown(output_dir, text_content)

    # ⑤ DB更新
    update_file_record(file_id,
        conversion_status='completed',
        converted_html_path=html_path
    )
    save_extracted_images(file_id, images)
```

**LibreOfficeの実行制約**

| 項目 | 値 |
|---|---|
| タイムアウト | 120秒 |
| 同時実行数 | 1（LibreOfficeはシングルプロセスのため排他制御） |
| 最大ファイルサイズ | 50 MB |
| 排他制御 | Celeryのconcurrencyまたはファイルロックで制御 |

### 7.3 PDF変換パイプライン

```python
def convert_pdf(file_path: str, file_id: int):
    output_dir = f"/files/converted/{file_id}"

    doc = fitz.open(file_path)

    text_parts = []
    images = []

    for page_num, page in enumerate(doc):
        # テキスト抽出
        text = page.get_text()

        if len(text.strip()) > 50:
            # テキストベースのページ → テキスト抽出
            text_parts.append(f"## ページ {page_num + 1}\n\n{text}")
        else:
            # スキャンされたページ → 画像化してOCR
            pix = page.get_pixmap(dpi=200)
            image_path = f"{output_dir}/page_{page_num + 1}.png"
            pix.save(image_path)
            images.append(image_path)

            # Tesseract OCR
            ocr_text = pytesseract.image_to_string(
                Image.open(image_path), lang='jpn+eng'
            )
            text_parts.append(f"## ページ {page_num + 1}\n\n{ocr_text}")

    # テキストを統合してMarkdown保存
    full_text = "\n\n".join(text_parts)
    save_as_markdown(output_dir, full_text)

    # HTML生成（テキスト + 画像参照）
    generate_html_from_text_and_images(output_dir, text_parts, images)
```

### 7.4 変換不要ファイルの処理

画像、テキスト系、ソースコードファイルは変換せずそのまま保存する。

```python
def handle_passthrough_file(file_path: str, file_id: int):
    # 原本をそのまま保存済み
    # conversion_status = 'not_required' に更新
    update_file_record(file_id, conversion_status='not_required')
```

### 7.5 コンテナへのファイル配置処理

タスクにファイルが紐付けられた際、変換済みファイルをworkspaceコンテナにコピーする。

```python
def deploy_files_to_container(task_id: int, file_ids: list[int]):
    container = get_workspace_container(task_id)

    for file_id in file_ids:
        file = get_file_record(file_id)

        # 原本をコピー
        docker_cp(file.storage_path,
                  container, f"/workspace/docs/originals/{file.original_name}")

        # 変換済みHTMLをコピー（存在する場合）
        if file.converted_html_path:
            docker_cp(file.converted_html_path,
                      container, f"/workspace/docs/html/{stem(file.original_name)}.html")

        # 抽出画像をコピー
        for img in file.extracted_images:
            docker_cp(img.storage_path,
                      container, f"/workspace/docs/images/{img.image_name}")
```

### 7.6 エラーハンドリング

| エラー | 対応 |
|---|---|
| LibreOfficeタイムアウト | conversion_status='failed'、ユーザーに通知 |
| 文字化け検知 | 変換結果のプレビューでユーザーが手動修正可能 |
| ファイルサイズ超過 | アップロード時に拒否（50MB制限） |
| 未対応ファイル形式 | conversion_status='not_supported'、ユーザーに通知 |
| 画像抽出失敗 | HTML自体は生成、画像欠損を通知 |

---

## 8. 仕様データベース処理設計

### 8.1 初期構築処理（既存仕様書からの自動抽出）

```
POST /repositories/{id}/specs/init
  │
  ├─ 入力: アップロード済みファイルIDの配列
  │
  ├─ 処理:
  │   ① 変換済みHTMLを取得（複数ファイル）
  │   ② Anthropic APIに抽出リクエスト
  │      ├─ システムプロンプト:
  │      │   「以下の仕様書から機能一覧、画面仕様、API仕様、
  │      │    DB仕様、ビジネスロジックを抽出し、
  │      │    指定のJSON形式で出力してください」
  │      ├─ 入力: HTMLテキスト + 画像（ビジョン）
  │      └─ 出力形式: 構造化JSON
  │   ③ JSONをパースしてDBに保存
  │   ④ 保存結果を返却
  │
  └─ 出力: 抽出された仕様データの一覧
```

**Anthropic APIへのリクエスト例**

```json
{
  "model": "claude-sonnet-4-5-20250929",
  "max_tokens": 8000,
  "system": "あなたは仕様書分析の専門家です。以下の仕様書から...",
  "messages": [
    {
      "role": "user",
      "content": [
        { "type": "text", "text": "以下のHTML形式の仕様書から..." },
        { "type": "text", "text": "<仕様書HTML>" }
      ]
    }
  ]
}
```

**期待するレスポンスJSON**

```json
{
  "features": [
    {
      "code": "F001",
      "name": "ログイン機能",
      "description": "メールアドレスとパスワードによるログイン",
      "screens": [
        {
          "code": "S001",
          "name": "ログイン画面",
          "url_path": "/login",
          "auth_required": false,
          "elements": [
            { "name": "メールアドレス入力欄", "type": "text_input", "validation": "メール形式必須" },
            { "name": "パスワード入力欄", "type": "password_input", "validation": "8文字以上" },
            { "name": "ログインボタン", "type": "button", "action": "POST /api/auth/login" }
          ]
        }
      ],
      "endpoints": [
        {
          "code": "A001",
          "method": "POST",
          "path": "/api/auth/login",
          "params": [
            { "direction": "request", "name": "email", "type": "string", "required": true },
            { "direction": "request", "name": "password", "type": "string", "required": true },
            { "direction": "response", "name": "token", "type": "string", "required": true }
          ]
        }
      ],
      "tables": [],
      "rules": []
    }
  ]
}
```

### 8.2 差分更新処理（指示確定時）

```
POST /tasks/{task_id}/instructions/{id}/confirm
  │
  ├─ 指示のspec_changesを取得
  │   （プロンプト変換時にAIが検出した仕様変更点）
  │
  ├─ ユーザーが確認・編集した変更点を適用:
  │   ① change_type = "create" → 新規レコード作成
  │   ② change_type = "update" → 既存レコード更新
  │   ③ change_type = "delete" → レコード削除
  │
  ├─ spec_change_history に変更履歴を記録:
  │   ├─ instruction_id（どの指示で変更されたか）
  │   ├─ entity_type, entity_id（何が変更されたか）
  │   ├─ change_type（追加/更新/削除）
  │   └─ old_value, new_value（変更前後の値）
  │
  └─ 仕様DB更新完了後、Claude Code実行を開始
```

### 8.3 実装後の整合性チェック（補完処理）

```
タスク完了時（テスト成功・push完了後）
  │
  ├─ workspaceコンテナ内のコードを解析:
  │   ├─ ルーティング定義からAPI一覧を抽出
  │   ├─ マイグレーションファイルからDB構造を抽出
  │   └─ コンポーネントファイルから画面要素を抽出
  │
  ├─ 現在の仕様DBと差分を比較
  │
  ├─ 差分がある場合:
  │   ├─ 通知: 「仕様DBとコードに差分があります」
  │   ├─ 差分内容を表示
  │   └─ ユーザーが「仕様DBに反映」ボタンで取り込み
  │
  └─ 差分がない場合:
      └─ 処理なし
```

### 8.4 プロンプト変換時の仕様変更検出ロジック

```python
def detect_spec_changes(original_text: str, repository_id: int) -> list:
    """
    プロンプト変換時に、指示内容から仕様DBの変更点を検出する。
    Anthropic APIに現在の仕様DB状態と指示内容を渡し、
    変更が必要な箇所を特定させる。
    """
    current_specs = get_specs_summary(repository_id)

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        system="""あなたは仕様変更の検出を行います。
        現在の仕様データベースの状態と、ユーザーの指示を比較し、
        仕様データベースへの変更点をJSON形式で出力してください。
        変更がない場合は空配列を返してください。""",
        messages=[
            {
                "role": "user",
                "content": f"""
                現在の仕様: {json.dumps(current_specs, ensure_ascii=False)}

                ユーザーの指示: {original_text}

                変更点をJSON配列で出力してください。
                """
            }
        ]
    )

    return parse_spec_changes(response)
```

---

## 9. 外部連携設計

### 9.1 GitHub API連携

#### 使用するAPI

| 操作 | APIエンドポイント | メソッド |
|---|---|---|
| リポジトリ情報取得 | /repos/{owner}/{repo} | GET |
| ブランチ一覧取得 | /repos/{owner}/{repo}/branches | GET |
| Issue作成 | /repos/{owner}/{repo}/issues | POST |
| Issueコメント追加 | /repos/{owner}/{repo}/issues/{number}/comments | POST |
| Issueクローズ | /repos/{owner}/{repo}/issues/{number} | PATCH |
| PR作成 | /repos/{owner}/{repo}/pulls | POST |
| Webhookイベント受信 | （Xolvien側エンドポイント） | POST |

#### GitHub API認証方式

```
HTTPヘッダー:
  Authorization: Bearer {personal_access_token}
  Accept: application/vnd.github.v3+json

必要なスコープ:
  - repo（リポジトリの読み書き）
  - write:org（組織リポジトリの場合）
```

#### Webhook受信処理

```python
async def handle_github_webhook(request: Request):
    # ① 署名検証
    signature = request.headers.get("X-Hub-Signature-256")
    body = await request.body()
    expected = "sha256=" + hmac.new(
        webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # ② イベント種別の判定
    event = request.headers.get("X-GitHub-Event")
    payload = await request.json()

    if event == "issues":
        action = payload["action"]
        if action in ("opened", "labeled"):
            await process_issue_event(payload)

    return {"status": "ok"}
```

#### レート制限への対応

| 項目 | 値 |
|---|---|
| GitHub API制限 | 5,000リクエスト/時間 |
| 対応方式 | X-RateLimit-Remaining ヘッダーを監視 |
| 制限接近時 | リクエスト間隔を広げる（指数バックオフ） |
| 制限到達時 | X-RateLimit-Reset まで待機、タスクを一時停止 |

### 9.2 Anthropic API連携

#### 使用する場面

| 場面 | モデル | 用途 |
|---|---|---|
| プロンプト変換 | claude-sonnet-4-5 | 指示をClaude Code向けプロンプトに変換 |
| 仕様抽出（初期構築） | claude-sonnet-4-5 | 仕様書から構造化データを抽出 |
| 仕様変更検出 | claude-sonnet-4-5 | 指示から仕様変更点を検出 |
| ドキュメント文章生成 | claude-sonnet-4-5 | 所見・総括等の文章を自動生成 |
| 整合性チェック | claude-sonnet-4-5 | コードと仕様DBの差分を分析 |

#### Claude Code CLI連携

```python
async def execute_claude_code(container_id: str, prompt: str, task_id: int):
    """
    workspaceコンテナ内でClaude Code CLIを実行し、
    stdoutをリアルタイムでWebSocketに配信する。
    """
    exec_result = docker_client.containers.get(container_id).exec_run(
        cmd=["claude", "--prompt", prompt],
        stream=True,
        demux=True,
        environment={
            "ANTHROPIC_API_KEY": get_decrypted_api_key(task_id)
        }
    )

    async for stdout_chunk, stderr_chunk in exec_result.output:
        if stdout_chunk:
            log_text = stdout_chunk.decode("utf-8")
            # DBにログ保存
            save_task_log(task_id, "claude_code", "info", log_text)
            # WebSocketに配信
            await broadcast_log(task_id, log_text)

        if stderr_chunk:
            err_text = stderr_chunk.decode("utf-8")
            save_task_log(task_id, "claude_code", "error", err_text)
            await broadcast_log(task_id, err_text)
```

#### API呼び出しの共通設定

```python
# Anthropic SDKの設定
anthropic_client = anthropic.Anthropic(
    api_key=get_system_anthropic_key(),
    timeout=300.0,        # 5分タイムアウト
    max_retries=3,        # 自動リトライ3回
)

# 共通のAPI呼び出しラッパー
async def call_anthropic_api(
    system_prompt: str,
    user_message: str,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 4096,
    images: list[str] = None
) -> str:
    content = [{"type": "text", "text": user_message}]

    if images:
        for img_path in images:
            with open(img_path, "rb") as f:
                img_data = base64.b64encode(f.read()).decode("utf-8")
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": img_data
                }
            })

    response = anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": content}]
    )

    return response.content[0].text
```

### 9.3 Cloudflare Tunnel連携

#### 設定ファイル

```yaml
# cloudflared/config.yml
tunnel: xolvien-tunnel
credentials-file: /etc/cloudflared/credentials.json

ingress:
  # GitHub Webhookエンドポイントのみ外部公開
  - hostname: xolvien.example.com
    path: /api/v1/webhooks/github
    service: http://backend:8000

  # GitHub OAuthコールバック
  - hostname: xolvien.example.com
    path: /api/v1/auth/github/callback
    service: http://backend:8000

  # Web UIは必要に応じて公開（VPN経由推奨）
  - hostname: xolvien.example.com
    service: http://frontend:80

  # デフォルト: 404
  - service: http_status:404
```

#### セットアップ手順

```bash
# 1. Cloudflare Tunnelの作成（初回のみ）
cloudflared tunnel create xolvien-tunnel

# 2. DNSの設定（初回のみ）
cloudflared tunnel route dns xolvien-tunnel xolvien.example.com

# 3. Docker Compose で自動起動（docker-compose.ymlに記載済み）
```

#### GitHub Webhook側の設定

| 項目 | 値 |
|---|---|
| Payload URL | https://xolvien.example.com/api/v1/webhooks/github |
| Content type | application/json |
| Secret | （設定画面で生成されたトークン） |
| Events | Issues, Issue comments |

---

## 10. セキュリティ設計

### 10.1 認証フロー（GitHub OAuth 2.0）

```
ブラウザ              バックエンド            GitHub
  │                    │                    │
  │ GET /auth/github   │                    │
  ├───────────────────→│                    │
  │                    │ state生成・保存     │
  │ 302 Redirect       │                    │
  │←───────────────────┤                    │
  │                    │                    │
  │ GitHub認証画面へ    │                    │
  ├────────────────────────────────────────→│
  │ ユーザーが承認     │                    │
  │←────────────────────────────────────────┤
  │ code + state      │                    │
  │                    │                    │
  │ GET /auth/github   │                    │
  │ /callback?code=... │                    │
  ├───────────────────→│                    │
  │                    │ state検証          │
  │                    │ code → token交換   │
  │                    ├───────────────────→│
  │                    │←───────────────────┤
  │                    │ access_token       │
  │                    │                    │
  │                    │ ユーザー情報取得    │
  │                    ├───────────────────→│
  │                    │←───────────────────┤
  │                    │ github_id, login   │
  │                    │                    │
  │                    │ 許可ユーザー確認    │
  │                    │ JWTトークン生成     │
  │                    │ セッション保存      │
  │                    │                    │
  │ Set-Cookie: jwt=...│                    │
  │←───────────────────┤                    │
  │ Redirect /         │                    │
```

### 10.2 JWTトークン仕様

```json
{
  "header": {
    "alg": "HS256",
    "typ": "JWT"
  },
  "payload": {
    "sub": "github_user_id",
    "login": "github_login",
    "iat": 1707600000,
    "exp": 1707686400
  }
}
```

| 項目 | 値 |
|---|---|
| アルゴリズム | HS256 |
| 署名キー | ENCRYPTION_KEY環境変数 |
| 有効期限 | 24時間（設定で変更可能） |
| 格納場所 | HttpOnly Cookie + Authorization ヘッダー |
| リフレッシュ | アクティビティがある場合は自動延長 |

### 10.3 認証情報の暗号化

APIキーやトークン等の秘匿情報は、AES-256-GCMで暗号化してDBに保存する。

```python
from cryptography.fernet import Fernet

# 暗号化キーは環境変数から取得
ENCRYPTION_KEY = os.environ["ENCRYPTION_KEY"]
cipher = Fernet(ENCRYPTION_KEY)

def encrypt_credential(plaintext: str) -> str:
    return cipher.encrypt(plaintext.encode()).decode()

def decrypt_credential(encrypted: str) -> str:
    return cipher.decrypt(encrypted.encode()).decode()
```

| 暗号化対象 | テーブル | カラム |
|---|---|---|
| GitHub Personal Access Token | credentials | encrypted_value |
| Anthropic API Key | credentials | encrypted_value |
| 環境変数（secret=true） | repo_env_vars | encrypted_value |
| Webhook Secret | system_settings | value（暗号化） |

### 10.4 API認証ミドルウェア

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer

security = HTTPBearer()

async def get_current_user(token: str = Depends(security)) -> User:
    try:
        payload = jwt.decode(token, ENCRYPTION_KEY, algorithms=["HS256"])
        user = await get_user_by_github_id(payload["sub"])
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
```

### 10.5 Webhookエンドポイントのセキュリティ

Webhookエンドポイント（/api/v1/webhooks/github）は認証不要だが、以下の防御を行う。

| 防御レイヤー | 方法 |
|---|---|
| 署名検証 | HMAC-SHA256でペイロードの改ざんを検証 |
| IPフィルタリング | GitHubのWebhook送信元IPをホワイトリスト登録（オプション） |
| レート制限 | 1分あたり60リクエストまで |
| ペイロードサイズ制限 | 最大25MB |

### 10.6 コンテナのセキュリティ

| 項目 | 方針 |
|---|---|
| ネットワーク隔離 | 各タスクは独立したDockerネットワーク |
| ホストアクセス | コンテナからホストのDocker socketへのアクセスは禁止（バックエンドのみ許可） |
| ファイルシステム | テストデータは読み取り専用でマウント |
| リソース制限 | CPU・メモリの上限を設定（5.7参照） |
| 秘匿情報 | APIキー等は環境変数で注入、コンテナ内にファイルとして保存しない |
