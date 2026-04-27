"""
frontend_service - Interface web (BFF : Backend For Frontend)

Ce service ne stocke aucune donnee. Il sert les templates HTML et fait le relais
entre le navigateur et les APIs backend. Le JWT est conserve dans un cookie
HttpOnly (inaccessible depuis JavaScript), ce qui previent les attaques XSS.

Port : 5000
BDD  : aucune
"""

import os
import requests
from flask import Flask, render_template_string, request, redirect, session, flash, jsonify

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secret123')

AUTH_URL     = os.environ.get('AUTH_SERVICE_URL',   'http://auth_service:5001')
PLANNING_URL = os.environ.get('PLANNING_SERVICE_URL','http://planning_service:5002')
EMARG_URL    = os.environ.get('EMARG_SERVICE_URL',  'http://emargement_service:5003')


# ---------------------------------------------------------------------------
# Utilitaires
# ---------------------------------------------------------------------------

def get_headers():
    """Headers Bearer a passer a chaque appel API backend."""
    return {'Authorization': f"Bearer {session.get('token', '')}"}


def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('token'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


def api_get(url, defaut=None):
    """Appel GET avec gestion d'erreur silencieuse pour ne pas crasher le frontend."""
    try:
        rep = requests.get(url, headers=get_headers(), timeout=5)
        if rep.status_code == 200:
            return rep.json()
    except Exception:
        pass
    return defaut or {}


# ---------------------------------------------------------------------------
# Template de base
# ---------------------------------------------------------------------------

BASE = """
<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Gestion Presences - CNAM</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: Arial, sans-serif; background: #f0f2f5; color: #333; min-height: 100vh; }

        .navbar {
            background: #2c3e50; color: white;
            padding: 14px 30px;
            display: flex; justify-content: space-between; align-items: center;
        }
        .navbar a { color: #cdd5de; text-decoration: none; margin-left: 18px; font-size: 14px; }
        .navbar a:hover { color: white; }
        .navbar .titre { font-size: 16px; font-weight: bold; }

        .container { max-width: 1100px; margin: 28px auto; padding: 0 20px; }

        .card { background: white; border-radius: 8px; padding: 24px; margin-bottom: 20px;
                box-shadow: 0 2px 6px rgba(0,0,0,0.07); }
        .card h2 { margin-bottom: 18px; color: #2c3e50; font-size: 19px; }

        .btn { display: inline-block; padding: 8px 16px; border-radius: 5px;
               border: none; cursor: pointer; font-size: 14px; text-decoration: none; margin: 3px; }
        .btn-primary   { background: #3498db; color: white; }
        .btn-success   { background: #27ae60; color: white; }
        .btn-danger    { background: #e74c3c; color: white; }
        .btn-warning   { background: #f39c12; color: white; }
        .btn-secondary { background: #95a5a6; color: white; }
        .btn:hover { opacity: 0.85; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }

        table { width: 100%; border-collapse: collapse; }
        th { background: #f8f9fa; padding: 10px 12px; text-align: left;
             border-bottom: 2px solid #dee2e6; font-size: 13px; }
        td { padding: 10px 12px; border-bottom: 1px solid #dee2e6; font-size: 14px; }
        tr:hover td { background: #f8f9fa; }

        .form-group { margin-bottom: 14px; }
        .form-group label { display: block; margin-bottom: 5px; font-weight: bold; font-size: 14px; }
        .form-group input, .form-group select, .form-group textarea {
            width: 100%; padding: 8px 11px; border: 1px solid #ced4da;
            border-radius: 5px; font-size: 14px;
        }

        .alert { padding: 11px 15px; border-radius: 5px; margin-bottom: 14px; font-size: 14px; }
        .alert-danger  { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .alert-success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .alert-info    { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }

        .badge { display: inline-block; padding: 2px 9px; border-radius: 12px;
                 font-size: 12px; font-weight: bold; }
        .badge-green  { background: #d4edda; color: #155724; }
        .badge-red    { background: #f8d7da; color: #721c24; }
        .badge-orange { background: #fff3cd; color: #856404; }
        .badge-blue   { background: #d1ecf1; color: #0c5460; }
        .badge-gray   { background: #e9ecef; color: #495057; }

        .grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
        .grid4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; }

        .stat-box { background: white; border-radius: 8px; padding: 20px; text-align: center;
                    box-shadow: 0 2px 6px rgba(0,0,0,0.07); }
        .stat-box .chiffre { font-size: 38px; font-weight: bold; }
        .stat-box .libelle { font-size: 13px; color: #666; margin-top: 4px; }

        /* Selecteur de statut dans la feuille d'appel */
        .select-statut { padding: 5px 8px; border-radius: 4px; border: 1px solid #ced4da; font-size: 13px; }
        .select-statut.present { border-color: #27ae60; color: #155724; background: #f0fff4; }
        .select-statut.absent  { border-color: #e74c3c; color: #721c24; background: #fff5f5; }
        .select-statut.retard  { border-color: #f39c12; color: #856404; background: #fffbf0; }
        .select-statut.excuse  { border-color: #3498db; color: #0c5460; background: #f0f8ff; }

        /* Barre d'actions groupees */
        .bulk-bar { display: flex; gap: 10px; align-items: center; padding: 12px 16px;
                    background: #f8f9fa; border-bottom: 1px solid #eee; flex-wrap: wrap; }
        .bulk-bar span { font-size: 13px; color: #555; margin-right: 6px; }

        /* Modale de confirmation cloture */
        .modal-overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.5);
                         z-index: 1000; align-items: center; justify-content: center; }
        .modal-overlay.actif { display: flex; }
        .modal-box { background: white; border-radius: 10px; padding: 30px; max-width: 440px;
                     width: 90%; box-shadow: 0 8px 30px rgba(0,0,0,0.2); }
        .modal-box h3 { margin-bottom: 14px; color: #2c3e50; }
        .modal-box p  { color: #555; margin-bottom: 22px; font-size: 14px; line-height: 1.5; }
        .modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
    </style>
</head>
<body>
{% if session.get('token') %}
<div class="navbar">
    <span class="titre">Gestion Presences | CNAM</span>
    <div>
        <span style="font-size:13px; color:#aab; margin-right:14px;">{{ session.get('user_nom','') }}</span>
        <a href="/sessions">Sessions</a>
        {% if session.get('role') == 'admin' %}
        <a href="/admin/promotions">Promotions</a>
        <a href="/admin/etudiants">Etudiants</a>
        <a href="/admin/stats">Statistiques</a>
        {% endif %}
        <a href="/logout" style="color:#e88;">Deconnexion</a>
    </div>
</div>
{% endif %}
<div class="container">
    {% for msg in get_flashed_messages(with_categories=true) %}
    <div class="alert alert-{{ msg[0] if msg[0] in ['success','info'] else 'danger' }}">{{ msg[1] }}</div>
    {% endfor %}
    {{ content | safe }}
</div>
</body>
</html>
"""


def render(content):
    return render_template_string(BASE, content=content)


# ---------------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return redirect('/sessions' if session.get('token') else '/login')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            rep = requests.post(f"{AUTH_URL}/auth/login", json={
                'email':    request.form['email'],
                'password': request.form['password']
            }, timeout=5)
            if rep.status_code == 200:
                data = rep.json()
                session['token']    = data['token']
                session['user_id']  = data['user']['id']
                session['user_nom'] = data['user']['prenom'] + ' ' + data['user']['nom']
                session['role']     = data['user']['role']
                return redirect('/sessions')
            else:
                flash(rep.json().get('error', 'Identifiants incorrects'), 'danger')
        except Exception:
            flash('Service indisponible, reessayez dans un instant', 'danger')

    return render("""
    <div style="max-width:380px; margin:70px auto;">
    <div class="card">
        <h2 style="text-align:center; margin-bottom:24px;">Connexion</h2>
        <form method="post">
            <div class="form-group">
                <label>Adresse email</label>
                <input type="email" name="email" placeholder="formateur@ecole.fr" required autofocus>
            </div>
            <div class="form-group">
                <label>Mot de passe</label>
                <input type="password" name="password" required>
            </div>
            <button class="btn btn-primary" type="submit" style="width:100%; margin-top:6px;">Se connecter</button>
        </form>
    </div>
    </div>
    """)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ---------------------------------------------------------------------------
