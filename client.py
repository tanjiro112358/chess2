import pygame
import socket
import json
import threading
import os
from cryptography.hazmat.primitives.asymmetric import dh
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import padding, hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.asymmetric.dh import DHParameterNumbers, DHPublicNumbers
import tkinter as tk
from tkinter import messagebox, simpledialog


class ChessClient:
    def __init__(self):
        pygame.init()

        # Screen settings
        self.WINDOW_WIDTH = 1200
        self.WINDOW_HEIGHT = 800
        self.BOARD_SIZE = 720
        self.SQUARE_SIZE = self.BOARD_SIZE // 9

        # Colors
        self.WHITE = (255, 255, 255)
        self.BLACK = (0, 0, 0)
        self.LIGHT_BROWN = (240, 217, 181)
        self.DARK_BROWN = (181, 136, 99)
        self.HIGHLIGHT = (255, 255, 0, 128)
        self.SELECTED = (0, 255, 0, 128)
        self.BLUE = (100, 149, 237)
        self.GRAY = (128, 128, 128)
        self.RED = (255, 0, 0)
        self.GREEN = (0, 255, 0)
        self.YELLOW = (255, 255, 0)

        # Initialize display
        self.screen = pygame.display.set_mode((self.WINDOW_WIDTH, self.WINDOW_HEIGHT))
        pygame.display.set_caption("Professional Chess Game - 9x9 with 2 Queens")
        self.clock = pygame.time.Clock()

        # Game state
        self.board = [[None for _ in range(9)] for _ in range(9)]
        self.selected_square = None
        self.valid_moves = []
        self.game_state = "menu"  # menu, lobby, waiting, playing
        self.player_color = None
        self.current_turn = "white"
        self.opponent_name = ""
        self.username = ""
        self.user_stats = {}
        self.in_check = False
        self.in_queue = False

        # Network
        self.socket = None
        self.connected = False
        self.aes_key = None

        # Load pieces
        self.pieces = {}
        self.load_pieces()

        # UI elements
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
        self.large_font = pygame.font.Font(None, 48)
        self.title_font = pygame.font.Font(None, 60)

        # Menu buttons
        self.menu_buttons = {
            'login': pygame.Rect(500, 300, 200, 50),
            'register': pygame.Rect(500, 370, 200, 50),
            'reset_password': pygame.Rect(500, 440, 200, 50),
            'quit': pygame.Rect(500, 510, 200, 50)
        }

        # Lobby buttons
        self.lobby_buttons = {
            'join_queue': pygame.Rect(50, 700, 150, 50),
            'leave_queue': pygame.Rect(220, 700, 150, 50),
            'logout': pygame.Rect(1000, 700, 150, 50)
        }

        # Game buttons
        self.game_buttons = {
            'resign': pygame.Rect(950, 600, 100, 40),
            'back_to_lobby': pygame.Rect(950, 650, 150, 40)
        }

    def load_pieces(self):
        """Load chess piece images with high-quality fallbacks"""
        piece_names = [
            'black_king', 'black_queen', 'black_rook', 'black_bishop',
            'black_knight', 'black_pawn',
            'white_king', 'white_queen', 'white_rook', 'white_bishop',
            'white_knight', 'white_pawn'
        ]

        for piece_name in piece_names:
            try:
                image_path = os.path.join('assets', f'{piece_name}.png')
                if os.path.exists(image_path):
                    image = pygame.image.load(image_path)
                    self.pieces[piece_name] = pygame.transform.scale(image,
                                                                     (self.SQUARE_SIZE - 10, self.SQUARE_SIZE - 10))
                else:
                    # Create professional text-based piece
                    surface = pygame.Surface((self.SQUARE_SIZE - 10, self.SQUARE_SIZE - 10))
                    color = self.WHITE if 'white' in piece_name else self.BLACK
                    bg_color = self.BLACK if 'white' in piece_name else self.WHITE
                    surface.fill(bg_color)

                    # Add border
                    pygame.draw.rect(surface, color, surface.get_rect(), 3)

                    # Add piece symbol
                    piece_symbols = {
                        'king': '♔', 'queen': '♕', 'rook': '♖',
                        'bishop': '♗', 'knight': '♘', 'pawn': '♙'
                    }
                    piece_type = piece_name.split('_')[1]
                    symbol = piece_symbols.get(piece_type, piece_type[0].upper())

                    font = pygame.font.Font(None, 48)
                    text_surface = font.render(symbol, True, color)
                    text_rect = text_surface.get_rect(center=(surface.get_width() // 2, surface.get_height() // 2))
                    surface.blit(text_surface, text_rect)

                    self.pieces[piece_name] = surface

            except Exception as e:
                print(f"Error loading piece {piece_name}: {e}")
                # Create minimal fallback
                surface = pygame.Surface((self.SQUARE_SIZE - 10, self.SQUARE_SIZE - 10))
                color = self.WHITE if 'white' in piece_name else self.BLACK
                surface.fill(color)
                self.pieces[piece_name] = surface

    def connect_to_server(self, host='10.100.102.43', port=8888):
        """Connect to chess server with encryption setup"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))

            # Receive server's public key data
            server_data_len = int.from_bytes(self.socket.recv(4), 'big')
            server_data_bytes = b''
            while len(server_data_bytes) < server_data_len:
                chunk = self.socket.recv(server_data_len - len(server_data_bytes))
                if not chunk:
                    raise ConnectionError("Server disconnected during key exchange")
                server_data_bytes += chunk

            server_data_json = server_data_bytes.decode('utf-8')
            server_public_data = json.loads(server_data_json)

            # Create DH parameters from received data
            param_numbers = DHParameterNumbers(
                server_public_data['p'],
                server_public_data['g']
            )
            parameters = param_numbers.parameters()

            # Generate client keypair
            private_key = parameters.generate_private_key()
            public_key = private_key.public_key()

            # Send client's public key data
            public_numbers = public_key.public_numbers()
            client_public_data = {
                'y': public_numbers.y,
                'p': public_numbers.parameter_numbers.p,
                'g': public_numbers.parameter_numbers.g
            }

            client_data_json = json.dumps(client_public_data)
            client_data_bytes = client_data_json.encode('utf-8')

            self.socket.send(len(client_data_bytes).to_bytes(4, 'big'))
            self.socket.send(client_data_bytes)

            # Reconstruct server's public key
            server_public_numbers = DHPublicNumbers(
                server_public_data['y'],
                param_numbers
            )
            server_public_key = server_public_numbers.public_key()

            # Calculate shared secret
            shared_secret = private_key.exchange(server_public_key)

            # Generate AES key
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=b'chess_salt',
                iterations=100000,
            )
            self.aes_key = kdf.derive(shared_secret)

            self.connected = True

            # Start receiving thread
            receive_thread = threading.Thread(target=self.receive_messages)
            receive_thread.daemon = True
            receive_thread.start()

            return True

        except Exception as e:
            return False

    def encrypt_message(self, message):
        """Encrypt message using AES-CBC"""
        iv = os.urandom(16)
        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(iv))
        encryptor = cipher.encryptor()

        # Pad message
        padder = padding.PKCS7(128).padder()
        padded_data = padder.update(message.encode()) + padder.finalize()

        encrypted = encryptor.update(padded_data) + encryptor.finalize()
        return iv + encrypted

    def decrypt_message(self, encrypted_data):
        """Decrypt message using AES-CBC"""
        iv = encrypted_data[:16]
        encrypted = encrypted_data[16:]

        cipher = Cipher(algorithms.AES(self.aes_key), modes.CBC(iv))
        decryptor = cipher.decryptor()

        padded_data = decryptor.update(encrypted) + decryptor.finalize()

        # Unpad message
        unpadder = padding.PKCS7(128).unpadder()
        data = unpadder.update(padded_data) + unpadder.finalize()

        return data.decode()

    def send_message(self, message):
        """Send encrypted message to server"""
        if not self.connected:
            return False

        try:
            encrypted_message = self.encrypt_message(json.dumps(message))
            self.socket.send(len(encrypted_message).to_bytes(4, 'big'))
            self.socket.send(encrypted_message)
            return True
        except Exception as e:
            return False

    def receive_messages(self):
        """Receive messages from server"""
        while self.connected:
            try:
                msg_len = int.from_bytes(self.socket.recv(4), 'big')
                if msg_len == 0:
                    break

                encrypted_data = self.socket.recv(msg_len)
                decrypted_msg = self.decrypt_message(encrypted_data)
                message = json.loads(decrypted_msg)

                self.handle_server_message(message)

            except Exception as e:
                break

        self.connected = False

    def handle_server_message(self, message):
        """Handle messages from server"""
        msg_type = message.get('type')

        if msg_type == 'login_response':
            if message.get('success'):
                self.username = message['username']
                self.user_stats = message['stats']
                self.game_state = 'lobby'
            else:
                messagebox.showerror("Login Failed", message.get('message', 'Login failed'))

        elif msg_type == 'register_response':
            if message.get('success'):
                messagebox.showinfo("Registration", "Registration successful! Please login.")
            else:
                messagebox.showerror("Registration Failed", message.get('message', 'Registration failed'))

        elif msg_type == 'reset_response':
            if message.get('success'):
                messagebox.showinfo("Reset Code", "Reset code sent to your email!")
            else:
                messagebox.showerror("Reset Failed", message.get('message', 'Reset failed'))

        elif msg_type == 'reset_password_response':
            if message.get('success'):
                messagebox.showinfo("Password Reset", "Password reset successful! Please login.")
            else:
                messagebox.showerror("Reset Failed", message.get('message', 'Reset failed'))

        elif msg_type == 'queue_response':
            if message.get('success'):
                if 'Joined queue' in message.get('message', ''):
                    self.in_queue = True
                elif 'Left queue' in message.get('message', ''):
                    self.in_queue = False

        elif msg_type == 'game_start':
            self.player_color = message['color']
            self.opponent_name = message['opponent']
            self.game_state = 'playing'
            self.current_turn = 'white'
            self.in_queue = False
            self.initialize_board()

        elif msg_type == 'opponent_move':
            # Update board with opponent's move
            if 'board' in message:
                self.board = message['board']

            # Update turn
            if 'turn' in message:
                self.current_turn = message['turn']

            # Check if we're in check
            self.in_check = message.get('in_check', False)

        elif msg_type == 'move_response':
            if message.get('success'):
                # Check if game ended
                if message.get('game_over'):
                    return

                # Update board state from server
                if 'board' in message:
                    self.board = message['board']

                # Update turn
                if 'turn' in message:
                    self.current_turn = message['turn']

                # Update check status
                self.in_check = message.get('in_check', False)

                # Clear selection
                self.selected_square = None
                self.valid_moves = []
            else:
                messagebox.showerror("Invalid Move", message.get('message', 'Invalid move'))
                # Clear selection on invalid move
                self.selected_square = None
                self.valid_moves = []

        elif msg_type == 'game_end':
            result = message['result']
            reason = message.get('reason', '')

            if result == 'win':
                if reason == 'opponent_resigned':
                    messagebox.showinfo("Victory!", "You won! Your opponent resigned.")
                elif reason == 'opponent_disconnected':
                    messagebox.showinfo("Victory!", "You won! Your opponent disconnected.")
                elif reason == 'checkmate':
                    messagebox.showinfo("Victory!", "You won by checkmate! Excellent play!")
                else:
                    messagebox.showinfo("Victory!", f"You won! ({reason})")
            elif result == 'loss':
                if reason == 'checkmate':
                    messagebox.showinfo("Defeat", "You lost by checkmate. Better luck next time!")
                else:
                    messagebox.showinfo("Defeat", f"You lost! ({reason})")
            elif result == 'draw':
                if reason == 'stalemate':
                    messagebox.showinfo("Draw", "Game drawn by stalemate!")
                else:
                    messagebox.showinfo("Draw", f"Game drawn! ({reason})")

            self.game_state = 'lobby'
            self.reset_game_state()

        elif msg_type == 'error':
            messagebox.showerror("Server Error", message.get('message', 'Unknown server error'))

    def show_login_dialog(self):
        """Show login dialog"""
        root = tk.Tk()
        root.withdraw()

        username = simpledialog.askstring("Login", "Username:")
        if not username:
            root.destroy()
            return

        password = simpledialog.askstring("Login", "Password:", show='*')
        if not password:
            root.destroy()
            return

        root.destroy()

        if not self.connected:
            if not self.connect_to_server():
                messagebox.showerror("Connection Error", "Could not connect to server")
                return

        self.send_message({
            'type': 'login',
            'username': username,
            'password': password
        })

    def show_register_dialog(self):
        """Show registration dialog"""
        root = tk.Tk()
        root.withdraw()

        username = simpledialog.askstring("Register", "Choose a username:")
        if not username:
            root.destroy()
            return

        password = simpledialog.askstring("Register", "Choose a password:", show='*')
        if not password:
            root.destroy()
            return

        email = simpledialog.askstring("Register", "Enter your email address:")
        if not email:
            root.destroy()
            return

        root.destroy()

        if not self.connected:
            if not self.connect_to_server():
                messagebox.showerror("Connection Error", "Could not connect to server")
                return

        self.send_message({
            'type': 'register',
            'username': username,
            'password': password,
            'email': email
        })

    def show_reset_password_dialog(self):
        """Show password reset dialog"""
        root = tk.Tk()
        root.withdraw()

        email = simpledialog.askstring("Reset Password", "Enter your email address:")
        if not email:
            root.destroy()
            return

        if not self.connected:
            if not self.connect_to_server():
                messagebox.showerror("Connection Error", "Could not connect to server")
                root.destroy()
                return

        self.send_message({
            'type': 'request_reset',
            'email': email
        })

        # Get reset code
        code = simpledialog.askstring("Reset Code", "Enter the 6-digit code sent to your email:")
        if not code:
            root.destroy()
            return

        new_password = simpledialog.askstring("New Password", "Enter your new password:", show='*')
        if not new_password:
            root.destroy()
            return

        root.destroy()

        self.send_message({
            'type': 'reset_password',
            'email': email,
            'code': code,
            'new_password': new_password
        })

    def initialize_board(self):
        """Initialize the chess board"""
        self.board = [[None for _ in range(9)] for _ in range(9)]

        # Place white pieces
        self.board[8][0] = 'white_rook'
        self.board[8][1] = 'white_knight'
        self.board[8][2] = 'white_bishop'
        self.board[8][3] = 'white_queen'
        self.board[8][4] = 'white_king'
        self.board[8][5] = 'white_queen'
        self.board[8][6] = 'white_bishop'
        self.board[8][7] = 'white_knight'
        self.board[8][8] = 'white_rook'

        for i in range(9):
            self.board[7][i] = 'white_pawn'

        # Place black pieces
        self.board[0][0] = 'black_rook'
        self.board[0][1] = 'black_knight'
        self.board[0][2] = 'black_bishop'
        self.board[0][3] = 'black_queen'
        self.board[0][4] = 'black_king'
        self.board[0][5] = 'black_queen'
        self.board[0][6] = 'black_bishop'
        self.board[0][7] = 'black_knight'
        self.board[0][8] = 'black_rook'

        for i in range(9):
            self.board[1][i] = 'black_pawn'

    def reset_game_state(self):
        """Reset game state"""
        self.selected_square = None
        self.valid_moves = []
        self.player_color = None
        self.current_turn = "white"
        self.opponent_name = ""
        self.board = [[None for _ in range(9)] for _ in range(9)]
        self.in_check = False

    def get_square_from_pos(self, pos):
        """Get board square from mouse position"""
        x, y = pos

        board_x = (self.WINDOW_WIDTH - self.BOARD_SIZE) // 2
        board_y = (self.WINDOW_HEIGHT - self.BOARD_SIZE) // 2

        if (board_x <= x <= board_x + self.BOARD_SIZE and
                board_y <= y <= board_y + self.BOARD_SIZE):

            col = (x - board_x) // self.SQUARE_SIZE
            row = (y - board_y) // self.SQUARE_SIZE

            if 0 <= row < 9 and 0 <= col < 9:
                return (row, col)

        return None

    def handle_square_click(self, square):
        """Handle clicking on a chess square"""
        row, col = square
        piece = self.board[row][col]

        if self.selected_square is None:
            # Select piece if it belongs to current player and it's their turn
            if (piece and
                    piece.startswith(self.player_color) and
                    self.current_turn == self.player_color):
                self.selected_square = square
                self.calculate_valid_moves(square)
        else:
            # Try to move piece
            if square == self.selected_square:
                # Deselect
                self.selected_square = None
                self.valid_moves = []
            elif square in self.valid_moves:
                # Make move
                self.make_move(self.selected_square, square)
            else:
                # Select different piece
                if (piece and
                        piece.startswith(self.player_color) and
                        self.current_turn == self.player_color):
                    self.selected_square = square
                    self.calculate_valid_moves(square)
                else:
                    self.selected_square = None
                    self.valid_moves = []

    def calculate_valid_moves(self, from_square):
        """Calculate valid moves for selected piece (client-side preview)"""
        self.valid_moves = []
        row, col = from_square
        piece = self.board[row][col]

        if not piece:
            return

        piece_type = piece.split('_')[1]
        piece_color = piece.split('_')[0]

        # Generate moves based on piece type (simplified client-side validation)
        if piece_type == 'pawn':
            self.calculate_pawn_moves(from_square, piece_color)
        elif piece_type == 'rook':
            self.calculate_rook_moves(from_square, piece_color)
        elif piece_type == 'knight':
            self.calculate_knight_moves(from_square, piece_color)
        elif piece_type == 'bishop':
            self.calculate_bishop_moves(from_square, piece_color)
        elif piece_type == 'queen':
            self.calculate_queen_moves(from_square, piece_color)
        elif piece_type == 'king':
            self.calculate_king_moves(from_square, piece_color)

    def calculate_pawn_moves(self, from_square, color):
        """Calculate pawn moves"""
        row, col = from_square
        direction = -1 if color == 'white' else 1

        # Forward move
        new_row = row + direction
        if 0 <= new_row < 9 and self.board[new_row][col] is None:
            self.valid_moves.append((new_row, col))

            # Double move from starting position
            if ((color == 'white' and row == 7) or (color == 'black' and row == 1)):
                new_row = row + 2 * direction
                if 0 <= new_row < 9 and self.board[new_row][col] is None:
                    self.valid_moves.append((new_row, col))

        # Diagonal captures
        for dc in [-1, 1]:
            new_row, new_col = row + direction, col + dc
            if (0 <= new_row < 9 and 0 <= new_col < 9):
                target = self.board[new_row][new_col]
                if target and not target.startswith(color):
                    self.valid_moves.append((new_row, new_col))

    def calculate_rook_moves(self, from_square, color):
        """Calculate rook moves"""
        row, col = from_square
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]

        for dr, dc in directions:
            for i in range(1, 9):
                new_row, new_col = row + i * dr, col + i * dc
                if not (0 <= new_row < 9 and 0 <= new_col < 9):
                    break

                target = self.board[new_row][new_col]
                if target is None:
                    self.valid_moves.append((new_row, new_col))
                elif not target.startswith(color):
                    self.valid_moves.append((new_row, new_col))
                    break
                else:
                    break

    def calculate_knight_moves(self, from_square, color):
        """Calculate knight moves"""
        row, col = from_square
        moves = [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)]

        for dr, dc in moves:
            new_row, new_col = row + dr, col + dc
            if (0 <= new_row < 9 and 0 <= new_col < 9):
                target = self.board[new_row][new_col]
                if target is None or not target.startswith(color):
                    self.valid_moves.append((new_row, new_col))

    def calculate_bishop_moves(self, from_square, color):
        """Calculate bishop moves"""
        row, col = from_square
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dr, dc in directions:
            for i in range(1, 9):
                new_row, new_col = row + i * dr, col + i * dc
                if not (0 <= new_row < 9 and 0 <= new_col < 9):
                    break

                target = self.board[new_row][new_col]
                if target is None:
                    self.valid_moves.append((new_row, new_col))
                elif not target.startswith(color):
                    self.valid_moves.append((new_row, new_col))
                    break
                else:
                    break

    def calculate_queen_moves(self, from_square, color):
        """Calculate queen moves (combination of rook and bishop)"""
        self.calculate_rook_moves(from_square, color)
        self.calculate_bishop_moves(from_square, color)

    def calculate_king_moves(self, from_square, color):
        """Calculate king moves"""
        row, col = from_square
        moves = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]

        for dr, dc in moves:
            new_row, new_col = row + dr, col + dc
            if (0 <= new_row < 9 and 0 <= new_col < 9):
                target = self.board[new_row][new_col]
                if target is None or not target.startswith(color):
                    self.valid_moves.append((new_row, new_col))

    def make_move(self, from_square, to_square):
        """Send move to server and update local board optimistically"""
        from_row, from_col = from_square
        to_row, to_col = to_square

        moving_piece = self.board[from_row][from_col]
        captured_piece = self.board[to_row][to_col]

        # Make the move locally (optimistic update)
        self.board[to_row][to_col] = moving_piece
        self.board[from_row][from_col] = None

        # Clear selection immediately
        self.selected_square = None
        self.valid_moves = []

        # Send move to server
        success = self.send_message({
            'type': 'move',
            'from': from_square,
            'to': to_square
        })

        if not success:
            # Rollback the move if sending failed
            self.board[from_row][from_col] = moving_piece
            self.board[to_row][to_col] = captured_piece

    def join_queue(self):
        """Join matchmaking queue"""
        self.send_message({'type': 'join_queue'})

    def leave_queue(self):
        """Leave matchmaking queue"""
        self.send_message({'type': 'leave_queue'})

    def resign_game(self):
        """Resign current game"""
        if messagebox.askyesno("Resign", "Are you sure you want to resign? You will lose the game."):
            # Immediately return to lobby
            self.game_state = 'lobby'
            self.reset_game_state()

            # Send resign message to server (for opponent notification)
            self.send_message({'type': 'resign'})

            # Show result to player
            messagebox.showinfo("Game Over", "You resigned and lost the game.")

    def logout(self):
        """Logout and return to menu"""
        self.game_state = 'menu'
        self.username = ""
        self.user_stats = {}
        self.in_queue = False
        if self.connected:
            self.socket.close()
            self.connected = False

    def draw_board(self):
        """Draw the professional chess board"""
        board_x = (self.WINDOW_WIDTH - self.BOARD_SIZE) // 2
        board_y = (self.WINDOW_HEIGHT - self.BOARD_SIZE) // 2

        # Draw coordinate labels
        for i in range(9):
            # Row numbers (left side)
            label = str(9 - i)
            text_surface = self.small_font.render(label, True, self.BLACK)
            self.screen.blit(text_surface, (board_x - 25, board_y + i * self.SQUARE_SIZE + self.SQUARE_SIZE // 2))

            # Column letters (bottom)
            label = chr(ord('a') + i)
            text_surface = self.small_font.render(label, True, self.BLACK)
            self.screen.blit(text_surface,
                             (board_x + i * self.SQUARE_SIZE + self.SQUARE_SIZE // 2, board_y + self.BOARD_SIZE + 5))

        # Draw squares
        for row in range(9):
            for col in range(9):
                x = board_x + col * self.SQUARE_SIZE
                y = board_y + row * self.SQUARE_SIZE

                if (row + col) % 2 == 0:
                    color = self.LIGHT_BROWN
                else:
                    color = self.DARK_BROWN

                pygame.draw.rect(self.screen, color,
                                 (x, y, self.SQUARE_SIZE, self.SQUARE_SIZE))

                # Highlight selected square
                if self.selected_square == (row, col):
                    highlight_surface = pygame.Surface((self.SQUARE_SIZE, self.SQUARE_SIZE))
                    highlight_surface.set_alpha(128)
                    highlight_surface.fill(self.GREEN)
                    self.screen.blit(highlight_surface, (x, y))

                # Highlight valid moves
                elif (row, col) in self.valid_moves:
                    highlight_surface = pygame.Surface((self.SQUARE_SIZE, self.SQUARE_SIZE))
                    highlight_surface.set_alpha(64)
                    highlight_surface.fill(self.YELLOW)
                    self.screen.blit(highlight_surface, (x, y))

                # Draw piece
                piece = self.board[row][col]
                if piece and piece in self.pieces:
                    piece_rect = self.pieces[piece].get_rect()
                    piece_rect.center = (x + self.SQUARE_SIZE // 2, y + self.SQUARE_SIZE // 2)
                    self.screen.blit(self.pieces[piece], piece_rect)

    def draw_game_ui(self):
        """Draw game interface"""
        # Game info panel
        info_x = 50
        info_y = 50

        # Turn indicator
        turn_text = f"Current Turn: {self.current_turn.capitalize()}"
        if self.current_turn == self.player_color:
            turn_text += " (YOUR TURN)"
            turn_color = self.GREEN
        else:
            turn_text += " (Opponent's Turn)"
            turn_color = self.RED

        turn_surface = self.font.render(turn_text, True, turn_color)
        self.screen.blit(turn_surface, (info_x, info_y))

        # Check warning
        if self.in_check and self.current_turn == self.player_color:
            check_text = " YOU ARE IN CHECK!"
            check_surface = self.large_font.render(check_text, True, self.RED)
            check_rect = check_surface.get_rect(center=(self.WINDOW_WIDTH // 2, 30))

            # Draw warning background
            bg_rect = check_rect.inflate(40, 20)
            pygame.draw.rect(self.screen, self.YELLOW, bg_rect)
            pygame.draw.rect(self.screen, self.RED, bg_rect, 4)

            self.screen.blit(check_surface, check_rect)

        # Player info
        player_text = f"You: {self.player_color.capitalize()} • {self.username}"
        player_surface = self.font.render(player_text, True, self.BLACK)
        self.screen.blit(player_surface, (info_x, info_y + 40))

        opponent_text = f"Opponent: {self.opponent_name}"
        opponent_surface = self.font.render(opponent_text, True, self.BLACK)
        self.screen.blit(opponent_surface, (info_x, info_y + 80))

        # Selected piece info
        if self.selected_square:
            row, col = self.selected_square
            piece = self.board[row][col]
            coord = f"{chr(ord('a') + col)}{9 - row}"
            selected_text = f"Selected: {piece} at {coord}"
            selected_surface = self.small_font.render(selected_text, True, self.BLACK)
            self.screen.blit(selected_surface, (info_x, info_y + 120))

        # Game buttons
        for button_name, rect in self.game_buttons.items():
            pygame.draw.rect(self.screen, self.BLUE, rect)
            pygame.draw.rect(self.screen, self.BLACK, rect, 2)

            text = button_name.replace('_', ' ').title()
            text_surface = self.small_font.render(text, True, self.WHITE)
            text_rect = text_surface.get_rect(center=rect.center)
            self.screen.blit(text_surface, text_rect)

    def draw_menu(self):
        """Draw main menu"""
        self.screen.fill(self.WHITE)

        # Title
        title_text = "Professional Chess Game"
        title_surface = self.title_font.render(title_text, True, self.BLACK)
        title_rect = title_surface.get_rect(center=(self.WINDOW_WIDTH // 2, 150))
        self.screen.blit(title_surface, title_rect)

        # Subtitle
        subtitle_text = "9x9 Board • 2 Queens"
        subtitle_surface = self.font.render(subtitle_text, True, self.GRAY)
        subtitle_rect = subtitle_surface.get_rect(center=(self.WINDOW_WIDTH // 2, 200))
        self.screen.blit(subtitle_surface, subtitle_rect)


        # Draw menu buttons
        for button_name, rect in self.menu_buttons.items():
            pygame.draw.rect(self.screen, self.BLUE, rect)
            pygame.draw.rect(self.screen, self.BLACK, rect, 2)

            text = button_name.replace('_', ' ').title()
            text_surface = self.font.render(text, True, self.WHITE)
            text_rect = text_surface.get_rect(center=rect.center)
            self.screen.blit(text_surface, text_rect)

    def draw_lobby(self):
        """Draw lobby screen"""
        self.screen.fill(self.WHITE)

        # Welcome message
        welcome_text = f"Welcome back, {self.username}!"
        welcome_surface = self.large_font.render(welcome_text, True, self.BLACK)
        welcome_rect = welcome_surface.get_rect(center=(self.WINDOW_WIDTH // 2, 100))
        self.screen.blit(welcome_surface, welcome_rect)

        # Player statistics
        stats = self.user_stats
        stats_lines = [
            f"Rating: {stats.get('rating', 1200)}",
            f"Games Played: {stats.get('games_played', 0)}",
            f"Wins: {stats.get('wins', 0)} • Losses: {stats.get('losses', 0)} • Draws: {stats.get('draws', 0)}"
        ]

        if stats.get('games_played', 0) > 0:
            win_rate = (stats.get('wins', 0) / stats.get('games_played', 1)) * 100
            stats_lines.append(f"Win Rate: {win_rate:.1f}%")

        start_y = 150
        for i, line in enumerate(stats_lines):
            stats_surface = self.font.render(line, True, self.BLACK)
            stats_rect = stats_surface.get_rect(center=(self.WINDOW_WIDTH // 2, start_y + i * 35))
            self.screen.blit(stats_surface, stats_rect)

        # Queue status
        if self.in_queue:
            queue_text = "🔍 Searching for opponent..."
            queue_surface = self.large_font.render(queue_text, True, self.BLUE)
            queue_rect = queue_surface.get_rect(center=(self.WINDOW_WIDTH // 2, 400))
            self.screen.blit(queue_surface, queue_rect)

            # Animated dots
            import time
            dots = "." * (int(time.time() * 2) % 4)
            dots_surface = self.large_font.render(dots, True, self.BLUE)
            dots_rect = dots_surface.get_rect(center=(self.WINDOW_WIDTH // 2 + 150, 400))
            self.screen.blit(dots_surface, dots_rect)
        else:
            instruction_text = "Ready to play? Join the queue to find a match!"
            instruction_surface = self.font.render(instruction_text, True, self.BLACK)
            instruction_rect = instruction_surface.get_rect(center=(self.WINDOW_WIDTH // 2, 400))
            self.screen.blit(instruction_surface, instruction_rect)

        # Draw lobby buttons
        for button_name, rect in self.lobby_buttons.items():
            # Skip leave_queue button if not in queue
            if button_name == 'leave_queue' and not self.in_queue:
                continue
            # Skip join_queue button if in queue
            if button_name == 'join_queue' and self.in_queue:
                continue

            pygame.draw.rect(self.screen, self.BLUE, rect)
            pygame.draw.rect(self.screen, self.BLACK, rect, 2)

            text = button_name.replace('_', ' ').title()
            text_surface = self.font.render(text, True, self.WHITE)
            text_rect = text_surface.get_rect(center=rect.center)
            self.screen.blit(text_surface, text_rect)

    def handle_menu_click(self, pos):
        """Handle menu button clicks"""
        for button_name, rect in self.menu_buttons.items():
            if rect.collidepoint(pos):
                if button_name == 'login':
                    self.show_login_dialog()
                elif button_name == 'register':
                    self.show_register_dialog()
                elif button_name == 'reset_password':
                    self.show_reset_password_dialog()
                elif button_name == 'quit':
                    return False
        return True

    def handle_lobby_click(self, pos):
        """Handle lobby button clicks"""
        for button_name, rect in self.lobby_buttons.items():
            if rect.collidepoint(pos):
                if button_name == 'join_queue' and not self.in_queue:
                    self.join_queue()
                elif button_name == 'leave_queue' and self.in_queue:
                    self.leave_queue()
                elif button_name == 'logout':
                    self.logout()

    def handle_game_click(self, pos):
        """Handle game button clicks"""
        for button_name, rect in self.game_buttons.items():
            if rect.collidepoint(pos):
                if button_name == 'resign':
                    self.resign_game()
                elif button_name == 'back_to_lobby':
                    self.resign_game()  # Same as resign for now

    def run(self):
        """Main game loop"""
        running = True

        while running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:  # Left click
                        pos = pygame.mouse.get_pos()

                        if self.game_state == 'menu':
                            running = self.handle_menu_click(pos)

                        elif self.game_state == 'lobby':
                            self.handle_lobby_click(pos)

                        elif self.game_state == 'playing':
                            # Check if click is on game buttons
                            button_clicked = False
                            for rect in self.game_buttons.values():
                                if rect.collidepoint(pos):
                                    button_clicked = True
                                    break

                            if button_clicked:
                                self.handle_game_click(pos)
                            else:
                                # Handle board clicks
                                square = self.get_square_from_pos(pos)
                                if square:
                                    self.handle_square_click(square)

            # Clear screen
            self.screen.fill(self.WHITE)

            # Draw everything based on current state
            if self.game_state == 'menu':
                self.draw_menu()
            elif self.game_state == 'lobby':
                self.draw_lobby()
            elif self.game_state == 'playing':
                self.draw_board()
                self.draw_game_ui()

            # Update display
            pygame.display.flip()
            self.clock.tick(60)

        # Cleanup
        if self.connected:
            self.socket.close()
        pygame.quit()


if __name__ == "__main__":
    client = ChessClient()
    client.run()