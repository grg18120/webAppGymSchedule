from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from website import db
from flask_login import login_required, login_user, logout_user, current_user
from random import randint
import calendar
import datetime
from .models import User #, ScheduleDate #, SingUpCode
from .utils.security import sanitize_str_input
from website.utils.datetime_utils import string_to_datetime


auth = Blueprint('auth', __name__)

@auth.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = sanitize_str_input(request.form.get('email'))
        password = sanitize_str_input(request.form.get('password'))

        if request.form.get('password') != password :
            flash('Password ', category='error')
        if request.form.get('email') != email :
            flash('Not Valid Email', category='error')
        
        print(request.form.get('password') == password)

        user = User.query.filter_by(email=email).first()
        if user:
            if check_password_hash(user.password, password):
                flash('Logged in successfully!', category='success')
                login_user(user, remember=True)
                return redirect(url_for('app.home'))
            else:
                flash('Incorrect password, try again.', category='error')
        else:
            flash('Email does not exist.', category='error')

    return render_template("login.html", user=current_user)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/sign-up', methods=['GET', 'POST'])
def sign_up():
    if request.method == 'POST':
        email = request.form.get('email')
        name_first = request.form.get('name_first')
        name_last = request.form.get('name_last')
        passwd = request.form.get('passwd')
        passwd_conf = request.form.get('passwd_conf')
        date_birth = string_to_datetime(date_string= request.form.get('date_birth'))
        address = request.form.get('address')

        if (str(passwd) ==  str(passwd_conf)):
            flash("Passwords do not matching", category='error')
        elif (len(email)<5 or "@" not in email):
            flash("Email not Valid", category='error')
        else:
            new_user = User(
                email=email,
                name_first=name_first, 
                name_last=name_last,
                password=generate_password_hash(password=passwd),
                date_birth=date_birth,
                address=address
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user, remember=True)
            flash("Account created", category='success')
            return redirect(url_for('app.home'))

    return render_template("sign_up.html", user=current_user)




# @auth.route('/sign-up-code', methods=['GET', 'POST'])
# def sing_up_code():

#     def deleteCode():
#         print("delete func")

#     sign_up_code_list = SingUpCode.query.all()
#     if request.method == "POST":
#         new_suc = SingUpCode(code = str(randint(10000000, 100000000)))
#         while new_suc.code in [code.code for code in sign_up_code_list]:
#             new_suc = SingUpCode(code = str(randint(10000000, 100000000)))
#         db.session.add(new_suc)
#         db.session.commit()

#     return render_template("sign-up-code.html", user=current_user, sign_up_code_list = sign_up_code_list, deleteCode=deleteCode)
    
# @auth.route('/user-info', methods=['GET', 'POST'])
# def user_info():
#     if request.method == 'POST':
#         email = request.form.get('email')
#         name_first = request.form.get('name_first')
#         existing_user = User.query.filter(User.email == email, User.id != current_user.id).first()
#         print(existing_user)

#         if email:
#             existing_user = User.query.filter(User.email == email, User.id != current_user.id).first()
#             if existing_user:
#                 flash(f"Email '{email}' is already in use!", "error")
#         try:
#             if (current_user.name_first == name_first and email == current_user.email):
#                 flash("No Change", category='error')
#             else:
#                 current_user.name_first =  name_first
#                 current_user.email = email
#                 db.session.commit()
#                 flash(f"User {current_user.name_first} updated successfully!", "success")
#         except Exception as e:
#                 db.session.rollback()
#                 flash(f"Error updating user: {e}", "danger")

#     return render_template("user-info.html", user=current_user)

# @auth.route('/schedule', methods=['GET'])
# def schedule():
    
#     month = request.args.get('month', type=int)
#     year = request.args.get('year', type=int)
#     datetime_now = datetime.datetime.now()


#     query = ScheduleDate.query
#     if month and year:
#         query = query.filter(
#             db.extract('month', ScheduleDate.date) == month,
#             db.extract('year', ScheduleDate.date) == year
#         )
#     else:        
#         query = query.filter(
#             db.extract('month', ScheduleDate.date) == datetime_now.month,
#             db.extract('year', ScheduleDate.date) == datetime_now.year
#         )


#     stored_date_list = query.order_by(ScheduleDate.date).all()

#     return render_template(
#         "schedule.html",
#         user=current_user,
#         date_list=stored_date_list,
#         current_date=datetime_now,
#         selected_month=month,
#         selected_year=year
#     )



# @auth.route('/schedule/toggle_day', methods=['POST'])
# def toggle_schedule_day():
#     date_id = int(request.form.get('schedule_date_id'))

#     date_choosed = ScheduleDate.query.filter_by(id=date_id).first()

#     if not date_choosed:
#         return jsonify(success=False, message="Date not found"), 404

