import logging
from telebot import TeleBot, types
from telebot.storage import StateMemoryStorage
from telebot.handler_backends import State, StatesGroup
import os
from dotenv import load_dotenv
import openai
from sql import safe_db_execute
from validatephone import validate_phone
import html
import re

# Настройка логгера (безопасное логирование)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.propagate = False  # Предотвращаем дублирование логов

# Безопасная загрузка переменных окружения
load_dotenv(override=False)

# Валидация критических переменных окружения
REQUIRED_ENV_VARS = ['TELEGRAM_TOKEN', 'OPENROUTER_API_KEY']
for var in REQUIRED_ENVARS:
    if not os.getenv(var):
        logger.critical(f"Отсутствует обязательная переменная окружения: {var}")
        raise EnvironmentError(f"Необходимо установить переменную окружения: {var}")

# Конфигурация OpenAI с проверками
openai.api_base = os.getenv("OPENAI_API_BASE", "https://openrouter.ai/api/v1")
openai.api_key = os.getenv("OPENROUTER_API_KEY")
if not openai.api_key:
    logger.critical("API ключ для OpenAI не найден!")
    raise ValueError("API ключ для OpenAI обязателен")

# Инициализация бота с безопасными настройками
storage = StateMemoryStorage()
bot = TeleBot(
    token=os.getenv('TELEGRAM_TOKEN'),
    state_storage=storage,
    num_threads=4,  # Ограничение параллельных потоков
    parse_mode='HTML'  # Безопасный режим разметки
)

# Ограничение длины вводимых данных
MAX_INPUT_LENGTH = 1000
MAX_NAME_LENGTH = 50
PHONE_NUMBER_LENGTH = 12

# Определение состояний с проверками
class DialogStates(StatesGroup):
    waiting_for_lesson = State()
    waiting_for_roots = State()
    waiting_for_goods = State()
    waiting_for_commandments = State()

def sanitize_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    """Очистка и проверка вводимых данных"""
    if not text or not isinstance(text, str):
        return ""
    
    # Удаление потенциально опасных символов и ограничение длины
    sanitized = html.escape(text.strip()[:max_length])
    return re.sub(r'[^\w\s\-.,!?а-яА-ЯёЁ]', '', sanitized)

