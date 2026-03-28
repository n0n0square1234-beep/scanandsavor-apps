import os
import json
import base64
import uuid
from datetime import datetime
from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import stripe

from models import db, User
from recipe_generator import generate_recipe_ideas, generate_full_recipe, analyze_image_ingredients, generate_meal_plan_ai, generate_grocery_list_ai
from favorites import load_favorites, save_favorite, remove_favorite
from meal_plans import load_meal_plans, save_meal_plan, remove_meal_plan

load_dotenv()

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = os.environ.get('SECRET_KEY', 'scanandsavor-secret-key-2024')
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'

database_url = os.environ.get('DATABASE_URL', 'sqlite:///users.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
CORS(app, supports_credentials=True, origins=['https://scanandsavor.onrender.com', 'http://localhost:5000'])

login_manager = LoginManager()
login_manager.init_app(app)

stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_BASIC_PRICE_ID = os.environ.get('STRIPE_BASIC_PRICE_ID')
STRIPE_PREMIUM_PRICE_ID = os.environ.get('STRIPE_PREMIUM_PRICE_ID')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.create_all()

# ── Shared recipes helpers ──────────────────────────────────────────────────
SHARED_RECIPES_FILE = "shared_recipes.json"

def load_shared_recipes():
    if not os.path.exists(SHARED_RECIPES_FILE):
        return {}
    with open(SHARED_RECIPES_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_shared_recipe(share_id, recipe):
    recipes = load_shared_recipes()
    recipes[share_id] = recipe
    with open(SHARED_RECIPES_FILE, "w", encoding="utf-8") as f:
        json.dump(recipes, f, ensure_ascii=False, indent=2)

# ── Static page ─────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return app.send_static_file('index.html')

# ── Auth routes ──────────────────────────────────────────────────────────────
@app.route('/auth/signup', methods=['POST'])
def signup():
    data = request.json
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    if not name or not email or not password:
        return jsonify({'error': 'All fields are required'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email already exists'}), 400
    hashed = generate_password_hash(password)
    user = User(name=name, email=email, password=hashed)
    db.session.add(user)
    db.session.commit()
    login_user(user, remember=True)
    return jsonify({'user': {'id': user.id, 'name': user.name, 'email': user.email, 'tier': user.tier, 'scans_used': user.scans_used}})

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({'error': 'Invalid email or password'}), 401
    login_user(user, remember=True)
    return jsonify({'user': {'id': user.id, 'name': user.name, 'email': user.email, 'tier': user.tier, 'scans_used': user.scans_used}})

@app.route('/auth/logout', methods=['POST'])
def logout():
    logout_user()
    return jsonify({'success': True})

@app.route('/auth/me')
def me():
    if current_user.is_authenticated:
        return jsonify({'user': {'id': current_user.id, 'name': current_user.name, 'email': current_user.email, 'tier': current_user.tier, 'scans_used': current_user.scans_used}})
    return jsonify({'user': None})

# ── Recipe routes ─────────────────────────────────────────────────────────────
@app.route('/recipe-list', methods=['POST'])
def recipe_list():
    data = request.json
    ingredients = data.get('ingredients', [])
    dietary_restrictions = data.get('dietary_restrictions', [])
    meal_type = data.get('meal_type', '')
    cook_time = data.get('cook_time', '')
    if not ingredients:
        return jsonify({'error': 'No ingredients provided'}), 400
    try:
        result = generate_recipe_ideas(ingredients, dietary_restrictions, meal_type, cook_time)
        return jsonify({'recipe_list': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/generate-recipe', methods=['POST'])
def generate_recipe():
    data = request.json
    ingredients = data.get('ingredients', [])
    dietary_restrictions = data.get('dietary_restrictions', [])
    meal_type = data.get('meal_type', '')
    recipe_name = data.get('recipe_name', '')
    cook_time = data.get('cook_time', '')
    try:
        result = generate_full_recipe(ingredients, dietary_restrictions, meal_type, recipe_name, cook_time)
        return jsonify({'recipe': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analyze-image', methods=['POST'])
def analyze_image():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required', 'message': 'Sign up free to scan your fridge and pantry with AI!'}), 401
    if current_user.tier == 'free':
        now = datetime.utcnow()
        if (now - current_user.scans_reset_date).days >= 30:
            current_user.scans_used = 0
            current_user.scans_reset_date = now
            db.session.commit()
        if not current_user.can_scan():
            return jsonify({'error': 'upgrade_required', 'message': 'You have used all 5 free scans this month. Upgrade to Basic for unlimited scans!'}), 403
    if 'image' not in request.files:
        return jsonify({'error': 'No image provided'}), 400
    image_file = request.files['image']
    image_data = base64.b64encode(image_file.read()).decode('utf-8')
    media_type = image_file.content_type or 'image/jpeg'
    try:
        ingredients = analyze_image_ingredients(image_data, media_type)
        current_user.use_scan()
        return jsonify({'ingredients': ingredients, 'scans_used': current_user.scans_used})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── Favorites routes ──────────────────────────────────────────────────────────
@app.route('/favorites', methods=['GET'])
def get_favorites():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required'}), 401
    favorites = load_favorites()
    return jsonify({'favorites': favorites})

@app.route('/favorites', methods=['POST'])
def add_favorite():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required'}), 401
    recipe = request.json
    favorites = save_favorite(recipe)
    return jsonify({'favorites': favorites})

@app.route('/favorites/<int:index>', methods=['DELETE'])
def delete_favorite(index):
    if not current_user.is_authenticated:
        return jsonify({'error': 'Not logged in'}), 401
    favorites = remove_favorite(index)
    return jsonify({'favorites': favorites})

# ── Meal plan routes ──────────────────────────────────────────────────────────
@app.route('/meal-plan', methods=['POST'])
def meal_plan():
    if not current_user.is_authenticated or current_user.tier != 'premium':
        return jsonify({'error': 'premium_required'}), 403
    data = request.json
    ingredients = data.get('ingredients', [])
    dietary_restrictions = data.get('dietary_restrictions', [])
    days = data.get('days', 7)
    budget = data.get('budget', None)
    try:
        result = generate_meal_plan_ai(ingredients, dietary_restrictions, days, budget)
        return jsonify({'meal_plan': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/grocery-list', methods=['POST'])
def grocery_list():
    if not current_user.is_authenticated or current_user.tier != 'premium':
        return jsonify({'error': 'premium_required'}), 403
    data = request.json
    selected_meals = data.get('selected_meals', [])
    dietary_restrictions = data.get('dietary_restrictions', [])
    try:
        result = generate_grocery_list_ai(selected_meals, dietary_restrictions)
        return jsonify({'grocery_list': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/meal-plans', methods=['GET'])
def get_meal_plans():
    plans = load_meal_plans()
    return jsonify({'meal_plans': plans})

@app.route('/meal-plans', methods=['POST'])
def add_meal_plan():
    plan = request.json
    plans = save_meal_plan(plan)
    return jsonify({'meal_plans': plans})

@app.route('/meal-plans/<int:index>', methods=['DELETE'])
def delete_meal_plan(index):
    plans = remove_meal_plan(index)
    return jsonify({'meal_plans': plans})

# ── Recipe sharing routes ─────────────────────────────────────────────────────
@app.route('/share-recipe', methods=['POST'])
def share_recipe():
    data = request.json
    share_id = str(uuid.uuid4())[:8]
    save_shared_recipe(share_id, data)
    share_url = f"https://scanandsavor.onrender.com/recipe/{share_id}"
    return jsonify({'share_url': share_url})

@app.route('/recipe/<share_id>')
def view_shared_recipe(share_id):
    recipes = load_shared_recipes()
    recipe = recipes.get(share_id)
    if not recipe:
        return "<h2 style='font-family:sans-serif;text-align:center;margin-top:4rem;color:#888;'>Recipe not found or link expired.</h2>", 404
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{recipe.get('title', 'Recipe')} — Scan&Savor</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #f5f5f0; min-height: 100vh; }}
    .app {{ max-width: 480px; margin: 0 auto; padding: 1rem; }}
    .header {{ text-align: center; padding: 1.5rem 0 1rem; }}
    .logo {{ font-size: 24px; font-weight: 600; color: #1a1a1a; }}
    .logo span {{ color: #1D9E75; }}
    .card {{ background: white; border-radius: 16px; padding: 1.25rem; margin-bottom: 1rem; box-shadow: 0 1px 3px rgba(0,0,0,0.06); }}
    .recipe-title {{ font-size: 22px; font-weight: 700; color: #1a1a1a; margin-bottom: 4px; }}
    .recipe-meta {{ font-size: 13px; color: #888; margin-bottom: 16px; }}
    .macro-grid {{ display: grid; grid-template-columns: repeat(4,1fr); gap: 8px; margin-bottom: 16px; }}
    .macro-card {{ border-radius: 10px; padding: 10px; text-align: center; }}
    .macro-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }}
    .macro-value {{ font-size: 18px; font-weight: 600; margin-top: 2px; }}
    .section-label {{ font-size: 12px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; margin-top: 16px; }}
    ul, ol {{ padding-left: 20px; }}
    li {{ margin-bottom: 8px; line-height: 1.6; font-size: 15px; color: #333; }}
    .tip {{ background: #E1F5EE; border-radius: 10px; padding: 12px; margin-top: 16px; }}
    .cta {{ background: #1D9E75; color: white; border-radius: 12px; padding: 14px; text-align: center; margin-top: 1rem; text-decoration: none; display: block; font-weight: 600; font-size: 16px; }}
    .shared-badge {{ background: #E1F5EE; color: #0F6E56; border-radius: 99px; padding: 4px 12px; font-size: 12px; font-weight: 600; display: inline-block; margin-bottom: 12px; }}
  </style>
</head>
<body>
<div class="app">
  <div class="header">
    <div class="logo">Scan<span>&Savor</span></div>
  </div>
  <div class="shared-badge">📤 Shared recipe</div>
  <div class="card">
    <div class="recipe-title">{recipe.get('title', 'Recipe')}</div>
    <div class="recipe-meta">{recipe.get('time', '')}{'&nbsp;·&nbsp;' + str(recipe.get('servings','')) + ' servings' if recipe.get('servings') else ''}</div>
    {'<div class="macro-grid"><div class="macro-card" style="background:#f5f5f0;"><div class="macro-label" style="color:#888;">Calories</div><div class="macro-value" style="color:#1a1a1a;">' + str(recipe.get('calories','')) + '</div></div><div class="macro-card" style="background:#E1F5EE;"><div class="macro-label" style="color:#0F6E56;">Protein</div><div class="macro-value" style="color:#0F6E56;">' + str(recipe.get('protein','')) + 'g</div></div><div class="macro-card" style="background:#E6F1FB;"><div class="macro-label" style="color:#185FA5;">Carbs</div><div class="macro-value" style="color:#185FA5;">' + str(recipe.get('carbs','')) + 'g</div></div><div class="macro-card" style="background:#FAEEDA;"><div class="macro-label" style="color:#854F0B;">Fat</div><div class="macro-value" style="color:#854F0B;">' + str(recipe.get('fat','')) + 'g</div></div></div>' if recipe.get('calories') else ''}
    <div class="section-label">Ingredients</div>
    <ul>{''.join(f'<li>{i}</li>' for i in recipe.get('ingList', []))}</ul>
    <div class="section-label">Instructions</div>
    <ol>{''.join(f'<li>{i}</li>' for i in recipe.get('instructions', []))}</ol>
    {'<div class="tip"><strong style="color:#0F6E56;font-size:13px;">Chef Tip</strong><p style="color:#0F6E56;margin-top:4px;font-size:14px;">' + recipe.get('tip','') + '</p></div>' if recipe.get('tip') else ''}
  </div>
  <a href="https://scanandsavor.onrender.com" class="cta">🍽️ Try Scan&Savor free</a>
</div>
</body>
</html>"""

# ── Stripe routes ─────────────────────────────────────────────────────────────
@app.route('/stripe/create-checkout', methods=['POST'])
def create_checkout():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Please log in first'}), 401
    data = request.json
    tier = data.get('tier')
    price_id = STRIPE_BASIC_PRICE_ID if tier == 'basic' else STRIPE_PREMIUM_PRICE_ID
    if not price_id:
        return jsonify({'error': 'Price not configured'}), 500
    try:
        customer_id = current_user.stripe_customer_id
        if customer_id:
            try:
                stripe.Customer.retrieve(customer_id)
            except stripe.error.InvalidRequestError:
                customer_id = None
        if not customer_id:
            customer = stripe.Customer.create(email=current_user.email, name=current_user.name)
            customer_id = customer.id
            current_user.stripe_customer_id = customer_id
            db.session.commit()
        checkout = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url='https://scanandsavor.onrender.com/?upgraded=true',
            cancel_url='https://scanandsavor.onrender.com/',
        )
        return jsonify({'checkout_url': checkout.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stripe/cancel-subscription', methods=['POST'])
def cancel_subscription():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Not logged in'}), 401
    try:
        if current_user.stripe_subscription_id:
            stripe.Subscription.modify(current_user.stripe_subscription_id, cancel_at_period_end=True)
        current_user.tier = 'free'
        current_user.stripe_subscription_id = None
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/stripe/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature')
    webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')
    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            event = json.loads(payload)
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    if event['type'] == 'checkout.session.completed':
        session_obj = event['data']['object']
        customer_id = session_obj.get('customer')
        subscription_id = session_obj.get('subscription')
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user and subscription_id:
            sub = stripe.Subscription.retrieve(subscription_id)
            price_id = sub['items']['data'][0]['price']['id']
            if price_id == STRIPE_BASIC_PRICE_ID:
                user.tier = 'basic'
            elif price_id == STRIPE_PREMIUM_PRICE_ID:
                user.tier = 'premium'
            user.stripe_subscription_id = subscription_id
            db.session.commit()
    elif event['type'] in ['customer.subscription.deleted', 'customer.subscription.updated']:
        sub = event['data']['object']
        customer_id = sub.get('customer')
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            if sub['status'] in ['canceled', 'unpaid', 'past_due']:
                user.tier = 'free'
                user.stripe_subscription_id = None
                db.session.commit()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=True)