#     date_choosed.date_bookable = not date_choosed.date_bookable
#     db.session.commit()

#     return jsonify(success=True, status="active" if date_choosed.date_bookable else "inactive")

# @auth.route('/schedule/toggle_all_days', methods=['GET', 'POST'])
# def toggle_all_days():
#     month = request.args.get('month', type=int)
#     year = request.args.get('year', type=int)

#     print(month, year)

#     if not month or not year:
#         return jsonify({"success": False, "message": "Missing month or year."})

#     query = ScheduleDate.query
#     query = query.filter(
#         db.extract('month', ScheduleDate.date) == month,
#         db.extract('year', ScheduleDate.date) == year
#     )
#     days = query.order_by(ScheduleDate.date).all()

#     for day in days:
#         day.date_bookable = not day.date_bookable

#     db.session.commit()

#     return jsonify({
#         "success": True,
#     })

# @auth.route('/schedule/activate_all_days', methods=['GET', 'POST'])
# def activate_all_days():
#     month = request.args.get('month', type=int)
#     year = request.args.get('year', type=int)

#     print("active")

#     if not month or not year:
#         return jsonify({"success": False, "message": "Missing month or year."})
    
#     query = ScheduleDate.query
#     query = query.filter(
#         db.extract('month', ScheduleDate.date) == month,
#         db.extract('year', ScheduleDate.date) == year
#     )
#     days = query.order_by(ScheduleDate.date).all()

#     for day in days:
#         day.date_bookable = 1

#     db.session.commit()

#     return jsonify({
#         "success": True,
#     })


# @auth.route('/schedule/inactivate_all_days', methods=['GET', 'POST'])
# def inactivate_all_days():
#     month = request.args.get('month', type=int)
#     year = request.args.get('year', type=int)

#     if not month or not year:
#         return jsonify({"success": False, "message": "Missing month or year."})
    
#     query = ScheduleDate.query
#     query = query.filter(
#         db.extract('month', ScheduleDate.date) == month,
#         db.extract('year', ScheduleDate.date) == year
#     )
#     days = query.order_by(ScheduleDate.date).all()

#     for day in days:
#         day.date_bookable = 0

#     db.session.commit()

#     return jsonify({
#         "success": True,
#     })


# @auth.route('/users', methods=['GET', 'POST'])
# def users():
#     users_list = User.query.all()
#     return render_template("users.html", user=current_user, users_list=users_list)

# @auth.route('/get_user', methods=['GET', 'POST'])
# def get_user():
#     users_list = User.query.all()
#     user_id = request.form.get('user_id')
#     user = next((u for u in users_list if str(u.id) == user_id), None)
#     if user:
#         return jsonify({
#             "id": user.id,
#             "name_last": user.name_last,
#             "name_first": user.name_first,
#             "email": user.email,
#             "date_created": user.date_created
#         })
#     else:
#         return jsonify({"error": "User not found"}), 404

# @auth.route('/edit_user', methods=['POST'])
# def edit_user():
#     users_list = User.query.all()
#     user_id = request.form.get('user_id')
#     new_last = request.form.get('name_last')
#     new_first = request.form.get('name_first')
#     new_email = request.form.get('email')
#     user = next((u for u in users_list if str(u.id) == user_id), None)
#     if user:
#         user.name_last = new_last
#         user.name_first = new_first
#         user.email = new_email
#         db.session.add(user)
#         db.session.commit()
#         return jsonify({"success": True})
#     else:
#         return jsonify({"error": "User not found"}), 404

# @auth.route('/status_change_user', methods=['POST'])
# def delete_user():
#     users_list = User.query.all()
#     user_id = request.form.get('user_id')
#     user = next((u for u in users_list if str(u.id) == user_id), None)
#     if user.disabled:
#         user.disabled = False
#     else:
#         user.disabled = True
#     db.session.add(user)
#     db.session.commit()
#     return jsonify({"success": True})

# @auth.route('/reset_password', methods=['POST'])
# def reset_password():
#     user_id = request.form.get('user_id')
#     users_list = User.query.all()
#     user = next((u for u in users_list if str(u.id) == user_id), None)

#     newPassword = request.form.get('newPassword')
#     confirmPassword = request.form.get('confirmPassword')

#     user.password = generate_password_hash(password=newPassword)
#     db.session.add(user)
#     db.session.commit()

#     print(newPassword, confirmPassword)
#     return jsonify({"message": f"Password reset successfully for User ID: {user_id}"})

@auth.route('/contact')
def contact():
    return redirect(url_for('app.home'))

@auth.route('/about')
def about():
    return redirect(url_for('app.home'))

@auth.route('/tmp')
def tmp():
    return render_template("tmp.html", text_var="Hello Var", boolean_var=True, user=current_user)


