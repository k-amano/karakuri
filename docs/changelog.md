# 改修履歴

---

## 2026-05-02（2）

### 日英両言語対応（UI i18n）

**変更内容:**

- フロントエンド `src/i18n/ja.ts`：全UI文字列の日本語翻訳マップを新設
  - 動的文字列（進捗カウンター・エラーメッセージ等）は関数型キーで対応
- フロントエンド `src/i18n/en.ts`：同構造の英語翻訳マップを新設
- フロントエンド `src/i18n/index.ts`：`LangContext` / `useLang()` hook を新設
  - `localStorage`（キー: `xolvien-lang`）に選択言語を永続化
  - デフォルト言語: 日本語
- フロントエンド `src/main.tsx`：`LangProvider` でアプリ全体をラップ
- フロントエンド `Dashboard.tsx` / `TaskCreate.tsx` / `TaskDetail.tsx`：
  - 全ハードコード文字列を `t.xxx` に置換
  - 各ページのヘッダーに `JA` / `EN` トグルボタンを追加
  - ステップバーのラベルを `getStepLabel(step.id)` で都度参照し、切り替え即時反映
  - `formatDate` のロケールを `lang` に応じて `ja-JP` / `en-US` に切り替え

---

## 2026-05-02

### E2Eテスト: verdict「未判定」バグの修正

**変更内容:**

- バックエンド `claude_service.py`：E2E テスト結果が全件「未判定」になる問題を修正
  - **原因1**: `_detect_test_command()` が Node.js プロジェクトに対して `npm test`（Jest）を返していたため、Jest が Playwright テストファイルを実行しようとして失敗・スキップされていた
  - **原因2**: `--reporter=line` 形式は端末制御コード（`[1A[2K`）のみで `✓`/`✘` を含まないため、`_extract_result_for_function()` が verdict を判定できなかった
  - **対応1**: `_detect_e2e_test_command()` を新設し、E2E 時は `_detect_test_command()` をバイパスして `npx playwright test --reporter=list 2>&1` を使用
  - **対応2**: `--reporter=list` に変更（`✓`/`✘` が1テストごとに出力される形式）
  - **対応3**: `_extract_result_for_function()` に Playwright `--reporter=list` 形式のパターンを追加（`function_name` を含む行で `✓`/`✘` を判定）
  - **対応4**: `XOLVIEN_RESULT:` が出力された TC は「テストが実行された証拠」として exit_code から verdict を確定。出力されなかった TC は `FAILED` として扱い、「未判定」を終端状態としない
  - **対応5**: 自動修正プロンプトに禁止事項を追加（`try/catch` で例外を握り潰して成功扱いにすること、`expect` 条件の弱体化を禁止。環境依存の問題は `grantPermissions()` / `page.route()` でモックして正しく検証するよう指示）

- ドキュメント `docs/roadmap.md`：今後の実装予定項目を追加
  - 日英両言語対応（優先度: 高）
  - ファイルアップロードによる要件解析
  - ドキュメント自動生成
  - 進捗インジケーターの改善
  - メッセージをいつでも送信可能にする
  - 例外ハンドリングの改善

---

## 2026-04-30

### フェーズ3: E2Eテスト（Playwright）

**変更内容:**

- バックエンド `claude_service.py`：`run_e2e_tests()` メソッドを追加
  - `_run_tests()` に `TestType.E2E` を渡すラッパー
  - `generate_test_cases(TestType.E2E)` でテストケース ID を `E2E-NNN`、関数名を `test_e2e001_` 形式で生成
  - E2E テストコード生成プロンプトを追加：Playwright のインストール、アプリのバックグラウンド起動、ヘッドレスモード実行、スクリーンショットを `/workspace/repo/test-reports/screenshots/` に保存する指示を含む
  - 結果ファイルを `/tmp/xolvien_e2e_results.jsonl` で管理（単体・結合と独立）
  - `[E2E]` タグでログを出力

- バックエンド `claude_service.py`：`generate_test_cases()` のE2E対応
  - E2E専用テストケース生成プロンプトを追加：ブラウザ操作シナリオ（URL・クリック・入力・期待表示）を具体的に記述させる指示。8〜12件程度
  - `_run_tests()` / `generate_test_cases()` 内の `is_integration` 単純二値分岐を `test_type` 直接参照に変更し、UNIT / INTEGRATION / E2E の三値を正しく処理

- バックエンド `models/test_case_item.py`：`tc_id` プロパティに `E2E` タイプを追加（`E2E-NNN` 形式）

- バックエンド `schemas/instruction.py`：`RunE2ETestsRequest` を追加

- バックエンド `api/instructions.py`：E2Eエンドポイントを追加
  - `POST /generate-e2e-test-cases`（ストリーミング）
  - `POST /run-e2e-tests`（ストリーミング）

- フロントエンド `services/api.ts`：E2E APIクライアント関数を追加
  - `generateE2ETestCasesStream()`
  - `runE2ETestsStream()`
  - `getTestCaseItems()` の型引数に `'e2e'` を追加

