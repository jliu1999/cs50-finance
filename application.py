import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

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

# create table history for storing transactions
db.execute("CREATE TABLE IF NOT EXISTS history (uid INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL, id INT, symbol TEXT, name TEXT, shares INT, price NUMERIC, status TEXT, date_time TEXT, FOREIGN KEY(id) REFERENCES users(id))")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # check how much CASH the user has
    cash = db.execute("SELECT cash FROM users WHERE id=:id", id=session["user_id"])

    # search user's current stocks and create a list of dictionary "portfolio"
    portfolio = db.execute("SELECT symbol, name, SUM(shares) FROM history WHERE id=:id GROUP BY symbol", id=session["user_id"])

    # if the user has never bought any stock, "portfolio" is empty and the web page will only display the default $10,000.00
    total_value = 0 # declare a variable to store the total value of all stocks and initialize to 0
    for item in portfolio:  # loop through all stocks the user owns, each "item" is a dictionary
        quotes = lookup(item["symbol"]) # look up each stock
        item["price"] = quotes["price"] # find the current price of each stock, and add it to the dictionary "item" as a new key/value pair
        item["total"] = round(quotes["price"] * item["SUM(shares)"], 2) # calculate the current value of each stock, and add it to the dictionary "item" as a new key/value pair
        total_value += item["total"] # add up the value of each stock, when exiting the loop, will have the total value of all stocks
    return render_template("portfolio.html", portfolio=portfolio, cash=usd(cash[0]["cash"]), sum=usd(total_value+cash[0]["cash"]))

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        # in case buying request comes from INDEX page, this request.args.get function returns the symbol of the stock
        # if buying request comes from navigation bar, this request.args.get function returns nothing and will be ignored
        return render_template("buy.html", symbol=request.args.get("symbol"))

    else:
        symbol = request.form.get("symbol") # get the symbol of stock the users wants to buy from html form input
        shares = int(request.form.get("shares")) # request.form.get returns a data type str even "shares" is of type number in html form, must convert to int

        # a few validation checks
        if not symbol:
            return apology("Must input a stock's symbol", 403)
        if not lookup(symbol):
            return apology("No such stock", 403)
        if not shares:
            return apology("Must input shares of the stock you want to buy", 403)
        if shares <= 0:
            return apology("Please input a positive integer number of shares", 403)

        quotes = lookup(symbol)
        total = round((quotes["price"] * float(shares)), 2) # round to 2 digits after decimal point

        cash = db.execute("SELECT * FROM users WHERE id = :id", id=session["user_id"]) # query table users to find how much cash available
        if total > cash[0]["cash"]:
            return apology("You don't have enough money in your account", 403)

        balance = cash[0]["cash"] - total # calculate how much cash left after purchasing

        # update table users
        db.execute("UPDATE users SET cash=:cash WHERE id=:id", cash=balance, id=session["user_id"])

        # update table history
        db.execute("SELECT datetime('now', 'localtime')")
        db.execute("INSERT INTO history (id, symbol, name, shares, price, status, date_time) VALUES (:id, :symbol, :name, :shares, :price, :status, datetime('now', 'localtime'))", id=session["user_id"], symbol=symbol, name=quotes["name"], shares=shares, price=quotes["price"], status="Bought")

        # display portfolio of the user
        # search all of the user's stocks and create a list of dictionary "portfolio"
        portfolio = db.execute("SELECT symbol, name, SUM(shares) FROM history WHERE id=:id GROUP BY symbol", id=session["user_id"])
        total_value = 0
        for item in portfolio:
            quotes_port = lookup(item["symbol"])
            item["price"] = quotes_port["price"]
            item["total"] = round(quotes_port["price"] * item["SUM(shares)"], 2)
            total_value += item["total"]
        flash("Bought!") # alert buying successfully
        return render_template("portfolio.html", portfolio=portfolio, cash=usd(balance), sum=usd(total_value+balance))

