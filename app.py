from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_mysqldb import MySQL
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
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'academic_support_system'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

# Create tables if they do not exist
def create_tables():
    with app.app_context():
        cur = mysql.connection.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usersss (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(100)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS courses (
                id INT AUTO_INCREMENT PRIMARY KEY,
                course_name VARCHAR(255) NOT NULL,
                lecturer_id INT NOT NULL,
                FOREIGN KEY (lecturer_id) REFERENCES usersss(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS appointments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                lecturer_id INT NOT NULL,
                appointment_time DATETIME NOT NULL,
                reason TEXT NOT NULL,
                feedback TEXT,
                FOREIGN KEY (student_id) REFERENCES usersss(id),
                FOREIGN KEY (lecturer_id) REFERENCES usersss(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                appointment_id INT NOT NULL,
                lecturer_id INT NOT NULL,
                student_id INT NOT NULL,
                FOREIGN KEY (appointment_id) REFERENCES appointments(id),
                FOREIGN KEY (lecturer_id) REFERENCES usersss(id),
                FOREIGN KEY (student_id) REFERENCES usersss(id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS attendance (
                id INT AUTO_INCREMENT PRIMARY KEY,
                student_id INT NOT NULL,
                course_id INT NOT NULL,
                attendance_date DATE NOT NULL,
                present TINYINT(1) NOT NULL DEFAULT 0,
                mark FLOAT NOT NULL DEFAULT 0,
                FOREIGN KEY (student_id) REFERENCES usersss(id),
                FOREIGN KEY (course_id) REFERENCES courses(id)
            )
        """)
        mysql.connection.commit()
        cur.close()

create_tables()

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
    role = request.form['role']  # Get the role from the signup form

    if password == confirm_password:
        hashed_password = generate_password_hash(password)
        cur = mysql.connection.cursor()
        cur.execute("INSERT INTO usersss (email, password, role) VALUES (%s, %s, %s)", (email, hashed_password, role))
        mysql.connection.commit()
        cur.close()
        flash("Signup successful. You can now login.")
        return redirect(url_for('home'))
    else:
        flash("Passwords do not match. Try again.")
        return redirect(url_for('home'))

@app.route('/login', methods=['POST'])
def login():
    email = request.form['email']
    password = request.form['password']
    cur = mysql.connection.cursor()
    cur.execute("SELECT * FROM usersss WHERE email = %s", [email])
    user = cur.fetchone()
    cur.close()

    if user and check_password_hash(user['password'], password):
        session['user_id'] = user['id']
        session['role'] = user['role']
        session['user_abbr'] = user['email'][:5].upper()
        flash(f"You were successfully logged in as {session['user_abbr']}")

        if user['role'] == 'Student':
            return redirect(url_for('student_dashboard'))
        elif user['role'] == 'Lecturer':
            return redirect(url_for('lecturer_dashboard'))
        elif user['role'] == 'Parent':
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
        user_id = session['user_id']
        cur = mysql.connection.cursor()
        cur.execute("SELECT email FROM usersss WHERE id = %s", [user_id])
        user = cur.fetchone()
        cur.close()

        user_abbr = user['email'][:5].upper() if user else ''
        return render_template('landing.html', user_abbr=user_abbr)
    else:
        return redirect(url_for('home'))

@app.route('/notifications')
def notifications():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    if session['role'] == 'Lecturer':
        lecturer_id = session['user_id']
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM appointments WHERE lecturer_id = %s AND feedback IS NULL", [lecturer_id])
        appointments = cur.fetchall()
        cur.close()

        return render_template('notifications.html', appointments=appointments)
    else:
        return redirect(url_for('home'))

@app.route('/appointments', methods=['GET', 'POST'])
def appointments():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT id, email, role FROM usersss WHERE role = 'Lecturer'")
    lecturers = cur.fetchall()

    if request.method == 'POST':
        student_id = session['user_id']
        lecturer_id = request.form['lecturer_id']
        appointment_time = request.form['appointment_time']
        reason = request.form['reason']

        cur.execute("INSERT INTO appointments (student_id, lecturer_id, appointment_time, reason) VALUES (%s, %s, %s, %s)",
                    (student_id, lecturer_id, appointment_time, reason))
        mysql.connection.commit()
        appointment_id = cur.lastrowid

        # Notify the respective lecturer
        cur.execute("INSERT INTO notifications (appointment_id, lecturer_id, student_id) VALUES (%s, %s, %s)",
                    (appointment_id, lecturer_id, student_id))
        mysql.connection.commit()

        flash("Appointment booked successfully.")
        return redirect(url_for('appointments'))

    cur.execute("SELECT appointments.*, usersss.email AS lecturer_email FROM appointments JOIN usersss ON appointments.lecturer_id = usersss.id WHERE student_id = %s", [session['user_id']])
    appointments = cur.fetchall()
    cur.close()

    return render_template('appoint.html', lecturers=lecturers, appointments=appointments)

@app.route('/send_feedback', methods=['POST'])
def send_feedback():
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))

    feedback = request.form['feedback']
    appointment_id = request.form['appointment_id']

    cur = mysql.connection.cursor()
    cur.execute("UPDATE appointments SET feedback = %s WHERE id = %s AND lecturer_id = %s",
                (feedback, appointment_id, session['user_id']))
    mysql.connection.commit()
    cur.close()

    flash("Feedback sent successfully.")
    return redirect(url_for('appointments'))

@app.route('/lecturer_dashboard')
def lecturer_dashboard():
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))
    return render_template('lecturer_dashboard.html',user_abbr=session.get('user_abbr'))

@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session or session['role'] != 'Student':
        return redirect(url_for('home'))
    return render_template('landing2.html',user_abbr=session.get('user_abbr'))

@app.route('/parent_dashboard')
def parent_dashboard():
    if 'user_id' not in session or session['role'] != 'Parent':
        return redirect(url_for('home'))
    return render_template('parent_dashboard.html')


@app.route('/mark_attendance_webcam', methods=['GET', 'POST'])
def mark_attendance_webcam():
    if 'user_id' not in session or session['role'] != 'Student':
        return redirect(url_for('home'))

    if request.method == 'POST':
        qr_data = scan_qr_code()

        # Check if QR code data was found
        if qr_data:
            # Split qr_data into course_id and attendance_date
            course_id, attendance_date = qr_data.split('_', 1)

            # Ensure attendance_date is in the correct format
            try:
                attendance_date = datetime.strptime(attendance_date, '%Y-%m-%d').date()
            except ValueError:
                flash("Invalid attendance date format.")
                return redirect(url_for('student_dashboard'))

            student_id = session['user_id']
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM attendance WHERE student_id = %s AND course_id = %s AND attendance_date = %s",
                        (student_id, course_id, attendance_date))
            attendance_record = cur.fetchone()

            if not attendance_record:
                cur.execute("INSERT INTO attendance (student_id, course_id, attendance_date, present, mark) VALUES (%s, %s, %s, 1, 0.5)",
                            (student_id, course_id, attendance_date))
            else:
                cur.execute("UPDATE attendance SET present = 1, mark = 0.5 WHERE id = %s", [attendance_record['id']])

            mysql.connection.commit()
            cur.close()

            flash("Attendance marked successfully.")
            return redirect(url_for('student_dashboard'))
        else:
            flash("No QR code detected. Please try again.")
            return redirect(url_for('student_dashboard'))

    return render_template('scan.html')

@app.route('/mark_attendance', methods=['POST'])
def mark_attendance():
    if 'user_id' not in session or session['role'] != 'Student':
        return redirect(url_for('home'))

    # Your existing code for processing attendance goes here...

    flash("Attendance marked successfully.")
    return redirect(url_for('scan'))  # Redirect to the scan.html page

@app.route('/scan')
def scan():
    return render_template('scan.html')

def notify_absentees():
    with app.app_context():
        cur = mysql.connection.cursor()
        attendance_date = datetime.now().date()

        cur.execute("""
            SELECT usersss.id, usersss.email, usersss.role, courses.course_name
            FROM usersss
            JOIN attendance ON usersss.id = attendance.student_id
            JOIN courses ON attendance.course_id = courses.id
            WHERE attendance.present = 0 AND attendance.attendance_date = %s
        """, [attendance_date])
        absentees = cur.fetchall()

        for absentee in absentees:
            # Notify the lecturer and parent
            # Assuming you have parents' emails stored somewhere
            lecturer_email = get_lecturer_email(absentee['course_id'])
            parent_email = get_parent_email(absentee['id'])
            send_email(lecturer_email, "Student Absence Notification", f"Student {absentee['email']} missed the class for {absentee['course_name']} on {attendance_date}")
            send_email(parent_email, "Student Absence Notification", f"Your child {absentee['email']} missed the class for {absentee['course_name']} on {attendance_date}")

        cur.close()

def get_lecturer_email(course_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT usersss.email FROM usersss JOIN courses ON usersss.id = courses.lecturer_id WHERE courses.id = %s", [course_id])
    lecturer = cur.fetchone()
    cur.close()
    return lecturer['email'] if lecturer else None

def get_parent_email(student_id):
    cur = mysql.connection.cursor()
    cur.execute("SELECT email FROM usersss WHERE role = 'Parent' AND id = %s", [student_id])
    parent = cur.fetchone()
    cur.close()
    return parent['email'] if parent else None

def send_email(to, subject, body):
    # Placeholder for sending email
    print(f"Sending email to {to} with subject {subject} and body {body}")

if __name__ == '__main__':
    app.run(debug=True)
