import streamlit as st

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


# AI整理結果を一時的に保存する場所
if "analysis_result" not in st.session_state:
    st.session_state.analysis_result = None


inquiry_text = st.text_area(
    "問い合わせ・依頼内容",
    placeholder="例：Excelを開くとマクロの警告が出ます。昨日までは使えていました。",
    height=180
)


if st.button("AIで整理"):
    if inquiry_text.strip():
        st.session_state.analysis_result = analyze_demo(inquiry_text)
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
        st.success("登録内容を確認しました。DB保存は次回実装します。")

        st.write("### 登録予定内容")
        st.write("**カテゴリ：**", category)
        st.write("**要約：**", summary)
        st.write("**優先度：**", priority)
        st.write("**不足情報：**", missing_info)
        st.write("**対応候補：**", suggested_action)