import telebot
import requests
import json
from openai import OpenAI

TOKEN=open('utils/bottoken.conf', 'r').read().strip()
OPENAI_KEY=open('utils/openai.conf', 'r').read().strip()
ALLOWED_GROUPS=open('utils/groups.conf', 'r').read()

bot = telebot.TeleBot(TOKEN)

def moderate_content(text, image=None):
    reason = None
    client = OpenAI(api_key=OPENAI_KEY)
    if image and text:
        input=[
            {'type': 'text', 'text': text},
            {'type': 'image_url', 'image_url': {'url': image} }
        ]
    elif image and not text:
        input=[
            {'type': 'image_url', 'image_url': {'url': image} }
        ]
    else:
        input=text
    response = client.moderations.create(
        model='omni-moderation-latest',
        input = input
    )
    if response.results[0].flagged:
        for category in response.results[0].category_scores:
            if category[1] > 0.5:
                reason = f'{category[0]} {category[1]:.2f}\n'
    return reason

def check_result(response):
    result = []
    for category in response.json()['moderationCategories']:
        if category['confidence'] > 0.8:
            result.append(category)
    return result

def format_message(result):
    message = ''
    for category in result:
        message = f'{message}\n{category["name"]} {category["confidence"]}'
    return message

def get_admins(chatid):
    dest = []
    administrator = bot.get_chat_administrators(chatid)
    for admin in administrator:
        if not admin.user.is_bot:
            dest.append(admin.user.id)
    return dest

def notify(message, admin, result):
    chatid = str(message.chat.id).replace('-100', '')
    button = telebot.types.InlineKeyboardMarkup()
    #if message.chat.is_forum and not message.edit_date:
    #   url = f'https://t.me/c/{chatid}/{message.reply_to_message.id}/{message.id}'
    #else:
    url = f'https://t.me/c/{chatid}/{message.id}'
    btn_msg = telebot.types.InlineKeyboardButton('Ver mensagem 💬', url=url)
    btn_ignore = telebot.types.InlineKeyboardButton(
        'Ignorar alerta ✅',
        callback_data=f'ignore#{message.chat.id}#{message.id}'
    )
    message_body = (
        '⚠️ <b>Novo alerta</b>\n'
        f'👤 <code>{message.from_user.id}</code> '
        f'{message.from_user.first_name}\n'
        f'👥 <code>{message.chat.id}</code> '
        f'{message.chat.title}\n'
        f'<blockquote>{message.text}{message.caption}</blockquote>\n'
        f'📋<b>Motivos</b>:\n'
        f'<code>{result}</code>\n'
    )
    button.row(btn_msg, btn_ignore)
    #button.row(btn_ignore)
    try:
        telebot.util.antiflood(
            bot.send_message(
                admin,
                message_body.replace('None', ''),
                parse_mode='HTML',
                reply_markup=button
            )
        )
    except:
        pass

def react_to_message(
        chatid,
        messageid,
        react=[telebot.types.ReactionTypeEmoji('🤔')]
    ):
    try:
        telebot.util.antiflood(
            bot.set_message_reaction(
                chatid,
                messageid,
                react
            )
        )
    except:
        pass

@bot.message_handler(commands=['start'])
def start(message):
    msg = (
        f'<b>Olá, {message.from_user.first_name}</b>,\n' +
        'Sou um bot capaz de analisar o conteúdo de mensagens de um grupo ' +
        'e de avisar os administradores caso o conteúdo seja considerado ' +
        'ofensivo ou inadequado.\n'
        'Estou em <b>beta</b>, funcionando apenas em grupos específicos.\n'
        '@GabrielRF'
    )
    if message.chat.id < 0:
        return
    bot.send_message(
        message.chat.id,
        msg,
        parse_mode='HTML'
    )

@bot.callback_query_handler(func=lambda query: 'ignore' in query.data)
def ignore(query):
    bot.answer_callback_query(
        query.id,
        text='Feito.',
        show_alert=False
    )
    query_data = query.data.split('#')
    chatid = query_data[1]
    messageid = query_data[2]
    react_to_message(chatid, messageid, None)
    button_data = (query.message.json['reply_markup']['inline_keyboard'][0][0])
    button_text=button_data['text']
    button_link=button_data['url']
    btn_msg = telebot.types.InlineKeyboardButton(button_text, url=button_link)
    button = telebot.types.InlineKeyboardMarkup()
    button.row(btn_msg)
    bot.edit_message_text(
        text=query.message.html_text.replace('⚠️ <b>Novo alerta</b>', '🆗 <s>Novo alerta</s>'),
        chat_id=query.from_user.id,
        message_id=query.message.id,
        reply_markup=button,
        parse_mode='HTML'
    )

@bot.message_handler(chat_types=['group', 'supergroup'], content_types=['photo'])
@bot.edited_message_handler(chat_types=['group', 'supergroup'], content_types=['photo'])
def moderate_image(message):
    if str(message.chat.id) not in ALLOWED_GROUPS:
        return
    admins = get_admins(message.chat.id)
    if message.from_user.id in admins:
        return
    photo_url = f'https://api.telegram.org/file/bot{TOKEN}/{bot.get_file(message.photo[-1].file_id).file_path}'
    result = moderate_content(message.caption, photo_url)
    dest = []
    if result:
        for admin in admins:
            notify(message, admin, result)
        react_to_message(message.chat.id, message.message_id)
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

@bot.message_handler(chat_types=['group', 'supergroup'], content_types=['sticker'])
@bot.edited_message_handler(chat_types=['group', 'supergroup'], content_types=['sticker'])
def moderate_sticker(message):
    if str(message.chat.id) not in ALLOWED_GROUPS:
        return
    admins = get_admins(message.chat.id)
    if message.from_user.id in admins:
        return
    photo_url = f'https://api.telegram.org/file/bot{TOKEN}/{bot.get_file(message.sticker.file_id).file_path}'
    try:
        result = moderate_content(message.caption, photo_url)
    except:
        result = 0
    dest = []
    if result:
        for admin in admins:
            notify(message, admin, result)
        react_to_message(message.chat.id, message.message_id)
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except:
            pass

@bot.message_handler(chat_types=['group', 'supergroup'], content_types=['text'])
@bot.edited_message_handler(chat_types=['group', 'supergroup'], content_types=['text'])
def cmd_magic(message):
    if str(message.chat.id) not in ALLOWED_GROUPS:
        return
    admins = get_admins(message.chat.id)
    if message.from_user.id in admins:
        return
    result = moderate_content(message.text)
    dest = []
    if result:
        for admin in admins:
            notify(message, admin, result)
        react_to_message(message.chat.id, message.message_id)

if __name__ == "__main__":
    bot.infinity_polling()
