from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(max=20),
        Regexp(r'^[A-Za-z]+$', message="Username must contain only letters")
    ])
    phone_number = StringField('Phone Number', validators=[
        DataRequired(),
        Length(min=10, max=10),
        Regexp(r'^\d{10}$', message="Phone number must be 10 digits")
    ])
    submit = SubmitField('Login')
