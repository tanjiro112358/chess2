# config.py - Configuration file for Chess Game

# Server Configuration
SERVER_HOST = '10.100.102.43'
SERVER_PORT = 8888

# Email Configuration (for password reset)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_USER = "scamersbait@gmail.com"  # Change this to your email
EMAIL_PASSWORD = "nnaf zqnm ffie niju"  # Change this to your Gmail app password

# Security Configuration
PEPPER = b"chess_game_pepper_2024_change_this_in"

# Database Configuration
USER_DATABASE_FILE = "users.pkl"

# Game Configuration
BOARD_SIZE = 9  # 9x9 board
QUEENS_PER_SIDE = 2

# Client Configuration
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 800
BOARD_PIXEL_SIZE = 720

# Colors (RGB)
COLORS = {
    'WHITE': (255, 255, 255),
    'BLACK': (0, 0, 0),
    'LIGHT_BROWN': (240, 217, 181),
    'DARK_BROWN': (181, 136, 99),
    'HIGHLIGHT': (255, 255, 0, 128),
    'SELECTED': (0, 255, 0, 128),
    'BLUE': (100, 149, 237),
    'GRAY': (128, 128, 128)
}

# Asset Configuration
ASSETS_FOLDER = "assets"
PIECE_NAMES = [
    'black_king', 'black_queen', 'black_rook', 'black_bishop',
    'black_knight', 'black_pawn',
    'white_king', 'white_queen', 'white_rook', 'white_bishop',
    'white_knight', 'white_pawn'
]

# Network Configuration
ENCRYPTION_ALGORITHM = "AES-256-CBC"
KEY_EXCHANGE = "Diffie-Hellman-2048"
HASH_ALGORITHM = "PBKDF2-HMAC-SHA256"
HASH_ITERATIONS = 10000

# Timeouts and Limits
CONNECTION_TIMEOUT = 30  # seconds
RESET_CODE_EXPIRY = 600  # 10 minutes in seconds
MAX_CONNECTIONS = 100