# Sessions de cours
# ---------------------------------------------------------------------------

@app.route('/sessions')
@login_required
def sessions():
    data = api_get(f"{EMARG_URL}/emargement/sessions")
    sessions_data = data.get('sessions', [])

    lignes = ''
    for s in sessions_data:
        badge_statut = (
            '<span class="badge badge-green">Ouverte</span>' if s['statut'] == 'ouverte'
            else '<span class="badge badge-gray">Fermee</span>'
        )
        lignes += f"""
        <tr>
            <td>{s['date']}</td>
            <td>{s['heure_debut']} - {s['heure_fin']}</td>
            <td>{s.get('promotion_nom') or 'Promo #' + str(s['promotion_id'])}</td>
            <td><strong>{s['matiere']}</strong></td>
            <td style="color:#666; font-size:13px;">{s.get('formateur_nom','')}</td>
            <td>{badge_statut}</td>
            <td>
                <span class="badge badge-green">{s['nb_presents']}P</span>
                <span class="badge badge-red">{s['nb_absents']}A</span>
            </td>
            <td><a href="/sessions/{s['id']}" class="btn btn-primary" style="padding:4px 10px;font-size:12px;">Ouvrir</a></td>
        </tr>"""

    corps = f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <h1 style="font-size:22px; color:#2c3e50;">Sessions de cours</h1>
        <a href="/sessions/nouvelle" class="btn btn-success">+ Nouvelle session</a>
    </div>
    <div class="card" style="padding:0; overflow:hidden;">
        <table>
            <thead><tr>
                <th>Date</th><th>Horaire</th><th>Promotion</th><th>Matiere</th>
                <th>Formateur</th><th>Statut</th><th>Presences</th><th></th>
            </tr></thead>
            <tbody>
                {lignes or '<tr><td colspan="8" style="text-align:center;padding:30px;color:#999;">Aucune session</td></tr>'}
            </tbody>
        </table>
    </div>"""
    return render(corps)


@app.route('/sessions/nouvelle', methods=['GET', 'POST'])
@login_required
def nouvelle_session():
    data_promos = api_get(f"{PLANNING_URL}/planning/promotions")
    promotions  = data_promos.get('promotions', [])

    if request.method == 'POST':
        try:
            rep = requests.post(f"{EMARG_URL}/emargement/sessions", headers=get_headers(), json={
                'promotion_id': int(request.form['promotion_id']),
                'matiere':      request.form['matiere'],
                'date':         request.form['date'],
                'heure_debut':  request.form['heure_debut'],
                'heure_fin':    request.form['heure_fin']
            }, timeout=10)
            if rep.status_code == 201:
                return redirect(f"/sessions/{rep.json()['session']['id']}")
            flash(rep.json().get('error', 'Erreur lors de la creation'), 'danger')
        except Exception:
            flash('Erreur serveur, reessayez', 'danger')

    options = ''.join(
        f"<option value='{p['id']}'>{p['nom']} - {p.get('annee','')} ({p.get('nb_etudiants',0)} et.)</option>"
        for p in promotions
    )
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')

    return render(f"""
    <div style="max-width:580px; margin:0 auto;">
    <h1 style="font-size:22px; color:#2c3e50; margin-bottom:18px;">Nouvelle session</h1>
    <div class="card">
        <form method="post">
            <div class="form-group">
                <label>Promotion</label>
                <select name="promotion_id" required>
                    <option value="">-- choisir une promotion --</option>
                    {options}
                </select>
            </div>
            <div class="form-group">
                <label>Matiere</label>
                <input type="text" name="matiere" placeholder="ex: Python, Reseau, BDD..." required>
            </div>
            <div class="form-group">
                <label>Date</label>
                <input type="date" name="date" value="{today}" required>
            </div>
            <div class="grid2">
                <div class="form-group">
                    <label>Heure debut</label>
                    <input type="time" name="heure_debut" value="08:00" required>
                </div>
                <div class="form-group">
                    <label>Heure fin</label>
                    <input type="time" name="heure_fin" value="10:00" required>
                </div>
            </div>
            <div style="display:flex; gap:10px; margin-top:8px;">
                <button class="btn btn-success" type="submit">Creer la session</button>
                <a href="/sessions" class="btn btn-secondary">Annuler</a>
            </div>
        </form>
    </div>
    </div>""")


@app.route('/sessions/<int:sid>')
@login_required
def voir_session(sid):
    rep = api_get(f"{EMARG_URL}/emargement/sessions/{sid}")
    if not rep:
        flash('Session introuvable', 'danger')
        return redirect('/sessions')

    s = rep
    est_ouverte = s['statut'] == 'ouverte'
    badge_statut = (
        '<span class="badge badge-green">Ouverte</span>' if est_ouverte
        else '<span class="badge badge-gray">Fermee</span>'
    )

    # Construction des lignes de la feuille d'appel
    lignes = ''
    for p in s.get('presences', []):
        nom_complet = f"{p.get('etudiant_prenom','')} {p.get('etudiant_nom','')}".strip()
        st = p['statut']

        if est_ouverte:
            # Selecteur AJAX pour modifier le statut sans recharger la page
            statut_html = f"""
            <select class="select-statut {st}"
                    onchange="changerStatut({p['id']}, this.value, this)">
                <option value="present" {'selected' if st=='present' else ''}>Presente</option>
                <option value="absent"  {'selected' if st=='absent'  else ''}>Absent</option>
                <option value="retard"  {'selected' if st=='retard'  else ''}>Retard</option>
                <option value="excuse"  {'selected' if st=='excuse'  else ''}>Excuse</option>
            </select>"""
        else:
            badges = {'present':'badge-green','absent':'badge-red','retard':'badge-orange','excuse':'badge-blue'}
            statut_html = f"<span class='badge {badges.get(st,'badge-gray')}'>{st}</span>"

        lignes += f"<tr id='ligne-{p['id']}'><td>{nom_complet}</td><td>{statut_html}</td></tr>"

    # Barre d'actions groupees (visible seulement si session ouverte)
    bulk_bar = ''
    if est_ouverte:
        bulk_bar = f"""
        <div class="bulk-bar">
            <span>Actions groupees :</span>
            <button class="btn btn-success" onclick="tousPresents()">Tous presents</button>
            <button class="btn btn-danger"  onclick="tousAbsents()">Tous absents</button>
        </div>"""

    # Bouton de cloture avec modale de confirmation
    btn_fermer = ''
    if est_ouverte and (s['formateur_id'] == session.get('user_id') or session.get('role') == 'admin'):
        nb_absents = s['nb_absents'] + s.get('nb_retards', 0)
        btn_fermer = f"""
        <button class="btn btn-danger" onclick="ouvrirModale()">Clore la session</button>
        <div class="modal-overlay" id="modal-cloture">
            <div class="modal-box">
                <h3>Confirmer la cloture</h3>
                <p>Cette action est irreversible. La session sera verrouilee et
                   <strong>{nb_absents} email(s)</strong> seront envoyes aux absents et retardataires.</p>
                <div class="modal-actions">
                    <button class="btn btn-secondary" onclick="fermerModale()">Annuler</button>
                    <a href="/sessions/{sid}/fermer" class="btn btn-danger">Confirmer la cloture</a>
                </div>
            </div>
        </div>"""

    return render(f"""
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px;">
        <div>
            <h1 style="font-size:22px; color:#2c3e50;">{s['matiere']} - {s.get('promotion_nom','Promo #'+str(s['promotion_id']))}</h1>
            <p style="color:#666; margin-top:5px; font-size:14px;">{s['date']} &bull; {s['heure_debut']} - {s['heure_fin']} &bull; {badge_statut}</p>
        </div>
        <div>
            {btn_fermer}
            <a href="/sessions" class="btn btn-secondary">Retour</a>
        </div>
    </div>

    <div class="grid4" style="margin-bottom:20px;">
        <div class="stat-box">
            <div class="chiffre" id="nb-presents" style="color:#27ae60;">{s['nb_presents']}</div>
            <div class="libelle">Presents</div>
        </div>
        <div class="stat-box">
            <div class="chiffre" id="nb-absents" style="color:#e74c3c;">{s['nb_absents']}</div>
            <div class="libelle">Absents</div>
        </div>
        <div class="stat-box">
            <div class="chiffre" id="nb-retards" style="color:#f39c12;">{s.get('nb_retards',0)}</div>
            <div class="libelle">Retards</div>
        </div>
        <div class="stat-box">
            <div class="chiffre" id="nb-excuses" style="color:#3498db;">{s.get('nb_excuses',0)}</div>
            <div class="libelle">Excuses</div>
        </div>
    </div>

    <div class="card" style="padding:0; overflow:hidden;">
        {bulk_bar}
        <table>
            <thead><tr><th>Etudiant</th><th style="width:160px;">Presence</th></tr></thead>
            <tbody id="liste-presences">
                {lignes or '<tr><td colspan="2" style="text-align:center;padding:30px;color:#999;">Aucun etudiant dans cette session</td></tr>'}
            </tbody>
        </table>
    </div>

    <div id="msg-ajax" style="position:fixed; bottom:20px; right:20px; display:none;
                               background:#2c3e50; color:white; padding:10px 18px;
                               border-radius:6px; font-size:13px;"></div>

    <script>
    // Met a jour un statut via PATCH et rafraichit les compteurs.
    // L'UI est modifiee immediatement (optimistic update), on revient en arriere si echec.
    function changerStatut(pid, statut, selectElem) {{
        const ancienStatut = selectElem.dataset.ancien || selectElem.value;
        selectElem.className = 'select-statut ' + statut;
        selectElem.dataset.ancien = statut;

        fetch('/api/presences/' + pid, {{
            method: 'PATCH',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ statut: statut }})
        }})
        .then(r => r.json())
        .then(data => {{
            if (data.error) {{
                afficherMsg('Erreur : ' + data.error, true);
                selectElem.value = ancienStatut;
                selectElem.className = 'select-statut ' + ancienStatut;
            }} else {{
                rafraichirCompteurs();
            }}
        }})
        .catch(() => {{
            afficherMsg('Erreur reseau, verifiez votre connexion', true);
            selectElem.value = ancienStatut;
        }});
    }}

    function rafraichirCompteurs() {{
        fetch('/api/sessions/{sid}/compteurs')
        .then(r => r.json())
        .then(d => {{
            document.getElementById('nb-presents').textContent = d.presents;
            document.getElementById('nb-absents').textContent  = d.absents;
            document.getElementById('nb-retards').textContent  = d.retards;
            document.getElementById('nb-excuses').textContent  = d.excuses;
        }})
        .catch(() => {{}});
    }}

    function tousPresents() {{ bulkAction('present'); }}
    function tousAbsents()  {{ bulkAction('absent');  }}

    function bulkAction(statut) {{
        fetch('/api/sessions/{sid}/bulk', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/json' }},
            body: JSON.stringify({{ statut: statut }})
        }})
        .then(r => r.json())
        .then(() => location.reload())
        .catch(() => afficherMsg('Erreur reseau', true));
    }}

    function afficherMsg(texte, erreur) {{
        const el = document.getElementById('msg-ajax');
        el.textContent = texte;
        el.style.background = erreur ? '#e74c3c' : '#27ae60';
        el.style.display = 'block';
        setTimeout(() => el.style.display = 'none', 3000);
    }}

    function ouvrirModale()  {{ document.getElementById('modal-cloture').classList.add('actif'); }}
    function fermerModale()  {{ document.getElementById('modal-cloture').classList.remove('actif'); }}
    </script>
    """)


@app.route('/sessions/<int:sid>/fermer')
@login_required
def fermer_session(sid):
    try:
        rep = requests.post(f"{EMARG_URL}/emargement/sessions/{sid}/fermer",
                            headers=get_headers(), timeout=5)
        if rep.status_code == 200:
            flash(rep.json().get('message', 'Session cloturee'), 'success')
        else:
            flash(rep.json().get('error', 'Erreur lors de la cloture'), 'danger')
    except Exception:
        flash('Erreur serveur', 'danger')
    return redirect(f'/sessions/{sid}')


# ---------------------------------------------------------------------------
# API proxy (appelee depuis le JavaScript de la page)
# ---------------------------------------------------------------------------

@app.route('/api/presences/<int:pid>', methods=['PATCH', 'PUT'])
@login_required
def api_modifier_presence(pid):
    """Relais AJAX : le JS appelle cette route, qui appelle l'emargement_service."""
    try:
        rep = requests.patch(
            f"{EMARG_URL}/emargement/presences/{pid}",
            headers=get_headers(),
            json=request.get_json(),
            timeout=5
        )
        return jsonify(rep.json()), rep.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/sessions/<int:sid>/compteurs')
