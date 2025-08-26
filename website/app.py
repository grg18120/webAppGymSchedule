from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from website import db
from flask_login import login_required, login_user, logout_user, current_user
import sqlite3
from random import randint
import calendar
import datetime
from sqlalchemy import extract


from .models import User, ScheduleTrainning
from website.utils import security, datetime_utils



app = Blueprint('app', __name__)

# ------------------------------------ home.html ------------------------------------
@app.route('/')
# @login_required
def home():
    return render_template("home.html", user=current_user)

# ------------------------------------ users.html ------------------------------------
@app.route('/users', methods=['GET', 'POST'])
@login_required
def users():
    users_list = User.query.all()
    return render_template("users.html", user=current_user, users_list=users_list)

@app.route('/get_user', methods=['GET', 'POST'])
@login_required
def get_user():
    users_list = User.query.all()
    user_id = request.form.get('user_id')
    user = next((u for u in users_list if str(u.id) == user_id), None)
    if user:
        if user.date_birth is None :
            user_date_birth = None
        else:
            user_date_birth = user.date_birth.strftime("%m-%d-%Y")
        
        return jsonify({
            "id": user.id,
            "name_last": user.name_last,
            "name_first": user.name_first,
            "email": user.email,
            "date_created": user.date_created,
            "date_birth": user_date_birth,
            "address": user.address
        })
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/edit_user', methods=['POST'])
@login_required
def edit_user():

    def datetime_string_match_format(date_string: str, date_format: str = "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(date_string, date_format)
        except ValueError:
            return None
    
    users_list = User.query.all()
    user_id = request.form.get('user_id')
    new_last = request.form.get('name_last')
    new_first = request.form.get('name_first')
    new_email = request.form.get('email')
    new_date_birth = request.form.get('date_birth')
    new_address = request.form.get('address')
    user = next((u for u in users_list if str(u.id) == user_id), None)
    if user:
        user.name_last = new_last
        user.name_first = new_first
        user.email = new_email
        user.date_birth = datetime_string_match_format(new_date_birth)
        user.address = new_address
        db.session.add(user)
        db.session.commit()
        return jsonify({"success": True})
    else:
        return jsonify({"error": "User not found"}), 404

@app.route('/status_change_user', methods=['POST'])
@login_required
def delete_user():
    users_list = User.query.all()
    user_id = request.form.get('user_id')
    user = next((u for u in users_list if str(u.id) == user_id), None)
    if user.status == 1:
        user.status = 0
    else:
        user.status = 1
    db.session.add(user)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/reset_password', methods=['POST'])
@login_required
def reset_password():
    user_id = request.form.get('user_id')
    users_list = User.query.all()
    user = next((u for u in users_list if str(u.id) == user_id), None)

    newPassword = request.form.get('newPassword')
    confirmPassword = request.form.get('confirmPassword')

    user.password = generate_password_hash(password=newPassword)
    db.session.add(user)
    db.session.commit()

    return jsonify({"message": f"Password reset successfully for User ID: {user_id}"})



@app.route('/trainers-book', methods=['GET', 'POST'])
@login_required
def trainers_book():
    current_date = datetime.datetime.now()

    if request.method == "POST":
        selected_month = int(request.form.get("month", current_date.month))
        selected_year = int(request.form.get("year", current_date.year))
    else:
        selected_month = current_date.month
        selected_year = current_date.year


    dates = datetime_utils.get_days_in_month(selected_year, selected_month)

    scheduled_trainning_query_list = ScheduleTrainning.query.filter(
        extract('month', ScheduleTrainning.datetime_start) == selected_month,
        extract('year', ScheduleTrainning.datetime_start) == selected_year
    ).order_by(
        ScheduleTrainning.datetime_start  # or just ScheduleTrainning.datetime_start
    ).all()
    trainers_dates_scheduled = set([datetime_utils.datetime_zero_time(s.datetime_start) for s in scheduled_trainning_query_list])
    users_dates_scheduled = set([datetime_utils.datetime_zero_time(s.datetime_start) for s in scheduled_trainning_query_list if s.user_id is not None])



    return render_template("trainers-book.html",
                           user=current_user,
                           selected_month=selected_month,
                           selected_year=selected_year,
                           current_date=current_date,
                           days=dates,
                           trainers_dates_scheduled = trainers_dates_scheduled,
                           users_dates_scheduled = users_dates_scheduled,
                           now=current_date
                           )
           


@login_required
@app.route('/trainers-book-select-date', methods=['GET', 'POST'])
def trainers_book_select_date():
    year = request.form.get('year')
    month = request.form.get('month')
    day = request.form.get('day')
    
    print(f"Selected date: {year}-{month}-{day}")

    schedule_training_list = ScheduleTrainning.query.filter(
        extract('year', ScheduleTrainning.datetime_start) == year,
        extract('month', ScheduleTrainning.datetime_start) == month,
        extract('day', ScheduleTrainning.datetime_start) == day
    ).all()


    dts = [(x.datetime_start, x.datetime_end) for x in schedule_training_list]
    print(dts)
    # start_date = datetime.datetime(
    #     year=int(year),
    #     month=int(month),
    #     day=int(day),   # <-- make sure day is int too
    #     hour=0,
    #     minute=0,
    #     second=0
    # )
    # print(start_date)
    


    return render_template("trainers-book-select-date.html",
                           user=current_user,
                           year = year,
                           month = month,
                           day = day,
                           schedule_trainning_list = schedule_training_list
                           )