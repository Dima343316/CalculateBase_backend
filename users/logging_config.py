import os
import logging
from logging.handlers import RotatingFileHandler


def setup_logger(name: str):
    """
    Настройка логгера с консольным выводом и ротацией логов в файл.
    Логи сохраняются в папке `logs`.
    :param name: Имя логгера (обычно __name__).
    :return: Настроенный логгер.
    """
    # Указываем папку для логов
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)  # Создаём папку, если её нет

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # Формат логов
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Обработчик для записи логов в файл с ротацией
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=3  # До 3 резервных копий
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)

    # Добавляем обработчики к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger

__all__ = ()
