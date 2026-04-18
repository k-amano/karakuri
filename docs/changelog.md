# 改修履歴

---

## 2026-04-14

### 前回の続きから再開（ステップバー）

**概要**: タスク詳細画面にステップバーを追加し、完了済みのステップから再開できるようにした。

**変更内容:**
- フロントエンド `TaskDetail.tsx` にステップバーUI（実装 → テストケース → 単体テスト → 結合テスト* → E2Eテスト* → 実装確認）を追加
- ページロード時に `GET /instructions/last-completed` と `GET /test-runs` でDB履歴を取得し、ステップ状態を復元
- 完了済みステップをクリックするとその画面に切り替わる。「実装」ステップは前回の指示を入力欄に復元する
- 旧バナー方式（`isResumed` フラグ + 青いバナー）を廃止
- バックエンド `instructions.py` に `GET /last-completed` エンドポイントを追加

---

## 2026-04-12

### フェーズ1：単体テスト自動化

**概要**: テストケース生成・単体テスト実行・自動修正ループを実装した。

**変更内容:**
- バックエンド `claude_service.py` に `generate_test_cases()`、`run_unit_tests()` を追加
  - テストコマンドはClaude Agentが `package.json` / `pyproject.toml` 等から自動判断
  - pytest未インストール時はClaude Agentが依存パッケージのインストールから実施
  - 自動修正ループ：最大3回。失敗テスト名・エラーメッセージ・標準出力をフィードバック
  - テストレポートを `/workspace/repo/test-reports/test-report-{日時}-unit.md` に保存
- バックエンド `instructions.py` に以下のエンドポイントを追加
  - `POST /generate-test-cases`（ストリーミング）
  - `POST /run-unit-tests`（ストリーミング）
- DBマイグレーション：`TestRun` モデルに `test_type`（UNIT/INTEGRATION/E2E）、`test_cases`、`retry_count`、`report_path` カラムを追加
- フロントエンドにテストケース確認パネル・実装確認パネルを追加
- `PromptState` を拡張：`test_cases` / `running_tests` / `reviewing` を追加

---

## 2026-04-07（推定）

### MVP 初期実装

**概要**: バックエンド・フロントエンドの基本機能を一通り実装した。

**変更内容:**
- バックエンド全機能実装（Docker管理、タスク/リポジトリ API、Claude Code実行、WebSocketログ配信、DB永続化）
- フロントエンド全機能実装（ダッシュボード、タスク作成、タスク詳細、ログビューア、要件確認フロー、プロンプト確認）
- `claude_service.py` の Claude Code実行をシミュレーションから実際のCLI（`--dangerously-skip-permissions` モード）に切り替え
- プロジェクト名を karakuri → Xolvien に変更
