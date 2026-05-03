"""Claude Code execution service."""
import os
import base64
import asyncio
import json
from typing import AsyncGenerator
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy import select as sa_select
from app.models.task import Task, TaskStatus
from app.models.instruction import Instruction, InstructionStatus
from app.models.test_run import TestRun, TestType
from app.models.task_log import TaskLog, LogLevel, LogSource
from app.models.test_case_item import TestCaseItem
from app.models.test_case_result import TestCaseResult, Verdict
from app.services.docker_service import get_docker_service

# Python script for text-only generation (prompt generation)
_RUNNER_SCRIPT = """\
import subprocess, sys, os
prompt = open('/tmp/xolvien_prompt.txt', encoding='utf-8').read()
env = {**os.environ, 'HOME': '/root'}
proc = subprocess.Popen(
    ['claude', '-p', prompt, '--output-format', 'text'],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    env=env,
)
for chunk in iter(lambda: proc.stdout.read(512), b''):
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
proc.wait()
sys.exit(proc.returncode)
"""

# Python script for agent mode execution (file read/write/bash tools enabled)
# Drops privileges to non-root xolvien user so --dangerously-skip-permissions is allowed
_RUNNER_SCRIPT_AGENT = """\
import subprocess, sys, os, shutil, pwd

prompt = open('/tmp/xolvien_prompt.txt', encoding='utf-8').read()

try:
    pw = pwd.getpwnam('xolvien')
    uid, gid, home = pw.pw_uid, pw.pw_gid, pw.pw_dir
except KeyError:
    uid = gid = None
    home = '/root'

if uid is not None:
    for d in ['.claude', '.ssh']:
        src, dst = f'/root/{d}', f'{home}/{d}'
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copytree(src, dst, symlinks=True)
            for dirpath, dirs, files in os.walk(dst):
                os.chown(dirpath, uid, gid)
                for f in files:
                    try:
                        os.chown(os.path.join(dirpath, f), uid, gid)
                    except Exception:
                        pass

    def drop_privs():
        os.setgid(gid)
        os.setuid(uid)

    cmd = ['claude', '--dangerously-skip-permissions', '-p', prompt]
    env = {**os.environ, 'HOME': home}
    preexec = drop_privs
else:
    cmd = ['claude', '-p', prompt, '--output-format', 'text']
    env = {**os.environ, 'HOME': '/root'}
    preexec = None

proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    env=env,
    cwd='/workspace/repo',
    preexec_fn=preexec,
)
for chunk in iter(lambda: proc.stdout.read(512), b''):
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
proc.wait()
sys.exit(proc.returncode)
"""


