import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import streamlit as st

# DBファイルは app.py と同じフォルダに置く
DB_PATH = Path(__file__).parent / "helpdesk.db"

# 日本時間（UTC+9）
JST = timezone(timedelta(hours=9))

# ステータスの選択肢（一覧の選択欄で使う）
STATUS_OPTIONS = ["未対応", "対応中", "完了"]

# 一覧の絞り込みで使う選択肢（先頭に「すべて」を付ける）
FILTER_OPTIONS = ["すべて"] + STATUS_OPTIONS

# AI整理のモード（今は "demo" のみ対応）
ANALYSIS_MODE = "demo"

st.set_page_config(
    page_title="AI問い合わせ・依頼対応",
    page_icon="🛠️"
)

st.title("AI問い合わせ・依頼対応")
mode_label = "デモモード" if ANALYSIS_MODE == "demo" else f"{ANALYSIS_MODE}モード"
st.caption(f"Ver.1 開発中｜{mode_label}")


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


def analyze_inquiry(text):
    # 画面からはこの関数だけを呼ぶ（モードに応じて分析関数を振り分ける）
    if ANALYSIS_MODE == "demo":
        return analyze_demo(text)

    # 将来：ここに実AIモード（analyze_real）を追加する
    raise ValueError(f"未対応の分析モードです：{ANALYSIS_MODE}")


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


def load_inquiries():
    # 登録済みの問い合わせを新しい順（id の大きい順）に全件読む
    with closing(sqlite3.connect(DB_PATH)) as conn:
        # row["status"] のように列名で値を取り出せるようにする
        conn.row_factory = sqlite3.Row
        rows = conn.execute("""
            SELECT id, inquiry_text, category, summary, priority,
                   missing_info, suggested_action, status, created_at
            FROM inquiries
            ORDER BY id DESC
        """).fetchall()

    # 1行ずつ普通の辞書に変換し、辞書のリストとして返す（0件なら []）
    return [dict(row) for row in rows]


def update_status(inquiry_id, new_status):
    # 指定した id の問い合わせだけ、ステータスを書き換える
    # WHERE id = ? を付けないと全件が書き換わるので注意
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            conn.execute(
                "UPDATE inquiries SET status = ? WHERE id = ?",
                (new_status, inquiry_id)
            )


def count_by_status(inquiries):
    # ステータスごとの件数を数える（最初は全部 0 件から始める）
    counts = {}
    for status in STATUS_OPTIONS:
        counts[status] = 0

    # 1件ずつ見て、そのステータスの件数を 1 増やす
    for inquiry in inquiries:
        status = inquiry["status"]
        if status in counts:
            counts[status] += 1

    # 例：{"未対応": 5, "対応中": 4, "完了": 3}
    return counts


def filter_inquiries(inquiries, status_filter, keyword):
    # 前後の空白を取り、大文字小文字を区別しないように小文字にそろえる
    keyword = (keyword or "").strip().lower()

    filtered = []
    for inquiry in inquiries:
        # ステータスの条件（「すべて」なら全件が対象）
        if status_filter != "すべて" and inquiry["status"] != status_filter:
            continue

        # キーワードの条件（空欄なら検索しない）
        if keyword:
            # None が入っていても or "" で空文字にしてからつなげる
            target = " ".join([
                inquiry["inquiry_text"] or "",
                inquiry["summary"] or "",
                inquiry["category"] or "",
            ]).lower()
            if keyword not in target:
                continue

        # ここまで来たら両方の条件に合っている
        filtered.append(inquiry)

    # 条件に合った問い合わせだけのリスト（0件なら []）
    return filtered


init_db()


# AI整理結果を一時的に保存する場所
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# 「AIで整理」を押した時点の問い合わせ文
if "original_text" not in st.session_state:
    st.session_state.original_text = ""

# ステータス変更後に表示するメッセージ（st.rerun() をまたいで残すため）
if "status_message" not in st.session_state:
    st.session_state.status_message = ""


inquiry_text = st.text_area(
    "問い合わせ・依頼内容",
    placeholder="例：Excelを開くとマクロの警告が出ます。昨日までは使えていました。",
    height=180
)


if st.button("AIで整理"):
    if inquiry_text.strip():
        try:
            st.session_state.analysis_result = analyze_inquiry(inquiry_text)
        except ValueError as e:
            st.error(f"AI整理に失敗しました：{e}")
            st.stop()
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


# ここから登録済み問い合わせ一覧（上の if の外なので、常に表示される）
st.divider()
st.subheader("登録済み問い合わせ一覧")

# 前回のステータス変更メッセージを1回だけ表示して消す
if st.session_state.status_message:
    st.success(st.session_state.status_message)
    st.session_state.status_message = ""

try:
    inquiries = load_inquiries()
except sqlite3.Error as e:
    # 読み込み失敗時はエラーだけを表示する（0件メッセージは出さない）
    st.error(f"一覧の読み込みに失敗しました：{e}")
    inquiries = []
else:
    # 読み込みに成功したときだけ、件数または0件メッセージを表示する
    if not inquiries:
        st.info("まだ登録された問い合わせはありません。")

# 一覧に表示する問い合わせ（1件もなければ空のまま）
filtered = []

if inquiries:
    # ステータス別件数（絞り込みに関係なく、常に全体の数を表示する）
    counts = count_by_status(inquiries)
    col_all, col_todo, col_doing, col_done = st.columns(4)
    col_all.metric("全件", len(inquiries))
    col_todo.metric("未対応", counts["未対応"])
    col_doing.metric("対応中", counts["対応中"])
    col_done.metric("完了", counts["完了"])

    # 絞り込み条件（key を付けると、st.rerun() 後も選択が残る）
    status_filter = st.radio(
        "ステータス",
        FILTER_OPTIONS,
        horizontal=True,
        key="filter_status"
    )
    keyword = st.text_input(
        "キーワード（問い合わせ内容・要約・カテゴリ）",
        key="search_keyword"
    )

    filtered = filter_inquiries(inquiries, status_filter, keyword)
    st.caption(f"表示中 {len(filtered)}件 / 全{len(inquiries)}件")

    if not filtered:
        st.info("条件に一致する問い合わせはありません。")

for inquiry in filtered:
    with st.expander(f"No.{inquiry['id']}｜[{inquiry['status']}]｜{inquiry['summary']}"):
        st.write("**登録日時：**", inquiry["created_at"])
        st.write("**カテゴリ：**", inquiry["category"])
        st.write("**優先度：**", inquiry["priority"])
        st.write("**問い合わせ内容：**", inquiry["inquiry_text"])
        st.write("**不足情報：**", inquiry["missing_info"])
        st.write("**対応候補：**", inquiry["suggested_action"])

        # key に id を入れて、問い合わせごとに別の選択欄として区別する
        new_status = st.selectbox(
            "ステータス",
            STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(inquiry["status"]),
            key=f"status_{inquiry['id']}"
        )

        # 選択がDBの値と同じ間はボタンを押せないようにする
        if st.button(
            "ステータスを保存",
            key=f"save_status_{inquiry['id']}",
            disabled=(new_status == inquiry["status"])
        ):
            try:
                update_status(inquiry["id"], new_status)
            except sqlite3.Error as e:
                st.error(f"ステータスの更新に失敗しました：{e}")
            else:
                st.session_state.status_message = (
                    f"No.{inquiry['id']} のステータスを「{new_status}」に変更しました"
                )
                # 最初から実行し直して、更新後のデータで一覧を表示する
                st.rerun()