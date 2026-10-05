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
st.caption(f"Ver.1｜{mode_label}")

if ANALYSIS_MODE == "demo":
    st.info(
        "現在はデモモードです。実AI APIには接続しておらず、"
        "入力文に含まれるキーワードをもとに、あらかじめ用意したルールで整理例を表示します。"
        "整理結果は登録前に確認・修正できます。"
    )

st.warning(
    "公開デモのため、個人情報や機密情報は入力しないでください。"
    "登録内容は他の利用者にも表示されることがあり、データは初期状態に戻る場合があります。"
)


def make_summary(text, max_length=40):
    # 入力文の最初の行（空行は飛ばす）を、長ければ max_length 文字で切って要約にする
    for line in text.splitlines():
        line = line.strip()
        if line:
            if len(line) > max_length:
                return line[:max_length] + "…"
            return line
    return ""


def analyze_demo(text):
    summary = make_summary(text)

    # 大文字小文字を区別しないように、小文字にそろえてから判定する
    if "excel" in text.lower() or "エクセル" in text:
        # マクロに触れているときだけ、マクロ向けの整理例を返す
        if "マクロ" in text or "macro" in text.lower():
            return {
                "category": "Office / Excel",
                "summary": summary,
                "priority": "中",
                "missing_info": "Excelのバージョン、警告メッセージの内容、対象ファイル",
                "suggested_action": "マクロ設定や信頼済み場所、ファイルの取得元を確認する"
            }

        return {
            "category": "Office / Excel",
            "summary": summary,
            "priority": "中",
            "missing_info": "Excelのバージョン、発生時期、具体的な症状やエラーメッセージ、対象ファイル",
            "suggested_action": "特定のファイルだけで起きるかを確認し、原因を切り分ける"
        }

    return {
        "category": "その他",
        "summary": summary,
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


# DBが空のときに登録するポートフォリオ用サンプル（id と created_at は固定値）
# 並び：id, inquiry_text, category, summary, priority,
#       missing_info, suggested_action, status, created_at
SAMPLE_INQUIRIES = [
    (1, "パスワードをリセットしたい", "アカウント", "パスワードをリセットしたい", "高",
     "対象のアカウント（ユーザーID）、利用しているシステム名、本人確認の方法",
     "本人確認のうえ、パスワードリセットの手順を案内する",
     "完了", "2026-10-01T15:59:22+09:00"),
    (2, "VPNにつながらない", "ネットワーク / VPN", "VPNにつながらない", "高",
     "接続場所（自宅・外出先など）、表示されるエラーメッセージ、発生時期",
     "インターネット自体に接続できるか確認し、VPNクライアントの再起動と再接続を案内する",
     "対応中", "2026-10-02T09:41:51+09:00"),
    (3, "プリンターで印刷できない", "プリンター", "プリンターで印刷できない", "中",
     "プリンター名・設置場所、エラー表示の有無、他の人も印刷できないか",
     "プリンターの電源・用紙・エラー表示と、印刷待ちのジョブを確認する",
     "未対応", "2026-10-03T17:52:51+09:00"),
    (4, "Excelが重い", "Office / Excel", "Excelが重い", "中",
     "Excelのバージョン、発生時期、具体的な症状やエラーメッセージ、対象ファイル",
     "特定のファイルだけで起きるかを確認し、原因を切り分ける",
     "対応中", "2026-10-05T13:16:07+09:00"),
    (5, "Excelでマクロの警告が出る", "Office / Excel", "Excelでマクロの警告が出る", "中",
     "Excelのバージョン、警告メッセージの内容、対象ファイル",
     "マクロ設定や信頼済み場所、ファイルの取得元を確認する",
     "未対応", "2026-10-05T14:25:47+09:00"),
    (6, "Outlookでメールを送信できない", "メール / Outlook", "Outlookでメールを送信できない", "中",
     "表示されるエラーメッセージ、送信できない宛先、発生時期、受信はできるか",
     "ネットワーク接続とOutlookの送受信状態を確認し、再起動や再送信を試す",
     "完了", "2026-10-05T14:56:20+09:00"),
]


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


def seed_sample_data():
    # テーブルが空のときだけサンプルを登録する（1件でもあれば何もしない）
    with closing(sqlite3.connect(DB_PATH)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM inquiries").fetchone()[0]
        if count > 0:
            return 0

        # id を明示し OR IGNORE を付けて、同時に起動しても二重に登録されないようにする
        with conn:
            conn.executemany(
                """
                INSERT OR IGNORE INTO inquiries (
                    id, inquiry_text, category, summary, priority,
                    missing_info, suggested_action, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                SAMPLE_INQUIRIES
            )

    # 登録したサンプルの件数を返す
    return len(SAMPLE_INQUIRIES)


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


def format_datetime(value):
    # DBの値（例：2026-10-05T12:30:00+09:00）を表示用に「2026-10-05 12:30」へ変換する
    # 変換できない値のときは、そのまま表示する（DBの値は変更しない）
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return value


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
seed_sample_data()


# AI整理結果を一時的に保存する場所
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None

# 「AIで整理」を押した時点の問い合わせ文
if "original_text" not in st.session_state:
    st.session_state.original_text = ""

# ステータス変更後に表示するメッセージ（st.rerun() をまたいで残すため）
if "status_message" not in st.session_state:
    st.session_state.status_message = ""

# 登録成功後に表示するメッセージ（st.rerun() をまたいで残すため）
if "registration_message" not in st.session_state:
    st.session_state.registration_message = ""


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


# 前回の登録成功メッセージを1回だけ表示して消す
if st.session_state.registration_message:
    st.success(st.session_state.registration_message)
    st.session_state.registration_message = ""


# AI整理後だけHuman Review画面を表示
if st.session_state.analysis_result is not None:

    result = st.session_state.analysis_result

    st.subheader("AI整理結果（デモ）")
    st.caption("内容を確認し、必要に応じて修正してください。")

    # 「AIで整理」を押した時点の文章（登録されるのはこの文章）
    st.text_area(
        "対象の問い合わせ内容",
        value=st.session_state.original_text,
        disabled=True
    )

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

        # 整理結果を消して、同じフォームから二重登録できないようにする
        st.session_state.analysis_result = None
        st.session_state.registration_message = (
            f"登録しました（No.{inquiry_id}、ステータス：未対応）。"
            "登録内容は下の一覧で確認できます。"
        )
        # 最初から実行し直して、フォームを閉じ、一覧に新しい問い合わせを表示する
        st.rerun()


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
        "ステータスで絞り込み",
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
        st.write("**登録日時：**", format_datetime(inquiry["created_at"]))
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