class ClaudeCodeService:
    """Service for executing Claude Code CLI in containers."""

    def __init__(self):
        """Initialize service."""
        self.docker_service = get_docker_service()

    def _write_text_to_container(self, container_id: str, path: str, text: str) -> None:
        """Write arbitrary text to a file inside the container via base64."""
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")
        cmd = (
            f"python3 -c \""
            f"import base64; "
            f"open('{path}', 'w', encoding='utf-8')"
            f".write(base64.b64decode('{b64}').decode('utf-8'))"
            f"\""
        )
        self.docker_service.execute_command(container_id, cmd, "/workspace")

    async def clarify_requirements(
        self,
        db: AsyncSession,
        task_id: int,
        instruction: str,
        history: list,
        lang: str = "ja",
    ) -> AsyncGenerator[str, None]:
        """
        Conduct a clarification Q&A session before prompt generation.
        Claude either asks questions or outputs PROMPT_READY\\n{prompt}.
        Uses -p mode (text only) — file reading is deferred to generate_prompt.
        """
        result = await db.execute(sa_select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("Task not found")
        if not task.container_id:
            raise ValueError("Task has no container")

        # Lightweight context: file list + README only
        _, file_list, _ = self.docker_service.execute_command(
            task.container_id,
            "find /workspace/repo -type f | grep -v '.git' 2>/dev/null || echo '(空)'",
            "/workspace",
        )
        _, readme, _ = self.docker_service.execute_command(
            task.container_id,
            "cat /workspace/repo/README.md 2>/dev/null || cat /workspace/repo/README 2>/dev/null || echo '(READMEなし)'",
            "/workspace/repo",
        )

        # Build conversation history text
        history_text = ""
        if history:
            for msg in history:
                if lang == "en":
                    role_label = "Claude" if msg["role"] == "assistant" else "User"
                else:
                    role_label = "Claude" if msg["role"] == "assistant" else "ユーザー"
                history_text += f"{role_label}: {msg['content']}\n\n"

        if lang == "en":
            clarify_prompt = f"""You are a requirements analyst. You receive user instructions and ask clarifying questions to generate the best possible code.

## Project Information

File list:
{file_list.strip()}

README:
{readme[:2000].strip()}

## User Instruction

{instruction}
"""
            if history_text:
                clarify_prompt += f"""
## Conversation History

{history_text.strip()}
"""
            clarify_prompt += """
## Your Role

This is the requirements clarification phase. Continue asking questions until the user clicks "Proceed".

Output 1–3 specific questions as a numbered list.
Prioritize clarifying the following:
- Programming language and framework to use (always ask if it cannot be determined from the file list)
- Features, constraints, and expected behavior
- If there is a UI, design and interaction flow
- Specifications the user should decide (not implementation details)

Never output "PROMPT_READY". Always respond with questions only.
No preamble or explanation — output the question list only.
"""
        else:
            clarify_prompt = f"""あなたは要件ヒアリング担当です。ユーザーの指示を受け取り、最適なコードを生成するために必要な不明点を質問します。

## プロジェクト情報

ファイル一覧:
{file_list.strip()}

README:
{readme[:2000].strip()}

## ユーザーの指示

{instruction}
"""
            if history_text:
                clarify_prompt += f"""
## これまでの会話

{history_text.strip()}
"""
            clarify_prompt += """
## あなたの役割

これは要件ヒアリングフェーズです。ユーザーが「次へ進む」を押すまで質問を続けてください。

番号付きリストで1〜3個の具体的な質問を出力してください。
以下の観点を優先的に確認してください：
- 使用するプログラミング言語・フレームワーク（ファイル一覧から判断できない場合は必ず聞く）
- 機能・制約・期待する動作
- UIがある場合はデザインや操作フロー
- ユーザーが決めるべき仕様（実装詳細ではなく）

「PROMPT_READY」は絶対に出力しないでください。必ず質問で応答してください。
説明や前置きは不要です。質問リストだけを出力してください。
"""

        self._write_text_to_container(task.container_id, "/tmp/xolvien_prompt.txt", clarify_prompt)
        self._write_text_to_container(task.container_id, "/tmp/xolvien_runner.py", _RUNNER_SCRIPT)

        async for chunk in self.docker_service.execute_command_stream(
            task.container_id,
            "python3 /tmp/xolvien_runner.py",
            "/workspace/repo",
        ):
            yield chunk

    async def generate_prompt(
        self,
        db: AsyncSession,
        task_id: int,
        instruction_content: str,
        feedback: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        Generate an optimized prompt from a brief user instruction.
        Streams the generated prompt text.
        """
        result = await db.execute(sa_select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("Task not found")
        if not task.container_id:
            raise ValueError("Task has no container")

        # Gather lightweight index context (file list, git log, README)
        _, file_list, _ = self.docker_service.execute_command(
            task.container_id,
            "find /workspace/repo -type f | grep -v '.git' 2>/dev/null || echo '(空)'",
            "/workspace",
        )
        _, git_log, _ = self.docker_service.execute_command(
            task.container_id,
            "git log --oneline -10 2>/dev/null || echo '(履歴なし)'",
            "/workspace/repo",
        )
        _, readme, _ = self.docker_service.execute_command(
            task.container_id,
            "cat /workspace/repo/README.md 2>/dev/null || cat /workspace/repo/README 2>/dev/null || echo '(READMEなし)'",
            "/workspace/repo",
        )

        # Get past instructions for this task
        past_result = await db.execute(
            sa_select(Instruction)
            .where(Instruction.task_id == task_id)
            .where(Instruction.status == InstructionStatus.COMPLETED)
            .order_by(Instruction.created_at.asc())
            .limit(5)
        )
        past_instructions = past_result.scalars().all()
        past_text = "\n".join(f"- {i.content}" for i in past_instructions) or "(なし)"

        # Build meta-prompt — file contents are NOT pre-embedded;
        # the agent reads relevant files itself based on the instruction
        meta_prompt = f"""あなたはプロンプトエンジニアです。ユーザーの簡潔な指示を、Claude Code CLIエージェントに渡す最適なプロンプトに変換してください。

## ワークスペース情報

作業ディレクトリ: /workspace/repo

ファイル一覧:
{file_list.strip()}

直近のgit履歴:
{git_log.strip()}

README:
{readme[:3000].strip()}

このタスクの過去の指示履歴:
{past_text}

## ユーザーの指示

{instruction_content}
"""
        if feedback:
            meta_prompt += f"""
## 前回生成したプロンプトへの指摘

{feedback}
"""
        meta_prompt += """
## 手順

1. まず上記のファイル一覧から、ユーザーの指示に関係するファイルを特定してください
2. 該当ファイルを読み込み、現在の実装を正確に把握してください
3. その上で、Claude Code CLIエージェントへ渡す最適なプロンプトを生成してください

## 出力ルール

生成するプロンプトには以下を含めてください：
- 対象ファイルの正確なパス（読み込んだ内容に基づく）
- 現状の実装を踏まえた具体的な変更内容
- 必要であれば動作確認の観点

注意: 実行エージェントはファイルの読み書きやコマンド実行を自動で行います。出力形式の指定は不要です。

プロンプト本文のみを出力してください。説明や前置きは不要です。
"""

        self._write_text_to_container(task.container_id, "/tmp/xolvien_prompt.txt", meta_prompt)
        self._write_text_to_container(task.container_id, "/tmp/xolvien_runner.py", _RUNNER_SCRIPT_AGENT)

        async for chunk in self.docker_service.execute_command_stream(
            task.container_id,
            "python3 /tmp/xolvien_runner.py",
            "/workspace/repo",
        ):
            yield chunk

    async def execute_instruction(
        self,
        db: AsyncSession,
        task_id: int,
        instruction_content: str,
    ) -> AsyncGenerator[str, None]:
        """
        Execute instruction via Claude Code CLI agent mode inside the task container.
        Claude has full tool access (file read/write/bash) via --dangerously-skip-permissions.
        """
        result = await db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()

        if not task:
            raise ValueError("Task not found")
        if not task.container_id:
            raise ValueError("Task has no container")
        if task.status not in [TaskStatus.IDLE, TaskStatus.RUNNING]:
            raise ValueError(f"Task is not ready (status: {task.status})")

        # Create instruction record
        instruction = Instruction(
            task_id=task_id,
            content=instruction_content,
            status=InstructionStatus.PENDING,
        )
        db.add(instruction)
        await db.commit()
        await db.refresh(instruction)

        output_buffer = []

        async def save_log(message: str):
            log = TaskLog(
                task_id=task_id,
                level=LogLevel.INFO,
                source=LogSource.CLAUDE,
                message=message,
                instruction_id=instruction.id,
            )
            db.add(log)
            await db.commit()

        try:
            task.status = TaskStatus.RUNNING
            instruction.status = InstructionStatus.RUNNING
            instruction.started_at = datetime.utcnow()
            await db.commit()

            yield f"[SYSTEM] 指示を受け付けました\n"
            yield f"[SYSTEM] {instruction_content}\n\n"

            # Write prompt and agent runner script into the container
            self._write_text_to_container(task.container_id, "/tmp/xolvien_prompt.txt", instruction_content)
            self._write_text_to_container(task.container_id, "/tmp/xolvien_runner.py", _RUNNER_SCRIPT_AGENT)

            yield "[Claude] Claude Code CLIを実行しています...\n\n"

            full_response = ""
            async for chunk in self.docker_service.execute_command_stream(
                task.container_id,
                "python3 /tmp/xolvien_runner.py",
                "/workspace/repo",
            ):
                yield chunk
                full_response += chunk
                output_buffer.append(chunk)
                if len(output_buffer) >= 50:
                    await save_log("".join(output_buffer))
                    output_buffer = []

            if output_buffer:
                await save_log("".join(output_buffer))
                output_buffer = []

            # Auto-commit changes
            yield "\n[GIT] 変更をコミットしています...\n"
            commit_msg = instruction_content.replace("\n", " ")[:72]
            # Write commit message to temp file to avoid shell escaping issues
            self._write_text_to_container(
                task.container_id, "/tmp/xolvien_commit_msg.txt", commit_msg
            )
            commit_cmd = (
                "git add -A && "
                "git diff --cached --quiet && echo '[GIT] 変更なし（コミットスキップ）' || "
                "git commit -F /tmp/xolvien_commit_msg.txt"
            )
            _, commit_out, _ = self.docker_service.execute_command(
                task.container_id, commit_cmd, "/workspace/repo"
            )
            if commit_out.strip():
                yield f"{commit_out.strip()}\n"
                log = TaskLog(
                    task_id=task_id,
                    level=LogLevel.INFO,
                    source=LogSource.GIT,
                    message=commit_out.strip(),
                    instruction_id=instruction.id,
                )
                db.add(log)

            instruction.status = InstructionStatus.COMPLETED
            instruction.completed_at = datetime.utcnow()
            instruction.output = full_response
            instruction.exit_code = 0
            task.status = TaskStatus.IDLE
            await db.commit()

            yield "\n[SYSTEM] 完了しました\n"

        except Exception as e:
            error_msg = str(e)
            instruction.status = InstructionStatus.FAILED
            instruction.completed_at = datetime.utcnow()
            instruction.error_message = error_msg
            instruction.exit_code = 1
            task.status = TaskStatus.IDLE
            await db.commit()

            log = TaskLog(
                task_id=task_id,
                level=LogLevel.ERROR,
                source=LogSource.CLAUDE,
                message=f"Instruction failed: {error_msg}",
                instruction_id=instruction.id,
            )
            db.add(log)
            await db.commit()

            yield f"\n[ERROR] {error_msg}\n"


    async def generate_test_cases(
        self,
        db: AsyncSession,
        task_id: int,
        implementation_prompt: str,
        test_type: TestType = TestType.UNIT,
    ) -> AsyncGenerator[str, None]:
        """
        Generate structured test cases (JSON) from an implementation prompt.
        Saves results to test_case_items table, streams progress to caller.
        Supports both UNIT and INTEGRATION test types.
        """
        result = await db.execute(sa_select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("Task not found")
        if not task.container_id:
            raise ValueError("Task has no container")

        is_integration = test_type == TestType.INTEGRATION
        is_e2e = test_type == TestType.E2E
        if is_e2e:
            tag = "[E2E]"
        elif is_integration:
            tag = "[ITEST]"
        else:
            tag = "[TEST]"

        _, file_list, _ = self.docker_service.execute_command(
            task.container_id,
            "find /workspace/repo -type f | grep -v '.git' | grep -v '__pycache__' | grep -v 'node_modules' 2>/dev/null || echo '(空)'",
            "/workspace",
        )

        if is_e2e:
            prompt = f"""あなたはE2Eテスト設計の専門家です。以下の実装プロンプトとプロジェクトのファイル一覧を参考にして、Playwright E2Eテストケース一覧を生成してください。

## E2Eテストとは何か（重要）

**E2Eテストはブラウザを通じたユーザーシナリオのテストです。** 以下の特徴を守ってください：

- 単体テスト: 個別の関数・コンポーネント単体の動作
- 結合テスト: HTTP APIレベルのリクエスト/レスポンスと複数コンポーネントの連携
- **E2Eテスト: ブラウザを起動し、実際のUIを操作するシナリオテスト**
  - ページを開く → UI要素を操作（クリック、入力）→ 画面に表示される結果を確認
  - ユーザー登録・ログイン・ログアウトのフロー全体
  - フォーム送信 → 画面遷移 → 成功/エラーメッセージの確認
  - 一覧表示 → 詳細ページ遷移 → 編集・削除などのCRUDフロー

## 実装予定の内容
{implementation_prompt}

## プロジェクトのファイル一覧
{file_list.strip()}

## 出力形式（必ずこの形式のみを出力すること）

```json
[
  {{
    "seq_no": 1,
    "target_screen": "対象画面またはシナリオ名（例: ログインページ、商品一覧→詳細遷移）",
    "test_item": "テスト項目の名称",
    "operation": "ブラウザでの具体的な操作手順（例: http://localhost:3000/login を開き、メールに \\"test@example.com\\" を入力し、パスワードに \\"password123\\" を入力してログインボタンをクリックする）",
    "expected_output": "期待されるUI上の結果（例: ダッシュボードページに遷移し、\\"ようこそ test@example.com\\" と表示される）",
    "function_name": "test_e2e001_短い説明（英数字とアンダースコアのみ）"
  }}
]
```

## 注意事項
- **必ずブラウザUI操作レベルのテストを設計すること**（APIの直接呼び出しはE2Eテストではない）
- **具体的なURL、入力値、クリック対象、表示内容を記述すること**
- 主要なユーザーシナリオを中心に **8〜12件程度**
- function_name は `test_e2e{{seq_no:03d}}_` で始まる英数字・アンダースコアのみの関数名にすること
- JSON以外のテキスト（説明文・Markdownの見出し等）は出力しないこと
- テストコードは生成しないこと（テストケース定義のみ）
"""
        elif is_integration:
            prompt = f"""あなたは結合テスト設計の専門家です。以下の実装プロンプトとプロジェクトのファイル一覧を参考にして、結合テストケース一覧を生成してください。

## 結合テストとは何か（重要）

**結合テストは単体テストではありません。** 以下の違いを必ず守ってください：

- 単体テスト: 個別の関数・コンポーネントの動作（例: フォームのバリデーション、localStorageへの書き込み）
- **結合テスト: 複数コンポーネント・レイヤーが連携して動作すること**
  - フロントエンド → APIサーバー → DB の一連のフロー
  - HTTP リクエスト → レスポンス → DB の状態変化
  - 認証フロー（ログイン → トークン取得 → 認証が必要なAPIの呼び出し）
  - 複数APIを組み合わせた業務フロー（作成 → 更新 → 削除 → 一覧取得）

## 実装予定の内容
{implementation_prompt}

## プロジェクトのファイル一覧
{file_list.strip()}

## 出力形式（必ずこの形式のみを出力すること）

```json
[
  {{
    "seq_no": 1,
    "target_screen": "対象APIエンドポイントまたはフロー名（例: POST /api/users、ログインフロー）",
    "test_item": "テスト項目の名称",
    "operation": "具体的なHTTPリクエストの内容（例: POST /api/users に Authorization: Bearer token、Body: {{\\"name\\": \\"Alice\\", \\"email\\": \\"alice@example.com\\"}} を送信する）",
    "expected_output": "期待されるHTTPレスポンスとDB状態（例: ステータス201、レスポンスBody: {{\\"id\\": 1, \\"name\\": \\"Alice\\"}}、DBのusersテーブルにレコードが1件追加されている）",
    "function_name": "test_itc001_短い説明（英数字とアンダースコアのみ）"
  }}
]
```

## 注意事項
- **必ずHTTPリクエスト/レスポンスレベルのテストを設計すること**（DOMやlocalStorageのテストは結合テストではない）
- **実際のAPIエンドポイントのURL、HTTPメソッド、リクエストボディ、レスポンスステータスを具体的に記述すること**
- 正常系・異常系・業務フロー連携を中心に **10〜15件程度**（多すぎない）
- function_name は `test_itc{{seq_no:03d}}_` で始まる英数字・アンダースコアのみの関数名にすること
- JSON以外のテキスト（説明文・Markdownの見出し等）は出力しないこと
- テストコードは生成しないこと（テストケース定義のみ）
"""
        else:
            prompt = f"""あなたはテスト設計の専門家です。以下の実装プロンプトとプロジェクトのファイル一覧を参考にして、単体テストのテストケース一覧を生成してください。

## 実装予定の内容
{implementation_prompt}

## プロジェクトのファイル一覧
{file_list.strip()}

## 出力形式（必ずこの形式のみを出力すること）

```json
[
  {{
    "seq_no": 1,
    "target_screen": "対象画面名（画面がない場合はモジュール名）",
    "test_item": "テスト項目の名称",
    "operation": "具体的な入力値を含む操作手順（例: 入力欄に \\"sk-test-12345\\" を入力して送信ボタンを押す）",
    "expected_output": "期待される具体的な出力値（例: localStorage[\\"apiKey\\"] が \\"sk-test-12345\\" になっている）",
    "function_name": "test_tc001_短い説明（英数字とアンダースコアのみ）"
  }}
]
```

## 注意事項
- 正常系・異常系・境界値を網羅し、各テストケースに具体的な入力値と期待出力値を必ず記述すること
- function_name は `test_tc{{seq_no:03d}}_` で始まる英数字・アンダースコアのみの関数名にすること
- JSON以外のテキスト（説明文・Markdownの見出し等）は出力しないこと
- テストコードは生成しないこと（テストケース定義のみ）
"""

        self._write_text_to_container(task.container_id, "/tmp/xolvien_prompt.txt", prompt)
        self._write_text_to_container(task.container_id, "/tmp/xolvien_runner.py", _RUNNER_SCRIPT_AGENT)

        raw_output = ""
        async for chunk in self.docker_service.execute_command_stream(
            task.container_id,
            "python3 /tmp/xolvien_runner.py",
            "/workspace/repo",
        ):
            yield chunk
            raw_output += chunk

        # Parse JSON and save to test_case_items
        yield f"\n{tag} テストケースをDBに保存しています...\n"
        try:
            items = self._parse_test_cases_json(raw_output)
            if not items:
                yield f"{tag} ⚠️ テストケースのJSON解析に失敗しました。出力を確認してください。\n"
                return

            # Delete previous test_case_items of this test_type only (keep other types)
            existing = await db.execute(
                sa_select(TestCaseItem).where(
                    TestCaseItem.task_id == task_id,
                    TestCaseItem.test_type == test_type,
                )
            )
            for item in existing.scalars().all():
                await db.delete(item)
            await db.commit()

            for item_data in items:
                tc = TestCaseItem(
                    task_id=task_id,
                    test_type=test_type,
                    seq_no=item_data["seq_no"],
                    target_screen=item_data.get("target_screen"),
                    test_item=item_data["test_item"],
                    operation=item_data.get("operation"),
                    expected_output=item_data.get("expected_output"),
                    function_name=item_data.get("function_name"),
                )
                db.add(tc)
            await db.commit()
            yield f"{tag} ✅ {len(items)} 件のテストケースを保存しました\n"
        except Exception as e:
            yield f"{tag} ⚠️ テストケース保存エラー: {e}\n"

    def _parse_test_cases_json(self, raw: str) -> list[dict]:
        """Extract and parse the JSON array from Claude's output."""
        # Find the first '[' and last ']' to extract the JSON array
        start = raw.find('[')
        end = raw.rfind(']')
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return []

    def _detect_e2e_test_command(self, container_id: str) -> str | None:
        """Detect Playwright config and return the appropriate E2E test command."""
        _, config_check, _ = self.docker_service.execute_command(
            container_id,
            "ls /workspace/repo/playwright.config.js /workspace/repo/playwright.config.ts 2>/dev/null | head -1 || echo ''",
            "/workspace/repo",
        )
        if config_check.strip():
            return "npx playwright test --reporter=list 2>&1"

        # Python Playwright fallback
        _, py_playwright, _ = self.docker_service.execute_command(
            container_id,
            "python -c 'import playwright' 2>/dev/null && echo 'ok' || echo ''",
            "/workspace/repo",
        )
        if py_playwright.strip() == "ok":
            return "python -m pytest tests/e2e/ -v 2>&1"

        # No Playwright config yet — it will be created by the code generation step
        return "npx playwright test --reporter=list 2>&1"

    def _detect_test_command(self, container_id: str) -> str | None:
        """
        Detect the test command from the project structure.
        Returns the command string, or None if no test framework is found.
        package.json is checked first — Node.js projects may also have requirements.txt.
        """
        # Check Node.js first (package.json is unambiguous)
        _, pkg_json, _ = self.docker_service.execute_command(
            container_id,
            "cat /workspace/repo/package.json 2>/dev/null || echo ''",
            "/workspace/repo",
        )
        if pkg_json.strip():
            return "npm test -- --watchAll=false --verbose 2>&1"

        # Check for Python test frameworks
        _, pyproject, _ = self.docker_service.execute_command(
            container_id,
            "cat /workspace/repo/pyproject.toml 2>/dev/null || echo ''",
            "/workspace/repo",
        )
        _, setup_py, _ = self.docker_service.execute_command(
            container_id,
            "test -f /workspace/repo/setup.py && echo 'exists' || echo ''",
            "/workspace/repo",
        )
        _, req_files, _ = self.docker_service.execute_command(
            container_id,
            "ls /workspace/repo/requirements*.txt 2>/dev/null || echo ''",
            "/workspace/repo",
        )

        is_python = (
            'pytest' in pyproject
            or 'unittest' in pyproject
            or setup_py.strip() == 'exists'
            or req_files.strip() != ''
        )

        if is_python:
            # Verify pytest is actually installed
            _, pytest_check, _ = self.docker_service.execute_command(
                container_id,
                "python -m pytest --version 2>/dev/null && echo 'ok' || echo 'missing'",
                "/workspace/repo",
            )
            if 'missing' in pytest_check:
                return None  # pytest not installed — caller should install first
            return "python -m pytest -v 2>&1"

        return None

    async def run_unit_tests(
        self,
        db: AsyncSession,
        task_id: int,
        implementation_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Generate unit test code, run tests, auto-fix up to 3 times."""
        async for chunk in self._run_tests(db, task_id, implementation_prompt, TestType.UNIT):
            yield chunk

    async def run_integration_tests(
        self,
        db: AsyncSession,
        task_id: int,
        implementation_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Generate integration test code, start server/DB, run tests, auto-fix up to 3 times."""
        async for chunk in self._run_tests(db, task_id, implementation_prompt, TestType.INTEGRATION):
            yield chunk

    async def run_e2e_tests(
        self,
        db: AsyncSession,
        task_id: int,
        implementation_prompt: str,
    ) -> AsyncGenerator[str, None]:
        """Generate Playwright E2E test code, run tests with screenshots, auto-fix up to 3 times."""
        async for chunk in self._run_tests(db, task_id, implementation_prompt, TestType.E2E):
            yield chunk

    async def _run_tests(
        self,
        db: AsyncSession,
        task_id: int,
        implementation_prompt: str,
        test_type: TestType,
    ) -> AsyncGenerator[str, None]:
        """
        Shared implementation for unit, integration, and E2E tests.
        Generates test code, executes tests, auto-fixes up to 3 times.
        Saves TestRun and TestCaseResult records. Streams progress logs.
        """
        is_integration = test_type == TestType.INTEGRATION
        is_e2e = test_type == TestType.E2E
        if is_e2e:
            tag = "[E2E]"
            report_suffix = "e2e"
            report_title = "E2Eテスト"
            commit_prefix = "test(e2e)"
        elif is_integration:
            tag = "[ITEST]"
            report_suffix = "integration"
            report_title = "結合テスト"
            commit_prefix = "test(integration)"
        else:
            tag = "[TEST]"
            report_suffix = "unit"
            report_title = "単体テスト"
            commit_prefix = "test"

        result = await db.execute(sa_select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if not task:
            raise ValueError("Task not found")
        if not task.container_id:
            raise ValueError("Task has no container")

        # Load approved test case items from DB (filtered by test_type)
        tc_result = await db.execute(
            sa_select(TestCaseItem).where(
                TestCaseItem.task_id == task_id,
                TestCaseItem.test_type == test_type,
            ).order_by(TestCaseItem.seq_no)
        )
        tc_items = tc_result.scalars().all()
        if not tc_items:
            yield f"{tag} ⚠️ テストケースが登録されていません。先にテストケースを生成・承認してください。\n"
            return

        task.status = TaskStatus.TESTING
        await db.commit()

        test_run = TestRun(
            task_id=task_id,
            test_type=test_type,
            started_at=datetime.utcnow(),
        )
        db.add(test_run)
        await db.commit()
        await db.refresh(test_run)

        yield f"{tag} テストコードを生成しています...\n"

        tc_summary_lines = []
        for tc in tc_items:
            tc_summary_lines.append(
                f"- {tc.tc_id} | {tc.test_item} | 操作: {tc.operation} | 期待出力: {tc.expected_output} | function: {tc.function_name}"
            )
        tc_summary = "\n".join(tc_summary_lines)

        _, file_list, _ = self.docker_service.execute_command(
            task.container_id,
            "find /workspace/repo -type f | grep -v '.git' | grep -v '__pycache__' | grep -v 'node_modules' 2>/dev/null",
            "/workspace",
        )

        if is_e2e:
            tc_id_example = "E2E-001"
            tc_func_example = "test_e2e001_xxx"
        elif is_integration:
            tc_id_example = "ITC-001"
            tc_func_example = "test_itc001_xxx"
        else:
            tc_id_example = "TC-001"
            tc_func_example = "test_tc001_xxx"
        xolvien_result_instruction = f"""
   **重要: 各テストケースは必ず以下のパターンで実際の出力値を `console.log` で出力すること**

   Jest（Node.js）の場合の例:
   ```javascript
   test('{tc_id_example}: テスト名', () => {{
     const actual = /* 実際の値 */;
     console.log('XOLVIEN_RESULT:' + JSON.stringify({{tc_id: '{tc_id_example}', actual: String(actual)}}));
     expect(actual).toBe(/* 期待値 */);
   }});
   ```

   pytest（Python）の場合の例:
   ```python
   import json
   def {tc_func_example}():
       actual = /* 実際の値 */
       print('XOLVIEN_RESULT:' + json.dumps({{'tc_id': '{tc_id_example}', 'actual': str(actual)}}))
       assert actual == /* 期待値 */
   ```"""

        if is_e2e:
            gen_prompt = f"""あなたはPlaywrightを使ったE2Eテストコード生成の専門家です。以下の手順をすべて実行してください。

## 実装内容
{implementation_prompt}

## 承認済みテストケース一覧
各テストケースの function_name で関数を生成し、操作と期待出力に基づいてテストコードを書いてください。

{tc_summary}

## プロジェクトのファイル一覧
{file_list.strip()}

## 実行手順（順番通りに行うこと）

1. `package.json` や `pyproject.toml`、`requirements*.txt` を読み込み、アプリの起動方法を特定してください
2. **@playwright/test をインストールしてください**
   - Node.js の場合: `npm install --save-dev @playwright/test && npx playwright install chromium`
   - Python の場合: `pip install pytest-playwright && playwright install chromium`
3. **`playwright.config.js` を作成してください（Node.js の場合）**
   ```javascript
   // playwright.config.js
   const {{ defineConfig }} = require('@playwright/test');
   module.exports = defineConfig({{
     testDir: './e2e',
     use: {{ headless: true, baseURL: 'http://localhost:3000' }},
   }});
   ```
   ポート番号はアプリの実際の起動ポートに合わせること。
4. **アプリをバックグラウンドで起動してください**
   - Node.js の場合: `npm start &` または `npm run dev &` などでサーバーを起動し、`curl` でヘルスチェックすること
   - Python の場合: `uvicorn app:app &` や `flask run &` などで起動すること
5. **E2E テストファイルを `e2e/` ディレクトリに作成してください（Node.js の場合: `e2e/tests.spec.js`）**
   - `@playwright/test` の `test` / `expect` を使い、**Jest の `test()` は使わないこと**
   - 各テストケースの function_name に対応したテスト名を設定すること
   - 各テストの先頭で `console.log('XOLVIEN_RESULT:' + JSON.stringify({{tc_id: 'E2E-001', actual: 'actual value'}}))` を出力すること

   **Node.js Playwright の例:**
   ```javascript
   const {{ test, expect }} = require('@playwright/test');

   test('{tc_id_example}: テスト名', async ({{ page }}) => {{
     await page.goto('/');
     const text = await page.textContent('h1');
     console.log('XOLVIEN_RESULT:' + JSON.stringify({{tc_id: '{tc_id_example}', actual: String(text)}}));
     await page.screenshot({{ path: '/workspace/repo/test-reports/screenshots/{tc_id_example}.png' }});
     await expect(page.locator('h1')).toHaveText('期待するテキスト');
   }});
   ```

   - `XOLVIEN_RESULT:` の出力は `expect` より前に行うこと
   - スクリーンショットを各テスト終了前に `/workspace/repo/test-reports/screenshots/` に保存すること
   - Playwright はヘッドレスモード（`headless: true`）で実行すること
   - スクリーンショット保存ディレクトリは事前に `mkdir -p` で作成すること
6. テストを実行してください: `npx playwright test --reporter=line`
7. テスト終了後にバックグラウンドで起動したサーバーを停止すること

注意:
- function_name は変更しないこと（DBでの結果照合に使用する）
- 記録する `actual` は文字列に変換すること
- **Jest を使わないこと。`@playwright/test` の `test()` のみ使用すること**
- `testPathIgnorePatterns` など Jest の設定を変更しないこと
"""
        elif is_integration:
            gen_prompt = f"""あなたは結合テストコード生成の専門家です。以下の手順をすべて実行してください。

## 実装内容
{implementation_prompt}

## 承認済みテストケース一覧
各テストケースの function_name で関数を生成し、操作と期待出力に基づいてテストコードを書いてください。

{tc_summary}

## プロジェクトのファイル一覧
{file_list.strip()}

## 実行手順（順番通りに行うこと）

1. `package.json` や `pyproject.toml`、`requirements*.txt` を読み込み、テストフレームワークとアプリの起動方法を特定してください
2. 既存のテストファイルがあれば確認し、命名規則・構造に従ってください
3. **APIサーバーとDBをバックグラウンドで起動してから**テストを実行する準備をしてください
   - Node.js の場合: `npm start &` や `node server.js &` などでサーバーを起動し、起動待ちを行うこと
   - Python の場合: `uvicorn app:app &` や `flask run &` などでサーバーを起動すること
   - DB が必要な場合: テスト用DB接続文字列をセットアップすること
   - サーバーの起動確認: `curl` や `wget` でヘルスチェックエンドポイントに到達できることを確認すること
4. テストケース一覧の全ケースについて、指定された function_name で関数を生成してください
   - 実際の HTTP リクエスト（axios, requests, fetch, httpx 等）を使ってAPIを呼び出すこと
   - DBの状態確認が必要な場合は実際のDB接続を使うこと
{xolvien_result_instruction}
5. テストの実行に必要な依存パッケージをインストールしてください（supertest, axios, httpx, pytest-httpx 等）
6. テストを実行してください

注意:
- function_name は変更しないこと（DBでの結果照合に使用する）
- `XOLVIEN_RESULT:` の出力は `expect/assert` より前に行うこと
- 記録する `actual` は文字列に変換すること
- テスト終了後にバックグラウンドで起動したサーバーを停止すること
"""
        else:
            gen_prompt = f"""あなたはテストコード生成の専門家です。以下の手順をすべて実行してください。

## 実装内容
{implementation_prompt}

## 承認済みテストケース一覧
各テストケースの function_name で関数を生成し、操作と期待出力に基づいてテストコードを書いてください。

{tc_summary}

## プロジェクトのファイル一覧
{file_list.strip()}

## 実行手順（順番通りに行うこと）

1. `package.json` や `pyproject.toml`、`requirements*.txt` を読み込み、テストフレームワーク（Jest, pytest 等）を特定してください
2. 既存のテストファイルがあれば確認し、命名規則・構造に従ってください
3. テストケース一覧の全ケースについて、指定された function_name で関数を生成してください
{xolvien_result_instruction}
4. テストの実行に必要な依存パッケージをインストールしてください
5. テストを実行してください

注意:
- function_name は変更しないこと（DBでの結果照合に使用する）
- `XOLVIEN_RESULT:` プレフィックス付きの出力は `expect/assert` より前に行うこと（テスト失敗時も記録されるよう）
- 記録する `actual` は文字列に変換すること
"""

        self._write_text_to_container(task.container_id, "/tmp/xolvien_prompt.txt", gen_prompt)
        self._write_text_to_container(task.container_id, "/tmp/xolvien_runner.py", _RUNNER_SCRIPT_AGENT)

        async for chunk in self.docker_service.execute_command_stream(
            task.container_id,
            "python3 /tmp/xolvien_runner.py",
            "/workspace/repo",
        ):
            yield chunk

        if is_e2e:
            test_command = self._detect_e2e_test_command(task.container_id)
            # list reporter outputs ✓/✘ per test, compatible with existing verdict parsing
            if test_command and "playwright" in test_command:
                test_command = test_command.replace("--reporter=line", "--reporter=list")
        else:
            test_command = self._detect_test_command(task.container_id)
        if test_command is None:
            yield f"\n{tag} テストフレームワークが見つかりません。テストコードを確認してください。\n"
            test_run.passed = False
            test_run.exit_code = -1
            test_run.error_output = "No test framework detected"
            test_run.completed_at = datetime.utcnow()
            test_run.summary = "テストフレームワーク未検出"
            await db.commit()
            task.status = TaskStatus.IDLE
            await db.commit()
            return

        test_run.test_command = test_command
        await db.commit()

        yield f"\n{tag} テストを実行しています: {test_command}\n"

        max_retries = 3
        passed = False
        last_output = ""
        last_error = ""

        if is_e2e:
            results_file = "/tmp/xolvien_e2e_results.jsonl"
        elif is_integration:
            results_file = "/tmp/xolvien_itc_results.jsonl"
        else:
            results_file = "/tmp/xolvien_tc_results.jsonl"
        self.docker_service.execute_command(
            task.container_id,
            f"rm -f {results_file} && touch {results_file} && chmod 777 {results_file}",
            "/workspace/repo",
        )

        for attempt in range(max_retries + 1):
            if attempt > 0:
                yield f"\n{tag} 自動修正 ({attempt}/{max_retries})...\n"

                fix_prompt = f"""テストが失敗しました。原因を特定して修正してください。

## 実装内容
{implementation_prompt}

## テストケース一覧
{tc_summary}

## テストコマンド
{test_command}

## テスト実行の出力
{last_output[-3000:] if len(last_output) > 3000 else last_output}

## 標準エラー出力
{last_error[-1000:] if len(last_error) > 1000 else last_error}

## 指示
1. 失敗の原因を特定してください（テストコードの問題か、実装コードの問題か）
2. 原因を修正してください（function_name は変更しないこと）
3. 依存パッケージが不足している場合はインストールしてください
4. テストの再実行は不要です。修正のみ行ってください

## 絶対に行ってはいけないこと
- テストが通るようにするためだけに、実装コードの検証ロジックを削除・緩和すること
  （例: `try/catch` で例外を握り潰して成功扱いにする、常に `true` を返すフォールバックを追加する）
- `expect` / `assert` の条件を弱める・削除すること
- クリップボード・通知・外部API 等の環境依存で失敗する場合は、
  Playwright の `browserContext.grantPermissions()` や `page.route()` でモックして正しく検証すること
"""
                self._write_text_to_container(task.container_id, "/tmp/xolvien_prompt.txt", fix_prompt)
                self._write_text_to_container(task.container_id, "/tmp/xolvien_runner.py", _RUNNER_SCRIPT_AGENT)

                async for chunk in self.docker_service.execute_command_stream(
                    task.container_id,
                    "python3 /tmp/xolvien_runner.py",
                    "/workspace/repo",
                ):
                    yield chunk

                yield f"\n{tag} テストを再実行しています...\n"

            exit_code, output, error = self.docker_service.execute_command(
                task.container_id,
                test_command,
                "/workspace/repo",
            )
            last_output = output
            last_error = error

            combined = (output + "\n" + error).strip()
            if combined:
                yield combined + "\n"

            passed = exit_code == 0
            test_run.retry_count = attempt
            test_run.exit_code = exit_code
            test_run.passed = passed
            test_run.output = output
            test_run.error_output = error

            if passed:
                yield f"\n{tag} ✅ テストがパスしました\n"
                break
            else:
                combined_out = output + "\n" + error
                infra_error_patterns = [
                    "EACCES", "EPERM", "ENOENT", "ENOSPC",
                    "permission denied", "Permission denied",
                    "Cannot find module", "command not found",
                ]
                infra_error = next(
                    (p for p in infra_error_patterns if p in combined_out), None
                )
                if infra_error:
                    yield f"\n{tag} ⛔ インフラエラーを検出しました（{infra_error}）。自動修正をスキップします。\n"
                    yield f"{tag} テストコードまたは環境設定を確認してください。\n"
                    break

                if attempt < max_retries:
                    yield f"\n{tag} ❌ テストが失敗しました (試行 {attempt + 1}/{max_retries + 1})\n"
                else:
                    yield f"\n{tag} 最大リトライ回数 ({max_retries}) に達しました。手動対応が必要です。\n"

        # Parse XOLVIEN_RESULT: lines from stdout
        actual_by_tc_id: dict[str, str] = {}
        for line in (last_output + "\n" + last_error).splitlines():
            if "XOLVIEN_RESULT:" not in line:
                continue
            try:
                json_part = line[line.index("XOLVIEN_RESULT:") + len("XOLVIEN_RESULT:"):]
                row = json.loads(json_part)
                if "tc_id" in row and "actual" in row:
                    actual_by_tc_id[row["tc_id"]] = str(row["actual"])
            except (ValueError, json.JSONDecodeError):
                pass
        if not actual_by_tc_id:
            _, jsonl_content, _ = self.docker_service.execute_command(
                task.container_id,
                f"cat {results_file} 2>/dev/null || echo ''",
                "/workspace/repo",
            )
            for line in jsonl_content.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    if "tc_id" in row and "actual" in row:
                        actual_by_tc_id[row["tc_id"]] = str(row["actual"])
                except json.JSONDecodeError:
                    pass

        # Save TestCaseResults
        last_combined = (last_output + "\n" + last_error).strip()
        executed_at = datetime.utcnow()
        final_exit_code = test_run.exit_code or 0
        for tc in tc_items:
            verdict, actual_fallback = self._extract_result_for_function(last_combined, tc.function_name, tc.tc_id)
            actual = actual_by_tc_id.get(tc.tc_id) or actual_fallback
            # If output-format parsing missed this test but XOLVIEN_RESULT: was emitted,
            # the test ran — infer verdict from the overall exit code as a last resort.
            # A test whose result line was not found is still FAILED (not 未判定).
            if verdict is None and tc.tc_id in actual_by_tc_id:
                verdict = Verdict.PASSED if final_exit_code == 0 else Verdict.FAILED
            elif verdict is None:
                verdict = Verdict.FAILED
            tcr = TestCaseResult(
                test_case_item_id=tc.id,
                test_run_id=test_run.id,
                actual_output=actual,
                verdict=verdict,
                executed_at=executed_at,
            )
            db.add(tcr)
        await db.commit()
        yield f"{tag} テスト結果を {len(tc_items)} 件保存しました\n"

        # Compute summary from TestCaseResult verdicts (TC件数ベース)
        tc_results_q = await db.execute(
            sa_select(TestCaseResult).where(TestCaseResult.test_run_id == test_run.id)
        )
        tc_results_all = tc_results_q.scalars().all()
        n_passed = sum(1 for r in tc_results_all if r.verdict == Verdict.PASSED)
        n_failed = sum(1 for r in tc_results_all if r.verdict in (Verdict.FAILED, Verdict.ERROR))
        n_skipped = sum(1 for r in tc_results_all if r.verdict == Verdict.SKIPPED)
        n_unknown = sum(1 for r in tc_results_all if r.verdict is None)
        parts = [f"{n_passed} passed", f"{n_failed} failed"]
        if n_skipped:
            parts.append(f"{n_skipped} skipped")
        if n_unknown:
            parts.append(f"{n_unknown} 未判定")
        summary = ", ".join(parts)
        test_run.summary = summary

        now_str = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        executed_at_str = executed_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        report_filename = f"test-report-{now_str}-{report_suffix}.md"
        report_path = f"/workspace/repo/test-reports/{report_filename}"

        tc_result2 = await db.execute(
            sa_select(TestCaseItem).where(
                TestCaseItem.task_id == task_id,
                TestCaseItem.test_type == test_type,
            ).order_by(TestCaseItem.seq_no)
        )
        tc_items2 = tc_result2.scalars().all()
        report_rows = ["| TC-ID | テスト項目 | 期待出力 | 実際の出力 | 判定 | 実行日時 |",
                       "|---|---|---|---|---|---|"]
        verdict_icon = {Verdict.PASSED: "✅", Verdict.FAILED: "❌", Verdict.ERROR: "⚠️", Verdict.SKIPPED: "⏭️"}
        for tc in tc_items2:
            r_res = await db.execute(
                sa_select(TestCaseResult)
                .where(TestCaseResult.test_case_item_id == tc.id)
                .where(TestCaseResult.test_run_id == test_run.id)
            )
            r = r_res.scalar_one_or_none()
            icon = verdict_icon.get(r.verdict, "—") if r and r.verdict else "—"
            verdict_str = r.verdict.value if r and r.verdict else "未実行"
            actual = (r.actual_output or "—") if r else "—"
            report_rows.append(
                f"| {tc.tc_id} | {tc.test_item} | {tc.expected_output or '—'} | {actual} | {icon} {verdict_str} | {executed_at_str} |"
            )
        results_table_md = "\n".join(report_rows)

        report_content = f"""# テストレポート（{report_title}）

| 項目 | 値 |
|---|---|
| 実行日時 | {executed_at_str} |
| テストコマンド | `{test_command}` |
| 結果 | {"✅ PASS" if passed else "❌ FAIL"} |
| リトライ回数 | {test_run.retry_count} |
| サマリー | {summary} |

## テスト結果集計表

{results_table_md}

## テスト実行ログ

```
{(last_output + chr(10) + last_error).strip()[-5000:]}
```
"""

        self.docker_service.execute_command(
            task.container_id,
            "mkdir -p /workspace/repo/test-reports",
            "/workspace/repo",
        )
        self._write_text_to_container(task.container_id, report_path, report_content)

        test_run.report_path = report_path
        test_run.completed_at = datetime.utcnow()
        await db.commit()

        commit_msg = f"{commit_prefix}: add {report_suffix} tests ({'pass' if passed else 'fail'})"
        self._write_text_to_container(task.container_id, "/tmp/xolvien_commit_msg.txt", commit_msg)
        _, commit_out, _ = self.docker_service.execute_command(
            task.container_id,
            "git add -A && git diff --cached --quiet && echo '[GIT] 変更なし' || git commit -F /tmp/xolvien_commit_msg.txt",
            "/workspace/repo",
        )
        if commit_out.strip():
            yield f"[GIT] {commit_out.strip()}\n"

        task.status = TaskStatus.IDLE
        await db.commit()

        yield f"\n{tag} レポートを保存しました: {report_path}\n"
        yield f"\n[SYSTEM] テスト完了: {summary}\n"

    def _extract_result_for_function(
        self, output: str, function_name: str | None, tc_id: str | None = None
    ) -> tuple[Verdict | None, str | None]:
        """
        Scan test output for a specific test and return (verdict, actual_output).

        Supports:
        - pytest verbose (-v): "tests/test_foo.py::test_tc001_xxx PASSED/FAILED"
          Failure detail block starts with "FAILED tests/...::function_name" in summary section;
          E-prefixed lines contain AssertionError details.
        - Jest (--verbose): "✓ TC-001: テスト名" (pass) / "✕ TC-001: テスト名" (fail)
          Failure detail block starts with "● TC-001: テスト名";
          "Expected:" / "Received:" lines contain assertion details.
        """
        import re as _re

        if not function_name and not tc_id:
            return None, None

        lines = output.splitlines()
        verdict: Verdict | None = None
        actual_lines: list[str] = []

        # ── Pass 1: determine verdict ────────────────────────────���────────────
        for line in lines:
            # pytest verbose: "path/test_foo.py::test_tc001_xxx PASSED  [ n%]"
            if function_name and function_name in line:
                if "PASSED" in line:
                    verdict = Verdict.PASSED
                elif "FAILED" in line:
                    verdict = Verdict.FAILED
                elif "ERROR" in line:
                    verdict = Verdict.ERROR
                elif "SKIPPED" in line:
                    verdict = Verdict.SKIPPED

            # Jest --verbose: "  ✓ TC-001: テスト名 (n ms)"  or "  ✕ TC-001: テスト名"
            if tc_id and (tc_id + ":") in line:
                if _re.search(r'[✓√]', line):
                    verdict = Verdict.PASSED
                elif _re.search(r'[✕×✗]', line):
                    verdict = Verdict.FAILED
                elif 'skip' in line.lower() or 'todo' in line.lower():
                    verdict = Verdict.SKIPPED

            # Playwright --reporter=list: "  ✓  N function_name (Xs)" or "  ✘  N function_name"
            if function_name and function_name in line:
                if _re.search(r'[✓√✔]', line):
                    verdict = Verdict.PASSED
                elif _re.search(r'[✘✗✕×]', line):
                    verdict = Verdict.FAILED

        if verdict is None:
            return None, None

        if verdict == Verdict.PASSED:
            # For passed tests, actual output = expected output (test confirmed it matches)
            return verdict, None

        # ── Pass 2: collect failure details ──────────────────────────────────
        in_block = False

        # Jest failure block: starts with "  ● TC-001: テスト名", ends at next "  ●" or blank+indented line
        if tc_id:
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("●") and (tc_id + ":") in line:
                    in_block = True
                    continue
                if in_block:
                    # Next failure block or separator ends this block
                    if stripped.startswith("●") and (tc_id + ":") not in line:
                        break
                    if _re.match(r'^-{5,}$', stripped):
                        break
                    # Collect Expected/Received lines
                    if stripped.startswith("Expected:") or stripped.startswith("Received:"):
                        actual_lines.append(stripped)
                    # Also collect "Error:" type lines
                    elif stripped.startswith("Error:") or stripped.startswith("TypeError:"):
                        actual_lines.append(stripped)

        # pytest failure block: "E   AssertionError: ..." lines near function_name in short summary
        if function_name and not actual_lines:
            capture = False
            for line in lines:
                stripped = line.strip()
                if function_name in line and "FAILED" in line:
                    capture = True
                if capture and stripped.startswith("E "):
                    actual_lines.append(stripped[2:].strip())
                if capture and _re.match(r'^=+$', stripped):
                    break

        actual = "\n".join(actual_lines[:5]) if actual_lines else None
        return verdict, actual


# Singleton instance
from typing import Optional as Opt
_claude_service: Opt[ClaudeCodeService] = None


def get_claude_service() -> ClaudeCodeService:
    """Get or create Claude Code service instance."""
    global _claude_service
    if _claude_service is None:
        _claude_service = ClaudeCodeService()
    return _claude_service
