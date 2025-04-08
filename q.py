from flask import Flask, render_template, request, jsonify, session, g, redirect, url_for
import pymysql
import os
from dotenv import load_dotenv
import random
import string
import secrets
from flask_wtf import CSRFProtect
from forms import LoginForm
from datetime import timedelta, datetime
import logging

logging.basicConfig(level=logging.INFO)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', secrets.token_hex(32))
app.permanent_session_lifetime = timedelta(seconds=3600)
csrf = CSRFProtect(app)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,
    SESSION_COOKIE_SAMESITE='Lax'
)

def get_db_connection():
    try:
        conn = pymysql.connect(
            host=os.getenv('DB_HOST', '127.0.0.1'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            db=os.getenv('DB_NAME', 'restaurant'),
            cursorclass=pymysql.cursors.DictCursor
        )
        return conn
    except pymysql.MySQLError as e:
        print(f"Database connection error: {e}")
        return None

@app.before_request
def before_request():
    g.db_connection = get_db_connection()
    if not g.db_connection:
        return jsonify({"message": "Failed to connect to database"}), 500

@app.teardown_request
def teardown_request(exception):
    if hasattr(g, 'db_connection') and g.db_connection:
        g.db_connection.close()

@app.route('/', methods=['GET'])
def home():
    form = LoginForm()
    return render_template('login.html', form=form)

@app.route('/web')
def web():
    if 'cId' not in session:
        return redirect('/')

    conn = g.db_connection
    username = "Guest"
    if conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username FROM customers WHERE cId = %s", (session['cId'],))
            result = cursor.fetchone()
            if result and 'username' in result:
                username = result['username']

    return render_template('web.html', username=username)

@app.route('/menu')
def menu_page():
    return render_template('menu.html')

@app.route('/points')
def points():
    return render_template('points.html')

@app.route('/orders')
def orders():
    return render_template('orders.html')

@app.route('/timer')
def timer_page():
    return render_template('timer.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

def generate_unique_order_id():
    return ''.join(random.choices(string.digits, k=6))

@app.route('/api/order-summary', methods=['POST'])
def order_summary():
    if 'cId' not in session:
        return jsonify({"message": "Not authenticated"}), 401

    data = request.get_json()
    if not data or 'orderData' not in data:
        return jsonify({"message": "Invalid request data"}), 400

    order_data = data['orderData']
    selected_items = order_data.get('selectedItems', [])

    if not selected_items:
        return jsonify({"message": "No items selected"}), 400

    conn = g.db_connection
    if not conn:
        return jsonify({"message": "Database connection failed"}), 500

    try:
        order_id = generate_unique_order_id()
        with conn.cursor() as cursor:
            for item in selected_items:
                required_fields = ['itemId', 'itemName', 'price', 'quantity']
                if not all(field in item for field in required_fields):
                    continue

                total_amount = float(item['price']) * int(item['quantity'])
                cursor.execute(
                    "INSERT INTO orders (orderId, cId, itemId, totalAmount, itemName, quantity, orderTime) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (order_id, session['cId'], item['itemId'], total_amount, item['itemName'], item['quantity'], datetime.now())
                )
            conn.commit()
        return jsonify({"message": "Order processed successfully", "orderId": order_id}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"message": "Error processing order", "error": str(e)}), 500

@csrf.exempt
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400

    username = data.get('username', '').strip()
    phone_number = data.get('phone_number', '').strip()

    if not username or not phone_number:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    if len(username) > 20 or not username.isalpha():
        return jsonify({'success': False, 'message': 'Username must be 1-20 alphabetic characters'}), 400

    if not phone_number.isdigit() or len(phone_number) != 10:
        return jsonify({'success': False, 'message': 'Phone number must be 10 digits'}), 400

    conn = g.db_connection
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'}), 500

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT cId FROM customers WHERE username = %s AND phone_number = %s", (username, phone_number))
            customer = cursor.fetchone()

            if customer:
                session['cId'] = customer['cId']
                return jsonify({'success': True, 'redirect': url_for('web'), 'message': 'Login successful'})

            cursor.execute("INSERT INTO customers (username, phone_number) VALUES (%s, %s)", (username, phone_number))
            conn.commit()
            session['cId'] = cursor.lastrowid

            return jsonify({'success': True, 'redirect': url_for('web'), 'message': 'Account created'})
    except pymysql.IntegrityError:
        return jsonify({'success': False, 'message': 'Username already exists'}), 400
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/redeem_reward', methods=['POST'])
def redeem_reward():
    if 'cId' not in session:
        return jsonify({'message': 'Not authenticated'}), 401

    points = request.json.get('points', 0)
    if not isinstance(points, int) or points < 0:
        return jsonify({'message': 'Invalid points value'}), 400

    if points >= 10:
        return jsonify({'success': True, 'redirect': url_for('orders')})
    return jsonify({'success': False, 'message': 'Need at least 10 points'}), 400

@csrf.exempt
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    logging.info(f"Webhook received: {data}")

    parameters = data.get('queryResult', {}).get('parameters', {})
    intent = data.get('queryResult', {}).get('intent', {}).get('displayName')
    username = "Guest"

    if 'cId' in session:
        conn = g.db_connection
        with conn.cursor() as cursor:
            cursor.execute("SELECT username FROM customers WHERE cId = %s", (session['cId'],))
            result = cursor.fetchone()
            if result:
                username = result['username']

    if intent == 'track.order':
        if 'cId' not in session:
            return jsonify({'fulfillmentText': "You're not logged in. Please log in first."})

        latest_order = get_latest_order(session['cId'])

        if latest_order and latest_order.get('orderTime'):
            order_time = latest_order['orderTime']
            now = datetime.now()
            elapsed_minutes = (now - order_time).total_seconds() / 60

            if elapsed_minutes < 5:
                status = "Your order is in the queue."
            elif elapsed_minutes < 10:
                status = "Your order is being prepared and will be out soon!"
            elif elapsed_minutes < 15:
                status = "Your order is in transit to the pickup counter."
            else:
                status = "Your order is ready! Please come pick it up."

            return jsonify({'fulfillmentText': status})
        else:
            return jsonify({'fulfillmentText': "I couldn't find any recent orders."})

    elif intent == 'loyalty.rewards':
        if 'cId' not in session:
            return jsonify({'fulfillmentText': "Please log in to view your loyalty rewards."})

        points = get_user_points(session['cId'])

        if points is not None:
            return jsonify({'fulfillmentText': f"You currently have {points} loyalty points!"})
        else:
            return jsonify({'fulfillmentText': "Sorry, we couldn't find your rewards info."})

    elif intent == 'order.complete':
        if 'cId' not in session:
            return jsonify({'fulfillmentText': "You're not logged in. Please log in first."})

        latest_order = get_latest_order(session['cId'])
        if latest_order and 'orderId' in latest_order:
            order_id = latest_order['orderId']
            session['last_order_id'] = order_id
            return jsonify({'fulfillmentText': f"Thanks for your order! 🍕 Your Order ID is {order_id}. Now, sit back and wait for the magic!"})
        else:
            return jsonify({'fulfillmentText': "We couldn't find your order in our system. Please try again or place a new order."})

    # Handle food item logging
    food_items = parameters.get('food-item', [])
    quantities = parameters.get('number', [])

    if not food_items:
        return jsonify({'fulfillmentText': "I didn't catch any items to add."}), 400

    conn = g.db_connection
    if not conn:
        return jsonify({'fulfillmentText': "Database error occurred."}), 500

    try:
        with conn.cursor() as cursor:
            for i, food in enumerate(food_items):
                qty = int(quantities[i]) if i < len(quantities) else 1
                item_str = f"{qty} x {food}"
                cursor.execute(
                    "INSERT INTO chatbot_logs (username, item) VALUES (%s, %s)",
                    (username, item_str)
                )
            conn.commit()

        item_summary = ', '.join([f"{int(quantities[i]) if i < len(quantities) else 1} x {food}" for i, food in enumerate(food_items)])
        return jsonify({'fulfillmentText': f"Got it, {username}! I've added: {item_summary} to your order. 🍕\nWould you like to order anything else? Type 'done' if you're finished, or tell me your next item and quantity."})
    except Exception as e:
        return jsonify({'fulfillmentText': f"Oops! Error: {str(e)}"}), 500

# Helper functions
def get_latest_order(cId):
    conn = g.db_connection
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT * FROM orders 
            WHERE cId = %s 
            ORDER BY orderTime DESC LIMIT 1
        """, (cId,))
        return cursor.fetchone()

def get_user_points(cId):
    conn = g.db_connection
    with conn.cursor() as cursor:
        cursor.execute("SELECT points FROM rewards WHERE cId = %s", (cId,))
        result = cursor.fetchone()
        return result['points'] if result else None

if __name__ == '__main__':
    app.run(debug=True)
