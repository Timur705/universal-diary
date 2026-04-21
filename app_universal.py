import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
from supabase import create_client, Client

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'universal_diary_secret_2026')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=1095)
app.config['SESSION_PERMANENT'] = True

SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ========== Вспомогательные функции ==========
def get_quarter(date_str):
    try:
        if '-' in date_str:
            date = datetime.strptime(date_str, '%Y-%m-%d')
        elif '.' in date_str:
            date = datetime.strptime(date_str, '%d.%m.%Y')
        else:
            return None
        year = date.year
        if (date.month == 9 and date.day >= 1) or (date.month == 10 and date.day <= 28):
            return 1
        if date.month == 11 or (date.month == 12 and date.day <= 31):
            return 2
        if (date.month == 1 and date.day >= 5) or date.month == 2 or (date.month == 3 and date.day <= 31):
            return 3
        if date.month == 4 or (date.month == 5 and date.day <= 31):
            return 4
    except:
        pass
    return None

def get_current_quarter():
    today = datetime.now()
    if today.month in [6,7,8]:
        return 4
    return get_quarter(today.strftime('%Y-%m-%d'))

def get_quarter_dates(quarter, year=None):
    if year is None:
        year = datetime.now().year
    if quarter == 1:
        if datetime.now().month < 9:
            year -= 1
        return f"{year}-09-01", f"{year}-10-28"
    elif quarter == 2:
        if datetime.now().month < 9:
            year -= 1
        return f"{year}-11-01", f"{year}-12-31"
    elif quarter == 3:
        return f"{year}-01-05", f"{year}-03-31"
    elif quarter == 4:
        return f"{year}-04-01", f"{year}-05-31"
    return None, None

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session['user_id'] is None:
            flash('Пожалуйста, войдите в систему')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Пожалуйста, войдите')
            return redirect(url_for('login'))
        user_resp = supabase.table('users').select('is_admin').eq('user_id', session['user_id']).execute()
        if not user_resp.data or not user_resp.data[0].get('is_admin'):
            flash('Доступ запрещён')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

# ========== Маршруты ==========
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        resp = supabase.table('users').select('*').eq('username', username).execute()
        user = resp.data[0] if resp.data else None
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['full_name'] = user['full_name']
            session['class'] = user['class']
            session['is_admin'] = user.get('is_admin', False)
            session.permanent = True
            flash(f'Добро пожаловать, {user["full_name"]}!')
            return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm_password']
        full_name = request.form['full_name']
        class_name = request.form['class']

        if password != confirm:
            flash('Пароли не совпадают')
            return render_template('register.html')
        if len(password) < 4:
            flash('Пароль должен быть не менее 4 символов')
            return render_template('register.html')
        if not full_name.strip():
            flash('Введите ФИО')
            return render_template('register.html')
        if not class_name.strip():
            flash('Введите класс')
            return render_template('register.html')

        existing = supabase.table('users').select('username').eq('username', username).execute()
        if existing.data:
            flash('Пользователь с таким именем уже существует')
            return render_template('register.html')

        password_hash = generate_password_hash(password)
        supabase.table('users').insert({
            'username': username,
            'password_hash': password_hash,
            'full_name': full_name,
            'class': class_name,
            'is_admin': False
        }).execute()
        flash('Регистрация успешна! Теперь войдите.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Вы вышли')
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    if session.get('is_admin'):
        return redirect(url_for('admin_panel'))

    user_id = session['user_id']
    subjects_resp = supabase.table('user_subjects').select('*').eq('user_id', user_id).order('title').execute()
    subjects = subjects_resp.data

    grades_resp = supabase.table('grades').select('grade_id, subject_id, date, score, user_subjects(title)').eq('user_id', user_id).order('date', desc=True).execute()
    records = []
    for g in grades_resp.data:
        records.append({
            'grade_id': g['grade_id'],
            'title': g['user_subjects']['title'],
            'date': g['date'],
            'score': g['score']
        })

    records_with_quarter = []
    for r in records:
        quarter = get_quarter(r['date'])
        if '-' in r['date']:
            parts = r['date'].split('-')
            formatted_date = f"{parts[2]}.{parts[1]}.{parts[0]}"
        else:
            formatted_date = r['date']
        records_with_quarter.append(dict(r, quarter=quarter, date=formatted_date))

    return render_template('index.html',
                           records=records_with_quarter,
                           subjects=subjects,
                           username=session['full_name'],
                           current_quarter=get_current_quarter(),
                           is_teacher=False)

