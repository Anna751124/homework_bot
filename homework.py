import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


logger = logging.getLogger(__name__)


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    return all(
        value is not None for value in [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправка сообщения в Telegram-чат."""
    logger.info(f'Бот отправил сообщение: {message}')
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
        logger.debug(f'Бот отправил сообщение: {message}')
    except telegram.error.TelegramError as error:
        logger.error(f'Ошибка при отправке сообщения: {error}', exc_info=True)


def get_api_answer(current_timestamp):
    """Получаем ответ от API Практикума."""
    logger.info('Отправляем запрос к API Практикума')
    timestamp = current_timestamp
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except Exception:
        error = 'Проблемы с подключением к серверу'
        raise ConnectionError(error)
    if response.status_code != HTTPStatus.OK:
        error = (
            f'Эндпоинт {ENDPOINT} недоступен. '
            f'Код ответа API: {response.status_code}'
        )
        raise Exception(error)
    return response.json()


def check_response(response):
    """Проверка ответа от API на корректность."""
    logger.info('Начинаем проверку ответа сервера')
    if not isinstance(response, dict):
        error = 'Некорректный ответ от API - ожидался словарь'
        raise TypeError(error)
    if ('homeworks' not in response) or ('current_date' not in response):
        error = (
            'Некорректный ответ от API - '
            'в словаре отсутствует необходимый ключ'
        )
        raise KeyError(error)
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        error = (
            'Некорректный ответ от API - '
            '"homeworks" должен иметь тип list'
        )
        raise TypeError(error)
    return homeworks[0]


def parse_status(homework):
    """Получаем статус последней домашней работы."""
    if 'homework_name' not in homework.keys():
        error = (
            'Некорректный ответ от API - '
            'в словаре отсутствует ключ "homework_name"'
        )
        raise KeyError(error)
    homework_name = homework["homework_name"]
    if 'status' not in homework.keys():
        error = (
            'Некорректный ответ от API - '
            'в словаре отсутствует ключ "status"'
        )
        raise KeyError(error)
    status = homework["status"]
    if status not in HOMEWORK_VERDICTS:
        error = (
            'Некорректный ответ от API - '
            'недокументированный статус домашней работы'
        )
        raise KeyError(error)
    verdict = HOMEWORK_VERDICTS[status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if check_tokens():
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    else:
        logger.critical('Отсутствует обязательная переменная окружения')
        raise SystemExit('Программа принудительно остановлена.')
    current_timestamp = int(time.time())
    previous_message = ''
    message = ''
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks:
                message = parse_status(homeworks)
                if message != previous_message:
                    send_message(bot, message)
                    previous_message = message
            else:
                logger.debug('В ответе отсутствует новый статус')
            current_timestamp = response.get('current_date')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(message)
            if message != previous_message:
                send_message(bot, message)
                previous_message = message
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(stream=sys.stdout)
    logger.addHandler(handler)
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] -function %(funcName)s- '
        '-line %(lineno)d- %(message)s'
    )
    handler.setFormatter(formatter)
    main()
