"""
Админ-панель (Streamlit): DAU/MAU, расход токенов, список пользователей, Ban, Premium
Запуск: streamlit run admin/app.py
"""

import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).parent.parent / "bot_database.db"
PAGE_TITLE = "Nero AI — Админ-панель"


def get_conn():
    return sqlite3.connect(str(DB_PATH), check_same_thread=False)


def check_auth() -> bool:
    """Проверка доступа к админке"""
    try:
        from config import settings

        pwd = getattr(settings, "ADMIN_PANEL_PASSWORD", "") or os.getenv("ADMIN_PANEL_PASSWORD", "")
    except Exception:
        pwd = os.getenv("ADMIN_PANEL_PASSWORD", "")
    if not pwd:
        st.error(
            "Ошибка безопасности: Пароль администратора не установлен. Укажите ADMIN_PANEL_PASSWORD в переменных окружения."
        )
        st.stop()
        return False
    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False
    return st.session_state.admin_authenticated


def login_form():
    st.subheader("Вход в админ-панель")
    pwd_input = st.text_input("Пароль", type="password")
    if st.button("Войти"):
        try:
            from config import settings

            expected = getattr(settings, "ADMIN_PANEL_PASSWORD", "") or os.getenv(
                "ADMIN_PANEL_PASSWORD", ""
            )
        except Exception:
            expected = os.getenv("ADMIN_PANEL_PASSWORD", "")
        if pwd_input == expected:
            st.session_state.admin_authenticated = True
            st.rerun()
        else:
            st.error("Неверный пароль")


def load_daily_active(days: int = 30) -> pd.DataFrame:
    """DAU за последние N дней"""
    conn = get_conn()
    try:
        df = pd.read_sql_query(
            """
            SELECT date(created_at) as date, COUNT(DISTINCT user_id) as dau
            FROM messages
            WHERE created_at >= date('now', '-%d days')
            GROUP BY date(created_at)
            ORDER BY date
            """
            % days,
            conn,
        )
    except Exception:
        df = pd.DataFrame(columns=["date", "dau"])
    finally:
        conn.close()
    return df


def load_mau(days: int = 30) -> int:
    """MAU — уникальные пользователи за последние N дней"""
    conn = get_conn()
    try:
        row = pd.read_sql_query(
            """
            SELECT COUNT(DISTINCT user_id) as mau
            FROM messages
            WHERE created_at >= date('now', '-%d days')
            """
            % days,
            conn,
        )
        return int(row.iloc[0]["mau"]) if not row.empty else 0
    except Exception:
        return 0
    finally:
        conn.close()


def load_token_usage() -> pd.DataFrame:
    """Расход токенов по дням"""
    conn = get_conn()
    try:
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
    except Exception:
        df = pd.DataFrame(columns=["date", "tokens"])
    finally:
        conn.close()
    return df


