# TELEGPT

import telebot
from dotenv import load_dotenv, find_dotenv
from telebot.types import BotCommand
import concurrent.futures
from flask import Flask, request
import os
from waitress import serve
import requests
import json
import time
import rich

main = Flask(__name__)

load_dotenv(find_dotenv())

chat_gpt = os.getenv("CHAT_GPT")
telegram_token = os.getenv("TELEGRAM_TOKEN")
host_url = os.getenv("HOST_URL")

bot = telebot.TeleBot(telegram_token)

start_time = time.time()


@main.route(f'/{telegram_token}', methods=['POST'])
def handle_telegram_webhook():
  update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
  if update.message and update.message.text:
    print(update.message.chat.id)
    bot.process_new_messages([update.message])
  return 'OK', 201


bot.set_my_commands(commands=[
  BotCommand("start", "Welcome 🙌"),
])


@bot.message_handler(commands=['start'])
def welcome(message):
  bot.send_chat_action(message.chat.id, "typing")
  bot.reply_to(
    message, """\
Hello @%s ! 😊 How are you ?\n
""" % message.from_user.username)


inputs, outputs = [], []


@bot.message_handler(content_types=['text'])
def cha_gpt(message):
  if message.chat.type in ['private', 'supergroup', 'group'
                           ] and not '/art' in message.text:
    bot.send_chat_action(message.chat.id, "typing")
    username = message.from_user.username
    print("@", username)
    msg = bot.send_message(message.chat.id, "🌀 Processing...")
    prompt = message.text
    inputs.append(prompt)
    print(inputs)

    last_input, last_output = inputs[-1], outputs[-1] if outputs else None

    url = "https://api.openai.com/v1/chat/completions"

    headers = {
      "Authorization": f"Bearer {chat_gpt}",
      "Content-Type": "application/json",
    }

    data = {
      "model":
      "gpt-3.5-turbo",
      "messages": [
        {
          "role": "system",
          "content": "You are a helpful assistant.",
        },
        {
          "role": "user",
          "content": f'{prompt}',
        },
      ],
    }

    if last_input and last_output:
      data["messages"].append({
        "role":
        "assistant",
        "content":
        f'(based on my previous question: {last_input}, and your previous answer: {last_output})',
      })

    response = requests.post(url, headers=headers, json=data)

    info = "🟡 Processing...\n\n"

    bot.edit_message_text(chat_id=message.chat.id,
                          message_id=msg.message_id,
                          text=info,
                          parse_mode='Markdown')

    rich.print(json.dumps(response.json(), indent=4, sort_keys=False))

    output = response.json()['choices'][0]['message']['content']
    outputs.append(output)

    rich.print(output)

    info = f"✅ Process Complete...\n\n{output} "
    bot.edit_message_text(chat_id=message.chat.id,
                          message_id=msg.message_id,
                          text=info,
                          parse_mode='Markdown')



functions = [welcome, chat_gpt]

with concurrent.futures.ThreadPoolExecutor() as executor:
  results = executor.map(lambda func: func, functions)


if __name__ == '__main__':
  print('🟢 BOT IS ONLINE')
  bot.set_webhook(url=f'{host_url}/{telegram_token}')
  serve(main, host='0.0.0.0', port=int(os.environ.get('PORT', 6100)))
