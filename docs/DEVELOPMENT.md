# 開発ガイド - Mynion

## 開発環境セットアップ

### 1. VSCode拡張機能インストール

VSCodeで推奨拡張機能をインストール：

1. VSCodeを開く
2. コマンドパレット（`Cmd+Shift+P` / `Ctrl+Shift+P`）を開く
3. `Extensions: Show Recommended Extensions`を実行
4. 表示された拡張機能をすべてインストール

または手動でインストール：
- Python
- Pylance
- Ruff
- GitHub Copilot（推奨）

### 2. GitHub Copilot設定

このプロジェクトでは、`.github/copilot-instructions.md` にプロジェクト固有のCopilot設定が定義されています：

- **レビューは日本語で提供**されます
- プロジェクトのコーディング規約やベストプラクティスが自動的に適用されます
- コミットメッセージのフォーマット（Issue番号を含める等）がレビューされます

### 3. 開発依存関係の同期

```bash
uv sync
```

## コード品質ツール

### Pylance（リアルタイム型チェック）

**自動実行** - VSCodeでファイルを開くと自動的に動作

- 型エラーを赤線で表示
- 自動補完を強化
- 関数の戻り値型をインレイヒント表示

### Mypy（厳密な型チェック）

**手動実行:**

```bash
# プロジェクト全体をチェック
mypy .

# 特定のディレクトリのみ
mypy cdk/
mypy interfaces/

# 厳密モード
mypy --strict cdk/
```

### Ruff（Linter + Formatter）

**自動実行** - ファイル保存時に自動実行

**手動実行:**

```bash
# Lint（問題検出）
ruff check .

# 自動修正
ruff check --fix .

# フォーマット
ruff format .

# フォーマット確認（CI用）
ruff format --check .
```

## 開発ワークフロー

### コード作成時

1. **VSCodeでコードを書く**
   - Pylanceがリアルタイムで型エラーを表示
   - 保存時にRuffが自動フォーマット

2. **コミット前チェック**
   ```bash
   # 型チェック
   mypy .

   # コード品質チェック
   ruff check .

   # フォーマット確認
   ruff format --check .
   ```

3. **自動修正**
   ```bash
   ruff check --fix .
   ruff format .
   ```

### CI/CDでの使用

```bash
# 型チェック
mypy . || exit 1

# Lintチェック
ruff check . || exit 1

# フォーマットチェック
ruff format --check . || exit 1
```

## トラブルシューティング

### Pylanceが型を認識しない

```bash
# 型スタブを再インストール
uv add --dev types-boto3

# VSCode再起動
```

### Mypyエラーが多すぎる

`pyproject.toml`で厳密度を調整：

```toml
[tool.mypy]
disallow_untyped_defs = false  # true→falseに変更
```

### Ruffとの既存コードの衝突

一時的に特定ルールを無効化：

```python
# ruff: noqa: E501
def very_long_function_name_that_exceeds_line_limit():
    pass
```

## VSCode設定カスタマイズ

`.vscode/settings.json`を編集：

```json
{
  // より厳密な型チェック
  "python.analysis.typeCheckingMode": "strict",

  // 保存時フォーマットを無効化
  "editor.formatOnSave": false
}
```

## よく使うコマンド

```bash
# すべてのチェックを実行
mypy . && ruff check . && ruff format --check .

# すべてを自動修正
ruff check --fix . && ruff format .

# CDKのみチェック
mypy cdk/ && ruff check cdk/
```
