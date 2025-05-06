from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header
import qrcode
import io
import base64

app = Flask(_name_)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ------------ Models ------------
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100))
    vehicle = db.Column(db.String(100))
    parking_time = db.Column(db.Integer)  # in minutes
    parking_type = db.Column(db.String(20))
    area = db.Column(db.String(20))
    slot = db.Column(db.String(20))
    start_time = db.Column(db.DateTime, default=datetime.utcnow)

# ------------ Email Helper ------------
def send_email(to, subject, body):
    sender = 'smartparkingvignan@gmail.com'  # use your real email
    password = 'twdt mgoa ldio fcvj'  # use app password (never share real)

    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = to
    msg['Subject'] = Header(subject, 'utf-8')
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to, msg.as_string())
    except Exception as e:
        print("Email error:", e)

# ------------ Reminder Scheduler ------------
def schedule_alert(email, end_time, name, slot, booking_id):
    reminder_time = end_time - timedelta(minutes=5)
    delay = (reminder_time - datetime.utcnow()).total_seconds()

    if delay < 0:
        return

    def alert():
        subject = "⏰ Parking Time Ending Soon"
        body = f"""Hi {name},

Your parking time for slot {slot} is ending in 5 minutes.

👉 To extend for a custom time:
http://localhost:5000/extend/{booking_id}

❌ To exit and free your slot:
http://localhost:5000/exit/{booking_id}

Thanks for using Smart Parking!"""
        send_email(email, subject, body)

    threading.Timer(delay, alert).start()

# ------------ Slot Assignment ------------
def assign_slot(area):
    booked = [b.slot for b in Booking.query.filter_by(area=area).all()]
    prefix = "front-" if area == "Front Gate" else "back-"
    for i in range(1, 16):
        slot_id = f"{prefix}{i}"
        if slot_id not in booked:
            return slot_id
    return None

# ------------ Routes ------------

@app.route('/')
def index():
    bookings = Booking.query.all()
    booked_slots = [b.slot for b in bookings]
    return render_template("index.html", booked_slots=booked_slots)

@app.route('/book', methods=['POST'])
def book():
    name = request.form['name']
    email = request.form['email']
    vehicle = request.form['vehicle']
    parking_time = int(request.form['time'])
    parking_type = request.form['type']
    area = request.form['area']

    slot = assign_slot(area)
    if not slot:
        return "❌ No available slots in selected area."

    booking = Booking(
        name=name,
        email=email,
        vehicle=vehicle,
        parking_time=parking_time,
        parking_type=parking_type,
        area=area,
        slot=slot
    )

    db.session.add(booking)
    db.session.commit()

    start = booking.start_time
    end = start + timedelta(minutes=parking_time)

    send_email(
        email,
        "✅ Parking Slot Booked",
        f"Hi {name},\n\nYour parking slot {slot} is confirmed for {parking_time} mins in {area}.\n\nThanks for using Smart Parking!"
    )

    schedule_alert(email, end, name, slot, booking.id)

    return redirect(url_for('index'))

@app.route('/extend/<int:booking_id>', methods=['GET'])
def extend_form(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template("extend.html", booking=booking)

@app.route('/extend/<int:booking_id>', methods=['POST'])
def extend_submit(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    extra_time = int(request.form['extra_time'])

    booking.parking_time += extra_time
    db.session.commit()

    new_end_time = booking.start_time + timedelta(minutes=booking.parking_time)
    schedule_alert(booking.email, new_end_time, booking.name, booking.slot, booking.id)

    rate = 10 if booking.parking_type == 'VIP' else 5
    total_price = (booking.parking_time // 10) * rate

    send_email(
        booking.email,
        "✅ Parking Extended",
        f"Hi {booking.name},\n\nYour parking time has been extended by {extra_time} minutes.\n\n📍 Slot: {booking.slot}\n🕒 Total Time: {booking.parking_time} minutes\n💸 Updated Price: ₹{total_price}"
    )

    return redirect(url_for('index'))

@app.route('/exit/<int:booking_id>')
def exit_parking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    send_email(
        booking.email,
        "🚗 Parking Session Ended",
        f"Hi {booking.name},\n\nYour parking session for slot {booking.slot} has ended.\n\nThanks for using Smart Parking!"
    )

    db.session.delete(booking)
    db.session.commit()

    return redirect(url_for('index'))

@app.route('/pay/<int:booking_id>')
def payment_qr(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    amount = "5.00"
    upi_id = "8309841877@ibl"
    payee_name = "Smart Parking"
    upi_link = f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount}&cu=INR"

    qr = qrcode.make(upi_link)
    img_io = io.BytesIO()
    qr.save(img_io, format='PNG')
    img_io.seek(0)
    qr_base64 = base64.b64encode(img_io.getvalue()).decode()

    return render_template('payment.html', booking=booking, qr_image=qr_base64, amount=amount)

@app.route('/payment_confirm/<int:booking_id>', methods=['POST'])
def payment_confirm(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    send_email(
        booking.email,
        "✅ Payment Received",
        f"Hi {booking.name},\n\nYour payment for slot {booking.slot} has been successfully received.\n\nThanks for using Smart Parking!"
    )

    return redirect(url_for('index'))

# ------------ Run App ------------
if _name_ == '_main_':
    with app.app_context():
        db.create_all()  # Ensure the database and tables are created
 import os 
port = int(os.environ.get("PORT", 5000)) 
app.run(debug=True, host='0.0.0.0', port=port)
