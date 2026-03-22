from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from recipe_generator import generate_recipe, generate_recipe_list, analyze_image, generate_meal_plan, generate_grocery_list
from favorites import load_favorites, save_favorite, remove_favorite
from meal_plans import load_meal_plans, save_meal_plan, remove_meal_plan
from models import db, User
import base64
import stripe
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='.')
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'scanandsavor-secret-key-2024')

database_url = os.getenv('DATABASE_URL', 'sqlite:///scanandsavor.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
CORS(app, supports_credentials=True, origins=['https://scanandsavor.onrender.com'])

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_BASIC_PRICE_ID = os.getenv('STRIPE_BASIC_PRICE_ID')
STRIPE_PREMIUM_PRICE_ID = os.getenv('STRIPE_PREMIUM_PRICE_ID')

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

with app.app_context():
    db.drop_all()
    db.create_all()

@app.route('/')
def home():
    return send_from_directory('.', 'index.html')

@app.route('/auth/signup', methods=['POST'])
def signup():
    data = request.json
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')
    name = data.get('name', '')
    if not email or not password or not name:
        return jsonify({'error': 'Please fill in all fields'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'An account with this email already exists'}), 400
    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    hashed_password = generate_password_hash(password)
    customer = stripe.Customer.create(email=email, name=name)
    user = User(email=email, password=hashed_password, name=name, stripe_customer_id=customer.id)
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return jsonify({'success': True, 'user': {'name': user.name, 'email': user.email, 'tier': user.tier, 'scans_used': user.scans_used}})

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').lower().strip()
    password = data.get('password', '')
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({'error': 'Incorrect email or password'}), 401
    login_user(user)
    return jsonify({'success': True, 'user': {'name': user.name, 'email': user.email, 'tier': user.tier, 'scans_used': user.scans_used}})

@app.route('/auth/logout', methods=['POST'])
def logout():
    logout_user()
    return jsonify({'success': True})

@app.route('/auth/me', methods=['GET'])
def me():
    if current_user.is_authenticated:
        return jsonify({'user': {'name': current_user.name, 'email': current_user.email, 'tier': current_user.tier, 'scans_used': current_user.scans_used}})
    return jsonify({'user': None})

@app.route('/stripe/config', methods=['GET'])
def stripe_config():
    return jsonify({'publishable_key': STRIPE_PUBLISHABLE_KEY})

@app.route('/stripe/create-checkout', methods=['POST'])
def create_checkout():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Please log in first'}), 401
    data = request.json
    tier = data.get('tier')
    price_id = STRIPE_BASIC_PRICE_ID if tier == 'basic' else STRIPE_PREMIUM_PRICE_ID
    try:
        checkout_session = stripe.checkout.Session.create(
            customer=current_user.stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{'price': price_id, 'quantity': 1}],
            mode='subscription',
            success_url='https://scanandsavor.onrender.com/stripe/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url='https://scanandsavor.onrender.com/',
        )
        return jsonify({'checkout_url': checkout_session.url})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/stripe/success')
def stripe_success():
    session_id = request.args.get('session_id')
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        customer_id = session.customer
        user = User.query.filter_by(stripe_customer_id=customer_id).first()
        if user:
            subscription = stripe.Subscription.retrieve(session.subscription)
            price_id = subscription['items']['data'][0]['price']['id']
            if price_id == STRIPE_BASIC_PRICE_ID:
                user.tier = 'basic'
            elif price_id == STRIPE_PREMIUM_PRICE_ID:
                user.tier = 'premium'
            user.stripe_subscription_id = session.subscription
            db.session.commit()
            login_user(user)
    except Exception as e:
        print("Stripe success error:", e)
    return send_from_directory('.', 'index.html')

@app.route('/stripe/cancel-subscription', methods=['POST'])
def cancel_subscription():
    if not current_user.is_authenticated:
        return jsonify({'error': 'Please log in'}), 401
    try:
        if current_user.stripe_subscription_id:
            stripe.Subscription.cancel(current_user.stripe_subscription_id)
            current_user.tier = 'free'
            current_user.stripe_subscription_id = None
            db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/analyze-image', methods=['POST'])
