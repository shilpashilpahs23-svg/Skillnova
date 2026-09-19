from flask import Flask, render_template, request, redirect, session, url_for, jsonify
from flask_socketio import SocketIO, emit, join_room
import sqlite3


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

app.secret_key = "skillnova_secret_key"

socketio = SocketIO(app, cors_allowed_origins="*")

DATABASE = "skillnova.db"


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# =========================================================
# NOTIFICATION HELPER
# =========================================================

def create_notification(student_id, message, notification_type):
    conn = get_db()

    conn.execute("""
        INSERT INTO notifications
        (student_id, message, notification_type, is_read)
        VALUES (?, ?, ?, 0)
    """, (
        student_id,
        message,
        notification_type
    ))

    conn.commit()
    conn.close()


# =========================================================
# DATABASE INITIALIZATION
# =========================================================

def init_db():

    conn = get_db()

    # -----------------------------------------------------
    # STUDENTS TABLE
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            college TEXT,
            bio TEXT
        )
    """)

    # -----------------------------------------------------
    # SKILLS TABLE
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            skill_name TEXT NOT NULL,
            skill_type TEXT NOT NULL,
            level TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    # -----------------------------------------------------
    # CONNECTIONS TABLE
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            FOREIGN KEY(sender_id) REFERENCES students(id),
            FOREIGN KEY(receiver_id) REFERENCES students(id)
        )
    """)

    # -----------------------------------------------------
    # TEAMS TABLE
    # IMPORTANT: column is team_name
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            description TEXT,
            created_by INTEGER NOT NULL,
            FOREIGN KEY(created_by) REFERENCES students(id)
        )
    """)

    # -----------------------------------------------------
    # TEAM MEMBERS TABLE
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            role TEXT DEFAULT 'Member',
            FOREIGN KEY(team_id) REFERENCES teams(id),
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    # -----------------------------------------------------
    # NOTIFICATIONS TABLE
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            notification_type TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
    """)

    # -----------------------------------------------------
    # MESSAGES TABLE
    # -----------------------------------------------------

    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sender_id) REFERENCES students(id),
            FOREIGN KEY(receiver_id) REFERENCES students(id)
        )
    """)

    conn.commit()
    conn.close()


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def index():

    return render_template("index.html")


# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        college = request.form.get("college", "").strip()

        if not full_name or not email or not password:

            return render_template(
                "register.html",
                error="Please fill all required fields."
            )

        conn = get_db()

        existing = conn.execute(
            "SELECT id FROM students WHERE email = ?",
            (email,)
        ).fetchone()

        if existing:

            conn.close()

            return render_template(
                "register.html",
                error="Email already registered."
            )

        conn.execute("""
            INSERT INTO students
            (full_name, email, password, college, bio)
            VALUES (?, ?, ?, ?, ?)
        """, (
            full_name,
            email,
            password,
            college,
            ""
        ))

        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template("register.html")


# =========================================================
# LOGIN
# =========================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        conn = get_db()

        student = conn.execute("""
            SELECT *
            FROM students
            WHERE email = ?
            AND password = ?
        """, (
            email,
            password
        )).fetchone()

        conn.close()

        if student:

            session["student_id"] = student["id"]

            # IMPORTANT:
            # After login user goes to dashboard.html
            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid email or password."
        )

    return render_template("login.html")


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))


# =========================================================
# DASHBOARD
# =========================================================

@app.route("/dashboard")
def dashboard():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    # Student details
    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (student_id,)).fetchone()

    if not student:

        conn.close()
        session.clear()

        return redirect(url_for("login"))

    # My skills
    skills = conn.execute("""
        SELECT *
        FROM skills
        WHERE student_id = ?
        ORDER BY id DESC
    """, (student_id,)).fetchall()

    # Accepted connections
    connection_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM connections
        WHERE
        (sender_id = ? OR receiver_id = ?)
        AND status = 'Accepted'
    """, (
        student_id,
        student_id
    )).fetchone()["count"]

    # Pending requests
    pending_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM connections
        WHERE receiver_id = ?
        AND status = 'Pending'
    """, (student_id,)).fetchone()["count"]

    # Teams
    team_count = conn.execute("""
        SELECT COUNT(DISTINCT team_id) AS count
        FROM team_members
        WHERE student_id = ?
    """, (student_id,)).fetchone()["count"]

    # Unread notifications
    notification_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE student_id = ?
        AND is_read = 0
    """, (student_id,)).fetchone()["count"]

    conn.close()

    return render_template(
        "dashboard.html",
        student=student,
        skills=skills,
        skill_count=len(skills),
        connection_count=connection_count,
        pending_count=pending_count,
        team_count=team_count,
        notification_count=notification_count
    )


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    if request.method == "POST":

        full_name = request.form.get("full_name", "").strip()
        college = request.form.get("college", "").strip()
        bio = request.form.get("bio", "").strip()

        conn.execute("""
            UPDATE students
            SET full_name = ?,
                college = ?,
                bio = ?
            WHERE id = ?
        """, (
            full_name,
            college,
            bio,
            student_id
        ))

        conn.commit()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (student_id,)).fetchone()

    conn.close()

    return render_template(
        "profile.html",
        student=student
    )


