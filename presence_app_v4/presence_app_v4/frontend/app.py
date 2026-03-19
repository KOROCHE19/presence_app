# frontend/app.py  —  v2
# Améliorations :
#   - AMÉLIORATION 2 : render_template() + dossier templates/ (plus de HTML dans Python)
#   - AMÉLIORATION 3 : pagination sur la liste des sessions et des étudiants
#   - AMÉLIORATION 5 : gunicorn (plus de debug=True)

import os
import logging
from datetime import date
from functools import wraps

import requests
from flask import Flask, render_template, request, redirect, session, flash

# ── logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] frontend — %(message)s'
)
logger = logging.getLogger(__name__)

# ── app ───────────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'secret123')

AUTH_URL     = os.environ.get('AUTH_SERVICE_URL',      'http://auth_service:5001')
PLANNING_URL = os.environ.get('PLANNING_SERVICE_URL',  'http://planning_service:5002')
EMARG_URL    = os.environ.get('EMARG_SERVICE_URL',     'http://emargement_service:5003')


# ── helpers ───────────────────────────────────────────────────────────────────
def get_headers():
    """Retourne le header Authorization portant le JWT de la session."""
    return {'Authorization': 'Bearer ' + session.get('token', '')}


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('token'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


# ── routes publiques ──────────────────────────────────────────────────────────
@app.route('/')
def index():
    if not session.get('token'):
        return redirect('/login')
    return redirect('/sessions')


@app.route('/login', methods=['GET', 'POST'])
def login():
    email_saisi = ''
    if request.method == 'POST':
        email_saisi = request.form.get('email', '')
        try:
            rep = requests.post(
                AUTH_URL + '/auth/login',
                json={'email': email_saisi, 'password': request.form['password']},
                timeout=5,
            )
            if rep.status_code == 200:
                data = rep.json()
                session['token']    = data['token']
                session['user_id']  = data['user']['id']
                session['user_nom'] = data['user']['prenom'] + ' ' + data['user']['nom']
                session['role']     = data['user']['role']
                logger.info('Connexion : %s', email_saisi)
                return redirect('/sessions')
            elif rep.status_code == 429:
                # Rate limit atteint sur auth_service
                flash('Trop de tentatives. Réessayez dans 1 minute.', 'danger')
            else:
                flash(rep.json().get('error', 'Erreur de connexion'), 'danger')
        except requests.exceptions.RequestException:
            flash('Service d\'authentification indisponible.', 'danger')

    # AMÉLIORATION 2 : render_template() au lieu de render_template_string()
    return render_template('login.html', email_saisi=email_saisi)


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ── sessions ──────────────────────────────────────────────────────────────────
@app.route('/sessions')
@login_required
def sessions():
    # AMÉLIORATION 3 : transmet page/per_page à l'API paginée
    page     = request.args.get('page', 1, type=int)
    per_page = 20

    sessions_data = []
    total = pages = 0
    has_next = has_prev = False

    try:
        rep = requests.get(
            EMARG_URL + '/emargement/sessions',
            headers=get_headers(),
            params={'page': page, 'per_page': per_page},
            timeout=5,
        )
        if rep.status_code == 200:
            payload    = rep.json()
            sessions_data = payload.get('sessions', [])
            total      = payload.get('total',    0)
            pages      = payload.get('pages',    1)
            has_next   = payload.get('has_next', False)
            has_prev   = payload.get('has_prev', False)
        else:
            flash('Erreur lors du chargement des sessions.', 'danger')
    except requests.exceptions.RequestException as e:
        logger.error('Erreur sessions : %s', e)
        flash('Service d\'émargement indisponible.', 'danger')

    return render_template(
        'sessions.html',
        sessions  = sessions_data,
        page      = page,
        pages     = pages,
        total     = total,
        has_next  = has_next,
        has_prev  = has_prev,
        per_page  = per_page,
    )


@app.route('/sessions/nouvelle', methods=['GET', 'POST'])
@login_required
def nouvelle_session():
    promotions = []
    try:
        rep = requests.get(
            PLANNING_URL + '/planning/promotions',
            headers=get_headers(),
            timeout=5,
        )
        if rep.status_code == 200:
            promotions = rep.json().get('promotions', [])
    except requests.exceptions.RequestException as e:
        logger.error('Erreur récupération promotions : %s', e)

    if request.method == 'POST':
        try:
            rep = requests.post(
                EMARG_URL + '/emargement/sessions',
                headers=get_headers(),
                json={
                    'promotion_id': int(request.form['promotion_id']),
                    'matiere':      request.form['matiere'],
                    'date':         request.form['date'],
                    'heure_debut':  request.form['heure_debut'],
                    'heure_fin':    request.form['heure_fin'],
                },
                timeout=10,
            )
            if rep.status_code == 201:
                s_id = rep.json()['session']['id']
                return redirect(f'/sessions/{s_id}')
            else:
                flash(rep.json().get('error', 'Erreur création session'), 'danger')
        except requests.exceptions.RequestException as e:
            logger.error('Erreur création session : %s', e)
            flash('Erreur serveur lors de la création.', 'danger')

    return render_template(
        'session_nouvelle.html',
        promotions = promotions,
        today      = date.today().strftime('%Y-%m-%d'),
    )


@app.route('/sessions/<int:id>')
@login_required
def voir_session(id):
    try:
        rep = requests.get(
            EMARG_URL + f'/emargement/sessions/{id}',
            headers=get_headers(),
            timeout=5,
        )
        if rep.status_code != 200:
            flash('Session introuvable.', 'danger')
            return redirect('/sessions')
        s = rep.json()
    except requests.exceptions.RequestException as e:
        logger.error('Erreur chargement session %d : %s', id, e)
        flash('Erreur chargement session.', 'danger')
        return redirect('/sessions')

    # AMÉLIORATION 2 : les données sont passées proprement au template
    # Plus de f-string avec du HTML dedans
    return render_template('session_detail.html', session=s, session_data=s)


@app.route('/sessions/<int:id>/fermer')
@login_required
def fermer_session(id):
    try:
        rep = requests.post(
            EMARG_URL + f'/emargement/sessions/{id}/fermer',
            headers=get_headers(),
            timeout=10,
        )
        if rep.status_code == 200:
            flash(rep.json().get('message', 'Session fermée.'), 'success')
        else:
            flash(rep.json().get('error', 'Erreur fermeture'), 'danger')
    except requests.exceptions.RequestException as e:
        logger.error('Erreur fermeture session %d : %s', id, e)
        flash('Erreur serveur.', 'danger')
    return redirect(f'/sessions/{id}')


# ── proxy AJAX présences ──────────────────────────────────────────────────────
@app.route('/api/presences/<int:id>', methods=['PUT'])
@login_required
def api_modifier_presence(id):
    """
    Proxy entre le JavaScript du navigateur et l'API emargement_service.
    Le JS ne peut pas appeler directement l'API (CORS + gestion du JWT).
    """
    data = request.get_json()
    try:
        rep = requests.put(
            EMARG_URL + f'/emargement/presences/{id}',
            headers=get_headers(),
            json=data,
            timeout=5,
        )
        return rep.json(), rep.status_code
    except requests.exceptions.RequestException as e:
        logger.error('Erreur modification présence %d : %s', id, e)
        return {'error': str(e)}, 500


# ── admin : promotions ────────────────────────────────────────────────────────
@app.route('/admin/promotions', methods=['GET', 'POST'])
@login_required
def admin_promotions():
    if session.get('role') != 'admin':
        flash('Réservé aux administrateurs.', 'danger')
        return redirect('/sessions')

    classes    = []
    promotions = []
    try:
        r1 = requests.get(PLANNING_URL + '/planning/classes',    headers=get_headers(), timeout=5)
        r2 = requests.get(PLANNING_URL + '/planning/promotions', headers=get_headers(), timeout=5)
        classes    = r1.json().get('classes',    []) if r1.status_code == 200 else []
        promotions = r2.json().get('promotions', []) if r2.status_code == 200 else []
    except requests.exceptions.RequestException as e:
        logger.error('Erreur chargement admin/promotions : %s', e)
        flash('Erreur chargement.', 'danger')

    if request.method == 'POST':
        action = request.form.get('action')
        try:
            if action == 'creer_classe':
                rep = requests.post(
                    PLANNING_URL + '/planning/classes',
                    headers=get_headers(),
                    json={'nom': request.form['nom'], 'code': request.form['code']},
                    timeout=5,
                )
            elif action == 'creer_promo':
                rep = requests.post(
                    PLANNING_URL + '/planning/promotions',
                    headers=get_headers(),
                    json={
                        'nom':       request.form['nom'],
                        'annee':     request.form['annee'],
                        'classe_id': int(request.form['classe_id']),
                    },
                    timeout=5,
                )
            else:
                rep = None

            if rep and rep.status_code not in [200, 201]:
                flash(rep.json().get('error', 'Erreur'), 'danger')
            elif rep:
                flash('Opération réussie.', 'success')
        except requests.exceptions.RequestException as e:
            logger.error('Erreur POST admin/promotions : %s', e)
            flash('Erreur serveur.', 'danger')
        return redirect('/admin/promotions')

    return render_template(
        'admin_promotions.html',
        classes    = classes,
        promotions = promotions,
    )


# ── admin : étudiants ─────────────────────────────────────────────────────────
@app.route('/admin/etudiants', methods=['GET', 'POST'])
@login_required
def admin_etudiants():
    if session.get('role') != 'admin':
        flash('Réservé aux administrateurs.', 'danger')
        return redirect('/sessions')

    promotions = []
    try:
        rep = requests.get(PLANNING_URL + '/planning/promotions', headers=get_headers(), timeout=5)
        promotions = rep.json().get('promotions', []) if rep.status_code == 200 else []
    except requests.exceptions.RequestException as e:
        logger.error('Erreur chargement promotions : %s', e)

    promo_filtre = request.args.get('promotion_id', '')
    page         = request.args.get('page', 1, type=int)
    per_page     = 50

    etudiants = []
    total = pages = 0
    has_next = has_prev = False
    msg_import = None

    if promo_filtre:
        try:
            rep = requests.get(
                PLANNING_URL + '/planning/etudiants',
                headers=get_headers(),
                params={'promotion_id': promo_filtre, 'page': page, 'per_page': per_page},
                timeout=5,
            )
            if rep.status_code == 200:
                payload  = rep.json()
                etudiants = payload.get('etudiants', [])
                total     = payload.get('total',    0)
                pages     = payload.get('pages',    1)
                has_next  = payload.get('has_next', False)
                has_prev  = payload.get('has_prev', False)
            else:
                flash('Erreur chargement étudiants.', 'danger')
        except requests.exceptions.RequestException as e:
            logger.error('Erreur étudiants promo %s : %s', promo_filtre, e)
            flash('Erreur service planning.', 'danger')

    if request.method == 'POST':
        action   = request.form.get('action')
        promo_id = request.form.get('promotion_id', '')

        if action == 'ajouter':
            try:
                rep = requests.post(
                    PLANNING_URL + '/planning/etudiants',
                    headers=get_headers(),
                    json={
                        'nom':              request.form['nom'],
                        'prenom':           request.form['prenom'],
                        'email':            request.form['email'],
                        'numero_etudiant':  request.form.get('numero_etudiant') or None,
                        'promotion_id':     int(promo_id),
                    },
                    timeout=5,
                )
                if rep.status_code in [200, 201]:
                    flash('Étudiant ajouté avec succès.', 'success')
                else:
                    flash(rep.json().get('error', 'Erreur ajout'), 'danger')
            except requests.exceptions.RequestException as e:
                logger.error('Erreur ajout étudiant : %s', e)
                flash('Erreur serveur.', 'danger')

        elif action == 'import_csv':
            fichier = request.files.get('fichier_csv')
            if not fichier or fichier.filename == '':
                flash('Aucun fichier sélectionné.', 'danger')
            else:
                try:
                    rep = requests.post(
                        PLANNING_URL + '/planning/etudiants/import-csv',
                        headers=get_headers(),
                        data={'promotion_id': promo_id},
                        files={'fichier': (fichier.filename, fichier.stream, 'text/csv')},
                        timeout=15,
                    )
                    data = rep.json()
                    if rep.status_code in [200, 201]:
                        msg_import = data.get('message', 'Import terminé')
                        if data.get('erreurs'):
                            msg_import += f" — {len(data['erreurs'])} ligne(s) ignorée(s)"
                        flash(msg_import, 'success')
                    else:
                        flash(data.get('error', 'Erreur import'), 'danger')
                except requests.exceptions.RequestException as e:
                    logger.error('Erreur import CSV : %s', e)
                    flash(f'Erreur : {e}', 'danger')

        return redirect(f'/admin/etudiants?promotion_id={promo_id}')

    return render_template(
        'admin_etudiants.html',
        promotions   = promotions,
        promo_filtre = promo_filtre,
        etudiants    = etudiants,
        total        = total,
        page         = page,
        pages        = pages,
        per_page     = per_page,
        has_next     = has_next,
        has_prev     = has_prev,
        msg_import   = msg_import,
    )


# ── AMÉLIORATION 5 : plus de app.run(debug=True) ─────────────────────────────
# Démarrage via gunicorn dans le Dockerfile :
#   CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