@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_pass():
    """Change user's password upon request"""

    if request.method == "GET":
        return render_template("change_pass.html")

    else:
        # Ensure old password is submitted
        if not request.form.get("old_pass"):
            return apology("Must provide old password", 403)
        # Ensure new password is submitted twice
        if not request.form.get("new_pass") or not request.form.get("new_pass2"):
            return apology("Must provide new password", 403)
        # Ensure the two new passwords are the same
        if request.form.get("new_pass") != request.form.get("new_pass2"):
            return apology("New password must be the same", 403)

        # query database for the old passowrd of the user
        rows = db.execute("SELECT * FROM users WHERE id=:id", id=session["user_id"])

        # Ensure old password is correct
        if not check_password_hash(rows[0]["hash"], request.form.get("old_pass")):
            return apology("Old password is not corret", 403)

        # Update table users with new password for the user
        db.execute("UPDATE users SET hash=:hash WHERE id=:id", hash=generate_password_hash(request.form.get("new_pass")), id=session["user_id"])

        # Redirect user to home page
        return redirect("/")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # search user's transaction history and create a list of dictionary "history"
    # because the displayed price should be the price when the transaction occurred, so no need to look up current price
    history = db.execute("SELECT symbol, shares, price, status, date_time FROM history WHERE id=:id", id=session["user_id"])
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("Must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("Must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("Invalid username and/or password", 403)

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
    """Get stock quote."""

    if request.method == "GET": # load qote page
        return render_template("quote.html")

    else: # quote the stock
        symbol = request.form.get("symbol")

        # a few validation checks
        if not symbol:
            return apology("Must input a stock's symbol", 403)
        if not lookup(symbol):
            return apology("No such stock", 403)

        quotes = lookup(symbol)
        return render_template("quoted.html", quotes=quotes)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "GET":
        return render_template("register.html")
    else:
        username = request.form.get("username")

        # a few validation checks
        if not username:
            return apology("Must provide username", 403)
        # check if the username already exists
        users = db.execute("SELECT username FROM users WHERE username=:username", username=username) # query table users to see if there is already such username
        if users: # if the list of dictionary "users" is not empty, then the username is occupied
            return apology("Account name already exists", 403)

        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # a few more validation checks
        if not password or not confirmation:
            return apology("Must provide password", 403)
        if password != confirmation:
            return apology("Password must be the same", 403)

        # update table users, no need to assign cash value for this user as it's defaulted to $10,000
        db.execute("INSERT INTO users(username, hash) VALUES(:username, :hash)", username=username, hash=generate_password_hash(password))

        # query database for the id of the newly registered user
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=username)

        # Remember the id of this newly registered user for this session
        session["user_id"] = rows[0]["id"]

        flash("Registered!") # alert registering successfully
        # claim an empty list of portfolio for the new user and display initial portfolio
        return render_template("portfolio.html", portfolio=[], cash="$10,000.00", sum="$10,000.00")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # search user's available stocks and create a list of dictionary "stocks"
    stocks = db.execute("SELECT symbol FROM history WHERE id = :id GROUP BY symbol", id=session["user_id"])

    # retrieve all values of "symbol" in the list of dictionary "stocks" and create a new list "list_of_symbol"
    # this list is more convenient for sell.html to display available stocks for selling, and also convenient for the validation check
    list_of_symbol = [stock["symbol"] for stock in stocks]

    if request.method == "GET":
        # in case selling request comes from INDEX page, this request.args.get returns the symbol of the stock
        if request.args.get("symbol"):
            return render_template("sell.html", symbol=request.args.get("symbol"))

        # if selling request comes from navigation bar, parse list_of_symbol to sell.html
        else:
            return render_template("sell.html", stocks=list_of_symbol)

    else:
        symbol = request.form.get("symbol")
        shares = int(request.form.get("shares")) # reuest.form.get returns a str, must convert to int

        # a few validation checks on symbol
        if not symbol:
            return apology("Must select a stock", 403)
        if not symbol in list_of_symbol:
            return apology("You don't have such stock", 403)
        # search all of user's stocks of "symbol" and sum all the shares and create a list of dictionary "sum_of_shares"
        sum_of_shares = db.execute("SELECT SUM(shares) FROM history WHERE id = :id AND symbol = :symbol", id=session["user_id"], symbol=symbol)
        if sum_of_shares[0]["SUM(shares)"] == 0:
            return apology("You don't have any share of this stock", 403)

        # a few more validation checks on shares
        if not shares:
            return apology("Must input shares of the stock you want to sell", 403)
        if shares <= 0:
            return apology("Please input a positive integer number of shares", 403)
        if shares > sum_of_shares[0]["SUM(shares)"]:
            return apology("You don't have that many shares", 403)

        quotes = lookup(symbol)
        total = round((quotes["price"] * float(shares)), 2)
        cash = db.execute("SELECT cash FROM users WHERE id =:id", id=session["user_id"]) # query user's previous cash amount
        balance = cash[0]["cash"] + total

        # update table users
        db.execute("UPDATE users SET cash=:cash WHERE id=:id", cash=balance, id=session["user_id"])

        # update table history
        db.execute("SELECT datetime('now', 'localtime')")
        # note when selling, shares should be negative
        db.execute("INSERT INTO history (id, symbol, name, shares, price, status, date_time) VALUES(:id, :symbol, :name, :shares, :price, :status, datetime('now', 'localtime'))", id=session["user_id"], symbol=symbol, name=quotes["name"], shares=-shares, price=quotes["price"], status="Sold")

        # display portfolio of the user
        # search all of the user's stocks and create a list of dictionary "portfolio"
        portfolio = db.execute("SELECT symbol, name, SUM(shares) FROM history WHERE id=:id GROUP BY symbol", id=session["user_id"])
        total_value = 0
        for item in portfolio:
            quotes_port = lookup(item["symbol"])
            item["price"] = quotes_port["price"]
            item["total"] = round(quotes_port["price"] * item["SUM(shares)"], 2)
            total_value += item["total"]
        flash("Sold!") # alert selling successfully
        return render_template("portfolio.html", portfolio=portfolio, cash=usd(balance), sum=usd(total_value+balance))

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
