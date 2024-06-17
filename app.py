from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import qrcode
import io
import base64
from datetime import datetime
import cv2
import numpy as np
import MySQLdb.cursors

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Database configuration
app.config['MYSQL_HOST'] = '127.0.0.1'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'academic_support_system'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)

def create_tables():
    with app.app_context():
        cur = mysql.connection.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS usersss (
                id INT AUTO_INCREMENT PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(100),
                name VARCHAR(255),
                matric_no VARCHAR(50),
                level VARCHAR(50)
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
                id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                student_id INT NOT NULL,
                lecturer_id INT NOT NULL,
                appointment_time DATETIME NOT NULL,
                reason VARCHAR(255),
                feedback TEXT,
                PRIMARY KEY (id),
                FOREIGN KEY (student_id) REFERENCES usersss(id),
                FOREIGN KEY (lecturer_id) REFERENCES usersss(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                user_id INT NOT NULL,
                message TEXT NOT NULL,
                is_read BOOLEAN DEFAULT 0,
                appointment_id INT UNSIGNED NOT NULL,
                lecturer_id INT NOT NULL,
                student_id INT NOT NULL,
                student_name VARCHAR(255),
                student_matric_no VARCHAR(50),
                student_level VARCHAR(50),
                reason VARCHAR(255),
                PRIMARY KEY (id),
                FOREIGN KEY (user_id) REFERENCES usersss(id),
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
@app.route('/')
def landing_page():
    if 'user_id' in session:
        return redirect(url_for('landing_after_login'))
    return render_template('landing.html')
 
@app.route('/')
def index():
    cur = mysql.connection.cursor()
    cur.execute('''SELECT VERSION()''')
    rv = cur.fetchall()
    return str(rv)   
    
    



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

    cur = mysql.connection.cursor()

    if session['role'] == 'Lecturer':
        lecturer_id = session['user_id']
        cur.execute("""
            SELECT notifications.*, appointments.appointment_time,
                   appointments.reason,
                   usersss.email AS student_email,
                   usersss.name AS student_name,
                   usersss.matric_no AS student_matric_no,
                   usersss.level AS student_level
            FROM notifications
            JOIN appointments ON notifications.appointment_id = appointments.id
            JOIN usersss ON appointments.student_id = usersss.id
            WHERE notifications.lecturer_id = %s AND appointments.feedback IS NULL
        """, [lecturer_id])
    elif session['role'] == 'Student':
        student_id = session['user_id']
        cur.execute("""
            SELECT notifications.*, appointments.appointment_time,
                   appointments.feedback,
                   usersss.email AS lecturer_email
            FROM notifications
            JOIN appointments ON notifications.appointment_id = appointments.id
            JOIN usersss ON appointments.lecturer_id = usersss.id
            WHERE notifications.student_id = %s
        """, [student_id])

    notifications = cur.fetchall()
    cur.close()

    return render_template('notifications.html', notifications=notifications)




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
    return redirect(url_for('notifications'))

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

        # Verify lecturer_id exists
        cur.execute("SELECT id FROM usersss WHERE id = %s AND role = 'Lecturer'", (lecturer_id,))
        lecturer = cur.fetchone()
        if not lecturer:
            flash("Selected lecturer does not exist.")
            return redirect(url_for('appointments'))

        cur.execute("INSERT INTO appointments (student_id, lecturer_id, appointment_time, reason) VALUES (%s, %s, %s, %s)",
                    (student_id, lecturer_id, appointment_time, reason))

        mysql.connection.commit()
        appointment_id = cur.lastrowid

        # Get student details
        cur.execute("SELECT name, matric_no, level FROM usersss WHERE id = %s", (student_id,))
        student = cur.fetchone()
        if not student:
            flash("Student details could not be found.")
            return redirect(url_for('appointments'))

        student_name = student['name']
        student_matric_no = student['matric_no']
        student_level = student['level']

        # Notify the respective lecturer
        cur.execute("""
            INSERT INTO notifications (user_id, reason, appointment_id, lecturer_id, student_id, student_name, student_matric_no, student_level)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (lecturer_id, reason, appointment_id, lecturer_id, student_id, student_name, student_matric_no, student_level))

        mysql.connection.commit()

        flash("Appointment booked successfully.")
        return redirect(url_for('appointments'))

    cur.execute("SELECT appointments.*, usersss.email AS lecturer_email FROM appointments JOIN usersss ON appointments.lecturer_id = usersss.id WHERE student_id = %s", [session['user_id']])
    appointments = cur.fetchall()
    cur.close()

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

    cur = mysql.connection.cursor()
    cur.execute("SELECT id, course_name FROM courses WHERE lecturer_id = %s", [session['user_id']])
    courses = cur.fetchall()
    cur.close()

    return render_template('generate_qr_code.html', courses=courses)

@app.route('/scan_qr', methods=['GET', 'POST'])
def scan_qr():
    if 'user_id' not in session or session['role'] != 'Student':
        return redirect(url_for('home'))

    if request.method == 'POST':
        file = request.files['qr_code']
        if file:
            file_bytes = np.frombuffer(file.read(), np.uint8)
            img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

            detector = cv2.QRCodeDetector()
            data, bbox, _ = detector.detectAndDecode(img)

            if data:
                course_id, course_name, lecturer_id, date = data.split(',')
                student_id = session['user_id']

                cur = mysql.connection.cursor()
                cur.execute("""
                    INSERT INTO attendance (student_id, course_id, attendance_date, present)
                    VALUES (%s, %s, %s, 1)
                """, (student_id, course_id, date))
                mysql.connection.commit()
                cur.close()

                flash(f"Attendance for {course_name} on {date} marked successfully.")
                return redirect(url_for('student_dashboard'))
            else:
                flash("Invalid QR Code. Please try again.")
                return redirect(url_for('scan_qr'))

    return render_template('scan.html')

@app.route('/add_courses')
def add_courses():
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))

    lecturer_id = session['user_id']
    courses = ['CMP 4', 'CMP 407', 'CMP 314']

    cur = mysql.connection.cursor()
    for course_name in courses:
        cur.execute("INSERT INTO courses (course_name, lecturer_id) VALUES (%s, %s)", (course_name, lecturer_id))
    mysql.connection.commit()
    cur.close()

    return "Courses added successfully!"


def scan_qr_code():
    camera = cv2.VideoCapture(0)
    qr_detector = cv2.QRCodeDetector()

    while True:
        success, frame = camera.read()
        if not success:
            break
        else:
            # Detect and decode the QR code
            data, bbox, _ = qr_detector.detectAndDecode(frame)

            if data:
                camera.release()
                cv2.destroyAllWindows()
                return data  # Return the QR code data if found

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

    camera.release()
    cv2.destroyAllWindows()
    return None

@app.route('/mark_attendance_webcam', methods=['GET', 'POST'])
def mark_attendance_webcam():
    if 'user_id' not in session or session['role'] != 'Student':
        return redirect(url_for('home'))

    if request.method == 'POST':
        qr_data = scan_qr_code()

        if qr_data:
            try:
                course_id, attendance_date = qr_data.split('_', 1)
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

    flash("Attendance marked successfully.")
    return redirect(url_for('scan'))

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
    print(f"Sending email to {to} with subject {subject} and body {body}")

@app.route('/view_attendance')
def view_attendance():
    if 'user_id' not in session:
        return redirect(url_for('home'))

    cur = mysql.connection.cursor(MySQLdb.cursors.DictCursor)

    if session['role'] == 'Lecturer':
        lecturer_id = session['user_id']
        cur.execute("""
            SELECT usersss.name AS student_name, usersss.matric_no, courses.course_name, attendance.attendance_date, attendance.present
            FROM attendance
            JOIN usersss ON attendance.student_id = usersss.id
            JOIN courses ON attendance.course_id = courses.id
            WHERE courses.lecturer_id = %s
        """, [lecturer_id])
    elif session['role'] == 'Student':
        student_id = session['user_id']
        cur.execute("""
            SELECT usersss.name AS student_name, usersss.matric_no, courses.course_name, attendance.attendance_date, attendance.present
            FROM attendance
            JOIN usersss ON attendance.student_id = usersss.id
            JOIN courses ON attendance.course_id = courses.id
            WHERE attendance.student_id = %s
        """, [student_id])

    attendance_records = cur.fetchall()
    cur.close()

    return render_template('view_attendance.html', attendance_records=attendance_records)

@app.route('/student_dashboard')
def student_dashboard():
    if 'user_id' not in session or session['role'] != 'Student':
        return redirect(url_for('home'))
    return render_template('landing2.html',user_abbr=session.get('user_abbr'))

@app.route('/lecturer_dashboard')
def lecturer_dashboard():
    if 'user_id' not in session or session['role'] != 'Lecturer':
        return redirect(url_for('home'))
    return render_template('parent.html',user_abbr=session.get('user_abbr'))

@app.route('/parent_dashboard')
def parent_dashboard():
    if 'user_id' not in session or session['role'] != 'Parent':
        return redirect(url_for('home'))
    return render_template('parent_dashboard.html')

if __name__ == '__main__':
    app.run(debug=True, port=5002)
