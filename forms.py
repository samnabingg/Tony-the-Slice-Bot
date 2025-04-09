from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, DataRequired, Length, Email, EqualTo, Regexp

class SignupForm(FlaskForm):
    username = StringField("Username", validators=[
        InputRequired(),
        Length(min=4, max=20),
        Regexp(r'^[A-Za-z]+$', message="Username must contain only letters")
    ])
    email = StringField("Email", validators=[
        InputRequired(),
        Email()
    ])
    phone = StringField("Phone Number", validators=[
        InputRequired(),
        Regexp(r'^\d{10}$', message="Phone number must be 10 digits")
    ])
    password = PasswordField("Password", validators=[
        InputRequired(),
        Length(min=6)
    ])
    confirm_password = PasswordField("Confirm Password", validators=[
        InputRequired(),
        EqualTo('password', message="Passwords must match")
    ])
    submit = SubmitField("Sign Up")


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[
        DataRequired(),
        Length(min=1, max=20),
        Regexp(r'^[A-Za-z]+$', message="Username must contain only letters")
    ])
    password = PasswordField("Password", validators=[
        DataRequired()
    ])
    submit = SubmitField("Login")
