# 設計書: スレッド内の返信はメンションなしでも反応する

## 変更内容

### 1. Slackアプリの設定変更

#### Event Subscriptions設定

Slack App管理画面 → Event Subscriptions → Subscribe to bot events

**追加するイベント:**

| イベント | 説明 |
|---------|------|
| `message.channels` | パブリックチャンネルのメッセージを受信 |

**手順:**

1. [Slack API](https://api.slack.com/apps) にアクセス
2. Mynionアプリを選択
3. 左メニュー「Event Subscriptions」をクリック
4. 「Subscribe to bot events」セクションで「Add Bot User Event」をクリック
5. `message.channels`を選択して追加
6. 右上の「Save Changes」をクリック
7. **アプリを再インストール**（権限変更のため必要）

#### OAuth & Permissions設定

`message.channels`イベントを追加すると、以下のスコープが自動的に追加される:

| スコープ | 説明 |
|---------|------|
| `channels:history` | すでに設定済み |

### 2. コード変更

**変更不要**

現在の`receiver.py`の実装:

```python
def should_respond(slack_client, slack_event, bot_user_id) -> bool:
    # メンションがあれば反応
    if f"<@{bot_user_id}>" in text:
        return True

    # スレッド内の返信で、ボットが参加していれば反応
    if thread_ts and is_bot_in_thread(slack_client, channel, thread_ts, bot_user_id):
        return True

    return False
```

このロジックは正しく実装されている。

### 3. ローカルテスト環境

#### ユニットテストの追加

`tests/test_receiver.py`を作成し、以下をテスト:

1. `is_bot_in_thread()` - ボット参加判定
2. `should_respond()` - 応答判定ロジック

#### テストケース

| ケース | 入力 | 期待結果 |
|--------|------|----------|
| メンションあり | `<@BOT_ID> hello` | `True` |
| スレッド内、ボット参加済み | thread_ts あり、ボットメッセージあり | `True` |
| スレッド内、ボット未参加 | thread_ts あり、ボットメッセージなし | `False` |
| 通常メッセージ | thread_ts なし、メンションなし | `False` |
| ボット自身のメッセージ | user == bot_user_id | `False` |

## 影響範囲

### 変更されるコンポーネント

| コンポーネント | 変更内容 |
|---------------|----------|
| Slackアプリ設定 | `message.channels`イベント追加 |
| `tests/test_receiver.py` | 新規作成 |

### 変更されないコンポーネント

| コンポーネント | 理由 |
|---------------|------|
| `receiver.py` | ロジック実装済み |
| `worker/handler.py` | 変更不要 |
| CDKスタック | 変更不要 |

## リスク考慮

### APIレート制限

- `conversations.replies`を毎回呼ぶとレート制限に引っかかる可能性
- 現在の実装は最新5件のみ取得（パフォーマンス考慮済み）
- 将来的にはキャッシュ導入を検討

### イベント量の増加

- `message.channels`を購読すると、すべてのチャンネルメッセージがLambdaに届く
- `should_respond()`で早期リターンしているため、処理負荷は最小限
- Lambda実行時間・コストへの影響は軽微
