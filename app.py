import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

# DBファイルは app.py と同じフォルダに置く
DB_PATH = Path(__file__).parent / "helpdesk.db"

# 日本時間（UTC+9）
JST = timezone(timedelta(hours=9))

st.set_page_config(
    page_title="AI問い合わせ・依頼対応",
    page_icon="🛠️"
)

st.title("AI問い合わせ・依頼対応")
st.caption("Ver.1 開発中｜デモモード")


def analyze_demo(text):
    if "Excel" in text or "エクセル" in text:
        return {
            "category": "Office / Excel",
            "summary": "Excelでマクロの警告が表示される",
            "priority": "中",
            "missing_info": "Excelのバージョン、警告メッセージの内容、対象ファイル",
            "suggested_action": "マクロ設定や信頼済み場所、ファイルの取得元を確認する"
        }

    return {
        "category": "その他",
        "summary": text,
        "priority": "中",
        "missing_info": "発生時期、利用環境、具体的なエラーメッセージ",
        "suggested_action": "詳細情報を確認して原因を切り分ける"
    }


def init_db():
    # テーブルがなければ作る（あれば何もしない）
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS inquiries (
                    id               INTEGER PRIMARY KEY AUTOINCREMENT,
                    inquiry_text     TEXT NOT NULL,
                    category         TEXT,
                    summary          TEXT,
                    priority         TEXT,
                    missing_info     TEXT,
                    suggested_action TEXT,
                    status           TEXT NOT NULL DEFAULT '未対応',
                    created_at       TEXT NOT NULL
                )
            """)


def save_inquiry(inquiry_text, category, summary, priority, missing_info, suggested_action):
    # 例：2026-10-01T15:30:00+09:00（末尾の +09:00 が日本時間の印）
    created_at = datetime.now(JST).isoformat(timespec="seconds")

    # closing：使い終わったら接続を閉じる
    # with conn：成功したら保存を確定（commit）、失敗したら取り消す（rollback）
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO inquiries (
                    inquiry_text, category, summary, priority,
                    missing_info, suggested_action, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (inquiry_text, category, summary, priority,
                 missing_info, suggested_action, "未対応", created_at)
            )
        # 登録された行の id を返す
        return cursor.lastrowid


init_db()


# AI整理結果を一時的に保存する場所
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# 「AIで整理」を押した時点の問い合わせ文
if "original_text" not in st.session_state:
    st.session_state.original_text = ""


inquiry_text = st.text_area(
    "問い合わせ・依頼内容",
    placeholder="例：Excelを開くとマクロの警告が出ます。昨日までは使えていました。",
    height=180
)


if st.button("AIで整理"):
    if inquiry_text.strip():
        st.session_state.analysis_result = analyze_demo(inquiry_text)
        st.session_state.original_text = inquiry_text
    else:
        st.warning("問い合わせ・依頼内容を入力してください。")


# AI整理後だけHuman Review画面を表示
if st.session_state.analysis_result is not None:

    result = st.session_state.analysis_result

    st.subheader("AI整理結果")
    st.caption("内容を確認し、必要に応じて修正してください。")

    category = st.text_input(
        "カテゴリ",
        value=result["category"]
    )

    summary = st.text_input(
        "要約",
        value=result["summary"]
    )

    priority_options = ["低", "中", "高"]

    priority = st.selectbox(
        "優先度",
        priority_options,
        index=priority_options.index(result["priority"])
    )

    missing_info = st.text_area(
        "不足情報",
        value=result["missing_info"]
    )

    suggested_action = st.text_area(
        "対応候補",
        value=result["suggested_action"]
    )

    if st.button("この内容で登録"):
        try:
            inquiry_id = save_inquiry(
                st.session_state.original_text,
                category,
                summary,
                priority,
                missing_info,
                suggested_action
            )
        except sqlite3.Error as e:
            st.error(f"登録に失敗しました：{e}")
            st.stop()

        st.success(f"登録しました（No.{inquiry_id}、ステータス：未対応）")

        st.write("### 登録内容")
        st.write("**カテゴリ：**", category)
        st.write("**要約：**", summary)
        st.write("**優先度：**", priority)
        st.write("**不足情報：**", missing_info)
        st.write("**対応候補：**", suggested_action)