def load_users(limit: int = 200) -> pd.DataFrame:
    """Список пользователей с базовой статистикой, is_banned, premium"""
    conn = get_conn()
    try:
        cols = "u.telegram_id, u.first_name, u.username, u.created_at"
        try:
            conn.execute("SELECT is_banned FROM users LIMIT 1")
            cols += ", COALESCE(u.is_banned, 0) as is_banned"
        except sqlite3.OperationalError:
            cols += ", 0 as is_banned"
        # subscriptions может отсутствовать в старых БД
        try:
            conn.execute("SELECT 1 FROM subscriptions LIMIT 1")
            join_sub = "LEFT JOIN subscriptions sub ON sub.user_id = u.telegram_id"
            cols += ", COALESCE(sub.tier, 'free') as tier"
        except sqlite3.OperationalError:
            join_sub = ""
            cols += ", 'free' as tier"
        df = pd.read_sql_query(
            f"""
            SELECT {cols},
                   COALESCE(s.requests_count, 0) as requests,
                   COALESCE(s.tokens_used, 0) as tokens,
                   COALESCE(s.images_generated, 0) as images
            FROM users u
            LEFT JOIN stats s ON s.user_id = u.telegram_id
            {join_sub}
            ORDER BY u.created_at DESC
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )
    except Exception:
        try:
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
        except Exception:
            df = pd.DataFrame()
    finally:
        conn.close()
    return df


def exec_ban(telegram_id: int, ban: bool) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET is_banned = ? WHERE telegram_id = ?",
            (1 if ban else 0, telegram_id),
        )
        conn.commit()
    except sqlite3.OperationalError:
        # колонка is_banned может отсутствовать
        pass
    finally:
        conn.close()


def exec_premium(telegram_id: int, give: bool) -> None:
    conn = get_conn()
    try:
        cur = conn.execute("SELECT 1 FROM subscriptions WHERE user_id = ?", (telegram_id,))
        exists = cur.fetchone() is not None
        if give:
            if exists:
                conn.execute(
                    "UPDATE subscriptions SET tier='premium', stars_paid_at=datetime('now'), updated_at=datetime('now') WHERE user_id=?",
                    (telegram_id,),
                )
            else:
                conn.execute(
                    "INSERT INTO subscriptions (user_id, tier, stars_paid_at, created_at, updated_at) "
                    "VALUES (?, 'premium', datetime('now'), datetime('now'), datetime('now'))",
                    (telegram_id,),
                )
        else:
            if exists:
                conn.execute(
                    "UPDATE subscriptions SET tier='free', stars_paid_at=NULL, updated_at=datetime('now') WHERE user_id=?",
                    (telegram_id,),
                )
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def main():
    st.set_page_config(page_title=PAGE_TITLE, layout="wide")
    st.title("🎛️ " + PAGE_TITLE)

    if not check_auth():
        login_form()
        return

    # Кнопка выхода
    if st.sidebar.button("Выйти"):
        st.session_state.admin_authenticated = False
        st.rerun()

    if not DB_PATH.exists():
        st.error("База данных не найдена. Запустите бота.")
        return

    tab_overview, tab_users, tab_personas = st.tabs(["📊 Обзор", "👥 Пользователи", "📝 Персонажи"])

    with tab_overview:
        conn = get_conn()
        try:
            total_users = pd.read_sql_query("SELECT COUNT(*) as c FROM users", conn).iloc[0]["c"]
            total_tokens = pd.read_sql_query(
                "SELECT COALESCE(SUM(tokens_used), 0) as c FROM stats", conn
            ).iloc[0]["c"]
            total_images = pd.read_sql_query(
                "SELECT COALESCE(SUM(images_generated), 0) as c FROM stats", conn
            ).iloc[0]["c"]
            mau = load_mau(30)
        except Exception:
            total_users = total_tokens = total_images = mau = 0
        finally:
            conn.close()

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Пользователей", total_users)
        col2.metric("MAU (30 дн.)", mau)
        col3.metric("Токенов израсходовано", f"{int(total_tokens):,}")
        col4.metric("Изображений", int(total_images))

        st.subheader("DAU (Daily Active Users)")
        dau_df = load_daily_active(30)
        if not dau_df.empty:
            st.line_chart(dau_df.set_index("date")["dau"])
        else:
            st.info("Нет данных")

        st.subheader("Расход токенов по дням")
        tokens_df = load_token_usage()
        if not tokens_df.empty:
            st.bar_chart(tokens_df.set_index("date")["tokens"])
        else:
            st.info("Нет данных")

    with tab_users:
        st.subheader("Список пользователей")
        users_df = load_users(300)
        if users_df.empty:
            st.info("Нет пользователей")
        else:
            # Поиск
            search = st.text_input("🔍 Поиск по ID, имени или username", "")
            if search:
                mask = (
                    users_df["telegram_id"].astype(str).str.contains(search, na=False)
                    | users_df["first_name"].astype(str).str.contains(search, na=False, case=False)
                    | users_df["username"].astype(str).str.contains(search, na=False, case=False)
                )
                users_df = users_df[mask]

            # Показываем колонки без is_banned (для компактности)
            display_df = users_df.drop(columns=["is_banned"], errors="ignore")
            st.dataframe(display_df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Действия над пользователем")
            tg_id = st.number_input("Telegram ID пользователя", min_value=1, value=0, step=1)
            if tg_id:
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    if st.button("⛔ Забанить", key="ban"):
                        exec_ban(tg_id, True)
                        st.success(f"Пользователь {tg_id} заблокирован")
                        st.rerun()
                with c2:
                    if st.button("✅ Разбанить", key="unban"):
                        exec_ban(tg_id, False)
                        st.success(f"Пользователь {tg_id} разблокирован")
                        st.rerun()
                with c3:
                    if st.button("⭐ Дать премиум", key="prem"):
                        exec_premium(tg_id, True)
                        st.success(f"Премиум выдан пользователю {tg_id}")
                        st.rerun()
                with c4:
                    if st.button("🔓 Снять премиум", key="unprem"):
                        exec_premium(tg_id, False)
                        st.success(f"Премиум снят у пользователя {tg_id}")
                        st.rerun()

    with tab_personas:
        st.subheader("Персонажи (промпты)")
        st.caption("Только просмотр. Редактирование — в config.py")
        try:
            import config

            for key, val in config.PERSONAS.items():
                with st.expander(f"**{val['name']}** (`{key}`)"):
                    st.text_area(
                        "Промпт", val["prompt"], height=120, disabled=True, key=f"persona_{key}"
                    )
        except Exception as e:
            st.warning(f"Не удалось загрузить персонажей: {e}")


if __name__ == "__main__":
    main()