def generate_ai_response(prompt: str, context: str = "") -> str:
    """Безопасная генерация ответа через OpenAI API"""
    try:
        if not prompt or len(prompt) > MAX_INPUT_LENGTH:
            raise ValueError("Недопустимая длина промпта")
            
        messages = [{
            "role": "system",
            "content": "Ты мудрый раввин, который помогает с вопросами о еврейских традициях."
        }]

        if context:
            safe_context = sanitize_input(context)
            messages.append({"role": "assistant", "content": safe_context})

        safe_prompt = sanitize_input(prompt)
        messages.append({"role": "user", "content": safe_prompt})

        response = openai.ChatCompletion.create(
            model="openai/gpt-3.5-turbo",
            messages=messages,
            max_tokens=1000,
            temperature=0.7,
            timeout=30  # Таймаут для запроса
        )
        
        if not response.choices:
            raise ValueError("Пустой ответ от API")
            
        return sanitize_input(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {str(e)}", exc_info=True)
        return "⚠️ Извините, не могу обработать запрос сейчас. Пожалуйста, попробуйте позже."

def is_state(message, state_class) -> bool:
    """Проверка состояния с обработкой ошибок"""
    try:
        current_state = bot.get_state(message.from_user.id, message.chat.id)
        return current_state == state_class.name
    except Exception as e:
        logger.error(f"Ошибка проверки состояния: {str(e)}")
        return False

@bot.message_handler(commands=['start'])
def start(message):
    try:
        # Очистка состояния и данных
        bot.delete_state(message.from_user.id, message.chat.id)

        # Создание безопасной клавиатуры
        markup = types.InlineKeyboardMarkup(row_width=1)
        buttons = [
            types.InlineKeyboardButton('📖 Уроки Торы', callback_data='lessons'),
            types.InlineKeyboardButton('🌳 Поиск корней', callback_data='roots_help'),
            types.InlineKeyboardButton('🛍️ Еврейские товары', callback_data='jewish_goods'),
            types.InlineKeyboardButton('❓ Консультация', callback_data='commandments_help')
        ]
        markup.add(*buttons)

        welcome_msg = """
        ✡️ <b>Шалом!</b> ✡️

Я ваш виртуальный помощник по еврейским традициям. 
Чем могу помочь сегодня?

Выберите одну из опций ниже:
        """
        bot.send_message(
            chat_id=message.chat.id,
            text=welcome_msg,
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка в /start: {str(e)}", exc_info=True)
        bot.send_message(message.chat.id, "⚠️ <b>Ошибка!</b> Пожалуйста, попробуйте позже.", parse_mode='HTML')

@bot.message_handler(commands=['help'])
def help_command(message):
    try:
        help_msg = """
        🆘 <b>Помощь</b>

Если у вас возникли вопросы или проблемы, пожалуйста:
1. Опишите вашу проблему
2. Напишите нам @support_username
3. Мы ответим в ближайшее время!

Спасибо за обращение! 🙏
        """
        bot.send_message(message.chat.id, help_msg, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка в /help: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ <b>Ошибка!</b> Пожалуйста, попробуйте позже.", parse_mode='HTML')

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        if not call.data or not call.message:
            raise ValueError("Невалидные данные callback")
            
        # Валидация callback данных
        valid_callbacks = ['lessons', 'roots_help', 'jewish_goods', 'commandments_help']
        if call.data not in valid_callbacks:
            logger.warning(f"Неизвестный callback: {call.data}")
            bot.answer_callback_query(call.id, "Неизвестная команда")
            return

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
                text="📚 <b>Уроки Торы</b>\n\nНажмите кнопку ниже для перехода к урокам:",
                reply_markup=markup,
                parse_mode='HTML'
            )

        elif call.data == 'roots_help':
            bot.set_state(call.from_user.id, DialogStates.waiting_for_roots, call.message.chat.id)
            roots_msg = """
            🌳 <b>Поиск еврейских корней</b>

Пожалуйста, отправьте ваши данные в формате:
<b>Имя НомерТелефона</b>

Пример: 
Моше 89161234567 или Давид +79161234567

Мы свяжемся с вами для уточнения деталей.
            """
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=roots_msg,
                parse_mode='HTML'
            )

        elif call.data == 'jewish_goods':
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton(
                "🛒 Перейти в магазин",
                url="https://example.com/jewish-goods"
            )
            markup.add(btn)
            goods_msg = """
            🛍️ <b>Еврейские товары</b>

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
                parse_mode='HTML'
            )

        elif call.data == 'commandments_help':
            bot.set_state(call.from_user.id, DialogStates.waiting_for_commandments, call.message.chat.id)
            commandments_msg = """
            ✡️ <b>Консультация по еврейским вопросам</b>

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
                parse_mode='HTML'
            )

        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Ошибка callback: {str(e)}", exc_info=True)
        try:
            bot.send_message(call.message.chat.id, "⚠️ <b>Ошибка!</b> Пожалуйста, попробуйте снова.", parse_mode='HTML')
        except:
            pass