# =========================================================
# MY SKILLS
# =========================================================

@app.route("/skills", methods=["GET", "POST"])
def skills():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    if request.method == "POST":

        skill_name = request.form.get("skill_name", "").strip()
        skill_type = request.form.get("skill_type", "").strip()
        level = request.form.get("level", "").strip()

        if skill_name and skill_type:

            conn.execute("""
                INSERT INTO skills
                (student_id, skill_name, skill_type, level)
                VALUES (?, ?, ?, ?)
            """, (
                student_id,
                skill_name,
                skill_type,
                level
            ))

            conn.commit()

        conn.close()

        return redirect(url_for("skills"))

    student_skills = conn.execute("""
        SELECT *
        FROM skills
        WHERE student_id = ?
        ORDER BY id DESC
    """, (student_id,)).fetchall()

    conn.close()

    return render_template(
        "skills.html",
        skills=student_skills
    )


# =========================================================
# DELETE SKILL
# =========================================================

@app.route("/delete_skill/<int:skill_id>", methods=["POST"])
def delete_skill(skill_id):

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    conn.execute("""
        DELETE FROM skills
        WHERE id = ?
        AND student_id = ?
    """, (
        skill_id,
        student_id
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("skills"))


# =========================================================
# FIND STUDENTS
# =========================================================

@app.route("/students")
def students():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    search = request.args.get("search", "").strip()

    conn = get_db()

    if search:

        students_list = conn.execute("""
            SELECT DISTINCT
                s.id,
                s.full_name,
                s.email,
                s.college,
                s.bio,
                sk.skill_name,
                sk.skill_type,
                sk.level
            FROM students s
            LEFT JOIN skills sk
                ON s.id = sk.student_id
            WHERE s.id != ?
            AND (
                sk.skill_name LIKE ?
                OR s.full_name LIKE ?
                OR s.college LIKE ?
            )
            ORDER BY s.full_name
        """, (
            student_id,
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%"
        )).fetchall()

    else:

        students_list = conn.execute("""
            SELECT DISTINCT
                s.id,
                s.full_name,
                s.email,
                s.college,
                s.bio,
                sk.skill_name,
                sk.skill_type,
                sk.level
            FROM students s
            LEFT JOIN skills sk
                ON s.id = sk.student_id
            WHERE s.id != ?
            ORDER BY s.full_name
        """, (
            student_id,
        )).fetchall()

    conn.close()

    return render_template(
        "students.html",
        students=students_list,
        search=search
    )


# =========================================================
# STUDENT PROFILE
# =========================================================

@app.route("/student_profile/<int:student_id>")
def student_profile(student_id):

    if "student_id" not in session:

        return redirect(url_for("login"))

    current_student_id = session["student_id"]

    conn = get_db()

    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (
        student_id,
    )).fetchone()

    if not student:

        conn.close()

        return redirect(url_for("students"))

    student_skills = conn.execute("""
        SELECT *
        FROM skills
        WHERE student_id = ?
        ORDER BY id DESC
    """, (
        student_id,
    )).fetchall()

    # Check connection status
    connection = conn.execute("""
        SELECT *
        FROM connections
        WHERE
        (sender_id = ? AND receiver_id = ?)
        OR
        (sender_id = ? AND receiver_id = ?)
        ORDER BY id DESC
        LIMIT 1
    """, (
        current_student_id,
        student_id,
        student_id,
        current_student_id
    )).fetchone()

    conn.close()

    connection_status = None

    if connection:
        connection_status = connection["status"]

    return render_template(
        "student_profile.html",
        student=student,
        skills=student_skills,
        connection_status=connection_status
    )


