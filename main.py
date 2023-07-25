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
import random
from typing import Dict
from typing import List
import regex
from PIL import Image, ImageFilter
from io import BytesIO
import re
import string
from telebot import util
from telebot import formatting
from langchain.agents import Tool
from langchain.memory import ConversationBufferMemory
from langchain.chat_models import ChatOpenAI
from langchain.agents import initialize_agent
from langchain.tools import DuckDuckGoSearchRun

main = Flask(__name__)

load_dotenv(find_dotenv())

open_api = os.getenv("OPENAI_API_KEY")
telegram_token = os.getenv("TELEGRAM_TOKEN")
host_url = os.getenv("HOST_URL")
bard_token = os.getenv("BARD_TOKEN")
brave_key = os.getenv("BRAVE_KEY")

bot = telebot.TeleBot(telegram_token)

start_time = time.time()


@main.route('/')
def index():
  return {"STATUS": "RUNNING"}


@main.route(f'/{telegram_token}', methods=['POST'])
def handle_telegram_webhook():
  update = telebot.types.Update.de_json(request.stream.read().decode('utf-8'))
  if update.message and update.message.text:
    print(update.message.chat.id)
    bot.process_new_messages([update.message])
  return 'OK', 201


bot.set_my_commands(commands=[
  BotCommand("start", "Welcome 🙌"),
  BotCommand("art", "Prompt 🎨"),
  BotCommand("bard", "Prompt 🤖"),
  BotCommand("gpt", "Just send Prompt Without Slash 🤖"),
  BotCommand("search", "Internet Access 🌐"),
])


@bot.message_handler(commands=['start'])
def welcome(message):
  bot.send_chat_action(message.chat.id, "typing")
  bot.reply_to(
    message, """\n
Hello @%s ! 😊 How are you ?\n
""" % message.from_user.username)


#DALLE IMG GEN


