from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import io
import base64
from datetime import datetime
import cv2
import numpy as np

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://root:@localhost:3306/academic_support_system'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Define your models
class User(db.Model):
    __tablename__ = 'usersss'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(100))
    name = db.Column(db.String(255))
    matric_no = db.Column(db.String(50))
    level = db.Column(db.String(50))

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    course_name = db.Column(db.String(255), nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('usersss.id'), nullable=False)

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('usersss.id'), nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('usersss.id'), nullable=False)
    appointment_time = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(255))
    feedback = db.Column(db.Text)

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('usersss.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False)
    lecturer_id = db.Column(db.Integer, db.ForeignKey('usersss.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('usersss.id'), nullable=False)
    student_name = db.Column(db.String(255))
    student_matric_no = db.Column(db.String(50))
    student_level = db.Column(db.String(50))
    reason = db.Column(db.String(255))

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('usersss.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    attendance_date = db.Column(db.Date, nullable=False)
    present = db.Column(db.Boolean, default=False)
    mark = db.Column(db.Float, default=0.0)

# Create tables
with app.app_context():
    db.create_all()

@app.route('/')
def landing_page():
    if 'user_id' in session:
        return redirect(url_for('landing_after_login'))
    return render_template('landing.html')

@app.route('/home')
def home():
    return render_template('login.html')

@app.route('/signup', methods=['POST'])
def signup():
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirm_password']
    role = request.form['role']

    if password == confirm_password:
        hashed_password = generate_password_hash(password)
        new_user = User(email=email, password=hashed_password, role=role)
        db.session.add(new_user)
        db.session.commit()
        flash("Signup successful. You can now login.")
        return redirect(url_for('home'))
    else:
        flash("Passwords do not match. Try again.")
        return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    user = User.query.filter_by(email=email).first()

    if user and check_password_hash(user.password, password):
        session['user_id'] = user.id
        session['role'] = user.role
        session['user_abbr'] = user.email[:5].upper()
        flash(f"You were successfully logged in as {session['user_abbr']}")

        if user.role == 'Student':
            return redirect(url_for('student_dashboard'))
        elif user.role == 'Lecturer':
            return redirect(url_for('lecturer_dashboard'))
        elif user.role == 'Parent':
            return redirect(url_for('parent_dashboard'))
    else:
        flash("Invalid login credentials. Please try again.")
        return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You were successfully logged out")
    return render_template('landing.html')

@app.route('/landing2')
def landing_after_login():
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        user_abbr = user.email[:5].upper() if user else ''
        return render_template('landing.html', user_abbr=user_abbr)
    else:
        return redirect(url_for('home'))

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    notifications = []
    if session['role'] == 'Lecturer':
        lecturer_id = session['user_id']
        notifications = Notification.query.join(Appointment).join(User).filter(
            Notification.lecturer_id == lecturer_id,
            Appointment.feedback == None
        ).all()
    elif session['role'] == 'Student':
        student_id = session['user_id']
        notifications = Notification.query.join(Appointment).join(User).filter(
            Notification.student_id == student_id
        ).all()

    return render_template('notifications.html', notifications=notifications)

@app.route('/send_feedback', methods=['POST'])
def send_feedback():
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))

    feedback = request.form['feedback']
    appointment_id = request.form['appointment_id']

    appointment = Appointment.query.filter_by(id=appointment_id, lecturer_id=session['user_id']).first()
    if appointment:
        appointment.feedback = feedback
        db.session.commit()

    flash("Feedback sent successfully.")
    return redirect(url_for('notifications'))

@app.route('/appointments', methods=['GET', 'POST'])
def appointments():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    lecturers = User.query.filter_by(role='Lecturer').all()

    if request.method == 'POST':
        student_id = session['user_id']
        lecturer_id = request.form['lecturer_id']
        appointment_time = request.form['appointment_time']
        reason = request.form['reason']

        lecturer = User.query.filter_by(id=lecturer_id, role='Lecturer').first()
        if not lecturer:
            flash("Selected lecturer does not exist.")
            return redirect(url_for('appointments'))

        new_appointment = Appointment(student_id=student_id, lecturer_id=lecturer_id, appointment_time=appointment_time, reason=reason)
        db.session.add(new_appointment)
        db.session.commit()

        student = User.query.get(student_id)
        if student:
            notification = Notification(
                user_id=lecturer_id,
                reason=reason,
                appointment_id=new_appointment.id,
                lecturer_id=lecturer_id,
                student_id=student_id,
                student_name=student.name,
                student_matric_no=student.matric_no,
                student_level=student.level
            )
            db.session.add(notification)
            db.session.commit()

        flash("Appointment booked successfully.")
        return redirect(url_for('appointments'))

    appointments = Appointment.query.join(User).filter_by(student_id=session['user_id']).all()

    return render_template('appoint.html', lecturers=lecturers, appointments=appointments)

@app.route('/generate_qr', methods=['GET', 'POST'])
def generate_qr():
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))

    if request.method == 'POST':
        course_id = request.form['course_id']
        course_name = request.form['course_name']
        lecturer_id = session['user_id']
        date = request.form['date']

        qr_data = f"{course_id},{course_name},{lecturer_id},{date}"
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill='black', back_color='white')

        buf = io.BytesIO()
        img.save(buf)
        img_base64 = base64.b64encode(buf.getvalue()).decode()

        return render_template('generate_qr_code.html', qr_code=img_base64)

    courses = Course.query.filter_by(lecturer_id=session['user_id']).all()
    return render_template('generate_qr_code.html', courses=courses)

@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        qr_code_file = request.files['qr_code']
        qr_code_data = cv2.imdecode(np.frombuffer(qr_code_file.read(), np.uint8), cv2.IMREAD_COLOR)
        qr_decoder = cv2.QRCodeDetector()
        qr_data, points, _ = qr_decoder.detectAndDecode(qr_code_data)

        if qr_data:
            course_id, course_name, lecturer_id, date = qr_data.split(',')
            student_id = session['user_id']
            attendance_date = datetime.strptime(date, '%Y-%m-%d').date()
            new_attendance = Attendance(student_id=student_id, course_id=course_id, attendance_date=attendance_date, present=True, mark=5.0)
            db.session.add(new_attendance)
            db.session.commit()
            flash("Attendance marked successfully.")
        else:
            flash("Invalid QR code. Please try again.")

    return render_template('scan.html')

@app.route('/get_attendance', methods=['GET'])
def get_attendance():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    attendance_records = []
    if session['role'] == 'Student':
        student_id = session['user_id']
        attendance_records = Attendance.query.filter_by(student_id=student_id).all()
    elif session['role'] == 'Lecturer':
        lecturer_id = session['user_id']
        attendance_records = Attendance.query.join(Course).filter(Course.lecturer_id == lecturer_id).all()

    return render_template('view_attendance.html', attendance_records=attendance_records)

@app.route('/student_dashboard')
def student_dashboard():
    return render_template('landing2.html',user_abbr=session.get('user_abbr'))

@app.route('/lecturer_dashboard')
def lecturer_dashboard():
    return render_template('parent.html',user_abbr=session.get('user_abbr'))

@app.route('/parent_dashboard')
def parent_dashboard():
    return render_template('parent_dashboard.html',user_abbr=session.get('user_abbr'))

if __name__ == '__main__':
    app.run(debug=True)
