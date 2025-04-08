# 🍕 Tony the Slice Bot

A smart, serverless pizza chatbot web application built with **Flask**, **Dialogflow**, and **MySQL**. Users can log in, view a menu, earn reward points, and place pizza orders either through a traditional web UI or a conversational chatbot powered by Dialogflow.

---

## 🚀 Features

- 🔐 User login with session management
- 🍽️ View menu and place orders
- 💬 Conversational ordering with Dialogflow chatbot
- 🎁 Loyalty points and rewards system
- 🧠 Chatbot logs orders to the same backend DB as web UI
- 🧾 Order summaries and tracking
- ☁️ Fully integrated Flask backend and HTML/CSS frontend

---

## 🛠️ Technologies Used

- **Backend**: Python (Flask), PyMySQL, Flask-WTF
- **Frontend**: HTML, CSS, JavaScript
- **Chatbot**: Google Dialogflow Messenger
- **Database**: MySQL
- **Dev Tools**: Git, GitHub

---

## 💡 How It Works

1. User logs in with a username and phone number.
2. Orders can be placed:
   - Through the traditional web menu
   - Or via chatbot (Dialogflow Messenger embedded on the site)
3. Chatbot logs orders in `chatbot_logs`, then submits them to the `orders` table upon confirmation.
4. User earns reward points and can redeem them for deals!

---

## 🖥️ How to Run Locally

1. **Clone the repo**
   ```bash
   git clone https://github.com/samnabingg/Tony-the-Slice-Bot.git
   cd Tony-the-Slice-Bot