# =========================================================
# SMART MATCHING
# =========================================================

@app.route("/matches")
def matches():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    my_skills = conn.execute("""
        SELECT skill_name, skill_type
        FROM skills
        WHERE student_id = ?
    """, (
        student_id,
    )).fetchall()

    # Skills I can teach
    my_teaching = set()

    # Skills I want to learn
    my_learning = set()

    for skill in my_skills:

        skill_name = skill["skill_name"].strip().lower()
        skill_type = skill["skill_type"].strip().lower()

        if skill_type in [
            "want to learn",
            "want-to-learn",
            "learning"
        ]:
            my_learning.add(skill_name)

        else:
            my_teaching.add(skill_name)

    # Get all other students
    students_list = conn.execute("""
        SELECT id, full_name, email, college, bio
        FROM students
        WHERE id != ?
        ORDER BY full_name
    """, (
        student_id,
    )).fetchall()

    match_list = []

    for student in students_list:

        other_skills = conn.execute("""
            SELECT skill_name, skill_type, level
            FROM skills
            WHERE student_id = ?
        """, (
            student["id"],
        )).fetchall()

        other_teaching = set()
        other_learning = set()

        for skill in other_skills:

            skill_name = skill["skill_name"].strip().lower()
            skill_type = skill["skill_type"].strip().lower()

            if skill_type in [
                "want to learn",
                "want-to-learn",
                "learning"
            ]:
                other_learning.add(skill_name)

            else:
                other_teaching.add(skill_name)

        score = 0

        # -------------------------------------------------
        # MATCH 1
        # They can teach what I want to learn
        # -------------------------------------------------

        first_match = my_learning.intersection(other_teaching)

        if first_match:
            score += 50

        # -------------------------------------------------
        # MATCH 2
        # I can teach what they want to learn
        # -------------------------------------------------

        second_match = my_teaching.intersection(other_learning)

        if second_match:
            score += 50

        if score > 0:

            match_list.append({
                "id": student["id"],
                "full_name": student["full_name"],
                "email": student["email"],
                "college": student["college"],
                "bio": student["bio"],
                "score": score,
                "can_teach": list(other_teaching),
                "want_to_learn": list(other_learning)
            })

    # Highest score first
    match_list.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    conn.close()

    return render_template(
        "matches.html",
        matches=match_list
    )


# =========================================================
# SEND CONNECTION REQUEST
# =========================================================

