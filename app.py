import logging
from telebot import TeleBot, types
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup
import os
from dotenv import load_dotenv
import openai
from sql import safe_db_execute
from validatephone import validate_phone

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# Инициализация OpenAI клиента
openai.api_base = "https://openrouter.ai/api/v1"
openai.api_key = os.getenv("OPENROUTER_API_KEY")

# Инициализация бота с хранилищем состояний
storage = StateMemoryStorage()
bot = TeleBot(os.getenv('TELEGRAM_TOKEN'), state_storage=storage)


# Определение состояний
class DialogStates(StatesGroup):
    waiting_for_lesson = State()
    waiting_for_roots = State()
    waiting_for_goods = State()
    waiting_for_commandments = State()


def generate_ai_response(prompt, context=""):
    """Генерация ответа через OpenAI API"""
    try:
        messages = [{
            "role": "system",
            "content": "Ты мудрый раввин, который помогает с вопросами о еврейских традициях."
        }]

        if context:
            messages.append({"role": "assistant", "content": context})

        messages.append({"role": "user", "content": prompt})

        response = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=messages,
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {str(e)}")
        return "⚠️ Извините, не могу обработать запрос сейчас. Пожалуйста, попробуйте позже."


@bot.message_handler(commands=['start'])
def start(message):
    try:
        bot.delete_state(message.from_user.id, message.chat.id)

        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton('📖 Уроки Торы', callback_data='lessons'),
            types.InlineKeyboardButton('🌳 Поиск корней', callback_data='roots_help'),
            types.InlineKeyboardButton('🛍️ Еврейские товары', callback_data='jewish_goods'),
            types.InlineKeyboardButton('❓ Консультация по еврейским вопросам', callback_data='commandments_help')
        ]
        markup.add(*buttons)

        welcome_msg = """
        ✡️ *Шалом!* ✡️

Я ваш виртуальный помощник по еврейским традициям. 
Чем могу помочь сегодня?

Выберите одну из опций ниже:
        """

        bot.send_message(
            chat_id=message.chat.id,
            text=welcome_msg,
            reply_markup=markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Ошибка в /start: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ *Ошибка!* Пожалуйста, попробуйте позже.", parse_mode='Markdown')


@bot.message_handler(commands=['help'])
def help(message):
    try:
        help_msg = """
        🆘 *Помощь*

Если у вас возникли вопросы или проблемы, пожалуйста:
1. Опишите вашу проблему
2. Напишите нам @support_username
3. Мы ответим в ближайшее время!

Спасибо за обращение! 🙏
        """
        bot.send_message(message.chat.id, help_msg)
    except Exception as e:
        logger.error(f"Ошибка в /help: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ *Ошибка!* Пожалуйста, попробуйте позже.", parse_mode='Markdown')


@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        if call.data == 'lessons':
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton(
                "➡️ Перейти к урокам",
                url="https://example.com/torah-lessons"
            )
            markup.add(btn)
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text="📚 *Уроки Торы*\n\nНажмите кнопку ниже для перехода к урокам:",
                reply_markup=markup,
                parse_mode='Markdown'
            )

        elif call.data == 'roots_help':
            bot.set_state(call.from_user.id, DialogStates.waiting_for_roots, call.message.chat.id)
            roots_msg = """
            🌳 *Поиск еврейских корней*

Пожалуйста, отправьте ваши данные в формате:
*Имя НомерТелефона*

Пример: 
Моше 89161234567 или Давид +79161234567

Мы свяжемся с вами для уточнения деталей.
            """
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=roots_msg,
                parse_mode='Markdown'
            )

        elif call.data == 'jewish_goods':
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton(
                "🛒 Перейти в магазин",
                url="https://example.com/jewish-goods"
            )
            markup.add(btn)
            goods_msg = """
            🛍️ *Еврейские товары*

Каждый еврей должен иметь:
- Кипы
- Талиты
- Мезузы
- Ханукии
- И другие религиозные атрибуты

Нажмите кнопку ниже, чтобы перейти в наш магазин:
            """
            bot.send_message(
                call.message.chat.id,
                text=goods_msg,
                reply_markup=markup,
                parse_mode='Markdown'
            )

        elif call.data == 'commandments_help':
            bot.set_state(call.from_user.id, DialogStates.waiting_for_commandments, call.message.chat.id)
            commandments_msg = """
            ✡️ *Консультация по еврейским вопросам*

Опишите ваш вопрос подробно, и наш мудрец даст вам развернутый ответ согласно традициям.

Примеры вопросов:
- Как правильно соблюдать шаббат?
- Какие есть законы кашрута?
- Как проводить еврейскую свадьбу?
            """
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=commandments_msg,
                parse_mode='Markdown'
            )

        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Ошибка callback: {str(e)}")
        bot.send_message(call.message.chat.id, "⚠️ *Ошибка!* Пожалуйста, попробуйте снова.", parse_mode='Markdown')