@bot.message_handler(commands=['art'])
def art_bing(message):
  bot.send_chat_action(message.chat.id, "typing")
  print(message.from_user.username)
  print(message.from_user.id)
  msg = bot.send_message(message.chat.id,
                         "🌀 Processing...",
                         reply_to_message_id=message.message_id)

  # Save cookies to a JSON file
  with open('cookies.json', 'r') as file:
    cookies = json.load(file)

  if message.text == '/art':
    warn = f" Please Send Prompt : /art <PROMPT> "
    bot.edit_message_text(chat_id=message.chat.id,
                          message_id=msg.message_id,
                          text=warn,
                          parse_mode='Markdown')

  def generate_images(auth_cookie: str,
                      prompt: str,
                      all_cookies: List[Dict] = None,
                      output_folder: str = "") -> List[str]:
    """
      Generates image links using Microsoft Bing.
      Parameters:
          auth_cookie: str
          prompt: str
      Optional Parameters:
          debug_file: str
          quiet: bool
          all_cookies: List[Dict]
          output_folder: str
      Returns:
          List[str]: List of image links
      """
    if os.environ.get("BING_URL") == None:
      BING_URL = "https://www.bing.com"
    else:
      BING_URL = os.environ.get("BING_URL")

    # Generate random IP between range 13.104.0.0/14
    FORWARDED_IP = (
      f"13.{random.randint(104, 107)}.{random.randint(0, 255)}.{random.randint(0, 255)}"
    )

    HEADERS = {
      "accept":
      "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
      "accept-language": "en-US,en;q=0.9",
      "cache-control": "max-age=0",
      "content-type": "application/x-www-form-urlencoded",
      "referrer": "https://www.bing.com/images/create/",
      "origin": "https://www.bing.com",
      "user-agent":
      "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36 Edg/110.0.1587.63",
      "x-forwarded-for": FORWARDED_IP,
    }

    # Error messages
    error_timeout = "Your request has timed out."
    error_redirect = "Redirect failed"
    error_blocked_prompt = "Your prompt has been blocked by Bing. Try to change any bad words and try again."
    error_being_reviewed_prompt = "Your prompt is being reviewed by Bing. Try to change any sensitive words and try again."
    error_noresults = "Could not get results"
    error_unsupported_lang = "\nThis language is currently not supported by Bing"
    error_bad_images = "Bad images"
    error_no_images = "No images"
    #
    sending_message = "Sending request..."
    wait_message = "Waiting for results..."
    download_message = "\nDownloading images..."

    def get_images(auth_cookie: str, prompt: str) -> List[str]:
      """
          Fetches image links from Bing
          Parameters:
              auth_cookie: str
              prompt: str
          Returns:
              List[str]: List of image links
          """
      session: requests.Session = requests.Session()
      session.headers = HEADERS
      session.cookies.set("_U", auth_cookie)
      print(session.cookies)
      print(session.headers)

      print(sending_message)

      url_encoded_prompt = requests.utils.quote(prompt)
      payload = f"q={url_encoded_prompt}&qs=ds"

      # https://www.bing.com/images/create?q=<PROMPT>&rt=3&FORM=GENCRE
      url = f"{BING_URL}/images/create?q={url_encoded_prompt}&rt=4&FORM=GENCRE"
      response = session.post(
        url,
        allow_redirects=False,
        data=payload,
        timeout=200,
      )

      # check for content warning message
      if "this prompt is being reviewed" in response.text.lower():
        raise Exception(error_being_reviewed_prompt)

      if "this prompt has been blocked" in response.text.lower():
        raise Exception(error_blocked_prompt)

      if ("we're working hard to offer image creator in more languages"
          in response.text.lower()):
        raise Exception(error_unsupported_lang)

      if response.status_code != 302:
        # if rt4 fails, try rt3
        url = f"{BING_URL}/images/create?q={url_encoded_prompt}&rt=3&FORM=GENCRE"
        response = session.post(url, allow_redirects=False, timeout=200)
        if response.status_code != 302:
          raise Exception(error_redirect)

      # Get redirect URL
      redirect_url = response.headers["Location"].replace("&nfy=1", "")
      print(redirect_url)
      request_id = redirect_url.split("id=")[-1]
      print(request_id)
      session.get(f"{BING_URL}{redirect_url}")

      # https://www.bing.com/images/create/async/results/{ID}?q={PROMPT}
      polling_url = f"{BING_URL}/images/create/async/results/{request_id}?q={url_encoded_prompt}"

      print(wait_message)

      start_wait = time.time()
      while True:
        if int(time.time() - start_wait) > 200:
          raise Exception(error_timeout)

        print(".", end="", flush=True)

        response = session.get(polling_url)
        if response.status_code != 200:
          raise Exception(error_noresults)

        if not response.text or response.text.find("errorMessage") != -1:
          time.sleep(1)
          continue
        else:
          break

      # Use regex to search for src=""
      image_links = regex.findall(r'src="([^"]+)"', response.text)
      # Remove size limit
      normal_image_links = [link.split("?w=")[0] for link in image_links]
      # Remove duplicates
      normal_image_links = list(set(normal_image_links))

      # Bad images
      bad_images = [
        "https://r.bing.com/rp/in-2zU3AJUdkgbA.png",
        "https://r.bing.com/rp/in-2zZcIqYSOfjE.png",
        "https://r.bing.com/rp/in-2zZooGcXebJI.png",
        "https://r.bing.com/rp/in-2zqLAdgjwmcA.png",
        "https://r.bing.com/rp/in-2zT4oSI23NjE.png",
        "https://r.bing.com/rp/in-2zThiW5yCVXw.png",
      ]

      # Remove bad images
      normal_image_links = [
        link for link in normal_image_links if link not in bad_images
      ]

      print(download_message)

      if output_folder:
        if not os.path.exists(output_folder):
          os.makedirs(output_folder)
        image_paths = []
        for index, link in enumerate(normal_image_links):
          try:
            response = session.get(link, timeout=5)
            response.raise_for_status()
            image_path = os.path.join(output_folder, f"image_{index}.jpg")
            with open(image_path, "wb") as image_file:
              image_file.write(response.content)
            image_paths.append(image_path)
          except Exception as e:
            print(f"Error downloading image: {link} - {e}")
        return image_paths

      return normal_image_links

    try:
      images = get_images(auth_cookie, prompt)
      return images
    except Exception as e:

      print(f"\n{str(e)}\n")
      return []

  def start(auth_cookie: str, prompt: str, output_folder: str = ""):
    text = prompt.strip()
    print(text)

    image_links = generate_images(
      auth_cookie,
      prompt,
      output_folder=output_folder,
    )

    print(image_links)
    media_group = []
    limit = 4
    count = 0  # Counter variable to keep track of the number of images added

    for image_link in image_links:
      response = requests.get(image_link)
      original_image_buffer = BytesIO(response.content)

      # Open the image using PIL
      image = Image.open(original_image_buffer)

      # Get the dimensions of the image
      width, height = image.size

      # Calculate the cropping coordinates
      crop_top = 0
      crop_bottom = height - 51  # Crop 51 pixels from the bottom

      # Crop the image
      cropped_image = image.crop((0, crop_top, width, crop_bottom))

      # Save the cropped image to a buffer
      cropped_image_buffer = BytesIO()
      cropped_image.save(cropped_image_buffer, format='JPEG')

      # Seek to the beginning of the buffer
      cropped_image_buffer.seek(0)

      # Create an InputMediaPhoto object with the cropped image buffer
      cropped_media = telebot.types.InputMediaPhoto(media=cropped_image_buffer)

      if count >= limit:
        break  # Stop adding images to the media_group if the limit is reached

      # Add the media to the media group
      media_group.append(cropped_media)
      count += 1  # Increment the counter

    # Send the media group
    bot.send_media_group(message.chat.id, media_group)

    info = f"✅ Process Complete..."
    bot.edit_message_text(chat_id=message.chat.id,
                          message_id=msg.message_id,
                          text=info,
                          parse_mode='Markdown')

  auth_cookie = random.choice(cookies)
  text = message.text.replace('/art', '').strip()
  prompt = f'{text}'
  output_folder = ""

  start(auth_cookie, prompt, output_folder=output_folder)


