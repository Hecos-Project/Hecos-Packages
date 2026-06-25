import logging
from pathlib import Path
from colorama import Fore, Style, init

init(autoreset=True)

# Crea la directory logs se non esiste
LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE = LOGS_DIR / "hpm_builder.log"

logger = logging.getLogger("HPM_Builder")
logger.setLevel(logging.DEBUG)

# File handler (dettagliato)
file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
file_handler.setFormatter(file_fmt)

logger.addHandler(file_handler)

def log_info(msg):
    logger.info(msg)
    print(f"{Fore.GREEN}[INFO]{Style.RESET_ALL} {msg}")

def log_warn(msg):
    logger.warning(msg)
    print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} {msg}")

def log_error(msg):
    logger.error(msg)
    print(f"{Fore.RED}[ERROR]{Style.RESET_ALL} {msg}")

def log_debug(msg):
    logger.debug(msg)
    # Su console stampiamo i debug solo in grigio (se necessario)
    # print(f"{Fore.LIGHTBLACK_EX}[DEBUG]{Style.RESET_ALL} {msg}")