def analyze():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required', 'message': 'Create a free account to use photo scanning!'}), 401
    if not current_user.can_scan():
        return jsonify({'error': 'upgrade_required', 'message': 'You have used all 5 free scans this month. Upgrade to Basic for unlimited scans!'}), 403
    if 'image' not in request.files:
        return jsonify({'error': 'No image uploaded'}), 400
    file = request.files['image']
    media_type = file.content_type
    image_data = base64.standard_b64encode(file.read()).decode('utf-8')
    ingredients = analyze_image(image_data, media_type)
    current_user.use_scan()
    return jsonify({'ingredients': ingredients, 'scans_used': current_user.scans_used})

@app.route('/recipe-list', methods=['POST'])
def get_recipe_list():
    data = request.json
    ingredients = data.get('ingredients', [])
    dietary_restrictions = data.get('dietary_restrictions', [])
    meal_type = data.get('meal_type', '')
    cook_time = data.get('cook_time', '')
    if not ingredients:
        return jsonify({'error': 'Please add at least one ingredient'}), 400
    recipe_list = generate_recipe_list(ingredients, dietary_restrictions, meal_type, cook_time)
    return jsonify({'recipe_list': recipe_list})

@app.route('/generate-recipe', methods=['POST'])
def get_recipe():
    data = request.json
    ingredients = data.get('ingredients', [])
    dietary_restrictions = data.get('dietary_restrictions', [])
    meal_type = data.get('meal_type', '')
    recipe_name = data.get('recipe_name', '')
    cook_time = data.get('cook_time', '')
    if not ingredients:
        return jsonify({'error': 'Please add at least one ingredient'}), 400
    recipe = generate_recipe(ingredients, dietary_restrictions, meal_type, recipe_name, cook_time)
    return jsonify({'recipe': recipe})

@app.route('/meal-plan', methods=['POST'])
def get_meal_plan():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required', 'message': 'Please log in'}), 401
    if current_user.tier != 'premium':
        return jsonify({'error': 'premium_required', 'message': 'Meal planner is a Premium feature. Upgrade to access it!'}), 403
    data = request.json
    ingredients = data.get('ingredients', [])
    dietary_restrictions = data.get('dietary_restrictions', [])
    days = data.get('days', 7)
    meal_plan = generate_meal_plan(ingredients, dietary_restrictions, days)
    return jsonify({'meal_plan': meal_plan})

@app.route('/grocery-list', methods=['POST'])
def get_grocery_list():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required', 'message': 'Please log in'}), 401
    if current_user.tier != 'premium':
        return jsonify({'error': 'premium_required', 'message': 'Grocery list is a Premium feature.'}), 403
    data = request.json
    selected_meals = data.get('selected_meals', [])
    dietary_restrictions = data.get('dietary_restrictions', [])
    if not selected_meals:
        return jsonify({'error': 'No meals selected'}), 400
    grocery_list = generate_grocery_list(selected_meals, dietary_restrictions)
    return jsonify({'grocery_list': grocery_list})

@app.route('/meal-plans', methods=['GET'])
def get_meal_plans():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required'}), 401
    return jsonify({'meal_plans': load_meal_plans()})

@app.route('/meal-plans', methods=['POST'])
def add_meal_plan():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required'}), 401
    data = request.json
    plans = save_meal_plan(data)
    return jsonify({'meal_plans': plans})

@app.route('/meal-plans/<int:index>', methods=['DELETE'])
def delete_meal_plan(index):
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required'}), 401
    plans = remove_meal_plan(index)
    return jsonify({'meal_plans': plans})

@app.route('/favorites', methods=['GET'])
def get_favorites():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required', 'message': 'Create a free account to save favorites!'}), 401
    return jsonify({'favorites': load_favorites()})

@app.route('/favorites', methods=['POST'])
def add_favorite():
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required', 'message': 'Create a free account to save favorites!'}), 401
    data = request.json
    favorites = save_favorite(data)
    return jsonify({'favorites': favorites})

@app.route('/favorites/<int:index>', methods=['DELETE'])
def delete_favorite(index):
    if not current_user.is_authenticated:
        return jsonify({'error': 'signup_required'}), 401
    favorites = remove_favorite(index)
    return jsonify({'favorites': favorites})

if __name__ == '__main__':
    app.run(debug=True, port=5000)