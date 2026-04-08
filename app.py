import os
import pandas as pd
import numpy as np
import base64
import io
import random
from faker import Faker
from flask import Flask, request, render_template_string, send_file

app = Flask(__name__)

# Константы
USERS_CSV = 'users.csv'
LIKES_CSV = 'likes.csv'

# 1. Генерация тестовых данных
def generate_data_if_not_exists():
    if os.path.exists(USERS_CSV) and os.path.exists(LIKES_CSV):
        return
    fake = Faker('ru_RU')
    n_users, n_videos, n_likes = 150, 600, 5000

    users = pd.DataFrame({
        'user_id': range(1, n_users + 1),
        'name': [fake.name() for _ in range(n_users)]
    })
    users.to_csv(USERS_CSV, index=False)

    likes_data = []
    for _ in range(n_likes):
        uid = random.randint(1, n_users)
        vid = random.randint(1, n_videos)
        likes_data.append({
            'user_id': uid,
            'url': f"https://media.example.com/v/{vid}",
            'timestamp': fake.date_time_between(start_date='-6m', end_date='now')
        })
    df_likes = pd.DataFrame(likes_data).drop_duplicates(subset=['user_id', 'url'])
    df_likes.to_csv(LIKES_CSV, index=False)
    print("✅ Тестовые данные сгенерированы и сохранены в CSV.")

# 2. Ядро рекомендаций
def calculate_recommendations(username: str, Nv: int = 10):
    u_df = pd.read_csv(USERS_CSV)
    l_df = pd.read_csv(LIKES_CSV, parse_dates=['timestamp'])

    if username not in u_df['name'].values:
        return pd.DataFrame(), "Пользователь не найден в базе."

    uid = u_df[u_df['name'] == username]['user_id'].iloc[0]
    
    # Последние Nv лайков целевого пользователя
    user_recent = l_df[l_df['user_id'] == uid].sort_values('timestamp', ascending=False).head(Nv)
    recent_urls = set(user_recent['url'].unique())

    # Пользователи, лайкавшие те же видео (коллаборативная связка)
    peers = l_df[(l_df['url'].isin(recent_urls)) & (l_df['user_id'] != uid)]
    peer_ids = peers['user_id'].unique()

    if len(peer_ids) == 0:
        return pd.DataFrame(), "Не найдено пользователей с пересекающимися интересами."

    # Кандидаты на рекомендацию (исключаем уже лайкнутые)
    candidates = l_df[(l_df['user_id'].isin(peer_ids)) & (~l_df['url'].isin(recent_urls))]
    if candidates.empty:
        return pd.DataFrame(), "Нет новых видео для рекомендации по заданным параметрам."

    # Скоринг: частота упоминаний среди "похожих" + свежесть лайка
    recs = candidates.groupby('url').agg(
        score=('user_id', 'count'),
        last_liked=('timestamp', 'max')
    ).reset_index()
    recs = recs.sort_values(['score', 'last_liked'], ascending=[False, False]).reset_index(drop=True)
    return recs, None

# 3. Шаблон HTML
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Рекомендательная система</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>body{background:#f8f9fa} .card{box-shadow:0 2px 8px rgba(0,0,0,.1)}</style>
</head>
<body class="container py-4">
    <div class="card p-4">
        <h3 class="mb-3">🎯 Генератор персональных рекомендаций</h3>
        <form method="POST" class="row g-3 mb-4">
            <div class="col-md-5">
                <label class="form-label fw-bold">Пользователь</label>
                <select name="username" class="form-select" required>
                    <option value="" disabled {% if not selected %}selected{% endif %}>Выберите из списка...</option>
                    {% for u in users %}
                    <option value="{{u}}" {% if u == selected %}selected{% endif %}>{{u}}</option>
                    {% endfor %}
                </select>
            </div>
            <div class="col-md-3">
                <label class="form-label fw-bold">Nv (последних лайков)</label>
                <input type="number" name="Nv" class="form-control" value="{{Nv}}" min="1" max="50">
            </div>
            <div class="col-md-4 d-flex align-items-end">
                <button type="submit" class="btn btn-primary w-100">🚀 Построить отчёт</button>
            </div>
        </form>
        {% if download_link %}
        <div class="mt-3">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <h5>Результат для: <span class="text-primary">{{selected}}</span></h5>
                <a href="{{download_link}}" class="btn btn-success" download="recs_{{selected}}.csv">📥 Скачать CSV</a>
            </div>
            <div class="table-responsive">
                {{ table_html|safe }}
            </div>
        </div>
        {% elif message %}
        <div class="alert alert-warning mt-3">⚠️ {{ message }}</div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/', methods=['GET', 'POST'])
def index():
    generate_data_if_not_exists()
    u_df = pd.read_csv(USERS_CSV)
    users = u_df['name'].tolist()

    if request.method == 'POST':
        username = request.form.get('username')
        Nv = int(request.form.get('Nv', 10))
        recs_df, msg = calculate_recommendations(username, Nv)

        if not recs_df.empty:
            # Генерация CSV в памяти для скачивания
            csv_buffer = io.BytesIO()
            recs_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_buffer.seek(0)
            b64 = base64.b64encode(csv_buffer.read()).decode()
            download_link = f"data:text/csv;base64,{b64}"
            
            table_html = recs_df.rename(columns={
                'url': 'Рекомендуемое видео',
                'score': 'Кол-во похожих лайков',
                'last_liked': 'Последний лайк у похожих'
            }).to_html(classes='table table-striped table-hover', index=False)
            return render_template_string(HTML_TEMPLATE, users=users, selected=username, Nv=Nv, 
                                          table_html=table_html, download_link=download_link, message=None)
        return render_template_string(HTML_TEMPLATE, users=users, selected=username, Nv=Nv, 
                                      table_html=None, download_link=None, message=msg)

    return render_template_string(HTML_TEMPLATE, users=users, selected=None, Nv=10, 
                                  table_html=None, download_link=None, message=None)

if __name__ == '__main__':
    print("🌐 Запуск сервера: http://127.0.0.1:5000")
    app.run(debug=True)