ba_input, ba_output = [], []

@bot.message_handler(commands=['bard'])
def bard_chat(message):
  bot.send_chat_action(message.chat.id, "typing")
  username = message.from_user.username
  print("@", username)
  msg = bot.send_message(message.chat.id,
                         "🌀 Processing...",
                         reply_to_message_id=message.message_id)

  text = message.text.replace('/bard', '').strip()
  print(text)

  ba_input.append(text)

  print(ba_input)

  prompt = f'You are an assistant to a human, powered by a large language model trained by Google.\n\nYou are designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, you are able to generate human-like text based on the input you receive, allowing you to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand.\n\nYou are constantly learning and improving, and your capabilities are constantly evolving. You are able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. You have access to some personalized information provided by the human in the Context section below. Additionally, you are able to generate your own text based on the input you receive, allowing you to engage in discussions and provide explanations and descriptions on a wide range of topics.\n\nOverall, you are a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether the human needs help with a specific question or just wants to have a conversation about a particular topic, you are here to assist.\n\nContext:\n{ba_output}\n\nCurrent conversation:\n{ba_input}\nLast line:\nHuman: {text}\nYou:'

  s = requests.Session()

  req_id = int("".join(random.choices(string.digits, k=4)))

  headers = {
    "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.43"
  }

  s.cookies.set("__Secure-1PSID", bard_token)

  res = s.get(url="https://bard.google.com/", timeout=10)

  sn = re.search(r"SNlM0e\":\"(.*?)\"", res.text).group(1)
  print(sn)

  params = {
    "bl": "boq_assistant-bard-web-server_20230620.14_p0",
    "_reqid": str(req_id),
    "rt": "c",
  }

  input_text_struct = [[prompt]]
  # Create the data dictionary for the POST request

  data = {
    "f.req": json.dumps([None, json.dumps(input_text_struct)]),
    "at": sn,
  }

  bard_2_req = "https://bard.google.com/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate"

  resp = s.post(
    url=bard_2_req,
    params=params,
    data=data,
    headers=headers,
    timeout=1000,
  )

  print(resp.text)

  chat_data = json.loads(resp.content.splitlines()[3])[0][2]

  json_chat_data = json.loads(chat_data)

  images = []
  if len(json_chat_data) >= 3:
    if len(json_chat_data[4][0]) >= 4:
      if json_chat_data[4][0][4]:
        for img in json_chat_data[4][0][4]:
          images.append(img[0][0][0])
  results = {
    "content": json_chat_data[4][0][1][0],
    "conversation_id": json_chat_data[1][0],
    "response_id": json_chat_data[1][1],
    "factualityQueries": json_chat_data[3],
    "textQuery": json_chat_data[2][0] if json_chat_data[2] is not None else "",
    "choices": [{
      "id": i[0],
      "content": i[1]
    } for i in json_chat_data[4]],
    "images": images,
  }

  print(results)

  info = "🟡 Processing..."

  bot.edit_message_text(chat_id=message.chat.id,
                        message_id=msg.message_id,
                        text=info)

  ba_output.append(results)
  o = results['content']


  
  # Define the 'ba_output' list before using it

  print(o)
  print(len(o))

  splitted_text = util.smart_split(o, chars_per_string=3000)
  for text in splitted_text:
    for i in '*_`[**':
      new_text = text.replace(i, '\\' + i)
    bot.send_message(message.chat.id, new_text, parse_mode='Markdown')

  info = f"✅ Process Complete...\n\n@{message.from_user.username}"
  bot.edit_message_text(chat_id=message.chat.id,
                        message_id=msg.message_id,
                        text=info)

# Internet Access

