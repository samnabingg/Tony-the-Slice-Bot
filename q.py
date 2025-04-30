from flask import Flask, render_template, request, jsonify, session, g, redirect, url_for
import pymysql
import os
from dotenv import load_dotenv
import random
import string
import secrets
from flask_wtf import CSRFProtect
from forms import LoginForm, SignupForm  # 🔥 Added SignupForm
from werkzeug.security import generate_password_hash  # 🔐 For hashing passwords
from datetime import timedelta, datetime
import logging
from werkzeug.security import check_password_hash
import json
from datetime import datetime, date



logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)


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
    
def extract_cid_from_context(contexts):
    for ctx in contexts:
        if 'user-session' in ctx.get('name', ''):
            params = ctx.get('parameters', {})
            cid = params.get('cid') or params.get('number')
            
            # 🔒 Make sure it's not a list
            if isinstance(cid, list) and len(cid) > 0:
                cid = cid[0]

            if isinstance(cid, (int, float, str)):
                try:
                    return int(cid)
                except ValueError:
                    pass
    return None

from datetime import datetime

def parse_reservation_time(raw_time):
    try:
        if "T" in raw_time:
            time_obj = datetime.fromisoformat(raw_time).time()
        else:
            time_obj = datetime.strptime(raw_time, "%H:%M:%S").time()
        return time_obj
    except ValueError:
        try:
            time_obj = datetime.strptime(raw_time, "%H:%M").time()
            return time_obj
        except Exception as e:
            print(f"[ERROR] Time parse failed: {e}")
            return None


@csrf.exempt
@app.route('/api/start-order', methods=['POST'])
def start_order():
    logging.info("POST /api/start-order hit")

    # Check for session authentication
    if 'cid' not in session:
        logging.warning("Unauthorized access attempt to /api/start-order")
        return jsonify({'message': 'Not authenticated'}), 401

    cid = session['cid']
    logging.debug(f"Session CID: {cid}")

    # Generate order ID if not already present
    if 'current_order_id' not in session:
        session['current_order_id'] = generate_unique_order_id()
        session['order_start_time'] = str(datetime.now())
        logging.info(f"New order started: orderId={session['current_order_id']}, startTime={session['order_start_time']}")
    else:
        logging.info(f"Resuming existing order: orderId={session['current_order_id']}")

    return jsonify({'orderId': session['current_order_id']}), 200

@csrf.exempt
@app.route('/api/order-summary', methods=['POST'])
def order_summary():
    logging.info("POST /api/order-summary hit")

    data = request.get_json()
    logging.debug(f"Raw request data: {data}")

    cid = data.get('cid')
    order_id = data.get('order_id')
    order_data = data.get('orderData', {})
    selected_items = order_data.get('selectedItems', [])

    if not cid or not order_id:
        logging.warning("Missing cid or order_id in request")
        return jsonify({"message": "Missing user or order info"}), 401

    if not selected_items:
        logging.warning("Order summary attempted with no items selected")
        return jsonify({"message": "No items selected"}), 400

    conn = g.db_connection
    if not conn:
        logging.error("Database connection not available in /api/order-summary")
        return jsonify({"message": "Database connection failed"}), 500
    try:
        with conn.cursor() as cursor:
            # Calculate total order value from all selected items
            total = sum(float(item['price']) * int(item['quantity']) for item in selected_items)

            for item in selected_items:
                if not all(k in item for k in ['itemId', 'itemName', 'price', 'quantity']):
                    logging.warning(f"Skipping malformed item: {item}")
                    continue

                total_amount = float(item['price']) * int(item['quantity'])

                logging.info(
                    f"Inserting item: orderId={order_id}, cid={cid}, "
                    f"itemId={item['itemId']}, itemName={item['itemName']}, "
                    f"quantity={item['quantity']}, total={total_amount}"
                )

                cursor.execute("""INSERT INTO orders (orderId, cid, itemId, totalAmount, itemName, quantity, orderTime)
                              VALUES (%s, %s, %s, %s, %s, %s, %s)""", (
                    order_id, cid, item['itemId'], total_amount,
                    item['itemName'], item['quantity'], datetime.now()
                ))

            # If total >= 20, add 5 points
            if total >= 20:
                cursor.execute("UPDATE customers SET loyalty_points = loyalty_points + 5 WHERE cid = %s", (cid,))

            conn.commit()


        logging.info(f"Order {order_id} committed successfully for CID {cid}")
        return jsonify({"message": "Items added to your order", "orderId": order_id}), 200

    except Exception as e:
        conn.rollback()
        logging.exception("Exception during order summary processing")
        return jsonify({"message": "Error processing order", "error": str(e)}), 500


