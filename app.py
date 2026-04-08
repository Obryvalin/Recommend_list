import streamlit as st
import pandas as pd
import numpy as np
from faker import Faker
from datetime import datetime, timedelta

# ---------------------------------------------------------
# 1. Генерация тестовых данных
# ---------------------------------------------------------
@st.cache_data
def generate_data(n_users=60, n_videos=150, n_likes=800):
    fake = Faker('ru_RU')
    np.random.seed(42)

    users = pd.DataFrame({
        'user_id': range(1, n_users + 1),
        'name': [fake.name() for _ in range(n_users)]
    })

    videos = [f"https://video.example.com/v/{i:04d}" for i in range(1, n_videos + 1)]

    likes_data = []
    base_ts = datetime.now() - timedelta(days=365)
    for _ in range(n_likes):
        uid = np.random.randint(1, n_users + 1)
        vid = np.random.choice(videos)
        ts = base_ts + timedelta(seconds=np.random.randint(0, 365 * 24 * 3600))
        likes_data.append({'user_id': uid, 'url': vid, 'timestamp': ts})

    likes = pd.DataFrame(likes_data).drop_duplicates(subset=['user_id', 'url'])
    return users, likes

# ---------------------------------------------------------
# 2. Логика рекомендаций
# ---------------------------------------------------------
def get_recommendations(target_name, users_df, likes_df, Nv=10, K=15):
    # ID целевого пользователя
    mask_user = users_df['name'] == target_name
    if not mask_user.any():
        return pd.DataFrame()
    target_uid = users_df.loc[mask_user, 'user_id'].values[0]

    # Последние Nv лайков
    user_recent = (
        likes_df[likes_df['user_id'] == target_uid]
        .sort_values('timestamp', ascending=False)
        .head(Nv)
    )
    recent_urls = set(user_recent['url'])

    if not recent_urls:
        return pd.DataFrame()

    # Пользователи, лайкавшие те же видео (кроме самого себя)
    similar_users = likes_df[
        (likes_df['url'].isin(recent_urls)) & (likes_df['user_id'] != target_uid)
    ]['user_id'].unique()

    if len(similar_users) == 0:
        return pd.DataFrame()

    # Кандидаты: видео, лайкнутые похожими пользователями, но не самим целевым
    candidates = likes_df[
        (likes_df['user_id'].isin(similar_users)) & (~likes_df['url'].isin(recent_urls))
    ]

    # Скоринг: частота упоминаний + вес по свежести (опционально)
    recs = candidates.groupby('url').size().reset_index(name='score')
    recs = recs.sort_values('score', ascending=False).head(K)
    recs['reason'] = recs['score'].apply(lambda x: f"Совпадение с {x} пользователями")
    recs.rename(columns={'url': 'recommended_url'}, inplace=True)
    return recs

# ---------------------------------------------------------
# 3. Генерация HTML-отчёта
# ---------------------------------------------------------
def build_html_report(target_name, rec_df, Nv):
    if rec_df.empty:
        return "<html><body><p>Недостаточно данных для отчёта.</p></body></html>"

    table_html = rec_df.to_html(index=False, classes='rec-table', border=0, escape=False)
    now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Рекомендации для {target_name}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 40px; background: #f8f9fa; color: #333; }}
  h1 {{ border-bottom: 2px solid #2c7a7b; padding-bottom: 10px; }}
  .meta {{ color: #666; margin-bottom: 20px; }}
  table {{ width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
  th {{ background: #2c7a7b; color: #fff; text-align: left; padding: 12px; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #eee; }}
  tr:hover td {{ background: #f1f5f5; }}
  .footer {{ margin-top: 30px; font-size: 0.85em; color: #888; }}
</style>
</head>
<body>
  <h1>📊 Персональные рекомендации</h1>
  <p class="meta">Пользователь: <b>{target_name}</b> | Анализ последних <b>{Nv}</b> лайков | Сформировано: {now_str}</p>
  {table_html}
  <p class="footer">Отчёт сгенерирован автоматически. Алгоритм: коллаборативная фильтрация по свежим активностям.</p>
</body>
</html>"""

# ---------------------------------------------------------
# 4. Streamlit UI
# ---------------------------------------------------------
def main():
    st.set_page_config(page_title="Рекомендательная система", layout="centered")
    st.title("🎬 Рекомендатель видео")

    users_df, likes_df = generate_data()
    user_names = sorted(users_df['name'].tolist())

    col1, col2 = st.columns([2, 1])
    with col1:
        selected_user = st.selectbox("Выберите пользователя:", user_names, index=0)
    with col2:
        Nv = st.slider("Nv (последних лайков):", 3, 50, 10)
        K = st.slider("K (кол-во рекомендаций):", 5, 30, 10)

    if st.button("🔍 Сгенерировать список", type="primary"):
        with st.spinner("Анализирую пересечения и формирую рейтинг..."):
            rec_df = get_recommendations(selected_user, users_df, likes_df, Nv, K)

        if rec_df.empty:
            st.warning("⚠️ Недостаточно данных или нет пересекающихся активностей. Попробуйте увеличить Nv или выбрать другого пользователя.")
        else:
            st.success(f"✅ Найдено {len(rec_df)} релевантных рекомендаций")
            st.dataframe(rec_df, use_container_width=True)

            html_content = build_html_report(selected_user, rec_df, Nv)
            safe_filename = f"recommendations_{selected_user.replace(' ', '_')}.html"
            
            st.download_button(
                label="📥 Скачать HTML-отчёт",
                data=html_content,
                file_name=safe_filename,
                mime="text/html"
            )

if __name__ == "__main__":
    main()