@app.route("/connect/<int:student_id>")
def connect(student_id):

    if "student_id" not in session:

        return redirect(url_for("login"))

    current_student_id = session["student_id"]

    # Prevent self connection
    if current_student_id == student_id:

        return redirect(url_for("students"))

    conn = get_db()

    # Check student exists
    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (
        student_id,
    )).fetchone()

    if not student:

        conn.close()

        return redirect(url_for("students"))

    # Check existing connection in either direction
    existing = conn.execute("""
        SELECT *
        FROM connections
        WHERE
        (sender_id = ? AND receiver_id = ?)
        OR
        (sender_id = ? AND receiver_id = ?)
        LIMIT 1
    """, (
        current_student_id,
        student_id,
        student_id,
        current_student_id
    )).fetchone()

    if existing:

        conn.close()

        return redirect(url_for(
            "student_profile",
            student_id=student_id
        ))

    # Create connection
    conn.execute("""
        INSERT INTO connections
        (sender_id, receiver_id, status)
        VALUES (?, ?, 'Pending')
    """, (
        current_student_id,
        student_id
    ))

    conn.commit()

    sender = conn.execute("""
        SELECT full_name
        FROM students
        WHERE id = ?
    """, (
        current_student_id,
    )).fetchone()

    conn.close()

    sender_name = sender["full_name"] if sender else "A student"

    create_notification(
        student_id,
        f"{sender_name} sent you a connection request.",
        "connection_request"
    )

    return redirect(url_for(
        "student_profile",
        student_id=student_id
    ))


# =========================================================
# CONNECTIONS
# =========================================================

@app.route("/connections")
def connections():

    if "student_id" not in session:

        return redirect(url_for("login"))

    current_student_id = session["student_id"]

    conn = get_db()

    # -----------------------------------------------------
    # PENDING REQUESTS
    # -----------------------------------------------------

    pending_requests = conn.execute("""
        SELECT
            c.id,
            c.sender_id AS student_id,
            s.full_name,
            s.email,
            s.college,
            s.bio
        FROM connections c
        JOIN students s
            ON s.id = c.sender_id
        WHERE c.receiver_id = ?
        AND c.status = 'Pending'
        ORDER BY c.id DESC
    """, (
        current_student_id,
    )).fetchall()

    # -----------------------------------------------------
    # ACCEPTED CONNECTIONS
    # -----------------------------------------------------

    accepted_connections = conn.execute("""
        SELECT
            c.id,
            CASE
                WHEN c.sender_id = ?
                THEN c.receiver_id
                ELSE c.sender_id
            END AS student_id,

            CASE
                WHEN c.sender_id = ?
                THEN receiver.full_name
                ELSE sender.full_name
            END AS full_name,

            CASE
                WHEN c.sender_id = ?
                THEN receiver.email
                ELSE sender.email
            END AS email,

            CASE
                WHEN c.sender_id = ?
                THEN receiver.college
                ELSE sender.college
            END AS college,

            CASE
                WHEN c.sender_id = ?
                THEN receiver.bio
                ELSE sender.bio
            END AS bio

        FROM connections c

        JOIN students sender
            ON sender.id = c.sender_id

        JOIN students receiver
            ON receiver.id = c.receiver_id

        WHERE
            (c.sender_id = ? OR c.receiver_id = ?)
            AND c.status = 'Accepted'

        ORDER BY c.id DESC
    """, (
        current_student_id,
        current_student_id,
        current_student_id,
        current_student_id,
        current_student_id,
        current_student_id,
        current_student_id
    )).fetchall()

    connection_count = len(accepted_connections)

    pending_count = len(pending_requests)

    conn.close()

    return render_template(
        "connection_partner.html",
        pending_requests=pending_requests,
        accepted_connections=accepted_connections,
        connection_count=connection_count,
        pending_count=pending_count
    )


# =========================================================
# ACCEPT CONNECTION
# =========================================================

@app.route("/accept_connection/<int:connection_id>")
def accept_connection(connection_id):

    if "student_id" not in session:

        return redirect(url_for("login"))

    current_student_id = session["student_id"]

    conn = get_db()

    connection = conn.execute("""
        SELECT *
        FROM connections
        WHERE id = ?
        AND receiver_id = ?
        AND status = 'Pending'
    """, (
        connection_id,
        current_student_id
    )).fetchone()

    if not connection:

        conn.close()

        return redirect(url_for("connections"))

    conn.execute("""
        UPDATE connections
        SET status = 'Accepted'
        WHERE id = ?
    """, (
        connection_id,
    ))

    sender_id = connection["sender_id"]

    receiver = conn.execute("""
        SELECT full_name
        FROM students
        WHERE id = ?
    """, (
        current_student_id,
    )).fetchone()

    conn.commit()
    conn.close()

    receiver_name = (
        receiver["full_name"]
        if receiver
        else "A student"
    )

    create_notification(
        sender_id,
        f"{receiver_name} accepted your connection request.",
        "connection_accepted"
    )

    return redirect(url_for("connections"))