- フロントエンド `pages/TaskDetail.tsx`：E2Eテストフローを実装
  - `ChatEntry` 型に `e2e_test_cases_generating` / `e2e_test_cases_ready` を追加（シアン `#06b6d4` 配色）
  - ステップバーの「E2Eテスト」から `future: true` フラグを削除してアクティブ化
  - セッション復元時に E2E テストケース（`getTestCaseItems(taskId, 'e2e')`）と最新 E2E TestRun を DB から取得して復元
  - ステップ遷移を更新：結合テスト合格 → E2Eテストへ自動遷移、E2Eテスト合格 → 実装確認へ遷移
  - `handleApproveE2ETestCases()` / `handleGenerateE2ETestCasesManual()` ハンドラを追加
  - `renderActionButtons()` に E2Eテストステップ用のボタン群を追加
  - `renderInputArea()` の disabled 条件に `e2e_test` を追加

- ドキュメント `docs/spec.md`・`docs/roadmap.md` を更新

---

## 2026-04-28

### 結合テスト品質改善・バグ修正

**変更内容:**

- バックエンド `claude_service.py`：結合テスト実行時の EACCES エラーを修正
  - 単体テスト用の `/tmp/xolvien_tc_results.jsonl` のみ事前作成していたため、結合テストで `/tmp/xolvien_itc_results.jsonl` への書き込みが全件失敗していた
  - `_run_tests()` に `results_file` 変数を追加し、`is_integration` フラグで JSONL ファイルパスを切り替え。作成・読み取りの両方で正しいパスを使用

- バックエンド `claude_service.py`：結合テストケース生成プロンプトを改善
  - 単体テストとの違い（DOM/localStorage ではなく HTTP リクエスト→API→DB のフロー）を明示するセクションを追加
  - `target_screen`・`operation`・`expected_output` に HTTP メソッド・URL・リクエストボディ・レスポンスステータスを必須記述するよう指示を強化
  - テストケース件数を 10〜15 件に制限（単体テスト同様の大量件数から削減）

- バックエンド `claude_service.py`：結合テストコード生成プロンプトの `XOLVIEN_RESULT:` サンプルを修正
  - 結合テストのサンプルが `TC-001`/`test_tc001_xxx` のままだったため `ITC-001`/`test_itc001_xxx` に切り替え

### フェーズ2: 結合テストケース分離（案A）

**変更内容:**

- バックエンド `claude_service.py`：`generate_test_cases()` に `test_type` 引数を追加
  - UNIT: `TC-NNN` / `test_tc001_` 形式、INTEGRATION: `ITC-NNN` / `test_itc001_` 形式
  - 既存の同 `test_type` の TC のみ削除して保存（他種別は保持）
- バックエンド `instructions.py`：`POST /generate-integration-test-cases`・`POST /run-integration-tests` エンドポイントを追加
- DBマイグレーション `a1b2c3d4e5f6`：`test_case_items` テーブルに `test_type` カラム追加（既存の `testtype` PG enum を `create_type=False` で共有）
- フロントエンド `TaskDetail.tsx`：結合テストケースの生成→確認→承認→実行の独立フローを追加
- フロントエンド `api.ts`：`getTestCaseItems(taskId, testType?)` に `test_type` クエリパラメータ対応を追加
- セッション再開時に単体・結合テストケースをそれぞれ DB から復元
- エラー発生時にチャット欄にエラーメッセージを表示（サイレント握り潰しを廃止）

---

## 2026-04-21

### テスト結果サマリー表示・修正UI改善（H2・H3）

**変更内容:**

- フロントエンド `TaskDetail.tsx`：実装確認パネルにテスト結果サマリーバナーを追加（H2）
  - テスト完了後および再開時に passed / failed 件数を緑 / 赤バナーで表示
  - `testResultSummary` state で管理し、テスト完了時とページロード時の両方でセット

- フロントエンド `TaskDetail.tsx`：テストケース修正UIを `window.prompt` からインライン入力欄に変更（H3）
  - 「修正を依頼」ボタンでパネル内にテキストエリア + 送信 / キャンセルボタンをトグル表示
  - 送信するとテストケースを再生成。キャンセルで入力欄を閉じる

---

## 2026-04-19

### コンテナ自動再起動・ステップバー改善・文字化け修正

**概要**: 翌日に続きから作業できない問題の修正、ステップバーのUI改善、ストリーミング文字化けの修正。

**変更内容:**

- バックエンド `docker_service.py`：`ensure_container_running()` メソッドを追加
  - `execute_command()` / `execute_command_stream()` の実行前にコンテナの状態を確認し、停止していれば自動で再起動する
  - これにより、`docker compose down` で停止した翌日でもタスクを作り直さずに続きから操作できる

- バックエンド `docker_service.py`：ストリーミングのUTF-8文字化けを修正（H1）
  - `chunk.decode("utf-8", errors="replace")` を `codecs.getincrementaldecoder` に変更
  - チャンク境界でマルチバイト文字が分割されても正しく結合してからデコードする

- フロントエンド `TaskDetail.tsx`：ステップバーのUI改善
  - 選択中のステップを黄色背景・黒テキストで強調表示
  - `テストケース` と `単体テスト` の2ステップを `単体テスト` 1ステップに統合（動作の違いがなかったため）
  - ステップバーのボタンからテスト結果件数の表示を削除（操作ボタンに情報を混在させない）
  - ページロード時の自動再開でも着地したステップが選択状態で表示される

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