@bot.message_handler(commands=['search'])
def search(message):
  if message.chat.type in ['private', 'supergroup', 'group']:
      bot.send_chat_action(message.chat.id, "typing")
      username = message.from_user.username
      print("@", username)
      msg = bot.send_message(message.chat.id,
                             "🌀 Processing...",
                             reply_to_message_id=message.message_id)

      prompt = message.text.replace('/search', '').strip()

      print(prompt)

      search = DuckDuckGoSearchRun()

      tools = [
        Tool(
          name="Current Search",
          func=search.run,
          description=
          "useful for when you need to answer questions about current events or the current state of the world"
        ),
      ]

      memory = ConversationBufferMemory(
                                        memory_key="chat_history",
                                        return_messages=True)

      llm = ChatOpenAI(openai_api_key=open_api,model="gpt-3.5-turbo-16k")

      agent_chain = initialize_agent(
        tools,
        llm,
        agent="chat-conversational-react-description",
        handle_parsing_errors="Check your output and make sure it conforms!",
        verbose=True,
        memory=memory)

      output = agent_chain.run(input=prompt)

      print(output)

      splitted_text = util.smart_split(output, chars_per_string=3000)
      for text in splitted_text:
        bot.send_message(message.from_user.id, text, parse_mode='Markdown')
      info = """✅ Process Complete...\n\n @%s """ % message.from_user.username
      bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=msg.message_id,
        text=info,
      )


inputs, outputs = [], []
block_words = ['/art', '/help', '/bard']


@bot.message_handler(content_types=['text'])
def cha_gpt_cus(message):
  if message.chat.type in ['private', 'supergroup', 'group']:
    if not any(word in message.text for word in block_words):
      bot.send_chat_action(message.chat.id, "typing")
      username = message.from_user.username
      print("@", username)
      msg = bot.send_message(message.chat.id,
                             "🌀 Processing...",
                             reply_to_message_id=message.message_id)
      prompt = message.text
      inputs.append(prompt)

      url = "https://api.openai.com/v1/chat/completions"

      headers = {
        "Authorization":
        f"Bearer {open_api}",
        "Content-Type":
        "application/json",
        "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.82"
      }

      data = {
        "model":
        "gpt-3.5-turbo-16k",
        "messages": [
          {
            "role":
            "assistant",
            "content":
            f'You are an assistant to a human, powered by a large language model trained by OpenAI.\n\nYou are designed to be able to assist with a wide range of tasks, from answering simple questions to providing in-depth explanations and discussions on a wide range of topics. As a language model, you are able to generate human-like text based on the input you receive, allowing you to engage in natural-sounding conversations and provide responses that are coherent and relevant to the topic at hand.\n\nYou are constantly learning and improving, and your capabilities are constantly evolving. You are able to process and understand large amounts of text, and can use this knowledge to provide accurate and informative responses to a wide range of questions. You have access to some personalized information provided by the human in the Context section below. Additionally, you are able to generate your own text based on the input you receive, allowing you to engage in discussions and provide explanations and descriptions on a wide range of topics.\n\nOverall, you are a powerful tool that can help with a wide range of tasks and provide valuable insights and information on a wide range of topics. Whether the human needs help with a specific question or just wants to have a conversation about a particular topic, you are here to assist.\n\nContext:\n{outputs}\n\nCurrent conversation:\n{inputs}\nLast line:\nHuman:{prompt}\nYou:',
          },
        ],
      }

      response = requests.post(url, headers=headers, json=data)

      # rich.print(json.dumps(response.json(), indent=4, sort_keys=False))

      info = "🟡 Processing..."

      bot.edit_message_text(chat_id=message.chat.id,
                            message_id=msg.message_id,
                            text=info)

      ob = response.json()

      outputs.append(ob)

      output = response.json()['choices'][0]['message']['content']

      splitted_text = util.smart_split(output, chars_per_string=3000)
      for text in splitted_text:
        bot.send_message(message.from_user.id, text, parse_mode='Markdown')
      info = """✅ Process Complete...\n\n @%s """ % message.from_user.username
      bot.edit_message_text(
        chat_id=message.chat.id,
        message_id=msg.message_id,
        text=info,
      )


functions = [welcome, cha_gpt_cus, search, art_bing, bard_chat]

with concurrent.futures.ThreadPoolExecutor() as executor:
  results = executor.map(lambda func: func, functions)

if __name__ == '__main__':
  print('🟢 BOT IS ONLINE')
  bot.set_webhook(url=f'{host_url}/{telegram_token}')
  serve(main, host='0.0.0.0', port=int(os.environ.get('PORT', 6100)))