# =========================================================
# REJECT CONNECTION
# =========================================================

@app.route("/reject_connection/<int:connection_id>")
def reject_connection(connection_id):

    if "student_id" not in session:

        return redirect(url_for("login"))

    current_student_id = session["student_id"]

    conn = get_db()

    connection = conn.execute("""
        SELECT *
        FROM connections
        WHERE id = ?
        AND receiver_id = ?
        AND status = 'Pending'
    """, (
        connection_id,
        current_student_id
    )).fetchone()

    if connection:

        conn.execute("""
            UPDATE connections
            SET status = 'Rejected'
            WHERE id = ?
        """, (
            connection_id,
        ))

        conn.commit()

    conn.close()

    return redirect(url_for("connections"))


# =========================================================
# NOTIFICATIONS
# =========================================================

@app.route("/notifications")
def notifications():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    notification_list = conn.execute("""
        SELECT *
        FROM notifications
        WHERE student_id = ?
        ORDER BY id DESC
    """, (
        student_id,
    )).fetchall()

    unread_count = conn.execute("""
        SELECT COUNT(*) AS count
        FROM notifications
        WHERE student_id = ?
        AND is_read = 0
    """, (
        student_id,
    )).fetchone()["count"]

    conn.close()

    return render_template(
        "notifications.html",
        notifications=notification_list,
        unread_count=unread_count
    )


# =========================================================
# READ NOTIFICATIONS
# =========================================================

