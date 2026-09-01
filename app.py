from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
app.secret_key = "change-this-secret-key"
DB_PATH = Path(__file__).with_name("secondary_portal.db")

def db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init_db():
    c = db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS students (
        student_id TEXT PRIMARY KEY, name TEXT NOT NULL, gender TEXT NOT NULL,
        date_of_birth TEXT, class_name TEXT NOT NULL, stream TEXT NOT NULL,
        academic_year TEXT NOT NULL, admission_date TEXT, address TEXT,
        status TEXT NOT NULL DEFAULT 'Active'
    );
    CREATE TABLE IF NOT EXISTS parents (
        parent_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
        contact TEXT NOT NULL, gender TEXT NOT NULL, relationship TEXT, email TEXT
    );
    CREATE TABLE IF NOT EXISTS student_parents (
        student_id TEXT NOT NULL, parent_id INTEGER NOT NULL, relationship TEXT,
        PRIMARY KEY(student_id,parent_id),
        FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE,
        FOREIGN KEY(parent_id) REFERENCES parents(parent_id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS subjects (
        subject_code TEXT PRIMARY KEY, subject_name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE IF NOT EXISTS marks (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL,
        subject_code TEXT NOT NULL, marks REAL NOT NULL, grade TEXT NOT NULL,
        term TEXT NOT NULL, academic_year TEXT NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(student_id,subject_code,term,academic_year),
        FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE,
        FOREIGN KEY(subject_code) REFERENCES subjects(subject_code) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS fee_structure (
        id INTEGER PRIMARY KEY AUTOINCREMENT, class_name TEXT NOT NULL,
        term TEXT NOT NULL, academic_year TEXT NOT NULL, amount REAL NOT NULL,
        description TEXT, UNIQUE(class_name,term,academic_year)
    );
    CREATE TABLE IF NOT EXISTS payments (
        payment_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL,
        amount REAL NOT NULL, term TEXT NOT NULL, academic_year TEXT NOT NULL,
        payment_method TEXT NOT NULL, reference TEXT, payment_date TEXT NOT NULL,
        FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS notifications (
        notification_id INTEGER PRIMARY KEY AUTOINCREMENT, student_id TEXT NOT NULL,
        parent_id INTEGER NOT NULL, notification_type TEXT NOT NULL,
        message TEXT NOT NULL, sent_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Sent',
        FOREIGN KEY(student_id) REFERENCES students(student_id) ON DELETE CASCADE,
        FOREIGN KEY(parent_id) REFERENCES parents(parent_id) ON DELETE CASCADE
    );
    """)
    c.commit(); c.close()

def grade(v):
    v=float(v)
    return "A" if v>=80 else "B" if v>=70 else "C" if v>=60 else "D" if v>=50 else "F"

@app.route("/")
def dashboard():
    c=db()
    counts={x:c.execute(f"SELECT COUNT(*) FROM {x}").fetchone()[0]
            for x in ("students","parents","subjects","marks","payments","notifications")}
    c.close()
    return render_template("dashboard.html",counts=counts)

@app.route("/students",methods=["GET","POST"])
def students():
    c=db()
    if request.method=="POST":
        try:
            c.execute("""INSERT INTO students
            (student_id,name,gender,date_of_birth,class_name,stream,academic_year,admission_date,address,status)
            VALUES(?,?,?,?,?,?,?,?,?,?)""",tuple(request.form.get(k,"").strip() for k in
            ("student_id","name","gender","date_of_birth","class_name","stream","academic_year","admission_date","address","status")))
            c.commit(); flash("Student registered successfully.","success")
        except sqlite3.IntegrityError:
            flash("Student number already exists. Student numbers must be unique.","error")
        finally: c.close()
        return redirect(url_for("students"))
    rows=c.execute("SELECT * FROM students ORDER BY name").fetchall(); c.close()
    return render_template("students.html",students=rows)

@app.route("/parents",methods=["GET","POST"])
def parents():
    c=db()
    if request.method=="POST":
        try:
            f=request.form
            cur=c.execute("INSERT INTO parents(name,contact,gender,relationship,email) VALUES(?,?,?,?,?)",
                          (f["name"].strip(),f["contact"].strip(),f["gender"],f["relationship"],f.get("email","").strip()))
            c.execute("INSERT INTO student_parents(student_id,parent_id,relationship) VALUES(?,?,?)",
                      (f["student_id"],cur.lastrowid,f["relationship"]))
            c.commit(); flash("Parent saved and linked to the student.","success")
        except sqlite3.IntegrityError as e:
            c.rollback(); flash(f"Parent could not be saved: {e}","error")
        finally: c.close()
        return redirect(url_for("parents"))
    students=c.execute("SELECT student_id,name FROM students ORDER BY name").fetchall()
    parents=c.execute("""SELECT p.*,sp.student_id,s.name student_name
                         FROM parents p LEFT JOIN student_parents sp ON sp.parent_id=p.parent_id
                         LEFT JOIN students s ON s.student_id=sp.student_id ORDER BY p.name""").fetchall()
    c.close(); return render_template("parents.html",students=students,parents=parents)

@app.route("/marks",methods=["GET","POST"])
def marks():
    c=db()
    if request.method=="POST":
        try:
            f=request.form; v=float(f["marks"])
            if not 0<=v<=100: raise ValueError
            c.execute("""INSERT INTO marks(student_id,subject_code,marks,grade,term,academic_year,created_at)
                         VALUES(?,?,?,?,?,?,?) ON CONFLICT(student_id,subject_code,term,academic_year)
                         DO UPDATE SET marks=excluded.marks,grade=excluded.grade,created_at=excluded.created_at""",
                      (f["student_id"],f["subject_code"],v,grade(v),f["term"],f["academic_year"],
                       datetime.now().isoformat(timespec="seconds")))
            c.commit(); flash("Mark saved successfully.","success")
        except (ValueError,sqlite3.IntegrityError): flash("Invalid mark or academic information.","error")
        finally: c.close()
        return redirect(url_for("marks"))
    students=c.execute("SELECT student_id,name FROM students ORDER BY name").fetchall()
    subjects=c.execute("SELECT subject_code,subject_name FROM subjects ORDER BY subject_name").fetchall()
    rows=c.execute("""SELECT m.*,s.name student_name,sub.subject_name FROM marks m
                      JOIN students s ON s.student_id=m.student_id JOIN subjects sub ON sub.subject_code=m.subject_code
                      ORDER BY s.name,m.term,sub.subject_name""").fetchall()
    c.close(); return render_template("marks.html",students=students,subjects=subjects,marks=rows)

@app.route("/subjects",methods=["POST"])
def add_subject():
    c=db()
    try:
        c.execute("INSERT INTO subjects VALUES(?,?)",(request.form["subject_code"].strip(),request.form["subject_name"].strip()))
        c.commit(); flash("Subject added successfully.","success")
    except sqlite3.IntegrityError: flash("Subject code or name already exists.","error")
    finally: c.close()
    return redirect(url_for("marks"))

@app.route("/fees",methods=["GET","POST"])
def fees():
    c=db()
    if request.method=="POST":
        try:
            f=request.form
            c.execute("""INSERT INTO fee_structure(class_name,term,academic_year,amount,description)
                         VALUES(?,?,?,?,?) ON CONFLICT(class_name,term,academic_year)
                         DO UPDATE SET amount=excluded.amount,description=excluded.description""",
                      (f["class_name"].strip(),f["term"],f["academic_year"].strip(),float(f["amount"]),f.get("description","").strip()))
            c.commit(); flash("Fee structure saved.","success")
        except (ValueError,sqlite3.IntegrityError): flash("Invalid fee information.","error")
        finally: c.close()
        return redirect(url_for("fees"))
    fees=c.execute("SELECT * FROM fee_structure ORDER BY academic_year DESC,class_name,term").fetchall()
    payments=c.execute("""SELECT p.*,s.name student_name FROM payments p JOIN students s ON s.student_id=p.student_id
                         ORDER BY p.payment_date DESC,p.payment_id DESC""").fetchall()
    students=c.execute("SELECT student_id,name FROM students ORDER BY name").fetchall()
    c.close(); return render_template("fees.html",fees=fees,payments=payments,students=students)

@app.route("/payments",methods=["POST"])
def payments():
    c=db()
    try:
        f=request.form
        c.execute("""INSERT INTO payments(student_id,amount,term,academic_year,payment_method,reference,payment_date)
                     VALUES(?,?,?,?,?,?,?)""",(f["student_id"],float(f["amount"]),f["term"],f["academic_year"],
                     f["payment_method"],f.get("reference",""),f.get("payment_date") or datetime.now().date().isoformat()))
        c.commit(); flash("Payment recorded.","success")
    except (ValueError,sqlite3.IntegrityError): flash("Payment could not be recorded.","error")
    finally: c.close()
    return redirect(url_for("fees"))

@app.route("/notifications",methods=["GET","POST"])
def notifications():
    c=db()
    if request.method=="POST":
        try:
            f=request.form
            linked=c.execute("SELECT 1 FROM student_parents WHERE student_id=? AND parent_id=?",
                             (f["student_id"],f["parent_id"])).fetchone()
            if not linked: raise ValueError("Selected parent is not linked to this student.")
            c.execute("""INSERT INTO notifications(student_id,parent_id,notification_type,message,sent_at,status)
                         VALUES(?,?,?,?,?,?)""",(f["student_id"],int(f["parent_id"]),f["notification_type"],
                         f["message"].strip(),datetime.now().isoformat(timespec="seconds"),"Sent"))
            c.commit(); flash("Notification saved successfully.","success")
        except (ValueError,sqlite3.IntegrityError): c.rollback(); flash("Notification could not be saved.","error")
        finally: c.close()
        return redirect(url_for("notifications"))
    students=c.execute("SELECT student_id,name FROM students ORDER BY name").fetchall()
    rows=c.execute("""SELECT n.*,s.name student_name,p.name parent_name,p.contact
                      FROM notifications n JOIN students s ON s.student_id=n.student_id
                      JOIN parents p ON p.parent_id=n.parent_id ORDER BY n.sent_at DESC""").fetchall()
    c.close(); return render_template("notifications.html",students=students,notifications=rows)

@app.route("/api/student/<student_id>/parents")
def student_parents(student_id):
    c=db(); rows=c.execute("""SELECT p.parent_id,p.name,p.contact,p.relationship FROM parents p
                              JOIN student_parents sp ON sp.parent_id=p.parent_id WHERE sp.student_id=?
                              ORDER BY p.name""",(student_id,)).fetchall(); c.close()
    return jsonify({"parents":[dict(r) for r in rows]})

with app.app_context(): init_db()

if __name__=="__main__":
    app.run(debug=True)