@app.route('/add-subject', methods=['POST'])
@login_required
def add_subject():
    if session.get('is_admin'):
        flash('Администратор не может добавлять предметы')
        return redirect(url_for('admin_panel'))
    title = request.form['title'].strip()
    if not title:
        flash('Название предмета не может быть пустым')
        return redirect(url_for('index'))
    existing = supabase.table('user_subjects').select('subject_id').eq('user_id', session['user_id']).eq('title', title).execute()
    if existing.data:
        flash('Такой предмет уже есть')
        return redirect(url_for('index'))
    supabase.table('user_subjects').insert({
        'user_id': session['user_id'],
        'title': title
    }).execute()
    flash(f'Предмет "{title}" добавлен')
    return redirect(url_for('index'))

@app.route('/delete-subject/<int:subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    if session.get('is_admin'):
        flash('Администратор не может удалять предметы')
        return redirect(url_for('admin_panel'))
    subj = supabase.table('user_subjects').select('user_id').eq('subject_id', subject_id).execute()
    if not subj.data or subj.data[0]['user_id'] != session['user_id']:
        flash('Нет прав')
        return redirect(url_for('index'))
    supabase.table('grades').delete().eq('subject_id', subject_id).execute()
    supabase.table('user_subjects').delete().eq('subject_id', subject_id).execute()
    flash('Предмет и все его оценки удалены')
    return redirect(url_for('index'))

@app.route('/add-grade', methods=['GET','POST'])
@login_required
def add_grade():
    if session.get('is_admin'):
        flash('Администратор не добавляет оценки')
        return redirect(url_for('admin_panel'))
    user_id = session['user_id']
    subjects_resp = supabase.table('user_subjects').select('*').eq('user_id', user_id).order('title').execute()
    subjects = subjects_resp.data
    if request.method == 'POST':
        subject_id = int(request.form['subject_id'])
        date = request.form['date']
        score = int(request.form['score'])
        if not (2 <= score <= 5):
            flash('Оценка должна быть от 2 до 5')
            return render_template('add.html', subjects=subjects, username=session['full_name'])
        if '.' in date:
            d,m,y = date.split('.')
            date_sql = f"{y}-{m}-{d}"
        else:
            date_sql = date
        supabase.table('grades').insert({
            'user_id': user_id,
            'subject_id': subject_id,
            'date': date_sql,
            'score': score
        }).execute()
        flash('Оценка добавлена')
        return redirect(url_for('index'))
    return render_template('add.html', subjects=subjects, username=session['full_name'])

@app.route('/delete-grade/<int:grade_id>', methods=['POST'])
@login_required
def delete_grade(grade_id):
    if session.get('is_admin'):
        flash('Администратор не удаляет оценки')
        return redirect(url_for('admin_panel'))
    grade = supabase.table('grades').select('user_id').eq('grade_id', grade_id).execute()
    if not grade.data or grade.data[0]['user_id'] != session['user_id']:
        flash('Нет прав')
        return redirect(url_for('index'))
    supabase.table('grades').delete().eq('grade_id', grade_id).execute()
    flash('Оценка удалена')
    return redirect(url_for('index'))

@app.route('/delete-all-grades', methods=['POST'])
@login_required
def delete_all_grades():
    if session.get('is_admin'):
        flash('Администратор не может удалять все оценки')
        return redirect(url_for('admin_panel'))
    supabase.table('grades').delete().eq('user_id', session['user_id']).execute()
    flash('Все ваши оценки удалены')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    if request.method == 'POST':
        full_name = request.form['full_name'].strip()
        class_name = request.form['class'].strip()
        old_password = request.form.get('old_password')
        new_password = request.form.get('new_password')
        confirm_new = request.form.get('confirm_new')
        if not full_name or not class_name:
            flash('ФИО и класс обязательны')
            return redirect(url_for('profile'))
        supabase.table('users').update({
            'full_name': full_name,
            'class': class_name
        }).eq('user_id', session['user_id']).execute()
        session['full_name'] = full_name
        session['class'] = class_name
        if old_password and new_password:
            if new_password != confirm_new:
                flash('Новый пароль не совпадает')
                return redirect(url_for('profile'))
            if len(new_password) < 4:
                flash('Пароль должен быть не менее 4 символов')
                return redirect(url_for('profile'))
            user_resp = supabase.table('users').select('password_hash').eq('user_id', session['user_id']).execute()
            if not user_resp.data or not check_password_hash(user_resp.data[0]['password_hash'], old_password):
                flash('Неверный старый пароль')
                return redirect(url_for('profile'))
            new_hash = generate_password_hash(new_password)
            supabase.table('users').update({'password_hash': new_hash}).eq('user_id', session['user_id']).execute()
            flash('Профиль обновлён, пароль изменён')
        else:
            flash('Профиль обновлён')
        return redirect(url_for('index'))
    return render_template('profile.html', username=session['username'], full_name=session['full_name'], class_name=session['class'])

# ========== API ==========
@app.route('/api/calculate', methods=['POST'])
@login_required
def api_calculate():
    data = request.get_json()
    user_id = session['user_id']
    subject_id = data.get('subject_id')
    target_threshold = float(data.get('threshold'))
    quarter = data.get('quarter')

    # Защита от None и строк
    if quarter is None or str(quarter).lower() == 'all':
        quarter = get_current_quarter()
    else:
        try:
            quarter = int(quarter)
        except:
            quarter = get_current_quarter()

    start_date, end_date = get_quarter_dates(quarter)
    if start_date is None or end_date is None:
        return jsonify({'error': 'Неверная четверть'}), 400

    start_obj = datetime.strptime(start_date, '%Y-%m-%d')
    end_obj = datetime.strptime(end_date, '%Y-%m-%d')

    resp = supabase.table('grades').select('score, date').eq('user_id', user_id).eq('subject_id', subject_id).execute()
    scores = []
    for row in resp.data:
        date_str = row['date']
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                date_obj = datetime.strptime(date_str, fmt)
                break
            except:
                continue
        else:
            continue
        if start_obj <= date_obj <= end_obj:
            scores.append(row['score'])

    current_count = len(scores)
    current_sum = sum(scores)

    if current_count == 0:
        return jsonify({
            'current_avg': 0,
            'count': 0,
            'has_estimates': False,
            'recommendation': '📝 Пока нет оценок в этой четверти. Добавьте первую оценку!'
        })

    current_avg = current_sum / current_count

    if current_avg >= target_threshold:
        return jsonify({
            'current_avg': round(current_avg, 2),
            'count': current_count,
            'has_estimates': True,
            'recommendation': f'🎉 Уже достигнут порог {target_threshold}! Текущий средний: {current_avg:.2f}'
        })

    # --- ПОЛНЫЙ ПЕРЕБОР КОМБИНАЦИЙ ---
    if target_threshold <= 2.67:
        allowed_grades = [5, 4, 3]
    else:
        allowed_grades = [5, 4]

    all_combinations = []

    for new_count in range(1, 16):
        needed_total = target_threshold * (current_count + new_count)
        needed_sum_from_new = max(0, needed_total - current_sum)

        max_possible = 5 * new_count
        min_possible = min(allowed_grades) * new_count

        if needed_sum_from_new > max_possible:
            continue
        if needed_sum_from_new <= min_possible:
            needed_sum_from_new = min_possible

        combos = []

        def generate(remaining, current, current_sum_combo):
            if remaining == 0:
                if current_sum_combo >= needed_sum_from_new:
                    cnt = {5: 0, 4: 0, 3: 0, 2: 0}
                    for g in current:
                        cnt[g] += 1
                    combos.append((cnt[5], cnt[4], cnt[3], cnt[2]))
                return
            for grade in allowed_grades:
                max_possible_remaining = grade + 5 * (remaining - 1)
                if current_sum_combo + max_possible_remaining < needed_sum_from_new:
                    continue
                generate(remaining - 1, current + [grade], current_sum_combo + grade)

        generate(new_count, [], 0)

        if combos:
            unique = []
            for c in combos:
                if c not in unique:
                    unique.append(c)
            unique.sort(key=lambda x: (-x[1], -x[0]))
            for combo in unique:
                all_combinations.append((new_count, combo[0], combo[1], combo[2], combo[3]))

    if not all_combinations:
        return jsonify({
            'current_avg': round(current_avg, 2),
            'count': current_count,
            'has_estimates': True,
            'recommendation': f'💪 Даже при всех пятёрках невозможно достичь порога {target_threshold} в этой четверти.'
        })

    only_fours = []
    mixed = []
    only_fives = []

    for new_count, fives, fours, threes, twos in all_combinations:
        if fives == 0 and fours > 0 and threes == 0:
            only_fours.append((new_count, fives, fours))
        elif fives > 0 and fours > 0:
            mixed.append((new_count, fives, fours))
        elif fives > 0 and fours == 0 and threes == 0:
            only_fives.append((new_count, fives, fours))

    min_only_fours = min(only_fours, key=lambda x: x[0]) if only_fours else None
    min_mixed = min(mixed, key=lambda x: x[0]) if mixed else None
    min_only_fives = min(only_fives, key=lambda x: x[0]) if only_fives else None

    quarter_names = {1: '1', 2: '2', 3: '3', 4: '4'}
    quarter_text = quarter_names.get(quarter, 'текущей')

    recommendation = f"📊 В {quarter_text} четверти\n\n"
    recommendation += f"📈 Текущий средний: {current_avg:.2f}\n\n"

    if min_only_fours:
        fours_count = min_only_fours[2]
        fours_list = ", ".join(["4"] * fours_count)
        recommendation += f"✅ Только 4-ки\n• {fours_list}\n\n"

    if min_mixed:
        mixed_fours = min_mixed[2]
        mixed_fives = min_mixed[1]
        mixed_list = []
        mixed_list.extend(["4"] * mixed_fours)
        mixed_list.extend(["5"] * mixed_fives)
        mixed_list_str = ", ".join(mixed_list)
        recommendation += f"✅ 4-ки и 5-ки\n• {mixed_list_str}\n\n"

    if min_only_fives:
        fives_count = min_only_fives[1]
        fives_list = ", ".join(["5"] * fives_count)
        recommendation += f"⭐ Только 5-ки\n• {fives_list}\n"

    return jsonify({
        'current_avg': round(current_avg, 2),
        'count': current_count,
        'has_estimates': True,
        'recommendation': recommendation,
        'need': {'combinations': all_combinations[:5]}
    })

@app.route('/api/preview', methods=['POST'])
@login_required
def api_preview():
    data = request.get_json()
    user_id = session['user_id']
    subject_id = data.get('subject_id')
    new_grades = data.get('new_grades')
    quarter = data.get('quarter')

    # Защита от None и строк
    if quarter is None or str(quarter).lower() == 'all':
        quarter = get_current_quarter()
    else:
        try:
            quarter = int(quarter)
        except:
            quarter = get_current_quarter()

    start_date, end_date = get_quarter_dates(quarter)
    if start_date is None or end_date is None:
        return jsonify({'error': 'Неверная четверть'}), 400

    start_obj = datetime.strptime(start_date, '%Y-%m-%d')
    end_obj = datetime.strptime(end_date, '%Y-%m-%d')

    resp = supabase.table('grades').select('score, date').eq('user_id', user_id).eq('subject_id', subject_id).execute()
    scores = []
    for row in resp.data:
        date_str = row['date']
        for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
            try:
                date_obj = datetime.strptime(date_str, fmt)
                break
            except:
                continue
        else:
            continue
        if start_obj <= date_obj <= end_obj:
            scores.append(row['score'])

    cnt = len(scores)
    total = sum(scores)

    if cnt == 0:
        new_avg = sum(new_grades) / len(new_grades)
        return jsonify({'current_avg': 0, 'new_avg': round(new_avg, 2), 'change': round(new_avg, 2), 'has_estimates': False})

    cur_avg = total / cnt
    new_avg = (total + sum(new_grades)) / (cnt + len(new_grades))
    change = new_avg - cur_avg
    return jsonify({'current_avg': round(cur_avg, 2), 'new_avg': round(new_avg, 2), 'change': round(change, 2), 'has_estimates': True})

@app.route('/api/stats', methods=['POST'])
@login_required
def api_stats():
    data = request.get_json()
    user_id = session['user_id']
    subject_id = data.get('subject_id')
    quarter = data.get('quarter')
    resp = supabase.table('grades').select('score, date').eq('user_id', user_id).eq('subject_id', subject_id).order('date', desc=True).execute()
    if quarter != 'all':
        start_date, end_date = get_quarter_dates(int(quarter))
        start_obj = datetime.strptime(start_date, '%Y-%m-%d')
        end_obj = datetime.strptime(end_date, '%Y-%m-%d')
        filtered = []
        for row in resp.data:
            date_str = row['date']
            for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    break
                except:
                    continue
            else:
                continue
            if start_obj <= date_obj <= end_obj:
                filtered.append(row)
        resp.data = filtered
    scores = [r['score'] for r in resp.data]
    if not scores:
        return jsonify({'count': 0, 'average': 0, 'scores': [], 'dates': []})
    avg = sum(scores) / len(scores)
    dates = []
    for r in resp.data:
        if '-' in r['date']:
            parts = r['date'].split('-')
            dates.append(f"{parts[2]}.{parts[1]}.{parts[0]}")
        else:
            dates.append(r['date'])
    return jsonify({'count': len(scores), 'average': round(avg, 2), 'scores': scores, 'dates': dates})

# ========== Админ-панель ==========
@app.route('/admin')
@admin_required
def admin_panel():
    users_resp = supabase.table('users').select('*').order('created_at', desc=True).execute()
    users = [u for u in users_resp.data if not u.get('is_admin')]
    stats = []
    for u in users:
        grades_resp = supabase.table('grades').select('score').eq('user_id', u['user_id']).execute()
        scores = [g['score'] for g in grades_resp.data]
        count = len(scores)
        avg = round(sum(scores)/count,2) if count else 0
        stats.append({
            'user_id': u['user_id'],
            'username': u['username'],
            'full_name': u['full_name'],
            'class': u['class'],
            'created_at': u['created_at'][:10] if u['created_at'] else '',
            'grades_count': count,
            'average': avg
        })
    classes = {}
    for u in users:
        cls = u['class']
        if cls not in classes:
            classes[cls] = {'total_avg':0, 'students_count':0, 'total_grades':0, 'sum_avg':0}
        classes[cls]['students_count'] += 1
        student_avg = next((s['average'] for s in stats if s['user_id'] == u['user_id']), 0)
        classes[cls]['sum_avg'] += student_avg
        classes[cls]['total_grades'] += next((s['grades_count'] for s in stats if s['user_id'] == u['user_id']), 0)
    for cls in classes:
        if classes[cls]['students_count'] > 0:
            classes[cls]['class_avg'] = round(classes[cls]['sum_avg'] / classes[cls]['students_count'], 2)
        else:
            classes[cls]['class_avg'] = 0
    return render_template('admin.html', users=stats, class_stats=classes)

@app.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user(user_id):
    supabase.table('users').delete().eq('user_id', user_id).eq('is_admin', False).execute()
    flash('Пользователь удалён')
    return redirect(url_for('admin_panel'))

@app.route('/admin/delete-user-grades/<int:user_id>', methods=['POST'])
@admin_required
def admin_delete_user_grades(user_id):
    supabase.table('grades').delete().eq('user_id', user_id).execute()
    flash('Все оценки пользователя удалены')
    return redirect(url_for('admin_panel'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)