@app.route("/read_notifications")
def read_notifications():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    conn.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE student_id = ?
    """, (
        student_id,
    ))

    conn.commit()
    conn.close()

    return redirect(url_for("notifications"))


# =========================================================
# CREATE TEAM
# =========================================================

@app.route("/create_team", methods=["GET", "POST"])
def create_team():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    if request.method == "POST":

        team_name = request.form.get("team_name", "").strip()
        description = request.form.get("description", "").strip()

        if not team_name:

            return render_template(
                "team_names.html",
                error="Team name is required."
            )

        conn = get_db()

        cursor = conn.execute("""
            INSERT INTO teams
            (team_name, description, created_by)
            VALUES (?, ?, ?)
        """, (
            team_name,
            description,
            student_id
        ))

        team_id = cursor.lastrowid

        # Add creator as Team Leader
        conn.execute("""
            INSERT INTO team_members
            (team_id, student_id, role)
            VALUES (?, ?, 'Team Leader')
        """, (
            team_id,
            student_id
        ))

        conn.commit()
        conn.close()

        return redirect(url_for(
            "team_details",
            team_id=team_id
        ))

    return render_template("team_names.html")


# =========================================================
# MY TEAMS
# =========================================================

@app.route("/team")
def team():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    teams = conn.execute("""
        SELECT
            t.id,
            t.team_name,
            t.description,
            t.created_by,
            tm.role

        FROM teams t

        JOIN team_members tm
            ON tm.team_id = t.id

        WHERE tm.student_id = ?

        ORDER BY t.id DESC
    """, (
        student_id,
    )).fetchall()

    conn.close()

    return render_template(
        "team_names.html",
        teams=teams
    )


# =========================================================
# TEAM DETAILS
# =========================================================

@app.route("/team/<int:team_id>")
def team_details(team_id):

    if "student_id" not in session:

        return redirect(url_for("login"))

    current_student_id = session["student_id"]

    conn = get_db()

    # Team
    team_data = conn.execute("""
        SELECT
            t.id,
            t.team_name,
            t.description,
            t.created_by,
            s.full_name AS creator_name
        FROM teams t
        JOIN students s
            ON s.id = t.created_by
        WHERE t.id = ?
    """, (
        team_id,
    )).fetchone()

    if not team_data:

        conn.close()

        return redirect(url_for("team"))

    # Check current user is member
    membership = conn.execute("""
        SELECT *
        FROM team_members
        WHERE team_id = ?
        AND student_id = ?
    """, (
        team_id,
        current_student_id
    )).fetchone()

    if not membership:

        conn.close()

        return redirect(url_for("team"))

    # Team members
    members = conn.execute("""
        SELECT
            tm.id,
            tm.student_id,
            tm.role,
            s.full_name,
            s.email,
            s.college
        FROM team_members tm
        JOIN students s
            ON s.id = tm.student_id
        WHERE tm.team_id = ?
        ORDER BY tm.id
    """, (
        team_id,
    )).fetchall()

    conn.close()

    return render_template(
        "team.html",
        team=team_data,
        members=members,
        current_role=membership["role"]
    )


# =========================================================
# ADD TEAM MEMBER
# =========================================================

@app.route("/add_team_member/<int:team_id>", methods=["POST"])
def add_team_member(team_id):

    if "student_id" not in session:

        return redirect(url_for("login"))

    current_student_id = session["student_id"]

    student_id = request.form.get("student_id")

    if not student_id:

        return redirect(url_for(
            "team_details",
            team_id=team_id
        ))

    try:

        student_id = int(student_id)

    except ValueError:

        return redirect(url_for(
            "team_details",
            team_id=team_id
        ))

    conn = get_db()

    # Check current user is team leader
    current_member = conn.execute("""
        SELECT *
        FROM team_members
        WHERE team_id = ?
        AND student_id = ?
    """, (
        team_id,
        current_student_id
    )).fetchone()

    if not current_member or current_member["role"] != "Team Leader":

        conn.close()

        return redirect(url_for(
            "team_details",
            team_id=team_id
        ))

    # Check student exists
    student = conn.execute("""
        SELECT *
        FROM students
        WHERE id = ?
    """, (
        student_id,
    )).fetchone()

    if not student:

        conn.close()

        return redirect(url_for(
            "team_details",
            team_id=team_id
        ))

    # Check already member
    existing = conn.execute("""
        SELECT *
        FROM team_members
        WHERE team_id = ?
        AND student_id = ?
    """, (
        team_id,
        student_id
    )).fetchone()

    if existing:

        conn.close()

        return redirect(url_for(
            "team_details",
            team_id=team_id
        ))

    # Add member
    conn.execute("""
        INSERT INTO team_members
        (team_id, student_id, role)
        VALUES (?, ?, 'Member')
    """, (
        team_id,
        student_id
    ))

    team = conn.execute("""
        SELECT team_name
        FROM teams
        WHERE id = ?
    """, (
        team_id,
    )).fetchone()

    conn.commit()
    conn.close()

    if team:

        create_notification(
            student_id,
            f"You were added to team '{team['team_name']}'.",
            "team_added"
        )

    return redirect(url_for(
        "team_details",
        team_id=team_id
    ))


# =========================================================
# CHAT PAGE
# =========================================================

@app.route("/chat/<int:student_id>")
def chat(student_id):

    if "student_id" not in session:

        return redirect(url_for("login"))

    current_student_id = session["student_id"]

    # Prevent chatting with yourself
    if current_student_id == student_id:

        return redirect(url_for("connections"))

    conn = get_db()

    # Check receiver exists
    receiver = conn.execute("""
        SELECT id, full_name, email, college, bio
        FROM students
        WHERE id = ?
    """, (
        student_id,
    )).fetchone()

    if not receiver:

        conn.close()

        return redirect(url_for("connections"))

    # -----------------------------------------------------
    # ONLY ACCEPTED CONNECTIONS CAN CHAT
    # -----------------------------------------------------

    connection = conn.execute("""
        SELECT *
        FROM connections
        WHERE
        (
            sender_id = ?
            AND receiver_id = ?
        )
        OR
        (
            sender_id = ?
            AND receiver_id = ?
        )
    """, (
        current_student_id,
        student_id,
        student_id,
        current_student_id
    )).fetchone()

    if not connection or connection["status"] != "Accepted":

        conn.close()

        return redirect(url_for("connections"))

    # Load previous messages
    messages = conn.execute("""
        SELECT
            m.id,
            m.sender_id,
            m.receiver_id,
            m.message,
            m.created_at
        FROM messages m
        WHERE
        (
            m.sender_id = ?
            AND m.receiver_id = ?
        )
        OR
        (
            m.sender_id = ?
            AND m.receiver_id = ?
        )
        ORDER BY m.id ASC
    """, (
        current_student_id,
        student_id,
        student_id,
        current_student_id
    )).fetchall()

    conn.close()

    return render_template(
        "chat.html",
        receiver=receiver,
        messages=messages,
        current_student_id=current_student_id
    )


# =========================================================
# CHAT DATA API
# =========================================================

@app.route("/chat_data/<int:student_id>")
def chat_data(student_id):

    if "student_id" not in session:

        return jsonify({
            "error": "Not logged in"
        }), 401

    current_student_id = session["student_id"]

    if current_student_id == student_id:

        return jsonify({
            "error": "Invalid chat"
        }), 400

    conn = get_db()

    # Check accepted connection
    connection = conn.execute("""
        SELECT *
        FROM connections
        WHERE
        (
            sender_id = ?
            AND receiver_id = ?
        )
        OR
        (
            sender_id = ?
            AND receiver_id = ?
        )
    """, (
        current_student_id,
        student_id,
        student_id,
        current_student_id
    )).fetchone()

    if not connection or connection["status"] != "Accepted":

        conn.close()

        return jsonify({
            "error": "Not connected"
        }), 403

    messages = conn.execute("""
        SELECT
            id,
            sender_id,
            receiver_id,
            message,
            created_at
        FROM messages
        WHERE
        (
            sender_id = ?
            AND receiver_id = ?
        )
        OR
        (
            sender_id = ?
            AND receiver_id = ?
        )
        ORDER BY id ASC
    """, (
        current_student_id,
        student_id,
        student_id,
        current_student_id
    )).fetchall()

    conn.close()

    result = []

    for message in messages:

        result.append({
            "id": message["id"],
            "sender_id": message["sender_id"],
            "receiver_id": message["receiver_id"],
            "message": message["message"],
            "created_at": message["created_at"]
        })

    return jsonify(result)


# =========================================================
# SOCKET.IO - JOIN CHAT
# =========================================================

@socketio.on("join_chat")
def handle_join_chat(data):

    if "student_id" not in session:

        return

    current_student_id = session["student_id"]

    try:

        receiver_id = int(data.get("receiver_id"))

    except (TypeError, ValueError):

        return

    if current_student_id == receiver_id:

        return

    conn = get_db()

    connection = conn.execute("""
        SELECT *
        FROM connections
        WHERE
        (
            sender_id = ?
            AND receiver_id = ?
        )
        OR
        (
            sender_id = ?
            AND receiver_id = ?
        )
        AND status = 'Accepted'
    """, (
        current_student_id,
        receiver_id,
        receiver_id,
        current_student_id
    )).fetchone()

    conn.close()

    if not connection or connection["status"] != "Accepted":

        return

    room_id = (
        f"chat_{min(current_student_id, receiver_id)}_"
        f"{max(current_student_id, receiver_id)}"
    )

    join_room(room_id)


# =========================================================
# SOCKET.IO - SEND MESSAGE
# =========================================================

@socketio.on("send_message")
def handle_send_message(data):

    if "student_id" not in session:

        return

    sender_id = session["student_id"]

    try:

        receiver_id = int(data.get("receiver_id"))

    except (TypeError, ValueError):

        return

    message_text = str(
        data.get("message", "")
    ).strip()

    if not message_text:

        return

    if sender_id == receiver_id:

        return

    conn = get_db()

    # Check accepted connection
    connection = conn.execute("""
        SELECT *
        FROM connections
        WHERE
        (
            sender_id = ?
            AND receiver_id = ?
        )
        OR
        (
            sender_id = ?
            AND receiver_id = ?
        )
    """, (
        sender_id,
        receiver_id,
        receiver_id,
        sender_id
    )).fetchone()

    if not connection or connection["status"] != "Accepted":

        conn.close()

        return

    # Check receiver exists
    receiver = conn.execute("""
        SELECT id
        FROM students
        WHERE id = ?
    """, (
        receiver_id,
    )).fetchone()

    if not receiver:

        conn.close()

        return

    # Save message
    cursor = conn.execute("""
        INSERT INTO messages
        (sender_id, receiver_id, message)
        VALUES (?, ?, ?)
    """, (
        sender_id,
        receiver_id,
        message_text
    ))

    message_id = cursor.lastrowid

    # Get message
    saved_message = conn.execute("""
        SELECT
            id,
            sender_id,
            receiver_id,
            message,
            created_at
        FROM messages
        WHERE id = ?
    """, (
        message_id,
    )).fetchone()

    conn.commit()
    conn.close()

    room_id = (
        f"chat_{min(sender_id, receiver_id)}_"
        f"{max(sender_id, receiver_id)}"
    )

    emit(
        "receive_message",
        {
            "id": saved_message["id"],
            "sender_id": saved_message["sender_id"],
            "receiver_id": saved_message["receiver_id"],
            "message": saved_message["message"],
            "created_at": saved_message["created_at"]
        },
        room=room_id
    )


# =========================================================
# DELETE PROFILE
# =========================================================

@app.route("/delete_profile", methods=["POST"])
def delete_profile():

    if "student_id" not in session:

        return redirect(url_for("login"))

    student_id = session["student_id"]

    conn = get_db()

    # Delete messages
    conn.execute("""
        DELETE FROM messages
        WHERE sender_id = ?
        OR receiver_id = ?
    """, (
        student_id,
        student_id
    ))

    # Delete notifications
    conn.execute("""
        DELETE FROM notifications
        WHERE student_id = ?
    """, (
        student_id,
    ))

    # Delete team memberships
    conn.execute("""
        DELETE FROM team_members
        WHERE student_id = ?
    """, (
        student_id,
    ))

    # Delete skills
    conn.execute("""
        DELETE FROM skills
        WHERE student_id = ?
    """, (
        student_id,
    ))

    # Delete connections
    conn.execute("""
        DELETE FROM connections
        WHERE sender_id = ?
        OR receiver_id = ?
    """, (
        student_id,
        student_id
    ))

    # Delete teams created by student
    created_teams = conn.execute("""
        SELECT id
        FROM teams
        WHERE created_by = ?
    """, (
        student_id,
    )).fetchall()

    for team in created_teams:

        conn.execute("""
            DELETE FROM team_members
            WHERE team_id = ?
        """, (
            team["id"],
        ))

    conn.execute("""
        DELETE FROM teams
        WHERE created_by = ?
    """, (
        student_id,
    ))

    # Delete student
    conn.execute("""
        DELETE FROM students
        WHERE id = ?
    """, (
        student_id,
    ))

    conn.commit()
    conn.close()

    session.clear()

    return redirect(url_for("index"))


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def page_not_found(error):

    return """
    <h1>404 - Page Not Found</h1>
    <p>The page you are looking for does not exist.</p>
    """, 404


@app.errorhandler(500)
def internal_server_error(error):

    return """
    <h1>500 - Internal Server Error</h1>
    <p>Something went wrong on the server.</p>
    """, 500


# =========================================================
# INITIALIZE DATABASE
# =========================================================

init_db()


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    socketio.run(
        app,
        debug=True,
        host="127.0.0.1",
        port=5000
    )