# Xolvien 実装状況

**最終更新**: 2026-04-12

## 概要

フロントエンド・バックエンドともに実装済み。現在はフェーズ1（単体テスト自動化）まで完了。

---

## 完了済み機能

### バックエンド

| 機能 | 状態 | 備考 |
|---|---|---|
| Docker コンテナ管理 | ✅ | タスクごとに隔離されたコンテナを自動生成 |
| タスク管理 API | ✅ | CRUD + 停止 + ログ取得 |
| リポジトリ管理 API | ✅ | CRUD |
| Claude Code 実行 | ✅ | エージェントモード（--dangerously-skip-permissions）|
| 要件ヒアリング | ✅ | 不明点をClaudeが質問、十分な情報が揃ったら自動的にプロンプト生成へ |
| プロンプト自動生成 | ✅ | ユーザーの簡潔な指示 → 最適化されたプロンプトに変換 |
| テストケース生成 | ✅ | 実装プロンプトからMarkdown形式のテストケース一覧を生成 |
| 単体テスト実行 | ✅ | テストコード生成 → 実行 → 自動修正ループ（最大3回）|
| テスト結果保存 | ✅ | Markdown形式で `/workspace/repo/test-reports/` に保存 |
| WebSocket ログストリーミング | ✅ | タスクごとのリアルタイムログ配信 |
| DB 永続化 | ✅ | PostgreSQL 16、Alembic マイグレーション管理 |
| 認証 | ✅ | Bearer トークン（MVP用固定トークン） |

### フロントエンド

| 機能 | 状態 | 備考 |
|---|---|---|
| ダッシュボード | ✅ | タスク一覧、ステータスバッジ、作成ボタン |
| タスク作成フォーム | ✅ | リポジトリ選択、ブランチ名入力 |
| タスク詳細画面 | ✅ | 左右分割ペイン（ログ / 操作パネル）、リサイズ可能 |
| ログビューア | ✅ | WebSocket リアルタイム + 履歴ログ、色分け表示 |
| 要件確認フロー | ✅ | Claude との Q&A、スキップ可能 |
| プロンプト確認 | ✅ | 生成されたプロンプトを表示、フィードバック入力で再生成 |
| テストケース確認 | ✅ | 生成後にユーザーが編集・承認 |
| 実装レビュー画面 | ✅ | テスト完了後に承認 / 差し戻し |
| Git Push | ✅ | ワンクリックでリモートに push |

---

## 実装済み API エンドポイント

```
GET  /health
GET  /docs

GET    /api/v1/repositories
POST   /api/v1/repositories
GET    /api/v1/repositories/{id}
PATCH  /api/v1/repositories/{id}
DELETE /api/v1/repositories/{id}

GET    /api/v1/tasks
POST   /api/v1/tasks
GET    /api/v1/tasks/{id}
PATCH  /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/stop
DELETE /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/git/push

POST /api/v1/tasks/{id}/instructions
POST /api/v1/tasks/{id}/instructions/execute-stream
POST /api/v1/tasks/{id}/instructions/clarify
POST /api/v1/tasks/{id}/instructions/generate-prompt
POST /api/v1/tasks/{id}/instructions/generate-test-cases
POST /api/v1/tasks/{id}/instructions/run-unit-tests
GET  /api/v1/tasks/{id}/instructions
GET  /api/v1/tasks/{id}/instructions/{instruction_id}

POST /api/v1/tasks/{id}/test-runs
GET  /api/v1/tasks/{id}/test-runs
GET  /api/v1/tasks/{id}/test-runs/{run_id}

GET /api/v1/tasks/{id}/logs
WS  /api/v1/ws/tasks/{id}/logs
WS  /api/v1/ws/tasks/{id}/status
```

---

## ユーザーフロー（現在の実装）

```
1. 指示入力
2. 要件確認（Claude との Q&A） ← スキップ可
3. プロンプト確認・承認 → 実行
4. テストケース生成（Claude が自動生成）
5. テストケースをユーザーが確認・編集・承認
6. テストコード生成 → 単体テスト実行
7. 失敗した場合は自動修正ループ（最大3回）
8. テスト完了後にユーザーが実装を確認 → 承認 / 差し戻し
9. Git Push
```

---

## 今後の実装予定（優先順位順）

### フェーズ2: 結合テスト

- DB・API 接続を伴うテストの実行
- 単体テストと同様の自動修正ループ

### フェーズ3: E2E テスト

- Playwright によるブラウザ操作テスト
- スクリーンショットのフィードバック活用
- テストレポートにスクリーンショットを含める

### PR 自動作成

- テスト完了後に GitHub PR を自動作成
- PR タイトル・本文を Claude が生成

### GitHub Issue 連携

- Webhook でイシューを受け取り、タスクを自動生成・実行

### マルチユーザー対応

- GitHub OAuth 認証
- ストリーミングのブロッキング解消
- ユーザーごとのリソース管理

---

## 既知の制限事項

- **Claude Code CLI**: 実際の CLI を使用（`--dangerously-skip-permissions` モード）
- **認証**: 固定トークン（`dev-token-12345`）。GitHub OAuth は未実装
- **シングルユーザー**: デフォルトユーザー1名のみ
- **Excel テストレポート**: 将来対応（現在は Markdown のみ）

---

## 開発環境の起動

```bash
# データベース
docker compose up -d db

# バックエンド
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# フロントエンド
cd frontend
npm run dev
```

アクセス先:
- フロントエンド: http://localhost:5173
- バックエンド API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