@login_required
def api_compteurs(sid):
    """Retourne juste les compteurs de la session pour le rafraichissement AJAX."""
    data = api_get(f"{EMARG_URL}/emargement/sessions/{sid}")
    if not data:
        return jsonify({'presents': 0, 'absents': 0, 'retards': 0, 'excuses': 0}), 200
    return jsonify({
        'presents': data.get('nb_presents', 0),
        'absents':  data.get('nb_absents', 0),
        'retards':  data.get('nb_retards', 0),
        'excuses':  data.get('nb_excuses', 0)
    }), 200


@app.route('/api/sessions/<int:sid>/bulk', methods=['POST'])
@login_required
def api_bulk(sid):
    """Relais pour l'action groupee."""
    try:
        rep = requests.post(
            f"{EMARG_URL}/emargement/sessions/{sid}/bulk",
            headers=get_headers(),
            json=request.get_json(),
            timeout=5
        )
        return jsonify(rep.json()), rep.status_code
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ---------------------------------------------------------------------------
# Pages admin
# ---------------------------------------------------------------------------

@app.route('/admin/promotions', methods=['GET', 'POST'])
@login_required
def admin_promotions():
    if session.get('role') != 'admin':
        flash('Acces reserve aux administrateurs', 'danger')
        return redirect('/sessions')

    classes    = api_get(f"{PLANNING_URL}/planning/classes").get('classes', [])
    promotions = api_get(f"{PLANNING_URL}/planning/promotions").get('promotions', [])

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'creer_classe':
                rep = requests.post(f"{PLANNING_URL}/planning/classes", headers=get_headers(), json={
                    'nom': request.form['nom'], 'code': request.form['code']
                }, timeout=5)
            elif action == 'creer_promo':
                rep = requests.post(f"{PLANNING_URL}/planning/promotions", headers=get_headers(), json={
                    'nom':      request.form['nom'],
                    'annee':    request.form['annee'],
                    'classe_id': int(request.form['classe_id'])
                }, timeout=5)
            else:
                rep = None

            if rep and rep.status_code not in [200, 201]:
                flash(rep.json().get('error', 'Erreur'), 'danger')
            elif rep:
                flash('Operation realisee avec succes', 'success')
        except Exception:
            flash('Erreur serveur', 'danger')
        return redirect('/admin/promotions')

    opts_classes = ''.join(f"<option value='{c['id']}'>{c['nom']}</option>" for c in classes)
    lignes_classes = ''.join(f"<tr><td>{c['nom']}</td><td><code>{c['code']}</code></td></tr>" for c in classes)
    lignes_promos  = ''.join(
        f"<tr><td>{p['nom']}</td><td>{p.get('annee','')}</td><td>{p.get('classe_nom','')}</td><td>{p.get('nb_etudiants',0)}</td></tr>"
        for p in promotions
    )

    return render(f"""
    <h1 style="font-size:22px; color:#2c3e50; margin-bottom:20px;">Gestion des promotions</h1>
    <div class="grid2">
        <div>
            <div class="card">
                <h2>Nouvelle classe</h2>
                <form method="post">
                    <input type="hidden" name="action" value="creer_classe">
                    <div class="form-group"><label>Nom</label><input name="nom" placeholder="ex: DevOps, DevWeb" required></div>
                    <div class="form-group"><label>Code</label><input name="code" placeholder="ex: DEVOPS, DEVWEB" required></div>
                    <button class="btn btn-success" type="submit">Creer</button>
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
                        <select name="classe_id" required><option value="">-- choisir --</option>{opts_classes}</select>
                    </div>
                    <div class="form-group"><label>Nom groupe</label><input name="nom" placeholder="ex: Groupe A" required></div>
                    <div class="form-group"><label>Annee scolaire</label><input name="annee" placeholder="ex: 2025-2026" required></div>
                    <button class="btn btn-success" type="submit">Creer</button>
                </form>
                <table style="margin-top:15px;">
                    <thead><tr><th>Nom</th><th>Annee</th><th>Classe</th><th>Et.</th></tr></thead>
                    <tbody>{lignes_promos or '<tr><td colspan="4" style="color:#999">Aucune promotion</td></tr>'}</tbody>
                </table>
            </div>
        </div>
    </div>""")


