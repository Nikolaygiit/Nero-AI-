"""
Админ-панель (Streamlit): DAU/MAU, расход токенов, список пользователей
Запуск: streamlit run admin/app.py
"""
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd

DB_PATH = Path(__file__).parent.parent / "bot_database.db"
PAGE_TITLE = "Nero AI — Админ-панель"


def get_conn():
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


def load_daily_active(days: int = 30) -> pd.DataFrame:
    """DAU за последние N дней"""
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT date(created_at) as date, COUNT(DISTINCT user_id) as dau
        FROM messages
        WHERE created_at >= date('now', '-%d days')
        GROUP BY date(created_at)
        ORDER BY date
        """ % days,
        conn,
    )
    conn.close()
    return df


def load_token_usage() -> pd.DataFrame:
    """Расход токенов по дням"""
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT date(updated_at) as date, SUM(tokens_used) as tokens
        FROM stats
        WHERE updated_at >= date('now', '-30 days')
        GROUP BY date(updated_at)
        ORDER BY date
        """,
        conn,
    )
    conn.close()
    return df


def load_users(limit: int = 100) -> pd.DataFrame:
    """Список пользователей с базовой статистикой"""
    conn = get_conn()
    df = pd.read_sql_query(
        """
        SELECT u.telegram_id, u.first_name, u.username, u.created_at,
               COALESCE(s.requests_count, 0) as requests,
               COALESCE(s.tokens_used, 0) as tokens,
               COALESCE(s.images_generated, 0) as images
        FROM users u
        LEFT JOIN stats s ON s.user_id = u.telegram_id
        ORDER BY u.created_at DESC
        LIMIT ?
        """,
        conn,
        params=(limit,),
    )
    conn.close()
    return df


def main():
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.title(PAGE_TITLE)

    if not DB_PATH.exists():
        st.error("База данных не найдена. Запустите бота.")
        return

    # Метрики сверху
    conn = get_conn()
    total_users = pd.read_sql_query("SELECT COUNT(*) as c FROM users", conn).iloc[0]["c"]
    total_tokens = pd.read_sql_query("SELECT COALESCE(SUM(tokens_used), 0) as c FROM stats", conn).iloc[0]["c"]
    total_images = pd.read_sql_query("SELECT COALESCE(SUM(images_generated), 0) as c FROM stats", conn).iloc[0]["c"]
    conn.close()

    col1, col2, col3 = st.columns(3)
    col1.metric("Пользователей", total_users)
    col2.metric("Токенов израсходовано", f"{int(total_tokens):,}")
    col3.metric("Изображений", int(total_images))

    # DAU / MAU
    st.subheader("DAU (Daily Active Users)")
    dau_df = load_daily_active(30)
    if not dau_df.empty:
        st.line_chart(dau_df.set_index("date")["dau"])
    else:
        st.info("Нет данных")

    # Расход токенов
    st.subheader("Расход токенов по дням")
    tokens_df = load_token_usage()
    if not tokens_df.empty:
        st.bar_chart(tokens_df.set_index("date")["tokens"])
    else:
        st.info("Нет данных")

    # Список пользователей
    st.subheader("Пользователи")
    users_df = load_users(200)
    if not users_df.empty:
        st.dataframe(users_df, width="stretch", hide_index=True)
    else:
        st.info("Нет пользователей")


if __name__ == "__main__":
    main()