@app.route('/api/complete-order', methods=['POST'])
def complete_order():
    logging.info("POST /api/complete-order hit")

    if 'cid' not in session or 'current_order_id' not in session:
        logging.warning("Order completion failed — missing session cid or current_order_id")
        return jsonify({'message': 'No order in progress'}), 400

    cid = session['cid']
    order_id = session.pop('current_order_id')  # Remove so they can’t accidentally reuse

    logging.info(f"Order completed: orderId={order_id}, cid={cid}")
    logging.debug(f"Remaining session data after completion: {dict(session)}")

    return jsonify({'message': 'Order completed', 'orderId': order_id})



@app.route('/api/order-current', methods=['GET'])
def get_current_order():
    logging.info("GET /api/order-current hit")

    if 'cid' not in session or 'current_order_id' not in session:
        logging.warning("Attempted to fetch current order without valid session data")
        return jsonify({"message": "No active order"}), 400

    cid = session['cid']
    order_id = session['current_order_id']
    logging.debug(f"Fetching current order for cid={cid}, orderId={order_id}")

    conn = g.db_connection
    if not conn:
        logging.error("Database connection not available in /api/order-current")
        return jsonify({"message": "Database connection failed"}), 500

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT itemName, quantity, totalAmount
                FROM orders
                WHERE cid = %s AND orderId = %s
            """, (cid, order_id))
            items = cursor.fetchall()

            logging.info(f"Order retrieved: orderId={order_id}, item count={len(items)}")
            logging.debug(f"Order details: {items}")

            return jsonify({"orderId": order_id, "items": items}), 200
    except Exception as e:
        logging.exception("Error retrieving current order from database")
        return jsonify({"message": "Failed to retrieve order", "error": str(e)}), 500


@app.before_request
def before_request():
    logging.debug("Running before_request middleware...")
    g.db_connection = get_db_connection()

    if g.db_connection:
        logging.debug("Database connection established successfully.")
    else:
        logging.error("Failed to establish database connection in before_request.")
        return jsonify({"message": "Failed to connect to database"}), 500

@app.teardown_request
def teardown_request(exception):
    try:
        if hasattr(g, 'db_connection') and g.db_connection:
            g.db_connection.close()
            app.logger.debug("Database connection closed successfully at teardown.")
    except Exception as e:
        app.logger.warning(f"Error during teardown: {e}")

    if exception:
        app.logger.error(f"Exception during request teardown: {str(exception)}")



@app.route('/', methods=['GET'])
def home():
    logging.info("GET / (login page) accessed")
    form = LoginForm()
    return render_template('login.html', form=form)



@app.route('/web')
def web():
    logging.info("GET /web (dashboard) accessed")

    if 'cid' not in session:
        logging.warning("Unauthorized access attempt to /web — redirecting to login")
        return redirect('/')

    cid = session['cid']
    logging.debug(f"Session CID: {cid}")

    conn = g.db_connection
    username = "Guest"

    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT username FROM customers WHERE cid = %s", (cid,))
                result = cursor.fetchone()
                if result and 'username' in result:
                    username = result['username']
                    logging.info(f"User dashboard accessed by: {username} (CID: {cid})")
                else:
                    logging.warning(f"No username found in DB for CID: {cid}")
        except Exception as e:
            logging.error(f"Error fetching username for CID {cid}: {str(e)}")
    else:
        logging.error("Database connection missing while rendering /web")

    return render_template("web.html", username=username, cid=cid)


@app.route('/menu')
def menu_page():
    return render_template('menu.html')

@app.route('/points')
def points():
    return render_template('points.html')

@app.route('/orders')
def orders():
    cid = session.get('cid')
    order_id = session.get('current_order_id')  # this is already set in the webhook

    if not cid or not order_id:
        logging.warning("Missing CID or Order ID for /orders page")
        return redirect('/')  # or show a message saying they must start order

    return render_template('orders.html', cid=cid, order_id=order_id)


@app.route('/timer')
def timer_page():
    return render_template('timer.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

def generate_unique_order_id():
    return ''.join(random.choices(string.digits, k=6))




@csrf.exempt
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data:
        return jsonify({'success': False, 'message': 'Invalid request'}), 400

    username = data.get('username', '').strip()
    password = data.get('password', '').strip()

    if not username or not password:
        return jsonify({'success': False, 'message': 'All fields are required'}), 400

    conn = g.db_connection
    if not conn:
        return jsonify({'success': False, 'message': 'Database error'}), 500

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT cid, password_hash FROM customers WHERE username = %s", (username,))
            customer = cursor.fetchone()

            if customer and check_password_hash(customer['password_hash'], password):
                session['cid'] = customer['cid']
                return jsonify({
    'success': True,
    'redirect': url_for('web'),
    'message': 'Login successful',
    'cid': customer['cid']  # ✅ Send cid to frontend
})

            else:
                return jsonify({'success': False, 'message': 'Invalid username or password'}), 401
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500
    
@app.route('/get_rewards', methods=['GET'])
def get_rewards():
    if 'cid' not in session:
        logging.warning("Attempt to access /get_rewards without login")
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401

    cid = session['cid']
    points = get_user_points(cid)

    if points is not None:
        logging.info(f"Returned {points} loyalty points for CID {cid}")
        return jsonify({'success': True, 'points': points})
    else:
        logging.warning(f"No loyalty data found for CID {cid}")
        return jsonify({'success': False, 'message': 'No rewards data found'}), 404
    
@app.route('/api/loyalty-points')
def get_loyalty_points():
    if 'cid' not in session:
        return jsonify({'points': 0})

    cid = session['cid']
    conn = g.db_connection

    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT loyalty_points FROM customers WHERE cid = %s", (cid,))
            result = cursor.fetchone()
            points = result['loyalty_points'] if result else 0
            return jsonify({'points': points})
    except Exception as e:
        logging.error(f"Error fetching loyalty points: {e}")
        return jsonify({'points': 0})



@app.route('/api/redeem_reward', methods=['POST'])
def redeem_reward():
    if 'cid' not in session:
        return jsonify({'message': 'Not authenticated'}), 401

    cid = session['cid']
    redeem_amount = request.json.get('points', 5)  # Default to 5 points per redemption

    if not isinstance(redeem_amount, int) or redeem_amount <= 0:
        return jsonify({'message': 'Invalid points value'}), 400

    conn = g.db_connection
    try:
        with conn.cursor() as cursor:
            # Get current points
            cursor.execute("SELECT loyalty_points FROM customers WHERE cid = %s", (cid,))
            result = cursor.fetchone()

            if not result:
                return jsonify({'message': 'User not found'}), 404

            current_points = result['loyalty_points']

            if current_points < redeem_amount:
                return jsonify({'success': False, 'message': f'You need at least {redeem_amount} points to redeem this reward.'}), 400

            # Deduct points
            cursor.execute(
                "UPDATE customers SET loyalty_points = loyalty_points - %s WHERE cid = %s",
                (redeem_amount, cid)
            )
            conn.commit()

        return jsonify({'success': True, 'message': f'{redeem_amount} points redeemed successfully!'})

    except Exception as e:
        logging.error(f"Error redeeming points: {e}")
        return jsonify({'success': False, 'message': 'Failed to redeem points'}), 500



@csrf.exempt
@app.route('/webhook', methods=['POST'])
def webhook():
    conn = g.db_connection

    data = request.get_json(silent=True, force=True)
    if not data:
        logging.warning("No data received in webhook.")
        return jsonify({"fulfillmentText": "Something went wrong. Please try again."})

    logging.info("Full webhook payload:\n" + json.dumps(data, indent=2))
    logging.info(f"Webhook received: {data}")

    intent = data.get('queryResult', {}).get('intent', {}).get('displayName', '')
    parameters = data.get('queryResult', {}).get('parameters', {})
    output_contexts = data.get('queryResult', {}).get('outputContexts', [])

    cid = session.get('cid')  # default to session cid
    if not cid:
        cid = (
    session.get('cid') or
    extract_cid_from_context(output_contexts) or
    data.get('originalDetectIntentRequest', {}).get('payload', {}).get('userId')
)

    username = "Guest"


    # Only run DB lookup if cid is now set
    if cid:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT username FROM customers WHERE cid = %s", (cid,))
                result = cursor.fetchone()
                if result and 'username' in result:
                    username = result['username']
                    logging.info(f"Webhook triggered by user: {username} (CID: {cid})")
        except Exception as e:
            logging.error(f"DB error fetching username for CID {cid}: {e}")
    else:
        logging.error("No CID available — skipping user-specific personalization.")


    # ---------- INTENT: DEFAULT WELCOME ----------
    if intent == "Default Welcome Intent":
        session_path = data.get("session", "")
        response = {
    "fulfillmentText": f"Welcome back, {username}! 🍕 What would you like to do today? (Hint: Place an order, track order, add/remove order, Table Reservation, Contact Info)",
    "outputContexts": [
        {
            "name": f"{session_path}/contexts/user-session",
            "lifespanCount": 50,
            "parameters": {
                "cid": cid if cid else ""  # better than nothing
            }
        }
    ]
}
        return jsonify(response)


    # ---------- INTENT: TRACK ORDER ----------
    if intent == 'track.order- context: Ongoing-tracking':
        order_id = None

        # Get the orderId directly from the outputContexts
        for ctx in output_contexts:
            if 'ongoing-tracking' in ctx.get('name', ''):
                order_id_param = ctx.get('parameters', {}).get('number', [])
                if isinstance(order_id_param, list) and order_id_param:
                    order_id = int(order_id_param[0])
                elif isinstance(order_id_param, (int, float)):
                    order_id = int(order_id_param)

        if not order_id:
            return jsonify({'fulfillmentText': "I couldn’t find any order ID to track."})

        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT orderTime FROM orders WHERE orderId = %s ORDER BY orderTime DESC LIMIT 1
            """, (order_id,))
            row = cursor.fetchone()

            if not row:
                return jsonify({'fulfillmentText': "I couldn’t find any recent orders."})

            order_time = row['orderTime']
            elapsed = (datetime.now() - order_time).total_seconds() / 60
            elapsed = round(elapsed, 1)
            if elapsed < 5:
                status = f"Your order is in the queue. It has only been {elapsed} minutes since you ordered"
            elif elapsed < 10:
                status = f"Your order is being prepared! It has been {elapsed} minutes since you ordered"
            elif elapsed < 15:
                status = f"Your order is heading to the counter. It has been {elapsed} minutes since you ordered"
            else:
                status = f"Your order is ready! Please pick it up. It has been {elapsed} minutes since you ordered"

        return jsonify({'fulfillmentText': status})


    # ---------- INTENT: LOYALTY REWARDS ----------
    elif intent == 'loyalty.rewards':
        points = get_user_points(cid)
        if points is not None:
            return jsonify({'fulfillmentText': f"You have {points} loyalty points!"})
        else:
            return jsonify({'fulfillmentText': "We couldn't find your rewards info."})
        

        # ---------- INTENT: ORDER ADD ---------- 
    elif intent == 'order.add- context: Ongoing-order':
        food_items = parameters.get('food-item', [])
        quantities = parameters.get('number', [])

        # 🛠 Ensure quantities is a list
        if isinstance(quantities, (int, float)):
            quantities = [quantities]


        if not food_items or not quantities or len(food_items) != len(quantities):
            return jsonify({'fulfillmentText': "Hmm, I couldn't understand the items. Can you try again with clear quantities?"})

        if 'current_order_id' not in session:
            session['current_order_id'] = generate_unique_order_id()
            logging.info(f"New order started from webhook: {session['current_order_id']}")

        order_id = session['current_order_id']
        mapping = {
            "Cheesy Pepperoni Pizza": "Pepperoni Pizza",
            "Cheesy Mushroom Pizza": "Mushroom Pizza",
            "Garlic Bread": "Garlic Bread",
            "Classic Pizza": "Classic Pizza",
            "Fries": "Fries",
            "Chicken Wings": "Wings",
            "Pop": "Soda"
        }

        try:
            with conn.cursor() as cursor:
                for name, qty in zip(food_items, quantities):
                    matched_name = mapping.get(name, name)  # fallback to original if no mapping
                    cursor.execute("SELECT itemId, price FROM product WHERE LOWER(itemName) = LOWER(%s)", (matched_name,))
                    product = cursor.fetchone()

                    if not product:
                        logging.warning(f"Unknown item: {name}")
                        continue

                    item_id = product['itemId']
                    price = float(product['price'])
                    total = price * int(qty)

                    cursor.execute("""
                        INSERT INTO orders (orderId, cId, itemId, totalAmount, itemName, quantity, orderTime)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (order_id, cid, item_id, total, matched_name, qty, datetime.now()))
                    # Calculate total order value (example)
                    total = price * int(qty)

                    # If total >= 20, add 5 points
                    if total >= 20:
                        cursor.execute("UPDATE customers SET loyalty_points = loyalty_points + 5 WHERE cid = %s", (cid,))

                conn.commit()

            return jsonify({'fulfillmentText': "Order added! Want anything else? Say 'Done' when you're finished."})
        except Exception as e:
            logging.error(f"Insert error in order.add: {e}")
            conn.rollback()
            return jsonify({'fulfillmentText': "Oops! There was a problem adding your order."})

    elif intent == "inject.cid":
        cid_text = data.get('queryResult', {}).get('queryText', '')
        if "set-cid:" in cid_text:
            try:
                cid = int(cid_text.split("set-cid:")[1].strip())
                logging.info(f"Injected CID into webhook: {cid}")
                session_path = data.get("session", "")
                return jsonify({
                    "fulfillmentText": "User context set.",
                    "outputContexts": [
                        {
                        "name": f"{session_path}/contexts/user-session",
                        "lifespanCount": 50,
                        "parameters": {
                            "cid": cid
                        }
                        }
                    ]
            })
            except:
                logging.error("Failed to parse injected CID.")
                return jsonify({"fulfillmentText": "Could not set user context."})




    
    # ---------- INTENT: ORDER COMPLETE ----------
    elif intent == 'order.complete- context: Ongoing-order':
        logging.info(f"Intent received: {intent}")

        if not cid:
            logging.error("CID not found — cannot complete order")
            return jsonify({'fulfillmentText': "Oops! We couldn’t confirm your user info."})

    # ✅ Get the latest order ID for this cid
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT orderId FROM orders WHERE cid = %s ORDER BY orderTime DESC LIMIT 1
            """, (cid,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'fulfillmentText': "No recent orders found."})
            order_id = row['orderId']

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT itemName, quantity FROM orders 
                    WHERE orderId = %s AND cid = %s
                """, (order_id, cid))
                items = cursor.fetchall()

                if not items:
                    return jsonify({'fulfillmentText': "I found your order ID, but no items were found in it."})

                # ✅ Full menu price list
                prices = {
                "Classic Pizza": 10.00,
                "Cheesy Pepperoni Pizza": 18.00,
                "Cheesy Mushroom Pizza": 16.00,
                "Garlic Bread": 3.50,
                "Fries": 3.50,
                "Soda": 2.00,
                "Wings": 8.50,
                "Pepperoni Pizza": 18.00,
                "Mushroom Pizza": 16.00  # fallback mapped names
                }

                summary_lines = []
                total = 0.0

                for item in items:
                    name = item['itemName']
                    qty = item['quantity']
                    price = prices.get(name, 0)
                    subtotal = qty * price
                    total += subtotal
                    summary_lines.append(f"{qty} x {name} (${price:.2f})")

                summary = ', '.join(summary_lines)
                response = f"{username}, this is your order summary: {summary}. 🍕 Your Order ID is {order_id}. Your total is: ${total:.2f}."

                return jsonify({'fulfillmentText': response})

        except Exception as e:
            logging.exception("Error fetching order details")
            return jsonify({'fulfillmentText': "Something went wrong getting your order summary."})




    # ---------- INTENT: TABLE RESERVATION ----------
    elif intent == "table.reservation":
        session_path = data.get("session", "")
    
        # Set context for next step
        return jsonify({
            "fulfillmentText": "Great choice! Let’s get you the best seat in the house. How many guests and what time?",
            "outputContexts": [
                {
                "name": f"{session_path}/contexts/awaiting_reservation_details",
                "lifespanCount": 5
                }
            ]
        })


    elif intent == "table.reservation.details":
        raw_time = parameters.get("time")
        num_guests = parameters.get("number")
        cid = (
            session.get('cid') or
            extract_cid_from_context(output_contexts) or
            data.get('originalDetectIntentRequest', {}).get('payload', {}).get('userId')
        )

        parsed_time = parse_reservation_time(raw_time)

        if not parsed_time or not num_guests:
            return jsonify({'fulfillmentText': "Sorry, I need both the number of guests and the time. Can you try again?"})

        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO reservations (cid, reservation_time, guests) VALUES (%s, %s, %s)",
                    (cid, parsed_time, num_guests)
                )

                conn.commit()
                logging.info(f"➡️ Reservation Params Received: time={raw_time}, guests={num_guests}")
            return jsonify({'fulfillmentText': f"✅ Table booked for {num_guests} at {parsed_time.strftime('%I:%M %p')}!"})
        except Exception as e:
            logging.error(f"Reservation DB error: {e}")
            return jsonify({'fulfillmentText': "Oops, something went wrong while saving your reservation."})
    

        
        # ---------- INTENT: ORDER REMOVE ----------
    elif intent == 'order.remove - context: Ongoing-order':
        food_items = parameters.get('food-item', [])

        quantities = parameters.get('number', [])
        if isinstance(quantities, (int, float)):
            quantities = [quantities]


        if not cid:
            return jsonify({'fulfillmentText': "Oops! We couldn’t confirm your user info."})

        if not food_items or not quantities or len(food_items) != len(quantities):
            return jsonify({'fulfillmentText': "I couldn't figure out what to remove. Can you try again?"})

        # Normalize names like in add
        mapping = {
            "Cheesy Pepperoni Pizza": "Pepperoni Pizza",
            "Cheesy Mushroom Pizza": "Mushroom Pizza",
            "Garlic Bread": "Garlic Bread",
            "Classic Pizza": "Classic Pizza",
            "Fries": "Fries"
        }

        # Get latest order ID
        with conn.cursor() as cursor:
            cursor.execute("SELECT orderId FROM orders WHERE cid = %s ORDER BY orderTime DESC LIMIT 1", (cid,))
            result = cursor.fetchone()
            if not result:
                return jsonify({'fulfillmentText': "No order found to remove from."})
            order_id = result['orderId']

            removed = []

            for name, qty in zip(food_items, quantities):
                matched_name = mapping.get(name, name)
                cursor.execute("SELECT itemId, price FROM product WHERE LOWER(itemName) = LOWER(%s)", (matched_name,))
                product = cursor.fetchone()

                if not product:
                    continue

                item_id = product['itemId']
                price = float(product['price'])

                # Check current quantity in order
                cursor.execute("""
                    SELECT quantity FROM orders 
                    WHERE cid = %s AND orderId = %s AND itemId = %s
                """, (cid, order_id, item_id))
                row = cursor.fetchone()

                if not row:
                    continue

                current_qty = row['quantity']
                remove_qty = int(qty)

                if current_qty > remove_qty:
                    new_qty = current_qty - remove_qty
                    new_total = price * new_qty
                    cursor.execute("""
                        UPDATE orders 
                        SET quantity = %s, totalAmount = %s 
                        WHERE cid = %s AND orderId = %s AND itemId = %s
                    """, (new_qty, new_total, cid, order_id, item_id))
                else:
                    cursor.execute("""
                        DELETE FROM orders 
                        WHERE cid = %s AND orderId = %s AND itemId = %s
                    """, (cid, order_id, item_id))

                removed.append(matched_name)

            conn.commit()

            if removed:
                return jsonify({'fulfillmentText': f"{', '.join(removed)} removed! Want something else?"})
            else:
                return jsonify({'fulfillmentText': "That item wasn’t in your order!"})
            
    
    elif intent == "reservation.check":
        if not cid:
            return jsonify({'fulfillmentText': "I couldn’t find your account. Please log in first."})

        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT reservation_time, guests
                    FROM reservations
                    WHERE cid = %s
                    ORDER BY reservation_time DESC
                    LIMIT 1
                """, (cid,))
                result = cursor.fetchone()

                if result:
                    reservation_time = result['reservation_time']
                    if isinstance(reservation_time, datetime):
                            res_time = reservation_time.strftime("%I:%M %p")
                    else:
                            res_time = str(reservation_time)

                    guests = result['guests']
                    return jsonify({'fulfillmentText': f"You have a reservation for {guests} people at {res_time}."})
                else:
                    return jsonify({'fulfillmentText': "You don’t have any reservations at the moment."})
        except Exception as e:
            logging.error(f"[RESERVATION CHECK ERROR] {e}")
            return jsonify({'fulfillmentText': "Something went wrong while checking your reservation."})




    # ---------- FALLBACK ----------
    return jsonify({"fulfillmentText": "Sorry, I didn't catch that. Can you say it again?"})