@app.route('/admin/etudiants', methods=['GET', 'POST'])
@login_required
def admin_etudiants():
    if session.get('role') != 'admin':
        flash('Acces reserve aux administrateurs', 'danger')
        return redirect('/sessions')

    promotions   = api_get(f"{PLANNING_URL}/planning/promotions").get('promotions', [])
    promo_filtre = request.args.get('promotion_id', '')
    etudiants    = []
    msg_import   = None

    if promo_filtre:
        etudiants = api_get(f"{PLANNING_URL}/planning/etudiants?promotion_id={promo_filtre}").get('etudiants', [])

    if request.method == 'POST':
        action   = request.form.get('action')
        promo_id = request.form.get('promotion_id', '')
        try:
            if action == 'ajouter':
                rep = requests.post(f"{PLANNING_URL}/planning/etudiants", headers=get_headers(), json={
                    'nom':     request.form['nom'],
                    'prenom':  request.form['prenom'],
                    'email':   request.form['email'],
                    'numero_etudiant': request.form.get('numero_etudiant') or None,
                    'promotion_id': int(promo_id)
                }, timeout=5)
                if rep.status_code in [200, 201]:
                    flash('Etudiant ajoute', 'success')
                else:
                    flash(rep.json().get('error', 'Erreur'), 'danger')

            elif action == 'import_csv':
                fichier = request.files.get('fichier_csv')
                if not fichier or not fichier.filename:
                    flash('Aucun fichier selectionne', 'danger')
                else:
                    rep = requests.post(
                        f"{PLANNING_URL}/planning/etudiants/import-csv",
                        headers=get_headers(),
                        data={'promotion_id': promo_id},
                        files={'fichier': (fichier.filename, fichier.stream, 'text/csv')},
                        timeout=15
                    )
                    d = rep.json()
                    if rep.status_code in [200, 201]:
                        msg_import = f"{d.get('inseres', 0)} insere(s), {d.get('doublons_base', 0)} doublon(s), {d.get('doublons_fichier', 0)} doublon(s) fichier"
                        if d.get('erreurs'):
                            msg_import += f" - {len(d['erreurs'])} ligne(s) ignoree(s)"
                    else:
                        flash(d.get('error', 'Erreur import'), 'danger')
        except Exception as ex:
            flash(f'Erreur : {ex}', 'danger')

        return redirect(f'/admin/etudiants?promotion_id={promo_id}')

    opts_promos = ''.join(
        f"<option value='{p['id']}' {'selected' if str(p['id'])==promo_filtre else ''}>"
        f"{p['nom']} - {p.get('annee','')} ({p.get('nb_etudiants',0)} et.)</option>"
        for p in promotions
    )

    lignes = ''.join(f"""
    <tr>
        <td>{e.get('numero_etudiant') or '...'}</td>
        <td>{e['prenom']} {e['nom']}</td>
        <td style="color:#666;font-size:13px;">{e['email']}</td>
    </tr>""" for e in etudiants)

    msg_import_html = f'<div class="alert alert-success">{msg_import}</div>' if msg_import else ''

    section_etudiants = ''
    if promo_filtre:
        section_etudiants = f"""
        <div class="grid2">
            <div class="card">
                <h2>Ajouter un etudiant</h2>
                <form method="post">
                    <input type="hidden" name="action" value="ajouter">
                    <input type="hidden" name="promotion_id" value="{promo_filtre}">
                    <div class="form-group"><label>Nom</label><input name="nom" required></div>
                    <div class="form-group"><label>Prenom</label><input name="prenom" required></div>
                    <div class="form-group"><label>Email</label><input type="email" name="email" required></div>
                    <div class="form-group"><label>N? etudiant (optionnel)</label><input name="numero_etudiant"></div>
                    <button class="btn btn-success" type="submit">Ajouter</button>
                </form>
            </div>
            <div class="card">
                <h2>Import CSV ou Excel</h2>
                <p style="font-size:13px; color:#666; margin-bottom:12px;">
                    Colonnes acceptees : nom, prenom, email, numero_etudiant (optionnel).<br>
                    Separateur : virgule ou point-virgule, auto-detecte.
                </p>
                <div style="background:#f8f9fa; border-radius:5px; padding:11px; font-family:monospace; font-size:12px; margin-bottom:14px; color:#555;">
                    Dupont;Jean;jean.dupont@email.fr;E001<br>
                    Martin;Sophie;sophie.martin@email.fr;E002
                </div>
                <form method="post" enctype="multipart/form-data">
                    <input type="hidden" name="action" value="import_csv">
                    <input type="hidden" name="promotion_id" value="{promo_filtre}">
                    <div class="form-group">
                        <input type="file" name="fichier_csv" accept=".csv,.txt,.xlsx,.xls" required
                               style="padding:6px; border:1px solid #ced4da; border-radius:5px; width:100%;">
                    </div>
                    <button class="btn btn-primary" type="submit">Importer</button>
                </form>
            </div>
        </div>
        <div class="card" style="padding:0; overflow:hidden;">
            <div style="padding:13px 18px; border-bottom:1px solid #eee; display:flex; justify-content:space-between; align-items:center;">
                <strong>{len(etudiants)} etudiant(s)</strong>
            </div>
            <table>
                <thead><tr><th>N?</th><th>Nom complet</th><th>Email</th></tr></thead>
                <tbody>{lignes or "<tr><td colspan='3' style='text-align:center;padding:24px;color:#999;'>Aucun etudiant dans cette promotion</td></tr>"}</tbody>
            </table>
        </div>"""

    return render(f"""
    <h1 style="font-size:22px; color:#2c3e50; margin-bottom:20px;">Gestion des etudiants</h1>
    {msg_import_html}
    <div class="card" style="padding:14px 22px; margin-bottom:20px;">
        <form method="get" style="display:flex; align-items:center; gap:12px;">
            <label style="font-weight:bold; white-space:nowrap;">Promotion :</label>
            <select name="promotion_id" style="flex:1; padding:8px; border:1px solid #ced4da; border-radius:5px; font-size:14px;">
                <option value="">-- choisir --</option>
                {opts_promos}
            </select>
            <button class="btn btn-primary" type="submit">Voir</button>
        </form>
    </div>
    {section_etudiants}
    """)


