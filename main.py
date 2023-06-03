import telebot
from dotenv import load_dotenv, find_dotenv
from telebot import formatting
from telebot.types import BotCommand
import concurrent.futures
from flask import Flask, request
import os
from waitress import serve
import requests
import json
from revChatGPT.V3 import Chatbot

main = Flask(__name__)

load_dotenv(find_dotenv())

chat_gpt = os.getenv("CHAT_GPT")
telegram_token = os.getenv("TELEGRAM_TOKEN")
host_url = os.getenv("HOST_URL")

bot = telebot.TeleBot(telegram_token)

chatbot = Chatbot(api_key=chat_gpt)


@main.route(f'/{telegram_token}', methods=['POST'])
def handle_telegram_webhook():
  update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
  if update.message and update.message.text:
    print(update.message.chat.id)
    bot.process_new_messages([update.message])
  return 'OK', 201


bot.set_my_commands(commands=[
  BotCommand("start", "Welcome 🙌"),
  BotCommand("gpt", "Help 🛡"),
])


@bot.message_handler(commands=['start'])
def welcome(message):
  bot.send_chat_action(message.chat.id, "typing")
  bot.reply_to(
    message, """\
Hello @%s ! 😊 How are you ?\n
""" % message.from_user.username)


gpt_chats = []


@bot.message_handler(content_types=['text'])
def chat_gpt(message):
  if message.chat.type in ['private']:
    command = message.text
    print(command)
    bot.send_chat_action(message.chat.id, "typing")
    msg = bot.send_message(message.chat.id, "🌀 Processing...")
    for data in chatbot.ask_stream(command):
      gpt_chats.append(data)
      print(data, end=" ", flush=True)

    output = ''.join(gpt_chats)
    info = f"✅ Process Complete...\n\n{output} "
    bot.edit_message_text(chat_id=message.chat.id,
                          message_id=msg.message_id,
                          text=info,parse_mode="Markdown")
    gpt_chats.clear()


functions = [welcome, chat_gpt]
with concurrent.futures.ThreadPoolExecutor() as executor:
  results = executor.map(lambda func: func, functions)

for t in results:
  print(t)

if __name__ == '__main__':
  print('🟢 BOT IS ONLINE')
  bot.set_webhook(url=f'{host_url}/{telegram_token}')
  serve(main, host='0.0.0.0', port=int(os.environ.get('PORT', 6100)))