@bot.message_handler(func=lambda message: is_state(message, DialogStates.waiting_for_roots))
def process_roots(message):
    try:
        if not message.text or len(message.text) > (MAX_NAME_LENGTH + PHONE_NUMBER_LENGTH + 1):
            error_msg = """
            ❌ <b>Неверный формат</b>

Пожалуйста, укажите <b>имя и номер телефона</b> через пробел.

Пример:
Авраам 89161234567 или Сара +79161234567
            """
            bot.reply_to(message, error_msg, parse_mode='HTML')
            return

        parts = message.text.strip().split()
        if len(parts) < 2:
            raise ValueError("Недостаточно данных")

        name = ' '.join(parts[:-1])
        number = parts[-1]

        # Валидация имени
        safe_name = sanitize_input(name, MAX_NAME_LENGTH)
        if not safe_name:
            raise ValueError("Невалидное имя")

        if not validate_phone(number):
            error_msg = """
            ❌ <b>Неверный номер телефона</b>

Пожалуйста, используйте один из форматов:
- <code>89161234567</code>
- <code>+79161234567</code>

Попробуйте еще раз:
            """
            bot.reply_to(message, error_msg, parse_mode='HTML')
            return

        # Проверка существующей заявки
        exists = safe_db_execute(
            "SELECT 1 FROM roots WHERE id = ? LIMIT 1",
            (message.from_user.id,),
            fetch=True
        )

        if exists:
            bot.reply_to(message, "ℹ️ Вы уже оставляли заявку. Мы скоро с вами свяжемся!", parse_mode='HTML')
        else:
            # Безопасное сохранение в базу
            success = safe_db_execute(
                "INSERT INTO roots (id, name, number) VALUES (?, ?, ?)",
                (message.from_user.id, safe_name, number)
            )

            if success:
                success_msg = f"""
                ✅ <b>Спасибо за заявку!</b>

Ваши данные:
- <b>Имя:</b> {safe_name}
- <b>Телефон:</b> {number}

Мы свяжемся с вами в ближайшее время! 📞
                """
                bot.reply_to(message, success_msg, parse_mode='HTML')
            else:
                raise Exception("Ошибка сохранения в базу")

        bot.delete_state(message.from_user.id, message.chat.id)
        logger.info(f"Обработана заявка на поиск корней от {message.from_user.id}")
    except Exception as e:
        logger.error(f"Ошибка обработки корней: {str(e)}", exc_info=True)
        bot.send_message(message.chat.id, "⚠️ <b>Ошибка обработки!</b> Пожалуйста, попробуйте позже.", parse_mode='HTML')
        bot.delete_state(message.from_user.id, message.chat.id)

@bot.message_handler(func=lambda message: is_state(message, DialogStates.waiting_for_commandments))
def process_commandments(message):
    try:
        if not message.text or len(message.text) > MAX_INPUT_LENGTH:
            raise ValueError("Невалидная длина вопроса")

        safe_question = sanitize_input(message.text)
        prompt = f"Пользователь спрашивает о соблюдении еврейских законов: {safe_question}. Объясните подробно как правильно соблюдать."
        response = generate_ai_response(prompt)

        formatted_response = f"""
        ✡️ <b>Ответ на ваш вопрос</b> ✡️

{response}

Если у вас остались вопросы, не стесняйтесь задавать их! 🙏
        """
        bot.send_message(message.chat.id, formatted_response, parse_mode='HTML')

    except Exception as e:
        logger.error(f"Ошибка обработки заповедей: {str(e)}", exc_info=True)
        bot.send_message(message.chat.id, "⚠️ <b>Ошибка обработки!</b> Пожалуйста, попробуйте позже.", parse_mode='HTML')
    finally:
        bot.delete_state(message.from_user.id, message.chat.id)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    try:
        # Очистка состояния при любом текстовом сообщении
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
        🔍 <b>Навигация</b>

Используйте кнопки ниже для выбора нужного раздела:
        """
        bot.send_message(
            chat_id=message.chat.id,
            text=nav_msg,
            reply_markup=markup,
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Ошибка обработки текста: {str(e)}", exc_info=True)
        bot.send_message(message.chat.id, "⚠️ <b>Ошибка!</b> Пожалуйста, попробуйте позже.", parse_mode='HTML')

if __name__ == '__main__':
    try:
        logger.info("🚀 Запуск бота...")
        bot.infinity_polling(timeout=60, long_polling_timeout=30)
    except Exception as e:
        logger.critical(f"Критическая ошибка: {str(e)}", exc_info=True)
    finally:
        logger.info("🛑 Бот остановлен")