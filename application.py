import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    user_data = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session['user_id'])
    stock_data = db.execute("SELECT * FROM :username", username = user_data[0]['username'])
    my_price_list = {}
    my_price_total = {}

    for data in stock_data:
        my_price_list[data['Symbol']] = lookup(data['Symbol'])['price']

    for data in stock_data:
        my_price_total[data['Symbol']] = lookup(data['Symbol'])['price'] * data['Shares']

    return render_template('index.html', stock_data = stock_data, user_cash = user_data[0]['cash'], my_price_list = my_price_list, my_price_total = sum(my_price_total.values()))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == 'POST':
        symbol = request.form.get('symbol').upper()
        if not symbol:
            return apology('Please provide a symbol')
        data = lookup(symbol)
        if not data:
            return apology('Stock symbol is invalid')

        try:
            number = int(request.form.get("shares"))
        except ValueError:
            return apology("shares must be a posative integer", 400)

        if number <= 0:
            return apology("Please provide positive number")

        user_data = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session['user_id'])
        total_price = float(data['price']) * number

        if total_price > user_data[0]['cash']:
            return apology('You dont have sufficient cash')
        else:
            my_row = db.execute("SELECT * FROM :username WHERE Symbol = :symbol", username = user_data[0]['username'], symbol = data['symbol'])
            if not my_row:
                db.execute("INSERT INTO :username (Symbol, Name, Shares) VALUES (:symbol, :name, :shares)", username = user_data[0]['username'], symbol = data['symbol'], name = data['name'], shares = number)
            else:
                db.execute("UPDATE :username SET Shares = Shares + :shares WHERE id = :share_id", username = user_data[0]['username'], shares = number, share_id = my_row[0]['id'])
            db.execute("UPDATE users SET cash = :value WHERE id = :user_id",value = (user_data[0]['cash'] - total_price), user_id = session['user_id'])
            db.execute("INSERT INTO :history (Symbol, Shares, Price, Transacted) VALUES (:symbol, :shares, :price, :datetime)", history = user_data[0]['username'] + '_history', symbol = data['symbol'], shares = number, price = float(data['price']), datetime = datetime.now())
        return redirect("/")


    else:
        return render_template('buy.html')


@app.route("/history")
@login_required
def history():
    user_data = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session['user_id'])
    my_history = db.execute("SELECT * FROM :history", history = user_data[0]['username'] + '_history')
    if not my_history:
        return apology("You have not done any transactions")
    else:
        return render_template("history.html", my_history = my_history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    if request.method == 'GET':
        return render_template("quote.html")
    else:
        symbol = request.form.get('symbol').upper()
        if not symbol:
            return apology('please provide a symbol')
        data = lookup(symbol)
        if not data:
            return apology('please provide a valid symbol')
        return render_template('quoted.html', data = data)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == 'POST':
        username = request.form.get("username")
        password = request.form.get("password")
        password_2 = request.form.get("confirmation")

        if not username:
            return apology("please provide a username")
        if not (password and password_2):
            return apology("please provide proper password")

        all_usernames = db.execute("SELECT id FROM users WHERE username = :username", username = username)
        if len(all_usernames) != 0:
            return apology("Sorry this username already exists")
        if password != password_2:
            return apology("password does not match")
        passw = generate_password_hash(password, method = 'plain', salt_length = 8)
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)", username = username, password = passw)
        db.execute("CREATE TABLE :username (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, Symbol TEXT NOT NULL, Name TEXT, Shares INTEGER)", username = username)
        db.execute("CREATE TABLE :history (id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, Symbol TEXT NOT NULL, Shares INTEGER NOT NULL, Price NUMERIC NOT NULL, Transacted DATETIME NOT NULL)", history = username + '_history')
        current_user = db.execute("SELECT * FROM users WHERE username = :username", username = username)
        session['user_id'] = current_user[0]['id']
        return redirect('/')
    else:
        return render_template("register.html")
    return redirect('/')


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == 'GET':
        user_data = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session['user_id'])
        my_row = db.execute("SELECT * FROM :username", username = user_data[0]['username'])
        if not my_row:
            return apology("You dont have any stocks to sell")
        return render_template("sell.html", my_row = my_row)

    else:
        symbol = request.form.get('symbol')
        number = request.form.get('shares')
        if not symbol or not number:
            return apology('Please provide symbol/number of stock')
        if int(number) <= 0:
            return apology('Please provide a positive number')

        user_data = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session['user_id'])
        my_row = db.execute("SELECT * FROM :username WHERE Symbol = :symbol", username = user_data[0]['username'], symbol = symbol)

        if int(number) > my_row[0]['Shares']:
            return apology("You dont have this amount of stocks")

        total_price = lookup(symbol)['price'] * int(number)
        db.execute('UPDATE :username SET Shares = Shares - :number WHERE Symbol = :symbol', username = user_data[0]['username'], number = int(number), symbol = symbol)
        db.execute('UPDATE users SET cash = cash + :total_price WHERE id = :user_id', total_price = total_price, user_id = session['user_id'])
        db.execute("INSERT INTO :history (Symbol, Shares, Price, Transacted) VALUES (:symbol, :shares, :price, :datetime)", history = user_data[0]['username'] + '_history', symbol = symbol, shares = -int(number), price = lookup(symbol)['price'], datetime = datetime.now())
        return redirect("/")

@app.route("/pass", methods=["GET", "POST"])
@login_required
def password():
    if request.method == 'POST':
        user_data = db.execute("SELECT * FROM users WHERE id = :user_id", user_id = session['user_id'])
        current_1 = user_data[0]['hash']
        current_2 = request.form.get('current')
        if not current_2:
            return apology("Provide current password")
        if current_1 != generate_password_hash(current_2, method = 'plain', salt_length = 8):
            return apology("Wrong current password")
        password_1 = generate_password_hash(request.form.get("password_1"), method = 'plain', salt_length = 8)
        password_2 = generate_password_hash(request.form.get('password_2'), method = 'plain', salt_length = 8)

        if not password_1 or not password_2:
            return apology("Please provide new password")

        if password_1 != password_2:
            return apology("The new passwords dont match")

        db.execute("UPDATE users SET hash = :password WHERE id = :user_id", password = password_1, user_id = session['user_id'])
    else:
        return render_template("password.html")
    return redirect('/')

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
