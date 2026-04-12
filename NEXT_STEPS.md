# Next Steps — Xolvien

## 現在の状態

フェーズ1（単体テスト自動化）まで実装済み。

完成しているフロー:
```
指示入力 → 要件確認 → プロンプト承認 → 実装
→ テストケース生成・承認 → テスト実行（自動修正ループ）
→ 実装レビュー → Git Push
```

---

## 次の実装ステップ（優先順位順）

### 1. 結合テスト（フェーズ2）

単体テストと同様の流れで、DB・API 接続を伴うテストを実装する。

**バックエンド:**
- `claude_service.py` に `run_integration_tests()` を追加
  - `TestType.INTEGRATION` で `TestRun` を作成
  - テストコンテナ内で DB や API を起動した状態でテスト実行
- `instructions.py` に `/run-integration-tests` エンドポイントを追加

**フロントエンド:**
- 単体テスト完了後に結合テストへ進むフローを追加
- `PromptState` に `'integration_tests'` を追加

---

### 2. E2E テスト（フェーズ3）

Playwright を使ったブラウザ操作テストの実装。

**バックエンド:**
- `claude_service.py` に `run_e2e_tests()` を追加
  - `TestType.E2E` で `TestRun` を作成
  - Playwright のスクリーンショットをフィードバックに含める
  - テストレポートにスクリーンショットのパスを記録

**フロントエンド:**
- E2E テスト結果にスクリーンショットプレビューを表示

---

### 3. PR 自動作成

テスト完了・ユーザー承認後に GitHub PR を自動作成する。

**バックエンド:**
- `git/push` エンドポイントを拡張、または新規に `git/create-pr` エンドポイントを追加
- `gh pr create` を使ってコンテナ内から PR を作成
- PR タイトル・本文を Claude が生成

**フロントエンド:**
- 実装レビュー画面の「承認」後に PR 作成オプションを表示

---

### 4. GitHub Issue 連携

GitHub Webhook でイシューを受け取り、タスクを自動生成・実行する。

**バックエンド:**
- `/api/v1/webhooks/github` エンドポイントを追加
- Issue の本文をタスクの指示として使用
- 自動的にフローを開始

---

### 5. マルチユーザー対応

シングルユーザーでの全機能実装完了後に着手する。

- GitHub OAuth 認証（`python-social-auth` または `authlib`）
- ユーザーごとのリポジトリ・タスク管理
- ストリーミングのブロッキング解消（現在は1タスクずつ実行）
- ユーザーごとのリソース制限

---

## 参考: 主要ファイル

```
backend/app/
├── services/
│   ├── claude_service.py   ← テスト実行ロジックの中心
│   └── test_service.py     ← テスト結果パース
├── api/
│   ├── instructions.py     ← テスト関連エンドポイント
│   └── tasks.py
└── models/
    └── test_run.py         ← TestType enum (UNIT / INTEGRATION / E2E)

frontend/src/
├── pages/TaskDetail.tsx    ← UIフロー全体
└── services/api.ts         ← API呼び出し
```

## 関連ドキュメント

- `docs/requirements-revision.md` — 実行フロー設計・テスト設計の詳細
- `MVP_IMPLEMENTATION_STATUS.md` — 実装済み機能の一覧
