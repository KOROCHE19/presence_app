# frontend - interface web pour le systeme de presences
# toutes les pages html sont ici

import os
import requests
from flask import Flask, render_template_string, request, redirect, url_for, session, flash

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secret123')

AUTH_URL = os.environ.get('AUTH_SERVICE_URL', 'http://auth_service:5001')
PLANNING_URL = os.environ.get('PLANNING_SERVICE_URL', 'http://planning_service:5002')
EMARG_URL = os.environ.get('EMARG_SERVICE_URL', 'http://emargement_service:5003')


# --- templates html ---

BASE_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Gestion Présences</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: Arial, sans-serif; background: #f0f2f5; color: #333; }

        .navbar {
            background: #2c3e50;
            color: white;
            padding: 15px 30px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .navbar a { color: white; text-decoration: none; margin-left: 20px; font-size: 14px; }
        .navbar a:hover { text-decoration: underline; }

        .container { max-width: 1100px; margin: 30px auto; padding: 0 20px; }

        .card {
            background: white;
            border-radius: 8px;
            padding: 25px;
            margin-bottom: 20px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.08);
        }
        .card h2 { margin-bottom: 20px; color: #2c3e50; font-size: 20px; }

        .btn {
            display: inline-block;
            padding: 9px 18px;
            border-radius: 5px;
            border: none;
            cursor: pointer;
            font-size: 14px;
            text-decoration: none;
            margin: 3px;
        }
        .btn-primary { background: #3498db; color: white; }
        .btn-success { background: #27ae60; color: white; }
        .btn-danger  { background: #e74c3c; color: white; }
        .btn-secondary { background: #95a5a6; color: white; }
        .btn:hover { opacity: 0.85; }

        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th { background: #f8f9fa; padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6; font-size: 13px; }
        td { padding: 10px; border-bottom: 1px solid #dee2e6; font-size: 14px; }
        tr:hover { background: #f8f9fa; }

        .form-group { margin-bottom: 15px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; font-size: 14px; }
        .form-group input, .form-group select, .form-group textarea {
            width: 100%; padding: 9px 12px; border: 1px solid #ced4da;
            border-radius: 5px; font-size: 14px;
        }

        .alert { padding: 12px 16px; border-radius: 5px; margin-bottom: 15px; font-size: 14px; }
        .alert-danger  { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }

        .badge {
            display: inline-block; padding: 3px 9px; border-radius: 12px;
            font-size: 12px; font-weight: bold;
        }
        .badge-success { background: #d4edda; color: #155724; }
        .badge-danger  { background: #f8d7da; color: #721c24; }
        .badge-warning { background: #fff3cd; color: #856404; }
        .badge-info    { background: #d1ecf1; color: #0c5460; }

        .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .stat-box { background: white; border-radius: 8px; padding: 20px; text-align: center; box-shadow: 0 2px 6px rgba(0,0,0,0.08); }
        .stat-box .number { font-size: 36px; font-weight: bold; color: #2c3e50; }
        .stat-box .label  { font-size: 13px; color: #666; margin-top: 5px; }

        .presence-row select { padding: 5px; border-radius: 4px; border: 1px solid #ced4da; }
    </style>
</head>
<body>
    {% if session.get('token') %}
    <div class="navbar">
        <strong>📋 Gestion Présences</strong>
        <div>
            <span style="font-size:13px; margin-right:15px;">{{ session.get('user_nom', '') }}</span>
            <a href="/sessions">Sessions</a>
            {% if session.get('role') == 'admin' %}
            <a href="/admin/promotions">Promotions</a>
            <a href="/admin/etudiants">Étudiants</a>
            {% endif %}
            <a href="/logout">Déconnexion</a>
        </div>
    </div>
    {% endif %}
    <div class="container">
        {% if get_flashed_messages() %}
            {% for msg in get_flashed_messages() %}
            <div class="alert alert-danger">{{ msg }}</div>
            {% endfor %}
        {% endif %}
        {{ content | safe }}
    </div>
</body>
</html>
"""


def render(content, **kwargs):
    return render_template_string(BASE_HTML, content=content, **kwargs)


def get_headers():
    """retourne les headers avec le token jwt"""
    return {'Authorization': 'Bearer ' + session.get('token', '')}


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('token'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


# --- pages ---

@app.route('/')
def index():
    if not session.get('token'):
        return redirect('/login')
    return redirect('/sessions')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            rep = requests.post(AUTH_URL + '/auth/login', json={
                'email': request.form['email'],
                'password': request.form['password']
            }, timeout=5)
            if rep.status_code == 200:
                data = rep.json()
                session['token'] = data['token']
                session['user_id'] = data['user']['id']
                session['user_nom'] = data['user']['prenom'] + ' ' + data['user']['nom']
                session['role'] = data['user']['role']
                return redirect('/sessions')
            else:
                flash(rep.json().get('error', 'Erreur de connexion'))
        except:
            flash('Service indisponible')

    content = """
    <div style="max-width:400px; margin:60px auto;">
    <div class="card">
        <h2>Connexion</h2>
        <form method="post">
            <div class="form-group">
                <label>Email</label>
                <input type="email" name="email" placeholder="formateur@ecole.fr" required>
            </div>
            <div class="form-group">
                <label>Mot de passe</label>
                <input type="password" name="password" required>
            </div>
            <button class="btn btn-primary" type="submit" style="width:100%">Se connecter</button>
        </form>
    </div>
    </div>
    """
    return render(content)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# liste des sessions
@app.route('/sessions')
@login_required
def sessions():
    try:
        rep = requests.get(EMARG_URL + '/emargement/sessions', headers=get_headers(), timeout=5)
        sessions_data = rep.json().get('sessions', []) if rep.status_code == 200 else []
    except:
        sessions_data = []
        flash('Erreur chargement sessions')

    lignes = ""
    for s in sessions_data:
        badge = '<span class="badge badge-success">ouverte</span>' if s['statut'] == 'ouverte' else '<span class="badge badge-info">fermée</span>'
        lignes += f"""
        <tr>
            <td>{s['date']}</td>
            <td>{s['heure_debut']} - {s['heure_fin']}</td>
            <td>{s.get('promotion_nom') or 'Promo #' + str(s['promotion_id'])}</td>
            <td>{s['matiere']}</td>
            <td>{s.get('formateur_nom', '')}</td>
            <td>{badge}</td>
            <td>
                <span class="badge badge-success">{s['nb_presents']} présents</span>
                <span class="badge badge-danger">{s['nb_absents']} absents</span>
            </td>
            <td><a href="/sessions/{s['id']}" class="btn btn-primary" style="padding:5px 10px; font-size:12px">Ouvrir</a></td>
        </tr>
        """

    content = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <h1 style="font-size:22px; color:#2c3e50;">Sessions de cours</h1>
        <a href="/sessions/nouvelle" class="btn btn-success">+ Nouvelle session</a>
    </div>
    <div class="card" style="padding:0; overflow:hidden;">
        <table>
            <thead><tr>
                <th>Date</th><th>Horaire</th><th>Promotion</th><th>Matière</th>
                <th>Formateur</th><th>Statut</th><th>Présences</th><th></th>
            </tr></thead>
            <tbody>{lignes if lignes else '<tr><td colspan="8" style="text-align:center;padding:30px;color:#999;">Aucune session</td></tr>'}</tbody>
        </table>
    </div>
    """
    return render(content)


# créer une nouvelle session
@app.route('/sessions/nouvelle', methods=['GET', 'POST'])
@login_required
def nouvelle_session():
    # recuperer les promotions
    try:
        rep = requests.get(PLANNING_URL + '/planning/promotions', headers=get_headers(), timeout=5)
        promotions = rep.json().get('promotions', []) if rep.status_code == 200 else []
    except:
        promotions = []

    if request.method == 'POST':
        try:
            rep = requests.post(EMARG_URL + '/emargement/sessions', headers=get_headers(), json={
                'promotion_id': int(request.form['promotion_id']),
                'matiere': request.form['matiere'],
                'date': request.form['date'],
                'heure_debut': request.form['heure_debut'],
                'heure_fin': request.form['heure_fin']
            }, timeout=10)
            if rep.status_code == 201:
                s_id = rep.json()['session']['id']
                return redirect('/sessions/' + str(s_id))
            else:
                flash(rep.json().get('error', 'Erreur création session'))
        except:
            flash('Erreur serveur')

    options_promo = ""
    for p in promotions:
        options_promo += f"<option value='{p['id']}'>{p['nom']} - {p.get('annee', '')} ({p.get('nb_etudiants', 0)} étudiants)</option>"

    from datetime import date
    today = date.today().strftime('%Y-%m-%d')

    content = f"""
    <div style="max-width:600px; margin:0 auto;">
    <h1 style="font-size:22px; color:#2c3e50; margin-bottom:20px;">Nouvelle session</h1>
    <div class="card">
        <form method="post">
            <div class="form-group">
                <label>Promotion</label>
                <select name="promotion_id" required>
                    <option value="">-- choisir une promotion --</option>
                    {options_promo}
                </select>
            </div>
            <div class="form-group">
                <label>Matière</label>
                <input type="text" name="matiere" placeholder="ex: Python, Réseau, BDD..." required>
            </div>
            <div class="form-group">
                <label>Date</label>
                <input type="date" name="date" value="{today}" required>
            </div>
            <div class="grid-2">
                <div class="form-group">
                    <label>Heure début</label>
                    <input type="time" name="heure_debut" value="08:00" required>
                </div>
                <div class="form-group">
                    <label>Heure fin</label>
                    <input type="time" name="heure_fin" value="10:00" required>
                </div>
            </div>
            <div style="display:flex; gap:10px; margin-top:10px;">
                <button class="btn btn-success" type="submit">Créer la session</button>
                <a href="/sessions" class="btn btn-secondary">Annuler</a>
            </div>
        </form>
    </div>
    </div>
    """
    return render(content)


# feuille de presence d'une session
@app.route('/sessions/<int:id>')
@login_required
def voir_session(id):
    try:
        rep = requests.get(EMARG_URL + '/emargement/sessions/' + str(id), headers=get_headers(), timeout=5)
        if rep.status_code != 200:
            flash('Session introuvable')
            return redirect('/sessions')
        s = rep.json()
    except:
        flash('Erreur chargement session')
        return redirect('/sessions')

    badge_statut = '<span class="badge badge-success">Ouverte</span>' if s['statut'] == 'ouverte' else '<span class="badge badge-info">Fermée</span>'

    lignes = ""
    for p in s.get('presences', []):
        nom_complet = (p.get('etudiant_prenom') or '') + ' ' + (p.get('etudiant_nom') or '')
        couleur_ligne = ''
        if p['statut'] == 'present': couleur_ligne = 'background:#f0fff4'
        elif p['statut'] == 'absent': couleur_ligne = 'background:#fff5f5'
        elif p['statut'] == 'retard': couleur_ligne = 'background:#fffbf0'

        if s['statut'] == 'ouverte':
            statut_html = f"""
            <select onchange="changerStatut({p['id']}, this.value)" style="padding:5px; border-radius:4px; border:1px solid #ced4da;">
                <option value="present" {'selected' if p['statut']=='present' else ''}>✅ Présent</option>
                <option value="absent"  {'selected' if p['statut']=='absent'  else ''}>❌ Absent</option>
                <option value="retard"  {'selected' if p['statut']=='retard'  else ''}>⏰ Retard</option>
                <option value="excusé"  {'selected' if p['statut']=='excusé'  else ''}>📝 Excusé</option>
            </select>
            """
        else:
            badges = {'present': 'badge-success', 'absent': 'badge-danger', 'retard': 'badge-warning', 'excusé': 'badge-info'}
            statut_html = f"<span class='badge {badges.get(p['statut'], '')}'>{p['statut']}</span>"

        lignes += f"<tr style='{couleur_ligne}'><td>{nom_complet}</td><td>{statut_html}</td></tr>"

    btn_fermer = ""
    if s['statut'] == 'ouverte':
        btn_fermer = f"<a href='/sessions/{id}/fermer' class='btn btn-danger' onclick=\"return confirm('Fermer cette session ?')\">Fermer la session</a>"

    content = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <div>
            <h1 style="font-size:22px; color:#2c3e50;">{s['matiere']} — {s.get('promotion_nom', 'Promo #' + str(s['promotion_id']))}</h1>
            <p style="color:#666; margin-top:5px; font-size:14px;">{s['date']} • {s['heure_debut']} - {s['heure_fin']} • {badge_statut}</p>
        </div>
        <div>
            {btn_fermer}
            <a href="/sessions" class="btn btn-secondary">Retour</a>
        </div>
    </div>

    <div class="grid-2" style="margin-bottom:20px;">
        <div class="stat-box">
            <div class="number" style="color:#27ae60;">{s['nb_presents']}</div>
            <div class="label">Présents</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color:#e74c3c;">{s['nb_absents']}</div>
            <div class="label">Absents</div>
        </div>
    </div>

    <div class="card" style="padding:0; overflow:hidden;">
        <table>
            <thead><tr><th>Étudiant</th><th>Présence</th></tr></thead>
            <tbody id="liste-presences">{lignes if lignes else '<tr><td colspan="2" style="text-align:center;padding:30px;color:#999;">Aucun étudiant</td></tr>'}</tbody>
        </table>
    </div>

    <script>
    // envoi la modification de statut au serveur sans recharger la page
    function changerStatut(presenceId, nouveauStatut) {{
        fetch('/api/presences/' + presenceId, {{
            method: 'PUT',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{statut: nouveauStatut}})
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.error) alert('Erreur : ' + data.error)
        }})
        .catch(() => alert('Erreur réseau'))
    }}
    </script>
    """
    return render(content)


# fermer une session
@app.route('/sessions/<int:id>/fermer')
@login_required
def fermer_session(id):
    try:
        rep = requests.post(EMARG_URL + '/emargement/sessions/' + str(id) + '/fermer', headers=get_headers(), timeout=5)
        if rep.status_code != 200:
            flash(rep.json().get('error', 'Erreur fermeture'))
    except:
        flash('Erreur serveur')
    return redirect('/sessions/' + str(id))


# api proxy pour modifier une presence (appelé en ajax depuis la page)
@app.route('/api/presences/<int:id>', methods=['PUT'])
@login_required
def api_modifier_presence(id):
    data = request.get_json()
    try:
        rep = requests.put(
            EMARG_URL + '/emargement/presences/' + str(id),
            headers=get_headers(),
            json=data,
            timeout=5
        )
        return rep.json(), rep.status_code
    except Exception as e:
        return {'error': str(e)}, 500


# --- pages admin ---

@app.route('/admin/promotions', methods=['GET', 'POST'])
@login_required
def admin_promotions():
    if session.get('role') != 'admin':
        flash('Réservé aux admins')
        return redirect('/sessions')

    # récuperer classes et promotions
    try:
        rep_classes = requests.get(PLANNING_URL + '/planning/classes', headers=get_headers(), timeout=5)
        classes = rep_classes.json().get('classes', []) if rep_classes.status_code == 200 else []

        rep_promos = requests.get(PLANNING_URL + '/planning/promotions', headers=get_headers(), timeout=5)
        promotions = rep_promos.json().get('promotions', []) if rep_promos.status_code == 200 else []
    except:
        classes = []
        promotions = []
        flash('Erreur chargement')

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'creer_classe':
                rep = requests.post(PLANNING_URL + '/planning/classes', headers=get_headers(), json={
                    'nom': request.form['nom'], 'code': request.form['code']
                }, timeout=5)
            elif action == 'creer_promo':
                rep = requests.post(PLANNING_URL + '/planning/promotions', headers=get_headers(), json={
                    'nom': request.form['nom'],
                    'annee': request.form['annee'],
                    'classe_id': int(request.form['classe_id'])
                }, timeout=5)
            if rep.status_code not in [200, 201]:
                flash(rep.json().get('error', 'Erreur'))
        except:
            flash('Erreur serveur')
        return redirect('/admin/promotions')

    options_classes = "".join([f"<option value='{c['id']}'>{c['nom']}</option>" for c in classes])

    lignes_classes = "".join([f"<tr><td>{c['nom']}</td><td><code>{c['code']}</code></td></tr>" for c in classes])
    lignes_promos = "".join([f"<tr><td>{p['nom']}</td><td>{p.get('annee','')}</td><td>{p.get('classe_nom','')}</td><td>{p.get('nb_etudiants',0)}</td></tr>" for p in promotions])

    content = f"""
    <h1 style="font-size:22px; color:#2c3e50; margin-bottom:20px;">Gestion des promotions</h1>
    <div class="grid-2">
        <div>
            <div class="card">
                <h2>Nouvelle classe</h2>
                <form method="post">
                    <input type="hidden" name="action" value="creer_classe">
                    <div class="form-group"><label>Nom</label><input name="nom" placeholder="ex: BTS SIO" required></div>
                    <div class="form-group"><label>Code</label><input name="code" placeholder="ex: BTS-SIO" required></div>
                    <button class="btn btn-success" type="submit">Créer</button>
                </form>
                <table style="margin-top:15px;">
                    <thead><tr><th>Nom</th><th>Code</th></tr></thead>
                    <tbody>{lignes_classes or '<tr><td colspan="2" style="color:#999">Aucune classe</td></tr>'}</tbody>
                </table>
            </div>
        </div>
        <div>
            <div class="card">
                <h2>Nouvelle promotion</h2>
                <form method="post">
                    <input type="hidden" name="action" value="creer_promo">
                    <div class="form-group"><label>Classe</label>
                        <select name="classe_id" required><option value="">-- choisir --</option>{options_classes}</select>
                    </div>
                    <div class="form-group"><label>Nom groupe</label><input name="nom" placeholder="ex: Groupe A" required></div>
                    <div class="form-group"><label>Année scolaire</label><input name="annee" placeholder="ex: 2025-2026" required></div>
                    <button class="btn btn-success" type="submit">Créer</button>
                </form>
                <table style="margin-top:15px;">
                    <thead><tr><th>Nom</th><th>Année</th><th>Classe</th><th>Étudiants</th></tr></thead>
                    <tbody>{lignes_promos or '<tr><td colspan="4" style="color:#999">Aucune promotion</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    </div>
    """
    return render(content)


@app.route('/admin/etudiants', methods=['GET', 'POST'])
@login_required
def admin_etudiants():
    if session.get('role') != 'admin':
        flash('Réservé aux admins')
        return redirect('/sessions')

    try:
        rep_promos = requests.get(PLANNING_URL + '/planning/promotions', headers=get_headers(), timeout=5)
        promotions = rep_promos.json().get('promotions', []) if rep_promos.status_code == 200 else []
    except:
        promotions = []

    promo_filtre = request.args.get('promotion_id', '')
    etudiants = []
    msg_import = None

    if promo_filtre:
        try:
            rep = requests.get(PLANNING_URL + '/planning/etudiants?promotion_id=' + promo_filtre, headers=get_headers(), timeout=5)
            etudiants = rep.json().get('etudiants', []) if rep.status_code == 200 else []
        except:
            flash('Erreur chargement étudiants')

    if request.method == 'POST':
        action = request.form.get('action')
        promo_id = request.form.get('promotion_id', '')

        if action == 'ajouter':
            try:
                rep = requests.post(PLANNING_URL + '/planning/etudiants', headers=get_headers(), json={
                    'nom': request.form['nom'],
                    'prenom': request.form['prenom'],
                    'email': request.form['email'],
                    'numero_etudiant': request.form.get('numero_etudiant') or None,
                    'promotion_id': int(promo_id)
                }, timeout=5)
                if rep.status_code in [200, 201]:
                    flash_msg = 'Étudiant ajouté ✓'
                else:
                    flash(rep.json().get('error', 'Erreur'))
            except:
                flash('Erreur serveur')

        elif action == 'import_csv':
            # import via fichier CSV
            fichier = request.files.get('fichier_csv')
            if not fichier or fichier.filename == '':
                flash('Aucun fichier sélectionné')
            else:
                try:
                    rep = requests.post(
                        PLANNING_URL + '/planning/etudiants/import-csv',
                        headers=get_headers(),
                        data={'promotion_id': promo_id},
                        files={'fichier': (fichier.filename, fichier.stream, 'text/csv')},
                        timeout=10
                    )
                    data = rep.json()
                    if rep.status_code in [200, 201]:
                        msg_import = data.get('message', 'Import terminé')
                        if data.get('erreurs'):
                            msg_import += ' — ' + str(len(data['erreurs'])) + ' ligne(s) ignorée(s)'
                    else:
                        flash(data.get('error', 'Erreur import'))
                except Exception as e:
                    flash('Erreur : ' + str(e))

        return redirect('/admin/etudiants?promotion_id=' + promo_id)

    options_promos = "".join([
        f"<option value='{p['id']}' {'selected' if str(p['id'])==promo_filtre else ''}>"
        f"{p['nom']} — {p.get('annee','')} ({p.get('nb_etudiants',0)} ét.)</option>"
        for p in promotions
    ])

    lignes = "".join([f"""
    <tr>
        <td>{e.get('numero_etudiant') or '—'}</td>
        <td>{e['prenom']} {e['nom']}</td>
        <td style="color:#666; font-size:13px;">{e['email']}</td>
    </tr>""" for e in etudiants])

    msg_import_html = f'<div class="alert alert-success">{msg_import}</div>' if msg_import else ''

    content = f"""
    <h1 style="font-size:22px; color:#2c3e50; margin-bottom:20px;">Gestion des étudiants</h1>

    {msg_import_html}

    <!-- choix de la promo -->
    <div class="card" style="padding:15px 25px;">
        <form method="get" style="display:flex; align-items:center; gap:12px;">
            <label style="font-weight:bold; white-space:nowrap;">Promotion :</label>
            <select name="promotion_id" style="flex:1; padding:8px; border:1px solid #ced4da; border-radius:5px; font-size:14px;">
                <option value="">-- choisir --</option>
                {options_promos}
            </select>
            <button class="btn btn-primary" type="submit">Voir</button>
        </form>
    </div>

    {"" if not promo_filtre else f'''
    <div class="grid-2">

        <!-- ajouter un etudiant manuellement -->
        <div class="card">
            <h2>Ajouter un étudiant</h2>
            <form method="post">
                <input type="hidden" name="action" value="ajouter">
                <input type="hidden" name="promotion_id" value="{promo_filtre}">
                <div class="form-group"><label>Nom</label><input name="nom" required></div>
                <div class="form-group"><label>Prénom</label><input name="prenom" required></div>
                <div class="form-group"><label>Email</label><input type="email" name="email" required></div>
                <div class="form-group"><label>N° étudiant <span style="color:#999;font-weight:normal">(optionnel)</span></label>
                    <input name="numero_etudiant"></div>
                <button class="btn btn-success" type="submit">Ajouter</button>
            </form>
        </div>

        <!-- import CSV -->
        <div class="card">
            <h2>Import CSV</h2>
            <p style="font-size:13px; color:#666; margin-bottom:15px;">
                Une ligne par étudiant, colonnes séparées par <code>,</code> ou <code>;</code><br>
                Format : <code>nom, prenom, email, numero_etudiant</code>
            </p>
            <div style="background:#f8f9fa; border-radius:5px; padding:12px; font-family:monospace; font-size:12px; margin-bottom:15px; color:#555;">
                Dupont;Jean;jean.dupont@email.fr;E001<br>
                Martin;Sophie;sophie.martin@email.fr;E002<br>
                Bernard;Lucas;lucas.b@email.fr;
            </div>
            <form method="post" enctype="multipart/form-data">
                <input type="hidden" name="action" value="import_csv">
                <input type="hidden" name="promotion_id" value="{promo_filtre}">
                <div class="form-group">
                    <label>Fichier CSV</label>
                    <input type="file" name="fichier_csv" accept=".csv,.txt" required
                           style="padding:6px; border:1px solid #ced4da; border-radius:5px; width:100%;">
                </div>
                <button class="btn btn-primary" type="submit">Importer</button>
            </form>
        </div>

    </div>

    <!-- liste des etudiants -->
    <div class="card" style="padding:0; overflow:hidden;">
        <div style="padding:15px 20px; border-bottom:1px solid #eee; display:flex; justify-content:space-between; align-items:center;">
            <strong>{len(etudiants)} étudiant(s) dans cette promotion</strong>
        </div>
        <table>
            <thead><tr><th>N°</th><th>Nom complet</th><th>Email</th></tr></thead>
            <tbody>{lignes if lignes else "<tr><td colspan='3' style='text-align:center;padding:25px;color:#999;'>Aucun étudiant dans cette promotion</td></tr>"}</tbody>
        </table>
    </div>
    '''}
    """
    return render(content)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