def is_state(message, state_class):
    current_state = bot.get_state(message.from_user.id, message.chat.id)
    return current_state == state_class.name

@bot.message_handler(func=lambda message: is_state(message, DialogStates.waiting_for_roots))
def process_roots(message):
    try:
        parts = message.text.strip().split()
        if len(parts) < 2:
            error_msg = """
            ❌ *Неверный формат*

Пожалуйста, укажите *имя и номер телефона* через пробел.

Пример:
Авраам 89161234567 или Сара +79161234567
            """
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return

        name = ' '.join(parts[:-1])
        number = parts[-1]

        if not validate_phone(number):
            error_msg = """
            ❌ *Неверный номер телефона*

Пожалуйста, используйте один из форматов:
- `89161234567`
- `+79161234567`

Попробуйте еще раз:
            """
            bot.reply_to(message, error_msg, parse_mode='Markdown')
            return

        exists = safe_db_execute(
            "SELECT 1 FROM roots WHERE id = ? LIMIT 1",
            (message.from_user.id,),
            fetch=True
        )

        if exists:
            bot.reply_to(message, "ℹ️ Вы уже оставляли заявку. Мы скоро с вами свяжемся!", parse_mode='Markdown')
        else:
            success = safe_db_execute(
                "INSERT INTO roots (id, name, number) VALUES (?, ?, ?)",
                (message.from_user.id, name, number)
            )

            if success:
                success_msg = """
                ✅ *Спасибо за заявку!*

Ваши данные:
- *Имя:* {}
- *Телефон:* {}

Мы свяжемся с вами в ближайшее время! 📞
                """.format(name, number)
                bot.reply_to(message, success_msg, parse_mode='Markdown')
            else:
                bot.reply_to(message, "⚠️ *Ошибка сохранения!* Пожалуйста, попробуйте позже.", parse_mode='Markdown')

        bot.delete_state(message.from_user.id, message.chat.id)
        logger.info(f"Processed roots: {name} {number}")
    except Exception as e:
        logger.error(f"Ошибка обработки корней: {str(e)}", exc_info=True)
        bot.send_message(message.chat.id, "⚠️ *Ошибка обработки!* Пожалуйста, попробуйте позже.", parse_mode='Markdown')
        bot.delete_state(message.from_user.id, message.chat.id)

@bot.message_handler(func=lambda message: is_state(message, DialogStates.waiting_for_commandments))
def process_commandments(message):
    try:
        prompt = f"Пользователь спрашивает о соблюдении еврейских законов: {message.text}. Объясните подробно как правильно соблюдать."
        response = generate_ai_response(prompt)

        formatted_response = f"""
        ✡️ *Ответ на ваш вопрос* ✡️

{response}

Если у вас остались вопросы, не стесняйтесь задавать их! 🙏
        """
        bot.send_message(message.chat.id, formatted_response, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка обработки заповедей: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ *Ошибка обработки!* Пожалуйста, попробуйте позже.", parse_mode='Markdown')
        bot.delete_state(message.from_user.id, message.chat.id)

@bot.message_handler(content_types=['text'])
def text(message):
    try:
        bot.delete_state(message.from_user.id, message.chat.id)

        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton('📖 Уроки Торы', callback_data='lessons'),
            types.InlineKeyboardButton('🌳 Поиск корней', callback_data='roots_help'),
            types.InlineKeyboardButton('🛍️ Еврейские товары', callback_data='jewish_goods'),
            types.InlineKeyboardButton('❓ Консультация', callback_data='commandments_help')
        ]
        markup.add(*buttons)

        nav_msg = """
        🔍 *Навигация*

Используйте кнопки ниже для выбора нужного раздела:
        """
        bot.send_message(
            chat_id=message.chat.id,
            text=nav_msg,
            reply_markup=markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        logger.error(f"Ошибка: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ *Ошибка!* Пожалуйста, попробуйте позже.", parse_mode='Markdown')

if __name__ == '__main__':
    logger.info("🚀 Запуск бота...")
    bot.infinity_polling()
    logger.info("🛑 Бот остановлен")