# Helper functions
def get_latest_order(cid):
    conn = g.db_connection
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT * FROM orders 
            WHERE cid = %s 
            ORDER BY orderTime DESC LIMIT 1
        """, (cid,))
        return cursor.fetchone()

def get_user_points(cid):
    if not cid:
        logging.warning("get_user_points called with missing CID")
        return None
    conn = g.db_connection
    with conn.cursor() as cursor:
        cursor.execute("SELECT loyalty_points FROM customers WHERE cid = %s", (cid,))

        result = cursor.fetchone()
        return result['loyalty_points'] if result else None


    

# ✅ SIGNUP ROUTE
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    form = SignupForm()
    if form.validate_on_submit():
        username = form.username.data.strip()
        email = form.email.data.strip()
        phone = form.phone.data.strip()
        password = form.password.data

        hashed_password = generate_password_hash(password)

        try:
            with g.db_connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO customers (username, email, phone_number, password_hash)
                    VALUES (%s, %s, %s, %s)
                """, (username, email, phone, hashed_password))
                g.db_connection.commit()

                # Log user in immediately after signup
                cursor.execute("SELECT cid FROM customers WHERE username = %s", (username,))
                user = cursor.fetchone()
                if user:
                    session['cid'] = user['cid']
                return redirect(url_for('web'))

        except pymysql.IntegrityError:
            return render_template('signup.html', form=form, message="Username or email already exists.")
        except Exception as e:
            return render_template('signup.html', form=form, message=f"Error: {str(e)}")

    return render_template('signup.html', form=form)

@app.route('/logout')
def logout():
    session.clear()
    logging.info("User logged out successfully.")
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.logger.setLevel(logging.DEBUG)
    logging.getLogger('werkzeug').setLevel(logging.DEBUG)
    logging.debug("🔥 Starting app with full debug logging")
    app.run(debug=True)