@app.route('/admin/stats')
@login_required
def admin_stats():
    if session.get('role') != 'admin':
        return redirect('/sessions')

    stats = api_get(f"{EMARG_URL}/emargement/stats")

    return render(f"""
    <h1 style="font-size:22px; color:#2c3e50; margin-bottom:20px;">Statistiques globales</h1>
    <div class="grid4" style="margin-bottom:24px;">
        <div class="stat-box">
            <div class="chiffre" style="color:#27ae60;">{stats.get('taux_presence', 0)}%</div>
            <div class="libelle">Taux de presence global</div>
        </div>
        <div class="stat-box">
            <div class="chiffre" style="color:#2c3e50;">{stats.get('total_sessions', 0)}</div>
            <div class="libelle">Sessions totales</div>
        </div>
        <div class="stat-box">
            <div class="chiffre" style="color:#3498db;">{stats.get('sessions_ouvertes', 0)}</div>
            <div class="libelle">Sessions en cours</div>
        </div>
        <div class="stat-box">
            <div class="chiffre" style="color:#e74c3c;">{stats.get('emails_envoyes', 0)}</div>
            <div class="libelle">Emails envoyes</div>
        </div>
    </div>
    <div class="card">
        <p style="color:#666; font-size:14px;">
            Les statistiques par promotion sont disponibles via l API
            <code>/emargement/stats/promotion/:id</code>.
            Un graphique Chart.js sera integre ici en v2.
        </p>
    </div>""")


# ---------------------------------------------------------------------------
# Demarrage
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
